from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    SECRET_KEY=(str, "insecure-key-for-dev"),
    ALLOWED_HOSTS=(list, ["*"]),
    DATABASE_URL=(str, f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
    REDIS_URL=(str, "redis://localhost:6385/0"),
    CORS_ALLOW_ALL_ORIGINS=(bool, True),
)

# Đọc file .env nếu tồn tại
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(env_file)

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# Cài đặt Daphne trước staticfiles cho ASGI
INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "corsheaders",
    "channels",
    # Local apps
    "apps.accounts",
    "apps.matches",
    "apps.teams",
    "apps.questions",
    "apps.rewards",
    "apps.economy",
    "apps.units",
    "apps.combat",
    "apps.realtime",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database
DATABASES = {
    "default": env.db("DATABASE_URL"),
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Ho_Chi_Minh"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Bound both the uploaded ZIP and its expanded XML before the XLSX reader sees it.
QUESTION_BANK_MAX_UPLOAD_BYTES = env.int("QUESTION_BANK_MAX_UPLOAD_BYTES", default=5 * 1024 * 1024)
QUESTION_BANK_MAX_EXPANDED_BYTES = env.int("QUESTION_BANK_MAX_EXPANDED_BYTES", default=25 * 1024 * 1024)
QUESTION_BANK_MAX_QUESTIONS = env.int("QUESTION_BANK_MAX_QUESTIONS", default=1000)
QUESTION_BANK_STAGING_HOURS = env.int("QUESTION_BANK_STAGING_HOURS", default=24)

# Django REST Framework
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}

# Channels Channel Layer
REDIS_URL = env("REDIS_URL")
if REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                # redis-py 8 defaults reads to 5s, equal to Channels' 5s
                # blocking receive. Give the server time to return its idle poll
                # instead of disconnecting healthy WebSockets every few seconds.
                "hosts": [{"address": REDIS_URL, "socket_timeout": 10,
                           "socket_connect_timeout": 5}],
            },
        },
    }
else:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        },
    }

# CORS
CORS_ALLOW_ALL_ORIGINS = env("CORS_ALLOW_ALL_ORIGINS")
