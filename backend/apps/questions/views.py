from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.matches.action_policy import validation_payload
from apps.matches.models import Match
from apps.matches.permissions import get_authenticated_member, is_host_of_match
from apps.questions.models import Question, TeamQuestion
from apps.questions.serializers import (
    AnswerSubmissionSerializer,
    QuestionAdminSerializer,
    TeamQuestionSerializer,
)
from apps.questions.services import QuestionService
from apps.teams.models import MemberRole


def resolve_team_for_request(request, match: Match):
    """
    Resolve the Team for an authenticated participant or host.
    Returns (team, member, error_response).
    """
    is_host = is_host_of_match(request, match)
    member = get_authenticated_member(request, match)

    if not is_host and not member:
        return (
            None,
            None,
            Response(
                {"error": "Valid participant or host authentication is required."},
                status=status.HTTP_401_UNAUTHORIZED,
            ),
        )

    team = None
    if member:
        team = member.team
    elif is_host:
        team_id = request.query_params.get("team_id") or request.data.get("team_id")
        if team_id:
            team = match.teams.filter(pk=team_id).first()
        else:
            team = match.teams.first()

    if not team:
        return (
            None,
            member,
            Response(
                {"error": "Participant is not assigned to a team."},
                status=status.HTTP_400_BAD_REQUEST,
            ),
        )

    return team, member, None


class MatchCurrentQuestionView(APIView):
    """
    GET /api/v1/matches/{match_id}/questions/current/
    Fetch or assign the team's current question (§5.1, §20).
    """

    def get(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        team, member, err = resolve_team_for_request(request, match)
        if err:
            return err

        if member and member.role == MemberRole.SPECTATOR:
            return Response({"error": "Spectators cannot request team questions."}, status=403)

        try:
            tq = QuestionService.get_or_assign_current_question(match, team)
        except ValidationError as e:
            return Response(validation_payload(e), status=status.HTTP_400_BAD_REQUEST)

        if not tq:
            return Response(
                {
                    "question": None,
                    "message": "No active question available for this team at this time.",
                },
                status=status.HTTP_200_OK,
            )

        return Response(TeamQuestionSerializer(tq).data)

    def post(self, request, match_id):
        import uuid
        match = get_object_or_404(Match, pk=match_id)
        team, member, err = resolve_team_for_request(request, match)
        if err:
            return err
        if member and member.role == MemberRole.SPECTATOR:
            return Response({"error": "Spectators cannot open questions."}, status=403)
        action = request.data.get("action")
        try:
            if action == "OPEN_SESSION":
                viewer = str(uuid.UUID(str(request.data.get("viewer_id"))))
                observed = request.data.get("question_id")
                question_id = uuid.UUID(str(observed)) if observed else None
                tq, previous_expired = QuestionService.open_session(match, team, question_id, viewer, member)
                return Response({**(TeamQuestionSerializer(tq).data if tq else {"question": None}),
                                 "previous_question_expired": previous_expired})
            question_id = uuid.UUID(str(request.data.get("question_id")))
            if action == "NEXT":
                from apps.matches.action_policy import ActionPolicy
                ActionPolicy.require_context(match, team, "ANSWER_QUESTION", member)
                tq = QuestionService.get_or_assign_current_question(match, team, advance_from=question_id)
            elif action in {"OPEN", "CLOSE", "HEARTBEAT"}:
                viewer = str(uuid.UUID(str(request.data.get("viewer_id"))))
                tq = QuestionService.update_viewing(match, team, question_id, viewer, action, member)
            else:
                raise ValueError("Unknown question action")
        except (ValueError, ValidationError, TeamQuestion.DoesNotExist) as exc:
            return Response({"error": str(exc)}, status=400)
        return Response(TeamQuestionSerializer(tq).data if tq else {"question": None})


class MatchAnswerQuestionView(APIView):
    """
    POST /api/v1/matches/{match_id}/questions/{question_id}/answer/
    Submit a single final answer for the given team question (§5.3, §20).
    """

    def post(self, request, match_id, question_id):
        match = get_object_or_404(Match, pk=match_id)
        team, member, err = resolve_team_for_request(request, match)
        if err:
            return err

        # Spectators cannot submit answers
        if member and member.role == MemberRole.SPECTATOR:
            return Response(
                {"error": "Spectators cannot submit answers."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = AnswerSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        answer = serializer.validated_data["answer"]

        try:
            tq = QuestionService.submit_answer(
                match=match,
                team=team,
                team_question_id=question_id,
                answer=answer,
                member=member,
            )
        except ValidationError as e:
            return Response(validation_payload(e), status=status.HTTP_400_BAD_REQUEST)

        return Response(TeamQuestionSerializer(tq).data)


class MatchQuestionHistoryView(APIView):
    """
    GET /api/v1/matches/{match_id}/questions/history/
    Audit trail of all assigned questions and answers for this team (§13 FR-03).
    """

    def get(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        team, member, err = resolve_team_for_request(request, match)
        if err:
            return err

        questions = TeamQuestion.objects.filter(
            match=match, team=team
        ).order_by("sequence_number")
        return Response(TeamQuestionSerializer(questions, many=True).data)


class QuestionListCreateView(APIView):
    permission_classes = [IsAdminUser]
    """
    GET /api/v1/questions/ - List question bank (Host/Admin)
    POST /api/v1/questions/ - Create question (Host/Admin)
    """

    def get(self, request):
        qs = Question.objects.all()
        diff = request.query_params.get("difficulty")
        if diff:
            qs = qs.filter(difficulty=diff.upper())
        cat = request.query_params.get("category")
        if cat:
            qs = qs.filter(category__iexact=cat)
        return Response(QuestionAdminSerializer(qs, many=True).data)

    def post(self, request):
        serializer = QuestionAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        q = serializer.save()
        return Response(QuestionAdminSerializer(q).data, status=status.HTTP_201_CREATED)


class QuestionDetailView(APIView):
    permission_classes = [IsAdminUser]
    """
    GET, PUT, PATCH, DELETE /api/v1/questions/{id}/
    Host CRUD on question items.
    """

    def get(self, request, question_id):
        q = get_object_or_404(Question, pk=question_id)
        return Response(QuestionAdminSerializer(q).data)

    def patch(self, request, question_id):
        q = get_object_or_404(Question, pk=question_id)
        if q.question_bank_id:
            return Response({"error": "Imported question banks are immutable."}, status=409)
        serializer = QuestionAdminSerializer(q, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        q = serializer.save()
        return Response(QuestionAdminSerializer(q).data)

    def delete(self, request, question_id):
        q = get_object_or_404(Question, pk=question_id)
        if q.question_bank_id:
            return Response({"error": "Imported question banks are immutable."}, status=409)
        q.delete()
        return Response({"message": "Question deleted successfully."})


class MatchQuestionProgressView(APIView):
    def get(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        team, member, err = resolve_team_for_request(request, match)
        if err:
            return err
        return Response(QuestionService.progress(match, team))
