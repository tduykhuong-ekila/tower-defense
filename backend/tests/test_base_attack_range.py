"""Base damage requires a real 200-unit distance, including restored troops."""
import json
import math

import pytest

from apps.combat.balance import movement_speed
from apps.combat.continuous import ContinuousEngine, base_in_range
from apps.combat.formation import physical_position
from apps.combat.map import get_game_map
from tests.test_continuous_combat import pure_state
from tests.test_spawn_tower_realtime import tower


@pytest.mark.parametrize("code", ["infantry", "tank", "artillery"])
@pytest.mark.parametrize("gap,eligible", [(200.01, False), (200, True), (199.99, True)])
def test_base_damage_checks_physical_distance_even_at_old_attack_node(code, gap, eligible):
    state = pure_state(code, node="node_lane_t2_1", config={"arena_layout_version": 7})
    graph = get_game_map(2, 7)
    base = graph.nodes[graph.get_base_node(2)]
    unit = state.entities[0]
    unit["simulation_state"]["world_position"] = {"x": base.x + gap, "y": base.y}
    result = ContinuousEngine.step(state, 0)
    assert any(e["type"] == "BASE_DAMAGED" for e in result.events) == eligible
    assert (result.new_state.teams["b"]["base_hp"] < 500) == eligible


@pytest.mark.parametrize("count", [2, 3, 8, 20])
@pytest.mark.parametrize("code", ["infantry", "tank", "artillery"])
def test_old_base_attack_stop_advances_into_range_without_teleporting(count, code):
    state = pure_state(code, node="node_lane_t2_1", config={"arena_layout_version": 7})
    for i in range(3, count + 1):
        state.teams[str(i)] = {"team_index": i, "status": "ACTIVE", "base_hp": 500}
    graph = get_game_map(count, 7)
    base_id = graph.get_base_node(2)
    unit = state.entities[0]
    unit["simulation_state"].update(route_nodes=[unit["current_node_id"]],
                                    route_distance=0, route_policy_version=1)
    assert not base_in_range(unit, base_id, graph)
    for _ in range(500):
        before = physical_position(unit, graph)
        result = ContinuousEngine.step(state, .2)
        state = result.new_state
        unit = state.entities[0]
        assert math.dist(before, physical_position(unit, graph)) <= movement_speed(unit, state.configuration) * .2 + 1e-6
        if any(e["type"] == "BASE_DAMAGED" for e in result.events):
            assert base_in_range(unit, base_id, graph)
            base = graph.nodes[base_id]
            assert 170 <= math.dist(physical_position(unit, graph), (base.x, base.y)) <= 200
            # Once firing, the troop holds its position while its cooldown runs.
            after = ContinuousEngine.step(state, .2).new_state.entities[0]
            assert physical_position(after, graph) == physical_position(unit, graph)
            return
        assert state.teams["b"]["base_hp"] == 500
        state.entities = json.loads(json.dumps(state.entities))
    pytest.fail("Restored troop did not advance from the old lane stop into base range")


@pytest.mark.parametrize("code", ["infantry", "tank", "artillery"])
def test_surviving_defenses_still_block_base_damage_inside_range(code):
    state = pure_state(code, node="node_lane_t2_1", config={"arena_layout_version": 7})
    graph = get_game_map(2, 7)
    base = graph.nodes[graph.get_base_node(2)]
    state.entities[0]["simulation_state"]["world_position"] = {"x": base.x + 150, "y": base.y}
    state.entities.append(tower(node="node_lane_t2_2", simulation_state={
        "grid_placement": {"row": 1, "col": 1},
        "world_position": {"x": base.x + 500, "y": base.y}}))
    assert not any(e["type"] == "BASE_DAMAGED" for e in ContinuousEngine.step(state, 0).events)


@pytest.mark.parametrize("gap,eligible", [(201, False), (199, True)])
def test_legacy_round_engine_also_rejects_base_shots_outside_range(gap, eligible):
    from apps.combat.engine import CombatEngine

    state = pure_state(node="node_lane_t2_1", config={"arena_layout_version": 7})
    graph = get_game_map(2, 7)
    base = graph.nodes[graph.get_base_node(2)]
    unit = state.entities[0]
    unit["movement"] = 0
    unit["simulation_state"]["world_position"] = {"x": base.x + gap, "y": base.y}
    result = CombatEngine.resolve_round(state)
    assert any(e["type"] == "BASE_DAMAGED" for e in result.events) == eligible
