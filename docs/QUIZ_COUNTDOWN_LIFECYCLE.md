# Persistent quiz countdown lifecycle

Assignment creates NOT_STARTED with a full budget. It does not consume time. First explicit OPEN establishes timer_started_at and expires_at once under Match→Team→Question locks. Reopening and other teammates' OPEN requests preserve that deadline. CLOSE and HEARTBEAT only settle remaining time; popup visibility and viewing leases no longer affect eligibility.

RUNNING remaining milliseconds are calculated from the absolute expires_at using server time. The scheduler settles hidden/disconnected questions, marks them EXPIRED at zero and emits the existing private QUESTION_EXPIRED event. The submit path also checks the deadline under lock, so a late answer cannot earn a reward while awaiting the scheduler. Snapshots and REST project the original deadline, server_now and remaining time.

Expiry never assigns another question. Reopen shows the same expired question. Terminal results display a separate Câu hỏi tiếp theo action, which sends NEXT with the acknowledged question ID, then explicitly OPENs the next assignment. GET, reconnect, hidden timeout and closing a result never progress. Duplicate NEXT requests acknowledge the old ID and return the already-created next question. Pending rewards block NEXT and remain recoverable; reward claims keep their existing atomic/idempotent path and 30-coin-or-unlock choice.

Existing explicit match rules are preserved: a host pause freezes the remaining budget; resume restarts that paused budget even if all quiz popups are hidden. Match completion freezes the session and makes rewards/submission unavailable. Ordinary popup closure, tab hiding, page refresh and disconnection do not pause.

questions migration 0004 resumes legacy popup-paused questions in active matches from their stored remaining budget at rollout. It does not change NOT_STARTED assignments or host-paused matches.

Closing hides immediately, including while NEXT/OPEN is still in flight; a dismissal flag prevents the late OPEN response from reopening it. The frontend keeps draft answers by question ID, updates the visible countdown independently from navigation, re-fetches on OPEN and restores state after reconnect. Local visual expiry disables submission but leaves the server as authority.

Tests: test_quiz_sessions.py covers no timer before OPEN, hidden elapsed time, fixed deadline across viewers and retries, hidden expiration, no hidden progression, explicit NEXT, snapshot recovery, reward idempotency and host pause. PostgreSQL tests cover concurrent opens/answers/rewards/NEXT. Browser acceptance includes a real 60-second hidden expiry and unchanged question identity on reopening.

Confirmed real-browser result: 60-second countdown continued while hidden, expired with the same question ID and no reward, reopened as EXPIRED, and required an explicit Next action. Three-client gameplay and PostgreSQL concurrency suites passed. See [browser evidence](qa/team-upgrades-browser.json).
