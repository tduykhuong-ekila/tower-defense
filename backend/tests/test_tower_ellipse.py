"""Tower shots use the same physical circle projected as the UI ellipse."""
import math

import pytest

from apps.combat.continuous import ContinuousEngine, candidates, entity_index
from apps.combat.engine import CombatState
from apps.combat.map import get_game_map
from apps.combat.targeting import find_tower_target


@pytest.mark.parametrize("code", ["infantry", "tank", "artillery"])
@pytest.mark.parametrize("grid", [False, True])
@pytest.mark.parametrize("angle", [0, math.pi / 4, math.pi / 2, math.pi])
def test_tower_only_acquires_units_inside_displayed_ellipse(code, grid, angle):
    graph = get_game_map(2, 5)
    node_id = "node_tower_t1_slot1"
    node = graph.nodes[node_id]
    tower = dict(id="tower", team_id="a", entity_kind="TOWER", status="ACTIVE",
                 current_hp=150, range=2, current_node_id=node_id, simulation_state={})
    if grid:
        tower["simulation_state"] = {"grid_placement": {"row": 1, "col": 1},
                                     "world_position": {"x": node.x + 200, "y": node.y}}
    x = tower["simulation_state"].get("world_position", {}).get("x", node.x)
    unit = dict(id="unit", team_id="b", entity_kind="UNIT", unit_type_code=code,
                status="ACTIVE", current_hp=80, current_node_id=node_id, simulation_state={})
    # Sharing the tower's graph node must never admit a physically distant unit.
    for radius, eligible in [(160.01, False), (159.99, True), (160.01, False)]:
        unit["simulation_state"]["world_position"] = {
            "x": x + radius * math.cos(angle), "y": node.y + radius * math.sin(angle)}
        assert bool(candidates(tower, entity_index([unit]), graph, ["UNIT"])) == eligible
        assert (find_tower_target(tower, [unit], graph, graph.get_base_node(1)) is unit) == eligible


def test_tower_range_uses_progress_between_nodes():
    graph = get_game_map(2, 5)
    start, end = "node_lane_t1_1", "node_lane_t1_2"
    a, b = graph.nodes[start], graph.nodes[end]
    tower = dict(id="tower", team_id="a", entity_kind="TOWER", status="ACTIVE",
                 current_hp=150, range=.1, current_node_id=start, simulation_state={
                     "grid_placement": {"row": 1, "col": 1},
                     "world_position": {"x": (a.x+b.x)/2, "y": (a.y+b.y)/2}})
    unit = dict(id="unit", team_id="b", entity_kind="UNIT", status="ACTIVE",
                current_hp=80, current_node_id=start,
                simulation_state={"next_node_id": end, "edge_progress": .5})
    assert candidates(tower, entity_index([unit]), graph, ["UNIT"]) == [unit]
    unit["simulation_state"]["edge_progress"] = 0
    assert not candidates(tower, entity_index([unit]), graph, ["UNIT"])


@pytest.mark.parametrize("grid", [False, True])
def test_realtime_tower_starts_and_stops_firing_at_ellipse_boundary(grid):
    graph = get_game_map(2, 5)
    node_id = "node_tower_t1_slot1"
    node = graph.nodes[node_id]
    tower = dict(id="tower", team_id="a", entity_kind="TOWER", status="ACTIVE",
                 current_hp=150, range=2, damage=20, level=1,
                 current_node_id=node_id, simulation_state={})
    if grid:
        tower["simulation_state"]["grid_placement"] = {"row": 1, "col": 1}
    unit = dict(id="unit", team_id="b", entity_kind="UNIT", unit_type_code="tank",
                status="ACTIVE", current_hp=80, level=1, damage=0, range=0,
                current_node_id="node_lane_t1_2", simulation_state={"order": "AT_RALLY"})
    state = CombatState(1, False, {
        "a": {"team_index": 1, "status": "ACTIVE", "base_hp": 500},
        "b": {"team_index": 2, "status": "ACTIVE", "base_hp": 500},
    }, [tower, unit], [], {"arena_layout_version": 5})
    for radius, fires in [(161, False), (159, True), (161, False)]:
        unit["simulation_state"]["world_position"] = {"x": node.x + radius, "y": node.y}
        result = ContinuousEngine.step(state, 0)
        assert any(e["type"] == "TOWER_ATTACKED" for e in result.events) == fires
        result_tower = next(e for e in result.new_state.entities if e["id"] == "tower")
        assert result_tower["simulation_state"]["combat_state"] == ("ATTACKING" if fires else "IDLE")


@pytest.mark.parametrize("code", ["infantry", "tank", "artillery"])
@pytest.mark.parametrize("tower_range", [1, 2, 3, 4])
@pytest.mark.parametrize("grid", [False, True])
def test_troops_enter_tower_ellipse_before_they_can_fire(code, tower_range, grid):
    graph = get_game_map(3, 5)
    node_id = "node_tower_t1_slot1"
    node = graph.nodes[node_id]
    defense = dict(id="tower", team_id="a", entity_kind="TOWER", status="ACTIVE",
                   current_hp=150, range=tower_range, current_node_id=node_id, simulation_state={})
    if grid:
        defense["simulation_state"]["grid_placement"] = {"row": 1, "col": 1}
    unit = dict(id="unit", team_id="b", entity_kind="UNIT", unit_type_code=code,
                status="ACTIVE", current_hp=80, range=10, current_node_id=node_id,
                simulation_state={})
    from apps.combat.targeting import find_unit_target
    inner_fraction = min(.9, 200 / (tower_range * 80)) * .99
    for fraction, troop_fires, tower_fires in [(1.01, False, False), (.95, False, True), (inner_fraction, True, True)]:
        unit["simulation_state"]["world_position"] = {
            "x": node.x + tower_range * 80 * fraction, "y": node.y}
        index = entity_index([unit, defense])
        assert bool(candidates(unit, index, graph, ["TOWER"])) == troop_fires
        assert (find_unit_target(unit, [defense], graph) is defense) == troop_fires
        assert bool(candidates(defense, index, graph, ["UNIT"])) == tower_fires
