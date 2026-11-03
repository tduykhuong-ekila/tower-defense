from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.matches.action_policy import validation_payload
from apps.matches.models import Match
from apps.questions.models import TeamQuestion
from apps.questions.views import resolve_team_for_request
from apps.rewards.serializers import ClaimRewardSerializer, RewardClaimSerializer
from apps.rewards.services import RewardService
from apps.teams.models import MemberRole


class MatchRewardClaimView(APIView):
    """
    POST /api/v1/matches/{match_id}/rewards/claim/
    Claim reward (Coins or Unlock) for a correctly answered question (§6.5, §20).
    """

    def post(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        team, member, err = resolve_team_for_request(request, match)
        if err:
            return err

        # Spectators cannot claim rewards
        if member and member.role == MemberRole.SPECTATOR:
            return Response(
                {"error": "Spectators cannot claim rewards."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ClaimRewardSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            claim = RewardService.claim_reward(
                match=match,
                team=team,
                team_question_id=data["team_question_id"],
                reward_type=data["reward_type"],
                unit_type_id=data.get("unit_type_id"),
                idempotency_key=data.get("idempotency_key"),
                member=member,
            )
        except ValidationError as e:
            return Response(validation_payload(e), status=status.HTTP_400_BAD_REQUEST)

        return Response(
            RewardClaimSerializer(claim, context={"team": team}).data,
            status=status.HTTP_200_OK,
        )


class MatchRewardOptionsView(APIView):
    """
    GET /api/v1/matches/{match_id}/rewards/options/{team_question_id}/
    Query reward options for a team question in PENDING_REWARD state (§6.4).
    """

    def get(self, request, match_id, team_question_id):
        match = get_object_or_404(Match, pk=match_id)
        team, member, err = resolve_team_for_request(request, match)
        if err:
            return err

        tq = get_object_or_404(TeamQuestion, pk=team_question_id, match=match)
        if tq.team_id != team.id:
            return Response(
                {"error": "Cannot view reward options for another team's question."},
                status=status.HTTP_403_FORBIDDEN,
            )

        options = RewardService.get_reward_options(tq)
        return Response(options)
