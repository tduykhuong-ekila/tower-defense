"""Infantry must reach and destroy defenses before damaging the selected base."""
import copy
import json
import math

import pytest

from apps.combat.balance import movement_speed
from apps.combat.continuous import ContinuousEngine, target_distance
from apps.combat.engine import CombatEngine
from apps.combat.formation import physical_position
from apps.combat.map import get_game_map
from tests.test_continuous_combat import pure_state
from tests.test_spawn_tower_realtime import tower


@pytest.mark.parametrize("count", [2, 4, 8, 20])
def test_roadside_towers_are_destroyed_without_leaving_sand_with_saved_ticks(count):
    state = pure_state(node="node_lane_t2_1", config={"arena_layout_version": 6})
    for index in range(3, count + 1):
        state.teams[str(index)] = {"team_index": index, "status": "ACTIVE", "base_hp": 500, "base_shield": 0}
    graph = get_game_map(count, 6)
    anchor = graph.nodes["node_lane_t2_2"]
    for index, offset in enumerate([80, -80]):
        state.entities.append(tower(node=anchor.node_id, id=f"tower-{index}", current_hp=10,
            simulation_state={"grid_placement": {"row": 1, "col": 1},
                              "world_position": {"x": anchor.x, "y": anchor.y + offset}}))
    destroyed = set()
    approached = False
    for _ in range(1500):
        old = next(e for e in state.entities if e["id"] == "unit")
        result = ContinuousEngine.step(state, .2)
        state = result.new_state
        unit = next(e for e in state.entities if e["id"] == "unit")
        assert math.dist(physical_position(old, graph), physical_position(unit, graph)) <= movement_speed(unit, state.configuration) * .2 + 1e-6
        approached |= bool(unit["simulation_state"].get("siege_detour"))
        for event in result.events:
            if event["type"] == "UNIT_ATTACKED":
                target = next(e for e in state.entities if e["id"] == event["target_entity_id"])
                assert target_distance(unit, target, graph) <= unit["range"]
            if event["type"] == "ENTITY_DESTROYED":
                destroyed.add(event["entity_id"])
            if event["type"] == "BASE_DAMAGED":
                assert destroyed >= {"tower-0", "tower-1"}
                assert not approached
                return
        assert state.teams["b"]["base_hp"] == 500
        state.entities = json.loads(json.dumps(state.entities))
    pytest.fail("Infantry did not clear both towers and resume the base attack")


@pytest.mark.parametrize("status,hp,team_id", [("DESTROYED", 0, "b"), ("ACTIVE", 100, "a")])
def test_friendly_and_destroyed_towers_do_not_protect_enemy_base(status, hp, team_id):
    state = pure_state(node="node_lane_t2_1")
    state.entities.append(tower(node="node_tower_t1_slot1", status=status, current_hp=hp, team_id=team_id))
    assert any(e["type"] == "BASE_DAMAGED" for e in ContinuousEngine.step(state, .2).events)


def test_disabled_tower_blocks_base_and_is_still_attackable():
    state = pure_state(node="node_lane_t2_1")
    state.entities.append(tower(node="node_tower_t2_slot1", status="DISABLED", current_hp=5))
    result = ContinuousEngine.step(state, .2)
    assert not any(e["type"] == "BASE_DAMAGED" for e in result.events)
    assert any(e["type"] == "UNIT_ATTACKED" for e in result.events)


def test_legacy_infantry_leaves_base_to_clear_distant_tower():
    state = pure_state(node="node_lane_t2_1")
    state.entities.append(tower(node="node_tower_t2_slot2", current_hp=10))
    hits = []
    for _ in range(20):
        result = CombatEngine.resolve_round(state)
        state = result.new_state
        hits.extend(e["type"] for e in result.events if e["type"] in ("UNIT_ATTACKED", "BASE_DAMAGED"))
        if "BASE_DAMAGED" in hits:
            assert hits[0] == "UNIT_ATTACKED"
            assert next(e for e in state.entities if e["id"] == "enemy-tower")["current_hp"] == 0
            return
    pytest.fail("Legacy Infantry never resumed attacking the base")


def test_tower_built_while_infantry_is_hitting_base_interrupts_the_base_attack():
    state = pure_state(node="node_lane_t2_1")
    result = ContinuousEngine.step(state, .2)
    assert any(e["type"] == "BASE_DAMAGED" for e in result.events)
    state = result.new_state
    state.entities.append(tower(node="node_tower_t2_slot2"))
    hp = state.teams["b"]["base_hp"]
    for _ in range(10):
        state = ContinuousEngine.step(state, .2).new_state
        assert state.teams["b"]["base_hp"] == hp


def test_road_firing_position_resumes_base_route_after_tower_destroyed():
    from apps.combat.formation import initialize_spawn

    state = pure_state(config={"arena_layout_version": 6})
    graph = get_game_map(2, 6)
    unit = state.entities[0]
    initialize_spawn(unit, [], graph.get_base_node(2), graph, 1, state.configuration)
    anchor = graph.nodes["node_lane_t2_1"]
    state.entities.append(tower(node=anchor.node_id, current_hp=5,
        simulation_state={"grid_placement": {"row": 1, "col": 1},
                          "world_position": {"x": anchor.x, "y": anchor.y + 80}}))
    destroyed = False
    for _ in range(2000):
        result = ContinuousEngine.step(state, .2)
        state = result.new_state
        unit = next(e for e in state.entities if e["id"] == "unit")
        destroyed |= any(e["type"] == "ENTITY_DESTROYED" for e in result.events)
        if destroyed:
            assert math.dist(physical_position(unit, graph), (anchor.x, anchor.y)) < 400
        if any(e["type"] == "BASE_DAMAGED" for e in result.events):
            assert unit["simulation_state"]["movement_zone"] == "ROUTE"
            assert not unit["simulation_state"].get("siege_detour")
            return
    pytest.fail("Infantry did not return to attack the base")


def test_retreat_during_road_approach_follows_roads_to_rally():
    from apps.combat.formation import redirect_route

    state = pure_state(node="node_lane_t2_2", config={"arena_layout_version": 6})
    graph = get_game_map(2, 6)
    anchor = graph.nodes["node_lane_t2_2"]
    state.entities.append(tower(node=anchor.node_id,
        simulation_state={"grid_placement": {"row": 1, "col": 1},
                          "world_position": {"x": anchor.x, "y": anchor.y + 80}}))
    for _ in range(10):
        state = ContinuousEngine.step(state, .2).new_state
    unit = next(e for e in state.entities if e["id"] == "unit")
    assert not unit["simulation_state"].get("siege_detour")
    rally = graph.get_spawn_node(1)
    redirect_route(unit, rally, graph)
    unit["simulation_state"].update(order="RETREAT", destination_rally_id=rally)
    for _ in range(1500):
        previous = physical_position(unit, graph)
        result = ContinuousEngine.step(state, .2)
        state = result.new_state
        unit = next(e for e in state.entities if e["id"] == "unit")
        assert math.dist(previous, physical_position(unit, graph)) <= movement_speed(unit, state.configuration) * .2 + 1e-6
        assert not any(e["type"] in ("UNIT_ATTACKED", "BASE_DAMAGED") for e in result.events)
        if unit["simulation_state"]["order"] == "AT_RALLY":
            return
    pytest.fail("Retreating Infantry did not reach its rally")
