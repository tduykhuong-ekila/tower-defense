import time
import uuid
from typing import Any, Dict, List, Optional

from django.core.exceptions import ValidationError
from django.db import OperationalError, connection, transaction
from django.db.models import Q

from apps.economy.models import TransactionType
from apps.economy.services import EconomyService
from apps.matches.action_policy import ActionPolicy
from apps.matches.models import Match
from apps.matches.services import MatchService
from apps.questions.models import QuestionStatus, TeamQuestion
from apps.questions.state_machine import transition_team_question
from apps.rewards.coin_rewards import public_coin_distribution
from apps.rewards.models import RewardClaim, RewardClaimStatus, RewardType
from apps.teams.models import Team
from apps.units.models import TeamUnlock, UnitType


class RewardService:
    @classmethod
    def get_eligible_units_for_team(cls, team: Team) -> List[UnitType]:
        """
        Return list of UnitType eligible for unlocking by the team (§6.3):
        - is_unlockable == True
        - is_starter == False
        - is_active == True
        - Not already unlocked by this team
        - Prerequisites met
        """
        unlocked_unit_ids = set(
            TeamUnlock.objects.filter(team=team).values_list("unit_type_id", flat=True)
        )
        unlocked_codes = set(
            UnitType.objects.filter(id__in=unlocked_unit_ids).values_list("code", flat=True)
        )

        candidates = UnitType.objects.filter(
            is_active=True,
            is_unlockable=True,
            is_starter=False,
        ).exclude(id__in=unlocked_unit_ids)

        eligible = []
        for unit in candidates:
            prereqs = unit.prerequisites or []
            # All prerequisite codes must be unlocked
            if all(p in unlocked_codes for p in prereqs):
                eligible.append(unit)

        return eligible

    @classmethod
    def get_reward_options(cls, team_question: TeamQuestion) -> Dict[str, Any]:
        """
        Build reward options payload for a question in PENDING_REWARD state (§6.4, §14.6).
        """
        team = team_question.team

        is_random = getattr(team_question, "reward_coin_random", False)
        # Never leak a sealed bag's draw through REST or WebSocket snapshots.
        coin_amount = None if is_random else team_question.reward_coin_amount
        eligible_units = cls.get_eligible_units_for_team(team)
        unlock_available = len(eligible_units) > 0

        # Reuse the catalog's effective stats so reward previews match deployment.
        from apps.units.serializers import UnitTypeSerializer

        unit_list = UnitTypeSerializer(
            eligible_units, many=True, context={"team": team, "match": team.match}
        ).data

        return {
            "team_question_id": str(team_question.id),
            "coin_amount": coin_amount,
            "coin_distribution": public_coin_distribution() if is_random else [],
            "unlock_available": unlock_available,
            "message": (
                ""
                if unlock_available
                else "All units unlocked. Receive coins to continue strengthening your base."
            ),
            "eligible_units": unit_list,
        }

    @classmethod
    def claim_reward(cls, *args, **kwargs) -> RewardClaim:
        # SQLite does not implement SELECT FOR UPDATE. Two deferred read transactions
        # can both fail when upgraded to writes. Retry the entire rolled-back claim,
        # preserving the unique question claim and idempotency checks on each attempt.
        for attempt in range(6):
            try:
                return cls._claim_reward_atomic(*args, **kwargs)
            except OperationalError as exc:
                if connection.vendor != "sqlite" or "locked" not in str(exc).lower() or attempt == 5:
                    raise
                time.sleep(0.015 * (attempt + 1))
        raise RuntimeError("Reward transaction retry exhausted")

    @classmethod
    @transaction.atomic
    def _claim_reward_atomic(
        cls,
        match: Match,
        team: Team,
        team_question_id: str,
        reward_type: str,
        unit_type_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        member=None,
    ) -> RewardClaim:
        """
        Atomically and idempotently claim a reward for a correctly answered question (§6.5).
        Enforces:
        - Unique claim per team_question (cannot double-claim).
        - Idempotency key reuse returns previous claim without duplicate payout.
        - Eliminated teams may claim quiz rewards while the match is active.
        - Question must belong to the caller's team.
        - Server strictly calculates coin amount; client amounts are ignored.
        - Unlock eligibility strictly verified (§6.3).
        """
        # 1. Idempotency check via idempotency_key
        if idempotency_key:
            existing_by_key = RewardClaim.objects.filter(
                idempotency_key=idempotency_key
            ).first()
            if existing_by_key:
                if existing_by_key.team_id != team.pk or str(existing_by_key.team_question_id) != str(team_question_id):
                    raise ValidationError("Idempotency key belongs to another team or question.")
                return existing_by_key

        match_locked = Match.objects.select_for_update().get(pk=match.pk)
        team_locked = Team.objects.select_for_update().get(pk=team.pk)

        try:
            tq = (
                TeamQuestion.objects.select_for_update()
                .select_related("match", "team")
                .get(pk=team_question_id, match=match_locked)
            )
        except TeamQuestion.DoesNotExist:
            raise ValidationError("Team question does not exist.")

        if tq.team_id != team_locked.id:
            raise ValidationError("Cannot claim rewards for another team's question.")

        # 2. Check if reward has already been claimed for this team_question
        existing_claim = RewardClaim.objects.filter(team_question=tq).first()
        if existing_claim:
            return existing_claim

        ActionPolicy.require_context(match_locked, team_locked, "CLAIM_REWARD", member)

        if tq.status != QuestionStatus.PENDING_REWARD:
            raise ValidationError(
                f"Question is not in PENDING_REWARD state (current: {tq.status})."
            )

        reward_type = str(reward_type).upper().strip()

        if reward_type == RewardType.COIN:
            # Server authoritative coin amount (§6.1, §20) via EconomyService (§2.3)
            coin_amount = tq.reward_coin_amount
            EconomyService.credit(
                team=team_locked,
                amount=coin_amount,
                transaction_type=TransactionType.REWARD_COIN,
                reference_type="QUESTION_REWARD",
                reference_id=str(tq.id),
                description=f"Reward choice: Coins for Question #{tq.sequence_number}",
            )
            # Reload updated coins
            team_locked.refresh_from_db(fields=["coins"])

            claim = RewardClaim.objects.create(
                team_question=tq,
                team=team_locked,
                reward_type=RewardType.COIN,
                coin_amount=coin_amount,
                unlocked_unit_type=None,
                status=RewardClaimStatus.CLAIMED,
                idempotency_key=idempotency_key,
            )

            transition_team_question(tq, QuestionStatus.REWARD_CLAIMED, save=True)

            MatchService.record_match_event(
                match=match_locked,
                event_type="REWARD_CLAIMED",
                payload={
                    "team_id": str(team_locked.id),
                    "team_question_id": str(tq.id),
                    "reward_type": RewardType.COIN,
                    "coin_amount": coin_amount,
                    "balance_after": team_locked.coins,
                    "claim_id": str(claim.id),
                },
            )
            return claim

        elif reward_type == RewardType.UNLOCK:
            if not unit_type_id:
                raise ValidationError("unit_type_id is required for UNLOCK reward.")

            # Search unit by UUID or code
            unit_query = Q(code=str(unit_type_id).strip())
            try:
                val_uuid = uuid.UUID(str(unit_type_id).strip())
                unit_query |= Q(id=val_uuid)
            except (ValueError, AttributeError):
                pass

            try:
                target_unit = UnitType.objects.get(unit_query)
            except UnitType.DoesNotExist:
                raise ValidationError(f"Unit '{unit_type_id}' does not exist.")

            # Verify unlock eligibility (§6.3)
            eligible_units = cls.get_eligible_units_for_team(team_locked)
            if target_unit.id not in [u.id for u in eligible_units]:
                raise ValidationError(
                    f"Unit '{target_unit.name}' is not eligible for unlocking (already unlocked, starter, or unmet prerequisites)."
                )

            # Create unlock record
            TeamUnlock.objects.create(
                team=team_locked,
                unit_type=target_unit,
                source_team_question=tq,
            )

            claim = RewardClaim.objects.create(
                team_question=tq,
                team=team_locked,
                reward_type=RewardType.UNLOCK,
                unlocked_unit_type=target_unit,
                coin_amount=0,
                status=RewardClaimStatus.CLAIMED,
                idempotency_key=idempotency_key,
            )

            transition_team_question(tq, QuestionStatus.REWARD_CLAIMED, save=True)

            MatchService.record_match_event(
                match=match_locked,
                event_type="REWARD_CLAIMED",
                payload={
                    "team_id": str(team_locked.id),
                    "team_question_id": str(tq.id),
                    "reward_type": RewardType.UNLOCK,
                    "unlocked_unit_code": target_unit.code,
                    "unlocked_unit_name": target_unit.name,
                    "claim_id": str(claim.id),
                },
            )
            return claim

        else:
            raise ValidationError(
                f"Invalid reward_type '{reward_type}'. Must be COIN or UNLOCK."
            )
