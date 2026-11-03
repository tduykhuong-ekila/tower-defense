from typing import List, Optional

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.economy.models import CoinTransaction, TransactionType
from apps.matches.models import Match, MatchStatus
from apps.matches.services import MatchService
from apps.teams.models import Team, TeamStatus


class EconomyService:
    """
    Authoritative server-side coin economy service (§7, §19.11).
    All coin balance mutations MUST go through credit/debit with row locking
    and atomic transactions. No inter-team transfers allowed (§7.3).
    """

    @classmethod
    @transaction.atomic
    def credit(
        cls,
        team: Team,
        amount: int,
        transaction_type: str = TransactionType.REWARD_COIN,
        reference_type: str = "",
        reference_id: Optional[str] = None,
        description: str = "",
    ) -> CoinTransaction:
        """
        Credit coins to a team atomically with row-locking (§7.3, §19.11).
        """
        if amount <= 0:
            raise ValidationError("Credit amount must be greater than zero.")

        team_locked = Team.objects.select_for_update().get(pk=team.pk)
        team_locked.coins += amount
        team_locked.save(update_fields=["coins"])

        tx = CoinTransaction.objects.create(
            match=team_locked.match,
            team=team_locked,
            amount=amount,
            balance_after=team_locked.coins,
            transaction_type=transaction_type,
            reference_type=reference_type,
            reference_id=str(reference_id) if reference_id else None,
            description=description,
        )

        MatchService.record_match_event(
            match=team_locked.match,
            event_type="COINS_UPDATED",
            payload={
                "team_id": str(team_locked.id),
                "amount": amount,
                "balance_after": team_locked.coins,
                "transaction_type": transaction_type,
                "reference_type": reference_type,
                "reference_id": str(reference_id) if reference_id else None,
            },
        )
        return tx

    @classmethod
    @transaction.atomic
    def debit(
        cls,
        team: Team,
        amount: int,
        transaction_type: str = TransactionType.PURCHASE,
        reference_type: str = "",
        reference_id: Optional[str] = None,
        description: str = "",
    ) -> CoinTransaction:
        """
        Debit coins from a team atomically with row-locking (§7.3, §19.11).
        Fails and leaves balance completely unchanged if insufficient coins.
        """
        if amount <= 0:
            raise ValidationError("Debit amount must be greater than zero.")

        team_locked = Team.objects.select_for_update().get(pk=team.pk)
        if team_locked.coins < amount:
            raise ValidationError(
                f"Không đủ coin. Cần {amount} coin nhưng chỉ có {team_locked.coins} coin."
            )

        team_locked.coins -= amount
        team_locked.save(update_fields=["coins"])

        tx = CoinTransaction.objects.create(
            match=team_locked.match,
            team=team_locked,
            amount=-amount,
            balance_after=team_locked.coins,
            transaction_type=transaction_type,
            reference_type=reference_type,
            reference_id=str(reference_id) if reference_id else None,
            description=description,
        )

        MatchService.record_match_event(
            match=team_locked.match,
            event_type="COINS_UPDATED",
            payload={
                "team_id": str(team_locked.id),
                "amount": -amount,
                "balance_after": team_locked.coins,
                "transaction_type": transaction_type,
                "reference_type": reference_type,
                "reference_id": str(reference_id) if reference_id else None,
            },
        )
        return tx

    @classmethod
    @transaction.atomic
    def award_passive_income(
        cls,
        match: Match,
        round_number: int = 1,
    ) -> List[CoinTransaction]:
        """
        Award passive income (10 coin/round by default) to all active teams (§7.2).
        Configurable via match.configuration['base_income_per_round'].
        Must not award when match is PAUSED or FINISHED.
        """
        match_locked = Match.objects.select_for_update().get(pk=match.pk)
        if match_locked.status != MatchStatus.ACTIVE:
            return []

        income = match_locked.configuration.get("base_income_per_round", 10)
        if income <= 0:
            return []

        active_teams = match_locked.teams.filter(status=TeamStatus.ACTIVE)
        transactions = []
        for team in active_teams:
            tx = cls.credit(
                team=team,
                amount=income,
                transaction_type=TransactionType.PASSIVE_INCOME,
                reference_type="ROUND",
                reference_id=str(round_number),
                description=f"Passive income for round {round_number}",
            )
            transactions.append(tx)

        return transactions
