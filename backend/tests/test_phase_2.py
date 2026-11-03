import threading
import uuid
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.economy.models import CoinTransaction, TransactionType
from apps.matches.services import MatchService, hash_token
from apps.questions.models import (
    Question,
    QuestionDifficulty,
    QuestionStatus,
    QuestionType,
    TeamQuestion,
)
from apps.questions.serializers import TeamQuestionSerializer
from apps.questions.services import QuestionService
from apps.questions.state_machine import (
    InvalidQuestionStateTransitionError,
    transition_team_question,
)
from apps.questions.validators import validate_answer
from apps.rewards.models import RewardClaim, RewardType
from apps.rewards.services import RewardService
from apps.teams.models import MemberRole, Team, TeamMember, TeamStatus
from apps.units.models import EntityCategory, TeamUnlock, UnitType


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def sample_match():
    """Create an active match with 4 teams and starter units unlocked."""
    match, host_token = MatchService.create_match(name="Test Arena")
    teams = []
    for i in range(4):
        team = Team.objects.create(match=match, name=f"Team {chr(65 + i)}")
        TeamMember.objects.create(
            match=match,
            team=team,
            display_name=f"Player {i}-1",
            role=MemberRole.MENTOR,
            token_hash="dummy_hash_1",
        )
        TeamMember.objects.create(
            match=match,
            team=team,
            display_name=f"Player {i}-2",
            role=MemberRole.MENTEE,
            token_hash="dummy_hash_2",
        )
        teams.append(team)

    # Mark teams ready
    for t in teams:
        t.is_ready = True
        t.save()

    # Ensure starter units exist
    UnitType.objects.get_or_create(
        code="infantry",
        defaults={
            "name": "Infantry",
            "category": EntityCategory.UNIT,
            "cost": 15,
            "is_starter": True,
            "is_unlockable": False,
        },
    )
    UnitType.objects.get_or_create(
        code="mg_tower",
        defaults={
            "name": "MG Tower",
            "category": EntityCategory.TOWER,
            "cost": 25,
            "is_starter": True,
            "is_unlockable": False,
        },
    )

    started_match = MatchService.start_match(match)
    return started_match, host_token, teams


@pytest.fixture
def unlockable_units():
    tank, _ = UnitType.objects.get_or_create(
        code="tank",
        defaults={
            "name": "Tank",
            "category": EntityCategory.UNIT,
            "cost": 35,
            "is_starter": False,
            "is_unlockable": True,
            "base_stats": {"hp": 120, "damage": 25, "range": 1},
        },
    )
    artillery, _ = UnitType.objects.get_or_create(
        code="artillery",
        defaults={
            "name": "Artillery",
            "category": EntityCategory.UNIT,
            "cost": 45,
            "is_starter": False,
            "is_unlockable": True,
            "base_stats": {"hp": 45, "damage": 40, "range": 3},
        },
    )
    return tank, artillery


@pytest.fixture
def sample_question():
    return Question.objects.create(
        type=QuestionType.MULTIPLE_CHOICE,
        category="Architecture",
        difficulty=QuestionDifficulty.EASY,
        content="What is the port for HTTPS?",
        options=[
            {"key": "A", "text": "80"},
            {"key": "B", "text": "443"},
            {"key": "C", "text": "8080"},
            {"key": "D", "text": "22"},
        ],
        answer_key="B",
        answer_validator_type="MULTIPLE_CHOICE",
        time_limit_seconds=60,
        explanation="HTTPS uses port 443 by default.",
    )


# -----------------------------------------------------------------------------
# 1. Answer Validators & State Machine Tests
# -----------------------------------------------------------------------------

@pytest.mark.django_db
def test_validators():
    # Multiple choice by key or text
    options = [{"key": "A", "text": "Alpha"}, {"key": "B", "text": "Beta"}]
    assert validate_answer("A", "A", "MULTIPLE_CHOICE", options)
    assert validate_answer("a", "A", "MULTIPLE_CHOICE", options)
    assert validate_answer("Beta", "B", "MULTIPLE_CHOICE", options)
    assert not validate_answer("C", "B", "MULTIPLE_CHOICE", options)

    # Exact match
    assert validate_answer("ExactText", "ExactText", "EXACT_MATCH")
    assert not validate_answer("exacttext", "ExactText", "EXACT_MATCH")

    # Case insensitive
    assert validate_answer("HelloWorld", "helloworld", "CASE_INSENSITIVE")
    assert validate_answer("  hello  ", "hello", "CASE_INSENSITIVE")

    # Numeric
    assert validate_answer("42", "42", "NUMERIC")
    assert validate_answer("42.0000", "42", "NUMERIC")
    assert not validate_answer("43", "42", "NUMERIC")

    # Normalized text
    assert validate_answer("Hà Nội!", "ha noi", "NORMALIZED_TEXT")


@pytest.mark.django_db
def test_state_machine_strict_transitions(sample_match, sample_question):
    match, _, teams = sample_match
    team = teams[0]
    tq = TeamQuestion.objects.create(
        match=match,
        team=team,
        question=sample_question,
        sequence_number=1,
        status=QuestionStatus.PENDING_QUESTION,
        expires_at=timezone.now() + timedelta(seconds=60),
    )

    # Valid: PENDING_QUESTION -> ANSWER_SUBMITTED
    transition_team_question(tq, QuestionStatus.ANSWER_SUBMITTED)
    assert tq.status == QuestionStatus.ANSWER_SUBMITTED

    # Valid: ANSWER_SUBMITTED -> ANSWER_CORRECT
    transition_team_question(tq, QuestionStatus.ANSWER_CORRECT)
    assert tq.status == QuestionStatus.ANSWER_CORRECT

    # Valid: ANSWER_CORRECT -> PENDING_REWARD
    transition_team_question(tq, QuestionStatus.PENDING_REWARD)
    assert tq.status == QuestionStatus.PENDING_REWARD

    # Invalid: PENDING_REWARD -> ANSWER_CORRECT (not allowed)
    with pytest.raises(InvalidQuestionStateTransitionError):
        transition_team_question(tq, QuestionStatus.ANSWER_CORRECT)

    # Valid: PENDING_REWARD -> REWARD_CLAIMED
    transition_team_question(tq, QuestionStatus.REWARD_CLAIMED)
    assert tq.status == QuestionStatus.REWARD_CLAIMED

    # Terminal state: REWARD_CLAIMED cannot transition to anything
    with pytest.raises(InvalidQuestionStateTransitionError):
        transition_team_question(tq, QuestionStatus.PENDING_QUESTION)


# -----------------------------------------------------------------------------
# 2. Payload Security (§5.1, §19.4)
# -----------------------------------------------------------------------------

@pytest.mark.django_db
def test_payload_security_no_sensitive_leak(sample_match, sample_question):
    match, _, teams = sample_match
    team = teams[0]
    tq = TeamQuestion.objects.create(
        match=match,
        team=team,
        question=sample_question,
        sequence_number=1,
        status=QuestionStatus.PENDING_QUESTION,
        expires_at=timezone.now() + timedelta(seconds=60),
    )

    # Unsubmitted question serialization
    serialized = TeamQuestionSerializer(tq).data
    q_data = serialized["question"]

    assert "answer_key" not in q_data
    assert "answer_validator_type" not in q_data
    assert "explanation" not in q_data
    assert "content" in q_data
    assert "options" in q_data

    # Once resolved, explanation can be shown
    tq.status = QuestionStatus.ANSWER_CORRECT
    tq.save()
    serialized_resolved = TeamQuestionSerializer(tq).data
    assert "explanation" in serialized_resolved["question"]
    assert "answer_key" not in serialized_resolved["question"]


# -----------------------------------------------------------------------------
# 3. Question Expiration and Single Submission
# -----------------------------------------------------------------------------

@pytest.mark.django_db
def test_expired_question_cannot_be_answered(sample_match, sample_question):
    match, _, teams = sample_match
    team = teams[0]
    tq = TeamQuestion.objects.create(
        match=match,
        team=team,
        question=sample_question,
        sequence_number=1,
        status=QuestionStatus.PENDING_QUESTION,
        remaining_ms=0,
        expires_at=timezone.now() - timedelta(seconds=10),  # expired
    )

    # Submit should detect expiration and set EXPIRED status
    QuestionService.update_viewing(match, team, tq.pk, "test-viewer", "OPEN")
    res = QuestionService.submit_answer(match, team, str(tq.id), "B")
    tq.refresh_from_db()
    assert tq.status == QuestionStatus.EXPIRED
    assert tq.is_correct is False


@pytest.mark.django_db
def test_already_submitted_question_cannot_be_resubmitted(sample_match, sample_question):
    match, _, teams = sample_match
    team = teams[0]
    tq = TeamQuestion.objects.create(
        match=match,
        team=team,
        question=sample_question,
        sequence_number=1,
        status=QuestionStatus.PENDING_QUESTION,
        expires_at=timezone.now() + timedelta(seconds=60),
    )

    # First submission: correct
    QuestionService.update_viewing(match, team, tq.pk, "test-viewer", "OPEN")
    QuestionService.submit_answer(match, team, str(tq.id), "B")
    tq.refresh_from_db()
    assert tq.status == QuestionStatus.PENDING_REWARD

    # Duplicate submissions return the already committed result.
    assert QuestionService.submit_answer(match, team, str(tq.id), "B").status == QuestionStatus.PENDING_REWARD


# -----------------------------------------------------------------------------
# 4. Scenario A: Correct Answer -> Receive Coins (+20, duplicate claim protected)
# -----------------------------------------------------------------------------

@pytest.mark.django_db
def test_scenario_a_correct_answer_coins(sample_match, sample_question):
    match, _, teams = sample_match
    team = teams[0]
    initial_coins = team.coins  # 100

    tq = TeamQuestion.objects.create(
        match=match,
        team=team,
        question=sample_question,
        sequence_number=1,
        status=QuestionStatus.PENDING_QUESTION,
        expires_at=timezone.now() + timedelta(seconds=60),
    )

    # Step 1: Submit correct answer
    QuestionService.update_viewing(match, team, tq.pk, "test-viewer", "OPEN")
    QuestionService.submit_answer(match, team, str(tq.id), "B")
    tq.refresh_from_db()
    assert tq.status == QuestionStatus.PENDING_REWARD

    # Step 2: Claim Coins
    claim = RewardService.claim_reward(
        match=match,
        team=team,
        team_question_id=str(tq.id),
        reward_type=RewardType.COIN,
        idempotency_key="key-abc-1",
    )
    assert claim.reward_type == RewardType.COIN
    assert claim.coin_amount == 30
    team.refresh_from_db()
    assert team.coins == initial_coins + 30

    # Verify audit transaction
    tx = CoinTransaction.objects.filter(team=team, transaction_type=TransactionType.REWARD_COIN).first()
    assert tx is not None
    assert tx.amount == 30
    assert tx.balance_after == initial_coins + 30

    # Step 3: Claim again with same or different key -> no duplicate payout
    claim2 = RewardService.claim_reward(
        match=match,
        team=team,
        team_question_id=str(tq.id),
        reward_type=RewardType.COIN,
        idempotency_key="key-abc-1",
    )
    team.refresh_from_db()
    assert team.coins == initial_coins + 30
    assert claim2.id == claim.id


# -----------------------------------------------------------------------------
# 5. Scenario B: Correct Answer -> Unlock Unit (Tank unlocked, no coin deduction)
# -----------------------------------------------------------------------------

@pytest.mark.django_db
def test_scenario_b_correct_answer_unlock(sample_match, sample_question, unlockable_units):
    tank, _ = unlockable_units
    match, _, teams = sample_match
    team = teams[0]
    initial_coins = team.coins

    tq = TeamQuestion.objects.create(
        match=match,
        team=team,
        question=sample_question,
        sequence_number=1,
        status=QuestionStatus.PENDING_QUESTION,
        expires_at=timezone.now() + timedelta(seconds=60),
    )

    QuestionService.update_viewing(match, team, tq.pk, "test-viewer", "OPEN")
    QuestionService.submit_answer(match, team, str(tq.id), "B")
    claim = RewardService.claim_reward(
        match=match,
        team=team,
        team_question_id=str(tq.id),
        reward_type=RewardType.UNLOCK,
        unit_type_id=tank.code,
    )

    assert claim.reward_type == RewardType.UNLOCK
    assert claim.unlocked_unit_type == tank
    team.refresh_from_db()
    # Coins NOT deducted
    assert team.coins == initial_coins

    # Tank is now unlocked for team
    assert TeamUnlock.objects.filter(team=team, unit_type=tank).exists()


# -----------------------------------------------------------------------------
# 6. Scenario C: All Units Unlocked -> Unlock Disabled, Coins Available
# -----------------------------------------------------------------------------

@pytest.mark.django_db
def test_scenario_c_all_units_unlocked(sample_match, sample_question, unlockable_units):
    tank, artillery = unlockable_units
    match, _, teams = sample_match
    team = teams[0]

    # Pre-unlock all unlockable units for this team
    for u in UnitType.objects.filter(is_unlockable=True):
        TeamUnlock.objects.get_or_create(team=team, unit_type=u)

    tq = TeamQuestion.objects.create(
        match=match,
        team=team,
        question=sample_question,
        sequence_number=1,
        status=QuestionStatus.PENDING_QUESTION,
        expires_at=timezone.now() + timedelta(seconds=60),
    )

    QuestionService.update_viewing(match, team, tq.pk, "test-viewer", "OPEN")
    QuestionService.submit_answer(match, team, str(tq.id), "B")
    tq.refresh_from_db()

    # Check reward options
    options = RewardService.get_reward_options(tq)
    assert options["unlock_available"] is False
    assert "All units unlocked" in options["message"]
    assert len(options["eligible_units"]) == 0

    # Attempt to unlock should be rejected
    with pytest.raises(ValidationError):
        RewardService.claim_reward(
            match=match,
            team=team,
            team_question_id=str(tq.id),
            reward_type=RewardType.UNLOCK,
            unit_type_id=tank.code,
        )

    # But coin claim still works!
    claim = RewardService.claim_reward(
        match=match,
        team=team,
        team_question_id=str(tq.id),
        reward_type=RewardType.COIN,
    )
    assert claim.reward_type == RewardType.COIN


# -----------------------------------------------------------------------------
# 7. Scenario E: Simultaneous Claim Requests (At Most One Reward)
# -----------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_scenario_e_simultaneous_claim_requests(sample_match, sample_question):
    match, _, teams = sample_match
    team = teams[0]
    initial_coins = team.coins

    tq = TeamQuestion.objects.create(
        match=match,
        team=team,
        question=sample_question,
        sequence_number=1,
        status=QuestionStatus.PENDING_REWARD,
        expires_at=timezone.now() + timedelta(seconds=60),
    )

    results = []
    errors = []

    def make_claim():
        try:
            # Need a new connection for thread in TransactionTestCase
            connection.close()
            claim = RewardService.claim_reward(
                match=match,
                team=team,
                team_question_id=str(tq.id),
                reward_type=RewardType.COIN,
                idempotency_key=str(uuid.uuid4()),
            )
            results.append(claim)
        except Exception as e:
            errors.append(e)
        finally:
            connection.close()

    t1 = threading.Thread(target=make_claim)
    t2 = threading.Thread(target=make_claim)

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # At most one claim created in DB
    assert RewardClaim.objects.filter(team_question=tq).count() == 1
    team.refresh_from_db()
    # Team received exactly 20 coins once
    assert team.coins == initial_coins + 30


# -----------------------------------------------------------------------------
# 8. Team Protection & Limits
# -----------------------------------------------------------------------------

@pytest.mark.django_db
def test_cannot_claim_other_teams_question(sample_match, sample_question):
    match, _, teams = sample_match
    team_a = teams[0]
    team_b = teams[1]

    tq_a = TeamQuestion.objects.create(
        match=match,
        team=team_a,
        question=sample_question,
        sequence_number=1,
        status=QuestionStatus.PENDING_REWARD,
        expires_at=timezone.now() + timedelta(seconds=60),
    )

    # Team B tries to claim Team A's reward
    with pytest.raises(ValidationError):
        RewardService.claim_reward(
            match=match,
            team=team_b,
            team_question_id=str(tq_a.id),
            reward_type=RewardType.COIN,
        )


@pytest.mark.django_db
def test_max_questions_limit_enforced(sample_match, sample_question):
    match, _, teams = sample_match
    team = teams[0]
    match.configuration["max_questions_per_team"] = 2
    match.save()

    # Create 2 questions already completed
    q2 = Question.objects.create(
        type=QuestionType.SHORT_TEXT,
        content="Q2",
        answer_key="ans2",
        time_limit_seconds=60,
    )
    TeamQuestion.objects.create(
        match=match,
        team=team,
        question=sample_question,
        sequence_number=1,
        status=QuestionStatus.REWARD_CLAIMED,
        expires_at=timezone.now(),
    )
    TeamQuestion.objects.create(
        match=match,
        team=team,
        question=q2,
        sequence_number=2,
        status=QuestionStatus.REWARD_CLAIMED,
        expires_at=timezone.now(),
    )

    # Attempt to assign 3rd question -> should return None (limit reached)
    latest = TeamQuestion.objects.filter(match=match, team=team).order_by("-sequence_number").first()
    next_q = QuestionService.get_or_assign_current_question(match, team, advance_from=latest.pk)
    assert next_q is None


@pytest.mark.django_db
@pytest.mark.parametrize("eliminate_before_assignment", [True, False])
def test_eliminated_team_can_answer_claim_and_continue(sample_match, sample_question, eliminate_before_assignment):
    from apps.matches.action_policy import ActionPolicy

    match, _, teams = sample_match
    team = teams[0]
    if not eliminate_before_assignment:
        tq = QuestionService.get_or_assign_current_question(match, team)
        QuestionService.update_viewing(match, team, tq.pk, "test-viewer", "OPEN")
    team.status = TeamStatus.ELIMINATED
    team.base_hp = 0
    team.save()
    if eliminate_before_assignment:
        tq = QuestionService.get_or_assign_current_question(match, team)
        QuestionService.update_viewing(match, team, tq.pk, "test-viewer", "OPEN")

    answered = QuestionService.submit_answer(match, team, str(tq.id), "B")
    assert answered.is_correct
    coins_before = team.coins
    claim = RewardService.claim_reward(match, team, str(tq.id), RewardType.COIN)
    team.refresh_from_db()
    assert team.coins == coins_before + claim.coin_amount
    assert QuestionService.progress(match, team)["correct"] == 1
    assert team.status == TeamStatus.ELIMINATED and team.base_hp == 0
    for action in ["DEPLOY_UNIT", "BUILD_TOWER", "RETARGET", "REPAIR_BASE", "UPGRADE_TEAM_TYPE"]:
        assert ActionPolicy.context(match, team, action).reason_code == "TEAM_ELIMINATED"

    Question.objects.create(content="Next question", answer_key="yes")
    next_question, _ = QuestionService.open_session(match, team, tq.pk, "test-viewer")
    assert next_question.sequence_number == 2
    assert next_question.timer_status == "RUNNING"

    # Quiz access still respects spectator permissions and the match lifecycle.
    member = team.members.first()
    member.role = MemberRole.SPECTATOR
    assert not ActionPolicy.context(match, team, "ANSWER_QUESTION", member).allowed
    for status in ["PAUSED", "FINISHED"]:
        match.status = status
        match.save(update_fields=["status"])
        with pytest.raises(ValidationError):
            QuestionService.submit_answer(match, team, next_question.pk, "yes")


# -----------------------------------------------------------------------------
# 9. Database Unique Constraints
# -----------------------------------------------------------------------------

@pytest.mark.django_db
def test_database_unique_constraints(sample_match, sample_question, unlockable_units):
    tank, _ = unlockable_units
    match, _, teams = sample_match
    team = teams[0]

    # Constraint 1: (match, team, sequence_number)
    TeamQuestion.objects.create(
        match=match,
        team=team,
        question=sample_question,
        sequence_number=1,
        expires_at=timezone.now() + timedelta(seconds=60),
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            TeamQuestion.objects.create(
                match=match,
                team=team,
                question=Question.objects.create(content="Q_dup_seq", answer_key="a"),
                sequence_number=1,  # Duplicate sequence
                expires_at=timezone.now() + timedelta(seconds=60),
            )

    # Constraint 2: (match, team, question)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            TeamQuestion.objects.create(
                match=match,
                team=team,
                question=sample_question,  # Duplicate question
                sequence_number=2,
                expires_at=timezone.now() + timedelta(seconds=60),
            )

    # Constraint 3: (team, unit_type) on TeamUnlock
    TeamUnlock.objects.create(team=team, unit_type=tank)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            TeamUnlock.objects.create(team=team, unit_type=tank)


# -----------------------------------------------------------------------------
# 10. HTTP REST API Tests
# -----------------------------------------------------------------------------

@pytest.mark.django_db
def test_question_and_reward_api_flow(api_client, sample_match, sample_question, unlockable_units):
    tank, _ = unlockable_units
    match, _, teams = sample_match
    team = teams[0]
    member = team.members.first()
    plain_token = "pt_gamer_12345"
    member.token_hash = hash_token(plain_token)
    member.save()

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {plain_token}")

    # 1. GET Current Question
    res = api_client.get(f"/api/v1/matches/{match.id}/questions/current/")
    assert res.status_code == status.HTTP_200_OK
    assert "question" in res.data
    q_data = res.data["question"]
    assert "answer_key" not in q_data  # No answer leak!
    tq_id = res.data["id"]

    # 2. POST Answer Question
    import uuid
    opened = api_client.post(f"/api/v1/matches/{match.id}/questions/current/", {
        "action": "OPEN", "question_id": str(tq_id), "viewer_id": str(uuid.uuid4()),
    }, format="json")
    assert opened.status_code == 200
    ans_res = api_client.post(
        f"/api/v1/matches/{match.id}/questions/{tq_id}/answer/",
        {"answer": sample_question.answer_key},
        format="json",
    )
    assert ans_res.status_code == status.HTTP_200_OK
    assert ans_res.data["is_correct"] is True
    assert ans_res.data["status"] == QuestionStatus.PENDING_REWARD
    assert ans_res.data["reward_options"] is not None

    # 3. POST Claim Reward (Coins)
    claim_res = api_client.post(
        f"/api/v1/matches/{match.id}/rewards/claim/",
        {
            "team_question_id": tq_id,
            "reward_type": "COIN",
            "idempotency_key": str(uuid.uuid4()),
        },
        format="json",
    )
    assert claim_res.status_code == status.HTTP_200_OK
    assert claim_res.data["reward_type"] == "COIN"
    sealed = TeamQuestion.objects.get(pk=tq_id)
    assert claim_res.data["coin_amount"] == sealed.reward_coin_amount
    assert claim_res.data["team_coins"] == 100 + sealed.reward_coin_amount

    # 4. GET Question History
    hist_res = api_client.get(f"/api/v1/matches/{match.id}/questions/history/")
    assert hist_res.status_code == status.HTTP_200_OK
    assert len(hist_res.data) == 1
    assert hist_res.data[0]["status"] == QuestionStatus.REWARD_CLAIMED
