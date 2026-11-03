"""Central rally admission and continuous tower coverage regressions."""
import asyncio
import copy
import math
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.db import connections

from apps.combat.balance import movement_speed
from apps.combat.continuous import ContinuousEngine, distance
from apps.combat.continuous_service import ContinuousCombatService
from apps.combat.formation import (
    bodies_clear,
    initialize_spawn,
    physical_position,
    synchronize_position,
)
from apps.combat.map import get_game_map
from apps.combat.navigation import project
from apps.matches.serializers import MatchConfigurationSerializer
from apps.matches.services import MatchService
from apps.realtime.services import RealtimeService
from apps.units.models import GameEntity
from apps.units.services import ConstructionService, UnitService
from config.asgi import application
from tests.test_battle_websocket import until
from tests.test_continuous_combat import pure_state, room
from tests.test_live_battle_gameplay import convoy


@pytest.mark.parametrize("count", [2, 4, 8, 20])
@pytest.mark.parametrize("codes", [("tank",) * 5, ("tank", "artillery", "tank", "tank", "artillery")])
def test_compact_rally_departs_together_without_skipping_waypoints(count, codes):
    state = convoy(codes, count=count)
    state.configuration["movement_baseline_round_seconds"] = 30
    game_map = get_game_map(count)
    owner = next(iter(state.teams))
    rally = game_map.to_dict(list(state.teams))["rally_areas"][0]
    assert rally["team_id"] == owner
    assert rally["entry_node_id"] == game_map.get_spawn_node(1)
    positions = {e["id"]: physical_position(e, game_map) for e in state.entities}
    assert len(set(positions.values())) == len(codes)
    for entity in state.entities:
        sim = entity["simulation_state"]
        assert sim["staging_entry_distance"] == 0
        assert sim["route_nodes"][0] == rally["entry_node_id"]
        assert math.dist(positions[entity["id"]], tuple(rally["spawn_point"].values())) <= rally["radius"]
    for _ in range(10):
        old = {e["id"]: copy.deepcopy(e) for e in state.entities}
        state = ContinuousEngine.step(state, .1).new_state
        for e in state.entities:
            before, sim = old[e["id"]], e["simulation_state"]
            budget = movement_speed(e, state.configuration) * .1
            assert e["status"] == "ACTIVE" and sim["movement_zone"] == "ROUTE"
            assert sim["movement_state"] == "MOVING"
            assert sim["route_distance"] - before["simulation_state"]["route_distance"] == pytest.approx(budget)
            assert math.dist(physical_position(before, game_map), physical_position(e, game_map)) <= budget + 1e-6


def tower(node="node_tower_t2_slot2", **changes):
    return {"id": "enemy-tower", "team_id": "b", "unit_type_code": "mg_tower", "entity_kind": "TOWER", "damage": 0,
            "range": 2, "current_hp": 100, "current_shield": 0, "status": "ACTIVE", "current_node_id": node,
            "simulation_state": {}, **changes}


def test_live_deployment_cannot_occupy_the_gate_ahead_of_waiting_troops():
    state = convoy(("infantry",) * 5)
    game_map = get_game_map(2)
    for _ in range(3):
        state = ContinuousEngine.step(state, .1).new_state
    late = copy.deepcopy(state.entities[-1])
    late.update(id="late", status="QUEUED", current_node_id=game_map.get_spawn_node(1), simulation_state={})
    initialize_spawn(late, state.entities, game_map.get_base_node(2), game_map, 6, state.configuration)
    spawn = game_map.nodes[game_map.get_spawn_node(1)]
    assert physical_position(late, game_map) != (spawn.x, spawn.y)
    state.entities.append(late)
    for _ in range(300):
        state = ContinuousEngine.step(state, .1).new_state
        if all(e["simulation_state"]["movement_zone"] == "ROUTE" for e in state.entities):
            break
    assert all(e["simulation_state"]["movement_zone"] == "ROUTE" for e in state.entities)


@pytest.mark.parametrize("code", ["infantry", "tank", "artillery"])
def test_rally_capacity_supports_thirty_troops_of_every_standard_footprint(code):
    state = convoy((code,) * 30, count=20)
    game_map = get_game_map(20)
    if code == "infantry":
        assert all(e["status"] == "ACTIVE" for e in state.entities)
        assert all(e["simulation_state"]["route_distance"] == 0 for e in state.entities)
        return
    for i, a in enumerate(state.entities):
        for b in state.entities[i + 1:]:
            assert bodies_clear(a, b, physical_position(a, game_map), physical_position(b, game_map), {"troop_formation_gap": 12})


@pytest.mark.parametrize("progress", [.01, .25, .5, .75, .99])
def test_infantry_attacks_adjacent_tower_across_entire_covered_road_edge(progress):
    state = pure_state(node="node_lane_t2_3")
    state.entities[0]["simulation_state"] = {"next_node_id": "node_lane_t2_2", "edge_progress": progress}
    state.entities.append(tower(current_shield=3))
    assert distance(state.entities[0], state.entities[1], get_game_map(2)) == 1
    result = ContinuousEngine.step(state, .2)
    hit = next(e for e in result.events if e["type"] == "UNIT_ATTACKED")
    assert hit["target_entity_id"] == "enemy-tower"
    assert hit["damage"] == 5 and hit["shield_absorbed"] == 3 and hit["target_hp_remaining"] == 98


@pytest.mark.parametrize("changes", [{"team_id": "a"}, {"status": "DESTROYED", "current_hp": 0}, {"current_node_id": "node_tower_t1_slot1"}])
def test_friendly_destroyed_and_out_of_range_towers_are_never_targeted(changes):
    state = pure_state(node="node_lane_t2_3")
    state.entities.append(tower(**changes))
    assert not any(e["type"] == "UNIT_ATTACKED" for e in ContinuousEngine.step(state, .2).events)


def test_target_priority_is_deterministic_configurable_and_tower_cooldown_is_respected():
    state = pure_state(node="node_lane_t2_3")
    state.entities.append(tower())
    enemy = copy.deepcopy(state.entities[0])
    enemy.update(id="enemy-unit", team_id="b", target_team_id="a", damage=0, simulation_state={})
    state.entities.append(enemy)
    for priority, expected in [(["UNIT", "TOWER"], "enemy-unit"), (["TOWER", "UNIT"], "enemy-tower")]:
        state.configuration["troop_target_priority"] = priority
        result = ContinuousEngine.step(state, .2)
        hit = next(e for e in result.events if e["type"] == "UNIT_ATTACKED")
        assert hit["target_entity_id"] == expected
        assert not any(e["type"] == "UNIT_ATTACKED" for e in ContinuousEngine.step(result.new_state, .2).events)
    serializer = MatchConfigurationSerializer(data={"troop_target_priority": ["UNIT", "UNIT"]}, partial=True)
    assert not serializer.is_valid()


@pytest.mark.django_db
def test_tick_persists_tower_death_once_and_full_entity_updates_restore_late_arrivals():
    match, teams, _, _ = room(prep=2, battle=60)
    unit = UnitService.deploy_unit(match, teams[0], "infantry", str(teams[1].pk))[1]
    target = ConstructionService.build_tower(match, teams[1], "mg_tower", "node_tower_t2_slot2")[1]
    target.current_hp, target.current_shield = 5, 0
    target.save()
    unit.status, unit.current_node_id = "ACTIVE", "node_lane_t2_3"
    unit.simulation_state = {"next_node_id": "node_lane_t2_2", "edge_progress": .5}
    unit.save()
    match = MatchService.advance_phase(match)
    at = datetime.fromisoformat(match.configuration["timer_state"]["next_tick_at"])
    assert ContinuousCombatService.tick(match.pk, at)
    assert not ContinuousCombatService.tick(match.pk, at)
    target.refresh_from_db()
    assert target.status == "DESTROYED" and target.current_hp == 0 and target.destroyed_at == at
    for tick in range(1, 4):
        assert ContinuousCombatService.tick(match.pk, at + timedelta(seconds=tick * .2))
    events = [e for row in match.events.filter(event_type="COMBAT_TICK") for e in row.payload["events"]]
    assert len([e for e in events if e["type"] == "ENTITY_DESTROYED" and e["entity_id"] == str(target.pk)]) == 1
    assert len([e for e in events if e["type"] == "TOWER_ATTACKED"]) == 1
    first = match.events.filter(event_type="COMBAT_TICK").earliest("sequence_number")
    update = next(e for e in first.payload["entity_updates"] if e["id"] == str(unit.pk))
    assert update["team_id"] == str(teams[0].pk) and update["unit_code"] == "infantry"
    assert update["entity_kind"] == "UNIT" and update["max_hp"] == 80
    snap = RealtimeService.build_snapshot(match)["payload"]
    assert str(target.pk) not in {e["id"] for e in snap["entities"]}


def test_simultaneous_hits_stop_at_zero_without_extra_damage_events():
    state = pure_state(node="node_lane_t2_3")
    follower = copy.deepcopy(state.entities[0])
    follower.update(id="second", simulation_state={})
    state.entities.extend([follower, tower(current_hp=5)])
    result = ContinuousEngine.step(state, .2)
    hits = [e for e in result.events if e["type"] == "UNIT_ATTACKED"]
    assert len(hits) == 1 and hits[0]["hp_damage"] == 5


@pytest.mark.django_db
def test_stationary_rally_troops_do_not_generate_unchanged_json_database_writes():
    match, teams, _, _ = room(prep=2, battle=60)
    entities = [UnitService.deploy_unit(match, teams[0], "infantry", str(teams[1].pk))[1] for _ in range(3)]
    unit_type = entities[-1].unit_type
    unit_type.base_stats["movement"] = 0
    unit_type.save()
    match = MatchService.advance_phase(match)
    at = datetime.fromisoformat(match.configuration["timer_state"]["next_tick_at"])
    assert ContinuousCombatService.tick(match.pk, at)
    with patch.object(GameEntity.objects, "bulk_update", wraps=GameEntity.objects.bulk_update) as update:
        assert ContinuousCombatService.tick(match.pk, at + timedelta(seconds=.2))
    written = {entity.pk for call in update.call_args_list for entity in call.args[0]}
    assert entities[-1].pk not in written


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("count", [4, 8, 20])
async def test_both_deployment_orders_builds_and_reconnect_share_identical_committed_events(count):
    match, teams, tokens, _ = await database_sync_to_async(room)(count=count, prep=300, battle=300)

    async def connect(i):
        client = WebsocketCommunicator(application, f"/ws/matches/{match.pk}/?token={tokens[i]}")
        assert (await client.connect())[0]
        return client, await until(client, "MATCH_STATE_SNAPSHOT")

    a, _ = await connect(0)
    b, _ = await connect(1)
    clients = [a, b]
    try:
        ids = set()
        for phase in range(2):
            if phase:
                await database_sync_to_async(MatchService.advance_phase)(match)
            for order in [(0, 1), (1, 0)]:
                for i in order:
                    await clients[i].send_json_to({"event_type": "DEPLOY_REQUEST", "payload": {
                        "unit_code": "infantry", "target_team_id": str(teams[1 - i].pk),
                        "idempotency_key": f"{phase}-{len(ids)}",
                    }})
                    events = await asyncio.gather(*(until(c, "UNIT_DEPLOYED") for c in clients))
                    assert events[0]["event_id"] == events[1]["event_id"]
                    assert events[0]["sequence_number"] == events[1]["sequence_number"]
                    for recipient, event in enumerate(events):
                        assert event["match_id"] == str(match.pk)
                        assert event["payload"]["team_id"] == str(teams[i].pk)
                        assert ("coins_after" in event["payload"]) == (recipient == i)
                        assert event["payload"]["simulation_state"]["movement_zone"] == "ROUTE"
                    ids.add(events[0]["payload"]["entity_id"])
            for i in [1, 0]:
                await clients[i].send_json_to({"event_type": "BUILD_REQUEST", "payload": {
                    "tower_code": "mg_tower", "node_id": f"node_tower_t{i + 1}_slot{phase + 1}",
                    "idempotency_key": f"build-{phase}-{i}",
                }})
                events = await asyncio.gather(*(until(c, "TOWER_BUILT") for c in clients))
                assert events[0]["event_id"] == events[1]["event_id"]
                ids.add(events[0]["payload"]["entity_id"])
        await a.disconnect()
        a, snapshot = await connect(0)
        clients[0] = a
        assert {e["id"] for e in snapshot["payload"]["entities"]} == ids
        await b.send_json_to({"event_type": "DEPLOY_REQUEST", "payload": {
            "unit_code": "infantry", "target_team_id": str(teams[0].pk), "idempotency_key": "after-reconnect",
        }})
        received = await asyncio.gather(*(until(c, "UNIT_DEPLOYED") for c in clients))
        assert received[0]["event_id"] == received[1]["event_id"]
    finally:
        await asyncio.gather(*(c.disconnect() for c in clients))
        await database_sync_to_async(connections.close_all)()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_idle_sockets_survive_redis_blocking_poll_and_still_broadcast_both_ways():
    match, teams, tokens, _ = await database_sync_to_async(room)(prep=300, battle=300)
    clients = [WebsocketCommunicator(application, f"/ws/matches/{match.pk}/?token={tokens[i]}") for i in range(2)]
    try:
        for client in clients:
            assert (await client.connect())[0]
            await until(client, "MATCH_STATE_SNAPSHOT")
        # RedisChannelLayer blocks for 5s while idle. A socket read timeout of
        # exactly 5s (redis-py 8's default) kills the consumer before a new action.
        await asyncio.sleep(6.2)
        for i, client in enumerate(clients):
            await client.send_json_to({"event_type": "PING"})
            await until(client, "PONG")
            await client.send_json_to({"event_type": "DEPLOY_REQUEST", "payload": {
                "unit_code": "infantry", "target_team_id": str(teams[1 - i].pk),
                "idempotency_key": f"after-idle-{i}",
            }})
            received = await asyncio.gather(*(until(c, "UNIT_DEPLOYED") for c in clients))
            assert received[0]["event_id"] == received[1]["event_id"]
    finally:
        await asyncio.gather(*(c.disconnect() for c in clients))
        await database_sync_to_async(connections.close_all)()
