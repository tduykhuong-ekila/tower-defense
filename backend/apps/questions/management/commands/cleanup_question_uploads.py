from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.questions.models import QuestionBank


class Command(BaseCommand):
    help = "Delete expired unassociated question uploads and their normalized questions."

    def handle(self, **options):
        cutoff = timezone.now() - timedelta(hours=settings.QUESTION_BANK_STAGING_HOURS)
        removed = 0
        # Lock in the same order as room creation, then recheck attachment under the lock.
        for bank_id in QuestionBank.objects.filter(created_at__lt=cutoff, matches__isnull=True).values_list("pk", flat=True).iterator(chunk_size=200):
            with transaction.atomic():
                bank = QuestionBank.objects.select_for_update().filter(pk=bank_id).first()
                if bank and not bank.matches.exists():
                    bank.delete()
                    removed += 1
        self.stdout.write(f"Removed {removed} expired question uploads.")
