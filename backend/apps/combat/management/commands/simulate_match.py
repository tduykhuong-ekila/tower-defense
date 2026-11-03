"""
Management command to simulate a full headless match deterministically (§2.7, FR-07).
Usage:
  python manage.py simulate_match --teams 4 --seed 42 --rounds 20 --output results.json
"""

import json
import random
from typing import Any, Dict

from django.core.management.base import BaseCommand

from apps.combat.balance import TOWER_ATTACK_RANGE
from apps.combat.engine import CombatEngine, CombatState
from apps.combat.map import get_game_map
from apps.combat.scoring import rank_teams
from apps.matches.defaults import DEFAULT_MATCH_CONFIGURATION, DEFAULT_SCORING_WEIGHTS


class Command(BaseCommand):
    help = "Simulates a complete headless match using deterministic bots and pure CombatEngine."

    def add_arguments(self, parser):
        parser.add_argument("--teams", type=int, default=4, help="Number of teams (4-8)")
        parser.add_argument("--seed", type=int, default=42, help="Deterministic random seed")
        parser.add_argument("--rounds", type=int, default=25, help="Max combat rounds to simulate")
        parser.add_argument("--output", type=str, default="", help="Path to write JSON trajectory")
        parser.add_argument("--quiet", action="store_true", help="Quiet output")

    def handle(self, *args, **options):
        num_teams = options["teams"]
        seed = options["seed"]
        max_rounds = options["rounds"]
        output_file = options["output"]
        quiet = options["quiet"]

        # Deterministic PRNG
        rng = random.Random(seed)

        if not quiet:
            self.stdout.write(self.style.SUCCESS(
                f"Starting headless simulation: {num_teams} teams, seed={seed}, max_rounds={max_rounds}"
            ))

        game_map = get_game_map(num_teams)

        # 1. Initialize teams
        teams_data: Dict[str, Dict[str, Any]] = {}
        for i in range(1, num_teams + 1):
            tid = f"team_{i}"
            teams_data[tid] = {
                "id": tid,
                "name": f"Team {i}",
                "team_index": i,
                "base_hp": 500,
                "initial_base_hp": 500,
                "base_shield": 0,
                "coins": 100,
                "score": 0,
                "status": "ACTIVE",
                "correct_answers": rng.randint(2, 6),
                "shield_remaining_rounds": 0,
            }

        # 2. Base units roster
        unit_types = {
            "infantry": {"cost": 15, "hp": 80, "damage": 10, "range": 1, "movement": 1, "kind": "UNIT"},
            "tank": {"cost": 35, "hp": 120, "damage": 25, "range": 1, "movement": 1, "kind": "UNIT"},
            "artillery": {"cost": 45, "hp": 70, "damage": 40, "range": 1.5, "movement": 1, "kind": "UNIT"},
            "mg_tower": {"cost": 25, "hp": 100, "damage": 15, "range": TOWER_ATTACK_RANGE, "movement": 0, "kind": "TOWER"},
            "cannon_tower": {"cost": 40, "hp": 150, "damage": 20, "range": TOWER_ATTACK_RANGE, "movement": 0, "kind": "TOWER"},
            "shield_generator": {"cost": 30, "hp": 100, "damage": 0, "range": 0, "movement": 0, "kind": "TOWER"},
        }

        # Initial state
        combat_state = CombatState(
            round_number=1,
            is_paused=False,
            teams=teams_data,
            entities=[],
            actions=[],
            configuration=DEFAULT_MATCH_CONFIGURATION,
            combat_stats={tid: {"bases_destroyed": 0, "base_damage_dealt": 0} for tid in teams_data},
        )

        rounds_trajectory = []
        entity_seq = 0

        # Simulation loop
        for round_idx in range(1, max_rounds + 1):
            # Bot planning phase: each active team queues actions deterministically
            active_tids = [tid for tid, t in combat_state.teams.items() if t["status"] == "ACTIVE" and t["base_hp"] > 0]
            if len(active_tids) <= 1:
                break

            for tid in sorted(active_tids):
                tinfo = combat_state.teams[tid]
                t_idx = tinfo["team_index"]

                # Possible target teams
                other_tids = [other for other in active_tids if other != tid]
                if not other_tids:
                    continue

                target_tid = rng.choice(other_tids)

                # Decisions: Deploy unit or build tower
                roll = rng.random()
                if roll < 0.65 and tinfo["coins"] >= 15:
                    # Deploy unit
                    u_code = "infantry"
                    if tinfo["coins"] >= 45 and rng.random() < 0.4:
                        u_code = "artillery"
                    elif tinfo["coins"] >= 35 and rng.random() < 0.5:
                        u_code = "tank"

                    u_spec = unit_types[u_code]
                    tinfo["coins"] -= u_spec["cost"]
                    entity_seq += 1

                    combat_state.entities.append({
                        "id": f"ent_{entity_seq}_{tid}_{u_code}",
                        "team_id": tid,
                        "unit_type_code": u_code,
                        "entity_kind": "UNIT",
                        "current_hp": u_spec["hp"],
                        "max_hp": u_spec["hp"],
                        "current_shield": 0,
                        "level": 1,
                        "status": "QUEUED",
                        "current_node_id": game_map.get_spawn_node(t_idx),
                        "target_team_id": target_tid,
                        "range": u_spec["range"],
                        "damage": u_spec["damage"],
                        "movement": u_spec["movement"],
                        "is_disabled": False,
                    })
                elif roll < 0.85 and tinfo["coins"] >= 25:
                    # Build tower if slot available
                    team_towers = [
                        e for e in combat_state.entities
                        if e["team_id"] == tid and e["entity_kind"] == "TOWER" and e["status"] == "ACTIVE"
                    ]
                    if len(team_towers) < 3:
                        slot_num = len(team_towers) + 1
                        slot_node = f"node_tower_t{t_idx}_slot{slot_num}"
                        tower_code = "mg_tower"
                        if tinfo["coins"] >= 40 and rng.random() < 0.4:
                            tower_code = "cannon_tower"
                        elif tinfo["coins"] >= 30 and rng.random() < 0.3:
                            tower_code = "shield_generator"

                        t_spec = unit_types[tower_code]
                        tinfo["coins"] -= t_spec["cost"]
                        entity_seq += 1

                        combat_state.entities.append({
                            "id": f"ent_{entity_seq}_{tid}_{tower_code}",
                            "team_id": tid,
                            "unit_type_code": tower_code,
                            "entity_kind": "TOWER",
                            "current_hp": t_spec["hp"],
                            "max_hp": t_spec["hp"],
                            "current_shield": 0,
                            "level": 1,
                            "status": "ACTIVE",
                            "current_node_id": slot_node,
                            "target_team_id": None,
                            "range": t_spec["range"],
                            "damage": t_spec["damage"],
                            "movement": 0,
                            "is_disabled": False,
                            "cooldown_remaining": 0,
                        })

            # Execute round via pure CombatEngine
            res = CombatEngine.resolve_round(combat_state)
            combat_state = res.new_state

            round_summary = {
                "round": res.round_number,
                "events_count": len(res.events),
                "eliminated_teams": res.eliminated_team_ids,
                "winner_team_id": res.winner_team_id,
                "is_match_over": res.is_match_over,
                "teams_hp": {tid: t["base_hp"] for tid, t in combat_state.teams.items()},
                "teams_coins": {tid: t["coins"] for tid, t in combat_state.teams.items()},
            }
            rounds_trajectory.append(round_summary)

            if not quiet:
                self.stdout.write(
                    f"Round {res.round_number}: {len(res.events)} events, "
                    f"Active teams: {[tid for tid, t in combat_state.teams.items() if t['status'] == 'ACTIVE']}"
                )

            if res.is_match_over:
                if not quiet:
                    self.stdout.write(self.style.SUCCESS(
                        f"Match ended in Round {res.round_number}! Winner: {res.winner_team_id}"
                    ))
                break

        # Calculate final rankings
        teams_final_stats = []
        for tid, t in combat_state.teams.items():
            active_towers = sum(
                1 for e in combat_state.entities
                if e["team_id"] == tid and e["entity_kind"] == "TOWER" and e["status"] == "ACTIVE"
            )
            c_stats = combat_state.combat_stats.get(tid, {})
            teams_final_stats.append({
                "team_id": tid,
                "team_name": t["name"],
                "base_hp": t["base_hp"],
                "coins": t["coins"],
                "bases_destroyed": c_stats.get("bases_destroyed", 0),
                "base_damage_dealt": c_stats.get("base_damage_dealt", 0),
                "correct_answers": t.get("correct_answers", 3),
                "surviving_towers": active_towers,
            })

        final_ranked = rank_teams(
            teams_final_stats,
            weights=DEFAULT_SCORING_WEIGHTS,
            total_initial_enemy_hp=num_teams * 500,
        )

        simulation_payload = {
            "seed": seed,
            "num_teams": num_teams,
            "total_rounds": len(rounds_trajectory),
            "winner_team_id": final_ranked[0]["team_id"],
            "rankings": final_ranked,
            "trajectory": rounds_trajectory,
        }

        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(simulation_payload, f, indent=2)
            self.stdout.write(self.style.SUCCESS(f"Simulation trajectory written to {output_file}"))

        if not quiet:
            self.stdout.write(self.style.SUCCESS("\n--- FINAL LEADERBOARD ---"))
            for r in final_ranked:
                self.stdout.write(
                    f"#{r['final_rank']} {r['team_name']}: Score={r['total_score']} "
                    f"(Bases Destroyed: {r['bases_destroyed']}, Damage: {r['base_damage_dealt']}, "
                    f"HP: {r['remaining_base_hp']}, Coins: {r['remaining_coins']})"
                )

        return json.dumps(simulation_payload)
