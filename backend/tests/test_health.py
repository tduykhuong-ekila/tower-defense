import pytest
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.test import Client


@pytest.mark.django_db
def test_health_check_endpoint():
    """Kiểm tra GET /api/v1/health/ trả về 200 và trạng thái healthy."""
    client = Client()
    response = client.get("/api/v1/health/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == "1.0.0"
    assert data["components"]["database"] == "connected"
    assert data["components"]["channel_layer"] == "connected"


def test_channel_layer_direct_ping():
    """Kiểm tra gửi và nhận message qua Channel Layer."""
    channel_layer = get_channel_layer()
    assert channel_layer is not None

    test_channel = "test_ping_channel"
    async_to_sync(channel_layer.send)(test_channel, {"type": "ping", "data": "tower_defense_ok"})
    message = async_to_sync(channel_layer.receive)(test_channel)
    assert message is not None
    assert message.get("data") == "tower_defense_ok"
