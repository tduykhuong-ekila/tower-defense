"""Upload staging and atomic attachment, using the game's capability-token convention."""

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.matches.models import Match
from apps.matches.services import MatchService, hash_token
from apps.questions.excel import parse_workbook
from apps.questions.models import Question, QuestionBank
from apps.questions.serializers import QuestionAdminSerializer


class UploadThrottle(AnonRateThrottle):
    rate = "30/hour"


class UploadInput(serializers.Serializer):
    file = serializers.FileField()


def upload_token(request):
    token = request.headers.get("X-Question-Bank-Token", "")
    if not 32 <= len(token) <= 128:
        raise ValidationError("Cần X-Question-Bank-Token dài 32–128 ký tự.")
    return token


def owns_bank(request, bank):
    token = request.headers.get("X-Question-Bank-Token", "")
    user = request.user
    return (bool(token) and constant_time_compare(bank.token_hash, hash_token(token))) or (
        user and user.is_authenticated and (user.is_staff or bank.owner_id == user.pk)
    )


def bank_payload(bank, page=1, page_size=10):
    attached = bank.matches.exists()
    expired = bank.created_at + timedelta(hours=settings.QUESTION_BANK_STAGING_HOURS) <= timezone.now()
    return {
        "id": str(bank.id), "source_filename": bank.source_filename,
        "valid_questions": bank.question_count, "invalid_questions": bank.invalid_questions,
        "errors": bank.errors, "sheets": bank.sheets,
        "status": "ATTACHED" if attached else "EXPIRED" if expired else "INVALID" if bank.errors else "VALIDATED",
        "can_create": not bank.errors and bank.question_count > 0 and (attached or not expired),
        "page": page, "page_size": page_size,
        "questions": QuestionAdminSerializer(bank.questions.order_by("import_order")[(page - 1) * page_size:page * page_size], many=True).data,
    }


class QuestionBankUploadView(APIView):
    throttle_classes = [UploadThrottle]

    def post(self, request):
        serializer = UploadInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        file = serializer.validated_data["file"]
        token = request.headers.get("X-Question-Bank-Token") or secrets.token_urlsafe(32)
        if not 32 <= len(token) <= 128:
            return Response({"error": "Upload token phải dài 32–128 ký tự."}, status=400)
        data = file.read(settings.QUESTION_BANK_MAX_UPLOAD_BYTES + 1)
        digest = hashlib.sha256(data).hexdigest()
        try:
            existing = QuestionBank.objects.filter(token_hash=hash_token(token)).first()
            if existing:
                if existing.content_sha256 != digest:
                    raise ValidationError("Upload token đã được dùng cho tệp khác; hãy chọn lại tệp.")
                return Response({**bank_payload(existing), "upload_token": token})
            parsed = parse_workbook(data, file.name)
            with transaction.atomic():
                bank, created = QuestionBank.objects.get_or_create(token_hash=hash_token(token), defaults={
                    "owner": request.user if request.user.is_authenticated else None,
                    "source_filename": file.name[:255], "content_sha256": digest,
                    "question_count": len(parsed["questions"]), "invalid_questions": parsed["invalid_questions"],
                    "errors": parsed["errors"], "sheets": parsed["sheets"],
                })
                if bank.content_sha256 != digest:
                    raise ValidationError("Upload token đã được dùng cho tệp khác.")
                if created:
                    Question.objects.bulk_create([Question(question_bank=bank, **q) for q in parsed["questions"]])
            return Response({**bank_payload(bank), "upload_token": token}, status=status.HTTP_201_CREATED)
        except ValidationError as exc:
            return Response({"error": "; ".join(exc.messages)}, status=400)


class QuestionBankPreviewView(APIView):
    def get_bank(self, request, bank_id):
        from django.shortcuts import get_object_or_404

        bank = get_object_or_404(QuestionBank, pk=bank_id)
        return bank if owns_bank(request, bank) else None

    def get(self, request, bank_id):
        bank = self.get_bank(request, bank_id)
        if bank is None:
            return Response({"error": "Chỉ chủ sở hữu ngân hàng câu hỏi được xem đáp án."}, status=403)
        try:
            page = max(1, int(request.query_params.get("page", 1)))
            page_size = max(1, min(100, int(request.query_params.get("page_size", 10))))
        except ValueError:
            return Response({"error": "page/page_size phải là số nguyên."}, status=400)
        return Response(bank_payload(bank, page, page_size))

    def delete(self, request, bank_id):
        with transaction.atomic():
            bank = QuestionBank.objects.select_for_update().filter(pk=bank_id).first()
            if bank is None:
                return Response(status=204)
            if not owns_bank(request, bank):
                return Response({"error": "Không có quyền xóa lượt tải lên."}, status=403)
            if bank.matches.exists():
                return Response({"error": "Ngân hàng đã gắn với phòng, không thể xóa."}, status=409)
            bank.delete()
        return Response(status=204)


@transaction.atomic
def create_match_with_bank(*, bank_id, token, name, configuration, created_by=None):
    bank = QuestionBank.objects.select_for_update().filter(pk=bank_id).first()
    if bank is None or not constant_time_compare(bank.token_hash, hash_token(token)):
        raise ValidationError("Ngân hàng câu hỏi hoặc upload token không hợp lệ.")
    # The same capability always yields the same initial room, including HTTP retries.
    creation_token = token + str(bank.pk)
    existing = Match.objects.filter(question_bank=bank, creation_token_hash=hash_token(creation_token)).first()
    if existing:
        return existing, MatchService.creation_host_token(creation_token)
    if bank.errors or not bank.question_count:
        raise ValidationError("Hãy sửa tất cả lỗi Excel và tải lên lại trước khi tạo phòng.")
    if bank.created_at + timedelta(hours=settings.QUESTION_BANK_STAGING_HOURS) <= timezone.now():
        raise ValidationError("Lượt tải lên đã hết hạn; hãy tải lại tệp.")
    return MatchService.create_match(name=name, configuration=configuration, created_by=created_by,
                                    question_bank=bank, creation_token=creation_token)
