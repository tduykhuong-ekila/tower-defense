import uuid

from django.conf import settings
from django.db import models


class QuestionBank(models.Model):
    """Immutable validated import; possession of its upload token owns the staging record."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    token_hash = models.CharField(max_length=64, unique=True)
    source_filename = models.CharField(max_length=255)
    content_sha256 = models.CharField(max_length=64)
    question_count = models.PositiveIntegerField(default=0)
    invalid_questions = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list)
    sheets = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)


class QuestionType(models.TextChoices):
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE", "Multiple Choice"
    SHORT_TEXT = "SHORT_TEXT", "Short Text"
    PUZZLE = "PUZZLE", "Logic Puzzle"
    MEMORY = "MEMORY", "Memory Challenge"
    DECODE = "DECODE", "Code / Text Decode"


class QuestionDifficulty(models.TextChoices):
    EASY = "EASY", "Easy"
    MEDIUM = "MEDIUM", "Medium"
    HARD = "HARD", "Hard"


class QuestionStatus(models.TextChoices):
    PENDING_QUESTION = "PENDING_QUESTION", "Pending Question"
    ANSWER_SUBMITTED = "ANSWER_SUBMITTED", "Answer Submitted"
    ANSWER_CORRECT = "ANSWER_CORRECT", "Answer Correct"
    ANSWER_INCORRECT = "ANSWER_INCORRECT", "Answer Incorrect"
    PENDING_REWARD = "PENDING_REWARD", "Pending Reward"
    REWARD_CLAIMED = "REWARD_CLAIMED", "Reward Claimed"
    EXPIRED = "EXPIRED", "Expired"


class Question(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question_bank = models.ForeignKey(QuestionBank, null=True, blank=True, on_delete=models.CASCADE, related_name="questions")
    import_order = models.PositiveIntegerField(null=True, blank=True)
    import_metadata = models.JSONField(default=dict, blank=True)
    type = models.CharField(
        max_length=30,
        choices=QuestionType.choices,
        default=QuestionType.MULTIPLE_CHOICE,
    )
    category = models.CharField(max_length=50, default="General", db_index=True)
    difficulty = models.CharField(
        max_length=20,
        choices=QuestionDifficulty.choices,
        default=QuestionDifficulty.MEDIUM,
        db_index=True,
    )
    content = models.TextField()
    options = models.JSONField(
        default=list,
        blank=True,
        help_text="List of choices for multiple choice questions, e.g. [{'key': 'A', 'text': '...'}, ...]",
    )
    answer_key = models.TextField(help_text="Canonical correct answer or pattern.")
    answer_validator_type = models.CharField(
        max_length=50,
        default="EXACT_MATCH",
        help_text="Validator type: EXACT_MATCH, MULTIPLE_CHOICE, CASE_INSENSITIVE, NUMERIC, REGEX, NORMALIZED_TEXT",
    )
    time_limit_seconds = models.IntegerField(default=60)
    explanation = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["difficulty", "category", "created_at"]
        constraints = [models.UniqueConstraint(fields=["question_bank", "import_order"], name="unique_bank_question_order")]

    def __str__(self):
        return f"[{self.type} - {self.difficulty}] {self.content[:60]}"


class TeamQuestion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    match = models.ForeignKey(
        "matches.Match",
        on_delete=models.CASCADE,
        related_name="team_questions",
    )
    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.CASCADE,
        related_name="assigned_questions",
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="team_assignments",
    )
    sequence_number = models.IntegerField()
    status = models.CharField(
        max_length=30,
        choices=QuestionStatus.choices,
        default=QuestionStatus.PENDING_QUESTION,
        db_index=True,
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    # Timer lifecycle is independent of answer/reward status and popup visibility.
    remaining_ms = models.PositiveIntegerField(default=60000)
    timer_started_at = models.DateTimeField(null=True, blank=True)
    timer_status = models.CharField(max_length=16, default="NOT_STARTED")
    timer_version = models.PositiveIntegerField(default=0)
    viewing_leases = models.JSONField(default=dict, blank=True)
    reward_coin_amount = models.PositiveIntegerField(default=30)
    # Existing assignments keep their earned fixed payout. Service assignments opt in.
    reward_coin_random = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_answer = models.TextField(blank=True, default="")
    is_correct = models.BooleanField(null=True, blank=True)

    class Meta:
        ordering = ["sequence_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["match", "team", "sequence_number"],
                name="unique_match_team_sequence",
            ),
            models.UniqueConstraint(
                fields=["match", "team", "question"],
                name="unique_match_team_question",
            ),
        ]

    def __str__(self):
        return f"Match {self.match_id} - Team {self.team.name} - Q#{self.sequence_number} ({self.status})"
