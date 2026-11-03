# Full gameplay flow audit — 17 October 2026

## Reproduction before gameplay changes

A disposable Django database and two real participants were used. In Round 1, the
attacker bought infantry through the actual battlefield UI and the defender bought an
MG tower. After server resolution, the browser displayed **Round 2**, ACTIVE,
PREPARATION, connected, 995 coins and only one of five unit slots occupied. Its infantry
card was **disabled**, while a real deployment API request from that same participant
was **accepted**. See [captured values](qa/flow-reproduction.json) and
[browser screenshot](qa/flow-reproduction.png).

This reproduces a client/server eligibility disagreement. It does not establish that
the backend forbids all later-round purchases: the current backend permits them.

## Current state machine and confirmed causes

- Match stages: LOBBY → PREPARATION → BUILD_AND_SCOUT → WAR → FINAL_ASSAULT → RESULTS.
- The existing D3 round model resolves combat atomically and immediately opens the next
  planning window. `COMBAT_RESOLVED` already contains the next round and its deadline.
- React's `blocked` combines server eligibility with **local Phaser `playing`**. Thus
  the server opens Round 2 while React still disables every purchase during Round 1's
  replay. Phaser also remains in COMBAT interaction mode until that replay finishes.
- Every combat packet is queued. There is a per-packet animation duration bound, but no
  queue bound, wall-clock recovery, or authoritative-snapshot cancellation. Background
  tab throttling, a paused scene clock, or rapid host resolutions can retain old replay
  locks beyond the planning window. Pointer listeners themselves are only removed on
  scene shutdown; missing pointer registration was not the reproduced cause.
- A second browser reproduction confirmed an **invisible reward modal lock**. Answering
  correctly, leaving the reward dialog open and crossing its expiration boundary removes
  the reward data and the dialog DOM, but leaves React's `modal = REWARD`. Cards remain
  disabled with `MODAL_OPEN` although no dialog exists. See
  [before-fix values](qa/reward-expiry-reproduction.json). This can survive subsequent
  rounds indefinitely. Snapshot reconciliation has the same risk when it removes pending
  question/reward data without clearing the requested dialog.
- `UNIT_DEPLOYED`, `TOWER_BUILT` and special-action events read `team_locked.coins` from
  before `EconomyService.debit` reloads/mutates another Team instance. Their stale
  `coins_after` can overwrite the correct preceding `COINS_UPDATED` balance on clients.
- Eligibility is duplicated across backend services, React cards and placement handlers.
  Cards omit capacity/phase explanations, and locked technology cards are selectable.
  Rejections usually contain only prose, so the UI cannot consistently identify the
  actual reason. Fetch has no timeout; an unresolved purchase can retain the pending lock.

## Limits, persistence and existing combat

- There is **no lifetime `has_deployed` / `has_built` flag**, and no deployment or
  construction quota per round. `max_*_per_action = 1` limits one purchase request.
- Active-unit capacity counts QUEUED/ACTIVE/DISABLED entities; tower capacity and slots
  count surviving structures. These are persistent occupancy limits, not counters to
  reset every round. The default remains five units and three towers.
- Repair is limited to one accepted action until that round resolves. Resolution marks
  accepted actions RESOLVED, which restores repair eligibility. Question/reward history
  and unlocks are match-wide and must never be cleared by round entry.
- Current construction stages are PREPARATION, BUILD_AND_SCOUT and WAR. FINAL_ASSAULT
  excludes new towers in the existing service and UI; this is preserved and explained.
- The engine, scheduler, movement, tower/unit attacks, shields, elimination, final scores
  and recovery were implemented previously. They need integration regression tests with
  **new purchases in later rounds**, not replacement or client-side damage.
- Existing stores use monotonic event sequences, but playback is outside that mechanism:
  a fresh snapshot can repair entity state without releasing its stale UI lock.

## Intended state machine

Keep the existing match stages and the instantaneous D3 engine. Store the logical round
phase alongside the existing timer: PLANNING → LOCKED → RESOLVING → RESULTS → next
PLANNING. Locked/resolving/results transitions occur inside the same match transaction;
commands serialize behind that lock and are validated against the committed round.
Publish the completed combat and next planning entry with explicit round/sequence data.

Playback is a replay of the **completed** round, never permission to override the next
planning round. New legal interactions may finish that replay and immediately use the
existing scene. Snapshots/reconnect and wall-clock expiry must discard stale replays.
Actual server non-planning phases, pause, elimination and finished matches remain locked.

## Files and regression risks

- Backend: shared action eligibility/rejection reasons; purchase/question/reward services;
  round clock and combat events; snapshot/team-state contracts; action adapters/logging.
- Frontend: shared availability derivation; match store/event ordering; BattlePage cards
  and placement; visible modal reconciliation; Phaser playback/bridge; bounded API
  waiting and error feedback.
- Tests: real Round 1/2/5 purchases, occupancy versus quotas, concurrency, snapshots,
  host disconnect, later-round canvas placement, interrupted replay and full matches.

Risks: silently changing balance or FINAL_ASSAULT policy; clearing persistent capacity;
duplicate income/purchases; suppressing all animations with an immediate ROUND_STARTED;
stale/out-of-order snapshots canceling current interactions; exposing private balances;
recreating the scene or resetting its camera. Tests must protect each of these behaviors.
