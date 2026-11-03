"""Troops engage only troops from the team assigned to each attacker."""
import pytest

from apps.combat.continuous import ContinuousEngine, candidates, entity_index
from apps.combat.engine import CombatState
from apps.combat.map import get_game_map
from apps.combat.targeting import find_unit_target
from apps.units.seeds import STANDARD_UNITS


def unit(uid, team, target, code="infantry"):
    stats = next(s["base_stats"] for s in STANDARD_UNITS if s["code"] == code)
    return {**stats, "id": uid, "team_id": team, "target_team_id": target,
            "unit_type_code": code, "entity_kind": "UNIT", "status": "ACTIVE",
            "current_node_id": "node_center", "current_hp": stats["hp"],
            "current_shield": 0, "simulation_state": {}}


@pytest.mark.parametrize("code", ["infantry", "tank", "artillery"])
@pytest.mark.parametrize("target_team", ["b", "c", None])
def test_target_selection_filters_units_by_assigned_team(code, target_team):
    graph = get_game_map(3)
    attacker = unit("attacker", "a", target_team, code)
    enemies = [unit("b-unit", "b", "c"), unit("c-unit", "c", "b")]
    expected = [e for e in enemies if e["team_id"] == target_team]
    assert candidates(attacker, entity_index(enemies), graph, ("UNIT",)) == expected
    assert find_unit_target(attacker, enemies, graph) == (expected[0] if expected else None)


@pytest.mark.parametrize("code", ["infantry", "tank", "artillery"])
def test_same_team_units_with_different_orders_do_not_share_targets(code):
    attackers = [unit("a1", "a", "b", code), unit("a2", "a", "c", code)]
    enemies = [unit("b-unit", "b", "c"), unit("c-unit", "c", "b")]
    for enemy in enemies:
        enemy["damage"] = 0
    teams = {tid: {"team_index": index, "status": "ACTIVE", "base_hp": 500,
                   "base_shield": 0} for index, tid in enumerate("abc", 1)}
    state = CombatState(1, False, teams, attackers + enemies, [], {})
    result = ContinuousEngine.step(state, .2)
    hits = {e["attacker_id"]: e["target_entity_id"] for e in result.events
            if e["type"] == "UNIT_ATTACKED"}
    assert hits == {"a1": "b-unit", "a2": "c-unit"}
    for entity in result.new_state.entities:
        if entity["id"] in hits:
            assert entity["simulation_state"]["attack_target_id"] == hits[entity["id"]]

    # A new order must take effect even while the previous shot cools down.
    for entity in result.new_state.entities:
        if entity["id"] == "a1":
            entity["target_team_id"] = "c"
    changed = ContinuousEngine.step(result.new_state, .2)
    assert next(e for e in changed.new_state.entities if e["id"] == "a1")[
        "simulation_state"]["attack_target_id"] == "c-unit"


@pytest.mark.parametrize("code", ["infantry", "tank", "artillery"])
def test_unassigned_enemy_does_not_trigger_combat(code):
    attacker = unit("attacker", "a", "b", code)
    enemy = unit("c-unit", "c", "b")
    enemy["damage"] = 0
    teams = {tid: {"team_index": index, "status": "ACTIVE", "base_hp": 500,
                   "base_shield": 0} for index, tid in enumerate("abc", 1)}
    result = ContinuousEngine.step(CombatState(1, False, teams, [attacker, enemy], [], {}), .2)
    assert not any(e["type"] == "UNIT_ATTACKED" for e in result.events)
    current = next(e for e in result.new_state.entities if e["id"] == "attacker")
    assert current["simulation_state"]["attack_target_id"] is None
    assert current["simulation_state"]["combat_state"] == "IDLE"


def test_tower_defense_still_targets_any_enemy_team():
    graph = get_game_map(3)
    tower = unit("tower", "a", None)
    tower["entity_kind"] = "TOWER"
    enemies = [unit("b-unit", "b", "c"), unit("c-unit", "c", "b")]
    assert candidates(tower, entity_index(enemies), graph, ("UNIT",)) == enemies
