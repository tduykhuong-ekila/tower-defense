"""
Targeting rules for defensive towers and combat units (§10.3, D5).
Pure deterministic functions.
"""

from typing import Any, Dict, List, Optional

from apps.combat.balance import TOWER_ATTACK_RANGE
from apps.combat.map import GameMap


def is_unit_target_allowed(attacker, target):
    """Attack orders engage the assigned team; base defenders engage every enemy."""
    if attacker.get("entity_kind") == "UNIT" and target.get("entity_kind") == "UNIT":
        if attacker.get("simulation_state", {}).get("order") == "DEFEND_BASE":
            return str(target.get("team_id")) != str(attacker.get("team_id"))
        target_team = attacker.get("target_team_id")
        return bool(target_team) and str(target.get("team_id")) == str(target_team)
    return True


def find_tower_target(
    tower: Dict[str, Any],
    enemy_units: List[Dict[str, Any]],
    game_map: GameMap,
    defended_base_node: str,
) -> Optional[Dict[str, Any]]:
    """
    Defensive Tower Targeting Priority (§10.3, Architectural Decision D5):
    1. Enemy unit closest to the defended base (measured by remaining nodes to the base).
    2. Tie-breaker: Deterministic smaller entity ID (string comparison).
    3. Unit must be within tower's range.
    4. Tower must not be disabled (e.g. by EMP).
    """
    if tower.get("is_disabled", False):
        return None

    tower_range = tower.get("range", TOWER_ATTACK_RANGE)
    tower_node = tower.get("current_node_id", "")
    if (not tower_node or tower_range <= 0
            or (tower_node not in game_map.nodes
                and not tower.get("simulation_state", {}).get("world_position"))):
        return None

    from apps.combat.continuous import target_distance

    valid_candidates = []

    for enemy in enemy_units:
        enemy_node = enemy.get("current_node_id", "")
        if not enemy_node or enemy.get("current_hp", 0) <= 0:
            continue

        # Same physical ellipse as placement/inspection and realtime combat.
        dist_to_tower = target_distance(tower, enemy, game_map)
        if dist_to_tower <= tower_range:
            # D5: Remaining distance to defended base
            remaining_to_base = game_map.distance(enemy_node, defended_base_node)
            valid_candidates.append({
                "entity": enemy,
                "remaining_distance": remaining_to_base,
                "entity_id": str(enemy["id"]),
            })

    if not valid_candidates:
        return None

    # Sort deterministically: 1. remaining_distance ASC, 2. entity_id ASC
    valid_candidates.sort(key=lambda c: (c["remaining_distance"], c["entity_id"]))
    return valid_candidates[0]["entity"]


def find_unit_target(
    attacker: Dict[str, Any],
    enemy_units: List[Dict[str, Any]],
    game_map: GameMap,
) -> Optional[Dict[str, Any]]:
    """
    Combat Unit Targeting:
    Target enemy combat units within attack range.
    Prioritize closest enemy unit, tie-break by entity_id.
    Fractional range is compared directly to graph distance without rounding.
    """
    if attacker.get("current_hp", 0) <= 0:
        return None

    attacker_range = attacker.get("range", 1)
    attacker_node = attacker.get("current_node_id", "")
    if not attacker_node or attacker_range <= 0:
        return None

    valid_candidates = []
    from apps.combat.continuous import target_distance

    for enemy in enemy_units:
        enemy_node = enemy.get("current_node_id", "")
        if not enemy_node or enemy.get("current_hp", 0) <= 0:
            continue

        if not is_unit_target_allowed(attacker, enemy):
            continue

        # Grid towers occupy a real footprint; attackers needn't reach the
        # anchor itself before the tower becomes a valid target.
        if (enemy.get("entity_kind") == "TOWER"
                or attacker.get("simulation_state", {}).get("grid_placement")
                or enemy.get("simulation_state", {}).get("grid_placement")):
            dist = target_distance(attacker, enemy, game_map)
        else:
            dist = game_map.distance(attacker_node, enemy_node)
        if dist <= attacker_range:
            valid_candidates.append({
                "entity": enemy,
                "distance": dist,
                "entity_id": str(enemy["id"]),
            })

    if not valid_candidates:
        return None

    # Deterministic sort: closest first, then smaller entity_id
    valid_candidates.sort(key=lambda c: (
        0 if attacker.get("unit_type_code") == "infantry" and c["entity"].get("entity_kind") == "TOWER" else 1,
        c["distance"], c["entity_id"]))
    return valid_candidates[0]["entity"]
