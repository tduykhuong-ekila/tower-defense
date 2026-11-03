"""Exact roadside masks reserve actual mobile bodies, rather than cell circumcircles."""
import json
import math
from pathlib import Path

import pytest

from apps.combat.build_geometry import (
    segment_intersects_rect,
    segment_rect_distance,
)
from apps.combat.formation import SPRITE_BODIES
from apps.combat.map import get_game_map
from apps.combat.mobile import crowd_offset
from apps.combat.navigation import project, staging_bounds, staging_slots
from apps.units.placement import (
    CELL_SIZE,
    FOOTPRINTS,
    MOVEMENT_ENVELOPE,
    PAINTED_ROAD_HALF_WIDTH,
    PLACEMENT_MOVEMENT_ENVELOPE,
    STAGING_BODY_ENVELOPE,
    STAGING_SAFETY_MARGIN,
    movement_cell_blocked,
    painted_cell_blocked,
    placement_grid,
    road_cell_blocked,
)
from tests.test_grid_placement import valid_cells


def test_exact_distance_crossings_corners_parallel_tangencies_and_degenerate_segments():
    rect = (0, 0, 32, 32)
    assert segment_rect_distance((-5, 16), (40, 16), rect) == 0
    assert segment_rect_distance((-5, -4), (-3, -4), rect) == 5
    assert segment_rect_distance((4, 35), (20, 35), rect) == 3
    assert segment_rect_distance((0, 32), (32, 32), rect) == 0
    assert segment_rect_distance((16, 16), (16, 16), rect) == 0
    assert segment_rect_distance((32, 40), (32, 40), rect) == 8
    assert segment_intersects_rect((-1, -1), (0, 0), rect)


def test_protected_corridor_covers_every_standard_body_and_crowd_slot():
    assert MOVEMENT_ENVELOPE == pytest.approx((-71, -68, 71, 15))
    for order in range(1, 16):
        offset = crowd_offset(order)
        x, oy = project((offset['x'], offset['y']))
        for w, h, y in SPRITE_BODIES.values():
            body = (x-w/2, oy+y-h/2, x+w/2, oy+y+h/2)
            assert all(a <= b + 1e-8 for a, b in zip(MOVEMENT_ENVELOPE[:2], body[:2]))
            assert all(a >= b - 1e-8 for a, b in zip(MOVEMENT_ENVELOPE[2:], body[2:]))
            assert road_cell_blocked(body, (-100, 0), (100, 0))
    assert movement_cell_blocked((20, 15, 52, 60), (-100, 0), (100, 0))
    assert not movement_cell_blocked((20, 16, 52, 60), (-100, 0), (100, 0))
    assert painted_cell_blocked((20, 28, 52, 60), (-100, 0), (100, 0), half_width=PAINTED_ROAD_HALF_WIDTH)
    assert painted_cell_blocked((20, 29, 52, 61), (-100, 0), (100, 0), half_width=PAINTED_ROAD_HALF_WIDTH)
    assert road_cell_blocked((20, -100, 52, -67), (-100, 0), (100, 0))


@pytest.mark.parametrize('count', [2, 4, 8, 20])
def test_nearest_roadside_footprints_clear_the_widened_road_and_troop_corridor(count):
    grid = placement_grid(get_game_map(count, 6))
    valid = list(valid_cells(grid))
    assert valid, (count, 'no safe tower footprints')
    closest = math.inf
    for row, col in valid:
        rect = (col*32-grid.offset[0], row*32-grid.offset[1], (col+3)*32-grid.offset[0], (row+3)*32-grid.offset[1])
        closest = min(closest, *(segment_rect_distance(a, b, rect)-grid.painted_half_width for a, b in grid.roads))
        assert not any(movement_cell_blocked(rect, a, b, PLACEMENT_MOVEMENT_ENVELOPE)
                       for a, b in grid.movement_roads)
        assert not any(painted_cell_blocked(rect, a, b, grid.curve_tolerance, grid.painted_half_width) for a, b in grid.roads)
        grid.validate(row, col, 'cannon_tower', 1, [])
    assert 0 <= closest < CELL_SIZE, (count, closest)


@pytest.mark.parametrize('count', [2, 4, 8, 20])
def test_new_rally_pockets_clear_every_unchanged_staging_approach(count):
    graph = get_game_map(count, 6)
    grid = placement_grid(graph)
    old_rallies = []
    approaches = []
    for team in range(1, count + 1):
        spawn_id = graph.get_spawn_node(team)
        spawn = graph.nodes[spawn_id]
        center = project((spawn.x, spawn.y))
        polygon = [project(p) for p in staging_bounds(graph, spawn_id)]
        old_rallies.append((min(p[0] for p in polygon), min(p[1] for p in polygon),
                            max(p[0] for p in polygon), max(p[1] for p in polygon)))
        for slot in staging_slots(graph, spawn_id):
            start = project(slot)
            for order in range(1, 16):
                offset = crowd_offset(order)
                shift = project((offset['x'], offset['y']))
                approaches.append((start, (center[0] + shift[0], center[1] + shift[1])))
    reopened = []
    for row, col in valid_cells(grid):
        rect = (col*CELL_SIZE-grid.offset[0], row*CELL_SIZE-grid.offset[1],
                (col+3)*CELL_SIZE-grid.offset[0], (row+3)*CELL_SIZE-grid.offset[1])
        if any(rect[0] < old[2]+4 and rect[2] > old[0]-4 and
               rect[1] < old[3]+4 and rect[3] > old[1]-4 for old in old_rallies):
            reopened.append((row, col, rect))
    assert reopened, (count, 'no new buildable staging-side footprint')
    for row, col, rect in reopened:
        assert not any(movement_cell_blocked(rect, a, b, STAGING_BODY_ENVELOPE,
                                             STAGING_SAFETY_MARGIN) for a, b in approaches)
        assert not any(movement_cell_blocked(rect, a, b, PLACEMENT_MOVEMENT_ENVELOPE)
                       for a, b in grid.movement_roads)
        assert not any(painted_cell_blocked(rect, a, b, grid.curve_tolerance) for a, b in grid.roads)
        grid.validate(row, col, 'cannon_tower', 1, [])


def export_fixtures(path):
    """Regenerate server-authored mask samples consumed by frontend parity tests."""
    fixtures = []
    for count in [2, 4, 8, 20]:
        graph = get_game_map(count, 6)
        grid = placement_grid(graph)
        valid = list(valid_cells(grid))
        near = []
        for r,c in valid:
            rect = (c*CELL_SIZE-grid.offset[0], r*CELL_SIZE-grid.offset[1],
                    (c+3)*CELL_SIZE-grid.offset[0], (r+3)*CELL_SIZE-grid.offset[1])
            gap = min(segment_rect_distance(a,b,rect)-grid.painted_half_width for a,b in grid.roads)
            if gap < 64:
                near.append((r,c,gap))
        near.sort(key=lambda item: item[2])
        sample = valid[::max(1, len(valid)//20)] + [(r,c) for r,c,_ in near[:20]]
        data = graph.to_dict([f'team-{i}' for i in range(1, count+1)])
        data['placement_grid'] = grid.metadata()
        fixtures.append({'map':data,'valid':[{'row':r,'col':c} for r,c in sample],
                         'nearRoadsideCount':len(near),'nearRoadside':[{'row':r,'col':c} for r,c,_ in near[:20]]})
    Path(path).write_text(json.dumps(fixtures, ensure_ascii=False))
