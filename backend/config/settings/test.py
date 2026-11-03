from .base import *  # noqa: F403

DEBUG = False
MATCH_SCHEDULER_ENABLED = False

# Sử dụng shared in-memory SQLite khi chạy test để hỗ trợ đa luồng (multi-threaded tests)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "file:test_mem?mode=memory&cache=shared",
        "OPTIONS": {
            "uri": True,
            "timeout": 20,
        },
        "TEST": {
            "NAME": "file:test_mem?mode=memory&cache=shared",
            "OPTIONS": {
                "uri": True,
                "timeout": 20,
            },
        },
    }
}

# Sử dụng InMemoryChannelLayer cho test
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

# Tăng tốc độ hash mật khẩu trong test
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]
