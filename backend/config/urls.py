from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path


def health_check(request):
    """
    Health check endpoint kiểm tra:
    - Server status
    - Database connectivity
    - Channel layer (Redis/Memory) connectivity
    """
    db_ok = False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            row = cursor.fetchone()
            if row and row[0] == 1:
                db_ok = True
    except Exception:
        db_ok = False

    channel_layer_ok = False
    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            # Gửi và nhận thử một message ping
            test_channel = "health_check_channel"
            async_to_sync(channel_layer.send)(test_channel, {"type": "ping", "data": "pong"})
            msg = async_to_sync(channel_layer.receive)(test_channel)
            if msg and msg.get("data") == "pong":
                channel_layer_ok = True
    except Exception:
        channel_layer_ok = False

    is_healthy = db_ok
    status_code = 200 if is_healthy else 503

    return JsonResponse(
        {
            "status": "healthy" if is_healthy else "unhealthy",
            "version": "1.0.0",
            "components": {
                "database": "connected" if db_ok else "unavailable",
                "channel_layer": "connected" if channel_layer_ok else "unavailable",
            },
        },
        status=status_code,
    )


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/health/", health_check, name="health_check"),
    path("api/v1/", include("apps.matches.urls")),
]
