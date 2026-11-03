# Quiz popup and timer audit

> Historical viewing-lease behavior is superseded by [persistent countdown lifecycle](QUIZ_COUNTDOWN_LIFECYCLE.md). Closing or disconnecting now keeps the original deadline running.

Date: 2026-10-24 (Asia/Ho_Chi_Minh).

## Confirmed causes

The original source and its existing modal regression test established these deterministic paths. A pre-change live browser reproduction was not captured; the corrected paths were subsequently exercised against a disposable backend with real React, Phaser and WebSocket clients.

1. **Assignment started the clock.** `QuestionService.get_or_assign_current_question` created `expires_at = now + time_limit_seconds` on every new assignment. `BattlePage.refresh` called that method on page load and unrelated lifecycle/combat refreshes, regardless of whether the question was visible.
2. **A read could skip a question.** The same service expired an overdue pending question and continued directly to assigning another. Scheduler expiration plus refresh therefore consumed and advanced hidden questions.
3. **Expiration removed the dialog.** `matchStore` handled `QUESTION_EXPIRED` by replacing `currentQuestion` with null. `visibleGameplayModal` also returned null for expired/claimed questions; `BattlePage` copied that result back into its modal intent. The old `gameplay-modal.test.ts` explicitly asserted this closure behavior. Expiration feedback in `QuestionModal` could not remain visible through that path.
4. **Opponent reward events dismissed local dialogs.** `BattlePage` applied team filtering to question data, but its following `REWARD_APPLIED` / `REWARD_CLAIMED` handler called `setModal(null)` outside that filter. The store already filtered foreign rewards; the page-level closure did not.
5. **Drafts followed visibility/deadline instead of identity.** `QuestionModal` reset selected/text answers when `isOpen` or `expires_at` changed. `RewardSelectionModal` reset the grid and selected unit on reopening. These effects lost user choices even when the entitlement/question was unchanged.
6. **Host pause discarded pending questions.** `MatchService.pause_match` changed all pending questions to EXPIRED. This is now a timer freeze that preserves question identity and remaining time.
7. **Match completion silently hid the current dialog.** Page/store match-ended handling cleared visibility/content. Completion now preserves the dialog and displays an explicit, non-actionable end-of-match message.

The quiz and reward components were already mounted at a stable level in `BattlePage`; Phaser did not create a React root per entity or own quiz visibility. Neither active modal used backdrop dismissal. The primary defects were state transitions and effects, rather than combat animation remounting. Global Escape dismissal was removed from the page; the dialog focus trap delegates Escape to the same authoritative close operation as Close.

## Before/after lifecycle

| Event | Original behavior | Updated behavior |
| --- | --- | --- |
| Background current-question GET | Assign/start; expire and potentially advance | Recover latest session; initially assign without starting |
| Explicit Open | Only show UI | Server opens a viewing lease and starts/resumes the budget |
| Close / Escape | Hide; countdown continued | Await authoritative pause for this viewer, then hide |
| Last viewer closes | Countdown continued | Preserve remaining milliseconds and question |
| One of several viewers closes | No viewer ownership | Remaining viewers keep the single shared countdown running |
| Browser disappears | Timer ran until its original deadline | Consumption is bounded by the final server lease expiry |
| Incorrect / timeout / claim | Refresh could assign another question | Retain result until explicit Next acknowledges its ID |
| Opponent claims a reward | Could close local reward/quiz UI | Foreign reward events do not alter local quiz intent |
| Host pause / match end | Expire/clear active question | Freeze timer; retain content and explain terminal match state |

## Boundaries

The existing `TeamQuestion` answer/reward state machine remains the entitlement authority. Timer state is a separate lifecycle on that same row, not a second question-progress model. Local visibility, drafts, submission pending state and reward selection remain UI concerns. Reward claims remain transactional and one per team-question.

See `QUIZ_REWARD_HUD_IMPLEMENTATION.md` for protocol details, compatibility decisions, commands, measured layout changes and final verification results.
