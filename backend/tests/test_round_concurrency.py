"""Cross-worker guarantees must be checked on PostgreSQL, which supports row locks."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from django.db import close_old_connections, connection

from apps.economy.models import CoinTransaction, TransactionType
from apps.matches.models import MatchEvent
from apps.matches.scheduler import MatchScheduler
from apps.matches.services import MatchService
from apps.questions.models import Question
from apps.questions.services import QuestionService
from apps.rewards.models import RewardClaim
from apps.rewards.services import RewardService
from apps.units.models import GameAction, GameEntity
from apps.units.services import UnitService
from tests.test_continuous_combat import room
from tests.test_round_lifecycle import T0, arena, tick

pytestmark = [pytest.mark.django_db(transaction=True),
              pytest.mark.skipif(connection.vendor != "postgresql", reason="Requires PostgreSQL row locks")]


def concurrent(run, count=4):
    gate = Barrier(count)
    def worker(index):
        close_old_connections()
        try:
            gate.wait(timeout=5)
            return run(index)
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(worker, range(count)))


def test_competing_schedulers_resolve_deadline_once():
    match, teams, _ = arena()
    UnitService.deploy_unit(match, teams[0], "infantry", str(teams[1].pk))
    tick(match, 10)
    concurrent(lambda _: MatchScheduler.advance_due(match.pk, T0 + timedelta(seconds=20)))
    match.refresh_from_db()
    assert match.configuration["current_round"] == 2
    assert MatchEvent.objects.filter(match=match, event_type="COMBAT_RESOLVED").count() == 1
    assert CoinTransaction.objects.filter(match=match, transaction_type=TransactionType.PASSIVE_INCOME).count() == 2
    assert GameEntity.objects.get(team=teams[0]).current_node_id == "node_lane_t1_2"


def test_simultaneous_shared_team_deployment_retry_charges_once():
    match, teams, _ = arena()
    results = concurrent(lambda _: UnitService.deploy_unit(
        match, teams[0], "infantry", str(teams[1].pk), idempotency_key="one-deploy",
    ))
    assert len({result[1].pk for result in results}) == 1
    assert GameAction.objects.filter(team=teams[0]).count() == 1
    assert GameEntity.objects.filter(team=teams[0]).count() == 1
    teams[0].refresh_from_db()
    assert teams[0].coins == 485


def test_many_teammates_deploy_beyond_cap_without_losing_debits():
    match, teams, _, _ = room(initial_coins=1000, max_active_units_per_team=1)
    from apps.teams.models import TeamMember
    member = TeamMember.objects.create(match=match, team=teams[0], display_name="Second teammate", role="MENTEE")
    first = teams[0].members.exclude(pk=member.pk).get()
    results = concurrent(lambda i: UnitService.deploy_unit(
        match, teams[0], "infantry", str(teams[1].pk), actor=member if i % 2 else first,
        idempotency_key=f"many-{i}"), count=20)
    assert len({entity.pk for _, entity in results}) == 20
    teams[0].refresh_from_db()
    assert teams[0].coins == 1000 - 20 * 15
    assert GameEntity.objects.filter(team=teams[0]).count() == 20
    assert match.events.filter(event_type="UNIT_DEPLOYED").count() == 20


def test_concurrent_distinct_and_duplicate_requests_cannot_overspend():
    from django.core.exceptions import ValidationError
    match, teams, _, _ = room(initial_coins=90, max_active_units_per_team=1)

    def deploy(i):
        try:
            return str(UnitService.deploy_unit(match, teams[0], "infantry", str(teams[1].pk),
                                              idempotency_key=f"budget-{i % 10}")[1].pk)
        except ValidationError as error:
            assert error.code == "INSUFFICIENT_COINS"
            return None
    results = concurrent(deploy, count=20)
    assert len({pk for pk in results if pk}) == 6
    teams[0].refresh_from_db()
    assert teams[0].coins == 0
    assert GameEntity.objects.filter(team=teams[0]).count() == 6
    assert GameAction.objects.filter(team=teams[0]).count() == 6


def test_simultaneous_reward_choice_cannot_claim_both():
    match, teams, _ = arena()
    Question.objects.create(content="Concurrent choice?", answer_key="yes", time_limit_seconds=120)
    tq = QuestionService.get_or_assign_current_question(match, teams[0])
    QuestionService.update_viewing(match, teams[0], tq.pk, "test-viewer", "OPEN")
    QuestionService.submit_answer(match, teams[0], str(tq.pk), "yes")
    results = concurrent(lambda i: RewardService.claim_reward(
        match, teams[0], str(tq.pk), "COIN" if i % 2 else "UNLOCK",
        unit_type_id="tank", idempotency_key=f"choice-{i}",
    ))
    assert len({claim.pk for claim in results}) == 1
    claim = RewardClaim.objects.get(team_question=tq)
    teams[0].refresh_from_db()
    assert teams[0].coins == (530 if claim.reward_type == "COIN" else 500)


def test_two_real_members_share_wallet_and_keep_deploying_in_round_two():
    from apps.combat.services import CombatService
    from apps.units.seeds import ensure_standard_units

    ensure_standard_units()
    match, _ = MatchService.create_match(configuration={"gameplay_mode": "LEGACY"})
    a = MatchService.create_team(match, "Shared team")
    b = MatchService.create_team(match, "Opponent")
    members = [MatchService.join_match(match, f"Member {i}", team_id=a.pk)[0] for i in range(2)]
    MatchService.join_match(match, "Opponent member", team_id=b.pk)
    MatchService.set_team_ready(a, True)
    MatchService.set_team_ready(b, True)
    match = MatchService.start_match(match)
    for round_number in (1, 2):
        concurrent(lambda i: UnitService.deploy_unit(match, a, "infantry", str(b.pk),
                   actor=members[i], idempotency_key=f"member-{i}-round-{round_number}"), count=2)
        if round_number == 1:
            CombatService.execute_combat_round(match, expected_round=1)
    a.refresh_from_db()
    assert a.coins == 100 - 4 * 15 + 10
    assert GameEntity.objects.filter(team=a).count() == 4
    assert set(GameAction.objects.filter(team=a).values_list("actor_id", flat=True)) == {m.pk for m in members}


def test_continuous_workers_commit_tick_and_damage_exactly_once():
    from datetime import datetime

    from apps.combat.continuous_service import ContinuousCombatService
    from tests.test_continuous_combat import room

    match, teams, _, _ = room(prep=2, battle=10)
    _, unit = UnitService.deploy_unit(match, teams[0], "infantry", str(teams[1].pk))
    unit.status = "ACTIVE"
    unit.current_node_id = "node_lane_t2_1"
    unit.simulation_state = {}
    unit.save()
    match = MatchService.advance_phase(match)
    tick_at = datetime.fromisoformat(match.configuration["timer_state"]["next_tick_at"])
    outcomes = concurrent(lambda _: ContinuousCombatService.tick(match.pk, tick_at))
    assert outcomes.count(True) == 1
    teams[1].refresh_from_db()
    match.refresh_from_db()
    assert teams[1].base_hp == 495
    assert match.configuration["simulation_tick"] == 1
    assert match.events.filter(event_type="COMBAT_TICK").count() == 1



def test_live_commands_racing_tick_preserve_entities_coins_and_deadline():
    from datetime import datetime

    from apps.combat.continuous_service import ContinuousCombatService
    from apps.units.services import ConstructionService
    from tests.test_continuous_combat import room

    match,teams,_,_=room(prep=2,battle=20)
    UnitService.deploy_unit(match,teams[0],"infantry",str(teams[1].pk))
    match=MatchService.advance_phase(match)
    deadline=match.configuration["timer_state"]["phase_ends_at"]
    tick_at=datetime.fromisoformat(match.configuration["timer_state"]["next_tick_at"])
    def command(index):
        if index==0:
            return ContinuousCombatService.tick(match.pk,tick_at)
        if index in (1,2):
            return str(UnitService.deploy_unit(match,teams[0],"infantry",str(teams[1].pk),idempotency_key="battle-deploy")[1].pk)
        return str(ConstructionService.build_tower(match,teams[1],"mg_tower","node_tower_t2_slot1",idempotency_key="battle-build")[1].pk)
    outcomes=concurrent(command,count=5)
    assert outcomes[0] is True and outcomes[1]==outcomes[2] and outcomes[3]==outcomes[4]
    match.refresh_from_db()
    for team in teams:
        team.refresh_from_db()
    assert teams[0].coins==470 and teams[1].coins==475
    assert match.entities.count()==3 and match.configuration["next_formation_order"]==3
    assert match.configuration["timer_state"]["phase_ends_at"]==deadline
    ContinuousCombatService.tick(match.pk,datetime.fromisoformat(match.configuration["timer_state"]["next_tick_at"]))
    assert match.entities.get(pk=outcomes[1]).simulation_state["route_distance"]>-83


def test_simultaneous_batch_retry_creates_ten_and_one_debit():
    match, teams, _, _ = room(initial_coins=500)
    results = concurrent(lambda _: UnitService.deploy_units(
        match, teams[0], "infantry", str(teams[1].pk), quantity=10, idempotency_key="batch-ten"))
    assert len({tuple(e.pk for e in entities) for _, entities in results}) == 1
    assert GameEntity.objects.filter(team=teams[0]).count() == 10
    assert CoinTransaction.objects.filter(team=teams[0], transaction_type="DEPLOY_UNIT").count() == 1
    teams[0].refresh_from_db()
    assert teams[0].coins == 350


def test_concurrent_batch_requests_cannot_overspend_shared_wallet():
    from django.core.exceptions import ValidationError
    match, teams, _, _ = room(initial_coins=150)
    def deploy(index):
        try:
            return UnitService.deploy_units(match, teams[0], "infantry", str(teams[1].pk),
                quantity=5, idempotency_key=f"batch-budget-{index % 10}")[0].pk
        except ValidationError as error:
            assert error.code == "INSUFFICIENT_COINS"
            return None
    results = concurrent(deploy, count=20)
    assert len({pk for pk in results if pk}) == 2
    teams[0].refresh_from_db()
    assert teams[0].coins == 0 and GameEntity.objects.filter(team=teams[0]).count() == 10
    assert CoinTransaction.objects.filter(team=teams[0], transaction_type="DEPLOY_UNIT").count() == 2


def test_concurrent_vehicle_batches_cannot_exceed_shared_capacity():
    from django.core.exceptions import ValidationError

    from apps.units.models import TeamUnlock, UnitType
    match, teams, _, _ = room(initial_coins=1000)
    TeamUnlock.objects.create(team=teams[0], unit_type=UnitType.objects.get(code="tank"))
    def deploy(index):
        try:
            return UnitService.deploy_units(match, teams[0], "tank", str(teams[1].pk),
                quantity=3, idempotency_key=f"tank-batch-{index}")[0].pk
        except ValidationError as error:
            assert error.code == "UNIT_LIMIT_REACHED"
            return None
    results = concurrent(deploy)
    assert len([pk for pk in results if pk]) == 1
    assert GameEntity.objects.filter(team=teams[0]).count() == 3
    teams[0].refresh_from_db()
    assert teams[0].coins == 895


def test_twenty_teams_deploy_concurrent_batches_during_battle():
    from datetime import datetime

    from apps.combat.continuous_service import ContinuousCombatService
    match, teams, _, _ = room(count=20, initial_coins=1000)
    match = MatchService.advance_phase(match)
    results = concurrent(lambda i: UnitService.deploy_units(
        match, teams[i], "infantry", teams[(i + 1) % 20].pk, quantity=10,
        idempotency_key=f"team-batch-{i}"), count=20)
    assert sum(len(entities) for _, entities in results) == 200
    assert GameEntity.objects.filter(match=match).count() == 200
    assert match.events.filter(event_type="ENTITIES_CREATED").count() == 20
    assert all(t.coins == 850 for t in match.teams.all())
    match.refresh_from_db()
    ContinuousCombatService.tick(match.pk, datetime.fromisoformat(match.configuration["timer_state"]["next_tick_at"]))
    assert all(e.simulation_state["route_distance"] > 0 for e in match.entities.all())
