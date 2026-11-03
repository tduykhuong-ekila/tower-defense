from django.urls import re_path

from apps.realtime.consumers import MatchConsumer

websocket_urlpatterns = [
    re_path(r"^ws/matches/(?P<match_id>[0-9a-fA-F-]+)/?$", MatchConsumer.as_asgi()),
]
