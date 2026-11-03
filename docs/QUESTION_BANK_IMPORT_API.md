# Question-bank upload API

Routes retain the existing `/api/v1/` prefix. The game uses capability tokens instead of
requiring a user account for creating a room. A cryptographically random upload token owns
the staged bank; only its hash is stored. Keep it private as with the Host token.

## Upload and preview

`POST /question-banks/upload/`: multipart `file`, with `X-Question-Bank-Token` (32–128
characters). The browser generates a fresh UUID for each selected file and reuses it on
retry. If the header is absent the server generates a token and returns it once in the
upload response. Anonymous uploads are throttled to 30/hour/IP; use shared cache/proxy
configuration appropriate to deployment for cross-worker rate limiting.

Successful parsing returns 201 with `id`, `upload_token`, `source_filename`, `sheets`,
`valid_questions`, `invalid_questions`, `errors`, `status`, `can_create`, `page`, `page_size`
and `questions`. First page size is 10. Each preview question includes options, `answer_key`,
`import_order` and source sheet/row/STT. Row errors use the actual Vietnamese column names:

```json
{"sheet":"Quiz_Fresher_Junior_20_Cau","row":2,"field":"Đáp án","message":"Đáp án phải là A, B, C hoặc D."}
```

Readable files with row/header errors are staged as INVALID; `can_create=false`.
`invalid_questions` counts distinct bad data rows; header-level errors are in `errors`
and are not misrepresented as bad question rows. Valid-row count excludes every failed row.
Unreadable, unsafe, unsupported or oversized packages return 400 without creating records.
Repeating the same token/content returns the same bank (200); changing bytes with an
existing token returns 400. Concurrent identical uploads cannot duplicate records.

`GET /question-banks/{id}/preview/?page=1&page_size=10`: requires the upload token header
or an authenticated owner/staff user. Otherwise 403. Page size is bounded to 100.
Staging expires after 24 hours; attached banks remain available for their matches.

`DELETE /question-banks/{id}/preview/`: owner token or owner/staff only; removes an unused
upload and its normalized questions (204). Attached bank returns 409. The UI supports
replace/remove and cancels obsolete requests; abandoned stages are cleaned by:

```sh
python manage.py cleanup_question_uploads
```

Schedule this command operationally if regular cleanup is desired. It locks and rechecks
attachment before deleting; attached banks are never removed.

## Create the room

`POST /matches/` retains `name` and `configuration`. New optional fields:

```json
{"name":"Quiz Battle","configuration":{"max_teams":20},"question_bank_id":"<upload UUID>","question_bank_token":"<private token>","creation_token":"<browser UUID>"}
```

Bank ID/token must be supplied together. All rows must be valid. The bank is locked and
the room, association and initial event commit together. Failure rolls back room creation,
retaining the stage for retry. Repeating a bank attachment returns the same initial room
and Host token. For rooms without uploads, `creation_token` supplies the same retry guarantee.
There is a database uniqueness constraint; a concurrent collision resolves to the existing room.
The public room response exposes `question_bank_id`, never its capability or answer keys.
Existing room creation without these optional fields remains supported.

Rematches reuse the immutable bank with new teams and separate TeamQuestion progress.

## Configuration and security

| Setting | Default |
| --- | --- |
| QUESTION_BANK_MAX_UPLOAD_BYTES | 5 × 1024 × 1024 |
| QUESTION_BANK_MAX_EXPANDED_BYTES | 25 × 1024 × 1024 |
| QUESTION_BANK_MAX_QUESTIONS | 1000 |
| QUESTION_BANK_STAGING_HOURS | 24 |

The bundled nginx API location permits 6 MiB for the default 5 MiB multipart upload.
Adjust ingress limits alongside the application limit when changing it. The upload UI
reports HTTP 413 explicitly. XLSX is read once into normalized database records, never
reparsed when answering. ZIP expansion, XML entities, macros/external links, dimensions,
row counts and text sizes are bounded before attachment. `defusedxml` is installed alongside
`openpyxl`, consistent with its [security guidance](https://openpyxl.readthedocs.io/en/stable/).

Global `/questions/` administration now requires Django staff authentication. Participant
question serializers and WebSocket events never include `answer_key` or validator configuration.
