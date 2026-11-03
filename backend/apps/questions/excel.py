"""Resource-bounded adapter for the owner's Vietnamese multiple-choice workbook."""

import math
import unicodedata
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from defusedxml.ElementTree import fromstring
from django.conf import settings
from django.core.exceptions import ValidationError
from openpyxl import load_workbook

HEADERS = ["STT", "Câu hỏi", "A", "B", "C", "D", "Đáp án", "Độ khó", "Chủ đề"]
REQUIRED = HEADERS[:7]
DIFFICULTIES = {
    "dễ": "EASY", "easy": "EASY",
    "trung bình": "MEDIUM", "khá": "MEDIUM", "medium": "MEDIUM",
    "khó": "HARD", "rất khó": "HARD", "hard": "HARD",
}


def normalized(value):
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).lstrip("\ufeff").split()).casefold()


def parse_workbook(data: bytes, filename: str):
    if not filename.lower().endswith(".xlsx"):
        raise ValidationError("Chỉ hỗ trợ tệp .xlsx.")
    if len(data) > settings.QUESTION_BANK_MAX_UPLOAD_BYTES:
        raise ValidationError("Tệp vượt quá giới hạn dung lượng cho phép.")
    limit = settings.QUESTION_BANK_MAX_QUESTIONS
    # ZIP metadata is checked before decompression. XML is never executed or evaluated.
    try:
        with ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 256 or sum(e.file_size for e in entries) > settings.QUESTION_BANK_MAX_EXPANDED_BYTES:
                raise ValidationError("Workbook vượt giới hạn tài nguyên giải nén.")
            names = [e.filename for e in entries]
            if len(names) != len(set(names)) or "xl/workbook.xml" not in names or "[Content_Types].xml" not in names:
                raise ValidationError("Tệp không phải workbook XLSX hợp lệ.")
            for entry in entries:
                name = entry.filename.lower()
                if "vbaproject" in name or "externallinks/" in name or entry.flag_bits & 1:
                    raise ValidationError("Không hỗ trợ macro, workbook mã hóa hoặc liên kết ngoài.")
                if name.endswith((".xml", ".rels")):
                    root = fromstring(archive.read(entry))
                    for element in root.iter():
                        tag = element.tag.rsplit("}", 1)[-1]
                        if tag == "Relationship" and element.get("TargetMode", "").lower() == "external":
                            raise ValidationError("Workbook chứa liên kết ngoài không được hỗ trợ.")
                        if tag == "Override" and "macroenabled" in element.get("ContentType", "").lower():
                            raise ValidationError("Không hỗ trợ workbook chứa macro.")
                        if tag == "mergeCell":
                            raise ValidationError("Không hỗ trợ ô gộp; hãy bỏ gộp ô trước khi nhập.")
                        if tag == "row" and int(element.get("r", 0)) > limit + 100:
                            raise ValidationError("Workbook có quá nhiều hàng.")
                        if tag == "c":
                            column = "".join(c for c in element.get("r", "") if c.isalpha())
                            if len(column) > 1 and (len(column) > 2 or column > "AF"):
                                raise ValidationError("Workbook có quá nhiều cột (tối đa 32).")
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError("Không đọc được tệp XLSX hoặc XML không an toàn.") from exc

    errors, questions, sheets = [], [], []
    invalid_rows, seen, scanned_rows = set(), set(), 0

    def error(sheet, row, field, message):
        errors.append({"sheet": sheet, "row": row, "field": field, "message": message})
        if row > 1:
            invalid_rows.add((sheet, row))

    try:
        workbook = load_workbook(BytesIO(data), read_only=True, data_only=False, keep_links=False)
        try:
            if len(workbook.worksheets) > 10:
                raise ValidationError("Tối đa 10 worksheet cho mỗi workbook.")
            for sheet in workbook.worksheets:
                # Do not trust a producer's dimension cache, including understated dimensions.
                sheet.reset_dimensions()
                rows = sheet.iter_rows(max_col=32)
                header = next(rows, ())
                if not any(c.value is not None for c in header):
                    if any(c.value is not None for row in rows for c in row):
                        error(sheet.title, 1, "header", "Hàng 1 phải chứa tên cột.")
                    continue
                sheets.append(sheet.title)
                columns = {}
                for index, cell in enumerate(header):
                    if cell.value is None:
                        continue
                    key = normalized(cell.value)
                    if key in columns:
                        error(sheet.title, 1, str(cell.value), "Tên cột bị trùng.")
                    columns[key] = index
                missing = [h for h in REQUIRED if normalized(h) not in columns]
                for field in missing:
                    error(sheet.title, 1, field, "Thiếu cột bắt buộc.")
                if missing or any(e["sheet"] == sheet.title for e in errors):
                    continue
                seen_numbers = set()
                for row_number, row in enumerate(rows, 2):
                    scanned_rows += 1
                    if scanned_rows > limit + 100:
                        raise ValidationError(f"Tối đa {limit} câu hỏi và 100 hàng trống.")
                    if all(c.value is None or c.value == "" for c in row):
                        continue
                    values = {}
                    for field in HEADERS:
                        index = columns.get(normalized(field))
                        cell = row[index] if index is not None else None
                        value = cell.value if cell else None
                        if cell and cell.data_type in ("f", "e"):
                            error(sheet.title, row_number, field, "Không hỗ trợ công thức hoặc giá trị lỗi Excel.")
                            value = None
                        elif value is not None and (isinstance(value, bool) or not isinstance(value, (str, int, float)) or isinstance(value, float) and not math.isfinite(value)):
                            error(sheet.title, row_number, field, "Kiểu giá trị ô không được hỗ trợ.")
                            value = None
                        values[field] = str(value).strip() if value is not None else ""
                    for field in REQUIRED:
                        if not values[field]:
                            error(sheet.title, row_number, field, "Giá trị không được để trống.")
                    for field, size in [("Câu hỏi", 4000), *((key, 2000) for key in "ABCD"), ("Chủ đề", 50), ("Độ khó", 30)]:
                        if len(values[field]) > size:
                            error(sheet.title, row_number, field, f"Vượt quá {size} ký tự.")
                    try:
                        number = float(values["STT"])
                        if not math.isfinite(number) or not number.is_integer() or number < 1 or number in seen_numbers:
                            raise ValueError
                        seen_numbers.add(number)
                    except ValueError:
                        error(sheet.title, row_number, "STT", "STT phải là số nguyên dương và không trùng trong sheet.")
                    answer = values["Đáp án"].upper()
                    if answer not in ("A", "B", "C", "D"):
                        error(sheet.title, row_number, "Đáp án", "Đáp án phải là A, B, C hoặc D.")
                    options = [normalized(values[k]) for k in "ABCD"]
                    if len(set(options)) != 4:
                        error(sheet.title, row_number, "A–D", "Các lựa chọn phải khác nhau.")
                    difficulty = DIFFICULTIES.get(normalized(values["Độ khó"]), "MEDIUM")
                    if values["Độ khó"] and normalized(values["Độ khó"]) not in DIFFICULTIES:
                        error(sheet.title, row_number, "Độ khó", "Độ khó không được hỗ trợ.")
                    fingerprint = normalized(values["Câu hỏi"])
                    if fingerprint in seen:
                        error(sheet.title, row_number, "Câu hỏi", "Câu hỏi bị trùng trong workbook.")
                    seen.add(fingerprint)
                    if (sheet.title, row_number) in invalid_rows:
                        continue
                    questions.append({
                        "content": values["Câu hỏi"],
                        "options": [{"key": k, "text": values[k]} for k in "ABCD"],
                        "answer_key": answer, "answer_validator_type": "MULTIPLE_CHOICE",
                        "difficulty": difficulty, "category": values["Chủ đề"] or "General",
                        "import_order": len(questions) + 1,
                        "import_metadata": {"sheet": sheet.title, "row": row_number, "STT": int(number), "Độ khó": values["Độ khó"]},
                    })
                    if len(questions) > limit:
                        raise ValidationError(f"Tối đa {limit} câu hỏi.")
        finally:
            workbook.close()
    except ValidationError:
        raise
    except (BadZipFile, KeyError, ValueError, TypeError, OSError) as exc:
        raise ValidationError("Workbook bị hỏng hoặc có cấu trúc không được hỗ trợ.") from exc
    if not questions and not errors:
        error("", 1, "Câu hỏi", "Workbook không có câu hỏi.")
    return {"questions": questions, "errors": errors, "sheets": sheets, "invalid_questions": len(invalid_rows)}
