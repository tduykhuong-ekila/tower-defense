"""Troop weapon hops and road firing stops must use the same arena scale."""
import json
import math
from unittest.mock import patch

import pytest

from apps.combat.balance import movement_speed, troop_tower_firing_radius
from apps.combat.build_geometry import movement_segments
from apps.combat.continuous import ContinuousEngine, candidates, entity_index, target_distance
from apps.combat.formation import (
    initialize_route,
    physical_position,
    position_at,
    synchronize_position,
)
from apps.combat.map import get_game_map
from apps.combat.siege import plan_road_firing_position
from apps.combat.targeting import find_unit_target
from tests.test_continuous_combat import pure_state
from tests.test_sand_navigation import assert_sand
from tests.test_spawn_tower_realtime import tower


@pytest.mark.parametrize("count", [2, 3, 8, 20])
@pytest.mark.parametrize("code", ["infantry", "tank", "artillery"])
def test_scaled_troop_range_and_spatial_index_agree_at_boundary(count, code):
    graph = get_game_map(count, 7)
    unit = pure_state(code, node="node_spawn_t1").entities[0]
    node = graph.nodes[unit["current_node_id"]]
    unit["simulation_state"]["world_position"] = {"x": node.x, "y": node.y}
    # Deliberately unrelated graph anchor: the physical broad phase must find it.
    defense = tower(node="node_spawn_t2", simulation_state={"grid_placement": {"row": 1, "col": 1}})
    radius = troop_tower_firing_radius(unit, graph, defense)
    assert radius == 144  # The shorter-range test tower still caps troops at 90%.
    for gap, expected in [(radius - .01, True), (radius + .01, False)]:
        defense["simulation_state"]["world_position"] = {"x": node.x + gap, "y": node.y}
        assert (target_distance(unit, defense, graph) <= unit["range"]) == expected
        assert bool(candidates(unit, entity_index([unit, defense]), graph, ["TOWER"])) == expected
        assert (find_unit_target(unit, [defense], graph) is defense) == expected


@pytest.mark.parametrize("code", ["infantry", "tank", "artillery"])
@pytest.mark.parametrize("saved_radius", [120, 376])
def test_saved_short_range_stop_recovers_and_troop_destroys_roadside_tower(code, saved_radius):
    state = pure_state(code, node="node_lane_t2_3", config={"arena_layout_version": 7})
    state.teams["b"]["team_index"] = 3
    state.teams["c"] = {"team_index": 2, "status": "ACTIVE", "base_hp": 500}
    graph = get_game_map(3, 7)
    a, b = graph.nodes["node_lane_t3_2"], graph.nodes["node_lane_t3_1"]
    dx, dy = b.x - a.x, b.y - a.y
    length = math.hypot(dx, dy)
    defense = tower(node=a.node_id, range=3, damage=1, current_hp=10, simulation_state={
        "grid_placement": {"row": 1, "col": 1},
        "world_position": {"x": (a.x+b.x)/2 - dy/length*150,
                           "y": (a.y+b.y)/2 + dx/length*150}})
    unit = state.entities[0]
    assert troop_tower_firing_radius(unit, graph, defense) == 200
    initialize_route(unit, graph.get_base_node(3), graph)
    unit["simulation_state"]["siege_target_id"] = defense["id"]
    # A persisted old plan used the fixed 120-unit reach and stopped too far away.
    with patch("apps.combat.siege.troop_tower_firing_radius", return_value=saved_radius):
        plan_road_firing_position(unit, defense, graph)
    sim = unit["simulation_state"]
    sim.pop("siege_firing_radius")
    sim["route_distance"] = sim["siege_stop_distance"]
    synchronize_position(unit, graph)
    x, y = position_at(unit, sim["route_distance"], graph)
    sim.update(world_position={"x": x, "y": y}, movement_zone="ROUTE", crowd_offset={"x": 0, "y": 0})
    state.entities.append(defense)
    roads = list(movement_segments(graph))
    for _ in range(1500):
        before = physical_position(unit, graph)
        result = ContinuousEngine.step(state, .2)
        state = result.new_state
        unit = next(e for e in state.entities if e["id"] == "unit")
        assert math.dist(before, physical_position(unit, graph)) <= movement_speed(unit, state.configuration) * .2 + 1e-6
        assert_sand(physical_position(unit, graph), roads)
        assert not unit["simulation_state"].get("siege_detour")
        if any(e["type"] == "UNIT_ATTACKED" for e in result.events):
            assert target_distance(unit, defense, graph) <= unit["range"]
            assert math.dist(physical_position(unit, graph), physical_position(defense, graph)) < defense["range"] * 80
        if next(e for e in state.entities if e["id"] == defense["id"])["current_hp"] <= 0:
            return
        state.entities = json.loads(json.dumps(state.entities))
    pytest.fail("Troop stayed outside weapon range instead of destroying the tower")


def test_siege_extension_does_not_mutate_shared_shortest_paths():
    graph = get_game_map(3, 7)
    node_id = "node_lane_t3_1"
    route = graph.path(node_id, node_id)
    route.append("node_lane_t3_2")
    assert graph.path(node_id, node_id) == [node_id]
