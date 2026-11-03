"""Capacity, stable identity, replay and real multiplayer checks."""
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.combat.benchmark import create_scenario
from apps.combat.map import GameMap, get_game_map
from apps.combat.models import MatchResult
from apps.combat.scoring import ScoringService
from apps.combat.services import CombatService
from apps.economy.models import CoinTransaction
from apps.economy.services import EconomyService
from apps.matches.models import Match, MatchEvent
from apps.matches.serializers import MatchConfigurationSerializer
from apps.matches.services import MatchService
from apps.questions.models import Question
from apps.questions.services import QuestionService
from apps.realtime.services import RealtimeService, scope_live_event
from apps.rewards.services import RewardService
from apps.teams.models import Team
from apps.units.models import GameEntity, UnitType
from config.asgi import application


@pytest.mark.parametrize('count', range(2, 21))
def test_every_arena_is_deterministic_connected_fair_and_has_unique_territories(count):
    graph = GameMap(count)
    assert graph.validate_map() == (True, [])
    assert json.dumps(graph.to_dict()) == json.dumps(GameMap(count).to_dict())
    assert len({(n.x, n.y) for n in graph.nodes.values() if n.node_type == 'base'}) == count
    for i in range(1, count+1):
        assert len([n for n in graph.nodes.values() if n.team_index == i and n.node_type == 'tower_slot']) == 6
        distances = sorted(len(graph.get_path_to_base(graph.get_spawn_node(i), j)) for j in range(1, count+1) if j != i)
        assert distances == sorted(len(graph.get_path_to_base(graph.get_spawn_node(1), j)) for j in range(2, count+1))
        for j in range(1, count+1):
            path = graph.get_path_to_base(graph.get_spawn_node(i), j)
            assert path and all(graph.nodes[n].is_passable for n in path)
            assert all(b in graph.adjacency[a] for a,b in zip(path,path[1:]))


@pytest.mark.parametrize('count', [1, 21, 100])
def test_invalid_arena_and_configuration_rejected(count):
    with pytest.raises(ValueError):
        GameMap(count)
    assert not MatchConfigurationSerializer(data={'min_teams': 2, 'max_teams': count}).is_valid()


def test_four_team_coordinates_and_hop_lengths_remain_compatible():
    graph = get_game_map(4)
    assert graph.nodes['node_base_t1'].x == 400
    assert graph.nodes['node_lane_t1_2'].x == 240
    assert len(graph.get_path_to_base('node_spawn_t1', 3)) == 9


@pytest.mark.django_db
@pytest.mark.parametrize('count', [2, 3, 4, 5, 8, 12, 13, 16, 19, 20])
def test_start_and_public_contract_with_mentor_mentee_teams(count):
    match, _ = MatchService.create_match(name='Capacity', configuration={'min_teams': 2, 'max_teams': 20})
    for i in range(count):
        team = MatchService.create_team(match, f'Team {i}')
        for role in ['MENTOR','MENTEE']:
            MatchService.join_match(match, f'{role} {i}', team_id=team.id, role=role)
        MatchService.set_team_ready(team, True)
    MatchService.start_match(match)
    match.refresh_from_db()
    response = APIClient().get(f'/api/v1/matches/{match.id}/map/')
    assert response.status_code == 200
    snapshot = RealtimeService.build_snapshot(match)['payload']
    assert response.json() == snapshot['map_data']
    assert len(snapshot['teams']) == count
    assert all(t['members_count'] == 2 and 'coins' not in t and 'members' not in t for t in snapshot['teams'])
    assert match.status == 'ACTIVE'


@pytest.mark.django_db
def test_capacity_cannot_overflow_or_shrink_below_existing_teams():
    match, _ = MatchService.create_match(name='Full', configuration={'max_teams': 20})
    for i in range(20):
        MatchService.create_team(match, str(i))
    with pytest.raises(ValidationError):
        MatchService.create_team(match, '21')
    with pytest.raises(ValidationError):
        MatchService.update_configuration(match, {'max_teams': 19})


@pytest.mark.django_db(transaction=True)
def test_same_round_concurrent_workers_and_retries_apply_income_once():
    scenario = create_scenario(20)
    def worker():
        connection.close()
        try:
            return CombatService.execute_combat_round(Match.objects.get(id=scenario.match.id), expected_round=1)
        finally:
            connection.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        a,b = list(pool.map(lambda _: worker(), range(2)))
    assert a.events == b.events
    assert CombatService.execute_combat_round(scenario.match, expected_round=1).events == a.events
    assert MatchEvent.objects.filter(match=scenario.match, event_type='COMBAT_RESOLVED').count() == 1
    assert CoinTransaction.objects.filter(match=scenario.match, reference_type='COMBAT_ROUND', reference_id='1').count() == 20
    scenario.match.refresh_from_db()
    assert scenario.match.configuration['current_round'] == 2


@pytest.mark.django_db
def test_snapshot_query_budget_is_bounded_and_private_fields_stay_scoped():
    scenario = create_scenario(20,4)
    with CaptureQueriesContext(connection) as queries:
        payload = RealtimeService.build_snapshot(scenario.match, str(scenario.teams[-1].id))['payload']
    assert len(queries) <= 9  # One bounded query for all team upgrade levels.
    assert len(payload['entities']) == 160
    assert payload['teams'][-1]['team_index'] == 20
    assert len(payload['teams'][-1]['members']) == 4
    assert all('coins' not in t and 'unlocked_units' not in t and 'members' not in t for t in payload['teams'][:-1])
    assert 'answer_key' not in json.dumps(payload)
    public = APIClient().get(f'/api/v1/matches/{scenario.match.id}/').json()
    assert all('coins' not in t for t in public['teams'])


@pytest.mark.django_db
def test_twenty_teams_play_answer_reward_deploy_combat_reconnect_and_finalize():
    scenario = create_scenario(20)
    match, teams = scenario.match, scenario.teams
    Question.objects.create(type='SHORT_TEXT',category='Arena',difficulty='EASY',content='2 + 2?',answer_key='4',answer_validator_type='NUMERIC',is_active=True)
    team = teams[-1]
    question = QuestionService.get_or_assign_current_question(match, team)
    QuestionService.update_viewing(match, team, question.pk, "test-viewer", "OPEN")
    QuestionService.submit_answer(match,team,str(question.id),'4',member=scenario.members[-1])
    team.refresh_from_db()
    before = team.coins
    claim = RewardService.claim_reward(match,team,str(question.id),'COIN',idempotency_key='twenty-reward',member=scenario.members[-1])
    again = RewardService.claim_reward(match,team,str(question.id),'COIN',idempotency_key='twenty-reward')
    team.refresh_from_db()
    question.refresh_from_db()
    assert team.coins == before + question.reward_coin_amount and claim.id == again.id
    with pytest.raises(ValidationError):
        RewardService.claim_reward(match, teams[0], str(question.id), 'COIN', idempotency_key='foreign-question')
    result = CombatService.execute_combat_round(match, expected_round=1)
    assert any(e.get('type') == 'UNIT_MOVED' and e.get('from_node') == 'node_spawn_t20' for e in result.events)
    GameEntity.objects.filter(match=match).update(status='DESTROYED')
    infantry = UnitType.objects.get(code='infantry')
    Team.objects.filter(match=match).exclude(id=teams[0].id).update(base_hp=10)
    for i, target in enumerate(teams[1:],2):
        GameEntity.objects.create(match=match, team=teams[0], unit_type=infantry, entity_kind='UNIT', current_hp=40,max_hp=40,status='ACTIVE',current_node_id=f'node_lane_t{i}_1',target_team=target)
    match.refresh_from_db()
    result = CombatService.execute_combat_round(match, expected_round=2)
    assert result.is_match_over and result.winner_team_id == str(teams[0].id)
    assert len(result.eliminated_team_ids) == 19
    assert MatchResult.objects.filter(match=match).count() == 20
    assert len(ScoringService.finalize_match(match)) == 20
    match.refresh_from_db()
    snapshot = RealtimeService.build_snapshot(match,str(team.id))['payload']
    assert snapshot['match']['status'] == 'FINISHED'
    assert snapshot['teams'][-1]['team_index'] == 20
    assert snapshot['viewer']['current_question']['status'] == 'REWARD_CLAIMED'


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_eighty_players_two_spectators_host_private_sync_and_reconnect():
    scenario = await database_sync_to_async(create_scenario)(20,4)
    def assign_active_questions():
        Question.objects.create(type='SHORT_TEXT',category='Socket',difficulty='EASY',content='2 + 2?',answer_key='4',answer_validator_type='NUMERIC',is_active=True)
        for team in scenario.teams:
            QuestionService.get_or_assign_current_question(scenario.match, team)
    await database_sync_to_async(assign_active_questions)()
    tokens = scenario.tokens+scenario.spectators+[scenario.host_token]
    comms = [WebsocketCommunicator(application,f'/ws/matches/{scenario.match.id}/?token={t}') for t in tokens]
    try:
        async def connect(comm):
            ok,_ = await comm.connect(timeout=20)
            assert ok
            snapshot = await comm.receive_json_from(timeout=20)
            if snapshot['event_type'] == 'JSON_CHUNK':
                parts = [snapshot['payload']['data']]
                total = snapshot['payload']['total']
                for index in range(1, total):
                    chunk = await comm.receive_json_from(timeout=20)
                    assert chunk['payload']['index'] == index
                    assert chunk['payload']['id'] == snapshot['payload']['id']
                    parts.append(chunk['payload']['data'])
                snapshot = json.loads(''.join(parts))
            assert len(snapshot['payload']['teams']) == 20
            return snapshot
        snapshots = await asyncio.gather(*(connect(c) for c in comms))
        assert all(s['payload']['viewer']['team_id'] is None for s in snapshots[-3:-1])
        await database_sync_to_async(EconomyService.credit)(scenario.teams[0],20,reference_type='MULTIPLAYER_QA')
        own = await asyncio.gather(*(c.receive_json_from(timeout=5) for c in comms[:4]+comms[-1:]))
        assert all(m['payload']['balance_after'] == snapshots[0]['payload']['viewer']['coins'] + 20 for m in own)
        redacted = await asyncio.gather(*(c.receive_json_from(timeout=5) for c in comms[4:-1]))
        assert all(m["event_type"] == "EVENT_REDACTED" and m["payload"] == {} for m in redacted)
        await comms[0].disconnect()
        replacement = WebsocketCommunicator(application,f'/ws/matches/{scenario.match.id}/?token={tokens[0]}')
        comms[0] = replacement
        snapshot = await connect(replacement)
        assert snapshot['payload']['viewer']['team_id'] == str(scenario.teams[0].id)
        assert snapshot['payload']['viewer']['current_question']['question']['content'] == '2 + 2?'
        assert len(snapshot['payload']['entities']) == 160
        assert snapshot['payload']['viewer']['coins'] == snapshots[0]['payload']['viewer']['coins'] + 20
        await comms[-2].send_json_to({'event_type':'DEPLOY_REQUEST','payload':{'unit_code':'infantry','target_team_id':str(scenario.teams[0].id)}})
        reject = await comms[-2].receive_json_from(timeout=5)
        assert reject['payload']['error_code'] == 'SPECTATOR_READ_ONLY'
    finally:
        await asyncio.gather(*(c.disconnect() for c in comms))


def test_public_combat_balances_are_projected_per_viewer_without_mutating_shared_event():
    event = {'event_id': 'one', 'payload': {'events': [
        {'type': 'INCOME_AWARDED', 'team_id': 'a', 'new_balance': 110},
        {'type': 'INCOME_AWARDED', 'team_id': 'b', 'new_balance': 220},
    ]}}
    own = scope_live_event(event, 'a', False)['payload']['events']
    assert own[0]['new_balance'] == 110 and 'new_balance' not in own[1]
    spectator = scope_live_event(event, None, False)['payload']['events']
    assert all('new_balance' not in e for e in spectator)
    assert scope_live_event(event, None, True) == event
    assert event['payload']['events'][1]['new_balance'] == 220
