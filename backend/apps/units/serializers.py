from rest_framework import serializers

from apps.units.models import (
    GameAction,
    GameEntity,
    TeamUnlock,
    UnitType,
)
from apps.units.upgrades import MAX_UPGRADE_LEVEL


class UnitTypeSerializer(serializers.ModelSerializer):
    level = serializers.SerializerMethodField()
    upgrade = serializers.SerializerMethodField()
    attack_interval_seconds = serializers.SerializerMethodField()
    hp = serializers.SerializerMethodField()
    movement_speed = serializers.SerializerMethodField()
    max_active_units = serializers.SerializerMethodField()
    damage = serializers.SerializerMethodField()
    range = serializers.SerializerMethodField()
    movement = serializers.SerializerMethodField()
    strategic_role = serializers.SerializerMethodField()
    is_unlocked = serializers.SerializerMethodField()

    class Meta:
        model = UnitType
        fields = [
            "id",
            "code",
            "name",
            "category",
            "description",
            "cost",
            "is_starter",
            "is_unlockable",
            "is_active",
            "prerequisites",
            "base_stats",
            "level", "upgrade", "attack_interval_seconds",
            "hp",
            "movement_speed",
            "max_active_units",
            "damage",
            "range",
            "movement",
            "strategic_role",
            "is_unlocked",
        ]

    def get_level(self, obj):
        from apps.units.upgrades import team_level
        cache = self.context.setdefault("upgrade_levels", {})
        if obj.pk not in cache:
            cache[obj.pk] = team_level(self.context.get("team"), obj)
        return cache[obj.pk]

    def effective(self, obj, level=None):
        from apps.units.upgrades import effective_stats
        return effective_stats(obj, self.get_level(obj) if level is None else level,
                               getattr(self.context.get("match"), "configuration", {}))

    def get_upgrade(self, obj):
        from apps.units.upgrades import eligible, upgrade_cost
        level = self.get_level(obj)
        cost = upgrade_cost(obj, level, getattr(self.context.get("match"), "configuration", {}))
        return {"eligible": eligible(obj), "max_level": MAX_UPGRADE_LEVEL, "cost": cost,
                "current_stats": self.effective(obj),
                "next_stats": self.effective(obj, level + 1) if cost is not None else None}

    def get_hp(self, obj):
        return self.effective(obj)["hp"]

    def get_attack_interval_seconds(self, obj):
        return self.effective(obj)["attack_interval_seconds"]

    def get_movement_speed(self, obj):
        from apps.combat.balance import movement_multiplier
        return movement_multiplier(obj.code) if obj.category == "UNIT" else 0

    def get_max_active_units(self, obj):
        if obj.code == "infantry" or obj.category == "TOWER":
            return None
        config = getattr(self.context.get("match"), "configuration", {})
        return config.get("max_active_units_per_team", 5)

    def get_damage(self, obj):
        return self.effective(obj)["damage"]

    def get_range(self, obj) -> float:
        return (obj.base_stats or {}).get("range", 1)

    def get_movement(self, obj) -> int:
        return (obj.base_stats or {}).get("movement", 1)

    def get_strategic_role(self, obj) -> str:
        return (obj.base_stats or {}).get("strategic_role", obj.description)

    def get_is_unlocked(self, obj) -> bool:
        team = self.context.get("team")
        if not team:
            return obj.is_starter
        if obj.is_starter:
            return True
        return TeamUnlock.objects.filter(team=team, unit_type=obj).exists()


class UnitTypeAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnitType
        fields = [
            "id",
            "code",
            "name",
            "category",
            "description",
            "cost",
            "is_starter",
            "is_unlockable",
            "is_active",
            "prerequisites",
            "base_stats",
        ]



class GameEntitySerializer(serializers.ModelSerializer):
    damage = serializers.SerializerMethodField()
    attack_interval_seconds = serializers.SerializerMethodField()

    def get_damage(self, obj):
        from apps.combat.balance import inspection_stats
        return inspection_stats(obj, getattr(self.context.get("match"), "configuration", None))["damage"]

    def get_attack_interval_seconds(self, obj):
        from apps.combat.balance import inspection_stats
        return inspection_stats(obj, getattr(self.context.get("match"), "configuration", None)).get("attack_interval_seconds")

    range = serializers.SerializerMethodField()
    movement_speed = serializers.SerializerMethodField()
    unit_type_code = serializers.CharField(source="unit_type.code", read_only=True)
    name = serializers.CharField(source="unit_type.name", read_only=True)
    target_team_name = serializers.CharField(source="target_team.name", read_only=True, allow_null=True)

    class Meta:
        model = GameEntity
        fields = [
            "id",
            "match_id",
            "team_id",
            "unit_type_id",
            "unit_type_code",
            "name",
            "entity_kind",
            "current_hp",
            "max_hp",
            "range",
            "damage",
            "attack_interval_seconds",
            "movement_speed",
            "current_shield",
            "level",
            "status",
            "current_node_id",
            "target_team_id",
            "target_team_name",
            "target_node_id",
            "simulation_state",
            "created_at",
            "destroyed_at",
        ]
        read_only_fields = fields

    def get_range(self, obj):
        from apps.combat.balance import entity_attack_range
        return entity_attack_range(obj)

    def get_movement_speed(self, obj):
        from apps.combat.balance import movement_multiplier
        return movement_multiplier(obj.unit_type.code) if obj.entity_kind == "UNIT" else 0


class GameActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = GameAction
        fields = [
            "id",
            "match_id",
            "team_id",
            "actor_id",
            "action_type",
            "payload",
            "status",
            "idempotency_key",
            "created_at",
            "resolved_at",
            "failure_reason",
        ]
        read_only_fields = fields


class DeploymentQuantityField(serializers.IntegerField):
    def to_internal_value(self, data):
        # JSON booleans, decimals (even 1.0), strings and null are not quantities.
        if type(data) is not int:
            self.fail("invalid")
        return super().to_internal_value(data)


class DeployUnitRequestSerializer(serializers.Serializer):
    unit_type_code_or_id = serializers.CharField(required=True)
    target_team_id = serializers.UUIDField(required=False)
    order = serializers.ChoiceField(choices=["ATTACK", "DEFEND_BASE"], default="ATTACK")
    quantity = DeploymentQuantityField(min_value=1, default=1)
    spawn_node_id = serializers.CharField(required=False, max_length=50)
    idempotency_key = serializers.CharField(required=False, max_length=128, default=None)


class BuildTowerRequestSerializer(serializers.Serializer):
    unit_type_code_or_id = serializers.CharField(required=True)
    node_id = serializers.CharField(required=False, max_length=50, default="")
    grid_row = serializers.JSONField(required=False)
    grid_col = serializers.JSONField(required=False)
    idempotency_key = serializers.CharField(required=False, max_length=128, default=None)


class SellTowerRequestSerializer(serializers.Serializer):
    entity_id = serializers.UUIDField(required=True)
    idempotency_key = serializers.CharField(required=False, max_length=128, default=None)


class UpgradeTowerRequestSerializer(serializers.Serializer):
    entity_id = serializers.UUIDField(required=True)
    idempotency_key = serializers.CharField(required=False, max_length=128, default=None)


class RepairBaseRequestSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(required=False, max_length=128, default=None)


class ScoutRequestSerializer(serializers.Serializer):
    target_team_id = serializers.UUIDField(required=True)
    idempotency_key = serializers.CharField(required=False, max_length=128, default=None)


class EmpRequestSerializer(serializers.Serializer):
    target_entity_id = serializers.UUIDField(required=True)
    idempotency_key = serializers.CharField(required=False, max_length=128, default=None)


class TeamUpgradeRequestSerializer(serializers.Serializer):
    entity_type = serializers.CharField(max_length=50)
    expected_current_level = DeploymentQuantityField(min_value=1, max_value=MAX_UPGRADE_LEVEL)
    idempotency_key = serializers.CharField(max_length=128)


class ArmyCommandRequestSerializer(serializers.Serializer):
    command_type = serializers.ChoiceField(choices=["RETARGET", "RETREAT_ALL", "DEFEND_BASE"])
    unit_ids = serializers.ListField(child=serializers.UUIDField(), required=False)
    target_team_id = serializers.UUIDField(required=False)
    idempotency_key = serializers.CharField(max_length=128)
    expected_command_version = serializers.IntegerField(required=False, min_value=0)
