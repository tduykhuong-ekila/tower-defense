import json
import logging
from typing import Any, Dict, List, Optional

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.utils import timezone

from apps.combat.balance import entity_attack_range, inspection_stats, movement_multiplier
from apps.matches.action_policy import ActionPolicy
from apps.matches.defaults import MIN_MEMBERS_PER_TEAM
from apps.matches.models import Match, MatchEvent
from apps.questions.models import TeamQuestion
from apps.realtime.events import ServerEventType, format_event_envelope
from apps.teams.models import Team
from apps.units.models import EntityStatus, TeamUnlock

logger = logging.getLogger(__name__)

PRIVATE_EVENT_TYPES = {
    ServerEventType.QUESTION_ASSIGNED,
    ServerEventType.ANSWER_RESULT,
    ServerEventType.REWARD_OPTIONS,
    ServerEventType.REWARD_APPLIED,
    ServerEventType.COINS_UPDATED,
    "QUESTION_TIMER_UPDATED",
    "QUESTION_EXPIRED",
    "QUESTION_ANSWERED_CORRECT",
    "QUESTION_ANSWERED_INCORRECT",
    "REWARD_CLAIMED",
    "COINS_CREDITED",
    "COINS_DEBITED",
    "UNIT_UNLOCKED",
}


def scope_live_event(envelope: dict, viewer_team_id: Optional[str], is_host: bool) -> dict:
    """Public combat/deployment deltas can contain nested private balances.

    Keep the original immutable event for hosts and persistence; project a copy for
    each viewer, including balances in the COMBAT_RESOLVED subevent list.
    """
    if is_host:
        return envelope
    payload = envelope.get("payload", {})
    if envelope.get("event_type") in PRIVATE_EVENT_TYPES and str(payload.get("team_id")) != str(viewer_team_id):
        return {**envelope, "event_type": "EVENT_REDACTED", "payload": {}}

    balance_fields = {"coins", "coins_after", "coins_before", "new_balance", "balance_after"}

    def project(value, owner=None):
        if isinstance(value, list):
            return [project(item, owner) for item in value]
        if not isinstance(value, dict):
            return value
        owner = value.get("team_id", owner)
        private = owner is not None and str(owner) != str(viewer_team_id)
        return {key: project(item, owner) for key, item in value.items()
                if not (private and key in balance_fields)}

    return {**envelope, "payload": project(envelope.get("payload", {}))}


class RealtimeService:
    @staticmethod
    def broadcast_match_event(event: MatchEvent) -> None:
        """
        Broadcast a persisted MatchEvent using standard envelope over Django Channels.
        All events use match.{match_id} for a contiguous shared sequence.
        The consumer projects private payloads separately for each authorized viewer.
        """
        context = {"match_id": str(event.match_id), "match_group": f"match.{event.match_id}",
                   "event_id": str(event.pk), "event_type": event.event_type,
                   "sequence": event.sequence_number,
                   "entity_id": event.payload.get("entity_id")}
        try:
            logger.debug("Realtime broadcast attempt match=%s type=%s sequence=%s event=%s entity=%s",
                         context["match_id"], context["event_type"], context["sequence"],
                         context["event_id"], context["entity_id"], extra=context)
            channel_layer = get_channel_layer()
            if not channel_layer:
                logger.warning("No channel layer; event awaits outbox retry", extra=context)
                return

            envelope = format_event_envelope(
                match_id=event.match_id,
                event_type=event.event_type,
                sequence_number=event.sequence_number,
                payload=event.payload,
                event_id=event.id,
                server_timestamp=event.created_at,
            )

            # Redis channel layers also have a message-size ceiling. Large events
            # already exist durably: queue a reference, then scope per consumer.
            message = {"type": "match_event", "data": envelope}
            if len(json.dumps(envelope).encode()) > 128 * 1024:
                message = {"type": "match_event", "event_id": str(event.pk)}
            async_to_sync(channel_layer.group_send)(f"match.{event.match_id}", message)
            MatchEvent.objects.filter(pk=event.pk).update(broadcasted_at=timezone.now())
        except Exception:
            logger.exception("Realtime broadcast failed; event awaits outbox retry match=%s group=%s type=%s sequence=%s event=%s entity=%s",
                             context["match_id"], context["match_group"], context["event_type"],
                             context["sequence"], context["event_id"], context["entity_id"], extra=context)

    @classmethod
    def emit_event(
        cls,
        match: Match,
        event_type: str,
        payload: Dict[str, Any],
    ) -> MatchEvent:
        """
        Convenience method to record MatchEvent and broadcast it via transaction.on_commit.
        """
        from apps.matches.services import MatchService

        event = MatchService.record_match_event(match, event_type, payload)
        # Note: MatchService.record_match_event hooks transaction.on_commit to broadcast
        return event

    @classmethod
    @transaction.atomic(savepoint=False)
    def build_snapshot(
        cls,
        match: Match,
        viewer_team_id: Optional[str] = None,
        is_host: bool = False,
    ) -> Dict[str, Any]:
        """
        Build authoritative match state snapshot according to viewer permissions (§2.4, §25).
        - Host sees all.
        - Team viewer sees full private info for own team and public info for enemy teams.
        - Spectator / projector viewer sees only public match state.
        """
        # Serialize the snapshot with all writers so its sequence and board describe
        # one committed round, even when a client reconnects during resolution.
        match = Match.objects.select_for_update().get(pk=match.pk)
        now = timezone.now()
        last_event = (
            MatchEvent.objects.filter(match=match).order_by("-sequence_number").first()
        )
        current_seq = last_event.sequence_number if last_event else 0

        from collections import Counter, defaultdict

        board_entities = list(match.entities.exclude(status=EntityStatus.DESTROYED)
                              .select_related("unit_type", "team"))
        counts = Counter((str(e.team_id), e.entity_kind) for e in board_entities
                         if e.status == EntityStatus.ACTIVE)
        unlocks = defaultdict(list)
        private_unlocks = TeamUnlock.objects.filter(team__match=match).select_related("unit_type")
        if not is_host:
            private_unlocks = private_unlocks.filter(team_id=viewer_team_id) if viewer_team_id else []
        for unlock in private_unlocks:
            unlocks[str(unlock.team_id)].append(unlock.unit_type.code)
        ordered_teams = list(match.teams.order_by("created_at", "id").prefetch_related("members"))

        # Teams summary
        teams_data: List[Dict[str, Any]] = []
        for team_index, team in enumerate(ordered_teams, 1):
            is_own_team = viewer_team_id and str(team.id) == str(viewer_team_id)
            has_private_access = is_host or is_own_team

            team_dict: Dict[str, Any] = {
                "team_index": team_index,
                "id": str(team.id),
                "name": team.name,
                "base_hp": team.base_hp,
                "initial_base_hp": team.initial_base_hp,
                "base_shield": team.base_shield,
                "score": team.score,
                "status": team.status,
                "is_ready": team.is_ready,
                "members_count": team.members.count(),
                "active_units_count": counts[(str(team.id), "UNIT")],
                "towers_count": counts[(str(team.id), "TOWER")],
            }

            if has_private_access:
                team_dict["coins"] = team.coins
                team_dict["unlocked_units"] = unlocks[str(team.id)]
                team_dict["members"] = [
                    {
                        "id": str(m.id),
                        "display_name": m.display_name,
                        "role": m.role,
                        "is_ready": m.is_ready,
                    }
                    for m in team.members.all()
                ]

            teams_data.append(team_dict)

        # Entities on board (active or non-destroyed)
        entities_data: List[Dict[str, Any]] = []
        for ent in board_entities:
            entities_data.append(
                {
                    "id": str(ent.id),
                    "team_id": str(ent.team_id),
                    "team_name": ent.team.name,
                    "unit_code": ent.unit_type.code,
                    "unit_name": ent.unit_type.name,
                    "entity_kind": ent.entity_kind,
                    "current_hp": ent.current_hp,
                    "max_hp": ent.max_hp,
                    **inspection_stats(ent, match.configuration),
                    "range": entity_attack_range(ent),
                    "movement_speed": movement_multiplier(ent.unit_type.code) if ent.entity_kind == "UNIT" else 0,
                    "current_shield": ent.current_shield,
                    "level": ent.level,
                    "status": ent.status,
                    "current_node_id": ent.current_node_id,
                    "simulation_state": ent.simulation_state,
                    "target_team_id": str(ent.target_team_id) if ent.target_team_id else None,
                }
            )

        # Private question & reward data for viewer team
        current_question_data = None
        pending_reward_data = None
        my_coins = None
        my_unlocked_units: List[str] = []

        if viewer_team_id:
            try:
                viewer_team = next((t for t in ordered_teams if str(t.id) == str(viewer_team_id)), None)
                if viewer_team is None:
                    raise Team.DoesNotExist
                my_coins = viewer_team.coins
                my_unlocked_units = unlocks[str(viewer_team.id)]

                # Check active question
                tq = (
                    TeamQuestion.objects.filter(match=match, team=viewer_team)
                    .order_by("-sequence_number")
                    .select_related("question")
                    .first()
                )
                if tq:
                    # Exclude answer_key for payload security (§2.3, §22)
                    from apps.questions.timers import remaining_at
                    is_expired = tq.status == "EXPIRED" or (tq.status == "PENDING_QUESTION" and remaining_at(tq, now) == 0)
                    current_question_data = {
                        "id": str(tq.id),
                        "sequence_number": tq.sequence_number,
                        "question_id": str(tq.question_id),
                        "question_title": tq.question.content[:60],
                        "content": tq.question.content,
                        "category": tq.question.category,
                        "difficulty": tq.question.difficulty,
                        "question_type": tq.question.type,
                        "options": tq.question.options,
                        "time_limit_seconds": tq.question.time_limit_seconds,
                        "assigned_at": tq.assigned_at.isoformat() if tq.assigned_at else None,
                        "expires_at": tq.expires_at.isoformat() if tq.expires_at else None,
                        "status": tq.status,
                        "is_expired": is_expired,
                    }

                    # Reuse the REST contract, retaining legacy flattened fields above.
                    # The previous reward snapshot referenced a nonexistent UnitType.tier
                    # and disconnected participants precisely while a reward was pending.
                    from apps.questions.serializers import TeamQuestionSerializer

                    current_question_data.update(TeamQuestionSerializer(tq).data)
                    pending_reward_data = current_question_data.get("reward_options")
            except Team.DoesNotExist:
                pass

        from apps.questions.services import QuestionService
        from apps.units.placement import map_for_match
        map_data = map_for_match(match, [team["id"] for team in teams_data])
        from apps.units.models import TeamUnitUpgrade
        upgrades = {str(team.pk): {} for team in ordered_teams}
        for upgrade in TeamUnitUpgrade.objects.filter(team__match=match).select_related("unit_type"):
            upgrades[str(upgrade.team_id)][upgrade.unit_type.code] = upgrade.level
        snapshot_payload = {
            "team_upgrades": upgrades,
            "simulation_at": match.configuration.get("timer_state", {}).get("simulation_at"),
            "tick_interval_ms": match.configuration.get("battle_tick_interval_ms", 200),
            "map_data": map_data,
            "match": {
                "id": str(match.id),
                "name": match.name,
                "room_code": match.room_code,
                "status": match.status,
                "phase": match.phase,
                "is_locked": match.is_locked,
                "created_at": match.created_at.isoformat(),
                "configuration": {**match.configuration, "min_players_per_team": MIN_MEMBERS_PER_TEAM,
                                  "action_rules": ActionPolicy.rules(match.configuration)},
            },
            "teams": teams_data,
            "entities": entities_data,
            "current_round": match.configuration.get("current_round", 1),
            "combat_stats": match.configuration.get("combat_stats", {}),
            "viewer": {
                "is_host": is_host,
                "team_id": viewer_team_id,
                "coins": my_coins,
                "unlocked_units": my_unlocked_units,
                "current_question": current_question_data,
                "pending_reward": pending_reward_data,
                "question_progress": QuestionService.progress(match, viewer_team) if viewer_team_id and my_coins is not None else None,
            },
        }

        return format_event_envelope(
            match_id=match.id,
            event_type=ServerEventType.MATCH_STATE_SNAPSHOT,
            sequence_number=current_seq,
            payload=snapshot_payload,
            server_timestamp=now,
        )
