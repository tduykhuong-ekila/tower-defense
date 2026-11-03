import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class TeamStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    ELIMINATED = "ELIMINATED", "Eliminated"


class MemberRole(models.TextChoices):
    MENTOR = "MENTOR", "Mentor"
    MENTEE = "MENTEE", "Mentee"
    HOST = "HOST", "Host"
    SPECTATOR = "SPECTATOR", "Spectator"


class Team(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    match = models.ForeignKey(
        "matches.Match",
        on_delete=models.CASCADE,
        related_name="teams",
    )
    name = models.CharField(max_length=50)
    initial_base_hp = models.IntegerField(default=500)
    base_hp = models.IntegerField(default=500)
    base_shield = models.IntegerField(default=0)
    coins = models.IntegerField(default=100)
    score = models.IntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=TeamStatus.choices,
        default=TeamStatus.ACTIVE,
    )
    is_ready = models.BooleanField(
        default=False,
        help_text="Flag indicating team readiness during Lobby phase.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(base_hp__gte=0),
                name="team_base_hp_gte_0",
            ),
            models.CheckConstraint(
                condition=Q(coins__gte=0),
                name="team_coins_gte_0",
            ),
            models.CheckConstraint(
                condition=Q(base_shield__gte=0),
                name="team_base_shield_gte_0",
            ),
            models.UniqueConstraint(
                fields=["match", "name"],
                name="unique_team_name_per_match",
            ),
        ]

    def __str__(self):
        return f"{self.name} (HP: {self.base_hp}, Coins: {self.coins}, Status: {self.status})"


class TeamMember(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    match = models.ForeignKey(
        "matches.Match",
        on_delete=models.CASCADE,
        related_name="members",
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="team_memberships",
    )
    display_name = models.CharField(max_length=50)
    role = models.CharField(
        max_length=20,
        choices=MemberRole.choices,
        default=MemberRole.MENTEE,
    )
    is_ready = models.BooleanField(default=False)
    token_hash = models.CharField(max_length=128, db_index=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["joined_at"]
        constraints = [
            # Each team can have at most one Mentor
            models.UniqueConstraint(
                fields=["team"],
                condition=Q(role=MemberRole.MENTOR, team__isnull=False),
                name="unique_mentor_per_team",
            ),
        ]

    def clean(self):
        super().clean()
        if self.role == MemberRole.MENTOR and self.team_id:
            existing_mentor = TeamMember.objects.filter(
                team_id=self.team_id,
                role=MemberRole.MENTOR,
            ).exclude(pk=self.pk)
            if existing_mentor.exists():
                raise ValidationError("Mỗi đội tối đa 1 Mentor.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        team_name = self.team.name if self.team else "Unassigned"
        return f"{self.display_name} [{self.role}] - Team: {team_name}"
