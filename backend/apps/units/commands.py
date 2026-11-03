"""Tactical orders extend GameAction, serialized with ticks by the match row lock."""

import uuid

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.combat.continuous_service import public_entity
from apps.combat.formation import redirect_route
from apps.combat.map import get_game_map
from apps.matches.action_policy import ActionPolicy
from apps.matches.models import Match
from apps.matches.services import MatchService
from apps.teams.models import Team
from apps.units.map import MapDefinition
from apps.units.models import GameAction, GameEntity


class ArmyCommandService:
    @classmethod
    @transaction.atomic
    def issue(
        cls,
        match,
        team,
        command_type,
        idempotency_key,
        unit_ids=None,
        target_team_id=None,
        expected_command_version=None,
        actor=None,
    ):
        match = Match.objects.select_for_update().get(pk=match.pk)
        team = Team.objects.select_for_update().get(pk=team.pk)
        if team.match_id != match.pk or (
            actor and (actor.team_id != team.pk or actor.role == "SPECTATOR")
        ):
            raise ValidationError(
                "Bạn không có quyền điều khiển đội này.", code="SPECTATOR_READ_ONLY"
            )
        if command_type not in ("RETARGET", "RETREAT_ALL", "DEFEND_BASE"):
            raise ValidationError("Lệnh quân đội không hợp lệ.", code="INVALID_COMMAND")
        key = str(idempotency_key or "").strip()
        if not key or len(key) > 128:
            raise ValidationError("Mã yêu cầu không hợp lệ.", code="INVALID_REQUEST_ID")
        try:
            ids = sorted({str(uuid.UUID(str(value))) for value in (unit_ids or [])})
            target_id = str(uuid.UUID(str(target_team_id))) if target_team_id else None
        except (ValueError, TypeError, AttributeError):
            raise ValidationError("Mã đơn vị hoặc mục tiêu không hợp lệ.", code="INVALID_TARGET")
        request = {
            "command_type": command_type,
            "unit_ids": ids,
            "target_team_id": target_id,
            "expected_command_version": expected_command_version,
        }
        existing = GameAction.objects.filter(team=team, idempotency_key=key).first()
        if existing:
            if existing.action_type != command_type or existing.payload.get("request") != request:
                raise ValidationError(
                    "Mã yêu cầu đã được dùng cho thao tác khác.", code="IDEMPOTENCY_CONFLICT"
                )
            # Return the original acknowledgement, never reapply a retry over a later order.
            return existing, existing.payload["result"]
        ActionPolicy.require_context(match, team, command_type, actor)
        version = match.configuration.get("army_command_version", 0)
        if expected_command_version is not None and expected_command_version != version:
            raise ValidationError("Lệnh đã cũ; hãy đồng bộ và thử lại.", code="STALE_COMMAND")
        eligible = (
            GameEntity.objects.select_for_update(of=("self",))
            .filter(
                match=match,
                team=team,
                entity_kind="UNIT",
                current_hp__gt=0,
                status__in=["ACTIVE", "QUEUED"],
            )
            .select_related("unit_type")
            .order_by("id")
        )
        if command_type == "DEFEND_BASE" and not ids:
            raise ValidationError("Chọn quân để bảo vệ căn cứ.", code="INVALID_UNITS")
        target = None
        if command_type == "RETARGET":
            if not ids or not target_id:
                raise ValidationError("Chọn quân và đội đối thủ.", code="INVALID_TARGET")
            target = (
                match.teams.filter(pk=target_id, status="ACTIVE", base_hp__gt=0)
                .exclude(pk=team.pk)
                .first()
            )
            if not target:
                raise ValidationError(
                    "Đội đối thủ không còn là mục tiêu hợp lệ.", code="INVALID_TARGET"
                )
            entities = list(eligible.filter(pk__in=ids))
            if len(entities) != len(ids):
                raise ValidationError(
                    "Chỉ có thể điều khiển quân đang sống của đội mình.", code="INVALID_UNITS"
                )
        else:
            if target_id:
                raise ValidationError(
                    "Lệnh về căn cứ không nhận mục tiêu tùy ý.",
                    code="INVALID_COMMAND",
                )
            if ids:
                entities = list(eligible.filter(pk__in=ids))
                if len(entities) != len(ids):
                    raise ValidationError(
                        "Chỉ có thể rút quân đang sống của đội mình.", code="INVALID_UNITS"
                    )
            else:
                entities = list(eligible)
                entities = [e for e in entities if e.unit_type.base_stats.get("movement", 1) > 0]
        if any(e.unit_type.base_stats.get("movement", 1) <= 0 for e in entities):
            raise ValidationError("Đơn vị không thể di chuyển.", code="INVALID_UNITS")
        graph = get_game_map(
            max(2, match.teams.count()), match.configuration.get("arena_layout_version", 3)
        )
        destination = (
            MapDefinition.get_team_base_node(target)
            if target
            else MapDefinition.get_team_spawn_node(team)
        )
        if command_type == "DEFEND_BASE":
            destination = MapDefinition.get_team_base_node(team)
        route_end = graph.attack_position(destination) if target or command_type == "DEFEND_BASE" else destination
        version += 1
        for entity in entities:
            unit = {
                "current_node_id": entity.current_node_id,
                "simulation_state": entity.simulation_state,
            }
            if not redirect_route(unit, route_end, graph):
                raise ValidationError("Không có tuyến đường hợp lệ.", code="NO_ROUTE")
            entity.current_node_id = unit["current_node_id"]
            entity.target_team = target
            entity.target_node_id = destination
            entity.simulation_state.update(
                order="ATTACK" if target else ("DEFEND_BASE" if command_type == "DEFEND_BASE" else "RETREAT"),
                destination_rally_id=destination if command_type == "RETREAT_ALL" else None,
                command_version=version,
            )
        if entities:
            GameEntity.objects.bulk_update(
                entities, ["current_node_id", "target_team", "target_node_id", "simulation_state"]
            )
        match.configuration["army_command_version"] = version
        match.save(update_fields=["configuration"])
        result = {
            "team_id": str(team.pk),
            "command_type": command_type,
            "command_version": version,
            "affected_count": len(entities),
            "entity_updates": [public_entity(e, match.configuration) for e in entities],
            "simulation_at": match.configuration.get("timer_state", {}).get("simulation_at"),
            "tick_interval_ms": match.configuration.get("battle_tick_interval_ms", 200),
        }
        action = GameAction.objects.create(
            match=match,
            team=team,
            actor=actor,
            action_type=command_type,
            idempotency_key=key,
            status="RESOLVED",
            resolved_at=timezone.now(),
            payload={"request": request, "result": result},
        )
        MatchService.record_match_event(
            match,
            "UNITS_RETARGETED" if target else ("ARMY_DEFENSE_ORDERED" if command_type == "DEFEND_BASE" else "ARMY_RETREAT_ORDERED"),
            {**result, "action_id": str(action.pk)},
        )
        return action, result
