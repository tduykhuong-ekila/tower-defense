from django.contrib import admin

from apps.teams.models import Team, TeamMember


class TeamMemberInline(admin.TabularInline):
    model = TeamMember
    extra = 0
    readonly_fields = ("id", "joined_at", "token_hash")


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "match",
        "base_hp",
        "coins",
        "score",
        "status",
        "is_ready",
        "created_at",
    )
    list_filter = ("status", "is_ready", "created_at")
    search_fields = ("name", "match__room_code")
    inlines = [TeamMemberInline]


@admin.register(TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    list_display = ("id", "display_name", "team", "match", "role", "is_ready", "joined_at")
    list_filter = ("role", "is_ready")
    search_fields = ("display_name", "match__room_code", "team__name")
    readonly_fields = ("id", "joined_at", "token_hash")
