"""Authoritative route and rally geometry. Distances are physical map-coordinate units."""

import math
from functools import lru_cache

FORMATION_MINIMUM_GAP = 2.0
# Occupied SVG body bounds at the existing Phaser display sizes (not texture frames).
# Exclude soft shadows and decorative weapons/plumes; allow their slight overlap.
SPRITE_BODIES = {
    "infantry": (34.0, 38.0, -20.0),
    "tank": (54.0, 44.0, -27.0),
    "artillery": (54.0, 50.0, -27.0),
}
PUBLIC_FORMATION_FIELDS = {
    "build_cost",
    "grid_placement",
    "order", "destination_rally_id", "command_version",
    "next_node_id",
    "edge_progress",
    "approach_node_id",
    "staging_distance",
    "formation_order",
    "formation_footprint",
    "movement_zone",
    "world_position",
    "movement_state",
    "combat_state",
    "attack_target_id",
    "attack_remaining",
    "movement_path",
    "crowd_offset",
    "route_nodes", "staging_entry_distance",
}


def redirect_route(entity, destination, game_map, *, physical_shortest=True):
    """Route from either endpoint of the occupied edge without relocating a troop.

    The first edge may be traversed backward. All later edges come from the
    authoritative passable graph; physical distance chooses the endpoint.
    Cosmetic offsets and the original speed reference remain unchanged.
    """
    sim = entity.setdefault("simulation_state", {})
    sim.pop("siege_stop_distance", None)
    point = physical_position(entity, game_map)
    node, next_node = entity["current_node_id"], sim.get("next_node_id")
    fraction = sim.get("edge_progress", 0)
    # At an endpoint there is no occupied partial edge to preserve. Keeping a
    # fully consumed edge would add phantom distance and can repeat a waypoint.
    if next_node and fraction <= 1e-9:
        next_node = None
    elif next_node and fraction >= 1 - 1e-9:
        node, next_node = next_node, None
    if next_node:
        length = edge_length(game_map, node, next_node)
        candidates = []
        for start, end, progress in ((node, next_node, length * fraction),
                                     (next_node, node, length * (1 - fraction))):
            path = game_map.shortest_physical_path if physical_shortest else game_map.path
            tail = path(end, destination)
            if tail:
                candidates.append((length - progress + route_lengths(tail, game_map)[-1],
                                   [start, *tail], progress))
        if not candidates:
            return False
        _, route, progress = min(candidates, key=lambda candidate: (candidate[0], candidate[1]))
    else:
        path = game_map.shortest_physical_path if physical_shortest else game_map.path
        route = path(node, destination)
        progress = -sim.get("staging_distance", 0)
    if not route:
        return False
    # Legacy staging approaches keep walking from their saved physical point.
    for key in ("navigation_path", "navigation_end", "staging_path", "staging_entry_distance"):
        sim.pop(key, None)
    sim.update(route_nodes=route, route_distance=progress, route_policy_version=1, movement_path=[],
               movement_state="STOPPED", combat_state="IDLE", attack_target_id=None)
    synchronize_position(entity, game_map)
    if progress >= 0 and sim.get("movement_zone") != "STAGING":
        center = position_at(entity, progress, game_map)
        sim["crowd_offset"] = {"x": point[0] - center[0], "y": point[1] - center[1]}
    sim["world_position"] = {"x": point[0], "y": point[1]}
    return True


def body(entity):
    return SPRITE_BODIES.get(
        entity.get("unit_type_code"),
        entity.get("simulation_state", {}).get("formation_body", (54.0, 50.0, -27.0)),
    )


def bodies_clear(a, b, point_a, point_b, config):
    """Opaque body bounds projected exactly like projectMap; preserve sprite anchors."""
    aw, ah, ay = body(a)
    bw, bh, by = body(b)
    dx, dy = point_a[0] - point_b[0], point_a[1] - point_b[1]
    angle = -math.pi * 3 / 4
    screen_x = (dx * math.cos(angle) - dy * math.sin(angle)) * 1.5
    screen_y = (dx * math.sin(angle) + dy * math.cos(angle)) * 0.86 + ay - by
    gap = config.get("troop_formation_gap", FORMATION_MINIMUM_GAP) * 0.86
    return (
        abs(screen_x) >= (aw + bw) / 2 + gap - 1e-8 or abs(screen_y) >= (ah + bh) / 2 + gap - 1e-8
    )


def swept_bodies_clear(a, b, point, leader_path, config):
    """Reserve just the bend's swept body, so a leader cannot turn into its rear.

    Straight roads give the same tight clearance. Segment/box intersection avoids
    undersampling the inside of sharp projected corners at high movement speed.
    """
    aw, ah, ay = body(a)
    bw, bh, by = body(b)
    gap = config.get("troop_formation_gap", FORMATION_MINIMUM_GAP) * 0.86
    half_x, half_y = (aw + bw) / 2 + gap - 1e-7, (ah + bh) / 2 + gap - 1e-7
    angle = -math.pi * 3 / 4

    def project(p):
        dx, dy = p[0] - point[0], p[1] - point[1]
        return (
            (dx * math.cos(angle) - dy * math.sin(angle)) * 1.5,
            (dx * math.sin(angle) + dy * math.cos(angle)) * 0.86 + by - ay,
        )

    points = [project(p) for p in leader_path]
    for start, end in zip(points, points[1:]):
        low, high = 0.0, 1.0
        for x, y, half in zip(start, end, (half_x, half_y)):
            delta = y - x
            if abs(delta) < 1e-10:
                if abs(x) >= half:
                    low, high = 1.0, 0.0
                    break
            else:
                t1, t2 = (-half - x) / delta, (half - x) / delta
                low, high = max(low, min(t1, t2)), min(high, max(t1, t2))
        if low < high:
            return False
    return True


def footprint(entity):
    # Lower bound for any projected road direction. Actual body clearance below
    # supplies the direction-dependent length without oversized diagonal circles.
    width, height, _ = body(entity)
    return min(width, height) / 1.5


def edge_length(game_map, a, b):
    x, y = game_map.nodes[a], game_map.nodes[b]
    return math.hypot(y.x - x.x, y.y - x.y)


def route_lengths(route, game_map):
    return _route_lengths(tuple(route), game_map)


@lru_cache(maxsize=4096)
def _route_lengths(route, game_map):
    cumulative = [0.0]
    for a, b in zip(route, route[1:]):
        cumulative.append(cumulative[-1] + edge_length(game_map, a, b))
    return tuple(cumulative)


def minimum_spacing(a, b, config):
    return (
        a["simulation_state"]["formation_footprint"] + b["simulation_state"]["formation_footprint"]
    ) / 2 + config.get("troop_formation_gap", FORMATION_MINIMUM_GAP)


def initialize_route(entity, target_base, game_map, *, approach_base=False):
    sim = entity.setdefault("simulation_state", {})
    # Recompute the derived footprint for existing saved troops as well as new ones.
    sim["formation_footprint"] = footprint(entity)
    # JSON persists arrays as lists. A tuple here dirties every stationary troop
    # on every tick after reloading, forcing needless bulk updates at 20 teams.
    sim["formation_body"] = list(body(entity))
    destination = target_base if approach_base else game_map.attack_position(target_base)
    old_route = sim.get("route_nodes", [])
    if (old_route and old_route[-1] == destination
            and sim.get("route_policy_version") == 1):
        return
    # Extending the same approach to the base preserves its origin, staging
    # entry and traveled distance. Re-routing from the current edge here would
    # reset progress and can send parked vehicles back toward an earlier node.
    if (approach_base and old_route
            and old_route[-1] == game_map.attack_position(target_base)
            and sim.get("route_policy_version") == 1):
        tail = game_map.path(old_route[-1], destination)
        if tail:
            sim["route_nodes"] = [*old_route, *tail[1:]]
            return
    sim.pop("navigation_path", None)
    sim.pop("navigation_end", None)
    sim.pop("siege_stop_distance", None)
    node = entity["current_node_id"]
    next_node = sim.get("next_node_id")
    if next_node:
        if not redirect_route(entity, destination, game_map):
            return
        route = sim["route_nodes"]
        progress = sim["route_distance"]
    else:
        route = game_map.path(node, destination)
        progress = -sim.get("staging_distance", 0)
    if not route:
        sim["route_nodes"] = []
        return
    sim["route_nodes"] = route
    sim["route_distance"] = progress
    sim["route_policy_version"] = 1
    if len(route) > 1:
        cumulative = route_lengths(route, game_map)
        sim.setdefault("reference_hop_length", cumulative[-1] / (len(route) - 1))


def synchronize_position(entity, game_map):
    sim = entity["simulation_state"]
    route = sim.get("route_nodes", [])
    if not route:
        return
    cumulative = route_lengths(route, game_map)
    position = min(sim.get("route_distance", 0), cumulative[-1])
    sim["route_distance"] = position
    sim.pop("next_node_id", None)
    sim["edge_progress"] = 0.0
    if position < 0 and len(route) > 1:
        entity["current_node_id"] = route[0]
        sim["approach_node_id"] = route[1]
        sim["staging_distance"] = -position
        return
    sim.pop("approach_node_id", None)
    sim.pop("staging_distance", None)
    for index in range(len(route) - 1):
        if position < cumulative[index + 1] - 1e-8:
            entity["current_node_id"] = route[index]
            sim["next_node_id"] = route[index + 1]
            sim["edge_progress"] = max(
                0,
                (position - cumulative[index])
                / max(1e-9, cumulative[index + 1] - cumulative[index]),
            )
            break
    else:
        entity["current_node_id"] = route[-1]


def initialize_spawn(entity, others, target_base, game_map, order, config):
    from apps.combat.navigation import staging_slots

    sim = entity.setdefault("simulation_state", {})
    sim["formation_order"] = order
    initialize_route(entity, target_base, game_map)
    sim["route_distance"] = 0.0
    synchronize_position(entity, game_map)
    if entity.get("unit_type_code") == "infantry":
        from apps.combat.mobile import initialize_infantry_spawn
        initialize_infantry_spawn(entity, game_map)
        return
    # Fixed bounded slots for vehicles, shared by every client.
    slots = staging_slots(game_map, entity["current_node_id"])
    # Reserve Infantry's compact 5×3 visual patch even if vehicles are bought first.
    # This affects artwork spacing only; all units still start at this spawn node.
    spawn = game_map.nodes[entity["current_node_id"]]
    infantry_patch = {"unit_type_code": "rally_patch",
                      "simulation_state": {"formation_body": (122.0, 70.0, -20.0)}}
    for point in slots:
        if not bodies_clear(entity, infantry_patch, point, (spawn.x, spawn.y), config):
            continue
        if all(
            bodies_clear(entity, other, point, physical_position(other, game_map), config)
            for other in others if other["status"] != "DESTROYED"
        ):
            sim["world_position"] = {"x": point[0], "y": point[1]}
            # Parking slots can be far from the centerline. Walk to the bounded
            # road patch inside the protected rally before following graph edges.
            sim["crowd_offset"] = {"x": point[0] - spawn.x, "y": point[1] - spawn.y}
            sim["staging_entry_distance"] = 0.0
            sim["movement_zone"] = "STAGING"
            if config.get("tower_placement_version") == 1:
                from apps.combat.mobile import crowd_offset
                sim["crowd_offset"] = crowd_offset(order)
                sim["movement_zone"] = "STAGING"
            entity["status"] = "ACTIVE"
            sim["movement_state"] = "STOPPED"
            sim["combat_state"] = "IDLE"
            return
    # Deployment transaction rolls back rather than stacking or extending a queue.
    from django.core.exceptions import ValidationError
    raise ValidationError("Khu tập kết đã đầy; hãy đợi quân tiến vào đường.")


def physical_position(entity, game_map):
    sim = entity.get("simulation_state", {})
    point = sim.get("world_position")
    if point:
        return point["x"], point["y"]
    return position_at(entity, sim.get("route_distance", 0), game_map)


def position_at(entity, position, game_map):
    route = entity["simulation_state"].get("route_nodes", [])
    if not route:
        node = game_map.nodes[entity["current_node_id"]]
        return node.x, node.y
    cumulative = route_lengths(route, game_map)
    for index in range(len(route) - 1):
        if position <= cumulative[index + 1]:
            a, b = game_map.nodes[route[index]], game_map.nodes[route[index + 1]]
            fraction = (position - cumulative[index]) / max(
                1e-9, cumulative[index + 1] - cumulative[index]
            )
            return a.x + (b.x - a.x) * fraction, a.y + (b.y - a.y) * fraction
    node = game_map.nodes[route[-1]]
    return node.x, node.y
