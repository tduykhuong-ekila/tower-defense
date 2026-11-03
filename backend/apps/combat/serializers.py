from rest_framework import serializers

from apps.combat.models import MatchResult


class MatchResultSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(source="team.name", read_only=True)

    class Meta:
        model = MatchResult
        fields = [
            "id",
            "match_id",
            "team_id",
            "team_name",
            "final_rank",
            "final_score",
            "bases_destroyed",
            "base_damage_dealt",
            "correct_answers",
            "remaining_base_hp",
            "remaining_coins",
            "surviving_towers",
            "created_at",
        ]
        read_only_fields = fields
