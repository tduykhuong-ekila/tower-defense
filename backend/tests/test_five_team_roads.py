"""Five-team sand roads have equal projected lengths and evenly spaced sectors."""
import math

import pytest

from apps.combat.build_geometry import (
    segment_distance,
)
from apps.combat.map import GameMap
from apps.combat.navigation import project, staging_bounds, unproject
from apps.units.placement import placement_grid


def test_five_team_roads_have_equal_projected_bands_and_sectors():
    graph = GameMap(5, 7)
    for pattern in ('node_base_t{}', 'node_lane_t{}_1', 'node_lane_t{}_2',
                    'node_lane_t{}_3', 'node_center_ring_t{}', 'node_spawn_t{}'):
        points = [project((graph.nodes[pattern.format(i)].x, graph.nodes[pattern.format(i)].y))
                  for i in range(1, 6)]
        assert [math.hypot(*p) for p in points] == pytest.approx([math.hypot(*points[0])] * 5)
        angles = [math.atan2(y, x) for x, y in points]
        gaps = [(angles[(i + 1) % 5] - angles[i]) % (2 * math.pi) for i in range(5)]
        assert gaps == pytest.approx([2 * math.pi / 5] * 5)
    # Every corresponding road, including the spawn spur and center ring, is equal.
    lengths = {}
    for u, neighbors in graph.adjacency.items():
        for v in neighbors:
            a, b = graph.nodes[u], graph.nodes[v]
            if u >= v or not a.is_passable or not b.is_passable:
                continue
            kind = tuple(sorted((a.node_type, b.node_type)))
            if kind == ('center', 'center'):
                kind += ('hub' if 'node_center' in (u, v) else 'ring',)
            lengths.setdefault(kind, []).append(math.dist(project((a.x, a.y)), project((b.x, b.y))))
    for band in lengths.values():
        assert band == pytest.approx([band[0]] * len(band))
    assert graph.validate_map() == (True, [])


def test_five_team_build_grid_and_rally_areas_fit_the_arena():
    graph = GameMap(5, 7)
    grid = placement_grid(graph)
    assert grid.geometry_revision == 17
    for team in range(1, 6):
        assert sum(owner == team for owner in grid.owners) >= 6 * 16
        for x, y in staging_bounds(graph, graph.get_spawn_node(team)):
            x, y = project((x, y))
            assert 0 < x + grid.offset[0] < grid.width
            assert 0 < y + grid.offset[1] < grid.height
        for enemy in range(1, 6):
            if team != enemy:
                assert graph.get_path_to_base(graph.get_spawn_node(team), enemy)


def test_legacy_five_team_geometry_is_unchanged():
    graph = GameMap(5, 6)
    for node in graph.nodes.values():
        if node.node_type == 'base':
            assert math.hypot(node.x, node.y) == pytest.approx(400 * graph.layout_scale)
    assert placement_grid(graph).geometry_revision == 11


def test_five_team_river_banks_clear_the_entire_building_territory():
    graph = GameMap(5, 7)
    grid = placement_grid(graph)
    path = grid.metadata()["riverPath"]
    assert all(a[1] < b[1] for a, b in zip(path, path[1:]))
    assert path[0][1] < 0 and path[-1][1] > grid.height
    assert path[0][0] == path[1][0]
    assert path[-1][0] == path[-2][0]
    # Keep the river visible within the client's padded scenery.
    right = grid.width + round(max(320, grid.width * 0.12))
    assert all(grid.width / 2 <= x < right - 48 for x, y in path)

    # Test whole segments, not only control points. Inverse projection gives
    # the exact circular outer boundary used by PlacementGrid.classify.
    local_path = [unproject((x - grid.offset[0], y - grid.offset[1])) for x, y in path]
    clearance = min(segment_distance((0, 0), a, b) for a, b in zip(local_path, local_path[1:]))
    # 48px banks expand by at most 48/.86 map units. This larger gap also
    # protects tower artwork extending beyond the outermost buildable cells.
    assert clearance > 420 * graph.layout_scale + 100
    assert grid.river_cells  # Water still has an authoritative collision mask.
    assert "WATER" not in grid.reasons  # No eligible building cell is lost to it.
    assert not grid.river_cells & grid.rally_cells
    for team in range(1, 6):
        assert grid.owners.count(team) > 0
