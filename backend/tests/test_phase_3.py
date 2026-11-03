import threading

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, connection, transaction
from rest_framework import status
from rest_framework.test import APIClient

from apps.economy.models import CoinTransaction, TransactionType
from apps.economy.services import EconomyService
from apps.matches.models import Match, MatchStatus
from apps.matches.services import MatchService, hash_token
from apps.teams.models import MemberRole, Team, TeamMember, TeamStatus
from apps.units.map import MapDefinition
from apps.units.models import (
    EntityCategory,
    EntityStatus,
    GameEntity,
    TeamUnlock,
    UnitType,
)
from apps.units.seeds import ensure_standard_units
from apps.units.services import ConstructionService, UnitService


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def setup_match():
    """Create an active match with 4 teams and standard units seeded."""
    ensure_standard_units()
    match, host_token = MatchService.create_match(name="Phase 3 Test Arena", configuration={"tower_placement_version":0,"arena_layout_version":5})
    teams = []
    plain_tokens = []

    for i in range(4):
        team = Team.objects.create(match=match, name=f"Team {chr(65 + i)}")
        # Mentor
        pt1 = f"pt_mentor_{i}"
        TeamMember.objects.create(
            match=match,
            team=team,
            display_name=f"Mentor-{i}",
            role=MemberRole.MENTOR,
            token_hash=hash_token(pt1),
        )
        # Mentee
        pt2 = f"pt_mentee_{i}"
        TeamMember.objects.create(
            match=match,
            team=team,
            display_name=f"Mentee-{i}",
            role=MemberRole.MENTEE,
            token_hash=hash_token(pt2),
        )
        team.is_ready = True
        team.save()
        teams.append(team)
        plain_tokens.append(pt1)

    started_match = MatchService.start_match(match)
    return started_match, host_token, teams, plain_tokens


@pytest.mark.django_db
def test_coin_balance_cannot_be_negative_and_failed_purchase_retains_balance(setup_match):
    """
    §7.3: Coin balance cannot be negative; failed purchases do not deduct coins.
    """
    match, _, teams, _ = setup_match
    team = teams[0]
    assert team.coins == 100

    # 1. Successful debit
    tx1 = EconomyService.debit(team, 40, TransactionType.PURCHASE)
    team.refresh_from_db()
    assert team.coins == 60
    assert tx1.amount == -40
    assert tx1.balance_after == 60

    # 2. Insufficient debit -> raises ValidationError without changing balance
    with pytest.raises(ValidationError) as exc_info:
        EconomyService.debit(team, 70, TransactionType.PURCHASE)
    assert "Không đủ coin" in str(exc_info.value)

    team.refresh_from_db()
    assert team.coins == 60  # Balance retains exact same value!

    # 3. DB CheckConstraint: team_coins_gte_0 directly in DB
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            team.coins = -10
            team.save()


@pytest.mark.django_db
def test_unit_and_tower_capacity_limits_and_destroyed_frees_slot(setup_match):
    """
    §8.5: Maximum 5 non-Infantry units; legacy tower foundations cannot overlap.
    Destroyed units/structures no longer count toward capacity.
    """
    match, _, teams, _ = setup_match
    team_a = teams[0]
    team_b = teams[1]

    # Give team sufficient coins for capacity testing
    team_a.coins = 500
    team_a.save()

    tank = UnitType.objects.get(code="tank")
    TeamUnlock.objects.get_or_create(team=team_a, unit_type=tank)
    slots = MapDefinition.get_valid_tower_slots(team_a)

    # Deploy 5 active units (hits capacity limit)
    for i in range(5):
        action, entity = UnitService.deploy_unit(
            match=match,
            team=team_a,
            unit_type_code_or_id="tank",
            target_team_id=str(team_b.id),
            idempotency_key=f"deploy-cap-{i}",
        )
        assert entity.status == EntityStatus.ACTIVE

    # 6th deployment should be rejected
    with pytest.raises(ValidationError) as exc:
        UnitService.deploy_unit(
            match=match,
            team=team_a,
            unit_type_code_or_id="tank",
            target_team_id=str(team_b.id),
            idempotency_key="deploy-cap-overflow",
        )
    assert "giới hạn tối đa 5 đơn vị chiến đấu" in str(exc.value)

    # Mark one unit destroyed (§8.5)
    first_entity = GameEntity.objects.filter(team=team_a, entity_kind=EntityCategory.UNIT).first()
    first_entity.status = EntityStatus.DESTROYED
    first_entity.save()

    # Now a 6th deployment must succeed because destroyed unit freed up capacity
    action6, entity6 = UnitService.deploy_unit(
        match=match,
        team=team_a,
        unit_type_code_or_id="tank",
        target_team_id=str(team_b.id),
        idempotency_key="deploy-cap-freed",
    )
    assert entity6 is not None

    # Tower Capacity: Build 3 towers on the 3 valid slots
    for i in range(3):
        ConstructionService.build_tower(
            match=match,
            team=team_a,
            unit_type_code_or_id="mg_tower",
            node_id=slots[i],
            idempotency_key=f"build-tower-{i}",
        )

    # Reusing an occupied legacy foundation must fail placement.
    with pytest.raises(ValidationError) as exc_tower:
        ConstructionService.build_tower(
            match=match,
            team=team_a,
            unit_type_code_or_id="mg_tower",
            node_id="node_tower_t1_slot1",
            idempotency_key="build-tower-overflow",
        )
    assert "đã có tháp phòng thủ" in str(exc_tower.value)


@pytest.mark.django_db
def test_locked_unit_cannot_be_deployed_and_invalid_node_rejected_without_debit(setup_match):
    """
    §6.3, §9.3: Locked units cannot be deployed. Invalid or occupied nodes are rejected without deducting coins.
    """
    match, _, teams, _ = setup_match
    team_a = teams[0]
    team_b = teams[1]
    init_coins = team_a.coins

    # Tank is an unlockable unit, not starter
    tank = UnitType.objects.get(code="tank")
    assert not TeamUnlock.objects.filter(team=team_a, unit_type=tank).exists()

    # Deploying locked tank should fail
    with pytest.raises(ValidationError) as exc:
        UnitService.deploy_unit(
            match=match,
            team=team_a,
            unit_type_code_or_id="tank",
            target_team_id=str(team_b.id),
        )
    assert "chưa được mở khóa" in str(exc.value)

    team_a.refresh_from_db()
    assert team_a.coins == init_coins  # No coins deducted!

    # Invalid tower placement node: node belonging to Team B territory
    team_b_slots = MapDefinition.get_valid_tower_slots(team_b)
    with pytest.raises(ValidationError) as exc_node:
        ConstructionService.build_tower(
            match=match,
            team=team_a,
            unit_type_code_or_id="mg_tower",
            node_id=team_b_slots[0],
        )
    assert "không hợp lệ hoặc không thuộc lãnh thổ" in str(exc_node.value)

    team_a.refresh_from_db()
    assert team_a.coins == init_coins  # No coins deducted!


@pytest.mark.django_db
def test_target_validation_cannot_target_self_or_eliminated_team(setup_match):
    """
    §9.4: Target base must belong to another active team. Cannot target own team or eliminated teams.
    """
    match, _, teams, _ = setup_match
    team_a = teams[0]
    team_b = teams[1]

    # 1. Target own team
    with pytest.raises(ValidationError) as exc_self:
        UnitService.deploy_unit(
            match=match,
            team=team_a,
            unit_type_code_or_id="infantry",
            target_team_id=str(team_a.id),
        )
    assert "Không thể chỉ định căn cứ của chính đội mình" in str(exc_self.value)

    # 2. Target eliminated team
    team_b.status = TeamStatus.ELIMINATED
    team_b.save()

    with pytest.raises(ValidationError) as exc_elim:
        UnitService.deploy_unit(
            match=match,
            team=team_a,
            unit_type_code_or_id="infantry",
            target_team_id=str(team_b.id),
        )
    assert "đã bị phá hủy hoặc loại" in str(exc_elim.value)


@pytest.mark.django_db
def test_repair_base_limits_and_max_hp_and_upgrade_tower_limit(setup_match):
    """
    §8.4: Repair base restores 50 HP (cannot exceed max), max 1 repair/round.
    Upgrade tower: 1 upgrade/tower (+25% damage), stores level.
    """
    match, _, teams, _ = setup_match
    team_a = teams[0]
    team_a.coins = 200
    team_a.save()

    # 1. Repair on full HP base -> rejected
    assert team_a.base_hp == team_a.initial_base_hp == 500
    with pytest.raises(ValidationError) as exc_full:
        ConstructionService.repair_base(match=match, team=team_a)
    assert "Căn cứ đã đạt lượng máu tối đa" in str(exc_full.value)

    # Damage base
    team_a.base_hp = 420
    team_a.save()

    # Repair base
    action = ConstructionService.repair_base(match=match, team=team_a, idempotency_key="rep-1")
    team_a.refresh_from_db()
    assert team_a.base_hp == 470
    assert team_a.coins == 180

    # Second repair in the same round window -> rejected
    with pytest.raises(ValidationError) as exc_rep2:
        ConstructionService.repair_base(match=match, team=team_a, idempotency_key="rep-2")
    assert "Mỗi round chỉ được sửa chữa 1 lần" in str(exc_rep2.value)

    # 2. Tower upgrade: Build tower first
    slots = MapDefinition.get_valid_tower_slots(team_a)
    build_action, tower = ConstructionService.build_tower(
        match=match,
        team=team_a,
        unit_type_code_or_id="mg_tower",
        node_id=slots[0],
        idempotency_key="build-upg-test",
    )
    assert tower.level == 1

    # Upgrade tower
    upg_action, upg_tower = ConstructionService.upgrade_tower(
        match=match,
        team=team_a,
        entity_id=str(tower.id),
        idempotency_key="upg-1",
    )
    assert upg_tower.level == 2

    # Type upgrades support Level 3, then reject Level 4.
    team_a.coins = 1000
    team_a.save(update_fields=["coins"])
    for level in (3,):
        _, upgraded = ConstructionService.upgrade_tower(match, team_a, str(tower.pk), idempotency_key=f"upg-{level}")
        assert upgraded.level == level
    with pytest.raises(ValidationError, match="CẤP TỐI ĐA"):
        ConstructionService.upgrade_tower(match, team_a, str(tower.pk), idempotency_key="upg-4")


@pytest.mark.django_db
def test_scenario_d_insufficient_coins_rejected_and_balance_unchanged(setup_match):
    """
    Scenario D (§28, Phase 3 §4):
    Team with 10 coins tries to deploy Infantry (15 coins).
    Rejected by server, no entity created, coin balance remains 10.
    """
    match, _, teams, _ = setup_match
    team_a = teams[0]
    team_b = teams[1]

    team_a.coins = 10
    team_a.save()

    entity_count_before = GameEntity.objects.count()
    tx_count_before = CoinTransaction.objects.count()

    with pytest.raises(ValidationError) as exc:
        UnitService.deploy_unit(
            match=match,
            team=team_a,
            unit_type_code_or_id="infantry",
            target_team_id=str(team_b.id),
        )

    assert "Không đủ coin" in str(exc.value)

    team_a.refresh_from_db()
    assert team_a.coins == 10
    assert GameEntity.objects.count() == entity_count_before
    assert CoinTransaction.objects.count() == tx_count_before


@pytest.mark.django_db
def test_duplicate_request_idempotency(setup_match):
    """
    §19.10, Phase 3 §4:
    Sending the same action with the same idempotency_key returns original result
    without double charging coins or creating duplicate entities.
    """
    match, _, teams, _ = setup_match
    team_a = teams[0]
    team_b = teams[1]

    idem_key = "test-idempotent-key-123"

    # First request
    action1, entity1 = UnitService.deploy_unit(
        match=match,
        team=team_a,
        unit_type_code_or_id="infantry",
        target_team_id=str(team_b.id),
        idempotency_key=idem_key,
    )
    team_a.refresh_from_db()
    coins_after_first = team_a.coins
    assert coins_after_first == 85  # 100 - 15

    # Second identical request with same idempotency key
    action2, entity2 = UnitService.deploy_unit(
        match=match,
        team=team_a,
        unit_type_code_or_id="infantry",
        target_team_id=str(team_b.id),
        idempotency_key=idem_key,
    )

    team_a.refresh_from_db()
    assert team_a.coins == coins_after_first  # Not charged a second time!
    assert action1.id == action2.id
    assert entity1.id == entity2.id
    assert GameEntity.objects.filter(team=team_a).count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_purchases_race_condition(setup_match):
    """
    §7.3, Phase 3 §4:
    Two concurrent requests try to spend coins when only enough for one.
    Only one must succeed; total balance cannot become negative.
    """
    match, _, teams, _ = setup_match
    team_a = teams[0]
    team_b = teams[1]

    # Set coins to 20 (Infantry costs 15, so only 1 can be bought)
    team_a.coins = 20
    team_a.save()

    results = []
    errors = []

    def purchase_worker(worker_id):
        for attempt in range(5):
            try:
                # Each thread opens its own db connection
                connection.close()
                t = Team.objects.get(pk=team_a.id)
                m = Match.objects.get(pk=match.id)
                action, entity = UnitService.deploy_unit(
                    match=m,
                    team=t,
                    unit_type_code_or_id="infantry",
                    target_team_id=str(team_b.id),
                    idempotency_key=f"concurrent-{worker_id}",
                )
                results.append(action)
                return
            except OperationalError:
                import time
                time.sleep(0.05 * (attempt + 1))
            except Exception as e:
                errors.append(e)
                return
            finally:
                connection.close()
        errors.append(OperationalError("Lock timeout after retries"))

    t1 = threading.Thread(target=purchase_worker, args=(1,))
    t2 = threading.Thread(target=purchase_worker, args=(2,))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    team_a.refresh_from_db()
    assert team_a.coins >= 0
    assert len(results) == 1, f"Results: {results}, Errors: {[repr(e) for e in errors]}"
    assert len(errors) == 1
    assert team_a.coins == 5  # 20 - 15 = 5


@pytest.mark.django_db
def test_coin_transaction_audit_trail_matches_balance(setup_match):
    """
    §7.3, §19.11: Audit trail in CoinTransaction must sum up and match final balance exactly.
    """
    match, _, teams, _ = setup_match
    team = teams[0]

    # Team starts with 100
    assert team.coins == 100

    # Credit 25
    EconomyService.credit(team, 25, TransactionType.REWARD_COIN, description="Quiz reward")
    # Debit 15
    EconomyService.debit(team, 15, TransactionType.DEPLOY_UNIT, description="Deploy Infantry")
    # Debit 25
    EconomyService.debit(team, 25, TransactionType.BUILD_TOWER, description="Build Tower")
    # Credit 10
    EconomyService.credit(team, 10, TransactionType.PASSIVE_INCOME, description="Passive Income")

    team.refresh_from_db()
    assert team.coins == 95  # 100 + 25 - 15 - 25 + 10 = 95

    # Sum of CoinTransactions
    total_tx = sum(tx.amount for tx in CoinTransaction.objects.filter(team=team))
    assert total_tx == 95
    assert CoinTransaction.objects.filter(team=team).first().balance_after == 95


@pytest.mark.django_db
def test_passive_income_awarded_once_per_round_not_when_paused(setup_match):
    """
    §7.2: Passive income (10 coins/round) awarded to all active teams, not when paused.
    """
    match, _, teams, _ = setup_match

    # Match active -> award round 1
    txs = EconomyService.award_passive_income(match, round_number=1)
    assert len(txs) == 4
    for t in teams:
        t.refresh_from_db()
        assert t.coins == 110  # 100 + 10

    # Pause match
    match.status = MatchStatus.PAUSED
    match.save()

    # Trying to award during pause must return []
    txs_paused = EconomyService.award_passive_income(match, round_number=2)
    assert txs_paused == []
    for t in teams:
        t.refresh_from_db()
        assert t.coins == 110  # Balance unchanged!


@pytest.mark.django_db
def test_action_api_endpoints_deploy_build_upgrade_repair_scout_emp(api_client, setup_match):
    """
    Test REST APIs:
    - POST /matches/{id}/actions/deploy/
    - POST /matches/{id}/actions/build/
    - POST /matches/{id}/actions/upgrade/
    - POST /matches/{id}/actions/repair/
    - POST /matches/{id}/actions/scout/
    - POST /matches/{id}/actions/emp/
    """
    match, host_token, teams, plain_tokens = setup_match
    team_a = teams[0]
    team_b = teams[1]
    token_a = plain_tokens[0]

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_a}")

    # 1. Deploy Unit API
    deploy_res = api_client.post(
        f"/api/v1/matches/{match.id}/actions/deploy/",
        {
            "unit_type_code_or_id": "infantry",
            "target_team_id": str(team_b.id),
            "idempotency_key": "api-deploy-1",
        },
        format="json",
    )
    assert deploy_res.status_code == status.HTTP_200_OK
    assert deploy_res.data["team_coins"] == 85
    assert deploy_res.data["action"]["action_type"] == "DEPLOY_UNIT"
    assert deploy_res.data["entity"]["unit_type_code"] == "infantry"

    # 2. Build Tower API
    slots = MapDefinition.get_valid_tower_slots(team_a)
    build_res = api_client.post(
        f"/api/v1/matches/{match.id}/actions/build/",
        {
            "unit_type_code_or_id": "mg_tower",
            "node_id": slots[0],
            "idempotency_key": "api-build-1",
        },
        format="json",
    )
    assert build_res.status_code == status.HTTP_200_OK
    assert build_res.data["team_coins"] == 60  # 85 - 25
    tower_entity_id = build_res.data["entity"]["id"]

    # Fund the team-wide upgrade (70), leaving 35 for later actions.
    team_a.coins = 105
    team_a.save(update_fields=["coins"])
    # 3. Upgrade Tower API
    upgrade_res = api_client.post(
        f"/api/v1/matches/{match.id}/actions/upgrade/",
        {
            "entity_id": tower_entity_id,
            "idempotency_key": "api-upgrade-1",
        },
        format="json",
    )
    assert upgrade_res.status_code == status.HTTP_200_OK
    assert upgrade_res.data["team_coins"] == 35  # 105 - 70
    assert upgrade_res.data["entity"]["level"] == 2

    # 4. Repair Base API (damage first)
    team_a.refresh_from_db()
    team_a.base_hp = 400
    team_a.save(update_fields=["base_hp"])
    repair_res = api_client.post(
        f"/api/v1/matches/{match.id}/actions/repair/",
        {"idempotency_key": "api-repair-1"},
        format="json",
    )
    assert repair_res.status_code == status.HTTP_200_OK
    assert repair_res.data["team_base_hp"] == 450
    assert repair_res.data["team_coins"] == 15  # 35 - 20

    # 5. Scout API
    scout_res = api_client.post(
        f"/api/v1/matches/{match.id}/actions/scout/",
        {
            "target_team_id": str(team_b.id),
            "idempotency_key": "api-scout-1",
        },
        format="json",
    )
    assert scout_res.status_code == status.HTTP_200_OK
    assert scout_res.data["team_coins"] == 5  # 15 - 10
    assert "unlocked_units" in scout_res.data["scout_data"]

    # 6. EMP API (give Team A coins to test EMP)
    team_a.coins = 50
    team_a.save()

    # Build a tower for Team B to EMP
    slots_b = MapDefinition.get_valid_tower_slots(team_b)
    _, tower_b = ConstructionService.build_tower(
        match=match,
        team=team_b,
        unit_type_code_or_id="mg_tower",
        node_id=slots_b[0],
    )

    emp_res = api_client.post(
        f"/api/v1/matches/{match.id}/actions/emp/",
        {
            "target_entity_id": str(tower_b.id),
            "idempotency_key": "api-emp-1",
        },
        format="json",
    )
    assert emp_res.status_code == status.HTTP_200_OK
    assert emp_res.data["team_coins"] == 20  # 50 - 30
    assert emp_res.data["entity"]["status"] == "DISABLED"


@pytest.mark.django_db
def test_team_state_endpoint_isolation_and_permissions(api_client, setup_match):
    """
    GET /matches/{id}/teams/{team_id}/state/
    Ensures that only team members (and host) can access team state snapshot (§19.7, §2.5).
    """
    match, host_token, teams, plain_tokens = setup_match
    team_a = teams[0]
    team_b = teams[1]
    token_a = plain_tokens[0]
    token_b = plain_tokens[1]

    # Team A member requests Team A state -> 200 OK
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_a}")
    res_a = api_client.get(f"/api/v1/matches/{match.id}/teams/{team_a.id}/state/")
    assert res_a.status_code == status.HTTP_200_OK
    assert res_a.data["team"]["id"] == str(team_a.id)
    assert "unlocked_units" in res_a.data
    assert "limits" in res_a.data
    assert "valid_tower_slots" in res_a.data

    # Team A member requests Team B state -> 403 Forbidden!
    res_b = api_client.get(f"/api/v1/matches/{match.id}/teams/{team_b.id}/state/")
    assert res_b.status_code == status.HTTP_403_FORBIDDEN

    # Host requests Team B state -> 200 OK
    api_client.credentials(HTTP_X_HOST_TOKEN=host_token)
    res_host = api_client.get(f"/api/v1/matches/{match.id}/teams/{team_b.id}/state/")
    assert res_host.status_code == status.HTTP_200_OK
    assert res_host.data["team"]["id"] == str(team_b.id)
