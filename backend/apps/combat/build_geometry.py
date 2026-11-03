"""Projected artwork/input clearance for version 5 foundations.

Matches BattleScene: base 137px at origin (.5,.88), tower 94px at (.5,.89),
56x45 marker hit area, and the tower's side banner. Conservative rectangles
include SVG strokes/padding and a small touch clearance, not just anchor radii.
"""

import math

from apps.combat.navigation import project, unproject
from apps.combat.road_shape import natural_road

BASE_BOUNDS = (-75, -125, 75, 45)
TOWER_BOUNDS = (-54, -90, 54, 25)


def bounds(point, offsets):
    return tuple(point[i % 2] + value for i, value in enumerate(offsets))


def overlaps(a, b, margin=4):
    return (
        a[0] < b[2] + margin
        and a[2] > b[0] - margin
        and a[1] < b[3] + margin
        and a[3] > b[1] - margin
    )


def movement_segments(graph):
    """Straight passable graph edges, including reverse/retarget/retreat routes."""
    for u, neighbors in sorted(graph.adjacency.items()):
        for v in sorted(neighbors):
            if u >= v or not graph.nodes[u].is_passable or not graph.nodes[v].is_passable:
                continue
            yield tuple(project((graph.nodes[n].x, graph.nodes[n].y)) for n in (u, v))


def road_segments(graph):
    """Reserve natural sand shoulders and the straight bridge/walking axes."""
    result = []
    sand_width = 70 if graph.layout_version >= 6 else 43
    for u, neighbors in sorted(graph.adjacency.items()):
        for v in sorted(neighbors):
            if u >= v or not graph.nodes[u].is_passable or not graph.nodes[v].is_passable:
                continue
            a, b = (project((graph.nodes[n].x, graph.nodes[n].y)) for n in (u, v))
            points = natural_road(a, b, f"{u}:{v}", sand_width)
            result.extend([(a, b), *zip(points, points[1:])])
    return result


def segment_distance(point, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0, min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / (dx * dx + dy * dy or 1)))
    return math.dist(point, (a[0] + t * dx, a[1] + t * dy))


def segment_intersects_rect(a, b, rect):
    """Closed segment/AABB slab test, including tangencies and zero length."""
    low, high = 0.0, 1.0
    for start, end, minimum, maximum in zip(a, b, rect[:2], rect[2:]):
        delta = end - start
        if abs(delta) < 1e-12:
            if start < minimum or start > maximum:
                return False
        else:
            t1, t2 = (minimum - start) / delta, (maximum - start) / delta
            low, high = max(low, min(t1, t2)), min(high, max(t1, t2))
            if low > high:
                return False
    return True


def segment_rect_distance(a, b, rect):
    """Exact Euclidean distance between a segment and a closed rectangle."""
    if segment_intersects_rect(a, b, rect):
        return 0.0
    left, top, right, bottom = rect
    corners = [(left, top), (right, top), (right, bottom), (left, bottom)]
    return min(
        *(segment_distance(p, a, b) for p in corners),
        *(math.hypot(max(left - p[0], 0, p[0] - right),
                     max(top - p[1], 0, p[1] - bottom)) for p in (a, b)),
    )


class BuildGeometry:
    def __init__(self, graph):
        self.graph = graph
        self.roads = road_segments(graph)
        self.bases = [
            bounds(project((n.x, n.y)), BASE_BOUNDS)
            for n in graph.nodes.values()
            if n.node_type == "base"
        ]
        self.barriers = [
            project((n.x, n.y)) for n in graph.nodes.values() if n.node_type == "barrier"
        ]
        self.width = max(1600, math.ceil(1200 * graph.layout_scale + 400))
        self.height = max(1040, math.ceil(688 * graph.layout_scale + 400))

    def valid(self, point, placed):
        rect = bounds(point, TOWER_BOUNDS)
        if (
            rect[0] < -self.width / 2 + 8
            or rect[2] > self.width / 2 - 8
            or rect[1] < -self.height / 2 - 60 + 8
            or rect[3] > self.height / 2 - 60 - 8
        ):
            return False
        if any(overlaps(rect, base) for base in self.bases):
            return False
        if any(overlaps(rect, bounds(other, TOWER_BOUNDS)) for other in placed):
            return False
        if any(math.dist(point, p) < 40 for p in self.barriers):
            return False
        # Narrow-phase only for segments within the foundation's road margin.
        for a, b in self.roads:
            if (
                min(a[0], b[0]) - 57.1 < point[0] < max(a[0], b[0]) + 57.1
                and min(a[1], b[1]) - 57.1 < point[1] < max(a[1], b[1]) + 57.1
                and segment_distance(point, a, b) < 57.1
            ):
                return False
        return True

    def place(self):
        placed = []
        for slot in (n for n in self.graph.nodes.values() if n.node_type == "tower_slot"):
            original = project((slot.x, slot.y))
            candidate = original
            if not self.valid(candidate, placed):
                # Closest valid projected position; same generator for every team/orientation.
                offsets = sorted(
                    ((x, y) for x in range(-40, 41) for y in range(-40, 41)),
                    key=lambda p: (p[0] ** 2 + p[1] ** 2, p[1], p[0]),
                )
                for x, y in offsets:
                    point = original[0] + x * 6, original[1] + y * 6
                    if self.valid(point, placed):
                        candidate = point
                        break
                else:
                    raise ValueError(f"No safe foundation for {slot.node_id}")
            slot.x, slot.y = unproject(candidate)
            placed.append(candidate)

    def validate(self):
        placed, errors = [], []
        for slot in (n for n in self.graph.nodes.values() if n.node_type == "tower_slot"):
            point = project((slot.x, slot.y))
            if not self.valid(point, placed):
                errors.append(f"Artwork/input footprint overlaps: {slot.node_id}")
            placed.append(point)
        return errors
