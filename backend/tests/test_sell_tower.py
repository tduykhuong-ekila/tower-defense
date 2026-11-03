"""Tower resale preserves paid cost, frees space and cannot credit twice."""
import pytest
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.combat.map import get_game_map
from apps.economy.models import CoinTransaction
from apps.matches.models import MatchEvent
from apps.teams.models import TeamMember
from apps.units.models import GameAction, GameEntity, UnitType
from apps.units.placement import placement_grid
from apps.units.services import ConstructionService
from tests.test_grid_placement import build, grid_room, valid_cells


def tower_room():
    match, teams, tokens, host = grid_room()
    cell = next(valid_cells(placement_grid(get_game_map(2, 6))))
    action, tower = build(match, teams[0], *cell)
    return match, teams, tokens, cell, action, tower


@pytest.mark.django_db
@pytest.mark.parametrize('hp,max_hp', [(100, 100), (51, 100), (1, 100), (80, 200)])
def test_sale_refund_uses_paid_price_and_hp_and_frees_footprint(hp, max_hp):
    match, teams, _, cell, purchase, tower = tower_room()
    team = teams[0]
    team.refresh_from_db()
    before = team.coins
    tower.current_hp, tower.max_hp, tower.status = hp, max_hp, 'DISABLED'
    tower.save()
    UnitType.objects.filter(pk=tower.unit_type_id).update(cost=999)
    action, sold = ConstructionService.sell_tower(match, team, tower.pk, idempotency_key='sale')
    refund = purchase.payload['cost'] * hp // max_hp
    team.refresh_from_db()
    assert team.coins == before + refund
    assert sold.status == 'DESTROYED' and sold.destroyed_at
    assert action.payload['refund'] == refund
    assert CoinTransaction.objects.filter(team=team, reference_type='SELL_TOWER').count() == int(refund > 0)
    assert MatchEvent.objects.filter(match=match, event_type='TOWER_SOLD').count() == 1
    retry, _ = ConstructionService.sell_tower(match, team, tower.pk, idempotency_key='sale')
    assert retry.pk == action.pk
    with pytest.raises(ValidationError):
        ConstructionService.sell_tower(match, team, tower.pk, idempotency_key='sale-again')
    UnitType.objects.filter(pk=tower.unit_type_id).update(cost=purchase.payload['cost'])
    _, replacement = build(match, team, *cell, key='rebuild')
    assert replacement.pk != tower.pk


@pytest.mark.django_db
@pytest.mark.parametrize('failure', ['enemy', 'spectator', 'paused', 'finished', 'eliminated', 'unit', 'dead', 'conflict'])
def test_rejected_sale_preserves_entity_and_economy(failure):
    match, teams, _, _, _, tower = tower_room()
    team, actor, key = teams[0], None, 'sale'
    if failure == 'enemy':
        team = teams[1]
    elif failure == 'spectator':
        actor = TeamMember.objects.get(team=teams[0])
        actor.role = 'SPECTATOR'
    elif failure in ('paused', 'finished'):
        match.status = failure.upper()
        match.save()
    elif failure == 'eliminated':
        team.status = 'ELIMINATED'
        team.save()
    elif failure == 'unit':
        tower.entity_kind = 'UNIT'
        tower.save()
    elif failure == 'dead':
        tower.current_hp = 0
        tower.save()
    elif failure == 'conflict':
        key = 'build'
    team.refresh_from_db()
    before = team.coins
    with pytest.raises(ValidationError):
        ConstructionService.sell_tower(match, team, tower.pk, actor=actor, idempotency_key=key)
    team.refresh_from_db()
    tower.refresh_from_db()
    assert team.coins == before
    assert tower.status == 'ACTIVE'
    assert not GameAction.objects.filter(team=team, action_type='SELL_TOWER').exists()


@pytest.mark.django_db
def test_rest_sale_in_live_battle_and_invalid_request():
    match, teams, tokens, _, purchase, tower = tower_room()
    match.phase = 'WAR'
    match.configuration['timer_state']['round_phase'] = 'BATTLE'
    match.save()
    client = APIClient()
    client.credentials(HTTP_X_PARTICIPANT_TOKEN=tokens[0])
    url = f'/api/v1/matches/{match.pk}/actions/sell/'
    assert client.post(url, {'entity_id': 'invalid'}, format='json').status_code == 400
    result = client.post(url, {'entity_id': str(tower.pk), 'idempotency_key': 'sale'}, format='json')
    assert result.status_code == 200, result.data
    assert result.data['refund'] == purchase.payload['cost']
    assert result.data['entity']['status'] == 'DESTROYED'
    assert client.post(url, {'entity_id': str(tower.pk), 'idempotency_key': 'sale'}, format='json').data['refund'] == result.data['refund']
    client.credentials(HTTP_X_PARTICIPANT_TOKEN=tokens[-1])
    assert client.post(url, {'entity_id': str(tower.pk), 'idempotency_key': 'sale'}, format='json').status_code == 403


@pytest.mark.django_db
def test_historical_tower_uses_build_receipt_when_price_changed():
    match, teams, _, _, purchase, tower = tower_room()
    tower.simulation_state.pop('build_cost')
    tower.save()
    UnitType.objects.filter(pk=tower.unit_type_id).update(cost=999)
    sale, _ = ConstructionService.sell_tower(match, teams[0], tower.pk)
    assert sale.payload['refund'] == purchase.payload['cost']
