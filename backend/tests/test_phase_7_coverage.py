import pytest
from rest_framework.test import APIRequestFactory

from apps.combat.engine import CombatEngine
from apps.combat.scoring import ScoringService
from apps.combat.views import MatchCombatResolveView, MatchResultsView
from apps.economy.models import TransactionType
from apps.economy.services import EconomyService
from apps.matches.services import MatchService
from apps.questions.models import (
    Question,
    QuestionDifficulty,
    QuestionStatus,
    QuestionType,
    TeamQuestion,
)
from apps.rewards.views import MatchRewardClaimView, MatchRewardOptionsView
from apps.teams.models import MemberRole
from apps.units.models import (
    UnitType,
)
from apps.units.seeds import ensure_standard_units
from apps.units.services import ConstructionService, UnitService
from apps.units.views import (
    MatchBuildTowerActionView,
    MatchDeployUnitActionView,
    MatchEmpActionView,
    MatchRepairBaseActionView,
    MatchScoutActionView,
    MatchTeamStateView,
    MatchUnitListView,
    MatchUpgradeTowerActionView,
    UnitTypeDetailView,
    UnitTypeListCreateView,
)


@pytest.fixture
def coverage_match_fixture(db):
    """Sets up an active 4-team match with members, tokens, and standard units."""
    ensure_standard_units()

    match, host_token = MatchService.create_match(
        name="Coverage Match",
        configuration={"gameplay_mode": "LEGACY", "tower_placement_version":0, "arena_layout_version":5,
            "initial_base_hp": 500,
            "initial_coins": 100,
            "match_duration_minutes": 30,
            "max_questions_per_team": 8,
            "correct_answer_coins": 20,
            "base_income_coins": 10,
            "max_towers_per_team": 3,
            "max_units_per_team": 5,
        },
    )
    teams = []
    from apps.teams.models import Team, TeamStatus
    for i in range(1, 5):
        t = Team.objects.create(
            match=match,
            name=f"Team {i}",
            base_hp=500,
            initial_base_hp=500,
            coins=100,
            status=TeamStatus.ACTIVE,
            is_ready=True,
        )
        teams.append(t)

    t1, t2 = teams[0], teams[1]

    # Add 1 mentor and 1 mentee to each team
    m1_lead, t1_lead_token = MatchService.join_match(match, "Lead 1", t1.id, MemberRole.MENTOR)
    m1_user, t1_user_token = MatchService.join_match(match, "Member 1", t1.id, MemberRole.MENTEE)
    m1_spec, t1_spec_token = MatchService.join_match(match, "Spectator 1", t1.id, MemberRole.SPECTATOR)

    m2_lead, t2_lead_token = MatchService.join_match(match, "Lead 2", teams[1].id, MemberRole.MENTOR)
    MatchService.join_match(match, "Member 2", teams[1].id, MemberRole.MENTEE)
    for i in range(2, 4):
        MatchService.join_match(match, f"Lead {i+1}", teams[i].id, MemberRole.MENTOR)
        MatchService.join_match(match, f"Member {i+1}", teams[i].id, MemberRole.MENTEE)

    MatchService.start_match(match)
    return {
        "match": match,
        "host_token": host_token,
        "teams": teams,
        "members": {
            "t1_lead": (m1_lead, t1_lead_token),
            "t1_user": (m1_user, t1_user_token),
            "t1_spec": (m1_spec, t1_spec_token),
            "t2_lead": (m2_lead, t2_lead_token),
        },
    }


def test_rewards_views_and_options(coverage_match_fixture):
    """Test MatchRewardClaimView and MatchRewardOptionsView edge cases."""
    data = coverage_match_fixture
    match = data["match"]
    t1, t2 = data["teams"][:2]
    m1_spec, spec_token = data["members"]["t1_spec"]
    m1_lead, lead_token = data["members"]["t1_lead"]
    m2_lead, t2_lead_token = data["members"]["t2_lead"]

    q = Question.objects.create(
        content="Coverage Q?",
        type=QuestionType.MULTIPLE_CHOICE,
        options=[{"text": "A", "is_correct": True}],
        difficulty=QuestionDifficulty.EASY,
    )
    from datetime import timedelta

    from django.utils import timezone
    tq1 = TeamQuestion.objects.create(
        match=match,
        team=t1,
        question=q,
        sequence_number=1,
        status=QuestionStatus.PENDING_REWARD,
        expires_at=timezone.now() + timedelta(minutes=5),
    )
    tq2 = TeamQuestion.objects.create(
        match=match,
        team=t2,
        question=q,
        sequence_number=1,
        status=QuestionStatus.PENDING_REWARD,
        expires_at=timezone.now() + timedelta(minutes=5),
    )

    factory = APIRequestFactory()

    # 1. Spectator attempts to claim reward -> 403
    request = factory.post(
        f"/api/v1/matches/{match.id}/rewards/claim/",
        {"team_question_id": str(tq1.id), "reward_type": "COINS"},
        HTTP_AUTHORIZATION=f"Bearer {spec_token}",
    )
    response = MatchRewardClaimView.as_view()(request, match_id=str(match.id))
    assert response.status_code == 403

    # 2. Query reward options for own team -> 200
    request = factory.get(
        f"/api/v1/matches/{match.id}/rewards/options/{tq1.id}/",
        HTTP_AUTHORIZATION=f"Bearer {lead_token}",
    )
    response = MatchRewardOptionsView.as_view()(request, match_id=str(match.id), team_question_id=str(tq1.id))
    assert response.status_code == 200
    assert "coin_amount" in response.data

    # 3. Query reward options for other team's question -> 403
    request = factory.get(
        f"/api/v1/matches/{match.id}/rewards/options/{tq2.id}/",
        HTTP_AUTHORIZATION=f"Bearer {lead_token}",
    )
    response = MatchRewardOptionsView.as_view()(request, match_id=str(match.id), team_question_id=str(tq2.id))
    assert response.status_code == 403

    # 4. Valid claim coins -> 200
    request = factory.post(
        f"/api/v1/matches/{match.id}/rewards/claim/",
        {"team_question_id": str(tq1.id), "reward_type": "COIN", "idempotency_key": "cov_claim_1"},
        HTTP_AUTHORIZATION=f"Bearer {lead_token}",
    )
    response = MatchRewardClaimView.as_view()(request, match_id=str(match.id))
    assert response.status_code == 200
    assert response.data["coin_amount"] > 0


def test_units_views_and_actions(coverage_match_fixture):
    """Test unit view endpoints: list, deploy, build, upgrade, repair, scout, emp, team_state."""
    data = coverage_match_fixture
    match = data["match"]
    t1, t2 = data["teams"][:2]
    m1_spec, spec_token = data["members"]["t1_spec"]
    m1_lead, lead_token = data["members"]["t1_lead"]
    factory = APIRequestFactory()

    # Give team 1 sufficient coins
    EconomyService.credit(team=t1, amount=500, transaction_type=TransactionType.REWARD_COIN, reference_type="TEST", reference_id="cov1")

    # 1. MatchUnitListView
    req = factory.get(f"/api/v1/matches/{match.id}/units/", HTTP_AUTHORIZATION=f"Bearer {lead_token}")
    res = MatchUnitListView.as_view()(req, match_id=str(match.id))
    assert res.status_code == 200
    assert len(res.data) >= 3

    # 2. MatchDeployUnitActionView - Spectator forbidden
    req = factory.post(
        f"/api/v1/matches/{match.id}/actions/deploy/",
        {"unit_type_code_or_id": "infantry", "target_team_id": str(t2.id)},
        HTTP_AUTHORIZATION=f"Bearer {spec_token}",
    )
    res = MatchDeployUnitActionView.as_view()(req, match_id=str(match.id))
    assert res.status_code == 403

    # 3. MatchDeployUnitActionView - Success
    req = factory.post(
        f"/api/v1/matches/{match.id}/actions/deploy/",
        {"unit_type_code_or_id": "infantry", "target_team_id": str(t2.id), "idempotency_key": "cov_deploy_1"},
        HTTP_AUTHORIZATION=f"Bearer {lead_token}",
    )
    res = MatchDeployUnitActionView.as_view()(req, match_id=str(match.id))
    assert res.status_code == 200
    assert res.data["action"]["action_type"] == "DEPLOY_UNIT"

    # 4. MatchBuildTowerActionView - Spectator forbidden
    req = factory.post(
        f"/api/v1/matches/{match.id}/actions/build/",
        {"unit_type_code_or_id": "mg_tower", "node_id": "node_tower_t1_slot1"},
        HTTP_AUTHORIZATION=f"Bearer {spec_token}",
    )
    res = MatchBuildTowerActionView.as_view()(req, match_id=str(match.id))
    assert res.status_code == 403

    # 5. MatchBuildTowerActionView - Success
    req = factory.post(
        f"/api/v1/matches/{match.id}/actions/build/",
        {"unit_type_code_or_id": "mg_tower", "node_id": "node_tower_t1_slot1", "idempotency_key": "cov_build_1"},
        HTTP_AUTHORIZATION=f"Bearer {lead_token}",
    )
    res = MatchBuildTowerActionView.as_view()(req, match_id=str(match.id))
    assert res.status_code == 200
    tower_entity_id = res.data["entity"]["id"]

    # 6. MatchUpgradeTowerActionView - Success
    req = factory.post(
        f"/api/v1/matches/{match.id}/actions/upgrade/",
        {"entity_id": tower_entity_id, "idempotency_key": "cov_upg_1"},
        HTTP_AUTHORIZATION=f"Bearer {lead_token}",
    )
    res = MatchUpgradeTowerActionView.as_view()(req, match_id=str(match.id))
    assert res.status_code == 200

    # 7. MatchRepairBaseActionView - Damaged base
    t1.base_hp = 300
    t1.save(update_fields=["base_hp"])
    req = factory.post(
        f"/api/v1/matches/{match.id}/actions/repair/",
        {"idempotency_key": "cov_rep_1"},
        HTTP_AUTHORIZATION=f"Bearer {lead_token}",
    )
    res = MatchRepairBaseActionView.as_view()(req, match_id=str(match.id))
    assert res.status_code == 200

    # 8. MatchScoutActionView - Success
    req = factory.post(
        f"/api/v1/matches/{match.id}/actions/scout/",
        {"target_team_id": str(t2.id), "idempotency_key": "cov_scout_1"},
        HTTP_AUTHORIZATION=f"Bearer {lead_token}",
    )
    res = MatchScoutActionView.as_view()(req, match_id=str(match.id))
    assert res.status_code == 200

    # 9. MatchEmpActionView - Success
    # Build a tower for team 2 first so it can be targeted by EMP
    _, t2_tower = ConstructionService.build_tower(match, t2, "mg_tower", "node_tower_t2_slot1")
    req = factory.post(
        f"/api/v1/matches/{match.id}/actions/emp/",
        {"target_entity_id": str(t2_tower.id), "idempotency_key": "cov_emp_1"},
        HTTP_AUTHORIZATION=f"Bearer {lead_token}",
    )
    res = MatchEmpActionView.as_view()(req, match_id=str(match.id))
    assert res.status_code == 200

    # 10. MatchTeamStateView
    req = factory.get(f"/api/v1/matches/{match.id}/teams/{t1.id}/state/", HTTP_AUTHORIZATION=f"Bearer {lead_token}")
    res = MatchTeamStateView.as_view()(req, match_id=str(match.id), team_id=str(t1.id))
    assert res.status_code == 200
    assert "team" in res.data
    assert "entities" in res.data


def test_combat_views_and_engine_branches(coverage_match_fixture):
    """Test combat views (resolve, results) and engine edge branches."""
    data = coverage_match_fixture
    match = data["match"]
    t1, t2 = data["teams"][:2]
    m1_lead, lead_token = data["members"]["t1_lead"]
    factory = APIRequestFactory()

    # 1. MatchCombatResolveView - non-host forbidden (403)
    req = factory.post(f"/api/v1/matches/{match.id}/combat/resolve/", HTTP_AUTHORIZATION=f"Bearer {lead_token}")
    res = MatchCombatResolveView.as_view()(req, match_id=str(match.id))
    assert res.status_code == 403

    # 2. MatchCombatResolveView - Host authorized
    req = factory.post(
        f"/api/v1/matches/{match.id}/combat/resolve/",
        HTTP_AUTHORIZATION=f"Bearer {data['host_token']}",
    )
    res = MatchCombatResolveView.as_view()(req, match_id=str(match.id))
    assert res.status_code == 200
    assert "round_number" in res.data

    # 3. MatchResultsView - match in progress preview
    req = factory.get(f"/api/v1/matches/{match.id}/results/")
    res = MatchResultsView.as_view()(req, match_id=str(match.id))
    assert res.status_code == 200
    assert res.data["match_id"] == str(match.id)

    # 4. Finalize match and check MatchResultsView with awards
    ScoringService.finalize_match(match)
    req = factory.get(f"/api/v1/matches/{match.id}/results/")
    res = MatchResultsView.as_view()(req, match_id=str(match.id))
    assert res.status_code == 200
    assert len(res.data["results"]) == 4
    assert "awards" in res.data


def test_construction_and_unit_service_validations(coverage_match_fixture):
    """Test validation errors in ConstructionService and UnitService."""
    from django.core.exceptions import ValidationError

    data = coverage_match_fixture
    match = data["match"]
    t1, t2 = data["teams"][:2]

    # 1. Invalid unit code
    with pytest.raises(ValidationError):
        ConstructionService.build_tower(match, t1, "non_existent_unit", "node_lane_t1_1")

    # 2. Building combat unit as tower
    with pytest.raises(ValidationError):
        ConstructionService.build_tower(match, t1, "infantry", "node_lane_t1_1")

    # 3. Build with insufficient coins
    t1.coins = 5
    t1.save(update_fields=["coins"])
    with pytest.raises(ValidationError):
        ConstructionService.build_tower(match, t1, "mg_tower", "node_lane_t1_1")

    # 4. Deploy with insufficient coins
    with pytest.raises(ValidationError):
        UnitService.deploy_unit(match, t1, "infantry", str(t2.id))

    # 5. Deploy targeting non-existent team
    t1.coins = 100
    t1.save(update_fields=["coins"])
    with pytest.raises(ValidationError):
        import uuid
        UnitService.deploy_unit(match, t1, "infantry", str(uuid.uuid4()))

    # 6. Deploy targeting self
    with pytest.raises(ValidationError):
        UnitService.deploy_unit(match, t1, "infantry", str(t1.id))

    # 7. Upgrade tower validations
    t1.coins = 500
    t1.save(update_fields=["coins"])
    _, tower_e = ConstructionService.build_tower(match, t1, "mg_tower", "node_tower_t1_slot2")
    # Upgrade once -> OK
    ConstructionService.upgrade_tower(match, t1, tower_e.id)
    ConstructionService.upgrade_tower(match, t1, tower_e.id)
    # Level 3 is now the maximum.
    with pytest.raises(ValidationError):
        ConstructionService.upgrade_tower(match, t1, tower_e.id)
    # Upgrade non-existent tower -> ValidationError
    with pytest.raises(ValidationError):
        import uuid
        ConstructionService.upgrade_tower(match, t1, uuid.uuid4())

    # 8. Repair base validations
    # Base already at max hp -> ValidationError
    t1.base_hp = 500
    t1.initial_base_hp = 500
    t1.save(update_fields=["base_hp", "initial_base_hp"])
    with pytest.raises(ValidationError):
        ConstructionService.repair_base(match, t1)
    # Repair with insufficient coins
    t1.base_hp = 300
    t1.coins = 5
    t1.save(update_fields=["base_hp", "coins"])
    with pytest.raises(ValidationError):
        ConstructionService.repair_base(match, t1)

    # 9. Scout validations
    t1.coins = 500
    t1.save(update_fields=["coins"])
    # Scout self -> ValidationError
    with pytest.raises(ValidationError):
        ConstructionService.scout(match, t1, str(t1.id))
    # Scout insufficient coins
    t1.coins = 2
    t1.save(update_fields=["coins"])
    with pytest.raises(ValidationError):
        ConstructionService.scout(match, t1, str(t2.id))

    # 10. EMP validations
    t1.coins = 500
    t1.save(update_fields=["coins"])
    # EMP own tower -> ValidationError
    with pytest.raises(ValidationError):
        ConstructionService.emp(match, t1, str(tower_e.id))
    # EMP non-existent tower -> ValidationError
    with pytest.raises(ValidationError):
        import uuid
        ConstructionService.emp(match, t1, str(uuid.uuid4()))
    # EMP insufficient coins
    t1.coins = 5
    t1.save(update_fields=["coins"])
    with pytest.raises(ValidationError):
        ConstructionService.emp(match, t1, str(tower_e.id))


def test_simulate_match_management_command():
    """Test headless match simulation command (§2.7, FR-07)."""
    from django.core.management import call_command
    call_command("simulate_match", teams=4, seed=42, rounds=5, quiet=True)


def test_unit_type_admin_views(db):
    """Test UnitTypeListCreateView and UnitTypeDetailView (GET, POST, PATCH, DELETE)."""
    factory = APIRequestFactory()

    # 1. List unit types
    req = factory.get("/api/v1/unit-types/?category=UNIT")
    res = UnitTypeListCreateView.as_view()(req)
    assert res.status_code == 200

    # 2. Create unit type
    new_unit_data = {
        "code": "drone_cov",
        "name": "Drone Coverage",
        "category": "UNIT",
        "cost": 30,
        "is_starter": False,
        "is_unlockable": True,
        "is_active": True,
        "base_stats": {
            "hp": 50,
            "damage": 20,
            "range": 1,
            "movement": 2,
            "strategic_role": "Fast flanker",
        },
    }
    req = factory.post("/api/v1/unit-types/", new_unit_data, format="json")
    res = UnitTypeListCreateView.as_view()(req)
    assert res.status_code == 201
    created_id = res.data["id"]

    # 3. Retrieve unit type
    req = factory.get(f"/api/v1/unit-types/{created_id}/")
    res = UnitTypeDetailView.as_view()(req, unit_type_id=created_id)
    assert res.status_code == 200
    assert res.data["code"] == "drone_cov"

    # 4. Patch unit type
    req = factory.patch(f"/api/v1/unit-types/{created_id}/", {"cost": 35}, format="json")
    res = UnitTypeDetailView.as_view()(req, unit_type_id=created_id)
    assert res.status_code == 200
    assert res.data["cost"] == 35

    # 5. Delete unit type
    req = factory.delete(f"/api/v1/unit-types/{created_id}/")
    res = UnitTypeDetailView.as_view()(req, unit_type_id=created_id)
    assert res.status_code == 200
    assert not UnitType.objects.filter(pk=created_id).exists()


def test_combat_engine_shield_generator_and_base_elimination():
    """Test CombatEngine processing shield_generator and base elimination events."""
    from apps.combat.engine import CombatState
    state = CombatState(
        round_number=1,
        is_paused=False,
        teams={
            "t1": {"name": "Team 1", "team_index": 1, "base_hp": 500, "status": "ACTIVE", "base_node": "node_base_t1", "base_shield": 0, "shield_remaining_rounds": 0},
            "t2": {"name": "Team 2", "team_index": 2, "base_hp": 10, "status": "ACTIVE", "base_node": "node_base_t2", "base_shield": 0, "shield_remaining_rounds": 0},
        },
        entities=[
            {
                "id": "shield_tow_1",
                "team_id": "t1",
                "entity_kind": "TOWER",
                "unit_type_code": "shield_generator",
                "current_node_id": "node_tower_t1_slot1",
                "current_hp": 100,
                "status": "ACTIVE",
                "cooldown_remaining": 0,
            },
            {
                "id": "u_finisher",
                "team_id": "t1",
                "entity_kind": "UNIT",
                "unit_type_code": "infantry",
                "target_team_id": "t2",
                "current_node_id": "node_lane_t2_1",
                "current_hp": 50,
                "damage": 50,
                "status": "ACTIVE",
                "range": 1,
            },
        ],
        actions=[],
        configuration={"base_income_per_round": 10},
        combat_stats={"t1": {"bases_destroyed": 0, "base_damage_dealt": 0}, "t2": {"bases_destroyed": 0, "base_damage_dealt": 0}},
    )
    res = CombatEngine.resolve_round(state)
    assert res.new_state.teams["t1"]["base_shield"] == 40
    assert "t2" in res.eliminated_team_ids


def test_units_views_validation_error_responses(coverage_match_fixture):
    """Test 400 Bad Request responses in action views on validation failures."""
    import uuid
    data = coverage_match_fixture
    match = data["match"]
    t1, t2 = data["teams"][:2]
    m1_lead, lead_token = data["members"]["t1_lead"]
    factory = APIRequestFactory()

    # 1. Deploy invalid unit -> 400
    req = factory.post(
        f"/api/v1/matches/{match.id}/actions/deploy/",
        {"unit_type_code_or_id": "invalid_unit_xyz", "target_team_id": str(t2.id)},
        HTTP_AUTHORIZATION=f"Bearer {lead_token}",
    )
    res = MatchDeployUnitActionView.as_view()(req, match_id=str(match.id))
    assert res.status_code == 400

    # 2. Build invalid node -> 400
    req = factory.post(
        f"/api/v1/matches/{match.id}/actions/build/",
        {"unit_type_code_or_id": "mg_tower", "node_id": "invalid_slot_123"},
        HTTP_AUTHORIZATION=f"Bearer {lead_token}",
    )
    res = MatchBuildTowerActionView.as_view()(req, match_id=str(match.id))
    assert res.status_code == 400

    # 3. Upgrade invalid entity -> 400
    req = factory.post(
        f"/api/v1/matches/{match.id}/actions/upgrade/",
        {"entity_id": str(uuid.uuid4())},
        HTTP_AUTHORIZATION=f"Bearer {lead_token}",
    )
    res = MatchUpgradeTowerActionView.as_view()(req, match_id=str(match.id))
    assert res.status_code == 400

    # 4. Repair base when full hp -> 400
    t1.base_hp = 500
    t1.initial_base_hp = 500
    t1.save(update_fields=["base_hp", "initial_base_hp"])
    req = factory.post(
        f"/api/v1/matches/{match.id}/actions/repair/",
        {},
        HTTP_AUTHORIZATION=f"Bearer {lead_token}",
    )
    res = MatchRepairBaseActionView.as_view()(req, match_id=str(match.id))
    assert res.status_code == 400

    # 5. Scout self -> 400
    req = factory.post(
        f"/api/v1/matches/{match.id}/actions/scout/",
        {"target_team_id": str(t1.id)},
        HTTP_AUTHORIZATION=f"Bearer {lead_token}",
    )
    res = MatchScoutActionView.as_view()(req, match_id=str(match.id))
    assert res.status_code == 400

    # 6. EMP invalid entity -> 400
    req = factory.post(
        f"/api/v1/matches/{match.id}/actions/emp/",
        {"target_entity_id": str(uuid.uuid4())},
        HTTP_AUTHORIZATION=f"Bearer {lead_token}",
    )
    res = MatchEmpActionView.as_view()(req, match_id=str(match.id))
    assert res.status_code == 400
