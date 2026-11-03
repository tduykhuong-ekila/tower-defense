from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.combat.models import MatchResult
from apps.combat.scoring import ScoringService
from apps.combat.serializers import MatchResultSerializer
from apps.combat.services import CombatService
from apps.matches.models import Match, MatchStatus
from apps.matches.permissions import is_host_of_match


class MatchMapView(APIView):
    """Public terrain metadata only; no coins, questions or hidden team state."""

    def get(self, request, match_id):
        from django.shortcuts import get_object_or_404


        match = get_object_or_404(Match, pk=match_id)
        teams = list(match.teams.order_by("created_at", "id"))
        from apps.units.placement import map_for_match
        data = map_for_match(match, [str(team.id) for team in teams])
        return Response(data)


class MatchResultsView(APIView):
    """
    Returns finalized match results and immutable leaderboard snapshot (§19.13, §20).
    GET /api/v1/matches/{id}/results/
    """

    def get(self, request, match_id):
        try:
            match = Match.objects.get(pk=match_id)
        except Match.DoesNotExist:
            return Response({"detail": "Trận đấu không tồn tại."}, status=status.HTTP_404_NOT_FOUND)

        # If match is finished or all but one team eliminated, ensure finalized
        results = MatchResult.objects.filter(match=match).order_by("final_rank")
        if not results.exists() and (match.status == MatchStatus.FINISHED or match.phase == "RESULTS"):
            results = ScoringService.finalize_match(match)
        elif not results.exists():
            # Match still in progress, return preview or empty results
            active_teams_count = match.teams.filter(status="ACTIVE").count()
            if active_teams_count <= 1 and match.status == MatchStatus.ACTIVE:
                results = ScoringService.finalize_match(match)

        match.refresh_from_db()
        results = MatchResult.objects.filter(match=match).select_related("team").order_by("final_rank")
        serializer = MatchResultSerializer(results, many=True)
        winners = list(results.filter(final_rank=1))
        winner = winners[0] if len(winners) == 1 else None

        duration_seconds = 0
        if match.started_at:
            end_time = match.ended_at or timezone.now()
            duration_seconds = max(0, int((end_time - match.started_at).total_seconds()))

        awards = (match.configuration or {}).get("awards", [])
        if not awards and results.exists():
            from apps.combat.scoring import calculate_match_awards
            results_data = [
                {
                    "team_id": r.team_id,
                    "team_name": r.team.name,
                    "final_rank": r.final_rank,
                    "total_score": r.final_score,
                    "bases_destroyed": r.bases_destroyed,
                    "base_damage_dealt": r.base_damage_dealt,
                    "correct_answers": r.correct_answers,
                    "remaining_base_hp": r.remaining_base_hp,
                    "remaining_coins": r.remaining_coins,
                    "surviving_towers": r.surviving_towers,
                    "actions_count": 0,
                }
                for r in results
            ]
            awards = calculate_match_awards(results_data)

        return Response({
            "match_id": str(match.id),
            "room_code": match.room_code,
            "status": match.status,
            "phase": match.phase,
            "winner_team_id": str(winner.team_id) if winner else None,
            "winner_team_ids": [str(result.team_id) for result in winners],
            "winner_team_name": " & ".join(result.team.name for result in winners) or None,
            "duration_seconds": duration_seconds,
            "awards": awards,
            "results": serializer.data,
        })


class MatchCombatResolveView(APIView):
    """
    Trigger manual / scheduler round resolution (§10.1).
    POST /api/v1/matches/{id}/combat/resolve/
    """

    def post(self, request, match_id):
        try:
            match = Match.objects.get(pk=match_id)
        except Match.DoesNotExist:
            return Response({"detail": "Trận đấu không tồn tại."}, status=status.HTTP_404_NOT_FOUND)

        if not is_host_of_match(request, match):
            return Response(
                {"detail": "Chỉ Host mới có quyền giải quyết round chiến đấu."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            expected = request.data.get("expected_round", match.configuration.get("current_round", 1))
            if expected is not None and (type(expected) is not int or expected < 1):
                raise ValueError("expected_round must be a positive integer")
            round_result = CombatService.execute_combat_round(match, expected_round=expected)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "match_id": str(match.id),
            "round_number": round_result.round_number,
            "events_count": len(round_result.events),
            "events": round_result.events,
            "eliminated_team_ids": round_result.eliminated_team_ids,
            "winner_team_id": round_result.winner_team_id,
            "is_match_over": round_result.is_match_over,
        }, status=status.HTTP_200_OK)
