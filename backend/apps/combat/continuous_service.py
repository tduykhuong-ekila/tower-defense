"""Atomic tick checkpoint, batched persistence, and compact authoritative deltas."""
import logging
import time
from datetime import timedelta

from django.db import transaction
from django.db.models import Count

from apps.combat.balance import entity_attack_range, inspection_stats, movement_multiplier
from apps.combat.continuous import ContinuousEngine
from apps.combat.engine import CombatState
from apps.combat.formation import PUBLIC_FORMATION_FIELDS
from apps.combat.scoring import ScoringService, calculate_team_score
from apps.matches.clock import lifecycle_payload
from apps.matches.models import Match
from apps.matches.services import MatchService
from apps.questions.models import TeamQuestion
from apps.teams.models import Team
from apps.units.models import GameAction, GameEntity

logger = logging.getLogger(__name__)


def public_entity(e, config=None):
    return {"id": str(e.id), "team_id": str(e.team_id),
            "unit_code": e.unit_type.code, "unit_name": e.unit_type.name,
            "entity_kind": e.entity_kind, "max_hp": e.max_hp, "level": e.level,
            "range": entity_attack_range(e),
            **inspection_stats(e, config),
            "movement_speed": movement_multiplier(e.unit_type.code) if e.entity_kind == "UNIT" else 0,
            "current_hp": e.current_hp, "current_shield": e.current_shield,
            "status": e.status, "current_node_id": e.current_node_id,
            "target_team_id": str(e.target_team_id) if e.target_team_id else None,
            "simulation_state": {k: v for k, v in e.simulation_state.items()
                                 if k in PUBLIC_FORMATION_FIELDS}}


class ContinuousCombatService:
    @classmethod
    @transaction.atomic
    def tick(cls, match_id, tick_at):
        started = time.perf_counter()
        match = Match.objects.select_for_update().get(pk=match_id)
        config = match.configuration
        timer = config.setdefault("timer_state", {})
        # Deadline equality is the idempotency key, checked again under the lock.
        if (match.status != "ACTIVE" or match.phase not in ("PREPARATION", "WAR")
                or config.get("gameplay_mode") != "CONTINUOUS"
                or timer.get("next_tick_at") != tick_at.isoformat()):
            return False
        teams = list(Team.objects.select_for_update().filter(match=match).order_by("created_at", "id"))
        entities = list(GameEntity.objects.select_for_update(of=("self",)).filter(
            match=match, status__in=["QUEUED", "ACTIVE", "DISABLED"]).select_related("unit_type").order_by("team_id", "id"))
        before = {str(e.id): public_entity(e, config) for e in entities}
        state = CombatState(config.get("current_round", 1), False,
            {str(t.id): {"id": str(t.id), "name": t.name, "team_index": i,
                        "base_hp": t.base_hp, "base_shield": t.base_shield,
                        "initial_base_hp": t.initial_base_hp, "coins": t.coins,
                        "score": t.score, "status": t.status} for i, t in enumerate(teams, 1)},
            [{**e.unit_type.base_stats, "range": entity_attack_range(e), "id": str(e.id), "team_id": str(e.team_id),
              "unit_type_code": e.unit_type.code, "entity_kind": e.entity_kind,
              "current_hp": e.current_hp, "max_hp": e.max_hp, "current_shield": e.current_shield,
              "level": e.level, "status": e.status, "current_node_id": e.current_node_id,
              "target_team_id": str(e.target_team_id) if e.target_team_id else None,
              "created_at": e.created_at.isoformat(),
              "simulation_state": e.simulation_state} for e in entities], [], config,
            config.get("combat_stats", {}))
        dt = config.get("battle_tick_interval_ms", 200) / 1000
        result = ContinuousEngine.step(state, dt)
        after = result.new_state
        # Refresh scoreboard on meaningful combat or once/second, using one aggregate query.
        refresh_scores = bool(result.events) or config.get("simulation_tick", 0) % 5 == 0
        correct = dict(TeamQuestion.objects.filter(match=match, is_correct=True).values("team_id")
                       .annotate(total=Count("id")).values_list("team_id", "total")) if refresh_scores else {}
        tower_counts = {}
        for entity in after.entities:
            if entity["entity_kind"] == "TOWER" and entity["status"] == "ACTIVE":
                tower_counts[entity["team_id"]] = tower_counts.get(entity["team_id"], 0) + 1
        changed_teams = []
        for t in teams:
            tid = str(t.id)
            info = after.teams[tid]
            score = calculate_team_score({**info, **after.combat_stats.get(tid, {}),
                "correct_answers": correct.get(t.pk, 0), "surviving_towers": tower_counts.get(tid, 0)},
                config.get("scoring_weights", {}), damage_dealt_cap=sum(x.initial_base_hp for x in teams))["total_score"] if refresh_scores else t.score
            if score != t.score:
                result.events.append({"type": "TEAM_SCORE_UPDATED", "team_id": tid,
                                      "score": score, "round_number": state.round_number})
            if (t.base_hp, t.base_shield, t.status, t.score, t.coins) != (info["base_hp"], info["base_shield"], info["status"], score, info["coins"]):
                t.base_hp, t.base_shield, t.status, t.score = info["base_hp"], info["base_shield"], info["status"], score
                t.coins = info["coins"]
                changed_teams.append(t)
        if changed_teams:
            Team.objects.bulk_update(changed_teams, ["base_hp", "base_shield", "status", "score", "coins"])
        by_id = {e["id"]: e for e in after.entities}
        changed_groups, updates = {}, []
        for e in entities:
            info = by_id[str(e.id)]
            dirty_fields = []
            for key in ("current_hp", "current_shield", "status", "current_node_id", "target_team_id", "simulation_state"):
                value = info[key]
                old = str(e.target_team_id) if key == "target_team_id" and e.target_team_id else getattr(e, key)
                if old != value:
                    setattr(e, key, value)
                    dirty_fields.append(key)
            if dirty_fields:
                if e.status == "DESTROYED" and not e.destroyed_at:
                    e.destroyed_at = tick_at
                    dirty_fields.append("destroyed_at")
                changed_groups.setdefault(tuple(dirty_fields), []).append(e)
            public = public_entity(e, config)
            if public != before[str(e.id)]:
                updates.append(public)
        for fields, objects in changed_groups.items():
            GameEntity.objects.bulk_update(objects, list(fields))
        GameAction.objects.filter(match=match, status__in=["QUEUED", "ACCEPTED"]).update(status="RESOLVED", resolved_at=tick_at)
        config["combat_stats"] = after.combat_stats
        config["continuous_shields"] = after.configuration.get("continuous_shields", {})
        config["simulation_tick"] = config.get("simulation_tick", 0) + 1
        timer["simulation_at"] = tick_at.isoformat()
        timer["next_tick_at"] = (tick_at + timedelta(seconds=dt)).isoformat()
        match.save(update_fields=["configuration"])
        # Empty ticks still persist their checkpoint, but do not grow the event log.
        if updates or result.events:
            MatchService.record_match_event(match, "COMBAT_TICK", {
                "tick": config["simulation_tick"], "simulation_at": tick_at.isoformat(),
                "tick_interval_ms": config.get("battle_tick_interval_ms", 200),
                "entity_updates": updates, "events": result.events,
                "eliminated_team_ids": result.eliminated_team_ids,
                **lifecycle_payload(match),
            })
        if result.is_match_over:
            config["elimination_winner_id"] = result.winner_team_id
            match.save(update_fields=["configuration"])
            ScoringService.finalize_match(match)
        duration = time.perf_counter() - started
        if duration > dt and config["simulation_tick"] % 25 == 0:
            logger.warning("combat_tick_over_budget match=%s entities=%s duration_ms=%.1f budget_ms=%.1f",
                           match.pk, len(entities), duration * 1000, dt * 1000,
                           extra={"match_id": str(match.pk), "entity_count": len(entities),
                                  "tick_duration_ms": duration * 1000, "tick_budget_ms": dt * 1000})
        return True
