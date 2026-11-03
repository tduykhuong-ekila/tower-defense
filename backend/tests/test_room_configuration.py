"""Single-player teams, server capacity constraints and legacy lobby compatibility."""
import pytest
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.matches.defaults import DEFAULT_MAX_TEAMS, MAX_TEAMS, MIN_TEAMS_TO_START
from apps.matches.models import MatchStatus
from apps.matches.serializers import MatchDetailSerializer
from apps.matches.services import MatchService
from apps.realtime.services import RealtimeService
from apps.teams.models import MemberRole, TeamMember


@pytest.mark.django_db
@pytest.mark.parametrize('maximum', [None, 2, 4, 20])
def test_create_with_only_maximum_capacity(maximum):
    config = {} if maximum is None else {'max_teams': maximum}
    response = APIClient().post('/api/v1/matches/', {'name': 'Capacity', 'configuration': config}, format='json')
    assert response.status_code == 201
    saved = response.json()['configuration']
    assert saved['max_teams'] == (DEFAULT_MAX_TEAMS if maximum is None else maximum)
    assert saved['min_teams'] == MIN_TEAMS_TO_START
    assert saved['min_players_per_team'] == 1
    assert response.json()['teams'] == []


@pytest.mark.django_db
@pytest.mark.parametrize('maximum', [0, 1, 21, -1, 4.5, 'invalid'])
def test_invalid_capacity_rejected(maximum):
    response = APIClient().post('/api/v1/matches/', {'configuration': {'max_teams': maximum}}, format='json')
    assert response.status_code == 400


def test_constraints_endpoint_matches_validation_constants():
    result = APIClient().get('/api/v1/matches/constraints/')
    assert result.status_code == 200
    assert result.json() == {'max_teams': MAX_TEAMS, 'min_teams_to_start': MIN_TEAMS_TO_START,
                             'default_max_teams': DEFAULT_MAX_TEAMS, 'min_members_per_team': 1}


@pytest.mark.django_db
@pytest.mark.parametrize('count,maximum', [(2, 4), (6, 20), (20, 20)])
def test_single_member_teams_ready_and_start_below_capacity(count, maximum):
    match, _ = MatchService.create_match(configuration={'max_teams': maximum})
    for i in range(count):
        team = MatchService.create_team(match, f'Team {i}')
        # No required mentor/mentee pair; either participant role suffices.
        MatchService.join_match(match, 'Solo', team.id, MemberRole.MENTOR if i % 2 else MemberRole.MENTEE)
        MatchService.set_team_ready(team, True)
    started = MatchService.start_match(match)
    assert started.status == MatchStatus.ACTIVE
    assert started.members.count() == count  # No synthetic participants.
    assert all(t.coins == 100 and t.base_hp == 500 for t in started.teams.all())
    assert started.configuration['correct_answer_coin_reward'] == 30


@pytest.mark.django_db
@pytest.mark.parametrize('role', [None, MemberRole.SPECTATOR, MemberRole.HOST])
def test_empty_or_nonplaying_team_cannot_start(role):
    match, _ = MatchService.create_match()
    team = MatchService.create_team(match, 'Missing player')
    if role:
        TeamMember.objects.create(match=match, team=team, display_name='Observer', role=role, token_hash='observer')
    MatchService.set_team_ready(team, True)
    other = MatchService.create_team(match, 'Solo')
    MatchService.join_match(match, 'Player', other.id)
    MatchService.set_team_ready(other, True)
    with pytest.raises(ValidationError, match='not have enough players'):
        MatchService.start_match(match)
    match.refresh_from_db()
    assert match.status == MatchStatus.LOBBY


@pytest.mark.django_db
def test_legacy_membership_minimum_normalizes_but_team_minimum_is_preserved():
    match, _ = MatchService.create_match(configuration={'min_teams': 4, 'max_teams': 8})
    match.configuration['min_players_per_team'] = 2
    match.save()
    assert MatchDetailSerializer(match).data['configuration']['min_players_per_team'] == 1
    assert RealtimeService.build_snapshot(match)['payload']['match']['configuration']['min_players_per_team'] == 1
    teams = []
    for i in range(4):
        team = MatchService.create_team(match, f'Team {i}')
        MatchService.join_match(match, 'Solo', team.id)
        MatchService.set_team_ready(team, True)
        teams.append(team)
        if i == 1:
            with pytest.raises(ValidationError, match='4 teams required'):
                MatchService.start_match(match)
    MatchService.join_match(match, 'Second player', teams[0].id)
    MatchService.set_team_ready(teams[0], True)
    started = MatchService.start_match(match)
    assert started.configuration['min_teams'] == 4
    assert started.configuration['min_players_per_team'] == 1
    assert teams[0].members.count() == 2


@pytest.mark.django_db
def test_capacity_blocks_new_teams_but_allows_joining_existing_team():
    match, _ = MatchService.create_match(configuration={'max_teams': 2})
    first = MatchService.create_team(match, 'One')
    MatchService.create_team(match, 'Two')
    with pytest.raises(ValidationError, match='Maximum number'):
        MatchService.create_team(match, 'Three')
    MatchService.join_match(match, 'Player', first.id)
    assert first.members.count() == 1


@pytest.mark.django_db
def test_capacity_cannot_shrink_below_existing_teams_and_start_revalidates_count():
    match, _ = MatchService.create_match(configuration={'max_teams': 4})
    for i in range(3):
        MatchService.create_team(match, str(i))
    with pytest.raises(ValidationError, match='existing team count'):
        MatchService.update_configuration(match, {'max_teams': 2})
    match.configuration['max_teams'] = 2
    match.save()
    with pytest.raises(ValidationError, match='exceeds configured arena capacity'):
        MatchService.start_match(match)


@pytest.mark.django_db
def test_one_competing_team_cannot_start_even_with_valid_member():
    match, _ = MatchService.create_match()
    team = MatchService.create_team(match, 'Solo team')
    MatchService.join_match(match, 'Player', team.id)
    MatchService.set_team_ready(team, True)
    with pytest.raises(ValidationError, match='2 teams required'):
        MatchService.start_match(match)


@pytest.mark.django_db
def test_foreign_match_member_does_not_satisfy_team_membership():
    match, _ = MatchService.create_match()
    other_match, _ = MatchService.create_match()
    first = MatchService.create_team(match, 'Invalid member')
    TeamMember.objects.create(match=other_match, team=first, display_name='Foreign', token_hash='foreign')
    MatchService.set_team_ready(first, True)
    second = MatchService.create_team(match, 'Valid member')
    MatchService.join_match(match, 'Player', second.id)
    MatchService.set_team_ready(second, True)
    with pytest.raises(ValidationError, match='not have enough players'):
        MatchService.start_match(match)
