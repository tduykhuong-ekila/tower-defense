"""Tight reservations, separate painted curves and swept mixed-troop routes."""
import copy
import math
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError

from apps.combat.build_geometry import segment_rect_distance
from apps.combat.formation import initialize_spawn, physical_position, redirect_route
from apps.combat.map import get_game_map
from apps.combat.mobile import move_mobile_units
from apps.combat.navigation import project
from apps.units.placement import (
    CELL_SIZE,
    FOOTPRINTS,
    MOVEMENT_ENVELOPE,
    PLACEMENT_MOVEMENT_ENVELOPE,
    movement_cell_blocked,
    painted_cell_blocked,
    placement_grid,
    road_cell_blocked,
)
from tests.test_continuous_combat import pure_state
from tests.test_grid_placement import shield_range_cells, valid_cells


def previous_road_mask(grid):
    result = set()
    for a, b in grid.roads:
        for r in range(max(0, math.floor((min(a[1], b[1])-73+grid.offset[1])/32)),
                       min(grid.rows, math.ceil((max(a[1], b[1])+73+grid.offset[1])/32))):
            for c in range(max(0, math.floor((min(a[0], b[0])-73+grid.offset[0])/32)),
                           min(grid.cols, math.ceil((max(a[0], b[0])+73+grid.offset[0])/32))):
                if (r, c) not in result and road_cell_blocked(
                        projected_rect(grid, r, c, 1), a, b, grid.curve_tolerance, 28.5):
                    result.add((r, c))
    return result


def projected_rect(grid, row, col, size=3):
    return (col*32-grid.offset[0], row*32-grid.offset[1],
            (col+size)*32-grid.offset[0], (row+size)*32-grid.offset[1])


@pytest.mark.parametrize('count', [2, 4, 8, 20])
def test_refinement_uses_the_reduced_placement_envelope(count):
    grid = placement_grid(get_game_map(count, 6))
    old_roads = previous_road_mask(grid)
    added = []
    for r, c in valid_cells(grid):
        # Previous 128px reservation at this grid origin or old curve exclusion.
        old_invalid = r+4 > grid.rows or c+4 > grid.cols or any(
            grid.owners[y*grid.cols+x] != 1 or (y, x) in old_roads
            for y in range(r, min(r+4, grid.rows)) for x in range(c, min(c+4, grid.cols)))
        if old_invalid:
            added.append((r, c))
    assert added
    assert MOVEMENT_ENVELOPE == pytest.approx((-71, -68, 71, 15))
    assert PLACEMENT_MOVEMENT_ENVELOPE == pytest.approx((-46, -68, 46, 15))
    closest = math.inf
    for r, c in added:
        rect = projected_rect(grid, r, c)
        assert not any(movement_cell_blocked(rect, a, b, PLACEMENT_MOVEMENT_ENVELOPE)
                       for a, b in grid.movement_roads)
        assert not any(painted_cell_blocked(rect, a, b, grid.curve_tolerance,
                                            grid.painted_half_width) for a, b in grid.roads)
        closest = min(closest, *(segment_rect_distance(a, b, rect)-grid.painted_half_width for a, b in grid.roads))
        grid.validate(r, c, 'cannon_tower', 1, [])
    assert closest < CELL_SIZE, (count, closest)


def test_new_footprint_contains_complete_texture_and_keeps_old_reservations():
    grid = placement_grid(get_game_map(2, 6))
    f = FOOTPRINTS['cannon_tower']
    r, c = next((r, c) for r, c in valid_cells(grid) if all(
        grid.owners[y*grid.cols+x] == 1 for y in range(r, r+6) for x in range(c, c+6)))
    anchor = grid.anchor(r, c, f)
    rect = grid.rectangle(r, c, f)
    assert rect[0] <= anchor[0]-47 < anchor[0]+47 <= rect[2]
    assert rect[1] <= anchor[1]-94*.89 < anchor[1]+94*.11 <= rect[3]
    saved = {'row': r, 'col': c, 'widthCells': 4, 'heightCells': 4, 'anchorOffsetY': 32}
    entity = SimpleNamespace(simulation_state={'grid_placement': saved}, current_node_id='')
    with pytest.raises(ValidationError, match='OCCUPIED'):
        grid.validate(r+3, c, 'mg_tower', 1, [entity])
    grid.validate(r+4, c, 'mg_tower', 1, [entity])
    assert entity.simulation_state['grid_placement'] == saved
    assert grid.anchor(r, c, saved) == (c*32+64, r*32+96)


@pytest.mark.parametrize('count', [2, 4, 8, 20])
def test_new_grid_troops_keep_moving_when_placement_corridor_is_reduced(count):
    graph = get_game_map(count, 6)
    grid = placement_grid(graph)
    units = []
    config = {'tower_placement_version': 1, 'movement_baseline_round_seconds': 1}
    for order, code in enumerate(['infantry', 'tank', 'artillery']*3, 1):
        unit = copy.deepcopy(pure_state(code).entities[0])
        unit.update(id=str(order), current_node_id=graph.get_spawn_node(1), simulation_state={})
        initialize_spawn(unit, units, graph.get_base_node(2), graph, order, config)
        units.append(unit)
    traveled = {u['id']: 0.0 for u in units}
    for tick in range(160):
        if tick in (25, 70):
            for unit in units:
                destination = graph.attack_position(graph.get_base_node(count)) if tick == 25 else graph.get_spawn_node(1)
                assert redirect_route(unit, destination, graph)
        starts = {u['id']: physical_position(u, graph) for u in units}
        move_mobile_units(units, graph, config, .2, set())
        for unit in units:
            start, end = starts[unit['id']], physical_position(unit, graph)
            traveled[unit['id']] += math.dist(start, end)
    assert all(d > 200 for d in traveled.values())
    assert all(u['current_node_id'] == graph.get_spawn_node(1) for u in units)


@pytest.mark.parametrize('count', range(2, 21))
def test_every_supported_team_count_retains_owned_builds_and_routes(count):
    graph = get_game_map(count, 6)
    grid = placement_grid(graph)
    for owner in range(1, count+1):
        row, col = next(valid_cells(grid, owner))
        for code in FOOTPRINTS:
            if code == 'shield_generator':
                near, far = shield_range_cells(grid, owner)
                assert near and far, (count, owner)
                grid.validate(*near, code, owner, [])
                with pytest.raises(ValidationError) as error:
                    grid.validate(*far, code, owner, [])
                assert error.value.code == 'PLACEMENT_SHIELD_RANGE'
            else:
                grid.validate(row, col, code, owner, [])
        assert graph.get_path_to_base(graph.get_spawn_node(owner), owner % count+1)
    assert grid.metadata()['geometryRevision'] == 11


def test_saved_vehicle_parking_offsets_protect_future_routes_without_relocating():
    from apps.combat.navigation import unproject
    graph = get_game_map(2, 6)
    grid = placement_grid(graph)
    row, col = next(valid_cells(grid))
    rect = projected_rect(grid, row, col)
    a, b = grid.movement_roads[0]
    offset = unproject(((rect[0]+rect[2]-a[0]-b[0])/2,
                        (rect[1]+rect[3]-a[1]-b[1])/2+27))
    state = {'crowd_offset': {'x': offset[0], 'y': offset[1]}}
    unit = SimpleNamespace(entity_kind='UNIT', unit_type=SimpleNamespace(code='tank'),
                           simulation_state=state, current_node_id=graph.get_spawn_node(1))
    with pytest.raises(ValidationError) as error:
        grid.validate(row, col, 'cannon_tower', 1, [unit])
    assert error.value.code == 'PLACEMENT_ROAD'
    assert unit.simulation_state == state
    # Normal bodies remain completely covered by the shared static mask.
    from apps.combat.mobile import crowd_offset
    unit.simulation_state = {'crowd_offset': crowd_offset(1)}
    grid.validate(row, col, 'cannon_tower', 1, [unit])


def test_saved_staging_approach_blocks_a_new_tower_at_its_physical_position():
    from apps.combat.navigation import unproject
    graph = get_game_map(2, 6)
    grid = placement_grid(graph)
    row, col = next(valid_cells(grid))
    rect = projected_rect(grid, row, col)
    x, y = unproject(((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2))
    spawn_id = graph.get_spawn_node(1)
    state = {'movement_zone': 'STAGING', 'world_position': {'x': x, 'y': y},
             'route_nodes': graph.path(spawn_id, 'node_center'),
             'staging_entry_distance': 80, 'crowd_offset': {'x': 0, 'y': 0}}
    unit = SimpleNamespace(entity_kind='UNIT', unit_type=SimpleNamespace(code='infantry'),
                           simulation_state=state, current_node_id=spawn_id)
    with pytest.raises(ValidationError) as error:
        grid.validate(row, col, 'cannon_tower', 1, [unit])
    assert error.value.code == 'PLACEMENT_RALLY'
    assert unit.simulation_state == state
