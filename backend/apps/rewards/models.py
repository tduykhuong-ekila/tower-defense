import uuid

from django.db import models


class RewardType(models.TextChoices):
    COIN = "COIN", "Receive Coins"
    UNLOCK = "UNLOCK", "Unlock Unit"


class RewardClaimStatus(models.TextChoices):
    CLAIMED = "CLAIMED", "Claimed"
    FAILED = "FAILED", "Failed"


class RewardClaim(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    team_question = models.OneToOneField(
        "questions.TeamQuestion",
        on_delete=models.CASCADE,
        related_name="reward_claim",
    )
    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.CASCADE,
        related_name="reward_claims",
    )
    reward_type = models.CharField(
        max_length=20,
        choices=RewardType.choices,
    )
    coin_amount = models.IntegerField(default=0)
    unlocked_unit_type = models.ForeignKey(
        "units.UnitType",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="claimed_unlocks",
    )
    status = models.CharField(
        max_length=20,
        choices=RewardClaimStatus.choices,
        default=RewardClaimStatus.CLAIMED,
    )
    idempotency_key = models.CharField(max_length=128, blank=True, null=True, db_index=True)
    claimed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-claimed_at"]

    def __str__(self):
        return f"Claim {self.id} for Team {self.team.name}: {self.reward_type}"
