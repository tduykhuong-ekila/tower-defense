"""
Unit movement resolution, path progression, enemy blocking, and fallback retargeting (§9.2, §9.4, D8).
Pure deterministic functions.
"""

import math
from typing import Any, Dict, List, Optional, Tuple

from apps.combat.balance import TROOP_BASE_ATTACK_RANGE
from apps.combat.map import GameMap


def resolve_unit_target(
    unit: Dict[str, Any],
    active_enemy_teams: Dict[str, Dict[str, Any]],  # team_id -> team_dict
    fallback_policy: str,  # 'RETARGET_NEAREST' | 'IDLE'
    game_map: GameMap,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Validates current target base.
    If target base was eliminated/destroyed, applies fallback_policy (§9.4, D8).
    Returns (target_team_id, target_base_node) or (None, None) if IDLE/no target.
    """
    curr_target_id = unit.get("target_team_id")
    current_node = unit.get("current_node_id", "")

    # Check if target is still active
    if curr_target_id and curr_target_id in active_enemy_teams:
        target_team = active_enemy_teams[curr_target_id]
        if target_team.get("status") == "ACTIVE" and target_team.get("base_hp", 0) > 0:
            target_idx = target_team.get("team_index", 1)
            return curr_target_id, game_map.get_base_node(target_idx)

    # Current target is invalid / eliminated
    if fallback_policy == "IDLE":
        return None, None

    # RETARGET_NEAREST: Find closest active enemy base from unit's current position
    closest_team_id = None
    min_dist = 999999
    closest_base_node = None

    for tid, tinfo in sorted(active_enemy_teams.items(), key=lambda x: str(x[0])):
        if tinfo.get("status") == "ACTIVE" and tinfo.get("base_hp", 0) > 0:
            t_idx = tinfo.get("team_index", 1)
            b_node = game_map.get_base_node(t_idx)
            atk_node = game_map.attack_position(b_node)
            dist = game_map.distance(current_node, atk_node)
            if dist < min_dist:
                min_dist = dist
                closest_team_id = tid
                closest_base_node = b_node

    return closest_team_id, closest_base_node


def resolve_units_movement(
    units: List[Dict[str, Any]],
    active_teams: Dict[str, Dict[str, Any]],  # team_id -> team_info
    game_map: GameMap,
    fallback_policy: str = "RETARGET_NEAREST",
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Simulates movement for all active combat units (§9.2):
    1. Deterministic sort by team_id, entity_id.
    2. Validates / updates targets according to fallback_policy.
    3. Advances unit along predefined path towards attack position.
    4. Blocks unit if enemy occupies destination node.
    Returns:
      (updated_units, movement_events)
    """
    # Deterministic processing order
    sorted_units = sorted(units, key=lambda u: (str(u.get("team_id", "")), str(u.get("id", ""))))

    # Track current occupied nodes by team for blocking rule (§9.2)
    # node_id -> set of team_ids occupying that node
    node_occupants: Dict[str, List[Dict[str, Any]]] = {}
    for u in sorted_units:
        if u.get("status") == "ACTIVE" and u.get("current_hp", 0) > 0:
            nid = u.get("current_node_id", "")
            if nid:
                node_occupants.setdefault(nid, []).append(u)

    movement_events = []

    for unit in sorted_units:
        if unit.get("entity_kind") == "TOWER":
            continue
        if unit.get("status") != "ACTIVE" or unit.get("current_hp", 0) <= 0:
            continue

        team_id = str(unit.get("team_id", ""))
        speed = unit.get("movement", 1)
        if speed <= 0:
            continue

        curr_node = unit.get("current_node_id", "")
        if not curr_node:
            continue

        # Filter enemy active teams
        enemy_teams = {tid: t for tid, t in active_teams.items() if tid != team_id}
        target_team_id, target_base_node = resolve_unit_target(
            unit, enemy_teams, fallback_policy, game_map
        )

        if not target_team_id or not target_base_node:
            # Unit remains IDLE
            continue

        if unit.get("target_team_id") != target_team_id:
            movement_events.append({
                "type": "UNIT_RETARGETED", "entity_id": str(unit["id"]),
                "team_id": team_id, "target_team_id": target_team_id,
            })
        unit["target_team_id"] = target_team_id
        target_atk_pos = game_map.attack_position(target_base_node)
        anchor, base_node = game_map.nodes[target_atk_pos], game_map.nodes[target_base_node]
        if math.dist((anchor.x, anchor.y), (base_node.x, base_node.y)) > TROOP_BASE_ATTACK_RANGE:
            target_atk_pos = target_base_node
        if unit.get("unit_type_code") == "infantry":
            from apps.combat.siege import defending_towers, tower_approach_node
            from apps.combat.targeting import find_unit_target
            towers = defending_towers(sorted_units, target_team_id)
            if find_unit_target(unit, towers, game_map):
                continue
            if towers:
                target_tower = min(towers, key=lambda tower: (
                    game_map.distance(curr_node, tower["current_node_id"]), str(tower["id"])
                ))
                target_atk_pos = tower_approach_node(unit, target_tower, game_map)

        # If already at attack position, don't move further; prepare for base attack
        if curr_node == target_atk_pos:
            continue

        # Get full predefined path from current node to target attack position
        planned_path = game_map.path(curr_node, target_atk_pos)
        if not planned_path or len(planned_path) <= 1:
            continue

        # Advance along path by up to `speed` nodes
        # planned_path[0] is curr_node, planned_path[1] is next node
        actual_path = [curr_node]
        for step in range(1, min(speed + 1, len(planned_path))):
            next_node = planned_path[step]

            # Impassable node check
            map_node = game_map.nodes.get(next_node)
            if map_node and not map_node.is_passable:
                # Impassable node blocked
                break

            # Blocking rule (§9.2): check if an enemy unit occupies next_node
            occupants = node_occupants.get(next_node, [])
            enemy_blocking = any(str(occ.get("team_id")) != team_id for occ in occupants)

            if enemy_blocking:
                # Blocked by enemy unit on next node, stop before it
                break

            actual_path.append(next_node)

        final_node = actual_path[-1]
        if final_node != curr_node:
            # Update node occupancy tracking
            if curr_node in node_occupants and unit in node_occupants[curr_node]:
                node_occupants[curr_node].remove(unit)
            node_occupants.setdefault(final_node, []).append(unit)

            unit["current_node_id"] = final_node
            movement_events.append({
                "type": "UNIT_MOVED",
                "entity_id": str(unit["id"]),
                "team_id": team_id,
                "from_node": curr_node,
                "to_node": final_node,
                "reached_attack_position": (final_node == target_atk_pos),
            })

    return sorted_units, movement_events
