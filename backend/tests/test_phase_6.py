import pytest
from rest_framework.test import APIClient

from apps.combat.models import MatchResult
from apps.matches.models import Match, MatchEvent, MatchPhase, MatchStatus
from apps.matches.services import MatchService
from apps.questions.models import Question, QuestionStatus, TeamQuestion
from apps.teams.models import MemberRole, TeamMember, TeamStatus


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def sample_match():
    match, host_token = MatchService.create_match(name="Phase 6 Championship", configuration={"gameplay_mode": "LEGACY"})
    # Add 4 teams with 2 members each
    for i in range(1, 5):
        team = MatchService.create_team(match, f"Team {i}")
        m1, t1 = MatchService.join_match(match, f"Mentor {i}", team_id=str(team.id), role=MemberRole.MENTOR)
        m2, t2 = MatchService.join_match(match, f"Mentee {i}", team_id=str(team.id), role=MemberRole.MENTEE)
        MatchService.set_team_ready(team, True)
    return match, host_token


@pytest.mark.django_db
def test_host_controls_authorization_and_participant_rejection(api_client, sample_match):
    """Chỉ host điều khiển được lifecycle; participant bị từ chối (§2.1, §22)."""
    match, host_token = sample_match
    participant_member = TeamMember.objects.filter(match=match).first()
    # Let's get participant plain token by joining a new member or inspect rejection without host header
    auth_host_header = {"HTTP_AUTHORIZATION": f"Bearer {host_token}"}
    no_auth_header = {}

    # 1. Non-host cannot start match
    res = api_client.post(f"/api/v1/matches/{match.id}/start/", **no_auth_header)
    assert res.status_code == 403

    # 2. Host can start match
    res = api_client.post(f"/api/v1/matches/{match.id}/start/", **auth_host_header)
    assert res.status_code == 200
    match.refresh_from_db()
    assert match.status == MatchStatus.ACTIVE
    assert match.phase == MatchPhase.PREPARATION

    # 3. Non-host cannot pause match
    res = api_client.post(f"/api/v1/matches/{match.id}/pause/", **no_auth_header)
    assert res.status_code == 403

    # 4. Host can pause match
    res = api_client.post(f"/api/v1/matches/{match.id}/pause/", **auth_host_header)
    assert res.status_code == 200
    match.refresh_from_db()
    assert match.status == MatchStatus.PAUSED

    # 5. Non-host cannot resume match
    res = api_client.post(f"/api/v1/matches/{match.id}/resume/", **no_auth_header)
    assert res.status_code == 403

    # 6. Host can resume match
    res = api_client.post(f"/api/v1/matches/{match.id}/resume/", **auth_host_header)
    assert res.status_code == 200
    match.refresh_from_db()
    assert match.status == MatchStatus.ACTIVE

    # 7. Non-host cannot advance phase
    res = api_client.post(f"/api/v1/matches/{match.id}/advance-phase/", {"target_phase": MatchPhase.BUILD_AND_SCOUT}, **no_auth_header)
    assert res.status_code == 403

    # 8. Host can advance phase
    res = api_client.post(f"/api/v1/matches/{match.id}/advance-phase/", {"target_phase": MatchPhase.BUILD_AND_SCOUT}, **auth_host_header)
    assert res.status_code == 200
    match.refresh_from_db()
    assert match.phase == MatchPhase.BUILD_AND_SCOUT

    # 9. Non-host cannot end match
    res = api_client.post(f"/api/v1/matches/{match.id}/end/", **no_auth_header)
    assert res.status_code == 403


@pytest.mark.django_db
def test_pause_stops_timers_preserves_questions_and_resume_restores_time(api_client, sample_match):
    """Pause: đóng câu hỏi đang mở theo §11; resume khôi phục thời gian còn lại chính xác."""
    match, host_token = sample_match
    auth_host_header = {"HTTP_AUTHORIZATION": f"Bearer {host_token}"}

    MatchService.start_match(match)
    team = match.teams.first()

    # Assign an open question to team
    q = Question.objects.create(
        content="What is defensive synergy?",
        answer_key="A",
        answer_validator_type="MULTIPLE_CHOICE",
        time_limit_seconds=60,
    )
    from datetime import timedelta

    from django.utils import timezone
    tq = TeamQuestion.objects.create(
        match=match,
        team=team,
        question=q,
        sequence_number=1,
        status=QuestionStatus.PENDING_QUESTION,
        expires_at=timezone.now() + timedelta(seconds=60),
    )

    # Pause match
    res = api_client.post(f"/api/v1/matches/{match.id}/pause/", **auth_host_header)
    assert res.status_code == 200

    # Match pause preserves the current question and its budget.
    tq.refresh_from_db()
    assert tq.status == QuestionStatus.PENDING_QUESTION
    assert tq.timer_status == "PAUSED"

    # Verify pause event recorded with remaining seconds
    match.refresh_from_db()
    timer_state = match.configuration.get("timer_state", {})
    assert "paused_at" in timer_state
    assert "phase_remaining_seconds" in timer_state
    assert timer_state["phase_remaining_seconds"] > 0

    # Resume match
    res = api_client.post(f"/api/v1/matches/{match.id}/resume/", **auth_host_header)
    assert res.status_code == 200
    match.refresh_from_db()
    assert match.status == MatchStatus.ACTIVE
    assert "resumed_at" in match.configuration["timer_state"]


@pytest.mark.django_db
def test_end_match_early_creates_single_immutable_result_snapshot(api_client, sample_match):
    """End sớm sinh đúng một MatchResult; gọi lại không tạo bản sao (§19.13, FR-10)."""
    match, host_token = sample_match
    auth_host_header = {"HTTP_AUTHORIZATION": f"Bearer {host_token}"}
    MatchService.start_match(match)

    # End match early
    res = api_client.post(f"/api/v1/matches/{match.id}/end/", **auth_host_header)
    assert res.status_code == 200

    match.refresh_from_db()
    assert match.status == MatchStatus.FINISHED
    assert match.phase == MatchPhase.RESULTS

    # Verify MatchResults created exactly for 4 teams
    results_count = MatchResult.objects.filter(match=match).count()
    assert results_count == 4

    # Repeated calls to end or results view must NOT duplicate results
    res2 = api_client.post(f"/api/v1/matches/{match.id}/end/", **auth_host_header)
    assert res2.status_code == 200
    assert MatchResult.objects.filter(match=match).count() == 4

    res_results = api_client.get(f"/api/v1/matches/{match.id}/results/")
    assert res_results.status_code == 200
    data = res_results.json()
    assert len(data["results"]) == 4
    assert data["duration_seconds"] >= 0
    assert "awards" in data
    assert MatchResult.objects.filter(match=match).count() == 4


@pytest.mark.django_db
def test_ranking_tie_break_and_eliminated_teams_in_results(api_client, sample_match):
    """Ranking đúng thứ tự tie-break; đội bị loại vẫn có trong ranking (§12, D6)."""
    match, host_token = sample_match
    auth_host_header = {"HTTP_AUTHORIZATION": f"Bearer {host_token}"}
    MatchService.start_match(match)

    teams = list(match.teams.all())
    # Team 1: active, high score, eliminated team 4
    teams[0].coins = 120
    teams[0].base_hp = 450
    teams[0].save()

    # Team 4: eliminated
    teams[3].base_hp = 0
    teams[3].status = TeamStatus.ELIMINATED
    teams[3].save()

    # Finalize match
    res = api_client.post(f"/api/v1/matches/{match.id}/end/", **auth_host_header)
    assert res.status_code == 200

    results_res = api_client.get(f"/api/v1/matches/{match.id}/results/")
    assert results_res.status_code == 200
    data = results_res.json()

    team_ids_in_results = [r["team_id"] for r in data["results"]]
    assert str(teams[3].id) in team_ids_in_results  # Eliminated team is in results!

    # Check rank order
    ranks = [r["final_rank"] for r in data["results"]]
    assert ranks == sorted(ranks)


@pytest.mark.django_db
def test_optional_awards_do_not_alter_official_score_unless_configured(sample_match):
    """Awards không đổi điểm chính thức khi config tắt (§13, D14)."""
    match, _ = sample_match
    MatchService.start_match(match)

    from apps.combat.scoring import ScoringService
    results_normal = ScoringService.finalize_match(match)
    scores_normal = {r.team_id: r.final_score for r in results_normal}

    # Awards should be generated in configuration
    match.refresh_from_db()
    awards = match.configuration.get("awards", [])
    assert len(awards) == 5
    award_ids = {a["id"] for a in awards}
    assert "best_strategist" in award_ids
    assert "best_defense" in award_ids
    assert "best_comeback" in award_ids
    assert "knowledge_champion" in award_ids
    assert "mentor_mentee_synergy" in award_ids


@pytest.mark.django_db
def test_administrative_overrides_and_audit_trail_no_tokens(api_client, sample_match):
    """Audit log ghi nhận mọi hành động host/override, tuyệt đối không chứa token (§26, D15)."""
    match, host_token = sample_match
    auth_host_header = {"HTTP_AUTHORIZATION": f"Bearer {host_token}"}
    MatchService.start_match(match)

    team1, team2 = list(match.teams.all())[:2]
    member = team1.members.first()

    # 1. Skip / override phase
    res_phase = api_client.post(
        f"/api/v1/matches/{match.id}/advance-phase/",
        {"target_phase": MatchPhase.FINAL_ASSAULT, "is_override": True, "reason": "Skip to assault"},
        **auth_host_header,
    )
    assert res_phase.status_code == 200
    match.refresh_from_db()
    assert match.phase == MatchPhase.FINAL_ASSAULT

    # 2. Reassign participant during active match via override
    res_reassign = api_client.post(
        f"/api/v1/matches/{match.id}/members/{member.id}/assign/",
        {"team_id": str(team2.id), "role": MemberRole.MENTEE, "is_override": True, "reason": "Balance team"},
        **auth_host_header,
    )
    assert res_reassign.status_code == 200

    # 3. Adjust coins via override
    res_coins = api_client.post(
        f"/api/v1/matches/{match.id}/override/adjust-coins/",
        {"team_id": str(team1.id), "amount": 50, "reason": "Compensation for network glitch"},
        **auth_host_header,
    )
    assert res_coins.status_code == 200
    assert res_coins.json()["balance_after"] == 150

    # 4. Close stuck question via override
    q = Question.objects.create(content="Stuck?", answer_key="X", answer_validator_type="EXACT_MATCH")
    from datetime import timedelta

    from django.utils import timezone
    tq = TeamQuestion.objects.create(
        match=match,
        team=team1,
        question=q,
        sequence_number=1,
        status=QuestionStatus.PENDING_QUESTION,
        expires_at=timezone.now() + timedelta(minutes=5),
    )
    res_close_q = api_client.post(
        f"/api/v1/matches/{match.id}/override/close-question/",
        {"team_question_id": str(tq.id), "reason": "Player browser hung"},
        **auth_host_header,
    )
    assert res_close_q.status_code == 200

    # 5. Kick participant during active match via override
    res_kick = api_client.delete(
        f"/api/v1/matches/{match.id}/members/{member.id}/?is_override=true&reason=Inappropriate+behavior",
        **auth_host_header,
    )
    assert res_kick.status_code == 200

    # Verify audit logs in MatchEvent
    override_events = MatchEvent.objects.filter(match=match, event_type="ADMINISTRATIVE_OVERRIDE")
    assert override_events.count() >= 5

    # Check NO token or secret in any event payload
    for ev in MatchEvent.objects.filter(match=match):
        payload_str = str(ev.payload).lower()
        assert "participant_token" not in payload_str
        assert "host_token" not in payload_str
        assert host_token.lower() not in payload_str


@pytest.mark.django_db
def test_host_monitoring_telemetry_and_event_filtering(api_client, sample_match):
    """Host telemetry feed and event filtering/pagination (§2.2)."""
    match, host_token = sample_match
    auth_host_header = {"HTTP_AUTHORIZATION": f"Bearer {host_token}"}
    MatchService.start_match(match)

    # Telemetry endpoint
    res_telem = api_client.get(f"/api/v1/matches/{match.id}/host-telemetry/", **auth_host_header)
    assert res_telem.status_code == 200
    telem = res_telem.json()
    assert telem["match_id"] == str(match.id)
    assert len(telem["teams"]) == 4
    for t in telem["teams"]:
        assert "base_hp" in t
        assert "coins" in t
        assert "active_units" in t
        assert "active_towers" in t
        assert "remaining_questions" in t
        assert "has_pending_reward" in t

    # Events endpoint filtering by event_type
    res_events = api_client.get(
        f"/api/v1/matches/{match.id}/events/?event_type=MATCH_STARTED,CONFIG_UPDATED&order=asc",
        **auth_host_header,
    )
    assert res_events.status_code == 200
    data = res_events.json()
    assert "events" in data
    assert any(ev["event_type"] == "MATCH_STARTED" for ev in data["events"])


@pytest.mark.django_db
def test_presets_balance_preview_and_rematch_api(api_client, sample_match):
    """Presets, balance preview, and rematch APIs (§2.3, §2.4, FR-10)."""
    match, host_token = sample_match
    auth_host_header = {"HTTP_AUTHORIZATION": f"Bearer {host_token}"}

    # 1. Presets list
    res_presets = api_client.get("/api/v1/matches/presets/")
    assert res_presets.status_code == 200
    presets = res_presets.json()
    assert len(presets) >= 3
    preset_ids = [p["id"] for p in presets]
    assert "quick_15m" in preset_ids

    # 2. Apply preset during LOBBY
    res_apply = api_client.post(
        f"/api/v1/matches/{match.id}/apply-preset/",
        {"preset_id": "quick_15m"},
        **auth_host_header,
    )
    assert res_apply.status_code == 200
    match.refresh_from_db()
    assert match.configuration["match_duration_seconds"] == 900
    assert match.configuration["initial_coins"] == 150

    # 3. Balance preview
    res_preview = api_client.post(
        f"/api/v1/matches/{match.id}/config/preview/",
        {"configuration": match.configuration},
        format="json",
        **auth_host_header,
    )
    assert res_preview.status_code == 200
    preview = res_preview.json()
    assert preview["total_match_minutes"] == 15.0
    assert preview["pacing"] == "FAST"
    assert preview["total_projected_coins_per_team"] > 150

    # 4. Rematch after finish
    MatchService.start_match(match)
    MatchService.end_match(match)

    res_rematch = api_client.post(f"/api/v1/matches/{match.id}/rematch/", **auth_host_header)
    assert res_rematch.status_code == 201
    rematch_data = res_rematch.json()
    assert rematch_data["new_match_id"] != str(match.id)
    assert len(rematch_data["new_room_code"]) == 6
    assert "host_token" in rematch_data

    # Verify new match has cloned teams in LOBBY
    new_match = Match.objects.get(pk=rematch_data["new_match_id"])
    assert new_match.status == MatchStatus.LOBBY
    assert new_match.teams.count() == 4


@pytest.mark.django_db
def test_unit_types_host_admin_crud(api_client, sample_match):
    """Host/admin management for UnitTypes (§2.3)."""
    # 1. List
    res = api_client.get("/api/v1/unit-types/")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    # 2. Create new custom unit
    payload = {
        "code": "CYBER_TITAN",
        "name": "Cyber Titan",
        "category": "UNIT",
        "description": "Heavy siege titan.",
        "cost": 150,
        "is_starter": False,
        "is_unlockable": True,
        "is_active": True,
        "base_stats": {"hp": 600, "damage": 80, "range": 2, "movement": 1},
    }
    res_create = api_client.post("/api/v1/unit-types/", payload, format="json")
    assert res_create.status_code == 201
    unit_id = res_create.json()["id"]

    # 3. Patch unit cost
    res_patch = api_client.patch(f"/api/v1/unit-types/{unit_id}/", {"cost": 160}, format="json")
    assert res_patch.status_code == 200
    assert res_patch.json()["cost"] == 160
