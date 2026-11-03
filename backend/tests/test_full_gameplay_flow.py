"""Later-round purchases must agree with server planning state and preserve resources."""
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.matches.action_policy import ActionPolicy
from apps.matches.models import MatchEvent
from apps.matches.scheduler import MatchScheduler
from apps.questions.models import Question
from apps.questions.services import QuestionService
from apps.rewards.services import RewardService
from apps.units.models import GameEntity, TeamUnlock
from apps.units.services import ConstructionService, UnitService
from tests.test_round_lifecycle import T0, arena, tick


@pytest.mark.django_db
@pytest.mark.parametrize('count', [2, 4, 8, 20])
def test_five_planning_rounds_accept_new_purchases_and_preserve_game_state(count):
    match, teams, host = arena(count=count)
    a,b=teams[:2]
    tick(match,10)
    Question.objects.create(content='Unlock test?',answer_key='yes',time_limit_seconds=120)
    tq=QuestionService.get_or_assign_current_question(match,a)
    QuestionService.update_viewing(match, a, tq.pk, "test-viewer", "OPEN")
    QuestionService.submit_answer(match,a,str(tq.pk),'yes')
    RewardService.claim_reward(match,a,str(tq.pk),'UNLOCK',unit_type_id='tank')
    initial=a.coins
    ids=[]
    for round_no in range(1,6):
        assert match.configuration['current_round']==round_no
        assert match.configuration['timer_state']['round_phase']=='PLANNING'
        ActionPolicy.require_context(match,a,'DEPLOY_UNIT')
        action,unit=UnitService.deploy_unit(match,a,'infantry',str(b.pk),idempotency_key=f'deploy-{round_no}')
        ids.append(unit.pk)
        a.refresh_from_db()
        deployed=MatchEvent.objects.filter(match=match,event_type='UNIT_DEPLOYED').latest('sequence_number')
        assert deployed.payload['coins_after']==a.coins
        if round_no in (1,2,5):
            slot={1:1,2:2,5:3}[round_no]
            _,tower=ConstructionService.build_tower(match,b,'mg_tower',f'node_tower_t2_slot{slot}')
            b.refresh_from_db()
            assert MatchEvent.objects.filter(match=match,event_type='TOWER_BUILT').latest('sequence_number').payload['coins_after']==b.coins
        MatchScheduler.advance_due(match.pk,T0+timedelta(seconds=10+round_no*10))
        match.refresh_from_db()
        assert match.configuration['current_round']==round_no+1
        assert match.configuration['timer_state']['round_phase']=='PLANNING'
        assert GameEntity.objects.filter(pk__in=ids).count()==round_no
        assert TeamUnlock.objects.filter(team=a,unit_type__code='tank').exists()
        assert a.assigned_questions.count()==1
        # Retry exactly the same purchase across the boundary: no extra debit/entity.
        assert UnitService.deploy_unit(match,a,'infantry',str(b.pk),idempotency_key=f'deploy-{round_no}')[1].pk==unit.pk
    a.refresh_from_db()
    b.refresh_from_db()
    assert a.coins==initial-5*15+5*10
    assert GameEntity.objects.filter(team=b,entity_kind='TOWER').count()==3
    before=b.coins
    with pytest.raises(ValidationError) as err:
        ConstructionService.build_tower(match,b,'mg_tower','node_tower_t2_slot1')
    assert err.value.code=='INVALID_POSITION'  # Occupied slot; three of six slots are still free.
    b.refresh_from_db()
    assert b.coins==before
    # The planning event names the actual open round and deadline.
    event=MatchEvent.objects.filter(match=match,event_type='ROUND_STARTED').latest('sequence_number')
    assert event.payload['current_round']==6 and event.payload['round_phase']=='PLANNING'


@pytest.mark.django_db
@pytest.mark.parametrize('phase',['LOCKED','RESOLVING','RESULTS'])
def test_server_rejects_commands_in_nonplanning_round_phase(phase,caplog):
    match,teams,host=arena()
    match.configuration['timer_state']['round_phase']=phase
    match.save()
    initial=teams[0].coins
    client=APIClient()
    response=client.post(f'/api/v1/matches/{match.pk}/actions/deploy/',{
        'unit_type_code_or_id':'infantry','target_team_id':str(teams[1].pk),
        'team_id':str(teams[0].pk),'idempotency_key':'blocked',
    },format='json',HTTP_X_HOST_TOKEN=host)
    assert response.status_code==400
    assert response.json()['error_code']=='INVALID_PHASE'
    response=client.post(f'/api/v1/matches/{match.pk}/actions/build/',{
        'unit_type_code_or_id':'mg_tower', 'node_id':'node_tower_t1_slot1',
        'team_id':str(teams[0].pk), 'idempotency_key':'blocked-build',
    },format='json',HTTP_X_HOST_TOKEN=host)
    assert response.status_code==400 and response.json()['error_code']=='INVALID_PHASE'
    assert not GameEntity.objects.filter(match=match).exists()
    teams[0].refresh_from_db()
    assert teams[0].coins==initial
    record=next(r for r in caplog.records if r.getMessage().startswith('action_rejected'))
    assert record.match_id==str(match.pk) and record.reason_code=='INVALID_PHASE'
    assert record.round_number==1 and record.round_phase==phase


@pytest.mark.django_db
def test_purchase_failure_reasons_remain_specific_and_no_coins_are_spent():
    match,teams,_=arena()
    a,b=teams
    with pytest.raises(ValidationError) as err:
        UnitService.deploy_unit(match,a,'tank',str(b.pk))
    assert err.value.code=='UNIT_LOCKED'
    a.coins=0
    a.save()
    with pytest.raises(ValidationError) as err:
        UnitService.deploy_unit(match,a,'infantry',str(b.pk))
    assert err.value.code=='INSUFFICIENT_COINS'
    assert not GameEntity.objects.filter(match=match).exists()


def test_policy_preserves_final_assault_construction_rule():
    match=SimpleNamespace(pk='m',status='ACTIVE',phase='FINAL_ASSAULT',configuration={})
    team=SimpleNamespace(pk='a',match_id='m',status='ACTIVE')
    assert ActionPolicy.context(match,team,'DEPLOY_UNIT').allowed
    assert ActionPolicy.context(match,team,'BUILD_TOWER').reason_code=='INVALID_PHASE'
