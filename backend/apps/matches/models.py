import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.matches.defaults import get_default_configuration


class MatchStatus(models.TextChoices):
    LOBBY = "LOBBY", "Lobby"
    ACTIVE = "ACTIVE", "Active"
    PAUSED = "PAUSED", "Paused"
    FINISHED = "FINISHED", "Finished"


class MatchPhase(models.TextChoices):
    LOBBY = "LOBBY", "Lobby"
    PREPARATION = "PREPARATION", "Preparation"
    BUILD_AND_SCOUT = "BUILD_AND_SCOUT", "Build and Scout"
    WAR = "WAR", "War"
    FINAL_ASSAULT = "FINAL_ASSAULT", "Final Assault"
    RESULTS = "RESULTS", "Results"


class Match(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question_bank = models.ForeignKey("questions.QuestionBank", null=True, blank=True, on_delete=models.PROTECT, related_name="matches")
    creation_token_hash = models.CharField(max_length=64, unique=True, null=True, blank=True)
    room_code = models.CharField(max_length=8, db_index=True)
    name = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20,
        choices=MatchStatus.choices,
        default=MatchStatus.LOBBY,
        db_index=True,
    )
    phase = models.CharField(
        max_length=30,
        choices=MatchPhase.choices,
        default=MatchPhase.LOBBY,
        db_index=True,
    )
    configuration = models.JSONField(default=get_default_configuration)
    host_token_hash = models.CharField(max_length=128, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_matches",
    )
    is_locked = models.BooleanField(
        default=False,
        help_text="If locked, no new participants can join this match.",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "matches"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["room_code"],
                condition=Q(status__in=[MatchStatus.LOBBY, MatchStatus.ACTIVE, MatchStatus.PAUSED]),
                name="unique_active_room_code",
            ),
        ]

    def __str__(self):
        return f"{self.name} [{self.room_code}] ({self.status}/{self.phase})"


class MatchEvent(models.Model):
    """
    Log of lifecycle transitions and game events with monotonic sequence numbers.
    Required for lifecycle tracking (Phase 1) and synchronization (Phase 5).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="events")
    sequence_number = models.BigIntegerField()
    event_type = models.CharField(max_length=50, db_index=True)
    payload = models.JSONField(default=dict)
    broadcasted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["match", "sequence_number"],
                name="unique_match_event_sequence",
            ),
        ]

    def __str__(self):
        return f"Match {self.match_id} Event #{self.sequence_number}: {self.event_type}"
