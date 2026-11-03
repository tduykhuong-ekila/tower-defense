"""Authoritative team upgrade balance; base catalog and range snapshots stay intact."""

import math

DEFAULT_UPGRADE_LEVEL = 1
MAX_UPGRADE_LEVEL = 3
LEVEL_MODIFIERS = {
    1: {"hp": 1.0, "damage": 1.0, "attack_rate": 1.0},
    2: {"hp": 1.15, "damage": 1.10, "attack_rate": 1.05},
    3: {"hp": 1.30, "damage": 1.20, "attack_rate": 1.10},
}
LEVEL_3_TROOP_MODIFIERS = {"hp": 1.60, "damage": 1.60, "attack_rate": 1.25}
UPGRADE_COSTS = {
    "infantry": [50, 100],
    "tank": [80, 160],
    "artillery": [90, 180],
    "tower": [70, 140],
}


def modifiers(level, unit_code=None):
    level = max(DEFAULT_UPGRADE_LEVEL, min(MAX_UPGRADE_LEVEL, int(level)))
    if level == 3 and unit_code in ("infantry", "artillery"):
        return LEVEL_3_TROOP_MODIFIERS
    return LEVEL_MODIFIERS[level]


def eligible(unit):
    return unit.code in ("infantry", "tank", "artillery") or unit.category == "TOWER"


def team_level(team, unit):
    if not team or not eligible(unit):
        return DEFAULT_UPGRADE_LEVEL
    from apps.units.models import TeamUnitUpgrade

    return min(MAX_UPGRADE_LEVEL, (
        TeamUnitUpgrade.objects.filter(team=team, unit_type=unit)
        .values_list("level", flat=True)
        .first()
        or DEFAULT_UPGRADE_LEVEL
    ))


def upgrade_cost(unit, level, config=None):
    if level < DEFAULT_UPGRADE_LEVEL or level >= MAX_UPGRADE_LEVEL or not eligible(unit):
        return None
    key = "tower" if unit.category == "TOWER" else unit.code
    return (
        (config or {}).get("team_upgrade_costs", {}).get(unit.code, UPGRADE_COSTS[key])[level - 1]
    )


def effective_stats(unit, level=1, config=None):
    from apps.combat.balance import (
        TROOP_DAMAGE_MULTIPLIER,
        attack_cooldown,
        movement_multiplier,
        troop_max_hp,
    )

    config = config or {}
    base = unit.base_stats or {}
    mod = modifiers(level, unit.code)
    hp = troop_max_hp(unit.code, base) if unit.category == "UNIT" else base.get("hp", 100)
    damage = base.get("damage", 0) * mod["damage"]
    continuous = config.get("gameplay_mode") == "CONTINUOUS"
    damage = (
        damage * TROOP_DAMAGE_MULTIPLIER
        if continuous and unit.category == "UNIT"
        else math.floor(damage + 1e-9)
    )
    damage = round(damage, 2)
    return {
        "hp": math.floor(hp * mod["hp"] + 0.5),
        "damage": damage,
        "range": base.get("range", 1),
        "movement_speed": movement_multiplier(unit.code) if unit.category == "UNIT" else 0,
        "attack_rate_multiplier": round(mod["attack_rate"], 2),
        "attack_interval_seconds": attack_cooldown(
            {**base, "unit_type_code": unit.code, "level": level}, config
        )
        if continuous and damage
        else None,
        "shield": base.get("shield", 0),
    }
