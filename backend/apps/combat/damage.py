"""
Damage calculation and shield absorption logic (§10.2, §10.4, D7).
Pure deterministic functions.
"""

import math
from typing import Tuple


def calculate_damage(base_damage: int, multiplier: float = 1.0) -> int:
    """
    §10.2 Base formula:
    final_damage = max(1, floor(base_damage * damage_multiplier))
    Multiplier: default 1.0, upgraded tower 1.25.
    """
    raw = math.floor(base_damage * multiplier)
    return max(1, int(raw))


def apply_damage_to_base(
    current_hp: int,
    current_shield: int,
    incoming_damage: int,
) -> Tuple[int, int, int, int]:
    """
    §10.4: Damage is absorbed by shield first, then base HP.
    HP never drops below 0.
    Returns:
      (shield_absorbed, hp_damage, new_shield, new_hp)
    """
    if incoming_damage <= 0:
        return 0, 0, current_shield, current_hp

    if current_shield >= incoming_damage:
        shield_absorbed = incoming_damage
        hp_damage = 0
        new_shield = current_shield - incoming_damage
        new_hp = current_hp
    else:
        shield_absorbed = current_shield
        remaining_damage = incoming_damage - current_shield
        new_shield = 0
        hp_damage = min(current_hp, remaining_damage)
        new_hp = max(0, current_hp - remaining_damage)

    return shield_absorbed, hp_damage, new_shield, new_hp


def apply_damage_to_entity(
    current_hp: int,
    current_shield: int,
    incoming_damage: int,
) -> Tuple[int, int, int, int]:
    """
    Applies damage to a combat unit or defensive tower.
    Returns:
      (shield_absorbed, hp_damage, new_shield, new_hp)
    """
    return apply_damage_to_base(current_hp, current_shield, incoming_damage)
