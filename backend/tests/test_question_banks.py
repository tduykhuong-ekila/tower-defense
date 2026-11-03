from datetime import timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework.test import APIClient

from apps.economy.models import CoinTransaction
from apps.matches.models import Match
from apps.matches.services import MatchService
from apps.questions.banks import create_match_with_bank
from apps.questions.excel import parse_workbook
from apps.questions.models import Question, QuestionBank, TeamQuestion
from apps.questions.services import QuestionService
from apps.realtime.services import RealtimeService, scope_live_event
from apps.rewards.models import RewardClaim
from apps.rewards.services import RewardService
from apps.units.models import TeamUnlock, UnitType
from apps.units.seeds import ensure_standard_units
from apps.units.services import UnitService

pytestmark = pytest.mark.django_db
SAMPLE = Path(__file__).parent / "fixtures" / "De_Thi_Quiz_Demo.xlsx"
TOKEN = "test-question-bank-owner-token-1234567890"


@pytest.fixture(autouse=True)
def clear_throttle():
    cache.clear()


def workbook_bytes(change=None):
    if change is None:
        return SAMPLE.read_bytes()
    workbook = load_workbook(SAMPLE)
    change(workbook)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def upload(data=None, token=TOKEN, filename="questions.xlsx"):
    return APIClient().post("/api/v1/question-banks/upload/", {
        "file": SimpleUploadedFile(filename, data if data is not None else workbook_bytes()),
    }, format="multipart", HTTP_X_QUESTION_BANK_TOKEN=token)


def active_room(count=2, token=TOKEN):
    ensure_standard_units()
    response = upload(token=token)
    assert response.status_code == 201, response.data
    match, host = create_match_with_bank(bank_id=response.data["id"], token=token,
        name="Imported quiz", configuration={"max_teams": count, "gameplay_mode": "CONTINUOUS", "initial_coins": 500})
    teams, players = [], []
    for index in range(count):
        team = MatchService.create_team(match, f"Team {index + 1}")
        players.append(MatchService.join_match(match, f"Player {index + 1}", team_id=team.pk))
        MatchService.set_team_ready(team, True)
        teams.append(team)
    return MatchService.start_match(match), teams, players, host


def answer(match, team, correct=True):
    latest = TeamQuestion.objects.filter(match=match, team=team).order_by("-sequence_number").first()
    tq = QuestionService.get_or_assign_current_question(match, team, advance_from=latest.pk if latest else None)
    QuestionService.update_viewing(match, team, tq.pk, "test-viewer", "OPEN")
    return QuestionService.submit_answer(match, team, str(tq.pk), tq.question.answer_key if correct else "incorrect")


def test_real_sample_schema_and_normalization():
    parsed = parse_workbook(workbook_bytes(), SAMPLE.name)
    assert parsed["sheets"] == ["Quiz_Fresher_Junior_20_Cau"]
    assert len(parsed["questions"]) == 20
    assert parsed["invalid_questions"] == 0 and not parsed["errors"]
    q = parsed["questions"][0]
    assert q["answer_key"] == "B" and q["difficulty"] == "EASY" and q["category"] == "Web dev"
    assert q["import_metadata"]["row"] == 2
    assert {q["difficulty"] for q in parsed["questions"]} == {"EASY", "MEDIUM", "HARD"}


@pytest.mark.parametrize("cell,value,field", [
    ("G1", "Wrong header", "Đáp án"), ("G2", "Z", "Đáp án"),
    ("B2", None, "Câu hỏi"), ("C2", None, "A"), ("B2", "=1+1", "Câu hỏi"),
    ("D2", "=SUM(1,2)", "B"), ("B2", "x" * 4001, "Câu hỏi"),
    ("H2", "unknown", "Độ khó"), ("A2", True, "STT"),
])
def test_row_and_header_errors(cell, value, field):
    parsed = parse_workbook(workbook_bytes(lambda w: setattr(w.active[cell], "value", value)), "q.xlsx")
    assert any(e["field"] == field for e in parsed["errors"])
    assert len(parsed["questions"]) == (0 if cell.endswith("1") else 19)
    assert parsed["invalid_questions"] == (0 if cell.endswith("1") else 1)


def test_duplicates_blank_rows_multi_sheet_and_physical_order():
    def edit(w):
        first = w.active
        first.insert_rows(3)
        second = w.create_sheet("Second")
        second.append([c.value for c in first[1]])
        second.append([c.value for c in first[2]])
        second.append([2, "Another question?", "one", "two", "three", "four", "a", None, None])
    parsed = parse_workbook(workbook_bytes(edit), "q.xlsx")
    assert len(parsed["questions"]) == 21
    assert parsed["invalid_questions"] == 1
    assert parsed["errors"][0]["field"] == "Câu hỏi"
    assert parsed["questions"][1]["import_metadata"]["row"] == 4
    assert parsed["questions"][-1]["answer_key"] == "A"


def test_empty_sheet_is_ignored_but_nonempty_wrong_schema_is_error():
    data = workbook_bytes(lambda w: w.create_sheet("Empty"))
    assert not parse_workbook(data, "q.xlsx")["errors"]
    data = workbook_bytes(lambda w: w.create_sheet("Invalid").append(["wrong"]))
    assert any(e["sheet"] == "Invalid" for e in parse_workbook(data, "q.xlsx")["errors"])


@pytest.mark.parametrize("filename,data", [("x.xls", b"bad"), ("x.xlsx", b"bad"), ("x.xlsx", b"PK\x03\x04bad")])
def test_invalid_workbooks(filename, data):
    assert upload(data=data, filename=filename).status_code == 400
    assert not QuestionBank.objects.exists()


def test_size_expansion_and_question_limits(settings):
    settings.QUESTION_BANK_MAX_UPLOAD_BYTES = 100
    assert upload().status_code == 400
    settings.QUESTION_BANK_MAX_UPLOAD_BYTES = 5 * 1024 * 1024
    settings.QUESTION_BANK_MAX_EXPANDED_BYTES = 100
    assert upload().status_code == 400
    settings.QUESTION_BANK_MAX_EXPANDED_BYTES = 25 * 1024 * 1024
    settings.QUESTION_BANK_MAX_QUESTIONS = 10
    assert upload().status_code == 400


def test_merge_external_links_macros_and_entity_attacks_rejected():
    assert upload(workbook_bytes(lambda w: w.active.merge_cells("B2:C2"))).status_code == 400
    for part, content in [
        ("xl/_rels/test.xml.rels", b'<Relationships><Relationship TargetMode="External" Target="https://example.com"/></Relationships>'),
        ("xl/vbaProject.bin", b"macro"),
        ("xl/test.xml", b'<!DOCTYPE x [<!ENTITY a "bad">]><x>&a;</x>'),
    ]:
        data = BytesIO(workbook_bytes())
        with ZipFile(data, "a", ZIP_DEFLATED) as archive:
            archive.writestr(part, content)
        assert upload(data.getvalue()).status_code == 400
    assert not QuestionBank.objects.exists()


def test_upload_preview_ownership_pagination_dedup_and_removal():
    one, two = upload(), upload()
    assert one.data["id"] == two.data["id"]
    assert QuestionBank.objects.count() == 1 and Question.objects.count() == 20
    url = f'/api/v1/question-banks/{one.data["id"]}/preview/'
    client = APIClient()
    assert client.get(url).status_code == 403
    assert client.get(url, HTTP_X_QUESTION_BANK_TOKEN="different-token").status_code == 403
    second = client.get(url + "?page=2", HTTP_X_QUESTION_BANK_TOKEN=TOKEN)
    assert second.status_code == 200 and second.data["questions"][0]["import_order"] == 11
    assert second.data["questions"][0]["answer_key"] in "ABCD"
    assert upload(workbook_bytes(lambda w: setattr(w.active["B2"], "value", "Changed?"))).status_code == 400
    assert client.delete(url, HTTP_X_QUESTION_BANK_TOKEN=TOKEN).status_code == 204
    assert not Question.objects.exists()


def test_failed_import_rolls_back_bank_and_questions():
    with patch("apps.questions.banks.Question.objects.bulk_create", side_effect=RuntimeError("DB failure")):
        with pytest.raises(RuntimeError):
            upload()
    assert not QuestionBank.objects.exists() and not Question.objects.exists()


@pytest.mark.parametrize("max_teams", [4, 20])
def test_atomic_room_creation_retry_and_association(max_teams):
    bank = upload().data
    client = APIClient()
    body = {"name": "Uploaded room", "question_bank_id": bank["id"], "question_bank_token": TOKEN, "configuration": {"max_teams": max_teams}}
    result = client.post("/api/v1/matches/", body, format="json")
    again = client.post("/api/v1/matches/", body, format="json")
    assert result.status_code == again.status_code == 201
    assert result.data["id"] == again.data["id"] and result.data["host_token"] == again.data["host_token"]
    assert Match.objects.count() == 1 and result.data["question_bank_id"] == bank["id"]
    assert result.data["configuration"]["max_teams"] == max_teams
    assert "question_bank_token" not in str(client.get("/api/v1/matches/").data)
    url = f'/api/v1/question-banks/{bank["id"]}/preview/'
    assert client.delete(url, HTTP_X_QUESTION_BANK_TOKEN=TOKEN).status_code == 409


def test_invalid_foreign_expired_staging_and_creation_rollback():
    invalid = upload(workbook_bytes(lambda w: setattr(w.active["G2"], "value", "Z"))).data
    with pytest.raises(ValidationError):
        create_match_with_bank(bank_id=invalid["id"], token=TOKEN, name="x", configuration={})
    bank = upload(token="second-upload-token-long-enough-123456").data
    args = dict(bank_id=bank["id"], token="second-upload-token-long-enough-123456", name="x", configuration={})
    with pytest.raises(ValidationError):
        create_match_with_bank(**{**args, "token": TOKEN})
    original = MatchService.create_match
    def fail(**kwargs):
        original(**kwargs)
        raise ValidationError("creation failed")
    with patch.object(MatchService, "create_match", side_effect=fail):
        with pytest.raises(ValidationError):
            create_match_with_bank(**args)
    assert not Match.objects.exists()
    QuestionBank.objects.update(created_at=timezone.now() - timedelta(days=2))
    with pytest.raises(ValidationError):
        create_match_with_bank(**args)
    call_command("cleanup_question_uploads")
    assert not QuestionBank.objects.exists()


def test_room_creation_without_upload_remains_compatible_and_idempotent():
    client = APIClient()
    body = {"name": "Legacy room", "creation_token": TOKEN}
    first = client.post("/api/v1/matches/", body, format="json")
    second = client.post("/api/v1/matches/", body, format="json")
    assert first.status_code == 201 and first.data["id"] == second.data["id"]
    assert first.data["host_token"] == second.data["host_token"]


@pytest.mark.parametrize("count", [2, 4, 8, 20])
def test_independent_teams_order_and_private_api(count):
    match, teams, players, host = active_room(count)
    first_ids = []
    for team, (member, token) in zip(teams, players):
        client = APIClient()
        client.credentials(HTTP_X_PARTICIPANT_TOKEN=token)
        response = client.get(f"/api/v1/matches/{match.pk}/questions/current/")
        assert response.status_code == 200
        assert "answer_key" not in str(response.data) and "explanation" not in response.data["question"]
        first_ids.append(response.data["question"]["id"])
        assert client.get("/api/v1/questions/").status_code == 403
        assert client.get(f"/api/v1/questions/{first_ids[-1]}/").status_code == 403
        tq = answer(match, team)
        assert tq.question.import_order == 1 and tq.status == "PENDING_REWARD"
    assert len(set(first_ids)) == 1
    assert TeamQuestion.objects.count() == count and not RewardClaim.objects.exists()


def test_continuous_phases_wrong_final_answer_full_bank_exhaustion_and_rewards():
    match, teams, players, _ = active_room()
    tq = QuestionService.get_or_assign_current_question(match, teams[0])
    match = MatchService.advance_phase(match)
    tq.refresh_from_db()
    assert tq.status == "PENDING_QUESTION"
    _, unit = UnitService.deploy_unit(match, teams[0], "infantry", str(teams[1].pk))
    QuestionService.update_viewing(match, teams[0], tq.pk, "test-viewer", "OPEN")
    correct = QuestionService.submit_answer(match, teams[0], str(tq.pk), tq.question.answer_key)
    teams[0].refresh_from_db()
    before = teams[0].coins
    assert correct.status == "PENDING_REWARD"
    QuestionService.update_viewing(match, teams[0], tq.pk, "test-viewer", "OPEN")
    duplicate = QuestionService.submit_answer(match, teams[0], str(tq.pk), "wrong")
    assert duplicate.status == "PENDING_REWARD" and duplicate.submitted_answer == tq.question.answer_key
    claim = RewardService.claim_reward(match, teams[0], str(tq.pk), "COIN")
    assert RewardService.claim_reward(match, teams[0], str(tq.pk), "UNLOCK", "tank").pk == claim.pk
    teams[0].refresh_from_db()
    assert teams[0].coins == before + correct.reward_coin_amount
    assert CoinTransaction.objects.filter(reference_id=str(tq.pk), transaction_type="REWARD_COIN").count() == 1
    incorrect = answer(match, teams[0], False)
    assert incorrect.status == "ANSWER_INCORRECT" and not RewardClaim.objects.filter(team_question=incorrect).exists()
    match = MatchService.advance_phase(match)
    assert match.configuration["current_round"] == 2
    for expected_order in range(3, 21):
        tq = answer(match, teams[0], False)
        assert tq.question.import_order == expected_order
    progress = QuestionService.progress(match, teams[0])
    assert progress == {"answered": 20, "correct": 1, "total": 20, "remaining": 0, "exhausted": True, "pending_reward_id": None}
    assert QuestionService.get_or_assign_current_question(match, teams[0], advance_from=tq.pk) is None
    assert QuestionService.progress(match, teams[1])["answered"] == 0
    assert UnitService.deploy_unit(match, teams[0], "infantry", str(teams[1].pk))[1].pk != unit.pk


def test_unlock_is_free_still_paid_to_deploy_and_exhausted_unlocks():
    match, teams, _, _ = active_room()
    tq = answer(match, teams[0])
    teams[0].refresh_from_db()
    before = teams[0].coins
    claim = RewardService.claim_reward(match, teams[0], str(tq.pk), "UNLOCK", "tank")
    teams[0].refresh_from_db()
    assert teams[0].coins == before and claim.coin_amount == 0
    assert TeamUnlock.objects.filter(team=teams[0], unit_type__code="tank").count() == 1
    UnitService.deploy_unit(match, teams[0], "tank", str(teams[1].pk))
    teams[0].refresh_from_db()
    assert teams[0].coins == before - UnitType.objects.get(code="tank").cost
    next_tq = answer(match, teams[0])
    with pytest.raises(ValidationError):
        RewardService.claim_reward(match, teams[0], str(next_tq.pk), "UNLOCK", "tank")
    for unit in UnitType.objects.filter(is_unlockable=True, is_active=True):
        TeamUnlock.objects.get_or_create(team=teams[0], unit_type=unit)
    options = RewardService.get_reward_options(next_tq)
    assert not options["unlock_available"] and options["coin_amount"] is None
    assert RewardService.claim_reward(match, teams[0], str(next_tq.pk), "COIN").coin_amount == next_tq.reward_coin_amount


def test_foreign_room_team_membership_spectator_finished_and_reconnect():
    a, teams, players, _ = active_room()
    b, other_teams, _, _ = active_room(token="other-question-bank-token-1234567890")
    tq = answer(a, teams[0])
    with pytest.raises(ValidationError):
        QuestionService.submit_answer(b, other_teams[0], str(tq.pk), "B")
    with pytest.raises(ValidationError):
        RewardService.claim_reward(a, teams[1], str(tq.pk), "COIN")
    from apps.teams.models import TeamMember
    spectator = TeamMember.objects.create(match=a, team=teams[0], display_name="spectator", role="SPECTATOR")
    with pytest.raises(ValidationError):
        QuestionService.submit_answer(a, teams[0], str(tq.pk), "B", member=spectator)
    snapshot = RealtimeService.build_snapshot(a, str(teams[0].pk))["payload"]
    assert snapshot["viewer"]["current_question"]["id"] == str(tq.pk)
    assert snapshot["viewer"]["pending_reward"]["coin_amount"] is None
    assert snapshot["viewer"]["question_progress"]["answered"] == 1
    assert "answer_key" not in str(snapshot)
    event = a.events.get(event_type="QUESTION_ANSWERED_CORRECT")
    envelope = {"event_type": event.event_type, "payload": event.payload}
    assert scope_live_event(envelope, str(teams[1].pk), False)["payload"] == {}
    assert scope_live_event(envelope, str(teams[0].pk), False)["payload"]["question_state"]["status"] == "PENDING_REWARD"
    assert "answer_key" not in str(event.payload)
    a = MatchService.end_match(a)
    with pytest.raises(ValidationError):
        QuestionService.submit_answer(a, teams[0], str(tq.pk), "B")
    with pytest.raises(ValidationError):
        RewardService.claim_reward(a, teams[0], str(tq.pk), "COIN")


def test_legacy_global_bank_never_selects_imported_questions():
    upload()
    match, _ = MatchService.create_match(configuration={"gameplay_mode": "CONTINUOUS"})
    assert QuestionService.question_total(match) == 0
    Question.objects.create(content="Legacy only", answer_key="yes")
    assert QuestionService.question_total(match) == 1


@pytest.mark.django_db(transaction=True)
def test_websocket_duplicate_answer_returns_claimed_state_without_new_reward_options():
    from asgiref.sync import async_to_sync

    from apps.realtime.consumers import MatchConsumer

    match, teams, players, _ = active_room()
    tq = answer(match, teams[0])
    RewardService.claim_reward(match, teams[0], str(tq.pk), "COIN")
    consumer = MatchConsumer()
    consumer.match_id = str(match.pk)
    consumer.team_id = str(teams[0].pk)
    consumer.team_member = players[0][0]
    result = async_to_sync(consumer.handle_submit_answer)({"team_question_id": str(tq.pk), "answer": "wrong"})
    assert result["status"] == "REWARD_CLAIMED"
    assert result["reward_options"] is None and result["question_state"]["reward_options"] is None
    assert result["question_progress"]["answered"] == 1
    assert RewardClaim.objects.count() == 1
