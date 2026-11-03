"""Lethal-hit attribution in both authoritative combat engines."""
import unittest

from apps.combat.continuous import ContinuousEngine
from apps.combat.engine import CombatEngine, CombatState
from apps.combat.rewards import KILL_REWARDS


def battle(code, attacker_kind="UNIT", victim_hp=1):
    teams = {tid: {"team_index": i, "status": "ACTIVE", "base_hp": 500,
                   "base_shield": 0, "coins": 100} for i, tid in enumerate(("a", "b"), 1)}
    attacker = {"id": "attacker", "team_id": "a", "unit_type_code": "tank" if attacker_kind == "UNIT" else "mg_tower",
                "entity_kind": attacker_kind, "current_hp": 500, "max_hp": 500,
                "current_shield": 0, "status": "ACTIVE", "level": 1,
                "current_node_id": "node_center", "target_team_id": "b",
                "damage": 100, "range": 3, "movement": 0, "simulation_state": {}}
    victim = {**attacker, "id": "victim", "team_id": "b", "unit_type_code": code,
              "entity_kind": "TOWER" if "tower" in code else "UNIT", "damage": 0,
              "current_hp": victim_hp, "max_hp": victim_hp, "target_team_id": "a", "simulation_state": {}}
    return CombatState(1, False, teams, [attacker, victim], [], {"base_income_per_round": 0})


class KillRewardTests(unittest.TestCase):
    def test_each_bounty_paid_once_in_both_engines(self):
        for code, reward in KILL_REWARDS.items():
            for engine in (CombatEngine.resolve_round, lambda s: ContinuousEngine.step(s, .2)):
                with self.subTest(code=code, engine=engine):
                    result = engine(battle(code))
                    self.assertEqual(result.new_state.teams["a"]["coins"], 100 + reward)
                    self.assertEqual(result.new_state.teams["b"]["coins"], 100)
                    payouts = [e for e in result.events if e["type"] == "KILL_REWARD_AWARDED"]
                    self.assertEqual(len(payouts), 1)
                    self.assertEqual(payouts[0]["target_entity_id"], "victim")
                    again = engine(result.new_state)
                    self.assertEqual(again.new_state.teams["a"]["coins"], 100 + reward)
                    self.assertFalse(any(e["type"] == "KILL_REWARD_AWARDED" for e in again.events))

    def test_tower_kills_pay_and_nonlethal_hits_do_not(self):
        for engine in (CombatEngine.resolve_round, lambda s: ContinuousEngine.step(s, .2)):
            result = engine(battle("infantry", attacker_kind="TOWER"))
            self.assertEqual(result.new_state.teams["a"]["coins"], 104)
            result = engine(battle("tank", victim_hp=1000))
            self.assertEqual(result.new_state.teams["a"]["coins"], 100)

    def test_multiple_attackers_cannot_duplicate_bounty(self):
        state = battle("tank")
        state.entities.append({**state.entities[0], "id": "attacker-2", "simulation_state": {}})
        result = ContinuousEngine.step(state, .2)
        self.assertEqual(result.new_state.teams["a"]["coins"], 107)

    def test_elimination_cleanup_and_paused_combat_do_not_pay(self):
        state = battle("tank", victim_hp=1000)
        state.teams["b"]["base_hp"] = 0
        result = ContinuousEngine.step(state, .2)
        self.assertEqual(result.new_state.teams["a"]["coins"], 100)
        self.assertFalse(any(e["type"] == "KILL_REWARD_AWARDED" for e in result.events))
        for engine in (CombatEngine.resolve_round, lambda s: ContinuousEngine.step(s, .2)):
            state = battle("tank")
            state.is_paused = True
            self.assertEqual(engine(state).new_state.teams["a"]["coins"], 100)
