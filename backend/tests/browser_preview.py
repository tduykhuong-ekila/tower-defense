"""Disposable backend for frontend browser checks; no existing database is touched.

Run from backend: .venv/bin/python tests/browser_preview.py
"""
import logging
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.test'

import django  # noqa: E402
from django.conf import settings  # noqa: E402
from django.core.management import call_command  # noqa: E402


def main():
    with TemporaryDirectory(prefix='tower-browser-') as directory:
        settings.DATABASES['default']['NAME'] = str(Path(directory) / 'test.sqlite3')
        settings.DATABASES['default']['OPTIONS']['transaction_mode'] = 'IMMEDIATE'
        logging.basicConfig(level=logging.WARNING)
        settings.ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']
        settings.MATCH_SCHEDULER_ENABLED = os.environ.get('TEST_SCHEDULER') == '1'
        django.setup()
        call_command('migrate', verbosity=0)
        if settings.MATCH_SCHEDULER_ENABLED:
            from apps.questions.models import Question
            Question.objects.create(type='SHORT_TEXT', content='Battle test: 2 + 2?', answer_key='4', time_limit_seconds=120)
            Question.objects.create(type='SHORT_TEXT', content='Battle test: 3 + 3?', answer_key='6', time_limit_seconds=120)
        if os.environ.get('TEST_QUIZ_SESSIONS') == '1':
            from apps.questions.models import Question
            for index in range(2):
                Question.objects.create(type='SHORT_TEXT', content=f'Battle test: 2 + 2? (bonus {index})', answer_key='4', time_limit_seconds=120)
        if os.environ.get('TEST_QUESTION_SECONDS'):
            from apps.questions.models import Question
            Question.objects.update(time_limit_seconds=int(os.environ['TEST_QUESTION_SECONDS']))
        port = os.environ.get('TEST_BACKEND_PORT', '8011')
        call_command('runserver', f'127.0.0.1:{port}', use_reloader=False, verbosity=0)


if __name__ == "__main__":
    main()
