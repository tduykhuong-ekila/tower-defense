import uuid
from typing import Any, Dict, Optional, Tuple

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from apps.economy.models import TransactionType
from apps.economy.services import EconomyService
from apps.matches.action_policy import ActionPolicy
from apps.matches.models import Match
from apps.matches.services import MatchService
from apps.teams.models import Team, TeamMember, TeamStatus
from apps.units.map import MapDefinition
from apps.units.models import (
    ActionStatus,
    ActionType,
    EntityCategory,
    EntityStatus,
    GameAction,
    GameEntity,
    UnitType,
)


class UnitService:
    """
    Handles unit deployment and unit roster operations (§8, §9.4, §14.7).
    """

    @classmethod
    def deploy_unit(cls, match, team, unit_type_code_or_id, target_team_id,
                    actor=None, idempotency_key=None):
        """Backward-compatible single-entity service contract."""
        action, entities = cls.deploy_units(
            match, team, unit_type_code_or_id, target_team_id,
            actor=actor, idempotency_key=idempotency_key,
        )
        return action, entities[0] if entities else None

    @classmethod
    @transaction.atomic
    def deploy_units(cls, match, team, unit_type_code_or_id, target_team_id=None,
                     actor=None, idempotency_key=None, quantity=1, spawn_node_id=None,
                     order="ATTACK"):
        """One locked, all-or-nothing purchase; all entities share one durable action."""
        if order not in ("ATTACK", "DEFEND_BASE"):
            raise ValidationError("Nhiệm vụ triển khai không hợp lệ.", code="INVALID_COMMAND")
        if order == "DEFEND_BASE" and target_team_id is not None:
            raise ValidationError("Bảo vệ căn cứ không nhận mục tiêu đối thủ.", code="INVALID_TARGET")
        if type(quantity) is not int or quantity < 1:
            raise ValidationError("Số lượng phải là số nguyên lớn hơn hoặc bằng 1.", code="INVALID_QUANTITY")
        key = str(idempotency_key if idempotency_key is not None else uuid.uuid4()).strip()
        if not key or len(key) > 128:
            raise ValidationError("Mã yêu cầu không hợp lệ.", code="INVALID_REQUEST_ID")
        match_locked = Match.objects.select_for_update().get(pk=match.pk)
        team_locked = Team.objects.select_for_update().get(pk=team.pk)
        # Authorize ownership even for retries after the phase/match has finished.
        if team_locked.match_id != match_locked.pk or (actor and (
                actor.team_id != team_locked.pk or actor.role == "SPECTATOR")):
            raise ValidationError("Bạn không có quyền điều khiển đội này.", code="SPECTATOR_READ_ONLY")
        existing = GameAction.objects.filter(team=team_locked, idempotency_key=key).first()
        if existing:
            payload = existing.payload
            unit_id = payload.get("unit_type_id")
            if unit_id is None and str(unit_type_code_or_id).strip() != payload.get("unit_type_code"):
                # Actions recorded before batch deployment stored only the code,
                # even when the original caller supplied a catalog UUID.
                unit_id = str(UnitType.objects.filter(code=payload.get("unit_type_code"))
                              .values_list("pk", flat=True).first())
            original_spawn = payload.get("spawn_node_id")
            if spawn_node_id is not None and original_spawn is None:
                original_spawn = MapDefinition.get_team_spawn_node(team_locked)
            if (existing.action_type != ActionType.DEPLOY_UNIT
                    or quantity != payload.get("quantity", 1)
                    or order != payload.get("order", "ATTACK")
                    or (str(target_team_id) if target_team_id is not None else None) != payload.get("target_team_id")
                    or str(unit_type_code_or_id).strip() not in (
                        payload.get("unit_type_code"), unit_id)
                    or (spawn_node_id is not None and spawn_node_id != original_spawn)):
                raise ValidationError("Mã yêu cầu đã được dùng cho thao tác khác.", code="IDEMPOTENCY_CONFLICT")
            ids = payload.get("entity_ids", [payload.get("entity_id")])
            by_id = {str(e.pk): e for e in GameEntity.objects.filter(
                match=match_locked, team=team_locked, pk__in=ids).select_related("unit_type", "target_team")}
            return existing, [by_id[eid] for eid in ids if eid in by_id]

        ActionPolicy.require_context(match_locked, team_locked, "DEPLOY_UNIT", actor)
        unit_query = Q(code=str(unit_type_code_or_id).strip())
        try:
            unit_query |= Q(id=uuid.UUID(str(unit_type_code_or_id).strip()))
        except (ValueError, AttributeError):
            pass
        unit = UnitType.objects.filter(unit_query).first()
        if not unit or not unit.is_active or unit.category != EntityCategory.UNIT:
            raise ValidationError("Đơn vị chiến đấu không tồn tại hoặc không kích hoạt.", code="INVALID_UNIT")
        target_team = None
        if order == "ATTACK":
            if str(target_team_id) == str(team_locked.pk):
                raise ValidationError("Không thể chỉ định căn cứ của chính đội mình làm mục tiêu.", code="INVALID_TARGET")
            if not target_team_id:
                raise ValidationError("Vui lòng chọn căn cứ đối thủ hợp lệ.", code="INVALID_TARGET")
            target_team = match_locked.teams.filter(pk=target_team_id).first()
            if target_team and (target_team.status != TeamStatus.ACTIVE or target_team.base_hp <= 0):
                raise ValidationError(f"Căn cứ {target_team.name} đã bị phá hủy hoặc loại khỏi trận đấu.", code="INVALID_TARGET")
            if not target_team or not MapDefinition.is_target_reachable(team_locked, target_team):
                raise ValidationError("Không có tuyến đường tới căn cứ đối thủ đang hoạt động.", code="INVALID_TARGET")
        ActionPolicy.require_purchase(match_locked, team_locked, "DEPLOY_UNIT", unit, quantity=quantity)
        spawn_node = MapDefinition.get_team_spawn_node(team_locked)
        if spawn_node_id is not None and spawn_node_id != spawn_node:
            raise ValidationError("Điểm tập kết không thuộc đội của bạn.", code="INVALID_POSITION")
        target_base = MapDefinition.get_team_base_node(target_team or team_locked)
        from apps.combat.continuous_service import public_entity
        from apps.combat.formation import initialize_spawn
        from apps.combat.map import get_game_map
        from apps.units.upgrades import effective_stats, team_level
        level = team_level(team_locked, unit)
        hp = effective_stats(unit, level, match_locked.configuration)["hp"]
        game_map = get_game_map(max(2, match_locked.teams.count()), match_locked.configuration.get("arena_layout_version", 3))
        if not game_map.path(spawn_node, game_map.attack_position(target_base)):
            raise ValidationError("Không có tuyến đường tấn công hợp lệ.", code="INVALID_TARGET")
        formation_order = match_locked.configuration.get("next_formation_order", 1)
        others = []
        if unit.code != "infantry":
            others = [{"id": str(e.pk), "status": e.status, "unit_type_code": e.unit_type.code,
                       "current_node_id": e.current_node_id, "simulation_state": e.simulation_state}
                      for e in GameEntity.objects.filter(match=match_locked, team=team_locked,
                          entity_kind="UNIT", status__in=["QUEUED", "ACTIVE"])
                      .exclude(unit_type__code="infantry").select_related("unit_type").order_by("created_at", "id")]
        entities = []
        for index in range(quantity):
            entity = GameEntity(
                match=match_locked, team=team_locked, unit_type=unit, entity_kind=EntityCategory.UNIT,
                current_hp=hp, max_hp=hp, level=level, status=EntityStatus.ACTIVE if unit.code == "infantry" else EntityStatus.QUEUED,
                current_node_id=spawn_node, target_team=target_team, target_node_id=target_base,
                simulation_state={"attack_range": unit.base_stats.get("range", 1), "order": order},
            )
            sim = {**unit.base_stats, "id": str(entity.pk), "team_id": str(team_locked.pk),
                   "unit_type_code": unit.code, "current_node_id": spawn_node, "status": entity.status,
                   "simulation_state": entity.simulation_state}
            initialize_spawn(sim, others, target_base, game_map, formation_order + index, match_locked.configuration)
            entity.status = sim["status"]
            entity.simulation_state = sim["simulation_state"]
            if unit.code != "infantry":
                others.append(sim)
            entities.append(entity)
        cost = unit.cost * quantity
        if cost:
            EconomyService.debit(team=team_locked, amount=cost, transaction_type=TransactionType.DEPLOY_UNIT,
                reference_type="DEPLOY_UNIT", reference_id=key,
                description=f"Triển khai {quantity} × {unit.name} " + (
                    f"tấn công {target_team.name}" if target_team else "bảo vệ căn cứ"))
        team_locked.refresh_from_db(fields=["coins"])
        GameEntity.objects.bulk_create(entities)
        match_locked.configuration["next_formation_order"] = formation_order + quantity
        match_locked.save(update_fields=["configuration"])
        action = GameAction.objects.create(
            match=match_locked, team=team_locked, actor=actor, action_type=ActionType.DEPLOY_UNIT,
            payload={"unit_type_code": unit.code, "unit_type_id": str(unit.pk), "unit_name": unit.name,
                     "target_team_id": str(target_team.pk) if target_team else None,
                     "target_team_name": target_team.name if target_team else None, "order": order,
                     "spawn_node_id": spawn_node, "quantity": quantity,
                     "entity_id": str(entities[0].pk), "entity_ids": [str(e.pk) for e in entities],
                     "unit_cost": unit.cost, "cost": cost},
            status=ActionStatus.ACCEPTED, idempotency_key=key,
        )
        payload = {"team_id": str(team_locked.pk), "action_id": str(action.pk), "quantity": quantity,
                   "cost": cost, "coins_after": team_locked.coins}
        if quantity == 1:
            # Preserve the legacy event shape for existing single-deploy consumers.
            payload.update(public_entity(entities[0]), entity_id=str(entities[0].pk))
            event_type = "UNIT_DEPLOYED"
        else:
            payload["entities"] = [public_entity(e) for e in entities]
            event_type = "ENTITIES_CREATED"
        MatchService.record_match_event(match_locked, event_type, payload)
        return action, entities

    @classmethod
    @transaction.atomic
    def set_team_target(cls, match: Match, team: Team, target_team: Team):
        match = Match.objects.select_for_update().get(pk=match.pk)
        team = Team.objects.select_for_update().get(pk=team.pk)
        ActionPolicy.require_context(match, team, "TARGET_SELECTED")
        target = match.teams.filter(pk=target_team.pk, status=TeamStatus.ACTIVE, base_hp__gt=0).first()
        if not target or target.pk == team.pk:
            raise ValidationError("Select an active enemy base in this match.")
        for entity in GameEntity.objects.select_for_update().filter(
            team=team, match=match, entity_kind=EntityCategory.UNIT,
            status__in=[EntityStatus.ACTIVE, EntityStatus.QUEUED],
        ).exclude(target_team=target):
            entity.target_team = target
            entity.target_node_id = MapDefinition.get_team_base_node(target)
            entity.save(update_fields=["target_team", "target_node_id"])
            MatchService.record_match_event(match, "UNIT_RETARGETED", {
                "team_id": str(team.pk), "entity_id": str(entity.pk),
                "target_team_id": str(target.pk),
            })


class ConstructionService:
    """
    Handles defensive structure construction, upgrades, and special operations (§8.3, §8.4, §9.3).
    """

    @classmethod
    @transaction.atomic
    def build_tower(
        cls,
        match: Match,
        team: Team,
        unit_type_code_or_id: str,
        node_id: str = "",
        actor: Optional[TeamMember] = None,
        idempotency_key: Optional[str] = None,
        grid_row=None, grid_col=None,
    ) -> Tuple[GameAction, GameEntity]:
        """
        Construct a defensive tower with authoritative geometry and atomic occupancy.
        Enforces full owned footprint, cost debit, occupancy and idempotency.
        """
        idempotency_key = str(idempotency_key if idempotency_key is not None else uuid.uuid4()).strip()
        node_id = str(node_id or "").strip()
        if not idempotency_key or len(idempotency_key) > 128:
            raise ValidationError("Mã yêu cầu không hợp lệ.", code="INVALID_REQUEST_ID")

        # Idempotency check
        match_locked = Match.objects.select_for_update().get(pk=match.pk)
        team_locked = Team.objects.select_for_update().get(pk=team.pk)

        existing_action = GameAction.objects.filter(
            team=team,
            idempotency_key=idempotency_key,
        ).first()
        if team_locked.match_id != match_locked.pk or (actor and (
                actor.team_id != team_locked.pk or actor.role == "SPECTATOR")):
            raise ValidationError("Bạn không có quyền điều khiển đội này.", code="SPECTATOR_READ_ONLY")
        from apps.units.placement import enabled, placement_grid
        grid_mode = enabled(match_locked) or grid_row is not None or grid_col is not None
        if existing_action:
            same_position = (existing_action.payload.get("grid_row") == grid_row
                             and existing_action.payload.get("grid_col") == grid_col) if grid_mode else existing_action.payload.get("node_id") == node_id
            if (existing_action.action_type != ActionType.BUILD_TOWER
                    or not same_position):
                raise ValidationError("Mã yêu cầu đã được dùng cho thao tác khác.", code="IDEMPOTENCY_CONFLICT")
            entity_id = existing_action.payload.get("entity_id")
            existing_entity = GameEntity.objects.filter(pk=entity_id).first()
            if existing_entity and str(unit_type_code_or_id) not in (
                    str(existing_entity.unit_type_id), existing_action.payload.get("unit_type_code")):
                raise ValidationError("Mã yêu cầu đã được dùng cho thao tác khác.", code="IDEMPOTENCY_CONFLICT")
            return existing_action, existing_entity

        ActionPolicy.require_context(match_locked, team_locked, "BUILD_TOWER", actor)

        # 3. Unit type validation (must be TOWER)
        unit_query = Q(code=str(unit_type_code_or_id).strip())
        try:
            val_uuid = uuid.UUID(str(unit_type_code_or_id).strip())
            unit_query |= Q(id=val_uuid)
        except (ValueError, AttributeError):
            pass

        try:
            tower_unit = UnitType.objects.get(unit_query)
        except UnitType.DoesNotExist:
            raise ValidationError(f"Công sự '{unit_type_code_or_id}' không tồn tại.")

        if not tower_unit.is_active:
            raise ValidationError(f"Công sự '{tower_unit.name}' hiện không kích hoạt.")

        if tower_unit.category != EntityCategory.TOWER:
            raise ValidationError(f"'{tower_unit.name}' không phải công sự phòng thủ (TOWER).")

        ActionPolicy.require_purchase(match_locked, team_locked, "BUILD_TOWER", tower_unit)

        state = {}
        if grid_mode:
            from apps.combat.map import get_game_map
            graph = get_game_map(max(2, match_locked.teams.count()), match_locked.configuration.get("arena_layout_version", 3))
            node_id, state = placement_grid(graph).validate(
                grid_row, grid_col, tower_unit.code, MapDefinition.get_team_index(team_locked)+1,
                GameEntity.objects.filter(match=match_locked, entity_kind__in=["TOWER", "SPECIAL", "UNIT"],
                    status__in=["ACTIVE", "QUEUED", "DISABLED"]).select_related("unit_type").only(
                        "entity_kind", "simulation_state", "current_node_id", "unit_type__code"))
        else:
            if grid_row is not None or grid_col is not None or not MapDefinition.is_valid_tower_slot(team_locked, node_id):
                raise ValidationError("Vị trí không hợp lệ hoặc không thuộc lãnh thổ phòng thủ của đội.", code="INVALID_POSITION")
            if GameEntity.objects.filter(match=match_locked, current_node_id=node_id,
                    status__in=["ACTIVE", "QUEUED", "DISABLED"]).exists():
                raise ValidationError("Vị trí đã có tháp phòng thủ đang hoạt động.", code="INVALID_POSITION")

        if tower_unit.code == "shield_generator" and not grid_mode:
            from apps.combat.map import get_game_map
            from apps.units.placement import shield_position_allowed
            graph = get_game_map(max(2, match_locked.teams.count()), match_locked.configuration.get("arena_layout_version", 3))
            node = graph.nodes[node_id]
            if not shield_position_allowed(graph, MapDefinition.get_team_index(team_locked) + 1, (node.x, node.y)):
                raise ValidationError("Máy tạo khiên phải nằm trong vòng khiên quanh căn cứ.", code="PLACEMENT_SHIELD_RANGE")

        # 6. Coin debit via EconomyService (§2.3, §7.3)
        cost = tower_unit.cost
        state["build_cost"] = cost
        EconomyService.debit(
            team=team_locked,
            amount=cost,
            transaction_type=TransactionType.BUILD_TOWER,
            reference_type="BUILD_TOWER",
            reference_id=idempotency_key,
            description=f"Xây dựng {tower_unit.name} tại {node_id}",
        )
        team_locked.refresh_from_db(fields=["coins"])

        # 7. Create GameEntity & GameAction
        from apps.units.upgrades import effective_stats, team_level
        level = team_level(team_locked, tower_unit)
        tower_hp = effective_stats(tower_unit, level, match_locked.configuration)["hp"]
        shield_amount = tower_unit.base_stats.get("shield", 0)

        entity = GameEntity.objects.create(
            match=match_locked,
            team=team_locked,
            unit_type=tower_unit,
            entity_kind=EntityCategory.TOWER,
            current_hp=tower_hp,
            max_hp=tower_hp,
            current_shield=shield_amount,
            level=level,
            status=EntityStatus.ACTIVE,
            current_node_id=node_id,
            simulation_state=state,
        )

        action = GameAction.objects.create(
            match=match_locked,
            team=team_locked,
            actor=actor,
            action_type=ActionType.BUILD_TOWER,
            payload={
                "unit_type_code": tower_unit.code,
                "unit_name": tower_unit.name,
                "node_id": node_id,
                "grid_row": grid_row, "grid_col": grid_col,
                "simulation_state": state,
                "entity_id": str(entity.id),
                "cost": cost,
            },
            status=ActionStatus.ACCEPTED,
            idempotency_key=idempotency_key,
        )

        MatchService.record_match_event(
            match=match_locked,
            event_type="TOWER_BUILT",
            payload={
                "team_id": str(team_locked.id),
                "entity_id": str(entity.id),
                "level": level,
                **effective_stats(tower_unit, level, match_locked.configuration),
                "tower_code": tower_unit.code,
                "tower_name": tower_unit.name,
                "current_hp": entity.current_hp,
                "max_hp": entity.max_hp,
                "range": tower_unit.base_stats.get("range", 0),
                "status": entity.status,
                "node_id": node_id,
                "grid_row": grid_row, "grid_col": grid_col,
                "simulation_state": state,
                "cost": cost,
                "coins_after": team_locked.coins,
            },
        )

        return action, entity

    @classmethod
    @transaction.atomic
    def sell_tower(cls, match, team, entity_id, actor=None, idempotency_key=None):
        key = str(idempotency_key if idempotency_key is not None else uuid.uuid4()).strip()
        if not key or len(key) > 128:
            raise ValidationError("Mã yêu cầu không hợp lệ.", code="INVALID_REQUEST_ID")
        match = Match.objects.select_for_update().get(pk=match.pk)
        team = Team.objects.select_for_update().get(pk=team.pk)
        if team.match_id != match.pk or (actor and (
                actor.team_id != team.pk or actor.role == "SPECTATOR")):
            raise ValidationError("Bạn không có quyền điều khiển đội này.", code="SPECTATOR_READ_ONLY")
        previous = GameAction.objects.filter(team=team, idempotency_key=key).first()
        if previous:
            if previous.action_type != ActionType.SELL_TOWER or previous.payload.get("entity_id") != str(entity_id):
                raise ValidationError("Mã yêu cầu đã được dùng cho thao tác khác.", code="IDEMPOTENCY_CONFLICT")
            return previous, GameEntity.objects.get(pk=entity_id, team=team, match=match)
        ActionPolicy.require_context(match, team, "SELL_TOWER", actor)
        entity = GameEntity.objects.select_for_update().select_related("unit_type").filter(
            pk=entity_id, match=match, team=team, entity_kind=EntityCategory.TOWER).first()
        if not entity:
            raise ValidationError("Tháp không thuộc đội của bạn.", code="INVALID_ENTITY")
        if entity.status not in (EntityStatus.ACTIVE, EntityStatus.DISABLED) or entity.current_hp <= 0:
            raise ValidationError("Tháp không còn tồn tại để bán.", code="INVALID_ENTITY")
        original_cost = entity.simulation_state.get("build_cost")
        if original_cost is None:
            build = GameAction.objects.filter(team=team, action_type=ActionType.BUILD_TOWER,
                payload__entity_id=str(entity.pk)).first()
            original_cost = build.payload["cost"] if build else entity.unit_type.cost
        refund = max(0, int(original_cost)) * min(entity.current_hp, entity.max_hp) // max(1, entity.max_hp)
        from django.utils import timezone
        entity.status = EntityStatus.DESTROYED
        entity.destroyed_at = timezone.now()
        entity.save(update_fields=["status", "destroyed_at"])
        if refund:
            EconomyService.credit(team, refund, transaction_type=TransactionType.REFUND,
                reference_type="SELL_TOWER", reference_id=key,
                description=f"Bán {entity.unit_type.name} ({entity.current_hp}/{entity.max_hp} HP)")
        team.refresh_from_db(fields=["coins"])
        payload = {"entity_id": str(entity.pk), "team_id": str(team.pk),
                   "original_cost": original_cost, "current_hp": entity.current_hp,
                   "max_hp": entity.max_hp, "refund": refund, "coins_after": team.coins}
        action = GameAction.objects.create(match=match, team=team, actor=actor,
            action_type=ActionType.SELL_TOWER, status=ActionStatus.ACCEPTED,
            idempotency_key=key, payload=payload)
        MatchService.record_match_event(match, "TOWER_SOLD", payload)
        return action, entity

    @classmethod
    @transaction.atomic
    def upgrade_tower(
        cls,
        match: Match,
        team: Team,
        entity_id: str,
        actor: Optional[TeamMember] = None,
        idempotency_key: Optional[str] = None,
    ) -> Tuple[GameAction, GameEntity]:
        idempotency_key = idempotency_key or str(uuid.uuid4())
        entity = GameEntity.objects.select_related("unit_type").filter(pk=entity_id, match=match, team=team, entity_kind="TOWER").first()
        if not entity:
            raise ValidationError("Tháp không thuộc đội của bạn.")
        from apps.units.upgrades import team_level
        previous = GameAction.objects.filter(team=team, idempotency_key=idempotency_key).first()
        expected = previous.payload.get("previous_level") if previous and previous.action_type == ActionType.UPGRADE_TEAM_TYPE else team_level(team, entity.unit_type)
        action, _ = TeamUpgradeService.purchase(match, team, entity.unit_type.code,
            expected, idempotency_key, actor)
        entity.refresh_from_db()
        return action, entity

    @classmethod
    @transaction.atomic
    def repair_base(
        cls,
        match: Match,
        team: Team,
        actor: Optional[TeamMember] = None,
        idempotency_key: Optional[str] = None,
    ) -> GameAction:
        """
        Restore 50 base HP, up to maximum base HP (§8.4).
        Limit: 1 repair action per team per round (§8.4, §8.5).
        """
        idempotency_key = (idempotency_key or str(uuid.uuid4())).strip()

        # Idempotency check
        match_locked = Match.objects.select_for_update().get(pk=match.pk)
        team_locked = Team.objects.select_for_update().get(pk=team.pk)

        existing_action = GameAction.objects.filter(
            team=team,
            idempotency_key=idempotency_key,
        ).first()
        if existing_action:
            return existing_action

        # Config gating
        special_enabled = match_locked.configuration.get("special_actions_enabled", {})
        if not special_enabled.get("repair", True):
            raise ValidationError("Thao tác gia cố căn cứ đã bị vô hiệu hóa trong cấu hình trận đấu.")

        ActionPolicy.require_context(match_locked, team_locked, "REPAIR_BASE", actor)

        if team_locked.base_hp >= team_locked.initial_base_hp:
            raise ValidationError(
                f"Căn cứ đã đạt lượng máu tối đa ({team_locked.initial_base_hp} HP), không cần sửa chữa."
            )

        # Limit: 1 repair action per round (§8.4, §8.5)
        # Check if a repair action was already accepted in the current round window
        round_duration = match_locked.configuration.get("round_duration_seconds", 30)
        recent_repair = GameAction.objects.filter(
            team=team_locked,
            action_type=ActionType.REPAIR_BASE,
            status=ActionStatus.ACCEPTED,
        ).exists()
        if recent_repair:
            raise ValidationError(
                f"Đội đã thực hiện sửa chữa căn cứ trong round này. Mỗi round chỉ được sửa chữa 1 lần (chu kỳ {round_duration}s)."
            )

        cost = match_locked.configuration.get("special_action_costs", {}).get("repair", 20)
        heal_amount = 50

        EconomyService.debit(
            team=team_locked,
            amount=cost,
            transaction_type=TransactionType.REPAIR_BASE,
            reference_type="REPAIR_BASE",
            reference_id=idempotency_key,
            description="Gia cố sửa chữa căn cứ (+50 HP)",
        )
        team_locked.refresh_from_db(fields=["coins"])

        team_locked.base_hp = min(team_locked.initial_base_hp, team_locked.base_hp + heal_amount)
        team_locked.save(update_fields=["base_hp"])

        action = GameAction.objects.create(
            match=match_locked,
            team=team_locked,
            actor=actor,
            action_type=ActionType.REPAIR_BASE,
            payload={
                "healed_amount": heal_amount,
                "base_hp_after": team_locked.base_hp,
                "cost": cost,
            },
            status=ActionStatus.ACCEPTED,
            idempotency_key=idempotency_key,
        )

        MatchService.record_match_event(
            match=match_locked,
            event_type="BASE_REPAIRED",
            payload={
                "team_id": str(team_locked.id),
                "healed_amount": heal_amount,
                "base_hp": team_locked.base_hp,
                "cost": cost,
                "coins_after": team_locked.coins,
            },
        )

        return action

    @classmethod
    @transaction.atomic
    def scout(
        cls,
        match: Match,
        team: Team,
        target_team_id: str,
        actor: Optional[TeamMember] = None,
        idempotency_key: Optional[str] = None,
    ) -> Tuple[GameAction, Dict[str, Any]]:
        """
        Scout an opponent team's defenses (§8.4).
        Reveals unlocked units and defensive structures.
        Does NOT reveal pending question or unrevealed answers.
        Cost: 10 coins (configurable).
        """
        idempotency_key = (idempotency_key or str(uuid.uuid4())).strip()

        # Idempotency check
        match_locked = Match.objects.select_for_update().get(pk=match.pk)
        team_locked = Team.objects.select_for_update().get(pk=team.pk)

        existing_action = GameAction.objects.filter(
            team=team,
            idempotency_key=idempotency_key,
        ).first()
        if existing_action:
            return existing_action, existing_action.payload.get("scout_data", {})


        special_enabled = match_locked.configuration.get("special_actions_enabled", {})
        if not special_enabled.get("scout", True):
            raise ValidationError("Thao tác trinh sát (Scout) đã bị vô hiệu hóa.")

        ActionPolicy.require_context(match_locked, team_locked, "SCOUT", actor)

        if str(target_team_id).strip() == str(team_locked.id):
            raise ValidationError("Không thể tự trinh sát đội của chính mình.")

        try:
            target_team = match_locked.teams.get(pk=target_team_id)
        except Team.DoesNotExist:
            raise ValidationError("Đội mục tiêu không tồn tại.")

        if target_team.status != TeamStatus.ACTIVE:
            raise ValidationError(f"Đội {target_team.name} đã bị loại khỏi trận đấu.")

        cost = match_locked.configuration.get("special_action_costs", {}).get("scout", 10)
        EconomyService.debit(
            team=team_locked,
            amount=cost,
            transaction_type=TransactionType.SPECIAL_ACTION,
            reference_type="SCOUT",
            reference_id=idempotency_key,
            description=f"Trinh sát đội {target_team.name}",
        )
        team_locked.refresh_from_db(fields=["coins"])

        # Build scout intelligence: unlocked units + towers only (§8.4)
        unlocked_units = [
            {"code": u.code, "name": u.name, "category": u.category}
            for u in UnitType.objects.filter(
                Q(is_starter=True) | Q(team_unlocks__team=target_team)
            ).distinct()
        ]

        active_towers = [
            {
                "id": str(t.id),
                "name": t.unit_type.name,
                "code": t.unit_type.code,
                "node_id": t.current_node_id,
                "hp": t.current_hp,
                "level": t.level,
            }
            for t in GameEntity.objects.filter(
                team=target_team,
                entity_kind=EntityCategory.TOWER,
                status=EntityStatus.ACTIVE,
            )
        ]

        scout_data = {
            "target_team_id": str(target_team.id),
            "target_team_name": target_team.name,
            "base_hp": target_team.base_hp,
            "base_shield": target_team.base_shield,
            "unlocked_units": unlocked_units,
            "towers": active_towers,
        }

        action = GameAction.objects.create(
            match=match_locked,
            team=team_locked,
            actor=actor,
            action_type=ActionType.SCOUT,
            payload={
                "target_team_id": str(target_team.id),
                "cost": cost,
                "scout_data": scout_data,
            },
            status=ActionStatus.ACCEPTED,
            idempotency_key=idempotency_key,
        )

        MatchService.record_match_event(
            match=match_locked,
            event_type="SCOUT_PERFORMED",
            payload={
                "team_id": str(team_locked.id),
                "target_team_id": str(target_team.id),
                "cost": cost,
            },
        )

        return action, scout_data

    @classmethod
    @transaction.atomic
    def emp(
        cls,
        match: Match,
        team: Team,
        target_entity_id: str,
        actor: Optional[TeamMember] = None,
        idempotency_key: Optional[str] = None,
    ) -> Tuple[GameAction, GameEntity]:
        """
        Disables an eligible enemy defensive tower for 1 combat round (§8.4).
        Cannot target base directly. Does not destroy the tower.
        Cost: 30 coins (configurable).
        """
        idempotency_key = (idempotency_key or str(uuid.uuid4())).strip()

        # Idempotency check
        match_locked = Match.objects.select_for_update().get(pk=match.pk)
        team_locked = Team.objects.select_for_update().get(pk=team.pk)

        existing_action = GameAction.objects.filter(
            team=team,
            idempotency_key=idempotency_key,
        ).first()
        if existing_action:
            action_entity_id = existing_action.payload.get("target_entity_id")
            entity = GameEntity.objects.filter(pk=action_entity_id).first()
            return existing_action, entity


        special_enabled = match_locked.configuration.get("special_actions_enabled", {})
        if not special_enabled.get("emp", True):
            raise ValidationError("Thao tác xung điện EMP đã bị vô hiệu hóa.")

        ActionPolicy.require_context(match_locked, team_locked, "EMP", actor)

        try:
            target_entity = GameEntity.objects.select_for_update().get(
                pk=target_entity_id,
                match=match_locked,
            )
        except GameEntity.DoesNotExist:
            raise ValidationError("Tháp phòng thủ mục tiêu không tồn tại.")

        if target_entity.team_id == team_locked.id:
            raise ValidationError("Không thể nhắm xung điện EMP vào tháp của chính đội mình.")

        if target_entity.entity_kind != EntityCategory.TOWER:
            raise ValidationError("EMP chỉ có thể vô hiệu hóa tháp phòng thủ (không được nhắm vào căn cứ).")

        if target_entity.status != EntityStatus.ACTIVE:
            raise ValidationError("Tháp mục tiêu hiện không hoạt động hoặc đã bị vô hiệu hóa.")

        cost = match_locked.configuration.get("special_action_costs", {}).get("emp", 30)
        EconomyService.debit(
            team=team_locked,
            amount=cost,
            transaction_type=TransactionType.SPECIAL_ACTION,
            reference_type="EMP",
            reference_id=idempotency_key,
            description=f"EMP vô hiệu hóa tháp {target_entity.unit_type.name} của đội {target_entity.team.name}",
        )
        team_locked.refresh_from_db(fields=["coins"])

        target_entity.status = EntityStatus.DISABLED
        target_entity.save(update_fields=["status"])

        action = GameAction.objects.create(
            match=match_locked,
            team=team_locked,
            actor=actor,
            action_type=ActionType.EMP,
            payload={
                "target_entity_id": str(target_entity.id),
                "target_team_id": str(target_entity.team_id),
                "cost": cost,
            },
            status=ActionStatus.ACCEPTED,
            idempotency_key=idempotency_key,
        )

        MatchService.record_match_event(
            match=match_locked,
            event_type="EMP_FIRED",
            payload={
                "team_id": str(team_locked.id),
                "target_entity_id": str(target_entity.id),
                "cost": cost,
            },
        )

        return action, target_entity


class TeamUpgradeService:
    @classmethod
    @transaction.atomic
    def purchase(cls, match, team, entity_type, expected_current_level, idempotency_key, actor=None):
        from apps.units.models import TeamUnitUpgrade, TeamUnlock
        from apps.units.upgrades import effective_stats, eligible, upgrade_cost
        match = Match.objects.select_for_update().get(pk=match.pk)
        team = Team.objects.select_for_update().get(pk=team.pk)
        if team.match_id != match.pk or (actor and (actor.team_id != team.pk or actor.role == "SPECTATOR")):
            raise ValidationError("Bạn không có quyền nâng cấp đội này.", code="FORBIDDEN")
        key = str(idempotency_key or "").strip()
        if not key or len(key) > 128:
            raise ValidationError("Cần mã yêu cầu hợp lệ.", code="INVALID_REQUEST_ID")
        code = str(entity_type).lower()
        previous = GameAction.objects.filter(team=team, idempotency_key=key).first()
        if previous:
            if (previous.action_type != ActionType.UPGRADE_TEAM_TYPE or previous.payload["entity_type"] != code
                    or previous.payload["previous_level"] != expected_current_level):
                raise ValidationError("Mã yêu cầu đã dùng cho thao tác khác.", code="IDEMPOTENCY_CONFLICT")
            return previous, previous.payload
        ActionPolicy.require_context(match, team, "UPGRADE_TEAM_TYPE", actor)
        if not match.configuration.get("special_actions_enabled", {}).get("upgrade", True):
            raise ValidationError("Nâng cấp đã bị vô hiệu hóa.")
        unit = UnitType.objects.filter(code=code, is_active=True).first()
        if not unit or not eligible(unit):
            raise ValidationError("Loại đơn vị không thể nâng cấp.", code="INVALID_UNIT")
        if not unit.is_starter and not TeamUnlock.objects.filter(team=team, unit_type=unit).exists():
            raise ValidationError("Mở khóa đơn vị trước khi nâng cấp.", code="UNIT_LOCKED")
        upgrade, _ = TeamUnitUpgrade.objects.get_or_create(team=team, unit_type=unit)
        if type(expected_current_level) is not int or upgrade.level != expected_current_level:
            raise ValidationError("Cấp đã thay đổi. Vui lòng tải lại.", code="STALE_LEVEL")
        cost = upgrade_cost(unit, upgrade.level, match.configuration)
        if cost is None:
            raise ValidationError("CẤP TỐI ĐA", code="MAX_LEVEL")
        if type(cost) is not int or cost <= 0:
            raise ValidationError("Cấu hình chi phí nâng cấp không hợp lệ.")
        EconomyService.debit(team, cost, TransactionType.PURCHASE, "UPGRADE_TEAM_TYPE", key,
                             f"Nâng cấp toàn đội {unit.name} cấp {upgrade.level + 1}")
        old_level = upgrade.level
        upgrade.level += 1
        upgrade.save(update_fields=["level"])
        stats = effective_stats(unit, upgrade.level, match.configuration)
        entities = list(GameEntity.objects.select_for_update().filter(match=match, team=team,
            unit_type=unit, status__in=["ACTIVE", "QUEUED", "DISABLED"], current_hp__gt=0))
        for entity in entities:
            entity.current_hp = min(stats["hp"], max(1, int(entity.current_hp / max(1, entity.max_hp) * stats["hp"] + .5)))
            entity.max_hp = stats["hp"]
            entity.level = upgrade.level
        if entities:
            GameEntity.objects.bulk_update(entities, ["current_hp", "max_hp", "level"])
        team.refresh_from_db(fields=["coins"])
        payload = {"team_id": str(team.pk), "entity_type": code, "previous_level": old_level,
                   "level": upgrade.level, "stats": stats, "cost": cost, "coins_after": team.coins,
                   "stat_version": 1}
        action = GameAction.objects.create(match=match, team=team, actor=actor,
            action_type=ActionType.UPGRADE_TEAM_TYPE, payload=payload, status=ActionStatus.ACCEPTED, idempotency_key=key)
        MatchService.record_match_event(match, "TEAM_UNIT_UPGRADED", payload)
        return action, payload
