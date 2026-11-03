# Formation and realtime audit — 2026-10-21

## Baseline

- Effective speed = catalog movement × stored mean route hop length / movement_baseline_round_seconds × **0.75**. All three standard mobile types have movement=1; with reference hop 80 and baseline 30 s each moves **2 world units/s**. Real routes use their own mean hop length.
- Formation used gap 12 plus the full 43/68 px texture diagonal divided by minimum map projection .86. Two Infantry centers measured **82.710678 world units** apart; Tank/Tank was 123.82. Actual opaque Infantry body occupies about 34×38 displayed pixels. Padding, diagonal inflation and gap compounded.
- Baseline `pytest tests/test_live_battle_gameplay.py -q`: **16 passed**. These tests did not cover lost snapshot responses or half-open sockets.

## End-to-end trace and confirmed defects

1. REST and consumer commands call the same unit/construction services: lock Match then Team, spend atomically, create stable GameEntity IDs, record MatchEvents. Tick writes also lock Match. Retain these guarantees.
2. MatchService.record_match_event locks Match for a durable monotonic sequence and publishes with transaction.on_commit. RealtimeService sends to match.UUID; consumer subscribes before snapshot. Private events are redacted while retaining the common sequence. No group-name or event-name mismatch was found here.
3. broadcasted_at is an existing outbox marker retried by MatchScheduler. group_send acceptance cannot guarantee subscriber receipt, including channel capacity drops. Failure logs lacked event/match/sequence context and traceback.
4. websocket.ts requestSync set syncPending even offline and never timed out. A lost response blocked every subsequent repair. No heartbeat detected connected-but-dead sockets. Reconnect stopped after eight failures, and remote code 1000 disabled reconnect even while mounted. Old socket callbacks could mutate new connection state after switching rooms.
5. Initial deltas could set an arbitrary cursor before a complete snapshot. COMBAT_TICK updates known entities only, so a missing spawn remained invisible until snapshot. Buffering must start at connection establishment.
6. matchStore.applySnapshot let sequence **0** bypass the stale guard, potentially erasing a newer board.
7. PhaserGame discarded live effects before battle-ready. Latest scene state was retained, but attacks/deaths were dropped. BattleScene movement signatures omitted simulation time, potentially spreading resumed movement across a preceding stationary interval.
8. BattlePage auxiliary REST refreshes already reject results overtaken by socket sequences. Phaser already maintains an entity-ID Map and restores latest state on boot. Keep both; gameplay deltas need no map rebuild.

## Reproduction scope

Baseline speed/spacing were measured in the pure engine. Transport defects were confirmed by control-flow inspection and new deterministic regression tests. Browser/load measurements after the fixes are recorded separately. This audit does not claim production Redis/network reproduction of the original intermittent symptom.
