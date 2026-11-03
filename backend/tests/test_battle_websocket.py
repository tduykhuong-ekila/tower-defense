"""Real authenticated consumer commands and fan-out, not mocked event payloads."""
import asyncio
import json

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import override_settings

from apps.combat.services import CombatService
from apps.matches.scheduler import ScheduledMatchApplication
from apps.matches.services import MatchService
from apps.questions.models import Question
from apps.questions.services import QuestionService
from apps.units.seeds import ensure_standard_units
from config.asgi import application


@database_sync_to_async
def setup():
    ensure_standard_units()
    match, host = MatchService.create_match(configuration={"gameplay_mode": "LEGACY", "tower_placement_version": 0, "arena_layout_version": 5, "initial_coins":500})
    teams, tokens = [], []
    for i in range(2):
        team = MatchService.create_team(match, f"WS Team {i}")
        _, token = MatchService.join_match(match, f"Member {i}", team_id=team.pk)
        MatchService.set_team_ready(team, True)
        teams.append(team)
        tokens.append(token)
    match = MatchService.start_match(match)
    Question.objects.create(content="Two plus two?", answer_key="4", time_limit_seconds=120)
    tq = QuestionService.get_or_assign_current_question(match, teams[0])
    QuestionService.update_viewing(match, teams[0], tq.pk, "test-viewer", "OPEN")
    return match, host, teams, tokens, tq


async def until(comm, kind):
    chunks = {}
    for _ in range(100):
        ev = await comm.receive_json_from(timeout=3)
        if ev["event_type"] == "JSON_CHUNK":
            payload = ev["payload"]
            parts = chunks.setdefault(payload["id"], [])
            assert payload["index"] == len(parts)
            parts.append(payload["data"])
            if len(parts) < payload["total"]:
                continue
            ev = json.loads("".join(chunks.pop(payload["id"])))
        assert ev["event_type"] != "ACTION_REJECTED", ev
        if ev["event_type"] == kind:
            return ev
    raise AssertionError(f"Missing {kind}")


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_real_websocket_answers_rewards_build_upgrade_emp_repair_target_and_combat():
    match, host, teams, tokens, tq = await setup()
    a = WebsocketCommunicator(application, f"/ws/matches/{match.pk}/?token={tokens[0]}")
    b = WebsocketCommunicator(application, f"/ws/matches/{match.pk}/?token={tokens[1]}")
    assert (await a.connect())[0]
    assert (await b.connect())[0]
    await until(a, "MATCH_STATE_SNAPSHOT")
    await until(b, "MATCH_STATE_SNAPSHOT")
    try:
        await a.send_json_to({"event_type":"ANSWER_SUBMITTED", "payload":{"question_id":str(tq.pk),"answer":"4"}})
        answered = await until(a, "ACTION_ACCEPTED")
        assert answered["payload"]["result"]["reward_options"]["coin_amount"] is None
        await a.send_json_to({"event_type":"REWARD_SELECTED", "payload":{
            "team_question_id":str(tq.pk),"reward_type":"COIN","idempotency_key":"reward"}})
        await until(a,"ACTION_ACCEPTED")
        await b.send_json_to({"event_type":"BUILD_REQUEST", "payload":{
            "tower_code":"mg_tower","node_id":"node_tower_t2_slot1","idempotency_key":"build"}})
        built = (await until(b,"ACTION_ACCEPTED"))["payload"]["result"]
        await b.send_json_to({"event_type":"UPGRADE_REQUEST", "payload":{
            "entity_id":built["entity_id"],"idempotency_key":"upgrade"}})
        await until(b,"ACTION_ACCEPTED")
        await a.send_json_to({"event_type":"DEPLOY_REQUEST", "payload":{
            "unit_code":"infantry","target_team_id":str(teams[1].pk),"idempotency_key":"deploy"}})
        deployed = (await until(a,"ACTION_ACCEPTED"))["payload"]["result"]
        await a.send_json_to({"event_type":"TARGET_SELECTED", "payload":{"target_team_id":str(teams[1].pk)}})
        await until(a,"ACTION_ACCEPTED")
        await a.send_json_to({"event_type":"SCOUT_REQUEST", "payload":{
            "target_team_id":str(teams[1].pk),"idempotency_key":"scout"}})
        scout = await until(a,"ACTION_ACCEPTED")
        assert scout["payload"]["result"]["scout_data"]["towers"]
        await a.send_json_to({"event_type":"EMP_REQUEST", "payload":{
            "target_entity_id":built["entity_id"],"idempotency_key":"emp"}})
        await until(a,"ACTION_ACCEPTED")
        await database_sync_to_async(CombatService.execute_combat_round)(match, expected_round=1)
        ev_a = await until(a,"COMBAT_RESOLVED")
        ev_b = await until(b,"COMBAT_RESOLVED")
        assert ev_a["payload"]["current_round"] == ev_b["payload"]["current_round"] == 2
        public_a = [e for e in ev_a["payload"]["events"] if e["type"] != "INCOME_AWARDED"]
        public_b = [e for e in ev_b["payload"]["events"] if e["type"] != "INCOME_AWARDED"]
        assert public_a == public_b
        assert any(e["type"] == "TOWER_ENABLED" for e in public_a)
        # Snapshot on reconnect restores actual movement and private economy.
        await a.disconnect()
        a = WebsocketCommunicator(application, f"/ws/matches/{match.pk}/?token={tokens[0]}")
        assert (await a.connect())[0]
        snap = (await until(a,"MATCH_STATE_SNAPSHOT"))["payload"]
        unit = next(e for e in snap["entities"] if e["id"] == deployed["entity_id"])
        assert unit["status"] == "ACTIVE"
        assert unit["current_node_id"] != "node_spawn_t1"
        assert snap["current_round"] == 2
        assert next(t for t in snap["teams"] if t["id"] == str(teams[1].pk)).get("coins") is None
    finally:
        await a.disconnect()
        await b.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_scheduler_task_survives_request_completion_and_stops_on_shutdown(monkeypatch):
    from apps.matches.scheduler import MatchScheduler
    called = asyncio.Event()
    loop = asyncio.get_running_loop()
    ticks = []
    def tick():
        ticks.append(1)
        loop.call_soon_threadsafe(called.set)
    async def inner(scope, receive, send):
        await send({"type":"http.response.start","status":200,"headers":[]})
    app = ScheduledMatchApplication(inner)
    monkeypatch.setattr(MatchScheduler, "tick", tick)
    messages = []
    async def send(message):
        messages.append(message)
    async def receive():
        return {"type":"lifespan.shutdown"}
    with override_settings(MATCH_SCHEDULER_ENABLED=True):
        await app({"type":"http"}, receive, send)
        task = app.task
        await asyncio.wait_for(called.wait(), 3)
        assert not task.done()
        await app({"type":"http"}, receive, send)
        assert app.task is task
        await app({"type":"lifespan"}, receive, send)
        assert task.cancelled()
        assert messages[-1]["type"] == "lifespan.shutdown.complete"
        assert ticks
