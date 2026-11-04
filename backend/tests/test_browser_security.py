import uuid
from unittest.mock import patch

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from rest_framework.test import APIClient

from apps.matches.services import MatchService, hash_token
from apps.realtime.browser_security import is_browser_session_blocked
from apps.realtime.models import BrowserSessionBlock
from config.asgi import application


def setup_match():
    match, host = MatchService.create_match()
    team = MatchService.create_team(match, "Inspection team")
    _, token = MatchService.join_match(match, "Player", team_id=team.pk)
    _, other = MatchService.join_match(match, "Teammate", team_id=team.pk)
    return match, host, token, other


def report(match, token, session, **payload):
    return APIClient().post(
        f"/api/v1/matches/{match.pk}/security/inspection/",
        {"reason": "inspection_shortcut", **payload}, format="json",
        HTTP_X_PARTICIPANT_TOKEN=token, HTTP_X_BROWSER_SESSION=str(session),
    )


@pytest.mark.django_db
@pytest.mark.parametrize("reason", ["inspection_shortcut", "devtool_detected"])
def test_report_authenticates_identity_is_idempotent_and_blocks_http_only_for_same_runtime(reason):
    match, host, token, other = setup_match()
    session = uuid.uuid4()
    assert report(match, "invalid", session).status_code == 403
    assert report(match, token, "invalid").status_code == 400
    assert report(match, token, session, reason="anything").status_code == 400
    assert BrowserSessionBlock.objects.count() == 0

    response = report(match, token, session, member_id="spoofed", reason=reason)
    assert response.status_code == 200
    assert response.data["event_type"] == "SESSION_BLOCKED"
    assert response.data["sequence_number"] == 0
    assert report(match, token, session, reason=reason).status_code == 200
    block = BrowserSessionBlock.objects.get()
    assert block.credential_hash == hash_token(token)
    assert block.reason == reason

    url = f"/api/v1/matches/{match.pk}/snapshot/"
    client = APIClient()
    denied = client.get(url, HTTP_X_PARTICIPANT_TOKEN=token, HTTP_X_BROWSER_SESSION=str(session))
    assert denied.status_code == 403
    assert denied.json()["event"]["event_type"] == "SESSION_BLOCKED"
    # A hidden/removed overlay cannot authorize the old runtime's actions.
    denied_write = client.post(f"/api/v1/matches/{match.pk}/teams/{block.match.teams.first().pk}/ready/",
                              {}, format="json", HTTP_X_PARTICIPANT_TOKEN=token,
                              HTTP_X_BROWSER_SESSION=str(session))
    assert denied_write.status_code == 403
    assert client.get(url, HTTP_X_PARTICIPANT_TOKEN=other, HTTP_X_BROWSER_SESSION=str(session)).status_code == 200
    assert client.get(url, HTTP_X_PARTICIPANT_TOKEN=token, HTTP_X_BROWSER_SESSION=str(uuid.uuid4())).status_code == 200
    assert client.get(url, HTTP_X_HOST_TOKEN=host, HTTP_X_BROWSER_SESSION=str(session)).status_code == 200


@pytest.mark.django_db
def test_host_runtime_can_report_and_broadcast_outage_does_not_undo_server_lock():
    match, host, token, other = setup_match()
    session = uuid.uuid4()
    with patch("apps.realtime.browser_security.get_channel_layer") as layer:
        async def fail(*_args, **_kwargs):
            raise RuntimeError("transport unavailable")
        layer.return_value.group_send = fail
        response = APIClient().post(f"/api/v1/matches/{match.pk}/security/inspection/",
                                    {"reason": "inspection_shortcut"}, format="json",
                                    HTTP_X_HOST_TOKEN=host, HTTP_X_BROWSER_SESSION=str(session))
    assert response.status_code == 200
    assert response.data["event_type"] == "SESSION_BLOCKED"
    assert BrowserSessionBlock.objects.get().credential_hash == hash_token(host)
    assert APIClient().get(f"/api/v1/matches/{match.pk}/host-telemetry/", HTTP_X_HOST_TOKEN=host,
                           HTTP_X_BROWSER_SESSION=str(session)).status_code == 403


@pytest.mark.django_db
def test_size_reports_are_rejected_and_legacy_false_positive_records_do_not_block_http():
    match, host, token, other = setup_match()
    session = uuid.uuid4()
    with patch("apps.realtime.browser_security.get_channel_layer") as layer:
        assert report(match, token, session, reason="docked_tools").status_code == 400
        layer.assert_not_called()
    assert BrowserSessionBlock.objects.count() == 0
    BrowserSessionBlock.objects.create(
        match=match, credential_hash=hash_token(token), session_id=session, reason="docked_tools",
    )
    assert not is_browser_session_blocked(match.pk, hash_token(token), session)
    assert APIClient().get(f"/api/v1/matches/{match.pk}/snapshot/",
                           HTTP_X_PARTICIPANT_TOKEN=token, HTTP_X_BROWSER_SESSION=str(session)).status_code == 200
    assert BrowserSessionBlock.objects.count() == 1, "Retain the old decision for audit"
    assert report(match, token, session, reason="devtool_detected").status_code == 200
    assert is_browser_session_blocked(match.pk, hash_token(token), session)


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_server_pushes_private_block_closes_socket_and_rejects_same_runtime_reconnect():
    match, host, token, other = await database_sync_to_async(setup_match)()
    session = uuid.uuid4()

    def socket(credential=token, session_id=session):
        return WebsocketCommunicator(application,
            f"/ws/matches/{match.pk}/?token={credential}&browser_session={session_id}")

    a, twin, teammate = socket(), socket(), socket(other)
    sockets = [a, twin, teammate]
    try:
        for ws in sockets:
            assert (await ws.connect())[0]
            assert (await ws.receive_json_from())["event_type"] == "MATCH_STATE_SNAPSHOT"
        response = await database_sync_to_async(report)(match, token, session, reason="devtool_detected")
        assert response.status_code == 200
        for ws in [a, twin]:
            event = await ws.receive_json_from()
            assert event["event_type"] == "SESSION_BLOCKED"
            assert event["payload"]["reload_required"] is True
            close = await ws.receive_output()
            assert close["type"] == "websocket.close" and close["code"] == 4003

        await teammate.send_json_to({"event_type": "PING"})
        assert (await teammate.receive_json_from())["event_type"] == "PONG"
        reconnect = socket()
        sockets.append(reconnect)
        assert (await reconnect.connect())[0]
        assert (await reconnect.receive_json_from())["event_type"] == "SESSION_BLOCKED"
        assert (await reconnect.receive_output())["code"] == 4003

        fresh_id = uuid.uuid4()
        legacy_block = await database_sync_to_async(BrowserSessionBlock.objects.create)(
            match=match, credential_hash=hash_token(token), session_id=fresh_id, reason="docked_tools",
        )
        fresh_page = socket(session_id=fresh_id)
        sockets.append(fresh_page)
        assert (await fresh_page.connect())[0]
        assert (await fresh_page.receive_json_from())["event_type"] == "MATCH_STATE_SNAPSHOT"
        # Simulate a missed broadcast: persisted server state still prevents
        # this live socket from issuing any more commands, including sync/ping.
        await database_sync_to_async(BrowserSessionBlock.objects.filter(pk=legacy_block.pk).update)(reason="inspection_shortcut")
        await fresh_page.send_json_to({"event_type": "STATE_SYNC_REQUEST"})
        assert (await fresh_page.receive_json_from())["event_type"] == "SESSION_BLOCKED"
        assert (await fresh_page.receive_output())["code"] == 4003
    finally:
        for ws in sockets:
            await ws.disconnect()
