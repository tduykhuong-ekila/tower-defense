import re
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser

from apps.matches.models import Match
from apps.matches.services import hash_token
from apps.teams.models import MemberRole, TeamMember


@database_sync_to_async
def authenticate_connection(match_id: str, token: str, user=None):
    """
    Authenticate WebSocket connection using participant token, host token, or user session.
    """
    try:
        match = Match.objects.filter(id=match_id).first()
        if not match:
            return {
                "authenticated": False,
                "error": "Match does not exist.",
            }

        # 1. Check Django authenticated user as host
        if user and user.is_authenticated and match.created_by_id == user.id:
            return {
                "authenticated": True,
                "is_host": True,
                "is_spectator": False,
                "team_member": None,
                "team_id": None,
                "role": MemberRole.HOST,
                "match": match,
            }

        if not token:
            return {
                "authenticated": False,
                "error": "Authentication token required.",
            }

        token_hash = hash_token(token)

        # 2. Check Host token
        if match.host_token_hash == token_hash:
            return {
                "authenticated": True,
                "is_host": True,
                "is_spectator": False,
                "team_member": None,
                "team_id": None,
                "role": MemberRole.HOST,
                "match": match,
            }

        # 3. Check Participant token (TeamMember)
        member = (
            TeamMember.objects.filter(match=match, token_hash=token_hash)
            .select_related("team")
            .first()
        )
        if member:
            return {
                "authenticated": True,
                "is_host": False,
                "is_spectator": member.role == MemberRole.SPECTATOR,
                "team_member": member,
                "team_id": str(member.team_id) if member.team_id else None,
                "role": member.role,
                "match": match,
            }

        return {
            "authenticated": False,
            "error": "Invalid host or participant token.",
        }
    except Exception as exc:
        return {
            "authenticated": False,
            "error": str(exc),
        }


class TokenAuthMiddleware:
    """
    ASGI Middleware to authenticate WebSocket connections for matches.
    Extracts token from query string or headers.
    """

    MATCH_PATH_REGEX = re.compile(
        r"^/ws/matches/(?P<match_id>[0-9a-fA-F-]+)/?$"
    )

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            path = scope.get("path", "")
            match = self.MATCH_PATH_REGEX.match(path)

            token = None
            # 1. Try query string: ?token=... or ?host_token=... or ?participant_token=...
            query_string = scope.get("query_string", b"").decode("utf-8")
            if query_string:
                qs = parse_qs(query_string)
                for key in ["token", "participant_token", "host_token"]:
                    if key in qs and qs[key]:
                        token = qs[key][0].strip()
                        break

            # 2. Try headers if not found in query string
            if not token:
                headers = dict(scope.get("headers", []))
                for header_key in [b"x-host-token", b"x-participant-token"]:
                    if header_key in headers:
                        token = headers[header_key].decode("utf-8").strip()
                        break

                if not token and b"authorization" in headers:
                    auth_val = headers[b"authorization"].decode("utf-8").strip()
                    if auth_val.startswith("Bearer ") or auth_val.startswith("Token "):
                        token = auth_val.split(" ", 1)[1].strip()

            user = scope.get("user", AnonymousUser())

            if match:
                match_id = match.group("match_id")
                auth_result = await authenticate_connection(match_id, token, user)
                scope["auth"] = auth_result
                scope["authenticated"] = auth_result.get("authenticated", False)
                scope["is_host"] = auth_result.get("is_host", False)
                scope["is_spectator"] = auth_result.get("is_spectator", False)
                scope["team_member"] = auth_result.get("team_member")
                scope["team_id"] = auth_result.get("team_id")
                scope["role"] = auth_result.get("role")
                scope["match_instance"] = auth_result.get("match")
            else:
                scope["authenticated"] = False
                scope["auth"] = {"authenticated": False, "error": "Invalid match route"}

        return await self.inner(scope, receive, send)


def TokenAuthMiddlewareStack(inner):
    return TokenAuthMiddleware(inner)
