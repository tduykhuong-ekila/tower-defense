"""Disposable, single-process browser QA; never uses the normal game database."""

import tempfile
from pathlib import Path

from .test import *  # noqa: F403

QA_DIRECTORY = Path(tempfile.gettempdir()) / "tower-defense-unlimited-qa"
QA_DIRECTORY.mkdir(parents=True, exist_ok=True)
DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(QA_DIRECTORY / "browser.sqlite3"),
        "OPTIONS": {"transaction_mode": "IMMEDIATE", "timeout": 20},
    }
}
