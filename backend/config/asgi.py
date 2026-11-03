import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

# Khởi tạo Django ASGI application sớm để đảm bảo các app model được nạp
django_asgi_app = get_asgi_application()

from apps.matches.scheduler import ScheduledMatchApplication
from apps.realtime.middleware import TokenAuthMiddlewareStack
from apps.realtime.routing import websocket_urlpatterns

application = ScheduledMatchApplication(ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": TokenAuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
))
