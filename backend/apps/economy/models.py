import uuid

from django.db import models


class TransactionType(models.TextChoices):
    INITIAL = "INITIAL", "Initial Coins"
    REWARD_COIN = "REWARD_COIN", "Reward Coin"
    PASSIVE_INCOME = "PASSIVE_INCOME", "Passive Income"
    PURCHASE = "PURCHASE", "Purchase"
    DEPLOY_UNIT = "DEPLOY_UNIT", "Deploy Unit"
    BUILD_TOWER = "BUILD_TOWER", "Build Tower"
    UPGRADE_TOWER = "UPGRADE_TOWER", "Upgrade Tower"
    REPAIR_BASE = "REPAIR_BASE", "Repair Base"
    SPECIAL_ACTION = "SPECIAL_ACTION", "Special Action"
    REFUND = "REFUND", "Refund"
    ADMIN_OVERRIDE = "ADMIN_OVERRIDE", "Admin Override"


class CoinTransaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    match = models.ForeignKey(
        "matches.Match",
        on_delete=models.CASCADE,
        related_name="coin_transactions",
    )
    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.CASCADE,
        related_name="coin_transactions",
    )
    amount = models.IntegerField()
    balance_after = models.IntegerField()
    transaction_type = models.CharField(
        max_length=50,
        choices=TransactionType.choices,
        default=TransactionType.REWARD_COIN,
    )
    reference_type = models.CharField(max_length=50, blank=True, default="", db_index=True)
    reference_id = models.CharField(max_length=128, blank=True, null=True, db_index=True)
    description = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.team.name}: {self.amount:+d} ({self.transaction_type}) => {self.balance_after}"
