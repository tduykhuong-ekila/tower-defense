"""Route changes preserve real position, speed and staging admission."""
import copy

import pytest

from apps.combat.continuous import ContinuousEngine
from apps.combat.formation import (
    initialize_route,
    physical_position,
    redirect_route,
    synchronize_position,
)
from apps.combat.map import get_game_map
from tests.test_live_battle_gameplay import convoy


@pytest.mark.parametrize("code", ["infantry", "tank", "artillery"])
@pytest.mark.parametrize("progress", [0, 20, 150])
def test_extending_base_approach_preserves_progress_position_speed_and_staging(code, progress):
    state = convoy((code,))
    unit = state.entities[0]
    graph = get_game_map(2)
    sim = unit["simulation_state"]
    if progress:
        sim.update(route_distance=progress, movement_zone="ROUTE")
        sim.pop("world_position", None)
        synchronize_position(unit, graph)
    before = copy.deepcopy(sim)
    point = physical_position(unit, graph)
    initialize_route(unit, "node_base_t2", graph, approach_base=True)
    assert sim["route_distance"] == before["route_distance"]
    assert sim["reference_hop_length"] == before["reference_hop_length"]
    assert sim["movement_zone"] == before["movement_zone"]
    assert sim.get("staging_entry_distance") == before.get("staging_entry_distance")
    assert physical_position(unit, graph) == point
    assert sim["route_nodes"][:-1] == before["route_nodes"]
    assert sim["route_nodes"][-1] == "node_base_t2"
    # Repeating the derived route update after a reload must be a no-op.
    ready = copy.deepcopy(sim)
    initialize_route(unit, "node_base_t2", graph, approach_base=True)
    assert sim == ready


@pytest.mark.parametrize("code", ["infantry", "tank", "artillery"])
def test_zero_speed_troop_keeps_position_and_progress_during_base_route_extension(code):
    state = convoy((code,))
    unit = state.entities[0]
    graph = get_game_map(2)
    point = physical_position(unit, graph)
    unit["movement"] = 0
    for _ in range(5):
        state = ContinuousEngine.step(state, .2).new_state
        assert physical_position(state.entities[0], graph) == point
        assert state.entities[0]["simulation_state"]["route_distance"] == 0


@pytest.mark.parametrize("fraction", [0, 1])
def test_redirect_at_edge_endpoint_has_no_phantom_completed_edge(fraction):
    unit = convoy(("infantry",)).entities[0]
    graph = get_game_map(2)
    node, next_node = unit["current_node_id"], unit["simulation_state"]["next_node_id"]
    endpoint = graph.nodes[next_node if fraction else node]
    unit["simulation_state"].update(edge_progress=fraction,
        world_position={"x": endpoint.x, "y": endpoint.y})
    assert redirect_route(unit, "node_lane_t2_1", graph)
    assert unit["current_node_id"] == endpoint.node_id
    assert unit["simulation_state"]["route_distance"] == 0
    assert physical_position(unit, graph) == (endpoint.x, endpoint.y)
    route = unit["simulation_state"]["route_nodes"]
    assert len(route) == len(set(route))
