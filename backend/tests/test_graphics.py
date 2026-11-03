"""Regression checks for the rendering contract; game rules remain server-owned."""
import pytest
from rest_framework.test import APIClient

from apps.matches.models import MatchEvent
from apps.matches.services import MatchService
from apps.realtime.services import RealtimeService
from apps.teams.models import Team
from apps.units.map import MapDefinition
from apps.units.seeds import ensure_standard_units
from apps.units.services import ConstructionService, UnitService


@pytest.mark.django_db
@pytest.mark.parametrize('team_count', [2, 4, 8])
def test_public_map_and_snapshot_share_exact_nodes_and_team_order(team_count):
    match, _ = MatchService.create_match(name='Graphics contract')
    for i in range(team_count):
        Team.objects.create(match=match, name=f'Team {i}')
    response = APIClient().get(f'/api/v1/matches/{match.id}/map/')
    assert response.status_code == 200
    map_data = response.json()
    snapshot = RealtimeService.build_snapshot(match)['payload']
    assert map_data == snapshot['map_data']
    assert map_data['num_teams'] == team_count
    assert len(map_data['team_ids']) == team_count
    ids = {node['node_id'] for node in map_data['nodes']}
    for i, team in enumerate(match.teams.order_by('created_at', 'id'), 1):
        assert map_data['team_ids'][i - 1] == str(team.id)
        assert MapDefinition.get_team_base_node(team) in ids
        assert MapDefinition.get_team_spawn_node(team) in ids
        assert set(MapDefinition.get_valid_tower_slots(team)) <= ids
    assert 'answer_key' not in str(map_data)
    assert 'coins' not in map_data


@pytest.mark.django_db
def test_deploy_and_build_events_include_server_hp_and_real_node_ids():
    ensure_standard_units()
    match, _ = MatchService.create_match(name='Playable graphics', configuration={'tower_placement_version':0,'arena_layout_version':5})
    teams = [Team.objects.create(match=match, name=f'Team {i}', coins=100) for i in range(2)]
    match.status = 'ACTIVE'
    match.phase = 'PREPARATION'
    match.save()
    _, entity = UnitService.deploy_unit(match, teams[0], 'infantry', str(teams[1].id), idempotency_key='graphics-deploy')
    event = MatchEvent.objects.get(match=match, event_type='UNIT_DEPLOYED')
    assert event.payload['current_hp'] == entity.current_hp == 80
    assert event.payload['max_hp'] == 80
    assert event.payload['current_node_id'] == 'node_spawn_t1'
    slot = MapDefinition.get_valid_tower_slots(teams[0])[0]
    _, tower = ConstructionService.build_tower(match, teams[0], 'mg_tower', slot, idempotency_key='graphics-build')
    event = MatchEvent.objects.get(match=match, event_type='TOWER_BUILT')
    assert event.payload['current_hp'] == tower.current_hp == 100
    assert event.payload['max_hp'] == 100
    assert event.payload['node_id'] == slot


@pytest.mark.django_db
def test_pending_reward_reconnect_has_complete_question_and_reward_contract():
    from datetime import timedelta

    from django.utils import timezone

    from apps.questions.models import Question, TeamQuestion

    ensure_standard_units()
    match, _ = MatchService.create_match(name='Reward reconnect')
    team = Team.objects.create(match=match, name='Readers')
    question = Question.objects.create(
        type='SHORT_TEXT', category='Test', difficulty='EASY', content='A test question',
        answer_key='secret answer', answer_validator_type='NORMALIZED_TEXT',
    )
    tq = TeamQuestion.objects.create(
        match=match, team=team, question=question, sequence_number=1,
        status='PENDING_REWARD', expires_at=timezone.now() + timedelta(seconds=60),
    )
    payload = RealtimeService.build_snapshot(match, viewer_team_id=str(team.id))['payload']
    assert payload['viewer']['current_question']['question']['content'] == question.content
    assert payload['viewer']['current_question']['id'] == str(tq.id)
    import json

    json.dumps(payload)  # Channels uses standard JSON, without DRF renderer coercion.
    reward = payload['viewer']['pending_reward']
    assert reward['coin_amount'] == 30
    assert reward['unlock_available'] is True
    assert reward['eligible_units'][0]['hp'] > 0
    assert 'answer_key' not in str(payload)
    assert question.answer_key not in str(payload)
