import json
import logging
import uuid
from typing import Any, Dict, Optional

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.core.exceptions import ValidationError

from apps.matches.models import Match, MatchEvent
from apps.matches.services import MatchService
from apps.questions.services import QuestionService
from apps.realtime.events import ClientEventType, ServerEventType, format_event_envelope
from apps.realtime.services import RealtimeService, scope_live_event
from apps.rewards.services import RewardService
from apps.teams.models import Team
from apps.units.services import ConstructionService, UnitService

logger = logging.getLogger(__name__)


class MatchConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer for realtime match synchronization (§21, §22, §25).
    Acts as a thin adapter between WebSocket clients and backend domain services (§16.2).
    """

    async def send_json(self, content, close=False):
        # Bound each frame below Daphne/Channels transport limits. Reassembly is
        # atomic on the client: no partial snapshot advances the state cursor.
        encoded = await self.encode_json(content)
        if len(encoded) <= 128 * 1024:
            await self.send(text_data=encoded, close=close)
            return
        size = 64 * 1024
        total = (len(encoded) + size - 1) // size
        transfer_id = str(uuid.uuid4())
        for index in range(total):
            await self.send(text_data=json.dumps({
                "event_type": "JSON_CHUNK", "match_id": self.match_id,
                "payload": {"id": transfer_id, "index": index, "total": total,
                            "data": encoded[index * size:(index + 1) * size]},
            }))
        if close:
            await self.close()

    async def connect(self):
        auth = self.scope.get("auth", {})
        if not auth.get("authenticated", False):
            await self.close(code=4003)
            return

        self.match_id = str(
            self.scope.get("url_route", {}).get("kwargs", {}).get("match_id", "")
        )
        if not self.match_id:
            import re
            m = re.search(r"/ws/matches/([0-9a-fA-F-]+)", self.scope.get("path", ""))
            if m:
                self.match_id = m.group(1)

        self.is_host = self.scope.get("is_host", False)
        self.is_spectator = self.scope.get("is_spectator", False)
        self.team_member = self.scope.get("team_member")
        self.team_id = self.scope.get("team_id")
        self.role = self.scope.get("role")

        # Groups (§2.1): match.{id}, match.{id}.team.{team_id}, match.{id}.host
        self.match_group = f"match.{self.match_id}"
        self.team_group = (
            f"match.{self.match_id}.team.{self.team_id}" if self.team_id else None
        )
        self.host_group = (
            f"match.{self.match_id}.host" if self.is_host else None
        )

        await self.channel_layer.group_add(self.match_group, self.channel_name)
        if self.team_group:
            await self.channel_layer.group_add(self.team_group, self.channel_name)
        if self.host_group:
            await self.channel_layer.group_add(self.host_group, self.channel_name)

        await self.accept()

        # Send initial snapshot upon connection (§25)
        snapshot = await self.get_snapshot()
        await self.send_json(snapshot)

    async def disconnect(self, code):
        if hasattr(self, "match_group"):
            await self.channel_layer.group_discard(self.match_group, self.channel_name)
        if getattr(self, "team_group", None):
            await self.channel_layer.group_discard(self.team_group, self.channel_name)
        if getattr(self, "host_group", None):
            await self.channel_layer.group_discard(self.host_group, self.channel_name)

    async def match_event(self, event):
        """Handler for events broadcasted through channel_layer."""
        envelope = event.get("data")
        if envelope is None:
            envelope = await self.get_event(event["event_id"])
        await self.send_json(scope_live_event(envelope, self.team_id, self.is_host))

    @database_sync_to_async
    def get_event(self, event_id):
        event = MatchEvent.objects.get(pk=event_id, match_id=self.match_id)
        return format_event_envelope(match_id=event.match_id, event_type=event.event_type,
                                     sequence_number=event.sequence_number, payload=event.payload,
                                     event_id=event.id, server_timestamp=event.created_at)

    async def receive_json(self, content, **kwargs):
        event_type = content.get("event_type") or content.get("type")
        payload = content.get("payload", {})
        idempotency_key = payload.get("idempotency_key")

        if event_type == "PING":
            # Refresh group membership for long-lived rooms (channel layers expire it).
            await self.channel_layer.group_add(self.match_group, self.channel_name)
            await self.send_json({"event_type": "PONG", "match_id": self.match_id,
                                  "payload": {"state_version": await self.get_state_version()}})
            return

        if event_type == ClientEventType.STATE_SYNC_REQUEST:
            snapshot = await self.get_snapshot()
            await self.send_json(snapshot)
            return

        # Spectators cannot perform state-changing actions (§2.2, §22)
        if self.is_spectator:
            await self.send_json(
                {
                    "event_type": ServerEventType.ACTION_REJECTED,
                    "payload": {
                        "reason": "Spectators cannot perform state-changing actions.",
                        "error_code": "SPECTATOR_READ_ONLY",
                        "idempotency_key": idempotency_key,
                    },
                }
            )
            return

        # Dispatch state-changing actions to service layer
        try:
            if event_type == ClientEventType.ANSWER_SUBMITTED:
                result = await self.handle_submit_answer(payload)
                await self.send_action_accepted("ANSWER_SUBMITTED", result, idempotency_key)

            elif event_type == ClientEventType.REWARD_SELECTED:
                result = await self.handle_select_reward(payload)
                await self.send_action_accepted("REWARD_SELECTED", result, idempotency_key)

            elif event_type == ClientEventType.DEPLOY_REQUEST:
                result = await self.handle_deploy(payload)
                await self.send_action_accepted("DEPLOY_REQUEST", result, idempotency_key)

            elif event_type == ClientEventType.BUILD_REQUEST:
                result = await self.handle_build(payload)
                await self.send_action_accepted("BUILD_REQUEST", result, idempotency_key)

            elif event_type == ClientEventType.UPGRADE_REQUEST:
                result = await self.handle_upgrade(payload)
                await self.send_action_accepted("UPGRADE_REQUEST", result, idempotency_key)

            elif event_type == ClientEventType.REPAIR_REQUEST:
                result = await self.handle_repair(payload)
                await self.send_action_accepted("REPAIR_REQUEST", result, idempotency_key)

            elif event_type == ClientEventType.SCOUT_REQUEST:
                result = await self.handle_scout(payload)
                await self.send_action_accepted("SCOUT_REQUEST", result, idempotency_key)

            elif event_type == ClientEventType.EMP_REQUEST:
                result = await self.handle_emp(payload)
                await self.send_action_accepted("EMP_REQUEST", result, idempotency_key)

            elif event_type == ClientEventType.TARGET_SELECTED:
                result = await self.handle_set_target(payload)
                await self.send_action_accepted("TARGET_SELECTED", result, idempotency_key)

            elif event_type == ClientEventType.READY_CHANGED:
                result = await self.handle_ready_changed(payload)
                await self.send_action_accepted("READY_CHANGED", result, idempotency_key)

            elif event_type in (ClientEventType.START_MATCH, "START_MATCH"):
                if not self.is_host:
                    await self.send_action_rejected(
                        "Only the Match Host can start the match.", "HOST_REQUIRED", idempotency_key
                    )
                    return
                result = await self.handle_host_start()
                await self.send_action_accepted("START_MATCH", result, idempotency_key)

            elif event_type in (ClientEventType.PAUSE_MATCH, "PAUSE_MATCH"):
                if not self.is_host:
                    await self.send_action_rejected(
                        "Only the Match Host can pause the match.", "HOST_REQUIRED", idempotency_key
                    )
                    return
                result = await self.handle_host_pause()
                await self.send_action_accepted("PAUSE_MATCH", result, idempotency_key)

            elif event_type in (ClientEventType.RESUME_MATCH, "RESUME_MATCH"):
                if not self.is_host:
                    await self.send_action_rejected(
                        "Only the Match Host can resume the match.", "HOST_REQUIRED", idempotency_key
                    )
                    return
                result = await self.handle_host_resume()
                await self.send_action_accepted("RESUME_MATCH", result, idempotency_key)

            elif event_type in (ClientEventType.END_MATCH, "END_MATCH"):
                if not self.is_host:
                    await self.send_action_rejected(
                        "Only the Match Host can end the match.", "HOST_REQUIRED", idempotency_key
                    )
                    return
                result = await self.handle_host_end()
                await self.send_action_accepted("END_MATCH", result, idempotency_key)

            elif event_type in (ClientEventType.ADVANCE_PHASE, "ADVANCE_PHASE"):
                if not self.is_host:
                    await self.send_action_rejected(
                        "Only the Match Host can advance match phases.", "HOST_REQUIRED", idempotency_key
                    )
                    return
                result = await self.handle_host_advance_phase(payload)
                await self.send_action_accepted("ADVANCE_PHASE", result, idempotency_key)

            else:
                await self.send_action_rejected(
                    f"Unknown client event type: {event_type}",
                    "UNKNOWN_EVENT_TYPE",
                    idempotency_key,
                )
        except ValidationError as val_err:
            reason = (
                val_err.message
                if hasattr(val_err, "message")
                else ", ".join(val_err.messages)
            )
            await self.send_action_rejected(reason, getattr(val_err, "code", None) or "VALIDATION_ERROR", idempotency_key)
        except Exception as exc:
            logger.exception("Error handling client message %s: %s", event_type, exc)
            await self.send_action_rejected(str(exc), "INTERNAL_ERROR", idempotency_key)

    async def send_action_accepted(
        self, action: str, result: Dict[str, Any], idempotency_key: Optional[str]
    ):
        await self.send_json(
            {
                "event_type": ServerEventType.ACTION_ACCEPTED,
                "payload": {
                    "action": action,
                    "result": result,
                    "idempotency_key": idempotency_key,
                },
            }
        )

    async def send_action_rejected(
        self, reason: str, error_code: str, idempotency_key: Optional[str]
    ):
        await self.send_json(
            {
                "event_type": ServerEventType.ACTION_REJECTED,
                "payload": {
                    "reason": reason,
                    "error_code": error_code,
                    "idempotency_key": idempotency_key,
                },
            }
        )

    @database_sync_to_async
    def get_state_version(self):
        from apps.matches.models import MatchEvent
        return (MatchEvent.objects.filter(match_id=self.match_id)
                .order_by("-sequence_number").values_list("sequence_number", flat=True).first() or 0)

    @database_sync_to_async
    def get_snapshot(self) -> Dict[str, Any]:
        match = Match.objects.get(id=self.match_id)
        return RealtimeService.build_snapshot(
            match=match,
            viewer_team_id=self.team_id,
            is_host=self.is_host,
        )

    @database_sync_to_async
    def handle_submit_answer(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.team_id:
            raise ValidationError("You must belong to a team to submit answers.")
        match = Match.objects.get(id=self.match_id)
        team = Team.objects.get(id=self.team_id, match=match)
        question_id = payload.get("question_id")
        answer = payload.get("answer")
        if not isinstance(answer, str) or not answer.strip() or len(answer) > 4000:
            raise ValidationError("Answer must contain 1–4000 characters.")

        tq = QuestionService.submit_answer(
            match=match,
            team=team,
            team_question_id=payload.get("team_question_id") or question_id,
            answer=answer,
            member=self.team_member,
        )

        reward_options = None
        if tq.status == "PENDING_REWARD":
            reward_options = RewardService.get_reward_options(tq)

        from apps.questions.serializers import TeamQuestionSerializer

        return {
            "team_id": str(team.pk),
            "team_question_id": str(tq.id),
            "is_correct": tq.is_correct,
            "status": tq.status,
            "reward_options": reward_options,
            "question_state": dict(TeamQuestionSerializer(tq).data),
            "question_progress": QuestionService.progress(match, team),
        }

    @database_sync_to_async
    def handle_select_reward(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.team_id:
            raise ValidationError("You must belong to a team to claim rewards.")
        match = Match.objects.get(id=self.match_id)
        team = Team.objects.get(id=self.team_id, match=match)

        claim = RewardService.claim_reward(
            match=match,
            team=team,
            team_question_id=payload.get("team_question_id"),
            reward_type=payload.get("reward_type"),
            unit_type_id=payload.get("unit_type_id"),
            idempotency_key=payload.get("idempotency_key"),
        )
        return {
            "claim_id": str(claim.id),
            "reward_type": claim.reward_type,
            "coin_amount": claim.coin_amount,
            "unlocked_unit_code": (
                claim.unlocked_unit_type.code if claim.unlocked_unit_type else None
            ),
        }

    @database_sync_to_async
    def handle_deploy(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.team_id:
            raise ValidationError("You must belong to a team to deploy units.")
        match = Match.objects.get(id=self.match_id)
        team = Team.objects.get(id=self.team_id, match=match)
        unit_code = payload.get("unit_code") or payload.get("unit_type_id")
        target_team_id = payload.get("target_team_id")

        action, entities = UnitService.deploy_units(
            match=match,
            team=team,
            unit_type_code_or_id=unit_code,
            target_team_id=target_team_id,
            actor=self.team_member,
            idempotency_key=payload.get("idempotency_key"),
            quantity=payload.get("quantity", 1),
            spawn_node_id=payload.get("spawn_node_id", payload.get("spawn_node")),
        )
        team.refresh_from_db()
        return {
            "action_id": str(action.id),
            "entity_id": str(entities[0].id) if entities else None,
            "entity_ids": [str(e.pk) for e in entities],
            "quantity": action.payload.get("quantity", 1),
            "unit_code": entities[0].unit_type.code,
            "spawn_node": entities[0].current_node_id,
            "coins_after": team.coins,
        }

    @database_sync_to_async
    def handle_build(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.team_id:
            raise ValidationError("You must belong to a team to build towers.")
        match = Match.objects.get(id=self.match_id)
        team = Team.objects.get(id=self.team_id, match=match)
        tower_code = payload.get("tower_code") or payload.get("unit_code")

        action, entity = ConstructionService.build_tower(
            match=match,
            team=team,
            unit_type_code_or_id=tower_code,
            grid_row=payload.get("grid_row"), grid_col=payload.get("grid_col"),
            node_id=payload.get("node_id"),
            actor=self.team_member,
            idempotency_key=payload.get("idempotency_key"),
        )
        team.refresh_from_db()
        return {
            "action_id": str(action.id),
            "entity_id": str(entity.id),
            "tower_code": entity.unit_type.code,
            "node_id": entity.current_node_id,
            "coins_after": team.coins,
        }

    @database_sync_to_async
    def handle_upgrade(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.team_id:
            raise ValidationError("You must belong to a team to upgrade towers.")
        match = Match.objects.get(id=self.match_id)
        team = Team.objects.get(id=self.team_id, match=match)

        if "entity_type" in payload:
            from apps.units.serializers import TeamUpgradeRequestSerializer
            from apps.units.services import TeamUpgradeService
            serializer = TeamUpgradeRequestSerializer(data=payload)
            if not serializer.is_valid():
                raise ValidationError(str(serializer.errors))
            action, result = TeamUpgradeService.purchase(match, team, actor=self.team_member, **serializer.validated_data)
            return {"action_id": str(action.pk), **result}
        action, entity = ConstructionService.upgrade_tower(
            match=match,
            team=team,
            entity_id=payload.get("entity_id"),
            actor=self.team_member,
            idempotency_key=payload.get("idempotency_key"),
        )
        team.refresh_from_db()
        return {
            "action_id": str(action.id),
            "entity_id": str(entity.id),
            "level": entity.level,
            "coins_after": team.coins,
        }

    @database_sync_to_async
    def handle_repair(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.team_id:
            raise ValidationError("You must belong to a team to repair base.")
        match = Match.objects.get(id=self.match_id)
        team = Team.objects.get(id=self.team_id, match=match)

        action = ConstructionService.repair_base(
            match=match,
            team=team,
            actor=self.team_member,
            idempotency_key=payload.get("idempotency_key"),
        )
        team.refresh_from_db()
        return {
            "action_id": str(action.id),
            "base_hp_after": team.base_hp,
            "coins_after": team.coins,
        }

    @database_sync_to_async
    def handle_scout(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.team_id:
            raise ValidationError("You must belong to a team to perform scouting.")
        match = Match.objects.get(id=self.match_id)
        team = Team.objects.get(id=self.team_id, match=match)
        target_team = Team.objects.get(id=payload.get("target_team_id"), match=match)

        action, scout_data = ConstructionService.scout(
            match=match,
            team=team,
            target_team_id=str(target_team.id),
            actor=self.team_member,
            idempotency_key=payload.get("idempotency_key"),
        )
        team.refresh_from_db()
        return {
            "action_id": str(action.id),
            "scout_data": scout_data,
        }

    @database_sync_to_async
    def handle_emp(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.team_id:
            raise ValidationError("You must belong to a team to use EMP.")
        match = Match.objects.get(id=self.match_id)
        team = Team.objects.get(id=self.team_id, match=match)

        action, entity = ConstructionService.emp(
            match=match,
            team=team,
            target_entity_id=payload.get("target_entity_id"),
            actor=self.team_member,
            idempotency_key=payload.get("idempotency_key"),
        )
        team.refresh_from_db()
        return {
            "action_id": str(action.id),
            "target_entity_id": str(entity.id),
            "status": entity.status,
        }

    @database_sync_to_async
    def handle_set_target(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.team_id:
            raise ValidationError("You must belong to a team to set target.")
        match = Match.objects.get(id=self.match_id)
        team = Team.objects.get(id=self.team_id, match=match)
        target_team = Team.objects.get(id=payload.get("target_team_id"), match=match)

        UnitService.set_team_target(match, team, target_team)
        return {
            "target_team_id": str(target_team.id),
            "target_team_name": target_team.name,
        }

    @database_sync_to_async
    def handle_ready_changed(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        is_ready = bool(payload.get("is_ready", True))
        if self.team_member:
            member = MatchService.set_member_ready(self.team_member, is_ready)
            # If member's team is ready, also update team ready if mentor
            if self.team_id:
                team = Team.objects.filter(id=self.team_id).first()
                if team and getattr(self, "role", None) == "MENTOR":
                    MatchService.set_team_ready(team, is_ready)
            return {"member_id": str(member.id), "is_ready": member.is_ready}
        elif self.team_id:
            team = Team.objects.get(id=self.team_id)
            MatchService.set_team_ready(team, is_ready)
            return {"team_id": str(team.id), "is_ready": team.is_ready}
        return {"is_ready": is_ready}

    @database_sync_to_async
    def handle_host_start(self) -> Dict[str, Any]:
        match = Match.objects.get(pk=self.match_id)
        m = MatchService.start_match(match)
        return {"match_id": str(m.id), "status": m.status, "phase": m.phase}

    @database_sync_to_async
    def handle_host_pause(self) -> Dict[str, Any]:
        match = Match.objects.get(pk=self.match_id)
        m = MatchService.pause_match(match)
        return {"match_id": str(m.id), "status": m.status, "phase": m.phase}

    @database_sync_to_async
    def handle_host_resume(self) -> Dict[str, Any]:
        match = Match.objects.get(pk=self.match_id)
        m = MatchService.resume_match(match)
        return {"match_id": str(m.id), "status": m.status, "phase": m.phase}

    @database_sync_to_async
    def handle_host_end(self) -> Dict[str, Any]:
        match = Match.objects.get(pk=self.match_id)
        m = MatchService.end_match(match)
        return {"match_id": str(m.id), "status": m.status, "phase": m.phase}

    @database_sync_to_async
    def handle_host_advance_phase(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        match = Match.objects.get(pk=self.match_id)
        target = payload.get("target_phase")
        is_override = bool(payload.get("is_override", False))
        reason = payload.get("reason", "")
        m = MatchService.advance_phase(
            match, target_phase=target, is_override=is_override, reason=reason
        )
        return {"match_id": str(m.id), "status": m.status, "phase": m.phase}

