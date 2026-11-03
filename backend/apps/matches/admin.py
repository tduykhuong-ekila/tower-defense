from django.contrib import admin

from apps.matches.models import Match, MatchEvent


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ("id", "room_code", "name", "status", "phase", "is_locked", "created_at")
    list_filter = ("status", "phase", "is_locked")
    search_fields = ("room_code", "name")
    readonly_fields = ("id", "created_at", "updated_at", "host_token_hash")


@admin.register(MatchEvent)
class MatchEventAdmin(admin.ModelAdmin):
    list_display = ("id", "match", "sequence_number", "event_type", "created_at")
    list_filter = ("event_type", "created_at")
    search_fields = ("match__room_code", "event_type")
    readonly_fields = ("id", "created_at")
