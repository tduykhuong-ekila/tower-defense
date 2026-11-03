# Quiz progression update

The extra “Câu hỏi tiếp theo” button is removed. The existing result/reward interface remains visible while open. Closing and reopening the quiz card is the normal progression interaction.

`OPEN_SESSION` extends the existing question-action endpoint. Under the match/team locks it settles the current deadline, keeps unfinished questions and pending rewards, or advances a finalized question and opens its successor in one transaction. The request carries the last observed question ID, so retries or simultaneous teammate opens cannot skip another question. Legacy NEXT is still accepted for older clients; the current UI does not send it and has no NEXT workflow.

| Current state when opening | Result |
| --- | --- |
| No assignment | Assign/open the first eligible question. |
| PENDING_QUESTION, still running | Restore the same question and original deadline. |
| PENDING_QUESTION, deadline elapsed | Finalize as expired; show a nonblocking timeout notice and open the next eligible question. |
| EXPIRED / ANSWER_INCORRECT / REWARD_CLAIMED | Open the next eligible question without another confirmation. |
| PENDING_REWARD | Restore reward selection; never skip the entitlement. |
| Bank exhausted | Show the existing completion notice. |

Opening for the first time starts the server deadline. CLOSE, HEARTBEAT, hidden expiration, GET refreshes, snapshots, unrelated socket events and component cleanup cannot advance the question. Closing does not pause a running deadline. Explicit global match pause/resume retains its established semantics. Background expiration finalizes only the active question; it never assigns or activates its successor.

Earned rewards persist across phase changes until claimed while gameplay remains eligible. Legacy stored reward-grace deadlines are ignored: the old scheduler hook is retained for compatibility but no longer discards a pending reward. Reward uniqueness and economy transactions still enforce one +30-coin or unlock choice per team-question. Existing older room configurations keep their configured coin amount; default rooms retain +30. Match completion/administrative closure still disables gameplay claims.

Files: `questions/services.py`, `questions/views.py`, `questions/state_machine.py`, `rewards/services.py`, `matches/services.py`, `QuestionModal.tsx`, `BattlePage.tsx`, `services/api.ts`.

Tests cover persistent countdowns, hidden expiration, explicit reopening without NEXT, wrong-answer progression, pending rewards, idempotent +30 claims, stale/repeated opening requests and simultaneous PostgreSQL team opens. The three-client browser suite verifies the real popup flow and absence of the extra button.
