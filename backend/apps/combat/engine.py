"""
Pure, Deterministic, Server-Authoritative Combat Engine (§10, §19, FR-07, D3, D5, D6, D7, D8, D11).
No WebSocket/HTTP or DB dependencies inside domain logic.
Headless simulation ready.
"""

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from apps.combat.damage import apply_damage_to_base, apply_damage_to_entity, calculate_damage
from apps.combat.map import get_game_map
from apps.combat.movement import resolve_units_movement
from apps.combat.rewards import award_kill_reward
from apps.combat.targeting import find_tower_target, find_unit_target
from apps.units.upgrades import modifiers


@dataclass
class CombatState:
    round_number: int
    is_paused: bool
    teams: Dict[str, Dict[str, Any]]
    entities: List[Dict[str, Any]]
    actions: List[Dict[str, Any]]
    configuration: Dict[str, Any]
    combat_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)

    def deep_copy(self) -> "CombatState":
        return CombatState(
            round_number=self.round_number,
            is_paused=self.is_paused,
            teams=copy.deepcopy(self.teams),
            entities=copy.deepcopy(self.entities),
            actions=copy.deepcopy(self.actions),
            configuration=copy.deepcopy(self.configuration),
            combat_stats=copy.deepcopy(self.combat_stats),
        )


@dataclass
class RoundResult:
    round_number: int
    events: List[Dict[str, Any]]
    new_state: Optional[CombatState]
    eliminated_team_ids: List[str]
    winner_team_id: Optional[str]
    is_match_over: bool


class CombatEngine:
    """
    Executes one complete combat round according to the 12-step sequence in GDD §10.1:
    1. Close planning phase (lock actions).
    2. Validate queued actions.
    3. Deduct/confirm coins for accepted actions.
    4. Spawn new combat units (QUEUED -> ACTIVE at spawn node).
    5. Apply valid movement along predefined paths.
    6. Resolve defensive tower attacks.
    7. Resolve combat unit attacks.
    8. Apply shield effects and base damage.
    9. Remove destroyed units and structures.
    10. Check elimination & victory conditions.
    11. Award passive income.
    12. Publish authoritative state and event log.
    """

    @classmethod
    def resolve_round(cls, state: CombatState) -> RoundResult:
        # Create an isolated copy of the state
        current = state.deep_copy()
        events: List[Dict[str, Any]] = []

        round_num = current.round_number
        config = current.configuration
        fallback_policy = config.get("fallback_policy", "RETARGET_NEAREST")
        base_income = config.get("base_income_per_round", 10)
        if current.is_paused:
            return RoundResult(round_num, [], current, [], None, False)
        num_teams = len(current.teams)
        game_map = get_game_map(num_teams, config.get("arena_layout_version", 3))

        # Initialize combat_stats if missing
        for tid in current.teams:
            current.combat_stats.setdefault(tid, {"bases_destroyed": 0, "base_damage_dealt": 0})

        # Disabled towers stay in the state for this round and recover afterwards.
        disabled_ids = {e["id"] for e in current.entities if e.get("status") == "DISABLED"}

        # --- STEP 1 & 2 & 3: Close Planning, Validate & Confirm Actions ---
        # Deterministically sort actions by (team_id, action_id/sequence)
        sorted_actions = sorted(
            current.actions,
            key=lambda a: (str(a.get("team_id", "")), str(a.get("id", "")))
        )
        for act in sorted_actions:
            if act.get("status") == "QUEUED":
                act["status"] = "ACCEPTED"
                events.append({
                    "type": "ACTION_LOCKED",
                    "action_id": str(act.get("id", "")),
                    "team_id": str(act.get("team_id", "")),
                    "action_type": act.get("action_type", ""),
                })

        # --- STEP 4: Spawn New Combat Units ---
        # Transition units with status=QUEUED to ACTIVE at team spawn node
        for entity in current.entities:
            if entity.get("status") == "QUEUED" and entity.get("entity_kind") == "UNIT":
                tid = str(entity.get("team_id", ""))
                team_info = current.teams.get(tid, {})
                t_idx = team_info.get("team_index", 1)
                spawn_node = game_map.get_spawn_node(t_idx)

                entity["status"] = "ACTIVE"
                entity["current_node_id"] = spawn_node
                events.append({
                    "type": "UNIT_SPAWNED",
                    "entity_id": str(entity["id"]),
                    "team_id": tid,
                    "unit_type": entity.get("unit_type_code", ""),
                    "node_id": spawn_node,
                })

        # --- STEP 5: Apply Valid Movement ---
        active_teams_map = {
            tid: t for tid, t in current.teams.items()
            if t.get("status") == "ACTIVE" and t.get("base_hp", 0) > 0
        }
        current.entities, move_events = resolve_units_movement(
            current.entities,
            active_teams_map,
            game_map,
            fallback_policy=fallback_policy,
        )
        events.extend(move_events)

        # --- STEP 6: Defensive Tower Attacks ---
        # Sort towers deterministically by (team_id, entity_id)
        towers = [
            e for e in current.entities
            if e.get("entity_kind") == "TOWER" and e.get("status") == "ACTIVE" and e.get("current_hp", 0) > 0
        ]
        towers.sort(key=lambda t: (str(t.get("team_id", "")), str(t.get("id", ""))))

        for tower in towers:
            team_id = str(tower.get("team_id", ""))
            team_info = current.teams.get(team_id, {})
            t_idx = team_info.get("team_index", 1)
            defended_base_node = game_map.get_base_node(t_idx)

            # Special case: Shield Generator tower (§8.3, D7)
            if tower.get("unit_type_code") == "shield_generator":
                # Check cooldown and current shield
                cd = tower.get("cooldown_remaining", 0)
                curr_base_shield = team_info.get("base_shield", 0)
                if cd <= 0 and curr_base_shield <= 0:
                    team_info["base_shield"] = tower.get("shield_amount", 40)
                    team_info["shield_remaining_rounds"] = config.get("shield_duration_rounds", 2)
                    tower["cooldown_remaining"] = tower.get("cooldown_rounds", 2)
                    events.append({
                        "type": "SHIELD_GENERATED",
                        "team_id": team_id,
                        "tower_id": str(tower["id"]),
                        "shield_amount": team_info["base_shield"],
                    })
                elif cd > 0:
                    tower["cooldown_remaining"] = cd - 1
                continue

            # Standard attack tower (MG tower, Cannon tower)
            # Find eligible enemy units
            enemy_units = [
                u for u in current.entities
                if u.get("entity_kind") == "UNIT"
                and str(u.get("team_id", "")) != team_id
                and u.get("status") == "ACTIVE"
                and u.get("current_hp", 0) > 0
            ]

            target_unit = find_tower_target(tower, enemy_units, game_map, defended_base_node)
            if target_unit:
                # Calculate damage with upgrade multiplier (§10.2)
                base_dmg = tower.get("damage", 15)
                level = tower.get("level", 1)
                mult = modifiers(level, tower.get("unit_type_code"))["damage"]
                dmg = calculate_damage(base_dmg, mult)

                s_abs, hp_dmg, new_s, new_hp = apply_damage_to_entity(
                    target_unit.get("current_hp", 0),
                    target_unit.get("current_shield", 0),
                    dmg,
                )
                target_unit["current_shield"] = new_s
                target_unit["current_hp"] = new_hp
                if new_hp == 0:
                    award_kill_reward(current.teams, team_id, target_unit, events)

                events.append({
                    "type": "TOWER_ATTACKED",
                    "tower_id": str(tower["id"]),
                    "tower_team_id": team_id,
                    "target_entity_id": str(target_unit["id"]),
                    "target_team_id": str(target_unit.get("team_id", "")),
                    "damage": dmg,
                    "hp_damage": hp_dmg,
                    "target_hp_remaining": new_hp,
                    "target_shield_remaining": new_s,
                    "shield_absorbed": s_abs,
                })

        # --- STEP 7: Combat Unit Attacks ---
        # Combat units attack enemy units in their attack range. At the base
        # attack position, an in-range enemy tower must be attacked before the
        # unit can damage the base in Step 8.
        active_combat_units = [
            u for u in current.entities
            if u.get("entity_kind") == "UNIT" and u.get("status") == "ACTIVE" and u.get("current_hp", 0) > 0
        ]
        active_combat_units.sort(key=lambda u: (str(u.get("team_id", "")), str(u.get("id", ""))))
        units_blocked_from_base_by_tower = set()

        for attacker in active_combat_units:
            # Skip if destroyed earlier in this round's tower attacks
            if attacker.get("current_hp", 0) <= 0:
                continue

            att_team_id = str(attacker.get("team_id", ""))
            target_team_id = str(attacker.get("target_team_id", ""))
            target_team_info = current.teams.get(target_team_id, {})
            target_team_idx = target_team_info.get("team_index", 1)
            target_base_node = game_map.get_base_node(target_team_idx)

            from apps.combat.continuous import base_in_range
            at_base_attack_position = base_in_range(attacker, target_base_node, game_map)

            # On the base attack position, towers take precedence over the
            # base. Elsewhere, preserve the regular unit/tower target rules.
            other_units = [
                u for u in current.entities
                if u.get("entity_kind") in (("TOWER",) if at_base_attack_position else ("UNIT", "TOWER"))
                and str(u.get("team_id", "")) != att_team_id
                and u.get("status") in ("ACTIVE", "DISABLED")
                and u.get("current_hp", 0) > 0
            ]
            target_enemy = find_unit_target(attacker, other_units, game_map)
            if target_enemy:
                base_dmg = attacker.get("damage", 10)
                level = attacker.get("level", 1)
                mult = modifiers(level, attacker.get("unit_type_code"))["damage"]
                dmg = calculate_damage(base_dmg, mult)

                s_abs, hp_dmg, new_s, new_hp = apply_damage_to_entity(
                    target_enemy.get("current_hp", 0),
                    target_enemy.get("current_shield", 0),
                    dmg,
                )
                target_enemy["current_shield"] = new_s
                target_enemy["current_hp"] = new_hp
                if new_hp == 0:
                    award_kill_reward(current.teams, att_team_id, target_enemy, events)

                events.append({
                    "type": "UNIT_ATTACKED",
                    "attacker_id": str(attacker["id"]),
                    "attacker_team_id": att_team_id,
                    "target_entity_id": str(target_enemy["id"]),
                    "target_team_id": str(target_enemy.get("team_id", "")),
                    "damage": dmg,
                    "hp_damage": hp_dmg,
                    "target_hp_remaining": new_hp,
                    "target_shield_remaining": new_s,
                    "shield_absorbed": s_abs,
                })
                if at_base_attack_position and target_enemy.get("entity_kind") == "TOWER":
                    units_blocked_from_base_by_tower.add(str(attacker["id"]))

        # --- STEP 8: Shield Effects & Base Damage ---
        # Units at the base position deal damage only after clearing any
        # in-range tower, then are removed (§10.4).
        for unit in active_combat_units:
            # Must still be alive after Step 6 & 7
            if unit.get("current_hp", 0) <= 0:
                continue
            if str(unit.get("id", "")) in units_blocked_from_base_by_tower:
                continue
            if unit.get("unit_type_code") == "infantry":
                from apps.combat.siege import defending_towers
                if defending_towers(current.entities, unit.get("target_team_id")):
                    continue

            target_team_id = str(unit.get("target_team_id", ""))
            if not target_team_id or target_team_id not in current.teams:
                continue

            target_team_info = current.teams[target_team_id]
            if target_team_info.get("status") != "ACTIVE" or target_team_info.get("base_hp", 0) <= 0:
                continue
            target_team_idx = target_team_info.get("team_index", 1)
            target_base_node = game_map.get_base_node(target_team_idx)

            from apps.combat.continuous import base_in_range
            if base_in_range(unit, target_base_node, game_map):
                # Unit deals damage only inside physical weapon range
                base_dmg = unit.get("damage", 10)
                dmg = calculate_damage(base_dmg, modifiers(unit.get("level", 1), unit.get("unit_type_code"))["damage"])

                s_abs, hp_dmg, new_shield, new_hp = apply_damage_to_base(
                    target_team_info.get("base_hp", 0),
                    target_team_info.get("base_shield", 0),
                    dmg,
                )
                target_team_info["base_shield"] = new_shield
                target_team_info["base_hp"] = new_hp

                # Track base damage dealt for scoring (§12.2, D11)
                attacker_team_id = str(unit.get("team_id", ""))
                if attacker_team_id in current.combat_stats:
                    current.combat_stats[attacker_team_id]["base_damage_dealt"] += hp_dmg + s_abs

                events.append({
                    "type": "BASE_DAMAGED",
                    "target_team_id": target_team_id,
                    "attacker_team_id": attacker_team_id,
                    "unit_id": str(unit["id"]),
                    "damage": dmg,
                    "shield_absorbed": s_abs,
                    "hp_damage": hp_dmg,
                    "base_hp_remaining": new_hp,
                    "base_shield_remaining": new_shield,
                })

                # §10.4: Unit is removed from the battlefield upon detonating against base
                unit["status"] = "DESTROYED"
                unit["current_hp"] = 0
                events.append({
                    "type": "ENTITY_DESTROYED",
                    "entity_id": str(unit["id"]),
                    "team_id": attacker_team_id,
                    "reason": "BASE_IMPACT",
                })

        # Decrement team base shield duration if active (D7: exists for 2 combat rounds)
        for tid, tinfo in current.teams.items():
            if tinfo.get("base_shield", 0) > 0:
                rem_rounds = tinfo.get("shield_remaining_rounds", 2) - 1
                tinfo["shield_remaining_rounds"] = rem_rounds
                if rem_rounds <= 0:
                    tinfo["base_shield"] = 0
                    events.append({
                        "type": "SHIELD_EXPIRED",
                        "team_id": tid,
                    })

        # --- STEP 9: Remove Destroyed Units & Structures ---
        for entity in current.entities:
            if entity["id"] in disabled_ids and entity.get("current_hp", 0) > 0:
                entity["status"] = "ACTIVE"
                entity["is_disabled"] = False
                events.append({"type": "TOWER_ENABLED", "entity_id": str(entity["id"])})
            if entity.get("status") in ("ACTIVE", "DISABLED") and entity.get("current_hp", 0) <= 0:
                entity["status"] = "DESTROYED"
                events.append({
                    "type": "ENTITY_DESTROYED",
                    "entity_id": str(entity["id"]),
                    "team_id": str(entity.get("team_id", "")),
                    "reason": "COMBAT_CASUALTY",
                })

        # --- STEP 10: Check Elimination & Victory Conditions ---
        newly_eliminated_team_ids = []
        for tid, tinfo in sorted(current.teams.items(), key=lambda x: str(x[0])):
            if tinfo.get("status") == "ACTIVE" and tinfo.get("base_hp", 0) <= 0:
                tinfo["status"] = "ELIMINATED"
                newly_eliminated_team_ids.append(tid)

                # Attribute base destruction to the last attacker or leading damage dealer
                events.append({
                    "type": "BASE_DESTROYED",
                    "team_id": tid,
                    "team_name": tinfo.get("name", ""),
                })
                events.append({
                    "type": "TEAM_ELIMINATED",
                    "team_id": tid,
                    "team_name": tinfo.get("name", ""),
                })

        # Attribute bases_destroyed credit to enemy teams that dealt damage
        if newly_eliminated_team_ids:
            for elim_id in newly_eliminated_team_ids:
                # Find attacker that contributed to this destruction
                # Find team that dealt the most damage or attacked it in this round
                last_dmg_event = next(
                    (e for e in reversed(events)
                     if e.get("type") == "BASE_DAMAGED" and e.get("target_team_id") == elim_id),
                    None
                )
                if last_dmg_event:
                    killer_tid = last_dmg_event.get("attacker_team_id")
                    if killer_tid and killer_tid in current.combat_stats:
                        current.combat_stats[killer_tid]["bases_destroyed"] += 1

        # Check surviving active teams
        active_teams = [
            tid for tid, t in current.teams.items()
            if t.get("status") == "ACTIVE" and t.get("base_hp", 0) > 0
        ]

        winner_team_id = None
        is_match_over = False

        if len(active_teams) == 1:
            # Single surviving active team -> Immediate Elimination Victory (§12.1)
            winner_team_id = active_teams[0]
            is_match_over = True
            events.append({
                "type": "VICTORY_DECLARED",
                "winner_team_id": winner_team_id,
                "victory_type": "ELIMINATION",
            })
        elif len(active_teams) == 0:
            # Simultaneous elimination of all remaining teams (D6, §12.1)
            # Tie-break: highest score, then base HP, then coins
            is_match_over = True
            events.append({
                "type": "VICTORY_DECLARED",
                "winner_team_id": None,  # Will be ranked by final scoring
                "victory_type": "SIMULTANEOUS_ELIMINATION",
            })

        # --- STEP 11: Passive Income ---
        # Only active teams receive passive income; paused matches do not grant income (§11, D9)
        if not current.is_paused and not is_match_over:
            for tid, tinfo in current.teams.items():
                if tinfo.get("status") == "ACTIVE" and tinfo.get("base_hp", 0) > 0:
                    tinfo["coins"] = tinfo.get("coins", 0) + base_income
                    events.append({
                        "type": "INCOME_AWARDED",
                        "team_id": tid,
                        "amount": base_income,
                        "new_balance": tinfo["coins"],
                    })

        # --- STEP 12: Publish Authoritative State ---
        current.round_number += 1
        events.append({
            "type": "COMBAT_RESOLVED",
            "round_number": round_num,
            "eliminated_teams": newly_eliminated_team_ids,
            "winner_team_id": winner_team_id,
            "is_match_over": is_match_over,
        })

        for event in events:
            event["round_number"] = round_num
        return RoundResult(
            round_number=round_num,
            events=events,
            new_state=current,
            eliminated_team_ids=newly_eliminated_team_ids,
            winner_team_id=winner_team_id,
            is_match_over=is_match_over,
        )
