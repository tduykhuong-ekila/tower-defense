import uuid

from django.db import models


class MatchResult(models.Model):
    """
    Immutable snapshot of a team's final performance in a match (§19.13, §12).
    Created once when the match is finalized by ScoringService.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    match = models.ForeignKey(
        "matches.Match",
        on_delete=models.CASCADE,
        related_name="results",
    )
    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.CASCADE,
        related_name="results",
    )
    final_rank = models.IntegerField(db_index=True)
    final_score = models.IntegerField(default=0)
    bases_destroyed = models.IntegerField(default=0)
    base_damage_dealt = models.IntegerField(default=0)
    correct_answers = models.IntegerField(default=0)
    remaining_base_hp = models.IntegerField(default=0)
    remaining_coins = models.IntegerField(default=0)
    surviving_towers = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["final_rank", "-final_score"]
        verbose_name = "Match Result"
        verbose_name_plural = "Match Results"
        constraints = [
            models.UniqueConstraint(
                fields=["match", "team"],
                name="unique_match_team_result",
            ),
        ]

    def __str__(self):
        return f"MatchResult: Match {self.match_id} - Team {self.team_id} (Rank #{self.final_rank}, Score {self.final_score})"
