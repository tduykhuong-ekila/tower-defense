"""Server-coordinate rally geometry and independent mobile movement.

Saved staging approaches remain supported; admission and road progression do not
reserve a leader, gate or convoy. Phaser only interpolates the resulting positions.
"""

import heapq
import math
from functools import lru_cache

from apps.combat.formation import (
    body,
    physical_position,
    position_at,
    route_lengths,
)

ANGLE = -math.pi * 3 / 4
PASSING_SHOULDER = 100.0


def project(point):
    x, y = point
    return (
        (x * math.cos(ANGLE) - y * math.sin(ANGLE)) * 1.5,
        (x * math.sin(ANGLE) + y * math.cos(ANGLE)) * 0.86,
    )


def unproject(point):
    x, y = point[0] / 1.5, point[1] / 0.86
    return x * math.cos(ANGLE) + y * math.sin(ANGLE), -x * math.sin(ANGLE) + y * math.cos(ANGLE)


@lru_cache(maxsize=256)
def staging_slots(game_map, spawn_id):
    """Compact bounded candidates for the supported 30-unit team cap.

    Screen-aligned cells account for the existing isometric body projection. The
    coordinates themselves are authoritative map positions, saved at deployment.
    """
    node = game_map.nodes[spawn_id]
    x, y = project((node.x, node.y))
    entry = game_map.nodes[sorted(game_map.adjacency[spawn_id])[0]]
    ex, ey = project((entry.x, entry.y))
    # Keep the outgoing road clear. A two-dimensional half-disc behind the spawn
    # avoids a mutual admission deadlock with a troop leaving the center slot.
    route = game_map.path(spawn_id, "node_center")
    road = [project((game_map.nodes[n].x, game_map.nodes[n].y)) for n in route]
    # Fit the largest standard body, including rooms with the old 12-unit gap.
    # Fine Infantry-only grids can exhaust their cells before 30 Tanks fit.
    cell_width, cell_height = 66, 62
    cells = sorted(
        (
            (i, j)
            for i in range(-10, 11)
            for j in range(-10, 11)
            if i * cell_width * (ex - x) + j * cell_height * (ey - y) <= 1e-7
        ),
        key=lambda p: (p[0] ** 2 + p[1] ** 2, p[1], p[0]),
    )
    slots = [(node.x, node.y)]
    for i, j in cells:
        if not (i or j):
            continue
        point = x + i * cell_width, y + j * cell_height
        rect = point[0] - 70, point[1] - 65, point[0] + 70, point[1] + 65
        if any(intersects(a, b, rect) for a, b in zip(road, road[1:])):
            continue
        slots.append(unproject(point))
        # Enough room for 30 large bodies plus the reserved gate, without a line.
        if len(slots) == 40:
            break
    return slots


@lru_cache(maxsize=256)
def staging_bounds(game_map, spawn_id):
    points = [project(p) for p in staging_slots(game_map, spawn_id)]
    left, right = min(p[0] for p in points) - 36, max(p[0] for p in points) + 36
    top, bottom = min(p[1] for p in points) - 35, max(p[1] for p in points) + 35
    return [unproject(p) for p in [(left, top), (right, top), (right, bottom), (left, bottom)]]


def admission_bounds(entity, game_map):
    bounds = [
        project(p) for p in staging_bounds(game_map, entity["simulation_state"]["route_nodes"][0])
    ]
    # Existing saved staging/negative queues keep their physical starting point
    # and old entry. The new compact patch must not strand them outside its bounds.
    for point in (physical_position(entity, game_map),
                  position_at(entity, entity["simulation_state"].get("staging_entry_distance", 0), game_map)):
        x, y = project(point)
        bounds[0] = min(bounds[0][0], x - 36), min(bounds[0][1], y - 35)
        bounds[2] = max(bounds[2][0], x + 36), max(bounds[2][1], y + 35)
    if entity["simulation_state"].get("staging_entry_distance", 0) > 0:
        for node_id in entity["simulation_state"]["route_nodes"][:4]:
            node = game_map.nodes[node_id]
            x, y = project((node.x, node.y))
            bounds[0] = min(bounds[0][0], x - 36), min(bounds[0][1], y - 35)
            bounds[2] = max(bounds[2][0], x + 36), max(bounds[2][1], y + 35)
    return bounds


def rectangle(mover, other, point, config):
    aw, ah, ay = body(mover)
    bw, bh, by = body(other)
    x, y = project(point)
    margin = config.get("troop_formation_gap", 2) * 0.86
    hx, hy = (aw + bw) / 2 + margin, (ah + bh) / 2 + margin
    return x - hx, y + by - ay - hy, x + hx, y + by - ay + hy


def collision_fraction(start, end, rect):
    """First entry into an open body rectangle; 1 means the segment is clear."""
    low, high = 0.0, 1.0
    for a, b, minimum, maximum in zip(start, end, rect[:2], rect[2:]):
        delta = b - a
        if abs(delta) < 1e-10:
            if a <= minimum + 1e-8 or a >= maximum - 1e-8:
                return 1.0
        else:
            t1, t2 = (minimum - a) / delta, (maximum - a) / delta
            low, high = max(low, min(t1, t2)), min(high, max(t1, t2))
    return max(0, low) if low < high - 1e-8 and high > 1e-8 and low < 1 - 1e-8 else 1.0


def intersects(start, end, rect):
    return collision_fraction(start, end, rect) < 1.0


def path_around(start, goal, obstacles, allowed=lambda a, b: True):
    """Deterministic visibility graph around nearby body rectangles (map metric)."""
    start, goal = project(start), project(goal)
    if not any(intersects(start, goal, rect) for rect in obstacles) and allowed(
        unproject(start), unproject(goal)
    ):
        return [unproject(goal)]
    points = [start, goal]
    for left, top, right, bottom in obstacles:
        points.extend(
            [
                (left - 0.1, top - 0.1),
                (left - 0.1, bottom + 0.1),
                (right + 0.1, top - 0.1),
                (right + 0.1, bottom + 0.1),
            ]
        )
    points = points[:2] + [
        p for p in points[2:] if not any(intersects(p, p, rect) for rect in obstacles)
    ]
    map_points = [unproject(p) for p in points]
    queue, costs, parents = [(0, 0, 0)], {0: 0}, {}
    while queue:
        _, cost, i = heapq.heappop(queue)
        if cost > costs[i] + 1e-8:
            continue
        if i == 1:
            result = []
            while i:
                result.append(unproject(points[i]))
                i = parents[i]
            return list(reversed(result))
        for j, p in enumerate(points):
            if i == j:
                continue
            length = math.dist(map_points[i], map_points[j])
            candidate = cost + length
            if (
                candidate < costs.get(j, math.inf) - 1e-8
                and not any(intersects(points[i], p, rect) for rect in obstacles)
                and allowed(map_points[i], map_points[j])
            ):
                costs[j], parents[j] = candidate, i
                heapq.heappush(
                    queue, (candidate + math.dist(map_points[j], map_points[1]), candidate, j)
                )
    return []


def advance_path(start, path, budget):
    point, traveled, remaining, trail = start, 0.0, list(path), [start]
    while remaining and budget > 1e-9:
        end = remaining[0]
        length = math.dist(point, end)
        if length <= budget + 1e-9:
            point = tuple(end)
            remaining.pop(0)
            budget -= length
            traveled += length
        else:
            point = tuple(a + (b - a) * budget / length for a, b in zip(point, end))
            traveled += budget
            budget = 0
        trail.append(point)
    return point, remaining, traveled, trail


def route_polyline(entity, start, end, game_map):
    sim = entity["simulation_state"]
    route = sim.get("route_nodes", [])
    lengths = route_lengths(route, game_map)
    return [
        position_at(entity, start, game_map),
        *(
            (game_map.nodes[node].x, game_map.nodes[node].y)
            for node, distance in zip(route, lengths)
            if start < distance < end
        ),
        position_at(entity, end, game_map),
    ]


def nearest_progress(entity, point, game_map):
    route = entity["simulation_state"].get("route_nodes", [])
    lengths = route_lengths(route, game_map)
    best = (math.inf, 0.0)
    for i, (a, b) in enumerate(zip(route, route[1:])):
        a, b = game_map.nodes[a], game_map.nodes[b]
        dx, dy = b.x - a.x, b.y - a.y
        t = max(
            0,
            min(1, ((point[0] - a.x) * dx + (point[1] - a.y) * dy) / max(1e-9, dx * dx + dy * dy)),
        )
        candidate = (
            math.dist(point, (a.x + dx * t, a.y + dy * t)),
            lengths[i] + (lengths[i + 1] - lengths[i]) * t,
        )
        best = min(best, candidate)
    return best


def staging_entry(entity, point, game_map):
    """One rally gate for all new troops; never skip an outgoing waypoint."""
    return 0.0


def legacy_staging_entry(entity, point, game_map):
    """Saved pre-rally queues retain a reachable approach without relocation."""
    route = entity["simulation_state"].get("route_nodes", [])
    if len(route) < 3 or math.dist(point, position_at(entity, 0, game_map)) < 1e-7:
        return 0.0
    lengths = route_lengths(route, game_map)
    best = (math.inf, lengths[1])
    for i in range(1, min(3, len(route) - 1)):
        a, b = game_map.nodes[route[i]], game_map.nodes[route[i + 1]]
        dx, dy = b.x - a.x, b.y - a.y
        t = max(
            0,
            min(1, ((point[0] - a.x) * dx + (point[1] - a.y) * dy) / max(1e-9, dx * dx + dy * dy)),
        )
        candidate = (
            math.dist(point, (a.x + dx * t, a.y + dy * t)),
            lengths[i] + (lengths[i + 1] - lengths[i]) * t,
        )
        best = min(best, candidate)
    return best[1]


def move_independently(units, game_map, config, dt, stopped):
    """Every eligible troop advances on the same timestep, without traffic locks."""
    from apps.combat.mobile import move_mobile_units

    move_mobile_units(units, game_map, config, dt, stopped)
