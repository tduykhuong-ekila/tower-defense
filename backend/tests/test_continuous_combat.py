"""Continuous-mode acceptance, using real services, clocks and authenticated sockets."""
import asyncio
import math
from datetime import timedelta
from unittest.mock import patch

import pytest
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.core.exceptions import ValidationError
from django.db import connections, transaction
from django.utils import timezone

from apps.combat.balance import attack_damage, movement_speed
from apps.combat.continuous import ContinuousEngine
from apps.combat.continuous_service import ContinuousCombatService
from apps.combat.engine import CombatState
from apps.combat.map import get_game_map
from apps.combat.models import MatchResult
from apps.matches.action_policy import ActionPolicy
from apps.matches.models import Match, MatchEvent
from apps.matches.scheduler import MatchScheduler
from apps.matches.services import MatchService
from apps.questions.models import Question
from apps.questions.services import QuestionService
from apps.realtime.services import RealtimeService
from apps.rewards.services import RewardService
from apps.units.models import GameEntity, TeamUnlock, UnitType
from apps.units.seeds import STANDARD_UNITS, ensure_standard_units
from apps.units.services import ConstructionService, UnitService
from config.asgi import application


def room(rounds=3, count=2, prep=2, battle=2, **configuration):
    ensure_standard_units()
    match, host = MatchService.create_match(configuration={
        "total_rounds": rounds, "max_teams": count, "initial_coins": 500,
        "tower_placement_version": 0, "arena_layout_version": 5,
        "first_preparation_duration_seconds": prep, "preparation_duration_seconds": prep,
        "battle_duration_seconds": battle, **configuration,
    })
    teams, tokens = [], []
    for i in range(count):
        team = MatchService.create_team(match, f"Continuous {i}")
        _, token = MatchService.join_match(match, f"Player {i}", team_id=team.pk)
        MatchService.set_team_ready(team, True)
        teams.append(team)
        tokens.append(token)
    _, spectator_token = MatchService.join_match(match, "Spectator", role="SPECTATOR")
    tokens.append(spectator_token)
    match = MatchService.start_match(match)
    return match, teams, tokens, host


def advance(match, moment):
    # Drain bounded catch-up using fresh reads, as a restarted scheduler would.
    for _ in range(200):
        old = Match.objects.get(pk=match.pk).configuration.get("timer_state")
        MatchScheduler.advance_due(match.pk, moment)
        match.refresh_from_db()
        if match.status == "FINISHED" or match.configuration["timer_state"] == old:
            return
    pytest.fail("Clock catch-up failed to converge")


@pytest.mark.django_db
@pytest.mark.parametrize("rounds", [2, 3])
def test_complete_major_rounds_preserve_survivors_and_finish(rounds):
    match, teams, _, _ = room(rounds)
    _, unit = UnitService.deploy_unit(match, teams[0], "infantry", str(teams[1].pk))
    _, tower = ConstructionService.build_tower(match, teams[0], "mg_tower", "node_tower_t1_slot1")
    start = match.started_at
    for n in range(1, rounds + 1):
        advance(match, start + timedelta(seconds=(n - 1) * 4 + 2))
        assert match.phase == "WAR"
        assert ActionPolicy.context(match, teams[0], "DEPLOY_UNIT").allowed
        assert ActionPolicy.context(match, teams[0], "BUILD_TOWER").allowed
        first_tick = timezone.datetime.fromisoformat(match.configuration["timer_state"]["next_tick_at"])
        assert ContinuousCombatService.tick(match.pk, first_tick)
        assert not ContinuousCombatService.tick(match.pk, first_tick)
        unit.refresh_from_db()
        assert unit.status == "ACTIVE" and unit.simulation_state["edge_progress"] > 0
        advance(match, start + timedelta(seconds=n * 4))
        unit.refresh_from_db()
        tower.refresh_from_db()
        assert unit.status == tower.status == "ACTIVE"
        assert unit.simulation_state["edge_progress"] > 0
        if n < rounds:
            assert match.phase == "PREPARATION" and match.configuration["current_round"] == n + 1
    assert match.status == "FINISHED" and match.results.count() == 2
    assert match.configuration["simulation_tick"] == rounds * 10
    assert match.events.filter(event_type="MATCH_ENDED").count() == 1
    teams[0].refresh_from_db()
    assert teams[0].coins == 500 - 15 - 25 + rounds * 10


@pytest.mark.django_db
def test_default_config_reward_and_pause_recovery():
    match, teams, _, _ = room(prep=120, battle=300)
    assert match.configuration["gameplay_mode"] == "CONTINUOUS"
    assert match.configuration["total_rounds"] == 3
    Question.objects.create(content="2+2?", answer_key="4", time_limit_seconds=120)
    tq = QuestionService.get_or_assign_current_question(match, teams[0])
    QuestionService.update_viewing(match, teams[0], tq.pk, "test-viewer", "OPEN")
    QuestionService.submit_answer(match, teams[0], str(tq.pk), "4")
    claim = RewardService.claim_reward(match, teams[0], str(tq.pk), "COIN", idempotency_key="one")
    assert claim.coin_amount == 30
    RewardService.claim_reward(match, teams[0], str(tq.pk), "COIN", idempotency_key="two")
    teams[0].refresh_from_db()
    assert teams[0].coins == 530
    start = match.started_at
    advance(match, start + timedelta(seconds=120))
    with patch("django.utils.timezone.now", return_value=start + timedelta(seconds=120.1)):
        match = MatchService.pause_match(match)
    advance(match, start + timedelta(seconds=220))
    assert match.configuration.get("simulation_tick", 0) == 0
    with patch("django.utils.timezone.now", return_value=start + timedelta(seconds=220.1)):
        match = MatchService.resume_match(match)
    advance(match, start + timedelta(seconds=220.2))
    assert match.configuration["simulation_tick"] == 1
    # Restart/retry same server time cannot repeat committed ticks.
    advance(Match.objects.get(pk=match.pk), start + timedelta(seconds=220.2))
    assert Match.objects.get(pk=match.pk).configuration["simulation_tick"] == 1


def pure_state(code="infantry", node="node_spawn_t1", config=None):
    stats = next(s["base_stats"] for s in STANDARD_UNITS if s["code"] == code)
    return CombatState(1, False, {
        "a": {"team_index": 1, "status": "ACTIVE", "base_hp": 500, "base_shield": 0},
        "b": {"team_index": 2, "status": "ACTIVE", "base_hp": 500, "base_shield": 0},
    }, [{**stats, "id": "unit", "team_id": "a", "unit_type_code": code,
         "entity_kind": "UNIT", "current_hp": stats["hp"], "current_shield": 0,
         "status": "ACTIVE", "current_node_id": node, "target_team_id": "b",
         "simulation_state": {}}], [], config or {})


@pytest.mark.parametrize("code,damage", [("infantry", 10), ("tank", 25), ("artillery", 40)])
def test_speed_damage_and_sequential_waypoints(code, damage):
    factor = {"infantry": 5.5, "tank": 4, "artillery": 5}[code]
    state = pure_state(code)
    e = state.entities[0]
    assert movement_speed(e, {}) == e["movement"] * 80 / 30 * factor
    assert sum(attack_damage(e) for _ in range(10)) == damage * 5
    game_map = get_game_map(2)
    original = state.entities[0]["current_node_id"]
    route = game_map.get_path_to_base(original, 2)
    visited = [original]
    for i in range(600):
        result = ContinuousEngine.step(state, .2)
        state = result.new_state
        current = state.entities[0]
        if current["current_node_id"] != visited[-1]:
            visited.append(current["current_node_id"])
        assert current["simulation_state"].get("next_node_id") in (None, *game_map.adjacency[current["current_node_id"]])
    assert visited == route[:len(visited)] and len(visited) > 2
    # Movement uses the centralized speed setting of 4 on the physical first edge.
    first = ContinuousEngine.step(pure_state(code), .2).new_state.entities[0]
    a, b = game_map.nodes[original], game_map.nodes[first["simulation_state"]["next_node_id"]]
    length = math.hypot(b.x - a.x, b.y - a.y)
    assert first["simulation_state"]["edge_progress"] * length == pytest.approx(e["movement"] * first["simulation_state"]["reference_hop_length"] / 30 * factor * .2)
    fast = pure_state(code, config={"movement_baseline_round_seconds": 1})
    for ticks in range(1, 200):
        fast = ContinuousEngine.step(fast, .2).new_state
        if fast.entities[0]["current_node_id"] == route[-1]:
            break
    assert ticks * .2 == pytest.approx((len(route) - 1) / e["movement"] / factor, abs=.2)


def test_repeated_base_hits_simultaneous_elimination_and_tower_damage():
    state = pure_state(node="node_lane_t2_1")
    hp = state.teams["b"]["base_hp"]
    for _ in range(11):
        state = ContinuousEngine.step(state, .2).new_state
    assert state.teams["b"]["base_hp"] == hp - 10
    assert state.entities[0]["status"] == "ACTIVE"
    tower = {"damage": 15, "entity_kind": "TOWER", "level": 1, "simulation_state": {}}
    assert attack_damage(tower) == 15
    state = pure_state(node="node_lane_t2_1")
    state.teams["a"]["base_hp"] = state.teams["b"]["base_hp"] = 5
    state.entities.append({**state.entities[0], "id": "other", "team_id": "b",
                           "current_node_id": "node_lane_t1_1", "target_team_id": "a", "simulation_state": {}})
    result = ContinuousEngine.step(state, .2)
    assert result.is_match_over and result.winner_team_id is None
    assert set(result.eliminated_team_ids) == {"a", "b"}


@pytest.mark.django_db(transaction=True)
def test_transport_failure_retries_committed_outbox_and_rollback_never_sends():
    match, _, _, _ = room()
    layer = get_channel_layer()
    with patch.object(layer, "group_send", side_effect=RuntimeError("offline")):
        event = MatchService.record_match_event(match, "TEST_PUBLIC", {})
    event.refresh_from_db()
    assert event.broadcasted_at is None
    with patch.object(layer, "group_send", wraps=layer.group_send) as send:
        MatchScheduler.tick()
        assert send.called
    event.refresh_from_db()
    assert event.broadcasted_at is not None
    with patch.object(layer, "group_send") as send:
        with pytest.raises(RuntimeError), transaction.atomic():
            MatchService.record_match_event(match, "ROLLED_BACK", {})
            raise RuntimeError("rollback")
        assert not send.called
    assert not match.events.filter(event_type="ROLLED_BACK").exists()


async def until(comm, kind):
    for _ in range(300):
        event = await comm.receive_json_from(timeout=5)
        assert event["event_type"] != "ACTION_REJECTED", event
        if event["event_type"] == kind:
            return event
    raise AssertionError(kind)


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("count", [2, 20])
async def test_public_spawn_build_live_combat_reconnect_and_complete_match(count):
    match, teams, tokens, host = await database_sync_to_async(room)(count=count, prep=2, battle=2)
    async def connect(token):
        client = WebsocketCommunicator(application, f"/ws/matches/{match.pk}/?token={token}")
        assert (await client.connect())[0]
        await until(client, "MATCH_STATE_SNAPSHOT")
        return client
    a, b, spectator = await asyncio.gather(connect(tokens[0]), connect(tokens[1]), connect(tokens[-1]))
    try:
        await a.send_json_to({"event_type": "DEPLOY_REQUEST", "payload": {
            "unit_code": "infantry", "target_team_id": str(teams[1].pk), "idempotency_key": "deploy"}})
        received = await asyncio.gather(*(until(c, "UNIT_DEPLOYED") for c in [a, b, spectator]))
        assert len({e["payload"]["entity_id"] for e in received}) == 1
        await b.send_json_to({"event_type": "BUILD_REQUEST", "payload": {
            "tower_code": "mg_tower", "node_id": "node_tower_t2_slot1", "idempotency_key": "build"}})
        built = await asyncio.gather(*(until(c, "TOWER_BUILT") for c in [a, b, spectator]))
        assert len({e["payload"]["entity_id"] for e in built}) == 1
        await database_sync_to_async(advance)(match, match.started_at + timedelta(seconds=2.4))
        ticks = await asyncio.gather(until(a, "COMBAT_TICK"), until(b, "COMBAT_TICK"))
        assert ticks[0]["payload"]["entity_updates"] == ticks[1]["payload"]["entity_updates"]
        await b.send_json_to({"event_type": "BUILD_REQUEST", "payload": {
            "tower_code": "mg_tower", "node_id": "node_tower_t2_slot2", "idempotency_key": "live-build"}})
        live_towers = await asyncio.gather(*(until(c, "TOWER_BUILT") for c in [a, b, spectator]))
        assert len({event["payload"]["entity_id"] for event in live_towers}) == 1
        await a.send_json_to({"event_type": "DEPLOY_REQUEST", "payload": {
            "unit_code": "infantry", "target_team_id": str(teams[1].pk), "idempotency_key": "live-deploy"}})
        live_units = await asyncio.gather(*(until(c, "UNIT_DEPLOYED") for c in [a, b, spectator]))
        assert len({event["payload"]["entity_id"] for event in live_units}) == 1
        assert all(event["payload"]["current_hp"] == event["payload"]["max_hp"] == 80 for event in live_units)
        await a.disconnect()
        a = await connect(tokens[0])
        await a.send_json_to({"event_type": "STATE_SYNC_REQUEST", "payload": {}})
        snapshot = (await until(a, "MATCH_STATE_SNAPSHOT"))["payload"]
        unit = next(e for e in snapshot["entities"] if e["id"] == received[0]["payload"]["entity_id"])
        assert unit["simulation_state"]["edge_progress"] > 0
        await database_sync_to_async(advance)(match, match.started_at + timedelta(seconds=12))
        await until(a, "MATCH_ENDED")
        assert await database_sync_to_async(MatchResult.objects.filter(match=match).count)() == count
    finally:
        await asyncio.gather(*(c.disconnect() for c in [a, b, spectator]))
        await database_sync_to_async(connections.close_all)()


@pytest.mark.django_db
def test_continuous_damage_events_tower_targeting_and_early_victory():
    state = pure_state(node="node_lane_t2_3")
    state.entities.append({"id": "tower", "team_id": "b", "entity_kind": "TOWER", "damage": 15,
        "range": 2, "current_hp": 100, "current_shield": 0, "status": "ACTIVE",
        "current_node_id": "node_tower_t2_slot2", "simulation_state": {}})
    result = ContinuousEngine.step(state, .2)
    hit = next(e for e in result.events if e["type"] == "TOWER_ATTACKED")
    assert hit["damage"] == 15 and hit["target_hp_remaining"] == 65
    assert next(e for e in result.events if e["type"] == "UNIT_ATTACKED")["damage"] == 5
    state = pure_state("artillery", node="node_lane_t2_3")
    state.entities.append({**next(e for e in result.new_state.entities if e["id"] == "tower"), "current_hp": 20, "simulation_state": {}})
    result = ContinuousEngine.step(state, .2)
    assert any(e["type"] == "ENTITY_DESTROYED" and e["entity_id"] == "tower" for e in result.events)
    match, teams, _, _ = room(prep=2, battle=10)
    _, unit = UnitService.deploy_unit(match, teams[0], "infantry", str(teams[1].pk))
    unit.status, unit.current_node_id = "ACTIVE", "node_lane_t2_1"
    unit.simulation_state = {}
    unit.save()
    teams[1].base_hp = 10
    teams[1].save()
    match = MatchService.advance_phase(match)
    advance(match, timezone.datetime.fromisoformat(match.configuration["timer_state"]["phase_started_at"]) + timedelta(seconds=2.4))
    assert match.status == "FINISHED"
    assert match.results.get(final_rank=1).team_id == teams[0].pk
    damages = [e for tick in match.events.filter(event_type="COMBAT_TICK") for e in tick.payload["events"] if e["type"] == "BASE_DAMAGED"]
    assert [e["damage"] for e in damages] == [5, 5]
    assert [e["base_hp_remaining"] for e in damages] == [5, 0]


@pytest.mark.django_db
def test_host_phase_override_follows_major_round_order_and_keeps_audit():
    match, _, _, _ = room()
    with pytest.raises(ValidationError):
        MatchService.advance_phase(match, "BUILD_AND_SCOUT", is_override=True)
    match = MatchService.advance_phase(match, "WAR", is_override=True, reason="Begin battle")
    assert match.phase == "WAR"
    event = match.events.get(event_type="ADMINISTRATIVE_OVERRIDE")
    assert event.payload["reason"] == "Begin battle"
    match = MatchService.advance_phase(match, "PREPARATION", is_override=True)
    assert match.phase == "PREPARATION" and match.configuration["current_round"] == 2
