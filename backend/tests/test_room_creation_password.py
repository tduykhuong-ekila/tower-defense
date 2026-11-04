import pytest
from rest_framework.test import APIClient

from apps.matches.models import Match

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("password", [None, "", "wrong", "admin123@", " Admin123@", 123, [], {}])
def test_missing_or_incorrect_password_cannot_create_room(password):
    body = {"name": "Protected room"}
    if password is not None:
        body["admin_password"] = password
    response = APIClient().post("/api/v1/matches/", body, format="json")
    assert response.status_code == 403
    assert response.data["error"] == "Mật khẩu quản trị viên không đúng."
    assert not Match.objects.exists()


def test_correct_password_creates_room_without_exposing_or_saving_password():
    response = APIClient().post("/api/v1/matches/", {
        "name": "Protected room", "admin_password": "Admin123@",
    }, format="json")
    assert response.status_code == 201
    assert response.data["host_token"]
    assert "Admin123@" not in str(response.data)
    assert "Admin123@" not in str(Match.objects.get().configuration)


def test_server_password_can_be_configured(settings):
    settings.ROOM_CREATION_PASSWORD = "AnotherPassword@"
    client = APIClient()
    assert client.post("/api/v1/matches/", {"admin_password": "Admin123@"}, format="json").status_code == 403
    assert client.post("/api/v1/matches/", {"admin_password": "AnotherPassword@"}, format="json").status_code == 201
