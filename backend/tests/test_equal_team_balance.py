"""Six- and seven-team arenas have equal roads and usable construction space."""
import math
from collections import defaultdict

import pytest
from django.core.exceptions import ValidationError

from apps.combat.map import GameMap
from apps.combat.navigation import project, staging_bounds
from apps.combat.road_shape import natural_road, road_shape_key
from apps.units.placement import placement_grid


@pytest.fixture(scope="module", params=[6, 7])
def arena(request):
    graph = GameMap(request.param, 7)
    return graph, placement_grid(graph)


def test_corresponding_roads_have_equal_painted_lengths(arena):
    graph, grid = arena
    count = graph.num_teams
    lengths = defaultdict(list)
    for u, neighbors in graph.adjacency.items():
        for v in neighbors:
            if u >= v or not graph.nodes[u].is_passable or not graph.nodes[v].is_passable:
                continue
            a, b = (project((graph.nodes[n].x, graph.nodes[n].y)) for n in (u, v))
            key = road_shape_key(graph, f"{u}:{v}")
            points = natural_road(a, b, key, grid.painted_road_widths[2])
            lengths[key].append(sum(math.dist(p, q) for p, q in zip(points, points[1:])))
    for band in lengths.values():
        assert len(band) == count
        assert band == pytest.approx([band[0]] * count)
    bases = [project((graph.nodes[graph.get_base_node(t)].x,
                      graph.nodes[graph.get_base_node(t)].y)) for t in range(1, count + 1)]
    angles = [math.atan2(y, x) for x, y in bases]
    assert [(angles[(i + 1) % count] - angles[i]) % (2 * math.pi) for i in range(count)] == pytest.approx([2 * math.pi / count] * count)


def test_equal_land_and_server_validated_tower_and_shield_opportunities(arena):
    graph, grid = arena
    counts = []
    for team in range(1, graph.num_teams + 1):
        tower_count = shield_count = 0
        for row in range(grid.rows - 2):
            for col in range(grid.cols - 2):
                if not all(grid.owners[(row + dr) * grid.cols + col + dc] == team
                           for dr in range(3) for dc in range(3)):
                    continue
                # Exercise the actual construction validator, including the
                # restricted shield ellipse, rather than just counting cells.
                for code in ("mg_tower", "cannon_tower"):
                    grid.validate(row, col, code, team, [])
                tower_count += 1
                try:
                    grid.validate(row, col, "shield_generator", team, [])
                    shield_count += 1
                except ValidationError as error:
                    assert error.code == "PLACEMENT_SHIELD_RANGE"
        counts.append((grid.owners.count(team), tower_count, shield_count))
    assert counts == [counts[0]] * graph.num_teams
    assert counts[0][0] >= 600
    assert counts[0][1] >= 400
    assert counts[0][2] >= 40


def test_balancing_preserves_exclusions_routes_and_serialized_mask(arena):
    graph, grid = arena
    metadata = grid.metadata()
    assert metadata["geometryRevision"] == (19 if graph.num_teams == 6 else 18)
    restored = [0] * len(grid.owners)
    for row, start, end, team in metadata["buildableRuns"]:
        restored[row * grid.cols + start:row * grid.cols + end] = [team] * (end - start)
    assert restored == grid.owners
    for cell, team in enumerate(grid.owners):
        if not team:
            continue
        row, col = divmod(cell, grid.cols)
        assert grid.classify(row, col) == (team, "")
        assert (row, col) not in grid.road_cells | grid.rally_cells | grid.river_cells
    for team in range(1, graph.num_teams + 1):
        for point in staging_bounds(graph, graph.get_spawn_node(team)):
            x, y = project(point)
            assert 0 < x + grid.offset[0] < grid.width
            assert 0 < y + grid.offset[1] < grid.height
        for enemy in range(1, graph.num_teams + 1):
            if enemy != team:
                assert graph.get_path_to_base(graph.get_spawn_node(team), enemy)
    assert graph.validate_map() == (True, [])


@pytest.mark.parametrize("count", [6, 7])
def test_legacy_geometry_is_unchanged(count):
    graph = GameMap(count, 6)
    assert graph.layout_scale == 3.6
    assert placement_grid(graph).geometry_revision == 11
    for team in range(1, count + 1):
        base = graph.nodes[graph.get_base_node(team)]
        assert math.hypot(base.x, base.y) == pytest.approx(1440)
