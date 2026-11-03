from django.contrib import admin

from apps.rewards.models import RewardClaim


@admin.register(RewardClaim)
class RewardClaimAdmin(admin.ModelAdmin):
    list_display = ["id", "team", "team_question", "reward_type", "coin_amount", "unlocked_unit_type", "status", "claimed_at"]
    list_filter = ["reward_type", "status"]
    search_fields = ["team__name", "idempotency_key"]
