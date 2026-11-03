"""Siege units prioritize the selected team's defenses before its base."""
import math

from apps.combat.balance import troop_tower_firing_radius
from apps.combat.formation import physical_position, redirect_route, route_lengths


def defending_towers(entities, team_id):
    return [e for e in entities if e.get("entity_kind") == "TOWER"
            and e.get("team_id") == team_id
            and e.get("status") in ("ACTIVE", "DISABLED") and e.get("current_hp", 0) > 0]


def tower_approach_node(entity, tower, game_map):
    node = tower["current_node_id"]
    if node not in game_map.nodes:
        return entity["current_node_id"]
    if game_map.nodes[node].is_passable:
        return node
    # Stay at a passable road anchor; never cross grass to a foundation.
    point = physical_position(tower, game_map)
    radius = entity.get("range", 1) * 80
    options = []
    for node_id, road_node in game_map.nodes.items():
        if not road_node.is_passable:
            continue
        route = game_map.shortest_physical_path(entity["current_node_id"], node_id)
        if route:
            road_distance = sum(
                math.dist((game_map.nodes[a].x, game_map.nodes[a].y),
                          (game_map.nodes[b].x, game_map.nodes[b].y))
                for a, b in zip(route, route[1:]))
            approach = max(0, math.dist((road_node.x, road_node.y), point) - radius)
            options.append((approach > 1e-7, approach if approach > 1e-7 else 0, road_distance, node_id))
    return min(options)[-1] if options else entity["current_node_id"]


def plan_road_firing_position(entity, target, game_map):
    """Shortest road travel to weapon range, including points inside an edge.

    Unreachable towers can only be approached as far as the road permits.
    """
    sim = entity["simulation_state"]
    goal = physical_position(target, game_map)
    # Cover the bounded cosmetic anchor offset in map coordinates.
    radius = max(0, troop_tower_firing_radius(entity, game_map, target) - 15)
    current = entity["current_node_id"]
    options = []
    for a_id, neighbors in sorted(game_map.adjacency.items()):
        if not game_map.nodes[a_id].is_passable:
            continue
        a = game_map.nodes[a_id]
        for b_id in sorted(neighbors):
            b = game_map.nodes[b_id]
            if not b.is_passable:
                continue
            dx, dy = b.x - a.x, b.y - a.y
            length = math.hypot(dx, dy)
            if length < 1e-9:
                continue
            projection = ((goal[0] - a.x) * dx + (goal[1] - a.y) * dy) / length ** 2
            nearest = max(0, min(1, projection))
            gap = math.dist(goal, (a.x + nearest * dx, a.y + nearest * dy))
            perpendicular_sq = max(0, math.dist(goal, (a.x, a.y)) ** 2 - (projection * length) ** 2)
            fraction = nearest
            if gap <= radius:
                fraction = max(0, min(1, projection - math.sqrt(max(0, radius ** 2 - perpendicular_sq)) / length))
            route = game_map.path(current, a_id)
            if not route:
                continue
            distance_to_anchor = route_lengths(route, game_map)[-1]
            next_id = sim.get("next_node_id")
            if next_id:
                current_edge = route_lengths([current, next_id], game_map)[-1]
                progress = sim.get("edge_progress", 0)
                tail = game_map.path(next_id, a_id)
                distance_to_anchor = min(
                    current_edge * progress + distance_to_anchor,
                    current_edge * (1 - progress) + route_lengths(tail, game_map)[-1]
                    if tail else math.inf,
                )
            cost = distance_to_anchor + fraction * length
            # Staying on the occupied edge avoids a detour via either endpoint.
            if current == a_id and sim.get("next_node_id") == b_id:
                cost = abs(fraction - sim.get("edge_progress", 0)) * length
            options.append((gap > radius, max(0, gap - radius), cost, a_id, b_id, fraction))
    if not options:
        return
    _, _, _, a_id, b_id, fraction = min(options)
    if current == a_id and sim.get("next_node_id") == b_id:
        progress = sim.get("edge_progress", 0)
        if fraction < progress:
            a_id, b_id, fraction, progress = b_id, a_id, 1 - fraction, 1 - progress
        sim["route_nodes"] = [a_id, b_id]
        sim["route_distance"] = progress * route_lengths([a_id, b_id], game_map)[-1]
        entity["current_node_id"] = a_id
    else:
        redirect_route(entity, a_id, game_map)
        sim["route_nodes"].append(b_id)
    lengths = route_lengths(sim["route_nodes"], game_map)
    sim["siege_stop_distance"] = lengths[-2] + fraction * (lengths[-1] - lengths[-2])
    sim["siege_goal_node"] = b_id
    sim["siege_firing_radius"] = troop_tower_firing_radius(entity, game_map, target)


def plan_siege(entity, towers, game_map):
    """Keep a stable target and approach it exclusively along sand roads."""
    sim = entity["simulation_state"]
    previous = sim.get("siege_target_id")
    target = next((t for t in towers if t["id"] == previous), None)
    if target is None and towers:
        point = physical_position(entity, game_map)
        target = min(towers, key=lambda t: (
            game_map.distance(entity["current_node_id"], t["current_node_id"]),
            math.dist(point, physical_position(t, game_map)), str(t["id"])))
    if previous != (target["id"] if target else None):
        # An off-road approach must walk back to its road anchor, including on
        # retarget/retreat. Never turn its saved position into a permanent offset.
        if sim.pop("siege_detour", False):
            sim["crowd_offset"] = sim.pop("siege_road_offset")
            sim.update(movement_zone="STAGING", staging_entry_distance=0)
            route = sim.get("route_nodes", [])
            if route:
                redirect_route(entity, route[-1], game_map)
        sim.pop("siege_goal", None)
        sim.pop("siege_goal_node", None)
        sim.pop("siege_stop_distance", None)
        sim.pop("siege_firing_radius", None)
        sim.pop("siege_target_id", None)
        if target:
            sim["siege_target_id"] = target["id"]
    if target:
        from apps.combat.continuous import target_distance
        if target_distance(entity, target, game_map) <= entity.get("range", 1):
            return target
        if ("siege_stop_distance" not in sim
                or sim.get("siege_firing_radius") != troop_tower_firing_radius(entity, game_map, target)):
            plan_road_firing_position(entity, target, game_map)
    sim.pop("siege_goal", None)
    return target
