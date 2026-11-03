from django.contrib import admin

from apps.questions.models import Question, TeamQuestion


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ["content_snippet", "type", "category", "difficulty", "time_limit_seconds", "is_active", "created_at"]
    list_filter = ["type", "difficulty", "category", "is_active"]
    search_fields = ["content", "answer_key", "category", "explanation"]
    list_editable = ["is_active"]
    exclude = ["question_bank", "import_order", "import_metadata"]

    def get_queryset(self, request):
        # Uploaded banks are immutable snapshots; this editor manages the legacy pool.
        return super().get_queryset(request).filter(question_bank__isnull=True)

    def content_snippet(self, obj):
        return obj.content[:60]
    content_snippet.short_description = "Question Content"


@admin.register(TeamQuestion)
class TeamQuestionAdmin(admin.ModelAdmin):
    list_display = ["match", "team", "sequence_number", "status", "is_correct", "assigned_at", "expires_at", "submitted_at"]
    list_filter = ["status", "is_correct", "match"]
    search_fields = ["team__name", "question__content"]
