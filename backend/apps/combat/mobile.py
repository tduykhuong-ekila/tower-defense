"""Independent mobile troop route progress; bounded cosmetic crowd offsets are server owned.

Road movement and tower approaches use graph nodes/edge progress. Bounded
cosmetic offsets keep ground anchors inside the painted sand. Dense Infantry armies use client crowd LOD rather than
collision reservations or a deployment quota.
"""

import math

from apps.combat.balance import movement_speed
from apps.combat.formation import (
    physical_position,
    position_at,
    route_lengths,
    synchronize_position,
)


def crowd_offset(order):
    # A compact 5 x 3 patch in projected pixels, repeated for large crowds.
    slot = (order - 1) % 15
    x, y = ((slot % 5) - 2) * 22, ((slot // 5) - 1) * 16
    angle = -math.pi * 3 / 4
    return {"x": x / 1.5 * math.cos(angle) + y / .86 * math.sin(angle),
            "y": -x / 1.5 * math.sin(angle) + y / .86 * math.cos(angle)}


def display_position(entity, progress, game_map):
    x, y = position_at(entity, progress, game_map)
    offset = entity["simulation_state"].get("crowd_offset", {"x": 0, "y": 0})
    # Keep the ground anchor inside even the narrowest yellow road (43px).
    from apps.combat.navigation import project
    width = math.hypot(*project((offset["x"], offset["y"])))
    scale = min(1.0, 12.0 / max(width, 1e-9))
    return x + offset["x"] * scale, y + offset["y"] * scale


def initialize_infantry_spawn(entity, game_map):
    sim = entity["simulation_state"]
    sim.update(crowd_offset=crowd_offset(sim["formation_order"]), movement_zone="ROUTE",
               movement_state="STOPPED", combat_state="IDLE")
    x, y = display_position(entity, 0, game_map)
    sim["world_position"] = {"x": x, "y": y}
    entity["status"] = "ACTIVE"


def move_mobile_units(units, game_map, config, dt, stopped):
    from apps.combat.navigation import advance_path

    for entity in units:
        sim = entity["simulation_state"]
        sim["movement_path"] = []
        sim["movement_state"] = "STOPPED"
        route = sim.get("route_nodes", [])
        if not route:
            continue
        origin = sim.get("route_distance", 0)
        sim.setdefault("movement_zone", "STAGING" if origin < 0 else "ROUTE")
        start = physical_position(entity, game_map)
        budget = 0 if entity["id"] in stopped else movement_speed(entity, config) * dt
        if budget <= 0:
            sim["world_position"] = {"x": start[0], "y": start[1]}
            continue
        # Existing troops of every type retain their saved position/HP. Old approaches walk to
        # their route independently. Old road troops retain their cosmetic offset.
        if "crowd_offset" not in sim or ("world_position" not in sim and origin >= 0):
            center = position_at(entity, max(0, origin), game_map)
            sim["crowd_offset"] = {"x": start[0] - center[0], "y": start[1] - center[1]} if origin >= 0 and sim.get("movement_zone") != "STAGING" else crowd_offset(sim["formation_order"])
        approaching = origin < 0 or sim.get("movement_zone") == "STAGING"
        trail = [start]
        if approaching:
            # No team departure selector, collision lock, or leader dependency.
            entry = max(0, sim.get("staging_entry_distance", 0))
            goal = display_position(entity, entry, game_map)
            point, remaining, traveled, approach = advance_path(start, [goal], budget)
            trail = approach
            budget -= traveled
            sim["world_position"] = {"x": point[0], "y": point[1]}
            if remaining:
                sim["movement_zone"] = "STAGING"
                sim["route_distance"] = max(0, origin)
                if traveled > 1e-7:
                    sim["movement_state"] = "MOVING"
                    sim["movement_path"] = [{"x": x, "y": y} for x, y in trail] if len(trail) > 2 else []
                continue
            origin = entry
            sim["route_distance"] = origin
            for key in ("staging_path", "navigation_path", "navigation_end", "legacy_staging_origin"):
                sim.pop(key, None)
        lengths = route_lengths(route, game_map)
        end = min(lengths[-1], sim.get("siege_stop_distance", lengths[-1]),
                  sim.get("base_attack_stop_distance", lengths[-1]), origin + max(0, budget))
        # Include every intervening corner even when one tick crosses many edges.
        trail.extend(display_position(entity, d, game_map) for d in lengths if origin < d < end)
        point = display_position(entity, end, game_map)
        trail.append(point)
        sim.update(route_distance=end, movement_zone="ROUTE")
        entity["status"] = "ACTIVE"
        synchronize_position(entity, game_map)
        sim["world_position"] = {"x": point[0], "y": point[1]}
        if any(math.dist(a, b) > 1e-7 for a, b in zip(trail, trail[1:])):
            sim["movement_state"] = "MOVING"
            sim["movement_path"] = [{"x": x, "y": y} for x, y in trail] if len(trail) > 2 else []
