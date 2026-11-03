"""Real row-lock integration checks against a disposable PostgreSQL test database.

Provide DATABASE_URL for the local PostgreSQL instance. pytest-django creates and
drops test_tower_defense_combat; it does not migrate or flush the source database.
"""

from .test import *  # noqa: F403

DATABASES = {"default": env.db("DATABASE_URL")}  # noqa: F405
DATABASES["default"]["TEST"] = {"NAME": "test_tower_defense_combat"}
# Test clusters initialized with C locale can otherwise inherit SQL_ASCII,
# which cannot store the Vietnamese JSON catalog seeded by migrations.
DATABASES["default"]["TEST"].update({"CHARSET": "UTF8", "TEMPLATE": "template0"})
