# Verified Excel question-bank schema

Inspected the owner's `/Users/admin/Downloads/De_Thi_Quiz_Demo.xlsx` on 2026-10-22.
An unchanged copy is the regression fixture `backend/tests/fixtures/De_Thi_Quiz_Demo.xlsx`.
SHA-256: `d179628c7472747ea5794c3488f4ef950302f3ef022ad0c798a0c9430e79b1ce`.

The workbook contains one visible sheet, **Quiz_Fresher_Junior_20_Cau**, range A1:I21.
Row 1 contains bold headers; rows 2–21 contain 20 questions. STT runs from 1 to 20.
There are no merged cells, blank rows, formulas, external workbook links, hidden rows,
filters or frozen panes. Formatting does not encode answers or question order.

| Actual header | Required | Meaning and validation |
| --- | --- | --- |
| STT | Yes | Positive integer, unique within its sheet; preserved as source metadata. |
| Câu hỏi | Yes | Nonblank question text, at most 4,000 characters. |
| A | Yes | Nonblank option, at most 2,000 characters. |
| B | Yes | Same rule. |
| C | Yes | Same rule. |
| D | Yes | Same rule; all four option texts must differ. |
| Đáp án | Yes | Exactly one option letter A, B, C or D, after trimming/uppercasing. |
| Độ khó | Optional | Dễ → EASY; Trung bình/Khá → MEDIUM; Khó/Rất khó → HARD. Blank defaults to MEDIUM. English EASY/MEDIUM/HARD also supported. |
| Chủ đề | Optional | Category, at most 50 characters; blank defaults to General. |

Observed difficulty labels: Dễ (2), Trung bình (5), Khá (3), Khó (7), Rất khó (3).
The original Vietnamese difficulty label is retained in `import_metadata`.

Example: row 2, STT 1, asks which CSS property implements two-dimensional grid layout.
Its `Đáp án` is `B`, whose text begins `display: grid`; `Độ khó` is `Dễ`, and
`Chủ đề` is `Web dev`. This becomes MULTIPLE_CHOICE with four keyed options,
server-only answer key B, difficulty EASY, import order 1, and sheet/row/STT metadata.

## Supported variations

- Sheet names are unrestricted; each nonempty sheet must use the same row-1 schema.
- Up to ten worksheets, processed in workbook tab order, then physical row order.
  STT identifies the source row; it does not sort or shuffle questions.
- Header case, Unicode compatibility normalization, surrounding/repeated whitespace,
  BOM, column reordering and optional metadata columns are supported.
- Completely blank rows/sheets are skipped. Nonempty sheets with bad headers fail validation.
- Finite numeric cell values are converted to text. Boolean/date/error values are rejected.
- Normalized duplicate question text is rejected across all worksheets. No partial import
  can create a room: every validation error must be corrected first.

## Limits and unsupported content

Only real `.xlsx` packages are supported. Defaults: 5 MiB compressed, 25 MiB expanded,
256 ZIP entries, 10 sheets, 32 columns, 1,000 questions and at most 100 additional blank rows.
Rows beyond the configured question bound plus 100 are rejected, including formatting-only rows.
Required fields cannot contain formulas; formulas/errors in recognized optional fields also fail.
Merged cells, encrypted ZIP entries, VBA/macros, external relationships/links and unsafe XML
entities are rejected. Formula results are never evaluated or accepted from cached values.
Additional unrecognized columns are ignored. This adapter intentionally supports one final
multiple-choice answer per question; it does not infer multiple answers or free-text schemas.

Implementation: `backend/apps/questions/excel.py`. Limits are settings documented in
`QUESTION_BANK_IMPORT_API.md`.
