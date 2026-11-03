import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator

from apps.combat.services import CombatService
from apps.matches.models import MatchPhase
from apps.matches.services import MatchService
from apps.realtime.events import ClientEventType, ServerEventType
from apps.realtime.services import RealtimeService
from apps.teams.models import MemberRole, Team, TeamMember
from config.asgi import application

db_join_match = database_sync_to_async(MatchService.join_match)
db_emit_event = database_sync_to_async(RealtimeService.emit_event)
db_execute_combat_round = database_sync_to_async(CombatService.execute_combat_round)


@pytest.fixture
def match_with_teams(db):
    """Fixture providing an active match with 4 teams and participant tokens."""
    from apps.units.seeds import ensure_standard_units

    ensure_standard_units()
    match, host_token = MatchService.create_match(name="Phase 5 Arena", configuration={"gameplay_mode": "LEGACY"})

    teams = []
    tokens = {}
    members = {}
    for i in range(4):
        team = MatchService.create_team(match, name=f"Team {chr(65 + i)}")
        m_mentor, t_mentor = MatchService.join_match(
            match=match,
            display_name=f"Mentor_{team.name}",
            team_id=team.id,
            role=MemberRole.MENTOR,
        )
        m_mentee, t_mentee = MatchService.join_match(
            match=match,
            display_name=f"Mentee_{team.name}",
            team_id=team.id,
            role=MemberRole.MENTEE,
        )
        MatchService.set_member_ready(m_mentor, True)
        MatchService.set_member_ready(m_mentee, True)
        MatchService.set_team_ready(team, True)
        teams.append(team)
        tokens[str(team.id)] = t_mentee
        members[str(team.id)] = m_mentee

    MatchService.start_match(match)
    return match, host_token, teams, tokens, members


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_websocket_auth_rejects_invalid_token(match_with_teams):
    match, _, _, _, _ = match_with_teams
    communicator = WebsocketCommunicator(
        application, f"/ws/matches/{match.id}/?token=invalid_token_123"
    )
    connected, close_code = await communicator.connect()
    assert not connected or close_code in [4001, 4003]
    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_websocket_auth_accepts_valid_host_and_participant(match_with_teams):
    match, host_token, teams, tokens, _ = match_with_teams

    # Host connection
    host_comm = WebsocketCommunicator(
        application, f"/ws/matches/{match.id}/?token={host_token}"
    )
    connected, _ = await host_comm.connect()
    assert connected
    # Should receive initial snapshot
    init_msg = await host_comm.receive_json_from()
    assert init_msg["event_type"] == ServerEventType.MATCH_STATE_SNAPSHOT
    assert init_msg["payload"]["viewer"]["is_host"] is True
    await host_comm.disconnect()

    # Participant connection
    team_a = teams[0]
    token_a = tokens[str(team_a.id)]
    part_comm = WebsocketCommunicator(
        application, f"/ws/matches/{match.id}/?token={token_a}"
    )
    connected, _ = await part_comm.connect()
    assert connected
    init_msg = await part_comm.receive_json_from()
    assert init_msg["event_type"] == ServerEventType.MATCH_STATE_SNAPSHOT
    assert init_msg["payload"]["viewer"]["team_id"] == str(team_a.id)
    assert init_msg["payload"]["viewer"]["is_host"] is False
    await part_comm.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_spectator_cannot_execute_state_changing_actions(match_with_teams):
    match, _, teams, _, _ = match_with_teams
    team_a = teams[0]

    from apps.matches.services import hash_token

    spec_token = "pt_spectator_test"
    await database_sync_to_async(TeamMember.objects.create)(
        match=match,
        team=team_a,
        display_name="Spectator_1",
        role=MemberRole.SPECTATOR,
        token_hash=hash_token(spec_token),
        is_ready=True,
    )

    spec_comm = WebsocketCommunicator(
        application, f"/ws/matches/{match.id}/?token={spec_token}"
    )
    connected, _ = await spec_comm.connect()
    assert connected
    await spec_comm.receive_json_from()  # initial snapshot

    # Attempt to deploy a unit
    await spec_comm.send_json_to(
        {
            "event_type": ClientEventType.DEPLOY_REQUEST,
            "payload": {
                "unit_code": "infantry",
                "target_team_id": str(teams[1].id),
                "idempotency_key": "spec-deploy-1",
            },
        }
    )

    resp = await spec_comm.receive_json_from()
    assert resp["event_type"] == ServerEventType.ACTION_REJECTED
    assert resp["payload"]["error_code"] == "SPECTATOR_READ_ONLY"
    await spec_comm.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_private_event_isolation_team_a_vs_team_b(match_with_teams):
    match, _, teams, tokens, _ = match_with_teams
    team_a = teams[0]
    team_b = teams[1]

    comm_a = WebsocketCommunicator(
        application, f"/ws/matches/{match.id}/?token={tokens[str(team_a.id)]}"
    )
    comm_b = WebsocketCommunicator(
        application, f"/ws/matches/{match.id}/?token={tokens[str(team_b.id)]}"
    )

    assert (await comm_a.connect())[0]
    assert (await comm_b.connect())[0]
    await comm_a.receive_json_from()
    await comm_b.receive_json_from()

    # Broadcast private event for Team A
    await db_emit_event(
        match=match,
        event_type=ServerEventType.COINS_UPDATED,
        payload={"team_id": str(team_a.id), "new_balance": 150},
    )

    # Team A must receive it
    msg_a = await comm_a.receive_json_from()
    assert msg_a["event_type"] == ServerEventType.COINS_UPDATED
    assert msg_a["payload"]["team_id"] == str(team_a.id)

    # Team B must NOT receive Team A's private event
    redacted = await comm_b.receive_json_from()
    assert redacted["event_type"] == "EVENT_REDACTED" and redacted["payload"] == {}

    await comm_a.disconnect()
    await comm_b.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_monotonic_sequence_number_and_envelope_format(match_with_teams):
    match, _, teams, tokens, _ = match_with_teams
    team_a = teams[0]

    comm = WebsocketCommunicator(
        application, f"/ws/matches/{match.id}/?token={tokens[str(team_a.id)]}"
    )
    await comm.connect()
    snapshot = await comm.receive_json_from()
    initial_seq = snapshot["sequence_number"]

    # Record 3 events
    e1 = await db_emit_event(
        match=match, event_type="TEST_EVENT_1", payload={"data": 1}
    )
    e2 = await db_emit_event(
        match=match, event_type="TEST_EVENT_2", payload={"data": 2}
    )
    e3 = await db_emit_event(
        match=match, event_type="TEST_EVENT_3", payload={"data": 3}
    )

    msg1 = await comm.receive_json_from()
    msg2 = await comm.receive_json_from()
    msg3 = await comm.receive_json_from()

    # Standard envelope compliance (§21)
    for msg in [msg1, msg2, msg3]:
        assert "event_id" in msg
        assert "match_id" in msg
        assert "event_type" in msg
        assert "sequence_number" in msg
        assert "server_timestamp" in msg
        assert "payload" in msg

    assert msg1["sequence_number"] == initial_seq + 1
    assert msg2["sequence_number"] == initial_seq + 2
    assert msg3["sequence_number"] == initial_seq + 3
    await comm.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_scenario_g_reconnection_and_sync_request(match_with_teams):
    """
    Scenario G: Reconnection (§25, §28)
    1. Team disconnects during match.
    2. Other events occur.
    3. Team reconnects and sends STATE_SYNC_REQUEST.
    4. Receives authoritative snapshot reflecting current state.
    """
    match, _, teams, tokens, _ = match_with_teams
    team_a = teams[0]
    token_a = tokens[str(team_a.id)]

    comm = WebsocketCommunicator(application, f"/ws/matches/{match.id}/?token={token_a}")
    await comm.connect()
    await comm.receive_json_from()  # initial snapshot
    await comm.disconnect()  # Disconnect

    # Match continues, events occur while team_a is offline
    await db_emit_event(
        match=match,
        event_type=ServerEventType.MATCH_PHASE_CHANGED,
        payload={"phase": MatchPhase.WAR},
    )

    # Team A reconnects
    comm_reconnected = WebsocketCommunicator(
        application, f"/ws/matches/{match.id}/?token={token_a}"
    )
    connected, _ = await comm_reconnected.connect()
    assert connected

    # Initial snapshot upon connect has updated phase
    reconnect_snapshot = await comm_reconnected.receive_json_from()
    assert reconnect_snapshot["event_type"] == ServerEventType.MATCH_STATE_SNAPSHOT

    # Client explicitly requests sync
    await comm_reconnected.send_json_to(
        {
            "event_type": ClientEventType.STATE_SYNC_REQUEST,
            "payload": {},
        }
    )
    sync_resp = await comm_reconnected.receive_json_from()
    assert sync_resp["event_type"] == ServerEventType.MATCH_STATE_SNAPSHOT
    assert sync_resp["payload"]["match"]["id"] == str(match.id)

    await comm_reconnected.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_http_events_after_sequence_endpoint(async_client, match_with_teams):
    match, host_token, teams, tokens, _ = match_with_teams
    team_a = teams[0]
    team_b = teams[1]

    # Create several events (public and private)
    await db_emit_event(
        match=match,
        event_type="PUBLIC_EVENT_1",
        payload={"message": "public 1"},
    )
    await db_emit_event(
        match=match,
        event_type=ServerEventType.COINS_UPDATED,
        payload={"team_id": str(team_a.id), "new_balance": 120},
    )
    await db_emit_event(
        match=match,
        event_type=ServerEventType.COINS_UPDATED,
        payload={"team_id": str(team_b.id), "new_balance": 90},
    )

    # Request as Team A
    resp_a = await async_client.get(
        f"/api/v1/matches/{match.id}/events/?after_sequence=0",
        headers={"authorization": f"Bearer {tokens[str(team_a.id)]}"},
    )
    assert resp_a.status_code == 200
    events_a = resp_a.json()["events"]
    # Team A sees public event and Team A's coin event, but NOT Team B's coin event
    team_b_coins_seen = any(
        e["event_type"] == ServerEventType.COINS_UPDATED
        and e["payload"].get("team_id") == str(team_b.id)
        for e in events_a
    )
    assert not team_b_coins_seen

    # Request as Host
    resp_host = await async_client.get(
        f"/api/v1/matches/{match.id}/events/?after_sequence=0",
        headers={"authorization": f"Bearer {host_token}"},
    )
    assert resp_host.status_code == 200
    events_host = resp_host.json()["events"]
    # Host sees everything
    team_b_coins_seen_by_host = any(
        e["event_type"] == ServerEventType.COINS_UPDATED
        and e["payload"].get("team_id") == str(team_b.id)
        for e in events_host
    )
    assert team_b_coins_seen_by_host


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_multi_client_integration_four_teams_receive_combat_resolved(
    match_with_teams,
):
    """
    Test Phase 5 Integration:
    4 client WebSockets connect simultaneously.
    Combat is resolved by server.
    All 4 clients receive COMBAT_RESOLVED event.
    """
    match, _, teams, tokens, _ = match_with_teams

    communicators = []
    for team in teams:
        comm = WebsocketCommunicator(
            application, f"/ws/matches/{match.id}/?token={tokens[str(team.id)]}"
        )
        connected, _ = await comm.connect()
        assert connected
        await comm.receive_json_from()  # Snapshot
        communicators.append(comm)

    # Trigger combat round execution via db_execute_combat_round
    round_result = await db_execute_combat_round(match)

    # All 4 communicators must receive COMBAT_RESOLVED event
    for comm in communicators:
        event = await comm.receive_json_from()
        assert event["event_type"] == ServerEventType.COMBAT_RESOLVED
        assert "round_number" in event["payload"]
        assert "events" in event["payload"]

    for comm in communicators:
        await comm.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_websocket_duplicate_request_idempotency_prevents_duplicate_effects(
    match_with_teams,
):
    """
    Test duplicate message / idempotency key via WebSocket (§2.3, §21).
    Sending identical action with same idempotency_key does not duplicate side effects.
    """
    match, _, teams, tokens, _ = match_with_teams
    team_a = teams[0]
    token_a = tokens[str(team_a.id)]

    comm = WebsocketCommunicator(
        application, f"/ws/matches/{match.id}/?token={token_a}"
    )
    assert (await comm.connect())[0]
    await comm.receive_json_from()  # initial snapshot

    initial_coins = team_a.coins
    idemp_key = "ws-test-idemp-deploy-1"

    async def receive_action_response():
        for _ in range(5):
            msg = await comm.receive_json_from()
            if msg.get("event_type") in [ServerEventType.ACTION_ACCEPTED, ServerEventType.ACTION_REJECTED]:
                return msg
        return None

    # Send first deploy request
    await comm.send_json_to(
        {
            "event_type": ClientEventType.DEPLOY_REQUEST,
            "payload": {
                "unit_code": "infantry",
                "target_team_id": str(teams[1].id),
                "idempotency_key": idemp_key,
            },
        }
    )

    resp1 = await receive_action_response()
    assert resp1 is not None and resp1["event_type"] == ServerEventType.ACTION_ACCEPTED
    action_id_1 = resp1["payload"]["result"]["action_id"]
    entity_id_1 = resp1["payload"]["result"]["entity_id"]

    # Send duplicate request with exact same idempotency_key
    await comm.send_json_to(
        {
            "event_type": ClientEventType.DEPLOY_REQUEST,
            "payload": {
                "unit_code": "infantry",
                "target_team_id": str(teams[1].id),
                "idempotency_key": idemp_key,
            },
        }
    )

    resp2 = await receive_action_response()
    assert resp2 is not None and resp2["event_type"] == ServerEventType.ACTION_ACCEPTED
    assert resp2["payload"]["result"]["action_id"] == action_id_1
    assert resp2["payload"]["result"]["entity_id"] == entity_id_1

    # Verify in DB that only 1 unit and 1 action was created, and coins debited once (infantry cost = 15)
    refreshed_team = await database_sync_to_async(Team.objects.get)(id=team_a.id)
    assert refreshed_team.coins == initial_coins - 15

    from apps.units.models import GameAction

    actions_count = await database_sync_to_async(
        GameAction.objects.filter(team=team_a, idempotency_key=idemp_key).count
    )()
    assert actions_count == 1

    await comm.disconnect()

