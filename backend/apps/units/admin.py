from django.contrib import admin

from apps.units.models import GameAction, GameEntity, TeamUnlock, UnitType


@admin.register(UnitType)
class UnitTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "category", "cost", "is_starter", "is_unlockable", "is_active"]
    list_filter = ["category", "is_starter", "is_unlockable", "is_active"]
    search_fields = ["name", "code", "description"]


@admin.register(TeamUnlock)
class TeamUnlockAdmin(admin.ModelAdmin):
    list_display = ["team", "unit_type", "unlocked_at", "source_team_question"]
    list_filter = ["unit_type__category", "unit_type"]
    search_fields = ["team__name", "unit_type__name"]


@admin.register(GameEntity)
class GameEntityAdmin(admin.ModelAdmin):
    # Levels are changed through the authoritative team purchase service.
    readonly_fields = ["level"]
    list_display = [
        "id",
        "match",
        "team",
        "unit_type",
        "entity_kind",
        "current_hp",
        "level",
        "status",
        "current_node_id",
        "created_at",
    ]
    list_filter = ["entity_kind", "status", "match"]
    search_fields = ["unit_type__name", "team__name", "current_node_id"]


@admin.register(GameAction)
class GameActionAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "match",
        "team",
        "action_type",
        "status",
        "idempotency_key",
        "created_at",
    ]
    list_filter = ["action_type", "status", "match"]
    search_fields = ["team__name", "idempotency_key"]
