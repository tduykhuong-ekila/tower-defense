"""Tactical order, versioned geometry and explicit quiz-open acceptance."""

import copy
import math
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.combat.balance import movement_speed
from apps.combat.build_geometry import BuildGeometry, segment_distance
from apps.combat.continuous import ContinuousEngine
from apps.combat.continuous_service import ContinuousCombatService
from apps.combat.formation import physical_position, redirect_route, synchronize_position
from apps.combat.map import GameMap, get_game_map
from apps.combat.navigation import project
from apps.matches.services import MatchService
from apps.questions.models import Question, TeamQuestion
from apps.questions.services import QuestionService
from apps.realtime.services import RealtimeService
from apps.rewards.services import RewardService
from apps.units.commands import ArmyCommandService
from apps.units.models import TeamUnlock, UnitType
from apps.units.services import ConstructionService, UnitService
from tests.test_continuous_combat import room
from tests.test_live_battle_gameplay import convoy


@pytest.mark.parametrize("count", range(2, 21))
def test_layout_v5_full_artwork_click_road_clearance_and_round_trip(count):
    graph = get_game_map(count, 5)
    assert graph.validate_map() == (True, [])
    assert BuildGeometry(graph).validate() == []
    assert graph.to_dict()["arena"]["version"] == 5
    assert GameMap.from_dict(graph.to_dict()).to_dict() == graph.to_dict()
    geom = BuildGeometry(graph)
    for i in range(1, count + 1):
        slots = [
            n for n in graph.nodes.values() if n.node_type == "tower_slot" and n.team_index == i
        ]
        assert len(slots) == 6
        for slot in slots:
            p = project((slot.x, slot.y))
            assert 57 <= min(segment_distance(p, a, b) for a, b in geom.roads) < 190
    assert get_game_map(count, 4).layout_version == 4


@pytest.mark.django_db
def test_six_constructions_per_team_use_exact_new_map_nodes():
    match, teams, _, _ = room(initial_coins=5000)
    graph = get_game_map(2, 5)
    for i, team in enumerate(teams, 1):
        for slot in range(1, 7):
            node = f"node_tower_t{i}_slot{slot}"
            _, entity = ConstructionService.build_tower(match, team, "mg_tower", node)
            assert entity.current_node_id == graph.nodes[node].node_id
    assert match.entities.filter(entity_kind="TOWER").count() == 12


def test_redirect_reverses_partial_edge_preserving_exact_world_point_and_cooldown():
    state = convoy(("infantry",))
    graph = get_game_map(2)
    e = state.entities[0]
    e["simulation_state"].update(route_distance=150, attack_remaining=0.73)
    synchronize_position(e, graph)
    e["simulation_state"].pop("world_position", None)
    before = physical_position(e, graph)
    old_next = e["simulation_state"]["next_node_id"]
    reference = e["simulation_state"]["reference_hop_length"]
    assert redirect_route(e, "node_spawn_t1", graph)
    assert physical_position(e, graph) == before
    assert e["current_node_id"] == old_next
    assert e["simulation_state"]["attack_remaining"] == 0.73
    assert e["simulation_state"]["reference_hop_length"] == reference
    assert all(graph.nodes[n].is_passable for n in e["simulation_state"]["route_nodes"])


def test_mixed_retreat_arrival_idle_redeploy_and_vulnerability():
    state = convoy(("infantry", "tank", "artillery"))
    graph = get_game_map(2)
    owner = state.entities[0]["team_id"]
    state.configuration["movement_baseline_round_seconds"] = 10
    for e in state.entities:
        sim = e["simulation_state"]
        sim.update(route_distance=200, movement_zone="ROUTE", attack_remaining=0.8)
        sim.pop("world_position", None)
        synchronize_position(e, graph)
        e["status"] = "ACTIVE"
        e["current_hp"] = 37
        assert redirect_route(e, "node_spawn_t1", graph)
        sim.update(order="RETREAT", destination_rally_id="node_spawn_t1")
        e["target_team_id"] = None
    before = copy.deepcopy(state.entities)
    state = ContinuousEngine.step(state, 0.2).new_state
    for e, old in zip(state.entities, before):
        assert e["simulation_state"]["route_distance"] > old["simulation_state"]["route_distance"]
        assert (
            math.dist(physical_position(e, graph), physical_position(old, graph))
            <= movement_speed(e, state.configuration) * 0.2 + 1e-6
        )
        assert e["current_hp"] == 37
    for _ in range(120):
        state = ContinuousEngine.step(state, 0.2).new_state
    assert all(e["simulation_state"]["order"] == "AT_RALLY" for e in state.entities)
    points = [physical_position(e, graph) for e in state.entities]
    for _ in range(5):
        state = ContinuousEngine.step(state, 0.2).new_state
    assert [physical_position(e, graph) for e in state.entities] == points
    enemy = copy.deepcopy(state.entities[0])
    enemy.update(
        id="enemy",
        team_id="b",
        target_team_id=owner,
        damage=10,
        range=2,
        current_node_id="node_spawn_t1",
    )
    enemy["simulation_state"] = {"attack_remaining": 0}
    state.entities.append(enemy)
    result = ContinuousEngine.step(state, 0.2)
    assert any(e["type"] == "UNIT_ATTACKED" and e["attacker_id"] == "enemy" for e in result.events)
    assert not any(e.get("attacker_id") in {u["id"] for u in before} for e in result.events)
    returned = result.new_state.entities[1]
    assert redirect_route(returned, "node_lane_t2_1", graph)
    returned["simulation_state"]["order"] = "ATTACK"
    returned["target_team_id"] = "b"
    assert returned["current_hp"] == 37


@pytest.fixture
def battle():
    match, teams, tokens, host = room(count=3, prep=600, battle=600)
    entities = []
    for code in ("infantry", "tank", "artillery"):
        if code != "infantry":
            TeamUnlock.objects.create(team=teams[0], unit_type=UnitType.objects.get(code=code))
        _, entity = UnitService.deploy_unit(match, teams[0], code, str(teams[1].pk))
        entities.append(entity)
    match = MatchService.advance_phase(match)
    return match, teams, tokens, host, entities


@pytest.mark.django_db
@pytest.mark.parametrize("code", ["infantry", "tank", "artillery"])
def test_gathering_retarget_selected_troop_keeps_position_until_battle(code):
    match, teams, tokens, _ = room(count=3, prep=600, battle=600)
    if code != "infantry":
        TeamUnlock.objects.create(team=teams[0], unit_type=UnitType.objects.get(code=code))
    _, selected = UnitService.deploy_unit(match, teams[0], code, str(teams[1].pk))
    _, other = UnitService.deploy_unit(match, teams[0], "infantry", str(teams[1].pk))
    before = copy.deepcopy(selected.simulation_state["world_position"])
    client = APIClient()
    client.credentials(HTTP_X_PARTICIPANT_TOKEN=tokens[0])
    response = client.post(f"/api/v1/matches/{match.pk}/actions/army/", {
        "command_type": "RETARGET", "idempotency_key": f"gather-{code}",
        "unit_ids": [str(selected.pk)], "target_team_id": str(teams[2].pk),
    }, format="json")
    assert response.status_code == 200, response.data
    selected.refresh_from_db()
    other.refresh_from_db()
    assert selected.target_team_id == teams[2].pk
    assert other.target_team_id == teams[1].pk
    assert selected.simulation_state["world_position"] == before
    assert selected.simulation_state["order"] == "ATTACK"
    tick = timezone.datetime.fromisoformat(match.configuration["timer_state"]["next_tick_at"])
    assert ContinuousCombatService.tick(match.pk, tick)
    selected.refresh_from_db()
    assert selected.simulation_state["world_position"] == before
    assert selected.target_team_id == teams[2].pk
    board = RealtimeService.build_snapshot(match, str(teams[0].pk))["payload"]["entities"]
    assert next(e for e in board if e["id"] == str(selected.pk))["target_team_id"] == str(teams[2].pk)
    match = MatchService.advance_phase(match)
    tick = timezone.datetime.fromisoformat(match.configuration["timer_state"]["next_tick_at"])
    assert ContinuousCombatService.tick(match.pk, tick)
    selected.refresh_from_db()
    assert selected.target_team_id == teams[2].pk


@pytest.mark.django_db
def test_returned_troops_can_be_retargeted_during_later_preparation(battle):
    match, teams, _, _, entities = battle
    match = MatchService.advance_phase(match)
    assert match.phase == "PREPARATION" and match.configuration["current_round"] == 2
    unit = entities[0]
    unit.simulation_state.update(order="AT_RALLY", movement_state="STOPPED")
    unit.target_team = None
    unit.save(update_fields=["simulation_state", "target_team"])

    action, result = ArmyCommandService.issue(
        match, teams[0], "RETARGET", "round-two-returned-unit", [unit.pk], teams[2].pk
    )

    unit.refresh_from_db()
    assert result["affected_count"] == 1
    assert unit.target_team_id == teams[2].pk
    assert unit.simulation_state["order"] == "ATTACK"


@pytest.mark.django_db
def test_command_atomicity_subset_idempotency_last_writer_and_snapshot(battle):
    match, teams, tokens, _, entities = battle
    first = entities[0]
    first.current_hp = 39
    first.level = 3
    first.simulation_state["attack_remaining"] = 0.66
    first.save()
    action, result = ArmyCommandService.issue(
        match, teams[0], "RETARGET", "retarget-1", [first.pk], teams[2].pk
    )
    first.refresh_from_db()
    entities[1].refresh_from_db()
    assert first.target_team_id == teams[2].pk and entities[1].target_team_id == teams[1].pk
    assert (
        first.current_hp == 39
        and first.level == 3
        and first.simulation_state["attack_remaining"] == 0.66
    )
    assert result["affected_count"] == 1
    _, retreated = ArmyCommandService.issue(match, teams[0], "RETREAT_ALL", "retreat-1")
    assert retreated["affected_count"] == 3
    again, original = ArmyCommandService.issue(
        match, teams[0], "RETARGET", "retarget-1", [first.pk], teams[2].pk
    )
    assert again.pk == action.pk and original == result
    first.refresh_from_db()
    assert first.simulation_state["order"] == "RETREAT"
    assert match.events.filter(event_type="ARMY_RETREAT_ORDERED").count() == 1
    assert match.events.filter(event_type="UNITS_RETARGETED").count() == 1
    with pytest.raises(ValidationError, match="Mã yêu cầu"):
        ArmyCommandService.issue(
            match, teams[0], "RETARGET", "retarget-1", [entities[1].pk], teams[2].pk
        )
    with pytest.raises(ValidationError, match="cũ"):
        ArmyCommandService.issue(
            match, teams[0], "RETREAT_ALL", "stale", expected_command_version=0
        )
    _, new = UnitService.deploy_unit(match, teams[0], "infantry", str(teams[1].pk))
    assert new.simulation_state.get("order", "ATTACK") == "ATTACK"
    ArmyCommandService.issue(match, teams[0], "RETARGET", "attack-again", [first.pk], teams[2].pk)
    board = {
        e["id"]: e
        for e in RealtimeService.build_snapshot(match, str(teams[1].pk))["payload"]["entities"]
    }
    assert board[str(first.pk)]["simulation_state"]["order"] == "ATTACK"
    assert board[str(entities[1].pk)]["simulation_state"]["order"] == "RETREAT"
    assert board[str(first.pk)]["current_hp"] == 39
    tick = timezone.datetime.fromisoformat(match.configuration["timer_state"]["next_tick_at"])
    assert ContinuousCombatService.tick(match.pk, tick)
    first.refresh_from_db()
    assert first.simulation_state["order"] == "ATTACK"


@pytest.mark.django_db
def test_authenticated_security_phase_targets_and_all_or_nothing(battle):
    match, teams, tokens, _, entities = battle
    client = APIClient()
    client.credentials(HTTP_X_PARTICIPANT_TOKEN=tokens[0])
    url = f"/api/v1/matches/{match.pk}/actions/army/"

    def send(**extra):
        return client.post(
            url,
            {
                "command_type": "RETARGET",
                "idempotency_key": str(uuid.uuid4()),
                "unit_ids": [str(entities[0].pk)],
                "target_team_id": str(teams[2].pk),
                **extra,
            },
            format="json",
        )

    assert send().status_code == 200
    _, enemy = UnitService.deploy_unit(match, teams[1], "infantry", str(teams[0].pk))
    assert send(unit_ids=[str(entities[1].pk), str(enemy.pk)]).status_code == 400
    entities[1].refresh_from_db()
    assert entities[1].target_team_id == teams[1].pk
    assert send(target_team_id=str(uuid.uuid4())).status_code == 400
    assert send(target_team_id=str(teams[0].pk)).status_code == 400
    teams[2].status = "ELIMINATED"
    teams[2].save()
    assert send().status_code == 400
    entities[0].status = "DESTROYED"
    entities[0].current_hp = 0
    entities[0].save()
    assert send(target_team_id=str(teams[1].pk)).status_code == 400
    client.credentials(HTTP_X_PARTICIPANT_TOKEN=tokens[-1])
    assert send().status_code == 400
    client.credentials()
    assert send().status_code == 401
    client.credentials(HTTP_X_PARTICIPANT_TOKEN=tokens[0])
    match.status = "FINISHED"
    match.save()
    assert send().status_code == 400


@pytest.mark.django_db
def test_explicit_quiz_reopen_advances_without_next_and_preserves_reward():
    match, teams, tokens, _ = room(prep=600)
    for i in range(4):
        Question.objects.create(content=f"Question {i}", answer_key="yes", time_limit_seconds=30)
    client = APIClient()
    client.credentials(HTTP_X_PARTICIPANT_TOKEN=tokens[0])
    url = f"/api/v1/matches/{match.pk}/questions/current/"
    q = client.get(url).data

    def opened(qid):
        response = client.post(
            url,
            {"action": "OPEN_SESSION", "question_id": qid, "viewer_id": str(uuid.uuid4())},
            format="json",
        )
        assert response.status_code == 200
        return response.data

    start = timezone.now()
    with patch("django.utils.timezone.now", return_value=start):
        first = opened(q["id"])
    with patch("django.utils.timezone.now", return_value=start + timedelta(seconds=31)):
        QuestionService.expire_overdue_questions(match)
        assert client.get(url).data["id"] == q["id"]
        assert TeamQuestion.objects.filter(team=teams[0]).count() == 1
        next_q = opened(q["id"])
        assert next_q["sequence_number"] == 2 and next_q["timer"]["status"] == "RUNNING"
        assert next_q["previous_question_expired"] and opened(q["id"])["id"] == next_q["id"]
        QuestionService.submit_answer(match, teams[0], next_q["id"], "yes")
        pending = opened(next_q["id"])
        assert pending["id"] == next_q["id"] and pending["status"] == "PENDING_REWARD"
        assert pending["reward_options"]["coin_amount"] is None
        claim = RewardService.claim_reward(
            match, teams[0], next_q["id"], "COIN", idempotency_key="one"
        )
        sealed = TeamQuestion.objects.get(pk=next_q["id"])
        assert claim.coin_amount == sealed.reward_coin_amount
        assert (
            RewardService.claim_reward(
                match, teams[0], next_q["id"], "COIN", idempotency_key="two"
            ).pk
            == claim.pk
        )
        third = opened(next_q["id"])
        assert third["sequence_number"] == 3
        QuestionService.submit_answer(match, teams[0], third["id"], "wrong")
        assert opened(third["id"])["sequence_number"] == 4


@pytest.mark.django_db(transaction=True)
def test_postgres_duplicate_commands_and_tick_ordering():
    from django.db import connection

    from tests.test_round_concurrency import concurrent

    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    match, teams, _, _ = room(count=3, prep=600, battle=600)
    _, units = UnitService.deploy_units(match, teams[0], "infantry", str(teams[1].pk), quantity=5)
    match = MatchService.advance_phase(match)
    results = concurrent(
        lambda _: ArmyCommandService.issue(match, teams[0], "RETREAT_ALL", "same-retreat")
    )
    assert len({action.pk for action, _ in results}) == 1
    assert match.events.filter(event_type="ARMY_RETREAT_ORDERED").count() == 1
    tick = timezone.datetime.fromisoformat(match.configuration["timer_state"]["next_tick_at"])

    def competing(i):
        if i == 0:
            return ContinuousCombatService.tick(match.pk, tick)
        if i == 1:
            return ArmyCommandService.issue(
                match, teams[0], "RETARGET", "concurrent-attack", [u.pk for u in units], teams[2].pk
            )
        return ArmyCommandService.issue(match, teams[0], "RETREAT_ALL", "concurrent-retreat")

    concurrent(competing, count=3)
    last = (
        match.events.filter(event_type__in=["UNITS_RETARGETED", "ARMY_RETREAT_ORDERED"])
        .order_by("-sequence_number")
        .first()
    )
    expected = last.payload["command_version"]
    for unit in units:
        unit.refresh_from_db()
        assert unit.simulation_state["command_version"] == expected
        assert unit.current_hp == 80
        assert (
            unit.simulation_state["order"] in ("RETREAT", "AT_RALLY")
            if last.event_type == "ARMY_RETREAT_ORDERED"
            else unit.simulation_state["order"] == "ATTACK"
        )
    assert len(set(match.events.values_list("sequence_number", flat=True))) == match.events.count()


@pytest.mark.django_db(transaction=True)
def test_postgres_concurrent_explicit_open_cannot_skip_questions():
    from django.db import connection

    from tests.test_round_concurrency import concurrent

    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    match, teams, _, _ = room(prep=600)
    for i in range(3):
        Question.objects.create(content=f"Concurrent {i}", answer_key="yes", time_limit_seconds=60)
    tq = QuestionService.get_or_assign_current_question(match, teams[0])
    QuestionService.update_viewing(match, teams[0], tq.pk, "viewer", "OPEN")
    QuestionService.submit_answer(match, teams[0], tq.pk, "wrong")
    results = concurrent(lambda _: QuestionService.open_session(match, teams[0], tq.pk, "viewer"))
    assert len({q.pk for q, _ in results}) == 1
    assert TeamQuestion.objects.filter(team=teams[0]).count() == 2
    assert all(q.sequence_number == 2 and q.timer_status == "RUNNING" for q, _ in results)
