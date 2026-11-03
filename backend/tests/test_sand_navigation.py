"""Troops minimize road distance and keep ground anchors inside yellow sand."""
import math

import pytest

from apps.combat.build_geometry import movement_segments, segment_distance
from apps.combat.continuous import ContinuousEngine
from apps.combat.formation import physical_position, redirect_route
from apps.combat.map import GameMap, MapNode, get_game_map
from apps.combat.navigation import project
from tests.test_continuous_combat import pure_state
from tests.test_spawn_tower_realtime import tower


def test_shortest_route_uses_length_instead_of_hops_and_excludes_grass():
    graph = GameMap(2)
    graph.nodes = {name: MapNode(name, 'lane', x=x, y=y, is_passable=passable)
                   for name, x, y, passable in [
                       ('a', 0, 0, True), ('b', 50, 100, True),
                       ('c', 1, 0, True), ('d', 2, 0, True), ('z', 3, 0, True),
                       ('grass', 1.5, 0, False)]}
    graph.adjacency = {name: set() for name in graph.nodes}
    for a, b in [('a', 'b'), ('b', 'z'), ('a', 'c'), ('c', 'd'), ('d', 'z'),
                 ('a', 'grass'), ('grass', 'z')]:
        graph._add_edge(a, b)
    graph._predefined_paths.clear()
    graph._precompute_graph()
    assert graph.path('a', 'z') == ['a', 'c', 'd', 'z']
    assert graph.shortest_physical_path('a', 'z') == graph.path('a', 'z')
    assert graph.distance('a', 'z') == 2  # Weapon ranges still use graph hops.
    assert not graph.path('a', 'grass')
    assert not graph.path('grass', 'grass')


def assert_sand(point, roads):
    assert min(segment_distance(project(point), a, b) for a, b in roads) <= 12.00001


@pytest.mark.parametrize('count,version', [(2, 6), (3, 6), (4, 6), (8, 6), (20, 6), (5, 7)])
@pytest.mark.parametrize('code', ['infantry', 'tank', 'artillery'])
def test_fast_movement_and_retreat_keep_every_trail_segment_on_sand(count, version, code):
    state = pure_state(code, config={'arena_layout_version': version,
                                    'movement_baseline_round_seconds': 1})
    for index in range(3, count + 1):
        state.teams[str(index)] = {'team_index': index, 'status': 'ACTIVE', 'base_hp': 500}
    graph = get_game_map(count, version)
    roads = list(movement_segments(graph))
    for tick in range(15):
        state = ContinuousEngine.step(state, 1).new_state
        unit = state.entities[0]
        assert_sand(physical_position(unit, graph), roads)
        trail = unit['simulation_state'].get('movement_path', [])
        for a, b in zip(trail, trail[1:]):
            for step in range(11):
                t = step / 10
                assert_sand((a['x'] * (1-t) + b['x'] * t,
                             a['y'] * (1-t) + b['y'] * t), roads)
        if tick == 5:
            rally = graph.get_spawn_node(1)
            assert redirect_route(unit, rally, graph)
            unit['simulation_state'].update(order='RETREAT', destination_rally_id=rally)


@pytest.mark.parametrize('offset', [60, 10000])
def test_siege_stops_on_road_even_when_tower_is_beyond_weapon_range(offset):
    state = pure_state(node='node_lane_t2_2', config={'arena_layout_version': 6,
                       'movement_baseline_round_seconds': 1})
    graph = get_game_map(2, 6)
    a, b = (graph.nodes[n] for n in ['node_lane_t2_2', 'node_lane_t2_3'])
    dx, dy = b.x-a.x, b.y-a.y
    length = math.hypot(dx, dy)
    state.entities.append(tower(node=a.node_id, current_hp=10000,
        simulation_state={'grid_placement': {'row': 1, 'col': 1},
                          'world_position': {'x': (a.x+b.x)/2 - dy/length*offset,
                                             'y': (a.y+b.y)/2 + dx/length*offset}}))
    roads = list(movement_segments(graph))
    attacked = False
    for _ in range(80):
        result = ContinuousEngine.step(state, .2)
        state = result.new_state
        unit = state.entities[0]
        assert_sand(physical_position(unit, graph), roads)
        assert not unit['simulation_state'].get('siege_detour')
        attacked |= any(e['type'] == 'UNIT_ATTACKED' for e in result.events)
    assert attacked == (offset == 60)
