"""One conversion boundary; catalog stats remain the original balancing baseline."""
import math
from datetime import datetime

# Dimensionless multiplier of catalog hops/round, converted to map units/second.
TROOP_MOVEMENT_SPEED = 4
INFANTRY_MOVEMENT_SPEED = 5.5
INFANTRY_ATTACK_RATE_MULTIPLIER = 1.5
INFANTRY_MAX_HP = 80
ARTILLERY_MOVEMENT_SPEED = 5
ARTILLERY_MAX_HP = 80
ARTILLERY_ATTACK_RANGE = 1.5
MG_TOWER_ATTACK_COOLDOWN_SECONDS = 1.8
CANNON_TOWER_BASE_DAMAGE = 20
TOWER_ATTACK_RANGE = 3
CANNON_TOWER_ATTACK_RANGE = TOWER_ATTACK_RANGE
MOBILE_TROOP_HP = 100
TANK_MAX_HP = 110
TROOP_DAMAGE_MULTIPLIER = 0.5
CLIMAX_TOWER_RESILIENCE_MULTIPLIER = 1.5
CLIMAX_MOBILE_FIRE_RATE_MULTIPLIER = 1.10
CLIMAX_DURATION_SECONDS = {1: 15, 2: 20, 3: 30}
REFERENCE_HOP_LENGTH = 80.0
# A placed tower is a 96px structure, not a point at its anchor. Let attackers
# reach its footprint by half a reference hop beyond their center-to-center range.
GRID_TOWER_TARGET_RANGE_BONUS = 0.5
TROOP_TOWER_RANGE_RATIO = 0.9
TROOP_TOWER_MAX_RANGE = 200.0
TROOP_BASE_ATTACK_RANGE = 200.0


def troop_tower_range_unit(game_map):
    """One troop weapon hop follows arena scaling, just like road graph hops.

    Towers keep their fixed physical ellipse; the footprint allowance stays at
    its artwork size instead of growing with the arena.
    """
    return REFERENCE_HOP_LENGTH * game_map.layout_scale


def troop_tower_firing_radius(entity, game_map, target=None):
    """Troops must enter the target tower's ellipse before firing back."""
    if entity.get("range", 1) <= 0:
        return 0.0
    radius = (entity.get("range", 1) * troop_tower_range_unit(game_map)
              + GRID_TOWER_TARGET_RANGE_BONUS * REFERENCE_HOP_LENGTH)
    if target is not None:
        tower_range = target.get("range", TOWER_ATTACK_RANGE)
        # Support structures have no offensive ellipse of their own.
        if tower_range <= 0:
            tower_range = TOWER_ATTACK_RANGE
        radius = min(radius, TROOP_TOWER_MAX_RANGE,
                     tower_range * REFERENCE_HOP_LENGTH * TROOP_TOWER_RANGE_RATIO)
    return radius


def troop_max_hp(code, stats):
    if code == "infantry":
        return INFANTRY_MAX_HP
    if code == "artillery":
        return ARTILLERY_MAX_HP
    if code == "tank":
        return TANK_MAX_HP
    return MOBILE_TROOP_HP if stats.get("movement", 1) > 0 else stats.get("hp", 100)


def entity_attack_range(entity):
    """Per-instance snapshot survives catalog updates and reconnects (fractional hops)."""
    return entity.simulation_state.get("attack_range", entity.unit_type.base_stats.get("range", 1))


def movement_multiplier(code):
    return {"infantry": INFANTRY_MOVEMENT_SPEED, "artillery": ARTILLERY_MOVEMENT_SPEED}.get(code, TROOP_MOVEMENT_SPEED)


def movement_speed(stats, config):
    speed = movement_multiplier(stats.get("unit_type_code"))
    return (stats.get("movement", 1) * stats.get("simulation_state", {}).get("reference_hop_length", REFERENCE_HOP_LENGTH)
            / config.get("movement_baseline_round_seconds", 30) * speed)


def attack_cooldown(entity, config):
    default_seconds = (
        MG_TOWER_ATTACK_COOLDOWN_SECONDS
        if entity.get("unit_type_code") == "mg_tower"
        else config.get("attack_cooldown_seconds", 2)
    )
    seconds = entity.get("attack_cooldown_seconds", default_seconds)
    from apps.units.upgrades import modifiers
    seconds /= modifiers(entity.get("level", 1), entity.get("unit_type_code"))["attack_rate"]
    code = entity.get("unit_type_code")
    if code == "infantry":
        seconds /= INFANTRY_ATTACK_RATE_MULTIPLIER
    if code in ("infantry", "tank") and climax_active(config):
        seconds /= CLIMAX_MOBILE_FIRE_RATE_MULTIPLIER
    return round(seconds, 2)


def climax_active(config):
    """True during the final configured seconds of a continuous battle round."""
    if config.get("gameplay_mode") != "CONTINUOUS":
        return False
    timer = config.get("timer_state", {})
    if timer.get("round_phase") != "BATTLE":
        return False
    round_number = config.get("current_round", 1)
    total_rounds = config.get("total_rounds", 3)
    duration = 30 if round_number >= total_rounds else CLIMAX_DURATION_SECONDS.get(round_number)
    end_value = timer.get("phase_ends_at")
    now_value = timer.get("simulation_at")
    if not duration or not end_value or not now_value:
        return False
    try:
        remaining = (datetime.fromisoformat(end_value) - datetime.fromisoformat(now_value)).total_seconds()
    except (TypeError, ValueError):
        return False
    return 0 < remaining <= duration


def combat_attacks_enabled(config):
    """Initial preparation is staging only; later prep stays continuous."""
    timer = config.get("timer_state", {})
    if (config.get("gameplay_mode") == "CONTINUOUS"
            and config.get("current_round", 1) == 1
            and timer.get("round_phase") != "BATTLE"):
        return False
    return True


def attack_damage(entity):
    """Integer HP: carry fractional damage between attacks, including across restarts.

    Base multiplier precedes upgrades. Towers keep the legacy floor-once policy.
    """
    from apps.units.upgrades import modifiers
    upgrade = modifiers(entity.get("level", 1), entity.get("unit_type_code"))["damage"]
    raw = round(entity.get("damage", 0) * upgrade, 2)
    if entity["entity_kind"] != "UNIT":
        return max(1, math.floor(raw)) if raw else 0
    state = entity["simulation_state"]
    raw = round(raw * TROOP_DAMAGE_MULTIPLIER, 2) + state.get("damage_remainder", 0)
    damage = math.floor(raw + 1e-9)
    state["damage_remainder"] = round(raw - damage, 8)
    return damage


def inspection_stats(entity, config=None):
    """Public effective stats using the combat engine's conversions, without mutating carry."""
    config = entity.match.configuration if config is None else config
    from apps.units.upgrades import effective_stats
    stats = effective_stats(entity.unit_type, entity.level, config)
    return {key: stats[key] for key in ("damage", "attack_interval_seconds")}
