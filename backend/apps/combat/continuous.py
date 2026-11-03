"""Pure fixed-step combat. Edges use actual map-coordinate lengths, never hop jumps."""
import math
from functools import lru_cache

from apps.combat.balance import (
    CLIMAX_TOWER_RESILIENCE_MULTIPLIER,
    TROOP_BASE_ATTACK_RANGE,
    attack_cooldown,
    attack_damage,
    climax_active,
    combat_attacks_enabled,
    troop_tower_firing_radius,
)
from apps.combat.damage import apply_damage_to_base, apply_damage_to_entity
from apps.combat.engine import RoundResult
from apps.combat.formation import initialize_route, redirect_route, route_lengths
from apps.combat.map import get_game_map
from apps.combat.movement import resolve_unit_target
from apps.combat.navigation import move_independently
from apps.combat.rewards import award_kill_reward
from apps.combat.siege import defending_towers, plan_siege
from apps.combat.targeting import is_unit_target_allowed

BASE_DEFENSE_RADIUS = 3


def range_position(entity, game_map):
    """Identical physical point for range checks and their spatial broad phase."""
    sim = entity.get("simulation_state", {})
    point = sim.get("world_position")
    if point:
        return point["x"], point["y"]
    node = game_map.nodes[entity["current_node_id"]]
    next_node = game_map.nodes.get(sim.get("next_node_id"))
    t = sim.get("edge_progress", 0)
    return ((node.x + (next_node.x - node.x) * t, node.y + (next_node.y - node.y) * t)
            if next_node else (node.x, node.y))


def base_in_range(entity, base_node, game_map):
    """Base damage always checks the actual troop position, never a lane ID."""
    if entity.get("range", 1) <= 0:
        return False
    node = game_map.nodes[base_node]
    return math.dist(range_position(entity, game_map), (node.x, node.y)) <= TROOP_BASE_ATTACK_RANGE


def distance(a, b, game_map):
    """Continuous graph range in existing hop units, including partial edges."""
    sa, sb = a.get("simulation_state", {}), b.get("simulation_state", {})
    if sa.get("grid_placement") or sb.get("grid_placement"):
        return math.dist(range_position(a, game_map), range_position(b, game_map)) / 80
    an, bn = a["current_node_id"], b["current_node_id"]
    ad, bd = sa.get("next_node_id"), sb.get("next_node_id")
    ap, bp = sa.get("edge_progress", 0), sb.get("edge_progress", 0)
    # Tower-slot edges describe coverage of the adjacent road span, not a
    # mandatory detour through its endpoints. A range-1 troop stays in range
    # between two covered nodes even if a tick never lands on either node.
    if a.get("entity_kind") == "TOWER" and bd:
        if game_map.distance(an, bn) == game_map.distance(an, bd) == 1:
            return 1.0
    if b.get("entity_kind") == "TOWER" and ad:
        if game_map.distance(bn, an) == game_map.distance(bn, ad) == 1:
            return 1.0
    if not ad and not bd:
        return game_map.distance(an, bn)
    if ad and (an, ad) == (bn, bd):
        return abs(ap - bp)
    if ad and (an, ad) == (bd, bn):
        return abs(ap - (1 - bp))
    d = game_map.distance
    if not bd:
        return min(d(an, bn) + ap, d(ad, bn) + 1 - ap)
    if not ad:
        return min(d(an, bn) + bp, d(an, bd) + 1 - bp)
    return min(d(an, bn) + ap + bp, d(an, bd) + ap + 1 - bp,
               d(ad, bn) + 1 - ap + bp, d(ad, bd) + 2 - ap - bp)


def target_distance(attacker, target, game_map):
    """Physical tower combat; troops fire from inside the target tower ellipse."""
    if attacker.get("entity_kind") == "TOWER":
        # Phaser projects a radius-80 map circle into the displayed 120 x 68.8
        # ellipse. Include edge progress and physical passing offsets.
        return math.dist(range_position(attacker, game_map), range_position(target, game_map)) / 80
    if target.get("entity_kind") == "TOWER":
        radius = troop_tower_firing_radius(attacker, game_map, target)
        if radius <= 0:
            return math.inf
        gap = math.dist(range_position(attacker, game_map), range_position(target, game_map))
        return gap / radius * attacker.get("range", 1)
    return distance(attacker, target, game_map)


@lru_cache(maxsize=4096)
def nearby_nodes(game_map, node, radius):
    return tuple(sorted(game_map.nodes_in_range(node, radius)))


class EntityIndex(dict):
    def __init__(self):
        super().__init__()
        self.grid_towers = []
        self.towers = []
        self.entities = []
        self.physical = None
        self.physical_towers = None

    def physical_nearby(self, attacker, game_map, towers_only=False):
        # Build once per movement/attack phase. Buckets only prune candidates;
        # exact range, allegiance, status and HP remain checked below.
        size = 80
        if self.physical is None:
            self.physical, self.physical_towers = {}, {}
            for entity in self.entities:
                x, y = range_position(entity, game_map)
                key = math.floor(x / size), math.floor(y / size)
                self.physical.setdefault(key, []).append(entity)
                if entity.get("entity_kind") == "TOWER":
                    self.physical_towers.setdefault(key, []).append(entity)
        x, y = range_position(attacker, game_map)
        radius = attacker.get("range", 1) * 80
        if self.towers and attacker.get("entity_kind") == "UNIT":
            radius = troop_tower_firing_radius(attacker, game_map)
        buckets = self.physical_towers if towers_only else self.physical
        return [entity
                for col in range(math.floor((x-radius)/size), math.floor((x+radius)/size)+1)
                for row in range(math.floor((y-radius)/size), math.floor((y+radius)/size)+1)
                for entity in buckets.get((col,row), ())]


def entity_index(entities):
    index = EntityIndex()
    for e in entities:
        index.entities.append(e)
        if e.get("entity_kind") == "TOWER":
            index.towers.append(e)
        if e.get("simulation_state", {}).get("grid_placement"):
            index.grid_towers.append(e)
        for node in (e["current_node_id"], e.get("simulation_state", {}).get("next_node_id")):
            if node:
                index.setdefault(node, {}).setdefault(e["team_id"], []).append(e)
    return index


def candidates(attacker, index, game_map, kinds):
    grid_attacker = (attacker.get("entity_kind") == "TOWER"
                     or attacker.get("simulation_state", {}).get("grid_placement"))
    if grid_attacker and isinstance(index, EntityIndex):
        nearby = {e["id"]: e for e in index.physical_nearby(attacker, game_map)}
    else:
        nodes = nearby_nodes(game_map, attacker["current_node_id"], math.ceil(attacker.get("range", 1)) + 1)
        nearby = {e["id"]: e for node in nodes
                  for team_id, group in index.get(node, {}).items() if team_id != attacker["team_id"]
                  for e in group}
        if isinstance(index, EntityIndex) and index.towers:
            for entity in index.physical_nearby(attacker, game_map, towers_only=True):
                nearby[entity["id"]] = entity
        elif grid_attacker:
            # Compatibility for callers supplying a plain graph index.
            for groups in index.values():
                for group in groups.values():
                    for entity in group:
                        nearby[entity["id"]] = entity
    return [e for e in nearby.values() if e["entity_kind"] in kinds
            and e["team_id"] != attacker["team_id"]
            and is_unit_target_allowed(attacker, e)
            and e["status"] in ("ACTIVE", "DISABLED") and e["current_hp"] > 0
            and e.get("simulation_state", {}).get("movement_zone") != "STAGING"
            and target_distance(attacker, e, game_map) <= attacker.get("range", 1)]


class ContinuousEngine:
    @classmethod
    def step(cls, state, dt):
        current = state.deep_copy()
        events = []
        if current.is_paused:
            return RoundResult(current.round_number, [], current, [], None, False)
        config = current.configuration
        priority = config.get("troop_target_priority", ["TOWER", "UNIT"])

        def troop_target_order(attacker, target):
            kind = target["entity_kind"]
            target_rank = (0 if kind == "TOWER" else 1) if attacker.get("unit_type_code") in ("tank", "artillery") else (
                priority.index(kind) if kind in priority else len(priority)
            )
            return (target_rank,
                    distance(attacker, target, game_map), target["id"])
        game_map = get_game_map(len(current.teams), config.get("arena_layout_version", 3))

        def acquire(attacker, index, kinds, cache, tower=False):
            # Physical offsets matter when a grid tower is a candidate.
            # Cache only for this immutable movement phase or simultaneous tier.
            sim = attacker["simulation_state"]
            key = (attacker["id"] if tower or sim.get("grid_placement") else attacker["team_id"], attacker["current_node_id"], sim.get("next_node_id"),
                   sim.get("edge_progress", 0), attacker.get("range", 1), tuple(kinds), attacker.get("target_team_id"), sim.get("order"),
                   tuple(sim.get("world_position", {}).get(axis) for axis in ("x", "y"))
                   if getattr(index, "towers", []) else None)
            if key not in cache:
                enemies = candidates(attacker, index, game_map, kinds)
                if sim.get("order") == "DEFEND_BASE":
                    home = {"current_node_id": game_map.get_base_node(current.teams[attacker["team_id"]]["team_index"])}
                    enemies = [enemy for enemy in enemies if enemy["entity_kind"] == "UNIT"
                               and distance(enemy, home, game_map) <= BASE_DEFENSE_RADIUS
                               and distance(attacker, home, game_map) <= BASE_DEFENSE_RADIUS]
                if tower:
                    base_node = game_map.get_base_node(current.teams[attacker["team_id"]]["team_index"])
                    def order(enemy):
                        return (distance(enemy, {"current_node_id": base_node}, game_map), enemy["id"])
                else:
                    def order(enemy):
                        return troop_target_order(attacker, enemy)
                cache[key] = min(enemies, key=order, default=None)
            return cache[key]

        entities = sorted(current.entities, key=lambda e: (e["team_id"], e["id"]))
        baseline = config.get("movement_baseline_round_seconds", 30)
        for tid in current.teams:
            current.combat_stats.setdefault(tid, {"bases_destroyed": 0, "base_damage_dealt": 0})
        for e in entities:
            sim = e.setdefault("simulation_state", {})
            remaining = sim.get("attack_remaining", 0)
            # Retain Infantry's fractional overshoot for the next eligible tick.
            # An idle/ready unit must not accumulate a backlog of overdue shots.
            sim["attack_remaining"] = (remaining - dt if remaining > 0 else 0) if e.get("unit_type_code") == "infantry" else max(0, remaining - dt)
            if e["status"] == "DISABLED":
                sim["disabled_remaining"] = sim.get("disabled_remaining", baseline) - dt
                if sim["disabled_remaining"] <= 0:
                    e["status"] = "ACTIVE"
                    sim.pop("disabled_remaining", None)
                    events.append({"type": "TOWER_ENABLED", "entity_id": e["id"]})

        # Shield duration/cooldown uses seconds, never a decrement per 200 ms tick.
        shields = config.setdefault("continuous_shields", {})
        for tid, t in current.teams.items():
            if t.get("base_shield", 0) > 0:
                shields[tid] = shields.get(tid, baseline * 2) - dt
                if shields[tid] <= 0:
                    t["base_shield"] = 0
                    events.append({"type": "SHIELD_EXPIRED", "team_id": tid})

        # Movement precedes tower/unit combat, preserving the existing ordering.
        active_teams = {tid: t for tid, t in current.teams.items()
                        if t["status"] == "ACTIVE" and t["base_hp"] > 0}
        movement_index = entity_index(entities)
        movement_targets = {}
        defenses = {tid: defending_towers(entities, tid) for tid in active_teams}
        initial_staging = (
            config.get("gameplay_mode") == "CONTINUOUS"
            and current.round_number == 1
            and config.get("timer_state", {}).get("round_phase") != "BATTLE"
        )
        movers, stopped, queued = [], set(), set()
        guard_threats = {}
        for ordinal, e in enumerate(entities, 1):
            if e["entity_kind"] != "UNIT" or e["status"] not in ("ACTIVE", "QUEUED") or e["current_hp"] <= 0:
                continue
            sim = e["simulation_state"]
            sim.pop("base_attack_stop_distance", None)
            sim.setdefault("formation_order", ordinal)
            if e["status"] == "QUEUED":
                queued.add(e["id"])
            if initial_staging:
                sim["combat_state"], sim["attack_target_id"] = "IDLE", None
                stopped.add(e["id"])
                movers.append(e)
                continue
            if sim.get("order") == "DEFEND_BASE":
                # Defenders guard their own approach and intercept every hostile team.
                # The home radius bounds pursuit; no enemy base/tower is a target.
                home = game_map.get_base_node(current.teams[e["team_id"]]["team_index"])
                guard_node = game_map.attack_position(home)
                if e["team_id"] not in guard_threats:
                    threats = [enemy for enemy in entities
                               if enemy["entity_kind"] == "UNIT" and enemy["team_id"] != e["team_id"]
                               and enemy["status"] == "ACTIVE" and enemy["current_hp"] > 0
                               and enemy.get("simulation_state", {}).get("movement_zone") != "STAGING"
                               and distance(enemy, {"current_node_id": home}, game_map) <= BASE_DEFENSE_RADIUS]
                    guard_threats[e["team_id"]] = min(threats, key=lambda enemy: (
                        distance(enemy, {"current_node_id": home}, game_map), enemy["id"]), default=None)
                threat = guard_threats[e["team_id"]]
                target = acquire(e, movement_index, ("UNIT",), movement_targets)
                destination = threat["current_node_id"] if threat else guard_node
                if not sim.get("route_nodes") or sim["route_nodes"][-1] != destination:
                    redirect_route(e, destination, game_map)
                sim["combat_state"] = "ATTACKING" if target else "IDLE"
                sim["attack_target_id"] = target["id"] if target else None
                if target:
                    stopped.add(e["id"])
                movers.append(e)
                continue
            if sim.get("order") in ("RETREAT", "AT_RALLY"):
                if e.get("unit_type_code") == "infantry":
                    plan_siege(e, [], game_map)
                sim["combat_state"], sim["attack_target_id"] = "IDLE", None
                if sim["order"] == "AT_RALLY":
                    stopped.add(e["id"])
                movers.append(e)
                continue
            tid, base = resolve_unit_target(e, {k: t for k, t in active_teams.items() if k != e["team_id"]},
                                            config.get("fallback_policy", "RETARGET_NEAREST"), game_map)
            if e.get("target_team_id") != tid:
                e["target_team_id"] = tid
                events.append({"type": "UNIT_RETARGETED", "entity_id": e["id"], "target_team_id": tid})
            if base and not sim.get("route_nodes"):
                initialize_route(e, base, game_map)
            siege_target = plan_siege(e, defenses.get(tid, []), game_map) if e.get("unit_type_code") in ("infantry", "tank", "artillery") else None
            if base and not siege_target:
                initialize_route(e, base, game_map, approach_base=True)
                lengths = route_lengths(sim.get("route_nodes", []), game_map)
                # Stop on the road just inside range, allowing for the bounded
                # 12px cosmetic ground offset. Never move a saved unit backward.
                sim["base_attack_stop_distance"] = max(
                    sim.get("route_distance", 0), lengths[-1] - (TROOP_BASE_ATTACK_RANGE - 15), 0)
                if base_in_range(e, base, game_map):
                    stopped.add(e["id"])
            target = None if sim.get("movement_zone") == "STAGING" or sim.get("staging_distance") else acquire(e, movement_index, ("UNIT", "TOWER"), movement_targets)
            sim["combat_state"] = "ATTACKING" if target else "IDLE"
            sim["attack_target_id"] = target["id"] if target else None
            if not base or target:
                stopped.add(e["id"])
            movers.append(e)
        move_independently(movers, game_map, config, dt, stopped)
        for e in movers:
            sim = e["simulation_state"]
            if sim.get("order") == "RETREAT" and e["current_node_id"] == sim.get("destination_rally_id") and not sim.get("next_node_id"):
                sim.update(order="AT_RALLY", movement_state="STOPPED")
                events.append({"type": "UNIT_RETURNED", "entity_id": e["id"], "team_id": e["team_id"]})
            if e["id"] in queued and e["status"] == "ACTIVE":
                events.append({"type": "UNIT_SPAWNED", "entity_id": e["id"], "node_id": e["current_node_id"]})

        # Towers fire first; simultaneous intents within each tier resolve together.
        attack_index = entity_index(entities)
        for kind in (("TOWER", "UNIT") if combat_attacks_enabled(config) else ()):
            intents = []
            targets = {}
            for e in entities:
                if e["entity_kind"] != kind or e["status"] != "ACTIVE" or e["current_hp"] <= 0:
                    continue
                sim, team = e["simulation_state"], current.teams[e["team_id"]]
                if kind == "UNIT" and sim.get("order") in ("RETREAT", "AT_RALLY"):
                    sim["combat_state"], sim["attack_target_id"] = "IDLE", None
                    continue
                if e.get("unit_type_code") == "shield_generator":
                    if sim["attack_remaining"] > 1e-9:
                        continue
                    if team["base_shield"] <= 0:
                        team["base_shield"] = e.get("shield_amount", 40)
                        shields[e["team_id"]] = baseline * 2
                        sim["attack_remaining"] = e.get("cooldown_rounds", 2) * baseline
                        events.append({"type": "SHIELD_GENERATED", "team_id": e["team_id"],
                                       "shield_amount": team["base_shield"]})
                    continue
                if e.get("damage", 0) <= 0:
                    continue
                target_team = current.teams.get(e.get("target_team_id")) if kind == "UNIT" else None
                at_base = (target_team and target_team["status"] == "ACTIVE" and target_team["base_hp"] > 0
                           and sim.get("movement_zone") != "STAGING"
                           and base_in_range(e, game_map.get_base_node(target_team["team_index"]), game_map))
                if e.get("unit_type_code") == "infantry" and (
                        defenses.get(e.get("target_team_id")) or sim.get("movement_zone") == "STAGING"):
                    at_base = False
                if e.get("unit_type_code") in ("tank", "artillery") and defenses.get(e.get("target_team_id")):
                    # Tanks and Artillery must finish the target team's surviving
                    # towers before switching to direct base damage.
                    at_base = False
                target_kinds = (("TOWER",) if at_base and e.get("unit_type_code") != "infantry" else ("UNIT", "TOWER")) if kind == "UNIT" else ("UNIT",)
                target = acquire(e, attack_index, target_kinds, targets, kind == "TOWER")
                if target or at_base:
                    sim["combat_state"] = "ATTACKING"
                    sim["attack_target_id"] = target["id"] if target else f"base:{e['target_team_id']}"
                    if sim["attack_remaining"] > 1e-9:
                        continue
                    overshoot = min(0, sim["attack_remaining"]) if e.get("unit_type_code") == "infantry" else 0
                    cooldown = attack_cooldown(e, config)
                    # Short custom Infantry cooldowns can span several eligible
                    # shots in one tick. Each intent/event is a distinct shot.
                    shots = 1 + math.floor((-overshoot + 1e-9) / cooldown) if e.get("unit_type_code") == "infantry" else 1
                    sim["attack_remaining"] = cooldown * shots + overshoot
                    for _ in range(shots):
                        damage = attack_damage(e)
                        if target and target.get("entity_kind") == "TOWER" and climax_active(config):
                            damage = math.floor(damage / CLIMAX_TOWER_RESILIENCE_MULTIPLIER + 1e-9)
                        intents.append((e, target, target_team, damage))
                else:
                    sim["combat_state"], sim["attack_target_id"] = "IDLE", None
            for e, target, target_team, damage in intents:
                if target:
                    if target["current_hp"] <= 0:
                        continue  # Earlier simultaneous hits already destroyed it.
                    absorbed, hp_damage, shield, hp = apply_damage_to_entity(target["current_hp"], target.get("current_shield", 0), damage)
                    target["current_hp"], target["current_shield"] = hp, shield
                    if hp == 0:
                        award_kill_reward(current.teams, e["team_id"], target, events)
                    events.append({"type": "TOWER_ATTACKED" if kind == "TOWER" else "UNIT_ATTACKED",
                                   "attacker_id": e["id"], "tower_id": e["id"] if kind == "TOWER" else None,
                                   "attacker_team_id": e["team_id"], "target_entity_id": target["id"],
                                   "target_team_id": target["team_id"], "damage": damage,
                                   "hp_damage": hp_damage, "shield_absorbed": absorbed,
                                   "target_hp_remaining": hp, "target_shield_remaining": shield})
                else:
                    if target_team["base_hp"] <= 0:
                        continue
                    absorbed, hp_damage, shield, hp = apply_damage_to_base(target_team["base_hp"], target_team["base_shield"], damage)
                    target_team["base_hp"], target_team["base_shield"] = hp, shield
                    current.combat_stats[e["team_id"]]["base_damage_dealt"] += hp_damage + absorbed
                    events.append({"type": "BASE_DAMAGED", "unit_id": e["id"], "attacker_team_id": e["team_id"],
                                   "target_team_id": e["target_team_id"], "damage": damage, "hp_damage": hp_damage,
                                   "shield_absorbed": absorbed, "base_hp_remaining": hp, "base_shield_remaining": shield})
            for e in entities:
                if e["status"] in ("ACTIVE", "DISABLED") and e["current_hp"] <= 0:
                    e["status"] = "DESTROYED"
                    events.append({"type": "ENTITY_DESTROYED", "entity_id": e["id"], "team_id": e["team_id"]})

        eliminated = []
        for tid, team in sorted(current.teams.items()):
            if team["status"] == "ACTIVE" and team["base_hp"] <= 0:
                team["status"] = "ELIMINATED"
                eliminated.append(tid)
                events.extend([{"type": "BASE_DESTROYED", "team_id": tid}, {"type": "TEAM_ELIMINATED", "team_id": tid}])
                killer = next((ev["attacker_team_id"] for ev in reversed(events)
                               if ev["type"] == "BASE_DAMAGED" and ev["target_team_id"] == tid and ev["hp_damage"] > 0), None)
                if killer:
                    current.combat_stats[killer]["bases_destroyed"] += 1
                for e in entities:
                    if e["team_id"] == tid and e["status"] != "DESTROYED":
                        e["status"], e["current_hp"] = "DESTROYED", 0
                        events.append({"type": "ENTITY_DESTROYED", "entity_id": e["id"], "team_id": tid})
        alive = [tid for tid, t in current.teams.items() if t["status"] == "ACTIVE"]
        for event in events:
            event["round_number"] = current.round_number
        current.entities = entities
        return RoundResult(current.round_number, events, current, eliminated,
                           alive[0] if len(alive) == 1 else None, len(alive) <= 1)
