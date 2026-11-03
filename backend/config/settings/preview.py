"""Persistent, single-process local preview; independent of the normal database."""

from .base import *  # noqa: F403

PREVIEW_DIRECTORY = BASE_DIR / ".local"  # noqa: F405
PREVIEW_DIRECTORY.mkdir(parents=True, exist_ok=True)

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(PREVIEW_DIRECTORY / "arena-preview.sqlite3"),
        "OPTIONS": {"timeout": 20, "transaction_mode": "IMMEDIATE"},
    }
}
CHANNEL_LAYERS = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
}
