"""Team type upgrades through real services, snapshots and authenticated fan-out."""

import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.core.exceptions import ValidationError
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from apps.combat.balance import attack_cooldown, attack_damage
from apps.combat.continuous_service import ContinuousCombatService
from apps.economy.models import CoinTransaction
from apps.matches.models import MatchEvent
from apps.matches.services import MatchService
from apps.questions.models import Question
from apps.questions.services import QuestionService
from apps.realtime.services import RealtimeService
from apps.units.models import GameEntity, TeamUnitUpgrade, TeamUnlock, UnitType
from apps.units.serializers import UnitTypeSerializer
from apps.units.services import ConstructionService, TeamUpgradeService, UnitService
from apps.units.upgrades import effective_stats
from config.asgi import application
from tests.test_battle_websocket import until
from tests.test_continuous_combat import room


@pytest.mark.django_db
@pytest.mark.parametrize(
    "code", ["infantry", "tank", "artillery", "mg_tower", "cannon_tower", "shield_generator"]
)
def test_all_types_existing_future_hp_cost_caps_and_opponent_isolation(code):
    match, teams, _, _ = room(initial_coins=5000, max_active_units_per_team=30)
    a, b = teams
    unit = UnitType.objects.get(code=code)
    for team in teams:
        if not unit.is_starter:
            TeamUnlock.objects.get_or_create(team=team, unit_type=unit)

    def spawn(team, index=1):
        if unit.category == "UNIT":
            return UnitService.deploy_units(
                match,
                team,
                code,
                str(b.pk if team == a else a.pk),
                quantity=10 if code == "infantry" and index == 1 else 1,
            )[1]
        return [
            ConstructionService.build_tower(
                match, team, code, f"node_tower_t{1 if team == a else 2}_slot{index}"
            )[1]
        ]

    old = spawn(a)
    enemy = spawn(b)[0]
    old[0].current_hp = old[0].max_hp // 2
    old[0].save(update_fields=["current_hp"])
    wreck = GameEntity.objects.create(
        match=match,
        team=a,
        unit_type=unit,
        entity_kind=unit.category,
        status="DESTROYED",
        current_hp=0,
        max_hp=80,
    )
    a.refresh_from_db()
    before = a.coins
    original_sim = old[0].simulation_state.copy()
    for level in (1, 2):
        key = f"{code}-{level}"
        action, payload = TeamUpgradeService.purchase(match, a, code, level, key)
        assert payload["level"] == level + 1
        assert TeamUpgradeService.purchase(match, a, code, level, key)[0].pk == action.pk
        expected = effective_stats(unit, level + 1, match.configuration)
        for e in old:
            e.refresh_from_db()
            assert e.level == level + 1 and e.max_hp == expected["hp"]
        assert old[0].simulation_state == original_sim
        assert abs(old[0].current_hp / old[0].max_hp - 0.5) < 0.02
        enemy.refresh_from_db()
        wreck.refresh_from_db()
        assert enemy.level == 1 and wreck.current_hp == 0 and wreck.status == "DESTROYED"
    future = spawn(a, 2)[0]
    assert future.level == 3 and future.max_hp == old[0].max_hp
    assert (
        RealtimeService.build_snapshot(match, str(a.pk))["payload"]["team_upgrades"][str(a.pk)][
            code
        ]
        == 3
    )
    assert (
        UnitTypeSerializer(unit, context={"team": a, "match": match}).data["upgrade"]["next_stats"]
        is None
    )
    purchases = CoinTransaction.objects.filter(team=a, reference_type="UPGRADE_TEAM_TYPE")
    assert purchases.count() == 2
    from apps.units.upgrades import UPGRADE_COSTS
    costs = UPGRADE_COSTS["tower" if unit.category == "TOWER" else code]
    assert sorted(-tx.amount for tx in purchases) == costs
    a.refresh_from_db()
    assert a.coins == before - sum(costs) - unit.cost
    with pytest.raises(ValidationError):
        TeamUpgradeService.purchase(match, a, code, 3, "level-four")
    assert TeamUnitUpgrade.objects.get(team=a, unit_type=unit).level == 3
    with pytest.raises(ValidationError):
        TeamUpgradeService.purchase(match, a, code, 1, "stale")
    assert TeamUnitUpgrade.objects.get(team=a, unit_type=unit).level == 3
    assert purchases.count() == 2


@pytest.mark.django_db
def test_auth_locked_insufficient_conflicting_retry_and_battle_phase():
    match, teams, tokens, _ = room(initial_coins=500)
    client = APIClient()
    url = f"/api/v1/matches/{match.pk}/upgrades/"
    data = {"entity_type": "infantry", "expected_current_level": 1, "idempotency_key": "purchase"}
    assert client.post(url, data, format="json").status_code == 401
    client.credentials(HTTP_X_PARTICIPANT_TOKEN=tokens[2])
    assert client.post(url, data, format="json").status_code in (400, 403)
    client.credentials(HTTP_X_PARTICIPANT_TOKEN=tokens[0])
    assert client.post(url, {**data, "entity_type": "tank"}, format="json").status_code == 400
    match = MatchService.advance_phase(match)
    assert match.phase == "WAR"
    assert client.post(url, data, format="json").status_code == 200
    assert client.post(url, data, format="json").status_code == 200
    assert client.post(url, {**data, "expected_current_level": 2}, format="json").status_code == 400
    assert client.post(url, {**data, "expected_current_level": 0}, format="json").status_code == 400
    assert client.post(url, {**data, "expected_current_level": 4}, format="json").status_code == 400
    assert (
        client.post(
            url, {**data, "expected_current_level": True, "idempotency_key": "bool"}, format="json"
        ).status_code
        == 400
    )
    teams[0].coins = 0
    teams[0].save(update_fields=["coins"])
    assert (
        client.post(
            url, {**data, "expected_current_level": 2, "idempotency_key": "poor"}, format="json"
        ).status_code
        == 400
    )
    assert TeamUnitUpgrade.objects.get(team=teams[0]).level == 2
    # Legacy route is a team-type adapter, including safe retries.
    teams[0].coins = 500
    teams[0].save(update_fields=["coins"])
    _, tower = ConstructionService.build_tower(match, teams[0], "mg_tower", "node_tower_t1_slot1")
    for _ in range(2):
        _, upgraded = ConstructionService.upgrade_tower(
            match, teams[0], tower.pk, idempotency_key="legacy"
        )
        assert upgraded.level == 2
    with pytest.raises(ValidationError):
        TeamUpgradeService.purchase(
            match, teams[0], "infantry", 2, "other", actor=teams[1].members.first()
        )


@pytest.mark.django_db
def test_upgraded_combat_tick_keeps_hp_level_range_motion_and_fractional_damage():
    match, teams, _, _ = room(initial_coins=1000)
    _, entity = UnitService.deploy_unit(match, teams[0], "infantry", str(teams[1].pk))
    entity.current_hp = 40
    entity.save(update_fields=["current_hp"])
    match = MatchService.advance_phase(match)
    TeamUpgradeService.purchase(match, teams[0], "infantry", 1, "live")
    tick = timezone.datetime.fromisoformat(match.configuration["timer_state"]["next_tick_at"])
    ContinuousCombatService.tick(match.pk, tick)
    entity.refresh_from_db()
    assert entity.level == 2 and entity.current_hp == 46 and entity.max_hp == 92
    assert entity.simulation_state["attack_range"] == 1
    state = {
        "unit_type_code": "infantry",
        "damage": 10,
        "level": 3,
        "entity_kind": "UNIT",
        "simulation_state": {},
    }
    assert sum(attack_damage(state) for _ in range(4)) == 32
    assert attack_cooldown(state, {}) == round(2 / 1.5 / 1.25, 2)


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_upgrade_socket_same_team_opponent_and_reconnect():
    match, teams, tokens, _ = await database_sync_to_async(room)(initial_coins=1000)
    from apps.matches.services import hash_token
    from apps.teams.models import TeamMember

    teammate_token = "pt_" + uuid.uuid4().hex
    await database_sync_to_async(TeamMember.objects.create)(
        match=match, team=teams[0], display_name="Teammate", token_hash=hash_token(teammate_token)
    )
    clients = [
        WebsocketCommunicator(application, f"/ws/matches/{match.pk}/?token={token}")
        for token in (tokens[0], teammate_token, tokens[1])
    ]
    for client in clients:
        assert (await client.connect())[0]
        await until(client, "MATCH_STATE_SNAPSHOT")
    try:
        await clients[0].send_json_to(
            {
                "event_type": "UPGRADE_REQUEST",
                "payload": {
                    "entity_type": "infantry",
                    "expected_current_level": 1,
                    "idempotency_key": "socket-upgrade",
                },
            }
        )
        await until(clients[0], "ACTION_ACCEPTED")
        for client in clients[1:]:
            event = await until(client, "TEAM_UNIT_UPGRADED")
            assert event["payload"]["level"] == 2
            assert event["payload"]["team_id"] == str(teams[0].pk)
        await clients[0].disconnect()
        clients[0] = WebsocketCommunicator(
            application, f"/ws/matches/{match.pk}/?token={tokens[0]}"
        )
        assert (await clients[0].connect())[0]
        snapshot = (await until(clients[0], "MATCH_STATE_SNAPSHOT"))["payload"]
        assert snapshot["team_upgrades"][str(teams[0].pk)]["infantry"] == 2
        assert snapshot["team_upgrades"][str(teams[1].pk)] == {}
    finally:
        for client in clients:
            await client.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(connection.vendor != "postgresql", reason="Requires PostgreSQL row locks")
def test_concurrent_upgrades_spawns_and_ticks_serialize():
    from tests.test_round_concurrency import concurrent

    match, teams, _, _ = room(initial_coins=5000)
    UnitService.deploy_units(match, teams[0], "infantry", str(teams[1].pk), quantity=10)
    results = concurrent(
        lambda _: TeamUpgradeService.purchase(match, teams[0], "infantry", 1, "same-key")
    )
    assert len({action.pk for action, _ in results}) == 1
    assert (
        CoinTransaction.objects.filter(team=teams[0], reference_type="UPGRADE_TEAM_TYPE").count()
        == 1
    )
    match = MatchService.advance_phase(match)
    tick = timezone.datetime.fromisoformat(match.configuration["timer_state"]["next_tick_at"])

    def run(i):
        if i == 0:
            return TeamUpgradeService.purchase(match, teams[0], "infantry", 2, "second")
        if i == 1:
            return ContinuousCombatService.tick(match.pk, tick)
        return UnitService.deploy_units(match, teams[0], "infantry", str(teams[1].pk), quantity=5)

    concurrent(run, count=3)
    assert GameEntity.objects.filter(team=teams[0], level=3, max_hp=104).count() == 15

    def compete(i):
        try:
            return TeamUpgradeService.purchase(match, teams[0], "infantry", 3, f"different-{i}")[
                0
            ].pk
        except ValidationError:
            return None

    results = concurrent(compete)
    assert sum(value is not None for value in results) == 0
    assert (
        CoinTransaction.objects.filter(team=teams[0], reference_type="UPGRADE_TEAM_TYPE").count()
        == 2
    )


@pytest.mark.django_db
@pytest.mark.parametrize("code,damage,interval", [("infantry", 8, 1.07), ("artillery", 32, 1.6)])
def test_level_three_troop_boost_matches_actual_combat(code, damage, interval):
    unit = UnitType.objects.get(code=code)
    stats = effective_stats(unit, 3, {"gameplay_mode": "CONTINUOUS"})
    assert stats["hp"] == 128
    assert stats["damage"] == damage
    assert stats["attack_interval_seconds"] == interval
    entity = {
        "unit_type_code": code, "entity_kind": "UNIT", "level": 3,
        "damage": unit.base_stats["damage"], "simulation_state": {},
    }
    assert attack_damage(entity) == damage
    assert attack_cooldown(entity, {}) == interval
    assert effective_stats(unit, 2)["hp"] == 92
    assert effective_stats(unit, 2)["damage"] == round(unit.base_stats["damage"] * 1.1)
