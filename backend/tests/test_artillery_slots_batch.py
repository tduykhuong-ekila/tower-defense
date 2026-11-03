"""Acceptance coverage for artillery, six foundations, and transactional batches."""
import asyncio
import importlib
from datetime import datetime
from unittest.mock import patch

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import connection, connections
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.combat.balance import entity_attack_range
from apps.combat.continuous import candidates, distance, entity_index
from apps.combat.continuous_service import ContinuousCombatService
from apps.combat.map import GameMap, get_game_map
from apps.economy.models import CoinTransaction
from apps.matches.models import Match
from apps.matches.services import MatchService
from apps.realtime.services import RealtimeService
from apps.units.map import MapDefinition
from apps.units.models import GameEntity, TeamUnlock, UnitType
from apps.units.serializers import GameEntitySerializer, UnitTypeSerializer
from apps.units.services import ConstructionService, UnitService
from config.asgi import application
from tests.test_continuous_combat import room


def unlock(team, code):
    TeamUnlock.objects.get_or_create(team=team, unit_type=UnitType.objects.get(code=code))


@pytest.mark.django_db
def test_artillery_catalog_spawn_and_unrelated_stats():
    match, teams, _, _ = room()
    unlock(teams[0], "artillery")
    artillery = UnitType.objects.get(code="artillery")
    assert artillery.name == "Pháo Binh Tầm Xa" and artillery.category == "UNIT"
    assert artillery.base_stats["range"] == 3 * .5 and artillery.base_stats["hp"] == 80
    assert artillery.base_stats["damage"] == 40 and artillery.cost == 45
    _, entities = UnitService.deploy_units(match, teams[0], "artillery", teams[1].pk, quantity=2)
    assert all(e.current_hp == e.max_hp == 80 and entity_attack_range(e) == 1.5 for e in entities)
    assert all(GameEntitySerializer(e).data["range"] == 1.5 for e in entities)
    stats = {u.code: UnitTypeSerializer(u, context={"match": match}).data for u in UnitType.objects.all()}
    assert tuple(stats["infantry"][k] for k in ["hp", "movement_speed", "damage", "range"]) == (80, 5.5, 5, 1)
    assert tuple(stats["tank"][k] for k in ["hp", "movement_speed", "damage", "cost"]) == (110, 4, 12.5, 35)
    assert tuple(stats["cannon_tower"][k] for k in ["hp", "damage", "range"]) == (150, 20, 3)
    snapshot = RealtimeService.build_snapshot(match, str(teams[0].pk))["payload"]
    assert all(e["range"] == 1.5 and e["max_hp"] == 80 for e in snapshot["entities"])


def test_fractional_artillery_target_eligibility_at_boundary():
    graph = get_game_map(2)
    attacker = {"id": "a", "team_id": "a", "entity_kind": "UNIT", "current_node_id": "node_lane_t2_1", "range": 1.5}
    for progress, eligible in [(0, True), (.5, True), (.5001, False), (1, False)]:
        target = {"id": "b", "team_id": "b", "entity_kind": "UNIT", "status": "ACTIVE", "current_hp": 80,
                  "current_node_id": "node_lane_t2_2", "simulation_state": {"next_node_id": "node_lane_t2_3", "edge_progress": progress}}
        assert distance(attacker, target, graph) == pytest.approx(1 + progress)
        assert bool(candidates(attacker, entity_index([target]), graph, ["UNIT"])) is eligible
    assert graph.nodes_in_range(attacker["current_node_id"], 1.5) == graph.nodes_in_range(attacker["current_node_id"], 1)


@pytest.mark.django_db
def test_migration_preserves_damaged_dead_and_active_artillery_and_old_range():
    match, teams, _, _ = room()
    unit = UnitType.objects.get(code="artillery")
    UnitType.objects.filter(pk=unit.pk).update(base_stats={**unit.base_stats, "range": 3, "hp": 100})
    old = [GameEntity.objects.create(match=match, team=teams[0], unit_type=unit, current_hp=hp,
        max_hp=100, status=status, current_node_id="node_spawn_t1") for hp, status in [(48, "ACTIVE"), (0, "DESTROYED")]]
    importlib.import_module("apps.units.migrations.0007_artillery_balance_and_six_slots").rebalance(apps, None)
    for entity, hp in zip(old, [48, 0]):
        entity.refresh_from_db()
        assert entity.current_hp == hp and entity.max_hp == 100
        assert entity_attack_range(entity) == GameEntitySerializer(entity).data["range"] == 3
    unit.refresh_from_db()
    assert unit.base_stats["range"] == 1.5 and unit.base_stats["hp"] == 70
    match.refresh_from_db()
    assert match.configuration["max_towers_per_team"] == 6
    assert RealtimeService.build_snapshot(match)["payload"]["entities"][0]["range"] == 3


@pytest.mark.parametrize("count", range(2, 21))
def test_six_owned_unique_valid_foundations_in_every_supported_arena(count):
    graph = GameMap(count)
    assert graph.validate_map() == (True, [])
    slots = [n for n in graph.nodes.values() if n.node_type == "tower_slot"]
    assert len(slots) == count * 6
    assert len({n.node_id for n in slots}) == len({(n.x, n.y) for n in slots}) == count * 6
    for i in range(1, count + 1):
        assert {n.node_id for n in slots if n.team_index == i} == {f"node_tower_t{i}_slot{k}" for k in range(1, 7)}
        assert all(not n.is_passable for n in slots if n.team_index == i)


def test_geometry_validation_detects_road_base_and_slot_overlap():
    graph = GameMap(20)
    slot = graph.nodes["node_tower_t1_slot6"]
    for node_id, expected in [("node_lane_t1_2", "road/bridge"), ("node_base_t1", "base"), ("node_tower_t1_slot5", "Overlapping")]:
        slot.x, slot.y = graph.nodes[node_id].x, graph.nodes[node_id].y
        assert any(expected in e for e in graph.validate_build_geometry())


@pytest.mark.django_db
def test_legacy_occupied_foundation_rejected_destroyed_rebuild_and_round_persistence():
    match, teams, _, _ = room(battle=1)
    slots = MapDefinition.get_valid_tower_slots(teams[0])
    towers = [ConstructionService.build_tower(match, teams[0], "mg_tower", slot,
              idempotency_key=f"tower-{i}")[1] for i, slot in enumerate(slots)]
    assert len(towers) == 6
    teams[0].refresh_from_db()
    assert teams[0].coins == 350
    with pytest.raises(ValidationError) as error:
        ConstructionService.build_tower(match, teams[0], "mg_tower", slots[-1])
    assert error.value.code == "INVALID_POSITION"
    assert ConstructionService.build_tower(match, teams[0], "mg_tower", slots[-1], idempotency_key="tower-5")[1].pk == towers[-1].pk
    assert GameEntity.objects.filter(team=teams[0]).count() == 6
    assert CoinTransaction.objects.filter(team=teams[0], transaction_type="BUILD_TOWER").count() == 6
    match = MatchService.advance_phase(match)
    match = MatchService.advance_phase(match)
    assert match.phase == "PREPARATION" and match.entities.filter(entity_kind="TOWER", status="ACTIVE").count() == 6
    towers[-1].status, towers[-1].current_hp = "DESTROYED", 0
    towers[-1].save()
    ConstructionService.build_tower(match, teams[0], "mg_tower", slots[-1])
    assert match.entities.exclude(status="DESTROYED").count() == 6


@pytest.mark.django_db
@pytest.mark.parametrize("quantity", [1, 5, 10, 100])
@pytest.mark.parametrize("battle", [False, True])
def test_batches_charge_once_create_exact_count_and_move_independently(quantity, battle):
    match, teams, _, _ = room(initial_coins=2000, max_active_units_per_team=1)
    if battle:
        match = MatchService.advance_phase(match)
    with CaptureQueriesContext(connection) as queries:
        action, entities = UnitService.deploy_units(match, teams[0], "infantry", teams[1].pk,
            quantity=quantity, idempotency_key="batch")
    assert len(queries) < 45 + quantity // 30
    assert len(entities) == len({e.pk for e in entities}) == quantity
    assert len({tuple(e.simulation_state["world_position"].values()) for e in entities}) >= min(quantity, 15)
    assert all(e.current_node_id == "node_spawn_t1" and e.max_hp == e.current_hp == 80 for e in entities)
    teams[0].refresh_from_db()
    assert teams[0].coins == 2000 - 15 * quantity
    assert CoinTransaction.objects.get(team=teams[0], transaction_type="DEPLOY_UNIT").amount == -15 * quantity
    assert action.payload["quantity"] == quantity and action.payload["cost"] == 15 * quantity
    again = UnitService.deploy_units(match, teams[0], "infantry", teams[1].pk, quantity=quantity, idempotency_key="batch")
    assert [e.pk for e in again[1]] == [e.pk for e in entities]
    assert match.entities.count() == quantity and match.game_actions.count() == 1
    assert match.events.filter(event_type="ENTITIES_CREATED" if quantity > 1 else "UNIT_DEPLOYED").count() == 1
    if battle:
        assert ContinuousCombatService.tick(match.pk, datetime.fromisoformat(match.configuration["timer_state"]["next_tick_at"]))
        assert all(e.simulation_state["route_distance"] > 0 for e in match.entities.all())


@pytest.mark.django_db
@pytest.mark.parametrize("quantity", [0, -1, 1.5, 1.0, True, False, None, "5"])
def test_invalid_quantity_rejected_at_rest_and_service_without_charging(quantity):
    match, teams, tokens, _ = room()
    with pytest.raises(ValidationError) as error:
        UnitService.deploy_units(match, teams[0], "infantry", teams[1].pk, quantity=quantity)
    assert error.value.code == "INVALID_QUANTITY"
    response = APIClient().post(f"/api/v1/matches/{match.pk}/actions/deploy/", {
        "unit_type_code_or_id": "infantry", "target_team_id": str(teams[1].pk), "quantity": quantity},
        format="json", HTTP_X_PARTICIPANT_TOKEN=tokens[0])
    assert response.status_code == 400
    assert not match.entities.exists() and not CoinTransaction.objects.filter(match=match, transaction_type="DEPLOY_UNIT").exists()


@pytest.mark.django_db
def test_rest_defaults_to_one_and_returns_batch_and_single_compatibility():
    match, teams, tokens, _ = room()
    for quantity in [None, 5]:
        payload = {"unit_type_code_or_id": "infantry", "target_team_id": str(teams[1].pk), "idempotency_key": f"q{quantity}"}
        if quantity:
            payload["quantity"] = quantity
        response = APIClient().post(f"/api/v1/matches/{match.pk}/actions/deploy/", payload,
            format="json", HTTP_X_PARTICIPANT_TOKEN=tokens[0])
        assert response.status_code == 200, response.data
        assert len(response.data["entities"]) == response.data["quantity"] == (quantity or 1)
        assert response.data["entity"]["id"] == response.data["entities"][0]["id"]


@pytest.mark.django_db
def test_preupgrade_single_action_retry_accepts_original_catalog_uuid():
    match, teams, _, _ = room()
    unit = UnitType.objects.get(code="infantry")
    action, entity = UnitService.deploy_unit(match, teams[0], str(unit.pk), teams[1].pk,
                                            idempotency_key="old-client")
    # Original deployment actions had no quantity, batch IDs, catalog UUID or spawn fingerprint.
    for key in ("quantity", "entity_ids", "unit_type_id", "spawn_node_id"):
        action.payload.pop(key)
    action.save(update_fields=["payload"])
    retry, entities = UnitService.deploy_units(match, teams[0], str(unit.pk), teams[1].pk,
        idempotency_key="old-client", spawn_node_id="node_spawn_t1")
    assert retry.pk == action.pk and [e.pk for e in entities] == [entity.pk]
    teams[0].refresh_from_db()
    assert teams[0].coins == 485 and match.entities.count() == 1


@pytest.mark.django_db
def test_vehicle_capacity_and_insufficient_coins_reject_entire_batches():
    match, teams, _, _ = room(initial_coins=200)
    unlock(teams[0], "tank")
    _, entities = UnitService.deploy_units(match, teams[0], "tank", teams[1].pk, quantity=3)
    assert len(entities) == 3
    for code, quantity, reason in [("tank", 3, "UNIT_LIMIT_REACHED"), ("infantry", 10, "INSUFFICIENT_COINS")]:
        with pytest.raises(ValidationError) as error:
            UnitService.deploy_units(match, teams[0], code, teams[1].pk, quantity=quantity)
        assert error.value.code == reason
    assert match.entities.count() == 3 and match.game_actions.count() == 1
    teams[0].refresh_from_db()
    assert teams[0].coins == 95


@pytest.mark.django_db
def test_spawn_failure_rolls_back_whole_batch_and_formation_sequence():
    match, teams, _, _ = room()
    unlock(teams[0], "tank")
    from apps.combat.formation import initialize_spawn
    count = 0
    def fail_second(*args):
        nonlocal count
        count += 1
        if count == 2:
            raise ValidationError("Khu tập kết đã đầy")
        return initialize_spawn(*args)
    before = Match.objects.get(pk=match.pk).configuration.copy()
    with patch("apps.combat.formation.initialize_spawn", side_effect=fail_second):
        with pytest.raises(ValidationError):
            UnitService.deploy_units(match, teams[0], "tank", teams[1].pk, quantity=3)
    assert not match.entities.exists() and not match.game_actions.exists()
    assert not CoinTransaction.objects.filter(team=teams[0], transaction_type="DEPLOY_UNIT").exists()
    teams[0].refresh_from_db()
    match.refresh_from_db()
    assert teams[0].coins == 500 and match.configuration == before


@pytest.mark.django_db
def test_spawn_ownership_unlock_and_idempotency_payload_conflicts():
    match, teams, _, _ = room()
    with pytest.raises(ValidationError) as error:
        UnitService.deploy_units(match, teams[0], "infantry", teams[1].pk, quantity=5, spawn_node_id="node_spawn_t2")
    assert error.value.code == "INVALID_POSITION"
    with pytest.raises(ValidationError) as error:
        UnitService.deploy_units(match, teams[0], "tank", teams[1].pk, quantity=3)
    assert error.value.code == "UNIT_LOCKED"
    UnitService.deploy_units(match, teams[0], "infantry", teams[1].pk, quantity=5, idempotency_key="same")
    with pytest.raises(ValidationError) as error:
        UnitService.deploy_units(match, teams[0], "infantry", teams[1].pk, quantity=1, idempotency_key="same")
    assert error.value.code == "IDEMPOTENCY_CONFLICT" and match.entities.count() == 5


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_two_clients_batch_tanks_sixth_tower_live_combat_and_reconnect():
    match, teams, tokens, _ = await database_sync_to_async(room)(battle=30)
    await database_sync_to_async(unlock)(teams[1], "tank")
    for i in range(1, 6):
        await database_sync_to_async(ConstructionService.build_tower)(match, teams[0], "mg_tower", f"node_tower_t1_slot{i}")
    comms = [WebsocketCommunicator(application, f"/ws/matches/{match.pk}/?token={token}") for token in tokens[:2]]
    async def until(comm, event_type):
        for _ in range(30):
            event = await comm.receive_json_from(timeout=10)
            if event["event_type"] == event_type:
                return event
        pytest.fail(f"Missing {event_type}")
    try:
        for comm in comms:
            assert (await comm.connect())[0]
            await until(comm, "MATCH_STATE_SNAPSHOT")
        for i, code, quantity in [(0, "infantry", 5), (1, "tank", 3)]:
            await comms[i].send_json_to({"event_type": "DEPLOY_REQUEST", "payload": {
                "unit_code": code, "target_team_id": str(teams[1-i].pk), "quantity": quantity, "idempotency_key": f"socket-{i}"}})
            events = await asyncio.gather(*(until(c, "ENTITIES_CREATED") for c in comms))
            ids = [e["id"] for e in events[0]["payload"]["entities"]]
            assert len(ids) == len(set(ids)) == quantity
            assert [e["id"] for e in events[1]["payload"]["entities"]] == ids
        await database_sync_to_async(ConstructionService.build_tower)(match, teams[0], "mg_tower", "node_tower_t1_slot6")
        events = await asyncio.gather(*(until(c, "TOWER_BUILT") for c in comms))
        assert all(e["payload"]["node_id"] == "node_tower_t1_slot6" for e in events)
        match = await database_sync_to_async(MatchService.advance_phase)(match)
        await database_sync_to_async(ContinuousCombatService.tick)(match.pk, datetime.fromisoformat(match.configuration["timer_state"]["next_tick_at"]))
        await asyncio.gather(*(until(c, "COMBAT_TICK") for c in comms))
        await comms[0].disconnect()
        comms[0] = WebsocketCommunicator(application, f"/ws/matches/{match.pk}/?token={tokens[0]}")
        assert (await comms[0].connect())[0]
        snapshot = await until(comms[0], "MATCH_STATE_SNAPSHOT")
        entities = snapshot["payload"]["entities"]
        assert len(entities) == len({e["id"] for e in entities}) == 14
    finally:
        await asyncio.gather(*(c.disconnect() for c in comms))
        await database_sync_to_async(connections.close_all)()
