from unittest.mock import patch

import pytest
from django.db import connection

from apps.matches.models import Match
from apps.questions.banks import create_match_with_bank
from apps.questions.models import TeamQuestion
from apps.questions.services import QuestionService
from apps.rewards.models import RewardClaim
from apps.rewards.services import RewardService
from apps.teams.models import TeamMember
from tests.test_question_banks import TOKEN, active_room, upload
from tests.test_round_concurrency import concurrent

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.skipif(connection.vendor != "postgresql", reason="Requires PostgreSQL row locks")]


def test_simultaneous_room_creation_attaches_once():
    bank = upload().data
    results = concurrent(lambda _: create_match_with_bank(bank_id=bank["id"], token=TOKEN, name="Concurrent", configuration={}))
    assert len({match.pk for match, token in results}) == 1
    assert len({token for match, token in results}) == 1
    assert Match.objects.count() == 1


def test_teammates_assign_answer_and_choose_mutually_exclusive_reward():
    match, teams, players, _ = active_room()
    second_member = TeamMember.objects.create(match=match, team=teams[0], role="MENTEE", display_name="Second teammate")
    actors = [players[0][0], second_member]
    assignments = concurrent(lambda _: QuestionService.get_or_assign_current_question(match, teams[0]))
    assert len({tq.pk for tq in assignments}) == 1
    tq = assignments[0]
    views = concurrent(lambda i: QuestionService.update_viewing(match, teams[0], tq.pk, f"viewer-{i}", "OPEN", actors[i % 2]))
    assert all(q.timer_status == "RUNNING" for q in views)
    with patch("apps.questions.services.draw_coin_reward", return_value=60) as draw:
        answers = concurrent(lambda i: QuestionService.submit_answer(match, teams[0], str(tq.pk), tq.question.answer_key, member=actors[i % 2]))
        draw.assert_called_once_with()
    assert all(q.status == "PENDING_REWARD" for q in answers)
    assert all(q.reward_coin_amount == 60 for q in answers)
    assert TeamQuestion.objects.filter(team=teams[0]).count() == 1
    claims = concurrent(lambda i: RewardService.claim_reward(match, teams[0], str(tq.pk), "COIN" if i % 2 else "UNLOCK", "tank", member=actors[i % 2]))
    assert len({claim.pk for claim in claims}) == 1
    assert RewardClaim.objects.count() == 1
    teams[0].refresh_from_db()
    tq.refresh_from_db()
    assert teams[0].coins == 500 + (tq.reward_coin_amount if claims[0].reward_type == "COIN" else 0)


def test_concurrent_viewers_close_and_next_have_one_timer_and_question():
    match, teams, players, _ = active_room()
    tq = QuestionService.get_or_assign_current_question(match, teams[0])
    opens = concurrent(lambda i: QuestionService.update_viewing(match, teams[0], tq.pk, f"v-{i}", "OPEN"))
    tq.refresh_from_db()
    assert len({q.expires_at for q in opens}) == 1
    assert tq.viewing_leases == {}
    assert tq.remaining_ms <= tq.question.time_limit_seconds * 1000
    closed = QuestionService.update_viewing(match, teams[0], tq.pk, "v-0", "CLOSE")
    assert closed.timer_status == "RUNNING"
    QuestionService.submit_answer(match, teams[0], tq.pk, "wrong")
    next_questions = concurrent(lambda _: QuestionService.get_or_assign_current_question(match, teams[0], advance_from=tq.pk))
    assert len({q.pk for q in next_questions}) == 1
    assert next_questions[0].sequence_number == 2
    assert TeamQuestion.objects.filter(team=teams[0]).count() == 2
