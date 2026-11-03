from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.matches.models import Match, MatchEvent, MatchStatus
from apps.matches.permissions import (
    get_authenticated_member,
    is_host_of_match,
)
from apps.matches.serializers import (
    AssignMemberRequestSerializer,
    CreateMatchRequestSerializer,
    CreateTeamRequestSerializer,
    JoinMatchRequestSerializer,
    MatchDetailSerializer,
    TeamDetailSerializer,
    TeamMemberSummarySerializer,
    UpdateTeamRequestSerializer,
)
from apps.matches.services import MatchService
from apps.teams.models import MemberRole, Team, TeamMember


class MatchConstraintsView(APIView):
    def get(self, request):
        from apps.matches.defaults import (
            DEFAULT_MAX_TEAMS,
            MAX_TEAMS,
            MIN_MEMBERS_PER_TEAM,
            MIN_TEAMS_TO_START,
        )

        return Response({
            "min_teams_to_start": MIN_TEAMS_TO_START,
            "max_teams": MAX_TEAMS,
            "default_max_teams": DEFAULT_MAX_TEAMS,
            "min_members_per_team": MIN_MEMBERS_PER_TEAM,
        })


class MatchListCreateView(APIView):
    """
    POST /api/v1/matches/ - Create a new match.
    GET /api/v1/matches/ - List recent active matches.
    """

    def post(self, request):
        serializer = CreateMatchRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        name = serializer.validated_data.get("name", "Battle Arena")
        config = serializer.validated_data.get("configuration")
        created_by = request.user if request.user and request.user.is_authenticated else None

        try:
            data = serializer.validated_data
            if data.get("question_bank_id"):
                from apps.questions.banks import create_match_with_bank

                match, host_token = create_match_with_bank(bank_id=data["question_bank_id"],
                    token=data["question_bank_token"], name=name, configuration=config, created_by=created_by)
            else:
                match, host_token = MatchService.create_match(name=name, configuration=config,
                    created_by=created_by, creation_token=data.get("creation_token"))
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except IntegrityError:
            from apps.matches.services import hash_token

            token = data.get("creation_token")
            match = Match.objects.filter(creation_token_hash=hash_token(token)).first() if token else None
            if match is None:
                raise
            host_token = MatchService.creation_host_token(token)

        response_data = MatchDetailSerializer(match).data
        response_data["host_token"] = host_token
        return Response(response_data, status=status.HTTP_201_CREATED)

    def get(self, request):
        matches = Match.objects.prefetch_related("teams__members", "members").filter(
            status__in=[MatchStatus.LOBBY, MatchStatus.ACTIVE, MatchStatus.PAUSED]
        ).order_by("-created_at")[:20]
        return Response(MatchDetailSerializer(matches, many=True).data)


class MatchDetailView(APIView):
    """
    GET /api/v1/matches/{id}/ - Retrieve match metadata (sensitive tokens omitted).
    """

    def get(self, request, match_id):
        match = get_object_or_404(Match.objects.prefetch_related("teams__members", "members"), pk=match_id)
        return Response(MatchDetailSerializer(match).data)


class MatchByCodeView(APIView):
    """
    GET /api/v1/matches/code/{room_code}/ - Lookup match by room code.
    """

    def get(self, request, room_code):
        match = get_object_or_404(
            Match,
            room_code=room_code.upper().strip(),
            status__in=[MatchStatus.LOBBY, MatchStatus.ACTIVE, MatchStatus.PAUSED],
        )
        return Response(MatchDetailSerializer(match).data)


class MatchJoinView(APIView):
    """
    POST /api/v1/matches/{id}/join/ - Join match with display name and optional team.
    Returns participant token and member summary.
    """

    def post(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        serializer = JoinMatchRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if serializer.validated_data.get("new_team_name") and get_authenticated_member(request, match):
            return Response(
                {"error": "Bạn đã tham gia phòng. Người chơi chỉ được tạo đội ở bước tham gia ban đầu."},
                status=status.HTTP_403_FORBIDDEN,
            )

        room_code = serializer.validated_data.get("room_code")
        if room_code and room_code.upper().strip() != match.room_code:
            return Response(
                {"error": "Room code does not match this match."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        display_name = serializer.validated_data["display_name"]
        team_id = serializer.validated_data.get("team_id")
        role = serializer.validated_data.get("role", MemberRole.MENTEE)
        user = request.user if request.user and request.user.is_authenticated else None

        try:
            member, participant_token = MatchService.join_match(
                match=match,
                display_name=display_name,
                team_id=team_id,
                role=role,
                user=user,
                new_team_name=serializer.validated_data.get("new_team_name"),
            )
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "member": TeamMemberSummarySerializer(member).data,
                "participant_token": participant_token,
                "match": MatchDetailSerializer(match).data,
            },
            status=status.HTTP_201_CREATED,
        )


class MatchStartView(APIView):
    """
    POST /api/v1/matches/{id}/start/ - Start match (Host only).
    """

    def post(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        if not is_host_of_match(request, match):
            return Response(
                {"error": "Only the Match Host can start the match."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            started_match = MatchService.start_match(match)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(MatchDetailSerializer(started_match).data)


class MatchPauseView(APIView):
    """
    POST /api/v1/matches/{id}/pause/ - Pause match (Host only).
    """

    def post(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        if not is_host_of_match(request, match):
            return Response(
                {"error": "Only the Match Host can pause the match."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            paused = MatchService.pause_match(match)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(MatchDetailSerializer(paused).data)


class MatchResumeView(APIView):
    """
    POST /api/v1/matches/{id}/resume/ - Resume match (Host only).
    """

    def post(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        if not is_host_of_match(request, match):
            return Response(
                {"error": "Only the Match Host can resume the match."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            resumed = MatchService.resume_match(match)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(MatchDetailSerializer(resumed).data)


class MatchEndView(APIView):
    """
    POST /api/v1/matches/{id}/end/ - End match (Host only).
    """

    def post(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        if not is_host_of_match(request, match):
            return Response(
                {"error": "Only the Match Host can end the match."},
                status=status.HTTP_403_FORBIDDEN,
            )

        ended = MatchService.end_match(match)
        return Response(MatchDetailSerializer(ended).data)


class MatchAdvancePhaseView(APIView):
    """
    POST /api/v1/matches/{id}/advance-phase/ - Advance phase along state machine or override (Host only).
    """

    def post(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        if not is_host_of_match(request, match):
            return Response(
                {"error": "Only the Match Host can advance match phases."},
                status=status.HTTP_403_FORBIDDEN,
            )

        target_phase = request.data.get("target_phase")
        is_override = bool(request.data.get("is_override", False))
        reason = request.data.get("reason", "")
        try:
            advanced = MatchService.advance_phase(
                match,
                target_phase=target_phase,
                is_override=is_override,
                reason=reason,
            )
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(MatchDetailSerializer(advanced).data)


class MatchLockView(APIView):
    """
    POST /api/v1/matches/{id}/lock/ - Toggle locked status for joining (Host only).
    """

    def post(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        if not is_host_of_match(request, match):
            return Response(
                {"error": "Only the Match Host can toggle match lock."},
                status=status.HTTP_403_FORBIDDEN,
            )

        is_locked = request.data.get("is_locked", not match.is_locked)
        locked_match = MatchService.set_locked(match, is_locked)
        return Response(MatchDetailSerializer(locked_match).data)


class MatchConfigUpdateView(APIView):
    """
    PATCH /api/v1/matches/{id}/config/ - Update configuration during LOBBY (Host only).
    """

    def patch(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        if not is_host_of_match(request, match):
            return Response(
                {"error": "Only the Match Host can update configuration."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if match.status != MatchStatus.LOBBY:
            return Response(
                {"error": "Configuration can only be updated while match is in LOBBY."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            updated = MatchService.update_configuration(match, request.data)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(MatchDetailSerializer(updated).data)


# -------------------------------------------------------------
# Lobby Administration Endpoints (Teams & Members)
# -------------------------------------------------------------


class MatchTeamListCreateView(APIView):
    """
    POST /api/v1/matches/{id}/teams/ - Create team (Host only, LOBBY only).
    """

    def post(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        if not is_host_of_match(request, match):
            return Response(
                {"error": "Chỉ host có thể tạo đội trong phòng chờ. Người chơi chỉ được tạo đội khi tham gia."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CreateTeamRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            team = MatchService.create_team(match, serializer.validated_data["name"])
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(TeamDetailSerializer(team).data, status=status.HTTP_201_CREATED)


class MatchTeamDetailView(APIView):
    """
    PATCH /api/v1/matches/{id}/teams/{team_id}/ - Update team name (Host only, LOBBY only).
    DELETE /api/v1/matches/{id}/teams/{team_id}/ - Delete team (Host only, LOBBY only).
    """

    def patch(self, request, match_id, team_id):
        match = get_object_or_404(Match, pk=match_id)
        if not is_host_of_match(request, match):
            return Response(
                {"error": "Only the Match Host can edit teams."},
                status=status.HTTP_403_FORBIDDEN,
            )

        team = get_object_or_404(Team, pk=team_id, match=match)
        serializer = UpdateTeamRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            updated_team = MatchService.update_team(team, serializer.validated_data["name"])
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(TeamDetailSerializer(updated_team).data)

    def delete(self, request, match_id, team_id):
        match = get_object_or_404(Match, pk=match_id)
        if not is_host_of_match(request, match):
            return Response(
                {"error": "Only the Match Host can delete teams."},
                status=status.HTTP_403_FORBIDDEN,
            )

        team = get_object_or_404(Team, pk=team_id, match=match)
        try:
            MatchService.delete_team(team)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"message": "Team deleted successfully."}, status=status.HTTP_200_OK)


class MatchTeamReadyView(APIView):
    """
    POST /api/v1/matches/{id}/teams/{team_id}/ready/ - Toggle ready status for a team.
    Allowed for Host or member of this team.
    """

    def post(self, request, match_id, team_id):
        match = get_object_or_404(Match, pk=match_id)
        team = get_object_or_404(Team, pk=team_id, match=match)

        is_host = is_host_of_match(request, match)
        member = get_authenticated_member(request, match)

        if not is_host and (not member or member.team_id != team.id):
            return Response(
                {"error": "Only team members or Host can change team readiness."},
                status=status.HTTP_403_FORBIDDEN,
            )

        new_ready = request.data.get("is_ready", not team.is_ready)
        try:
            updated_team = MatchService.set_team_ready(team, bool(new_ready))
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(TeamDetailSerializer(updated_team).data)


class MatchMemberAssignView(APIView):
    """
    POST /api/v1/matches/{id}/members/{member_id}/assign/ - Assign member to team or change role.
    Allowed for Host, or the member themselves during LOBBY.
    """

    def post(self, request, match_id, member_id):
        match = get_object_or_404(Match, pk=match_id)
        member = get_object_or_404(TeamMember, pk=member_id, match=match)

        is_host = is_host_of_match(request, match)
        auth_member = get_authenticated_member(request, match)

        if not is_host and (not auth_member or auth_member.id != member.id):
            return Response(
                {"error": "Not authorized to modify this member."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = AssignMemberRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        team_id = serializer.validated_data.get("team_id")
        role = serializer.validated_data.get("role")

        if not is_host and (
            auth_member.role not in (MemberRole.MENTEE, MemberRole.MENTOR)
            or role not in (None, MemberRole.MENTEE, MemberRole.MENTOR)
        ):
            return Response({"error": "Chỉ mentee/mentor có thể tự chọn đội và vai trò chơi."},
                            status=status.HTTP_403_FORBIDDEN)

        is_override = is_host and bool(request.data.get("is_override", False))
        reason = request.data.get("reason", "")

        try:
            updated_member = MatchService.assign_member(
                member,
                team_id=team_id,
                role=role,
                is_override=is_override,
                reason=reason,
            )
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(TeamMemberSummarySerializer(updated_member).data)


class MatchMemberDetailView(APIView):
    """
    DELETE /api/v1/matches/{id}/members/{member_id}/ - Remove/kick participant (Host only).
    """

    def delete(self, request, match_id, member_id):
        match = get_object_or_404(Match, pk=match_id)
        if not is_host_of_match(request, match):
            return Response(
                {"error": "Only the Match Host can remove participants."},
                status=status.HTTP_403_FORBIDDEN,
            )

        member = get_object_or_404(TeamMember, pk=member_id, match=match)
        is_override = (
            request.query_params.get("is_override", "").lower() in ("true", "1")
            or bool(request.data.get("is_override", False)) if hasattr(request, "data") else False
        )
        reason = request.query_params.get("reason") or (
            request.data.get("reason", "") if hasattr(request, "data") else ""
        )
        try:
            MatchService.remove_member(member, is_override=is_override, reason=reason)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"message": "Member removed successfully."}, status=status.HTTP_200_OK)


class MatchEventsListView(APIView):
    """
    GET /api/v1/matches/{id}/events/?event_type=...&after_sequence=N&until_sequence=M&limit=100&order=asc|desc
    Filtered and paginated event retrieval (§2.2, §2.4, §25, FR-09).
    Host can inspect full combat logs and audit trails.
    """

    def get(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        is_host = is_host_of_match(request, match)
        auth_member = get_authenticated_member(request, match)

        if not is_host and not auth_member:
            return Response(
                {"error": "You must be a valid participant or host of this match."},
                status=status.HTTP_403_FORBIDDEN,
            )

        qs = MatchEvent.objects.filter(match=match)

        # Sequence filtering
        after_seq = request.query_params.get("after_sequence")
        if after_seq is not None:
            try:
                qs = qs.filter(sequence_number__gt=int(after_seq))
            except (ValueError, TypeError):
                pass

        until_seq = request.query_params.get("until_sequence")
        if until_seq is not None:
            try:
                qs = qs.filter(sequence_number__lte=int(until_seq))
            except (ValueError, TypeError):
                pass

        # Event type filtering (comma-separated list supported)
        event_types_param = request.query_params.get("event_type")
        if event_types_param:
            types_list = [t.strip() for t in event_types_param.split(",") if t.strip()]
            if types_list:
                qs = qs.filter(event_type__in=types_list)

        # Ordering
        order_param = request.query_params.get("order", "asc").lower()
        if order_param == "desc":
            qs = qs.order_by("-sequence_number")
        else:
            qs = qs.order_by("sequence_number")

        # Pagination
        try:
            limit = min(500, max(1, int(request.query_params.get("limit", 100))))
        except (ValueError, TypeError):
            limit = 100

        try:
            offset = max(0, int(request.query_params.get("offset", 0)))
        except (ValueError, TypeError):
            offset = 0

        total_count = qs.count()
        events_slice = qs[offset : offset + limit]

        from apps.realtime.events import format_event_envelope
        from apps.realtime.services import PRIVATE_EVENT_TYPES

        viewer_team_id = (
            str(auth_member.team_id) if (auth_member and auth_member.team_id) else None
        )

        events_data = []
        for ev in events_slice:
            payload = ev.payload or {}
            event_team_id = payload.get("team_id")

            # Check privacy for non-hosts
            if ev.event_type in PRIVATE_EVENT_TYPES and event_team_id:
                if not is_host and event_team_id != viewer_team_id:
                    continue

            events_data.append(
                format_event_envelope(
                    match_id=match.id,
                    event_type=ev.event_type,
                    sequence_number=ev.sequence_number,
                    payload=payload,
                    event_id=ev.id,
                    server_timestamp=ev.created_at,
                )
            )

        return Response({
            "events": events_data,
            "count": len(events_data),
            "total": total_count,
            "limit": limit,
            "offset": offset,
        })


class MatchOverrideCloseQuestionView(APIView):
    """
    POST /api/v1/matches/{id}/override/close-question/
    Administrative override to close a stuck question (§11, §26).
    """

    def post(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        if not is_host_of_match(request, match):
            return Response(
                {"error": "Only the Match Host can perform administrative overrides."},
                status=status.HTTP_403_FORBIDDEN,
            )

        team_question_id = request.data.get("team_question_id")
        reason = request.data.get("reason", "")
        if not team_question_id:
            return Response(
                {"error": "team_question_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            MatchService.override_close_stuck_question(match, team_question_id, reason=reason)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"message": "Question closed successfully via override."})


class MatchOverrideAdjustCoinsView(APIView):
    """
    POST /api/v1/matches/{id}/override/adjust-coins/
    Administrative override to adjust coin balance / undo faulty rewards (§7, §26).
    """

    def post(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        if not is_host_of_match(request, match):
            return Response(
                {"error": "Only the Match Host can perform administrative overrides."},
                status=status.HTTP_403_FORBIDDEN,
            )

        team_id = request.data.get("team_id")
        amount = request.data.get("amount")
        reason = request.data.get("reason", "")
        if not team_id or amount is None:
            return Response(
                {"error": "team_id and amount are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            tx = MatchService.override_adjust_coins(
                match, team_id=team_id, amount=int(amount), reason=reason
            )
        except (ValidationError, ValueError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "message": "Coins adjusted successfully.",
            "team_id": str(team_id),
            "amount": tx.amount,
            "balance_after": tx.balance_after,
        })


class MatchHostTelemetryView(APIView):
    """
    GET /api/v1/matches/{id}/host-telemetry/
    Comprehensive monitoring telemetry for Host Dashboard (§14.8, §2.2).
    """

    def get(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        if not is_host_of_match(request, match):
            return Response(
                {"error": "Only the Match Host can access host telemetry."},
                status=status.HTTP_403_FORBIDDEN,
            )

        telemetry = MatchService.get_host_telemetry(match)
        return Response(telemetry)


class MatchPresetsView(APIView):
    """
    GET /api/v1/matches/presets/
    List pre-configured match presets (Standard 30m, Quick 15m, Blitz 10m) (§2.3).
    """

    def get(self, request):
        from apps.matches.defaults import MATCH_PRESETS

        return Response(list(MATCH_PRESETS.values()))


class MatchApplyPresetView(APIView):
    """
    POST /api/v1/matches/{id}/apply-preset/
    Apply a configuration preset to match during LOBBY (Host only) (§2.3).
    """

    def post(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        if not is_host_of_match(request, match):
            return Response(
                {"error": "Only the Match Host can apply presets."},
                status=status.HTTP_403_FORBIDDEN,
            )

        preset_id = request.data.get("preset_id")
        if not preset_id:
            return Response(
                {"error": "preset_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            updated = MatchService.apply_preset(match, preset_id)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(MatchDetailSerializer(updated).data)


class MatchBalancePreviewView(APIView):
    """
    POST /api/v1/matches/{id}/config/preview/
    Preview game balance metrics and projected coin income for tuning (§7.4, FR-09).
    """

    def post(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        from apps.matches.defaults import calculate_balance_preview

        config_candidate = request.data.get("configuration") or request.data or match.configuration
        preview = calculate_balance_preview(config_candidate)
        return Response(preview)


class MatchRematchView(APIView):
    """
    POST /api/v1/matches/{id}/rematch/
    Create a new match retaining teams, members, and configuration (§14.9, FR-10).
    """

    def post(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        if not is_host_of_match(request, match):
            return Response(
                {"error": "Only the Match Host can create a rematch."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            new_match, host_token = MatchService.create_rematch(match)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "new_match_id": str(new_match.id),
            "new_room_code": new_match.room_code,
            "host_token": host_token,
            "match": MatchDetailSerializer(new_match).data,
        }, status=status.HTTP_201_CREATED)



class MatchSnapshotView(APIView):
    """One transaction-consistent recovery envelope, scoped exactly like WebSocket."""

    def get(self, request, match_id):
        from apps.realtime.services import RealtimeService

        match = get_object_or_404(Match, pk=match_id)
        member = get_authenticated_member(request, match)
        return Response(RealtimeService.build_snapshot(
            match, viewer_team_id=str(member.team_id) if member and member.team_id else None,
            is_host=is_host_of_match(request, match),
        ))
