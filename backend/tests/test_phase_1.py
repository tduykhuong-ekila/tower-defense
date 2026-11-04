import pytest
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from apps.matches.models import Match, MatchPhase, MatchStatus
from apps.matches.services import MatchService
from apps.teams.models import MemberRole, Team, TeamMember


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
def test_create_match_api(api_client):
    """Host can create match, receiving room code and host token."""
    response = api_client.post(
        "/api/v1/matches/",
        {"admin_password": "Admin123@", "name": "Championship 2026", "configuration": {"min_teams": 4}},
        format="json",
    )
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert "room_code" in data
    assert len(data["room_code"]) == 6
    assert data["status"] == "LOBBY"
    assert data["phase"] == "LOBBY"
    assert "host_token" in data
    assert data["host_token"].startswith("ht_")


@pytest.mark.django_db
def test_room_code_uniqueness_in_active_rooms():
    """Active matches must have unique room codes; finished matches allow room code reuse."""
    match1, _ = MatchService.create_match(name="Match 1")
    code = match1.room_code

    # Attempting to insert a duplicate active match with the same room_code violates DB constraint
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Match.objects.create(
                room_code=code,
                name="Duplicate Active Match",
                status=MatchStatus.LOBBY,
                phase=MatchPhase.LOBBY,
                host_token_hash="fakehash",
            )

    # If the first match finishes, the same room code can be reused
    match1.status = MatchStatus.FINISHED
    match1.save()

    match2 = Match.objects.create(
        room_code=code,
        name="Reused After Finished",
        status=MatchStatus.LOBBY,
        phase=MatchPhase.LOBBY,
        host_token_hash="fakehash2",
    )
    assert match2.room_code == code


@pytest.mark.django_db
def test_non_host_cannot_modify_lobby_or_start_match(api_client):
    """User without host token or guest participant cannot start match or edit lobby."""
    match, host_token = MatchService.create_match(name="Test Match")
    team = MatchService.create_team(match, "Team Alpha")
    member, pt_token = MatchService.join_match(match, "Player 1", team_id=team.id)

    # 1. Unauthenticated / No token
    res = api_client.post(f"/api/v1/matches/{match.id}/start/")
    assert res.status_code == 403

    # 2. Participant token used to attempt starting match
    res = api_client.post(
        f"/api/v1/matches/{match.id}/start/",
        headers={"X-Participant-Token": pt_token},
    )
    assert res.status_code == 403

    # 3. Participants cannot create another team after joining the lobby.
    res = api_client.post(
        f"/api/v1/matches/{match.id}/teams/",
        {"name": "Team Rogue"},
        headers={"X-Participant-Token": pt_token},
        format="json",
    )
    assert res.status_code == 403
    member.refresh_from_db()
    assert member.team_id == team.id
    assert match.teams.count() == 1

    # 4. Participant token used to update config
    res = api_client.patch(
        f"/api/v1/matches/{match.id}/config/",
        {"initial_coins": 9999},
        headers={"X-Participant-Token": pt_token},
        format="json",
    )
    assert res.status_code == 403

    # 5. Room code alone in headers or body does NOT grant host privileges (§2.4)
    res = api_client.post(
        f"/api/v1/matches/{match.id}/start/",
        {"room_code": match.room_code},
        format="json",
    )
    assert res.status_code == 403


@pytest.mark.django_db
def test_host_can_remove_participant_before_start_but_not_after(api_client):
    """Host can remove participant before start; cannot remove participant after start."""
    # Create match requiring 2 teams for easy testing
    match, host_token = MatchService.create_match(
        name="Kick Test",
        configuration={"min_teams": 2, "min_players_per_team": 1},
    )
    team1 = MatchService.create_team(match, "Team 1")
    team2 = MatchService.create_team(match, "Team 2")

    member1, _ = MatchService.join_match(match, "Member 1", team_id=team1.id)
    member2, _ = MatchService.join_match(match, "Member 2", team_id=team1.id)
    member3, _ = MatchService.join_match(match, "Member 3", team_id=team2.id)

    # Host removes member2 before start -> succeeds
    res = api_client.delete(
        f"/api/v1/matches/{match.id}/members/{member2.id}/",
        headers={"X-Host-Token": host_token},
    )
    assert res.status_code == 200
    assert not TeamMember.objects.filter(pk=member2.id).exists()

    # Now ready up and start the match
    MatchService.set_team_ready(team1, True)
    MatchService.set_team_ready(team2, True)
    MatchService.start_match(match)

    # Host tries to remove member1 after start -> rejected with 400
    res = api_client.delete(
        f"/api/v1/matches/{match.id}/members/{member1.id}/",
        headers={"X-Host-Token": host_token},
    )
    assert res.status_code == 400
    assert TeamMember.objects.filter(pk=member1.id).exists()


@pytest.mark.django_db
def test_join_rejected_when_match_locked_or_started(api_client):
    """Join is rejected when match is locked or has already started (with allow_late_join=False)."""
    match, host_token = MatchService.create_match(
        name="Lock Test",
        configuration={"min_teams": 2, "min_players_per_team": 1, "allow_late_join": False},
    )
    team1 = MatchService.create_team(match, "Team 1")

    # Lock the match
    api_client.post(
        f"/api/v1/matches/{match.id}/lock/",
        {"is_locked": True},
        headers={"X-Host-Token": host_token},
        format="json",
    )
    match.refresh_from_db()
    assert match.is_locked is True

    # Attempt to join locked match
    res = api_client.post(
        f"/api/v1/matches/{match.id}/join/",
        {"display_name": "Late Joiner", "team_id": str(team1.id)},
        format="json",
    )
    assert res.status_code == 400
    assert "locked" in res.json()["error"].lower()

    # Unlock match
    api_client.post(
        f"/api/v1/matches/{match.id}/lock/",
        {"is_locked": False},
        headers={"X-Host-Token": host_token},
        format="json",
    )

    # Start match
    team2 = MatchService.create_team(match, "Team 2")
    MatchService.join_match(match, "P1", team_id=team1.id)
    MatchService.join_match(match, "P2", team_id=team2.id)
    MatchService.set_team_ready(team1, True)
    MatchService.set_team_ready(team2, True)
    MatchService.start_match(match)

    # Attempt to join started match
    res = api_client.post(
        f"/api/v1/matches/{match.id}/join/",
        {"display_name": "Late Joiner 2"},
        format="json",
    )
    assert res.status_code == 400
    assert "already started" in res.json()["error"].lower()


@pytest.mark.django_db
def test_start_rejected_when_insufficient_teams_or_unready(api_client):
    """Start is rejected when teams < min_teams or teams are not ready."""
    match, host_token = MatchService.create_match(
        name="Validation Test",
        configuration={"min_teams": 4, "min_players_per_team": 2},
    )
    t1 = MatchService.create_team(match, "Team 1")
    t2 = MatchService.create_team(match, "Team 2")

    # Only 2 teams created, but 4 required
    res = api_client.post(
        f"/api/v1/matches/{match.id}/start/",
        headers={"X-Host-Token": host_token},
    )
    assert res.status_code == 400
    assert "4 teams required" in res.json()["error"]

    # Add teams 3 and 4
    t3 = MatchService.create_team(match, "Team 3")
    t4 = MatchService.create_team(match, "Team 4")

    # Add members to meet min_players_per_team
    for t in [t1, t2, t3, t4]:
        MatchService.join_match(match, f"{t.name}_P1", team_id=t.id)
        MatchService.join_match(match, f"{t.name}_P2", team_id=t.id)

    # Teams are not ready yet
    res = api_client.post(
        f"/api/v1/matches/{match.id}/start/",
        headers={"X-Host-Token": host_token},
    )
    assert res.status_code == 400
    assert "not ready" in res.json()["error"]


@pytest.mark.django_db
def test_invalid_phase_transition_rejected(api_client):
    """Phase transitions must follow the strict sequence."""
    match, host_token = MatchService.create_match(
        name="Phase Test",
        configuration={"gameplay_mode": "LEGACY", "min_teams": 2, "min_players_per_team": 1},
    )
    t1 = MatchService.create_team(match, "T1")
    t2 = MatchService.create_team(match, "T2")
    MatchService.join_match(match, "P1", team_id=t1.id)
    MatchService.join_match(match, "P2", team_id=t2.id)
    MatchService.set_team_ready(t1, True)
    MatchService.set_team_ready(t2, True)

    MatchService.start_match(match)
    match.refresh_from_db()
    assert match.phase == MatchPhase.PREPARATION

    # Trying to jump directly to FINAL_ASSAULT or RESULTS -> rejected
    res = api_client.post(
        f"/api/v1/matches/{match.id}/advance-phase/",
        {"target_phase": MatchPhase.RESULTS},
        headers={"X-Host-Token": host_token},
        format="json",
    )
    assert res.status_code == 400
    assert "Invalid phase transition" in res.json()["error"]

    # Advance to BUILD_AND_SCOUT -> succeeds
    res = api_client.post(
        f"/api/v1/matches/{match.id}/advance-phase/",
        {"target_phase": MatchPhase.BUILD_AND_SCOUT},
        headers={"X-Host-Token": host_token},
        format="json",
    )
    assert res.status_code == 200
    assert res.json()["phase"] == MatchPhase.BUILD_AND_SCOUT


@pytest.mark.django_db
def test_mentor_limit_per_team(api_client):
    """Each team can have at most one Mentor."""
    match, host_token = MatchService.create_match(name="Mentor Test")
    team = MatchService.create_team(match, "Alpha")

    # Member 1 joins as MENTOR -> succeeds
    res1 = api_client.post(
        f"/api/v1/matches/{match.id}/join/",
        {"display_name": "Mentor 1", "team_id": str(team.id), "role": MemberRole.MENTOR},
        format="json",
    )
    assert res1.status_code == 201

    # Member 2 tries to join as MENTOR to same team -> rejected
    res2 = api_client.post(
        f"/api/v1/matches/{match.id}/join/",
        {"display_name": "Mentor 2", "team_id": str(team.id), "role": MemberRole.MENTOR},
        format="json",
    )
    assert res2.status_code == 400
    assert "already has a mentor" in res2.json()["error"].lower()


@pytest.mark.django_db
def test_successful_start_and_stat_initialization(api_client):
    """
    Host creates match with custom stats, 4 teams join and get ready,
    Host starts match, verify teams have base_hp and coins correctly initialized from config.
    """
    custom_hp = 750
    custom_coins = 250

    match, host_token = MatchService.create_match(
        name="Epic Battle",
        configuration={
            "min_teams": 4,
            "min_players_per_team": 1,
            "initial_base_hp": custom_hp,
            "initial_coins": custom_coins,
        },
    )

    team_ids = []
    for i in range(1, 5):
        team = MatchService.create_team(match, f"Squad {i}")
        team_ids.append(team.id)
        # Participant joins team
        res = api_client.post(
            f"/api/v1/matches/{match.id}/join/",
            {"display_name": f"Hero_{i}", "team_id": str(team.id), "role": MemberRole.MENTEE},
            format="json",
        )
        assert res.status_code == 201
        # Set team ready
        MatchService.set_team_ready(team, True)

    # Host starts match
    res = api_client.post(
        f"/api/v1/matches/{match.id}/start/",
        headers={"X-Host-Token": host_token},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == MatchStatus.ACTIVE
    assert data["phase"] == MatchPhase.PREPARATION

    # Verify each team's stats
    teams = Team.objects.filter(match=match)
    assert teams.count() == 4
    for t in teams:
        assert t.base_hp == custom_hp
        assert t.initial_base_hp == custom_hp
        assert t.coins == custom_coins
        assert t.base_shield == 0
        assert t.status == "ACTIVE"


@pytest.mark.django_db
def test_pause_and_resume_and_end_match(api_client):
    """Host can pause, resume and end active match."""
    match, host_token = MatchService.create_match(
        name="Lifecycle Test",
        configuration={"min_teams": 2, "min_players_per_team": 1},
    )
    t1 = MatchService.create_team(match, "T1")
    t2 = MatchService.create_team(match, "T2")
    MatchService.join_match(match, "P1", team_id=t1.id)
    MatchService.join_match(match, "P2", team_id=t2.id)
    MatchService.set_team_ready(t1, True)
    MatchService.set_team_ready(t2, True)
    MatchService.start_match(match)

    # Pause
    res = api_client.post(
        f"/api/v1/matches/{match.id}/pause/", headers={"X-Host-Token": host_token}
    )
    assert res.status_code == 200
    assert res.json()["status"] == MatchStatus.PAUSED

    # Resume
    res = api_client.post(
        f"/api/v1/matches/{match.id}/resume/", headers={"X-Host-Token": host_token}
    )
    assert res.status_code == 200
    assert res.json()["status"] == MatchStatus.ACTIVE

    # End
    res = api_client.post(f"/api/v1/matches/{match.id}/end/", headers={"X-Host-Token": host_token})
    assert res.status_code == 200
    assert res.json()["status"] == MatchStatus.FINISHED
    assert res.json()["phase"] == MatchPhase.RESULTS
