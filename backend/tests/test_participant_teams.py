"""Participants create teams only on initial join; lobby creation remains host-only."""
import uuid

import pytest
from rest_framework.test import APIClient

from apps.matches.models import MatchStatus
from apps.matches.services import MatchService
from apps.teams.models import MemberRole

pytestmark = pytest.mark.django_db


def post(match, path, data, token=None):
    headers = {"X-Participant-Token": token} if token else {}
    return APIClient().post(f"/api/v1/matches/{match.id}/{path}/", data,
                            format="json", headers=headers)


@pytest.mark.parametrize("role", [MemberRole.MENTOR, MemberRole.MENTEE])
def test_join_creates_team_and_keeps_selected_role(role):
    match, _ = MatchService.create_match()
    result = post(match, "join", {"display_name": "Player", "role": role,
                                  "new_team_name": "  My team  "})
    assert result.status_code == 201
    team = match.teams.get()
    assert team.name == "My team"
    assert result.data["member"]["team_id"] == str(team.id)
    assert result.data["member"]["role"] == role
    assert team.members.count() == 1
    assert result.data["participant_token"].startswith("pt_")


@pytest.mark.parametrize("role", [MemberRole.MENTOR, MemberRole.MENTEE])
@pytest.mark.parametrize("already_assigned", [True, False])
def test_participant_cannot_create_in_lobby(role, already_assigned):
    match, _ = MatchService.create_match()
    old = MatchService.create_team(match, "Old")
    member, token = MatchService.join_match(match, "Player", old.id if already_assigned else None, role)
    if already_assigned:
        MatchService.set_team_ready(old, True)
    result = post(match, "teams", {"name": "New"}, token)
    assert result.status_code == 403
    member.refresh_from_db()
    old.refresh_from_db()
    assert member.team_id == (old.id if already_assigned else None)
    assert member.role == role
    assert old.is_ready == already_assigned
    assert match.teams.count() == 1
    assert match.members.count() == 1


@pytest.mark.parametrize("role", [MemberRole.MENTOR, MemberRole.MENTEE])
def test_joined_participant_cannot_reuse_join_endpoint_to_create_team(role):
    match, _ = MatchService.create_match()
    member, token = MatchService.join_match(match, "Player", role=role)
    assert post(match, "join", {"display_name": "Player again", "role": role,
                                "new_team_name": "Another team"}, token).status_code == 403
    member.refresh_from_db()
    assert member.team_id is None
    assert match.teams.count() == 0 and match.members.count() == 1


def test_token_from_another_match_does_not_block_initial_join_creation():
    previous, _ = MatchService.create_match()
    _, token = MatchService.join_match(previous, "Previous player")
    match, _ = MatchService.create_match()
    assert post(match, "join", {"display_name": "Player", "new_team_name": "New team"}, token).status_code == 201
    assert match.teams.count() == 1 and match.members.count() == 1


@pytest.mark.parametrize("failure", ["duplicate", "capacity", "locked", "active", "spectator", "blank", "long"])
def test_join_creation_failure_leaves_no_team_or_member(failure):
    match, _ = MatchService.create_match(configuration={"max_teams": 2, "allow_late_join": True})
    MatchService.create_team(match, "Existing")
    data = {"display_name": "Player", "role": "MENTEE", "new_team_name": "New"}
    if failure == "duplicate":
        data["new_team_name"] = " existing "
    elif failure == "capacity":
        MatchService.create_team(match, "Second")
    elif failure == "locked":
        match.is_locked = True
        match.save()
    elif failure == "active":
        match.status = MatchStatus.ACTIVE
        match.save()
    elif failure == "spectator":
        data["role"] = "SPECTATOR"
    elif failure == "blank":
        data["new_team_name"] = "  "
    else:
        data["new_team_name"] = "x" * 51
    count = match.teams.count()
    assert post(match, "join", data).status_code == 400
    assert match.teams.count() == count
    assert match.members.count() == 0


def test_existing_team_and_new_name_are_mutually_exclusive():
    match, _ = MatchService.create_match()
    team = MatchService.create_team(match, "Existing")
    assert post(match, "join", {"display_name": "Player", "team_id": str(team.id),
                                "new_team_name": "New"}).status_code == 400
    assert match.teams.count() == 1 and match.members.count() == 0


def test_participant_create_authentication_and_match_scope():
    match, host = MatchService.create_match()
    other, _ = MatchService.create_match()
    _, foreign_token = MatchService.join_match(other, "Foreign")
    _, spectator = MatchService.join_match(match, "Observer", role="SPECTATOR")
    for token in [None, "invalid", foreign_token, spectator]:
        assert post(match, "teams", {"name": "Blocked"}, token).status_code == 403
    response = APIClient().post(f"/api/v1/matches/{match.id}/teams/", {"name": "Host team"},
                                format="json", headers={"X-Host-Token": host})
    assert response.status_code == 201
    assert match.teams.get().members.count() == 0


@pytest.mark.parametrize("failure", ["duplicate", "capacity", "locked", "active"])
def test_failed_lobby_creation_preserves_original_membership(failure):
    match, _ = MatchService.create_match(configuration={"max_teams": 2})
    old = MatchService.create_team(match, "Old")
    member, token = MatchService.join_match(match, "Player", old.id)
    name = "New"
    if failure == "duplicate":
        name = "old"
    elif failure == "capacity":
        MatchService.create_team(match, "Second")
    elif failure == "locked":
        match.is_locked = True
        match.save()
    else:
        match.status = MatchStatus.ACTIVE
        match.save()
    count = match.teams.count()
    assert post(match, "teams", {"name": name}, token).status_code == 403
    member.refresh_from_db()
    assert member.team_id == old.id
    assert match.teams.count() == count


def test_invitation_join_still_enforces_team_capacity_and_mentor_limit():
    match, _ = MatchService.create_match(configuration={"max_players_per_team": 2})
    team = MatchService.create_team(match, "Invited")
    MatchService.join_match(match, "Mentor", team.id, "MENTOR")
    MatchService.set_team_ready(team, True)
    payload = {"room_code": match.room_code, "display_name": "Guest", "team_id": str(team.id)}
    assert post(match, "join", {**payload, "role": "MENTOR"}).status_code == 400
    result = post(match, "join", {**payload, "role": "MENTEE"})
    assert result.status_code == 201
    assert result.data["member"]["team_id"] == str(team.id)
    team.refresh_from_db()
    assert not team.is_ready
    # Capacity and team validation apply to a new name; Guest now resumes.
    resumed = post(match, "join", payload)
    assert resumed.status_code == 201
    assert resumed.data["member"]["id"] == result.data["member"]["id"]
    payload = {**payload, "display_name": "Another guest"}
    assert post(match, "join", payload).status_code == 400
    assert post(match, "join", {**payload, "team_id": str(uuid.uuid4())}).status_code == 400
    other, _ = MatchService.create_match()
    foreign = MatchService.create_team(other, "Foreign")
    assert post(match, "join", {**payload, "team_id": str(foreign.id)}).status_code == 400


def test_self_assignment_cannot_escalate_role_or_override_active_match():
    match, _ = MatchService.create_match()
    team = MatchService.create_team(match, "Destination")
    member, token = MatchService.join_match(match, "Player")
    path = f"members/{member.id}/assign"
    assert post(match, path, {"team_id": str(team.id), "role": "HOST"}, token).status_code == 403
    assert post(match, path, {"team_id": str(team.id), "role": "MENTEE"}, token).status_code == 200
    match.status = MatchStatus.ACTIVE
    match.save()
    assert post(match, path, {"role": "MENTOR", "is_override": True}, token).status_code == 400


def test_spectator_cannot_self_assign_into_playing_role():
    match, _ = MatchService.create_match()
    team = MatchService.create_team(match, "Destination")
    member, token = MatchService.join_match(match, "Observer", role="SPECTATOR")
    assert post(match, f"members/{member.id}/assign",
                {"team_id": str(team.id), "role": "MENTEE"}, token).status_code == 403
