"""
Authoritative Database Bridge and Round Scheduler Service for Combat Engine (§10.1, §10.5, §19, FR-07).
Connects the pure domain CombatEngine to Django models with strict row locking and idempotency.
"""

import logging
from typing import Any, Dict, List

from django.core.exceptions import ValidationError
from django.db import OperationalError, connection, transaction
from django.db.models import Count
from django.utils import timezone

from apps.combat.engine import CombatEngine, CombatState, RoundResult
from apps.combat.scoring import ScoringService, calculate_team_score
from apps.economy.models import CoinTransaction, TransactionType
from apps.matches.clock import lifecycle_payload, open_planning_window
from apps.matches.defaults import DEFAULT_MATCH_CONFIGURATION
from apps.matches.models import Match, MatchEvent, MatchStatus
from apps.matches.services import MatchService
from apps.questions.models import TeamQuestion
from apps.teams.models import Team
from apps.units.models import (
    ActionStatus,
    EntityCategory,
    EntityStatus,
    GameAction,
    GameEntity,
)

logger = logging.getLogger(__name__)


class CombatService:
    """
    Authoritative state management and persistence for combat rounds.
    """

    @classmethod
    def execute_combat_round(cls, match: Match, expected_round: int | None = None, resolved_at=None) -> RoundResult:
        import time

        for attempt in range(8):
            try:
                return cls._execute_combat_round_atomic(match, expected_round, resolved_at)
            except OperationalError as exc:
                if connection.vendor != "sqlite" or "locked" not in str(exc).lower() or attempt == 7:
                    raise
                time.sleep(0.02 * (attempt + 1))
        raise RuntimeError("Combat transaction retry exhausted")

    @classmethod
    @transaction.atomic
    def _execute_combat_round_atomic(cls, match: Match, expected_round: int | None = None, resolved_at=None) -> RoundResult:
        """
        Locks the match row, aggregates current game state, delegates resolution
        to the pure CombatEngine, and atomically writes back all state changes (§10.1).
        Guarantees idempotency via row-locking and monotonic round sequence numbers (§10.5).
        """
        match_locked = Match.objects.select_for_update().get(pk=match.pk)

        config = match_locked.configuration or DEFAULT_MATCH_CONFIGURATION
        if config.get("gameplay_mode") == "CONTINUOUS":
            raise ValidationError("Continuous battles are advanced by the server tick scheduler.")
        current_round = config.get("current_round", 1)
        # Retrying the same explicit round replays its persisted result, including
        # after match completion. The lock serializes competing workers on Postgres.
        if expected_round is not None and expected_round != current_round:
            previous = MatchEvent.objects.filter(
                match=match_locked, event_type="COMBAT_RESOLVED",
                payload__round_number=expected_round,
            ).first()
            if previous:
                p = previous.payload
                return RoundResult(expected_round, p["events"], None,
                                   p["eliminated_team_ids"], p["winner_team_id"], p["is_match_over"])
            raise ValidationError("Round không còn hiện hành; hãy đồng bộ trạng thái.")

        if match_locked.status == MatchStatus.FINISHED:
            raise ValidationError("Trận đấu đã kết thúc, không thể giải quyết round chiến đấu.")

        if match_locked.status == MatchStatus.PAUSED:
            raise ValidationError("Trận đấu đang tạm dừng (PAUSED). Hãy tiếp tục trước khi giải quyết round.")

        if match_locked.status != MatchStatus.ACTIVE or match_locked.phase in ("LOBBY", "RESULTS"):
            raise ValidationError("Combat requires an active match in a playable phase.")

        timer = config.setdefault("timer_state", {})
        timer["round_phase"] = "LOCKED"
        logger.info("round_locked match=%s round=%s", match.pk, current_round, extra={"match_id": str(match.pk), "round_number": current_round})

        config = match_locked.configuration or DEFAULT_MATCH_CONFIGURATION
        current_round = config.get("current_round", 1)

        # 1. Fetch and lock all teams
        teams_qs = Team.objects.select_for_update().filter(match=match_locked).order_by("created_at", "id")
        teams_map: Dict[str, Dict[str, Any]] = {}
        for idx, t in enumerate(teams_qs):
            teams_map[str(t.id)] = {
                "id": str(t.id),
                "name": t.name,
                "team_index": idx + 1,
                "base_hp": t.base_hp,
                "initial_base_hp": t.initial_base_hp,
                "base_shield": t.base_shield,
                "coins": t.coins,
                "score": t.score,
                "status": t.status,
                "shield_remaining_rounds": config.get("active_shields", {}).get(str(t.id), 2 if t.base_shield else 0),
            }

        # 2. Fetch active and queued entities
        entities_qs = (
            GameEntity.objects.select_for_update(of=("self",))
            .filter(match=match_locked, status__in=[EntityStatus.ACTIVE, EntityStatus.QUEUED, EntityStatus.DISABLED])
            .select_related("unit_type")
        )
        entities_list: List[Dict[str, Any]] = []
        for e in entities_qs:
            base_stats = e.unit_type.base_stats or {}
            dmg = base_stats.get("damage", 10)
            from apps.combat.balance import entity_attack_range
            rng = entity_attack_range(e)
            mov = base_stats.get("movement", 1 if e.entity_kind == EntityCategory.UNIT else 0)

            entities_list.append({
                "id": str(e.id),
                "team_id": str(e.team_id),
                "unit_type_code": e.unit_type.code,
                "simulation_state": e.simulation_state,
                "entity_kind": e.entity_kind,
                "current_hp": e.current_hp,
                "max_hp": e.max_hp,
                "current_shield": e.current_shield,
                "level": e.level,
                "status": e.status,
                "current_node_id": e.current_node_id,
                "target_team_id": str(e.target_team_id) if e.target_team_id else None,
                "range": rng,
                "damage": dmg,
                "movement": mov,
                "is_disabled": (e.status == EntityStatus.DISABLED),
                "cooldown_remaining": config.get("entity_effects", {}).get(str(e.id), {}).get("cooldown_remaining", 0),
                "shield_amount": base_stats.get("shield", 40),
                "cooldown_rounds": base_stats.get("cooldown_rounds", 2),
            })

        # 3. Fetch queued player actions for this planning window
        actions_qs = (
            GameAction.objects.select_for_update()
            .filter(match=match_locked, status__in=[ActionStatus.QUEUED, ActionStatus.ACCEPTED])
        )
        actions_list: List[Dict[str, Any]] = []
        for a in actions_qs:
            actions_list.append({
                "id": str(a.id),
                "team_id": str(a.team_id),
                "action_type": a.action_type,
                "payload": a.payload,
                "status": a.status,
            })

        combat_stats = config.get("combat_stats", {})

        # 4. Assemble pure CombatState
        combat_state = CombatState(
            round_number=current_round,
            is_paused=(match_locked.status == MatchStatus.PAUSED),
            teams=teams_map,
            entities=entities_list,
            actions=actions_list,
            configuration=config,
            combat_stats=combat_stats,
        )

        # 5. Delegate resolution to pure CombatEngine
        timer["round_phase"] = "RESOLVING"
        round_result = CombatEngine.resolve_round(combat_state)
        timer["round_phase"] = "RESULTS"
        logger.info("combat_completed match=%s round=%s", match.pk, current_round, extra={"match_id": str(match.pk), "round_number": current_round})

        # 6. Authoritative Persistence: Apply new state to DB
        now = timezone.now()
        new_state = round_result.new_state

        team_objects = {str(t.id): t for t in teams_qs}
        entity_objects = {str(e.id): e for e in entities_qs}
        action_objects = {str(a.id): a for a in actions_qs}
        correct_answers = dict(TeamQuestion.objects.filter(match=match_locked, is_correct=True)
                               .values("team_id").annotate(total=Count("id")).values_list("team_id", "total"))
        total_initial_hp = sum(t.initial_base_hp for t in team_objects.values())

        # Update Teams
        for tid, tinfo in new_state.teams.items():
            t_obj = team_objects.get(tid)
            if t_obj:
                t_obj.base_hp = tinfo["base_hp"]
                t_obj.base_shield = tinfo["base_shield"]
                t_obj.status = tinfo["status"]
                t_obj.coins = tinfo["coins"]
                score = calculate_team_score({
                    **tinfo, **new_state.combat_stats.get(tid, {}),
                    "correct_answers": correct_answers.get(t_obj.pk, 0),
                    "surviving_towers": sum(1 for entity in new_state.entities if entity["team_id"] == tid
                                             and entity["entity_kind"] == "TOWER" and entity["status"] == "ACTIVE"),
                }, config.get("scoring_weights", {}), damage_dealt_cap=total_initial_hp)["total_score"]
                t_obj.score = score
                tinfo["score"] = score
                round_result.events.append({"type": "TEAM_SCORE_UPDATED", "team_id": tid,
                                            "score": score, "round_number": current_round})
        Team.objects.bulk_update(list(team_objects.values()), ["base_hp", "base_shield", "status", "coins", "score"])

        # Update Entities
        for e_dict in new_state.entities:
            e_id = e_dict["id"]
            e_obj = entity_objects.get(e_id)
            if e_obj:
                e_obj.current_hp = e_dict["current_hp"]
                e_obj.current_shield = e_dict["current_shield"]
                e_obj.status = e_dict["status"]
                e_obj.current_node_id = e_dict["current_node_id"]
                e_obj.target_team_id = e_dict.get("target_team_id")
                if e_dict["status"] == EntityStatus.DESTROYED and not e_obj.destroyed_at:
                    e_obj.destroyed_at = now
        GameEntity.objects.bulk_update(list(entity_objects.values()), [
            "current_hp", "current_shield", "status", "current_node_id", "target_team_id", "destroyed_at"
        ])

        # Mark processed actions as RESOLVED
        for a_dict in new_state.actions:
            a_id = a_dict["id"]
            a_obj = action_objects.get(a_id)
            if a_obj:
                a_obj.status = ActionStatus.RESOLVED
                a_obj.resolved_at = now
        GameAction.objects.bulk_update(list(action_objects.values()), ["status", "resolved_at"])

        # Record CoinTransactions for passive income awarded in this round
        base_income = config.get("base_income_per_round", 10)
        income_transactions = []
        for ev in round_result.events:
            if ev.get("type") == "INCOME_AWARDED":
                team_target = team_objects.get(ev["team_id"])
                if team_target:
                    income_transactions.append(CoinTransaction(
                        match=match_locked,
                        team=team_target,
                        amount=base_income,
                        transaction_type=TransactionType.PASSIVE_INCOME,
                        reference_type="COMBAT_ROUND",
                        reference_id=str(current_round),
                        balance_after=ev["new_balance"],
                        description=f"Thu nhập định kỳ round {current_round}",
                    ))
        CoinTransaction.objects.bulk_create(income_transactions)

        # Update Match configuration with new round & combat stats
        config["current_round"] = new_state.round_number
        config["combat_stats"] = new_state.combat_stats
        config["active_shields"] = {
            tid: info.get("shield_remaining_rounds", 0)
            for tid, info in new_state.teams.items() if info.get("base_shield", 0) > 0
        }
        config["entity_effects"] = {
            entity["id"]: {"cooldown_remaining": entity.get("cooldown_remaining", 0)}
            for entity in new_state.entities
            if entity.get("status") != EntityStatus.DESTROYED and entity.get("cooldown_remaining", 0)
        }
        open_planning_window(config, resolved_at or now)
        if round_result.is_match_over:
            config["elimination_winner_id"] = round_result.winner_team_id
        match_locked.configuration = config
        match_locked.save(update_fields=["configuration", "updated_at"])

        # Record COMBAT_RESOLVED event in MatchEvent log (§19.12)
        MatchService.record_match_event(
            match_locked,
            event_type="COMBAT_RESOLVED",
            payload={
                "round_number": current_round,
                "events_count": len(round_result.events),
                "events": round_result.events,
                "eliminated_team_ids": round_result.eliminated_team_ids,
                "winner_team_id": round_result.winner_team_id,
                "is_match_over": round_result.is_match_over,
                **lifecycle_payload(match_locked),
            },
        )

        # If victory declared or match finished -> Finalize match snapshot (§19.13, Scenario H)
        if round_result.is_match_over:
            ScoringService.finalize_match(match_locked)
        else:
            MatchService.record_match_event(match_locked, "ROUND_STARTED", lifecycle_payload(match_locked))
            logger.info("round_planning match=%s round=%s", match.pk, new_state.round_number, extra={"match_id": str(match.pk), "round_number": new_state.round_number})

        return round_result
