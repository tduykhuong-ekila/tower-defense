"""Natural sand remains wide enough for the shortest road-only troop routes."""
import math

import pytest

from apps.combat.build_geometry import road_segments, segment_distance
from apps.combat.map import get_game_map
from apps.combat.navigation import project
from apps.combat.road_shape import natural_road


@pytest.mark.parametrize('count', [2, 3, 5, 20])
@pytest.mark.parametrize('version', [5, 7])
def test_all_natural_roads_contain_the_full_troop_corridor(count, version):
    graph = get_game_map(count, version)
    sand_width = 70 if version >= 6 else 43
    has_bend = False
    for u, neighbors in sorted(graph.adjacency.items()):
        for v in sorted(neighbors):
            if u >= v or not graph.nodes[u].is_passable or not graph.nodes[v].is_passable:
                continue
            a, b = (project((graph.nodes[n].x, graph.nodes[n].y)) for n in (u, v))
            points = natural_road(a, b, f'{u}:{v}', sand_width)
            assert math.dist(points[0], a) < 1e-8
            assert math.dist(points[-1], b) < 1e-8
            has_bend |= any(segment_distance(p, a, b) > 2 for p in points)
            dx, dy = b[0]-a[0], b[1]-a[1]
            length = math.hypot(dx, dy)
            if not length:
                continue
            for i, (start, end) in enumerate(zip(points, points[1:])):
                for fraction in (0, .5, 1):
                    t = (i + fraction) / 32
                    for offset in (-12, 0, 12):
                        point = (a[0]+dx*t-dy/length*offset,
                                 a[1]+dy*t+dx/length*offset)
                        assert segment_distance(point, start, end) <= sand_width/2 - 2
    assert has_bend
    # The placement mask reserves all painted bends, in addition to bridge axes.
    assert len(road_segments(graph)) > 32
