"""Returning by exact display name recovers the participant within one room."""
import pytest
from rest_framework.test import APIClient

from apps.matches.models import MatchStatus
from apps.matches.services import MatchService, hash_token
from apps.teams.models import MemberRole, TeamMember

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("status", [MatchStatus.LOBBY, MatchStatus.ACTIVE, MatchStatus.PAUSED])
def test_rejoin_preserves_identity_team_role_and_progress_in_locked_room(status):
    match, _ = MatchService.create_match(configuration={"max_players_per_team": 1})
    team = MatchService.create_team(match, "Original")
    member, old_token = MatchService.join_match(match, "Hoàng Long", team.id, MemberRole.MENTOR)
    member.is_ready = True
    member.save(update_fields=["is_ready"])
    team.coins = 123
    team.is_ready = True
    team.save(update_fields=["coins", "is_ready"])
    match.status = status
    match.is_locked = True
    match.save(update_fields=["status", "is_locked"])

    # No previous browser token, and the default role differs from the saved one.
    result = APIClient().post(f"/api/v1/matches/{match.id}/join/", {
        "display_name": "  Hoàng Long  ", "room_code": match.room_code,
    }, format="json")
    assert result.status_code == 201
    assert result.data["member"]["id"] == str(member.id)
    assert result.data["member"]["team_id"] == str(team.id)
    assert result.data["member"]["role"] == MemberRole.MENTOR
    assert result.data["member"]["is_ready"] is True
    member.refresh_from_db()
    team.refresh_from_db()
    assert member.token_hash == hash_token(result.data["participant_token"])
    assert member.token_hash != hash_token(old_token)
    assert match.members.count() == 1
    assert team.coins == 123 and team.is_ready
    denied = APIClient().post(f"/api/v1/matches/{match.id}/join/", {
        "display_name": "New player",
    }, format="json")
    assert denied.status_code == 400


def test_names_are_exact_and_scoped_to_room():
    first, _ = MatchService.create_match()
    second, _ = MatchService.create_match()
    original, _ = MatchService.join_match(first, "Long")
    other, _ = MatchService.join_match(second, "Long")
    different_case, _ = MatchService.join_match(first, "long")
    recovered, _ = MatchService.join_match(first, "Long", new_team_name="Must not create")
    assert recovered.pk == original.pk
    assert len({original.pk, other.pk, different_case.pk}) == 3
    assert first.teams.count() == 0


def test_legacy_duplicate_names_do_not_resume_arbitrary_player():
    match, _ = MatchService.create_match()
    original, _ = MatchService.join_match(match, "Duplicate")
    TeamMember.objects.create(match=match, display_name="Duplicate", token_hash="legacy")
    result = APIClient().post(f"/api/v1/matches/{match.id}/join/", {
        "display_name": "Duplicate",
    }, format="json")
    assert result.status_code == 400
    assert "trùng" in result.data["error"]
    original.refresh_from_db()
    assert match.members.count() == 2
