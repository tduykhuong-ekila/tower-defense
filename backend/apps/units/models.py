import uuid

from django.core.exceptions import ValidationError
from django.db import models


class EntityCategory(models.TextChoices):
    UNIT = "UNIT", "Unit"
    TOWER = "TOWER", "Tower"
    SPECIAL = "SPECIAL", "Special"


class EntityStatus(models.TextChoices):
    QUEUED = "QUEUED", "Queued"
    ACTIVE = "ACTIVE", "Active"
    DISABLED = "DISABLED", "Disabled"
    DESTROYED = "DESTROYED", "Destroyed"


class ActionType(models.TextChoices):
    DEFEND_BASE = "DEFEND_BASE", "Defend own base"
    RETARGET = "RETARGET", "Retarget troops"
    RETREAT_ALL = "RETREAT_ALL", "Retreat all troops"
    DEPLOY_UNIT = "DEPLOY_UNIT", "Deploy Unit"
    BUILD_TOWER = "BUILD_TOWER", "Build Tower"
    SELL_TOWER = "SELL_TOWER", "Sell Tower"
    UPGRADE_TEAM_TYPE = "UPGRADE_TEAM_TYPE", "Upgrade Team Type"
    UPGRADE_TOWER = "UPGRADE_TOWER", "Upgrade Tower"
    REPAIR_BASE = "REPAIR_BASE", "Repair Base"
    SCOUT = "SCOUT", "Scout"
    EMP = "EMP", "EMP"


class ActionStatus(models.TextChoices):
    QUEUED = "QUEUED", "Queued"
    ACCEPTED = "ACCEPTED", "Accepted"
    RESOLVED = "RESOLVED", "Resolved"
    REJECTED = "REJECTED", "Rejected"
    CANCELLED = "CANCELLED", "Cancelled"


def validate_unit_base_stats(base_stats, category):
    """Validate JSON base_stats schema and required attributes (§19.7, §8)."""
    if not isinstance(base_stats, dict):
        raise ValidationError("base_stats must be a valid JSON object.")

    if category == EntityCategory.UNIT:
        required_fields = ["hp", "damage", "range"]
        for f in required_fields:
            if f not in base_stats:
                raise ValidationError(f"Unit base_stats missing required field: {f}")
            val = base_stats[f]
            if not isinstance(val, (int, float)) or val < 0:
                raise ValidationError(f"Unit base_stats field '{f}' must be a non-negative number.")
    elif category == EntityCategory.TOWER:
        required_fields = ["hp"]
        for f in required_fields:
            if f not in base_stats:
                raise ValidationError(f"Tower base_stats missing required field: {f}")
            val = base_stats[f]
            if not isinstance(val, (int, float)) or val < 0:
                raise ValidationError(f"Tower base_stats field '{f}' must be a non-negative number.")


class UnitType(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=100)
    category = models.CharField(
        max_length=20,
        choices=EntityCategory.choices,
        default=EntityCategory.UNIT,
    )
    description = models.TextField(blank=True, default="")
    base_stats = models.JSONField(default=dict, blank=True)
    cost = models.IntegerField(default=0)
    is_starter = models.BooleanField(default=False)
    is_unlockable = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    prerequisites = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["cost", "name"]

    def clean(self):
        super().clean()
        if self.base_stats:
            validate_unit_base_stats(self.base_stats, self.category)

    def save(self, *args, **kwargs):
        self.clean()
        if self.category == EntityCategory.UNIT and self.base_stats and self.base_stats.get("movement", 1) > 0:
            from apps.combat.balance import troop_max_hp
            self.base_stats = {**self.base_stats, "hp": troop_max_hp(self.code, self.base_stats)}
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} [{self.code}] ({self.category}, Cost: {self.cost})"


class TeamUnlock(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.CASCADE,
        related_name="unlocked_units",
    )
    unit_type = models.ForeignKey(
        UnitType,
        on_delete=models.CASCADE,
        related_name="team_unlocks",
    )
    unlocked_at = models.DateTimeField(auto_now_add=True)
    source_team_question = models.ForeignKey(
        "questions.TeamQuestion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="source_unlocks",
    )

    class Meta:
        ordering = ["-unlocked_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "unit_type"],
                name="unique_team_unit_unlock",
            ),
        ]

    def __str__(self):
        return f"Team {self.team.name} unlocked {self.unit_type.name}"


class GameEntity(models.Model):
    """
    Represents deployed units and constructed structures (§19.9, §8).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    match = models.ForeignKey(
        "matches.Match",
        on_delete=models.CASCADE,
        related_name="entities",
    )
    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.CASCADE,
        related_name="entities",
    )
    unit_type = models.ForeignKey(
        UnitType,
        on_delete=models.CASCADE,
        related_name="entities",
    )
    entity_kind = models.CharField(
        max_length=20,
        choices=EntityCategory.choices,
        default=EntityCategory.UNIT,
        db_index=True,
    )
    current_hp = models.IntegerField(default=0)
    max_hp = models.IntegerField(default=0)
    current_shield = models.IntegerField(default=0)
    level = models.IntegerField(default=1)
    status = models.CharField(
        max_length=20,
        choices=EntityStatus.choices,
        default=EntityStatus.ACTIVE,
        db_index=True,
    )
    current_node_id = models.CharField(max_length=50, blank=True, default="", db_index=True)
    target_team = models.ForeignKey(
        "teams.Team",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="targeted_by_entities",
    )
    simulation_state = models.JSONField(default=dict, blank=True)
    target_node_id = models.CharField(max_length=50, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    destroyed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(level__gte=1, level__lte=3), name="game_entity_level_1_3"),
        ]
        verbose_name_plural = "game entities"

    def __str__(self):
        return (
            f"Entity {self.unit_type.name} [{self.status}] - "
            f"Team {self.team.name} (HP: {self.current_hp}/{self.max_hp}, Node: {self.current_node_id})"
        )


class GameAction(models.Model):
    """
    Tracks state-changing player commands with idempotency and audit logs (§19.10, §10.1).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    match = models.ForeignKey(
        "matches.Match",
        on_delete=models.CASCADE,
        related_name="game_actions",
    )
    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.CASCADE,
        related_name="game_actions",
    )
    actor = models.ForeignKey(
        "teams.TeamMember",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="game_actions",
    )
    action_type = models.CharField(
        max_length=50,
        choices=ActionType.choices,
        db_index=True,
    )
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=30,
        choices=ActionStatus.choices,
        default=ActionStatus.QUEUED,
        db_index=True,
    )
    idempotency_key = models.CharField(max_length=128, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "idempotency_key"],
                name="unique_team_action_idempotency",
            ),
        ]

    def __str__(self):
        return (
            f"Action {self.action_type} [{self.status}] by "
            f"Team {self.team.name} (key: {self.idempotency_key[:8]}...)"
        )


class TeamUnitUpgrade(models.Model):
    # A Team belongs to exactly one Match, so (team, type) also scopes by match.
    team = models.ForeignKey("teams.Team", on_delete=models.CASCADE, related_name="unit_upgrades")
    unit_type = models.ForeignKey(UnitType, on_delete=models.CASCADE, related_name="team_upgrades")
    level = models.PositiveSmallIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["team", "unit_type"], name="unique_team_type_upgrade"),
            models.CheckConstraint(condition=models.Q(level__gte=1, level__lte=3), name="team_upgrade_level_1_3"),
        ]
