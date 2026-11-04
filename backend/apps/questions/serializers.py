from django.utils import timezone
from rest_framework import serializers

from apps.questions.models import Question, QuestionStatus, TeamQuestion
from apps.rewards.services import RewardService


class QuestionPublicSerializer(serializers.ModelSerializer):
    """
    Public participant-facing serializer for active questions (§5.1, §19.4).
    CRITICAL: Never exposes answer_key, answer_validator_type, or explanation.
    """

    class Meta:
        model = Question
        fields = [
            "id",
            "type",
            "category",
            "difficulty",
            "content",
            "options",
            "time_limit_seconds",
        ]


class QuestionResolvedSerializer(serializers.ModelSerializer):
    """
    Serializer for questions that have already been submitted or expired.
    Includes explanation and reference answers for review.
    """

    correct_answer = serializers.SerializerMethodField()

    def get_correct_answer(self, obj):
        answer = str(obj.answer_key).strip()
        if obj.type == "MULTIPLE_CHOICE":
            for index, option in enumerate(obj.options or []):
                key = str(option.get("key", "")) if isinstance(option, dict) else chr(65 + index)
                text = str(option.get("text", "")) if isinstance(option, dict) else str(option)
                if answer.casefold() in (key.strip().casefold(), text.strip().casefold()):
                    return f"{key}. {text}"
        return answer

    class Meta:
        model = Question
        fields = [
            "id",
            "type",
            "category",
            "difficulty",
            "content",
            "options",
            "time_limit_seconds",
            "explanation",
            "correct_answer",
        ]


class QuestionAdminSerializer(serializers.ModelSerializer):
    """Full question serializer for Host management and Django admin."""

    class Meta:
        model = Question
        fields = "__all__"
        read_only_fields = ["question_bank", "import_order", "import_metadata"]


class TeamQuestionSerializer(serializers.ModelSerializer):
    # Foreign-key *_id fields otherwise remain raw UUIDs in Channels JSON.
    match_id = serializers.UUIDField(read_only=True)
    team_id = serializers.UUIDField(read_only=True)
    question = serializers.SerializerMethodField()
    time_remaining_seconds = serializers.SerializerMethodField()
    reward_options = serializers.SerializerMethodField()
    timer = serializers.SerializerMethodField()

    class Meta:
        model = TeamQuestion
        fields = [
            "id",
            "match_id",
            "team_id",
            "sequence_number",
            "status",
            "assigned_at",
            "expires_at",
            "submitted_at",
            "submitted_answer",
            "is_correct",
            "question",
            "time_remaining_seconds",
            "reward_options",
            "timer",
        ]

    def get_question(self, obj):
        # Only expose explanation if question is submitted, completed or expired
        if obj.status in [
            QuestionStatus.ANSWER_CORRECT,
            QuestionStatus.ANSWER_INCORRECT,
            QuestionStatus.PENDING_REWARD,
            QuestionStatus.REWARD_CLAIMED,
            QuestionStatus.EXPIRED,
        ]:
            return QuestionResolvedSerializer(obj.question).data
        return QuestionPublicSerializer(obj.question).data

    def get_time_remaining_seconds(self, obj) -> int:
        if obj.status != QuestionStatus.PENDING_QUESTION:
            return 0
        from apps.questions.timers import remaining_at
        return (remaining_at(obj) + 999) // 1000

    def get_timer(self, obj):
        from apps.questions.timers import remaining_at
        now = timezone.now()
        remaining = remaining_at(obj, now)
        status = obj.timer_status
        if obj.status != QuestionStatus.PENDING_QUESTION:
            status = "EXPIRED" if obj.status == QuestionStatus.EXPIRED else "COMPLETED"
        elif remaining == 0:
            status = "EXPIRED"
        return {"status": status, "remaining_ms": remaining, "version": obj.timer_version,
                "server_now": now.isoformat(), "deadline_at": obj.expires_at.isoformat() if status == "RUNNING" else None}

    def get_reward_options(self, obj):
        if obj.status == QuestionStatus.PENDING_REWARD:
            return RewardService.get_reward_options(obj)
        return None


class AnswerSubmissionSerializer(serializers.Serializer):
    answer = serializers.CharField(
        required=True,
        max_length=4000,
        allow_blank=False,
        trim_whitespace=True,
        help_text="The submitted answer (e.g. choice key 'A' or text).",
    )
