from typing import Optional

from rest_framework import permissions

from apps.matches.models import Match
from apps.matches.services import hash_token
from apps.teams.models import MemberRole, TeamMember


def extract_token_from_request(
    request, header_name: str, prefix: Optional[str] = None
) -> Optional[str]:
    """Extract a token from headers (dedicated header, Bearer header, or query param)."""
    # 1. Custom dedicated header (e.g. X-Host-Token or X-Participant-Token)
    val = request.headers.get(header_name)
    if val:
        return val.strip()

    # 2. Authorization header: "Bearer <token>" or "Token <token>"
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer ") or auth_header.startswith("Token "):
        token = auth_header.split(" ", 1)[1].strip()
        if prefix:
            if token.startswith(prefix):
                return token
        else:
            return token

    return None


def get_request_host_token(request) -> Optional[str]:
    """Retrieve host token if supplied in request."""
    return extract_token_from_request(request, "X-Host-Token", prefix="ht_")


def get_request_participant_token(request) -> Optional[str]:
    """Retrieve participant token if supplied in request."""
    return extract_token_from_request(request, "X-Participant-Token", prefix="pt_")


def is_host_of_match(request, match: Match) -> bool:
    """Verify if the request represents the host of this match."""
    # Authenticated Django user who created the match
    if request.user and request.user.is_authenticated and match.created_by_id == request.user.id:
        return True

    # Host token validation
    token = get_request_host_token(request)
    if not token:
        # Fallback: check standard Authorization bearer token without ht_ prefix
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer ") or auth_header.startswith("Token "):
            token = auth_header.split(" ", 1)[1].strip()

    if token:
        token_hash = hash_token(token)
        if match.host_token_hash == token_hash:
            return True

    return False


def get_authenticated_member(request, match: Match) -> Optional[TeamMember]:
    """Retrieve the TeamMember corresponding to participant token in this match."""
    token = get_request_participant_token(request)
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer ") or auth_header.startswith("Token "):
            token = auth_header.split(" ", 1)[1].strip()

    if not token:
        return None

    token_hash = hash_token(token)
    return TeamMember.objects.filter(match=match, token_hash=token_hash).first()


class IsMatchHost(permissions.BasePermission):
    """
    Allows access only to the verified match host (via Django user or host_token).
    """

    message = "Only the Match Host is authorized to perform this action."

    def has_object_permission(self, request, view, obj):
        match = obj if isinstance(obj, Match) else getattr(obj, "match", None)
        if not match:
            return False
        return is_host_of_match(request, match)


class IsParticipantOfMatch(permissions.BasePermission):
    """
    Allows access to participants with a valid participant token for this match, or the Host.
    """

    message = "You must be a valid participant of this match."

    def has_object_permission(self, request, view, obj):
        match = obj if isinstance(obj, Match) else getattr(obj, "match", None)
        if not match:
            return False

        if is_host_of_match(request, match):
            return True

        member = get_authenticated_member(request, match)
        if member:
            # Attach to request for convenience in downstream views
            request.team_member = member
            return True

        return False


class IsTeamMember(permissions.BasePermission):
    """
    Allows access if the participant belongs to the team (or host).
    """

    message = "You can only perform actions for your assigned team."

    def has_object_permission(self, request, view, obj):
        # obj is expected to be a Team or have a team attribute
        team = obj if hasattr(obj, "members") else getattr(obj, "team", None)
        match = getattr(team, "match", None) or getattr(obj, "match", None)

        if match and is_host_of_match(request, match):
            return True

        member = getattr(request, "team_member", None)
        if not member and match:
            member = get_authenticated_member(request, match)

        if member and team and member.team_id == team.id:
            return True

        return False


class NotSpectatorForWrite(permissions.BasePermission):
    """
    Blocks write requests from members with the SPECTATOR role.
    """

    message = "Spectators cannot perform state-changing actions."

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True

        match = obj if isinstance(obj, Match) else getattr(obj, "match", None)
        if match and is_host_of_match(request, match):
            return True

        member = getattr(request, "team_member", None)
        if not member and match:
            member = get_authenticated_member(request, match)

        if member and member.role == MemberRole.SPECTATOR:
            return False

        return True
