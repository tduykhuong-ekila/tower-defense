# Army control, map and quiz audit

Confirmed against the repository on 2026-10-24, before implementation.

- `questions/services.py` requires `advance_from` to match the terminal question. `questions/views.py` exposes a separate NEXT action, and `QuestionModal.tsx` renders “Câu hỏi tiếp theo”. `BattlePage.tsx` otherwise opens only the existing question. The countdown already uses a persistent server deadline; CLOSE does not pause it. GET, snapshots and timer reconciliation must retain their non-advancing behavior.
- Pending rewards already use a unique team-question claim. Continuous matches do not schedule legacy phase-transition reward grace deadlines; retain existing reward rules and never advance past PENDING_REWARD.
- `combat/map.py` versions 3/4 check circular 70-pixel base-center clearance. `BattleScene.ts` displays a 137×137 base at origin (0.5, 0.88), extending about 121 pixels above its anchor. Its input area extends 120 pixels upward. This asymmetric footprint is not protected by the circle; it can cover Red's lower-sector slots after isometric projection. Slots already use authoritative graph coordinates; depth alone cannot fix the overlap. Tower artwork is 94×94 and also extends upward. A versioned new layout must protect full rendered/input rectangles, while retaining saved layouts.
- `BattleScene.ts` has entity inspection, rings and stable visual IDs, but no army selection. Ordinary dragging pans the camera. Rectangle selection needs a distinct mode to preserve pan and pinch zoom.
- `UnitService.set_team_target` changes all team troop targets without selection or idempotency. It is the legacy TARGET_SELECTED socket action. `GameAction` already supplies durable per-team idempotency; new tactical commands should extend it.
- `ContinuousEngine` resolves a strategic enemy every tick. Without an explicit order, retreat or returned troops would immediately acquire an enemy again. Combat acquisition must skip retreat/at-rally attackers while retaining them as valid victims.
- `formation.initialize_route` can only continue forward on the current edge before rerouting. The graph itself is bidirectional and can route home; selecting either current-edge endpoint using remaining physical route cost allows legal reversals without changing world position.
- `ContinuousCombatService.tick`, deployments and snapshots serialize through the match row lock, and `record_match_event` broadcasts after commit. Tactical commands can use that same boundary and event sequence instead of adding a queue or simulation manager.
- `matchStore.ts` already reconciles full COMBAT_TICK entity updates. Extend this handling to command events, with snapshots carrying persistent orders for reconnects.

No AGENTS.md was present in this workspace or its ancestor directories. This workspace has no Git metadata. Existing art, balance, upgrade rules, cameras and map topology can be retained.
