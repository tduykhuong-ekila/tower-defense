# Question-bank and continuous-quiz audit

Audit date: 2026-10-22. The supplied workbook was available and inspected before parser implementation.

| Existing behavior | Finding | Implemented change |
| --- | --- | --- |
| Question / TeamQuestion | Persistent answer history, sequence uniqueness and one assignment per team/question already existed. | Reused both models; added bank/import fields to Question. |
| RewardClaim / TeamUnlock / CoinTransaction | One-to-one reward claims, transactional match/team locks, free unlocks and fixed +20 coins already existed. | Reused existing reward/economy services. No second reward system. |
| Room creation | No XLSX staging, validation, preview or bank reference; repeated POSTs could create additional rooms. | Persistent capability-owned staging; atomic attachment; unique creation token and retry-stable Host credentials. |
| Assignment | Global active question pool, random difficulty selection and default maximum eight questions. | Uploaded rooms randomly draw from only their own bank without repeating a question for a team; full bank size determines availability. Legacy rooms still use their separate global pool and configured limit. |
| Continuous phases | ANSWER_QUESTION and CLAIM_REWARD were Preparation-only. Advancing to Battle expired both pending questions and pending rewards. | Both actions allowed throughout Preparation/Battle; phase transition preserves pending state and question timer. |
| Answer submission | Final-answer policy and expiry existed; repeats raised validation errors. | Uploaded questions return the already committed result on teammate/repeated submissions; never regrade or issue another entitlement. |
| Public CRUD | Global question CRUD used AllowAny and serialized answer_key. | Staff-only global question administration; imported records immutable through CRUD. Owner-only paginated upload preview. |
| Realtime | Existing ordered outbox, private-event redaction, snapshots, gap recovery and wallet/unlock events. Quiz events omitted usable question data. | Existing quiz events now include public team-question state and progress, scoped to the authorized team. Snapshot restores progress. |
| Battle UI REST reconciliation | Any combat event could make a question response appear stale, leaving the HUD empty during a busy battle. | Separate quiz sequence tracks quiz changes independently of combat ticks. |
| Snapshot performance | Original query-budget regression requires at most eight queries. | All progress counts, total and pending entitlement aggregate in one query; original budget test passes. |

Phaser scene construction, movement, attack damage, deployment prices/capacities, target selection,
round income and existing combat lifecycle are preserved. Modal state blocks pointer placement;
it does not pause the scene or server scheduler.

There is no Git metadata in this supplied checkout, so the audit and changes were performed
directly in the existing workspace. No production database was used for verification.
