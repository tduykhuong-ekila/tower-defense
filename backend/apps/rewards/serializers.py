from rest_framework import serializers

from apps.rewards.models import RewardClaim, RewardType
from apps.units.models import TeamUnlock
from apps.units.serializers import UnitTypeSerializer


class ClaimRewardSerializer(serializers.Serializer):
    team_question_id = serializers.UUIDField(required=True)
    reward_type = serializers.ChoiceField(choices=RewardType.choices, required=True)
    unit_type_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    idempotency_key = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, max_length=128
    )


class RewardClaimSerializer(serializers.ModelSerializer):
    unlocked_unit = serializers.SerializerMethodField()
    team_coins = serializers.SerializerMethodField()
    unlocked_unit_codes = serializers.SerializerMethodField()

    class Meta:
        model = RewardClaim
        fields = [
            "id",
            "team_question_id",
            "team_id",
            "reward_type",
            "coin_amount",
            "unlocked_unit",
            "team_coins",
            "unlocked_unit_codes",
            "status",
            "idempotency_key",
            "claimed_at",
        ]

    def get_unlocked_unit(self, obj):
        if obj.unlocked_unit_type:
            return UnitTypeSerializer(obj.unlocked_unit_type, context=self.context).data
        return None

    def get_team_coins(self, obj) -> int:
        return obj.team.coins

    def get_unlocked_unit_codes(self, obj):
        return list(
            TeamUnlock.objects.filter(team=obj.team).values_list("unit_type__code", flat=True)
        )
