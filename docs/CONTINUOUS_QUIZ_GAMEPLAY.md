# Continuous team quiz gameplay

Uploaded rooms offer every imported question, in tab/physical-row order, throughout all
major rounds. Each team has its own persistent TeamQuestion sequence and final answers.
Legacy rooms retain their configured question limit/difficulty selection and cannot draw
from any uploaded bank.

| Lifecycle | Read progress/history | Assign / submit / claim |
| --- | --- | --- |
| Lobby | Yes for authorized members | No |
| Active Preparation / PLANNING | Yes | Yes |
| Active Battle (WAR / BATTLE) | Yes | Yes |
| Paused | Yes | No |
| Results / Finished | Yes | No new submissions/claims |
| Eliminated or spectator | Authorized read only | No |

The existing `GET /matches/{id}/questions/current/` chooses the next eligible question;
the frontend never selects an arbitrary Question ID. The answer route takes the assigned
**TeamQuestion ID**, not the bank Question ID:

`POST /matches/{id}/questions/{team_question_id}/answer/` with `{"answer":"B"}`.

One final answer is recorded. Wrong answers or timeouts consume that question with no
reward. Correct answers become PENDING_REWARD and block assignment of the next question
until the single entitlement is claimed or an existing configured deadline expires.
The normal 60-second question timer remains in force, including across phase transitions
and while the panel is hidden. No new implicit reward deadline/default payout is invented.
Legacy configured reward grace periods remain supported.

`POST /matches/{id}/rewards/claim/` accepts `team_question_id`, `reward_type` COIN or UNLOCK,
optional `unit_type_id` and `idempotency_key`. Match/team/question locks and the existing
one-to-one RewardClaim ensure only one choice commits. COIN credits exactly 20 with one
CoinTransaction. UNLOCK is free, verifies prerequisite/locked/active status, and records one
TeamUnlock. Deployment/building still spends the normal price. Fully unlocked teams retain
the coin choice; the existing reward dialog disables unlocking and explains why.

`GET /matches/{id}/questions/progress/` returns `answered`, `correct`, `total`, `remaining`,
`exhausted`, `pending_reward_id`. Progress means final answers/timeouts, including questions
with a pending reward. `history/` remains the existing authorized audit trail. Browser reload,
reconnect and round transitions restore persisted state; exhaustion disables new answering
without blocking battle purchases or erasing resources.

## Realtime and HUD

Reused events: QUESTION_ASSIGNED, QUESTION_ANSWERED_CORRECT, QUESTION_ANSWERED_INCORRECT,
QUESTION_EXPIRED and REWARD_CLAIMED. Their team-private payloads now carry `question_state`
(existing safe TeamQuestion serializer) and `question_progress`. Wallet/unlock events retain
their existing contracts. Other teams receive EVENT_REDACTED placeholders to preserve
global sequence continuity. The viewer snapshot adds `question_progress` alongside existing
`current_question` / `pending_reward` fields.

The HUD shows answered/total, correct and remaining counts, a pending-reward entry point,
and a completion message. The question heading shows current number / total. Incorrect
feedback remains visible until Continue/Close, which requests the next question. Rewards
animate after server confirmation. Quiz event ordering is tracked separately from combat
ticks, so continuous movement does not invalidate a current-question REST result.

Opening the React question/reward dialog blocks placement input under its backdrop through
the existing Phaser interaction lock. It does not recreate the scene, alter camera position,
pause simulation, stop the scheduler or disable WebSocket delivery. Teammates can continue
deployment/building through their own clients.
