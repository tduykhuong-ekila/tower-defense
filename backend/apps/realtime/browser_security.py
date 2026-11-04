import hashlib
import logging
import uuid

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.matches.models import Match
from apps.matches.permissions import (
    get_authenticated_member,
    get_request_host_token,
    get_request_participant_token,
    is_host_of_match,
)
from apps.matches.services import hash_token
from apps.realtime.events import ServerEventType, format_event_envelope
from apps.realtime.models import BrowserSessionBlock

# Size-based reports caused false positives. Reject them from stale clients and
# retain old records for audit without enforcing those unreliable decisions.
INSPECTION_REASONS = {"inspection_shortcut", "devtool_detected"}
logger = logging.getLogger(__name__)


def parse_session_id(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def browser_session_group(match_id, credential_hash, session_id):
    digest = hashlib.sha256(f"{match_id}:{credential_hash}:{session_id}".encode()).hexdigest()
    return f"browser.{digest}"


def blocked_envelope(match_id):
    # Private control message, outside the shared match state sequence.
    return format_event_envelope(match_id, ServerEventType.SESSION_BLOCKED, 0, {
        "error_code": "BROWSER_SESSION_BLOCKED",
        "reason": "Phiên trình duyệt đã bị khóa. Hãy đóng DevTools, tải lại trang và vào lại phòng.",
        "reload_required": True,
    })


def is_browser_session_blocked(match_id, credential_hash, session_id):
    return bool(session_id and credential_hash and BrowserSessionBlock.objects.filter(
        match_id=match_id, credential_hash=credential_hash, session_id=session_id,
        reason__in=INSPECTION_REASONS,
    ).exists())


class BrowserInspectionReportView(APIView):
    def post(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)
        if is_host_of_match(request, match):
            credential_hash = match.host_token_hash
        else:
            member = get_authenticated_member(request, match)
            if not member:
                return Response({"error": "Valid match credentials required."}, status=403)
            credential_hash = member.token_hash

        session_id = parse_session_id(request.headers.get("X-Browser-Session"))
        reason = request.data.get("reason") if isinstance(request.data, dict) else None
        if not session_id or not isinstance(reason, str) or reason not in INSPECTION_REASONS:
            return Response({"error": "Invalid browser session or inspection reason."}, status=400)

        BrowserSessionBlock.objects.update_or_create(
            match=match, credential_hash=credential_hash, session_id=session_id,
            defaults={"reason": reason},
        )
        envelope = blocked_envelope(match.pk)
        # The database decision survives worker restarts and dropped broadcasts.
        # HTTP returns the same control event when the socket is not connected.
        layer = get_channel_layer()
        if layer:
            try:
                async_to_sync(layer.group_send)(
                    browser_session_group(match.pk, credential_hash, session_id),
                    {"type": "browser_session_blocked", "data": envelope},
                )
            except Exception:
                logger.exception("Browser block broadcast failed for match %s; HTTP acknowledgement remains available", match.pk)
        return Response(envelope)


class BrowserSessionBlockMiddleware:
    """Reject API calls for a reported runtime, even if its UI guard is removed."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        session_id = parse_session_id(request.headers.get("X-Browser-Session"))
        if session_id and request.path.startswith("/api/v1/") and not request.path.endswith("/security/inspection/"):
            tokens = [get_request_host_token(request), get_request_participant_token(request)]
            hashes = [hash_token(token) for token in tokens if token]
            blocks = BrowserSessionBlock.objects.filter(session_id=session_id, reason__in=INSPECTION_REASONS)
            # Django user sessions can also authorize the host without a token.
            if request.user.is_authenticated:
                host_hashes = Match.objects.filter(created_by=request.user).values_list("host_token_hash", flat=True)
                hashes.extend(host_hashes)
            block = blocks.filter(credential_hash__in=hashes).first() if hashes else None
            if block:
                envelope = blocked_envelope(block.match_id)
                return JsonResponse({"error": envelope["payload"]["reason"],
                                     "error_code": "BROWSER_SESSION_BLOCKED", "event": envelope}, status=403)
        return self.get_response(request)
