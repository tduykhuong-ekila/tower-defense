# Infantry animation audit — 2026-10-22

## Findings recorded before implementation

Reproduction: `INFANTRY_AUDIT_BASELINE=1 node frontend/tests/infantry-animation.browser.mjs`, using real React/Phaser, authenticated WebSockets and a temporary Django database. Twenty Infantry deployed from the same rally area, then moved for seven seconds. Evidence: `docs/qa/infantry-animation-before.json` and `infantry-animation-before.png`.

Measured **421 frames, 34 combat ticks, 74 in-viewport visibility transitions, 134 animation starts, zero sprite identity changes**, approximately 60 FPS. Thirteen soldiers changed visibility repeatedly. Only six of twenty sprites were visible at the end despite all remaining alive. This reproduces the reported blinking without deaths, camera motion, reconnection, missing assets or a scene restart.

## Confirmed causes

1. `BattleScene.update` rebuilt a Set of 38 × 30 screen cells every 100 ms. `claimCrowdCell` showed only the first ID in a cell. Ordinary continuous movement across the fixed grid changed cell membership and repeatedly toggled individual roots' `visible` properties. Culling also paused/resumed their animations. This was not sprite destruction: the entity registry and object identities remained stable.
2. Walking was inferred from the distance rendered in one frame. At the end of an interpolation buffer, even a still-moving authoritative unit stopped its animation immediately. The next packet restarted it. Hiding a walking sprite compounded this: Phaser pause marks it not playing, which the walking code interpreted as requiring a new `play` call when it reappeared.
3. Reconnect snapshots lacked the simulation timestamp carried by tick deltas. `MotionTrack` could mix receive-time samples with simulation-time samples in one history, rejecting a later valid tick. This timing defect follows from the code path; it is distinct from the measured visibility root cause. Existing socket/store sequence checks already reject older snapshots and duplicate events.

## Backend baseline and authority

- `combat/balance.py`: Infantry movement factor **6**, HP **80**; other troop movement factor **4**. Actual distance/second is `movement × persisted reference_hop_length / movement_baseline_round_seconds × factor`. Catalog movement stays 1; no additional multiplier is needed.
- `ContinuousEngine`: default cooldown **2.0 seconds** from the entity override or match configuration. Every entity persists `simulation_state.attack_remaining` in JSON and database checkpoints. Default fixed step is **200 ms**, configurable from 100–1000 ms. The old code clamped negative remainder and reset the full cooldown on a shot; simply dividing by 1.5 would round 1⅓ seconds up to 1.4 seconds at 200 ms and lose part of the requested increase.
- Damage is server-only: one intent applies damage once, then emits an attack event. Infantry's unupgraded hit remains **5 HP**, cost **15 coins**. Target acquisition, tower-before-unit tiers, rally offsets, simultaneous independent Infantry movement, unlimited paid deployment and transaction/deadline idempotency already exist.

## Hypotheses checked and ruled out as the reproduced cause

- `visuals` is keyed by authoritative ID. Reconciliation updates existing objects; pooling occurs only on removal. No position/HP/fire update recreates a sprite.
- All eighty Infantry SVG frames exist, have the same 64 × 64 canvas and include the complete body. BootScene preloads them and registers twenty shared four-frame walk animations; the scene does not reload textures while moving.
- Live movement has one position writer: `MotionTrack` → `BattleScene.update`. Live shot recoil changes the child sprite's angle, and idle bobbing changes its local Y; neither writes the root's interpolated position. Legacy movement tweens run outside continuous battle.
- Root depth follows world Y; status alpha is 0.4 only for disabled entities. Spawn/death fades have legitimate lifecycle triggers. No camera visibility flags or texture resets occur per live packet.
- `PhaserGame` creates/destroys its game in an empty-dependency effect. State, callbacks and wallet changes update the same scene. Map recreation is keyed to arena/team identity. BattlePage registers one socket listener with cleanup; WebSocketClient deduplicates IDs/sequences, buffers gaps and chunked snapshots, and requests recovery.

## Implementation direction

Remove unstable screen-cell hiding; keep viewport/overview culling and bounded cosmetic effects. Retain one sprite per living authoritative entity. Use authoritative movement state with buffered-motion fallback for walking transitions, and distinguish a paused animation from a different animation. An actual stopped packet should settle into idle after interpolation drains; missing packets should not restart walking every frame. Preserve event-driven weapon recoil/projectiles without changing root motion.

Set the Infantry movement factor to 7. Divide only Infantry's configured cooldown by 1.5. Carry fractional tick overshoot while continuously engaged, discard overdue idle debt, and keep checkpointed cooldown state. Do not change global tick duration, damage, HP, cost or other unit cooldown policy.

Add simulation-time metadata to snapshots and normalize snapshot entities in the store, so the existing bounded, timestamped road-polyline track remains consistent across recovery. Test visibility/object/animation stability in Chrome, deterministic fire counts and damage, restart persistence, stale events, and both multiplayer directions. Measure larger armies after removing the faulty culling before claiming performance characteristics.

## Additional confirmed cause during validation

After removing screen-cell culling and fixing locomotion transitions, the same movement probe recorded 40 animation starts for 20 units. `BattlePage` calls `skipCombat()` on a recovery snapshot, and `finishPlayback()` unconditionally stopped every sprite, including live continuous units. Restricting those stops to legacy replay reduced the measurement to **20 starts**, one per unit. An explicit live sync request now preserves animation phase as well as sprite identity. This is separate from timestamp normalization and does not change authoritative state.

## Verified result

Final movement probe: **437 frames, 34 combat ticks, zero visibility transitions, zero identity changes, zero inactive/transparent/missing-texture frames, 20 walk starts for 20 soldiers**. All twenty remained rendered. FPS samples: 62, 60, 60, 60, 60, 60, 60, 60. Explicit recovery, offscreen pause/resume and a 500 ms held-packet gap did not restart walking. Camera overview still deliberately hides troop detail; outside-viewport sprites retain their objects and resume their current animation.

Evidence: `docs/qa/infantry-animation-after.json`, `infantry-animation-after.png`. The tests use seven-second local Chrome samples and do not establish internet-latency or many-room capacity. Broader combat, load and acceptance results are recorded in [the implementation report](INFANTRY_FIRE_RATE_MOVEMENT_FIX.md).


A subsequent 300-entity controlled rendering fixture crossed screen boundaries for 181 frames with **zero visibility/identity changes and zero additional scene objects**. Fifteen exact positions remained represented by fifteen persistent visible bodies. Large-army overlap culling was added only after the unrestricted rendering measurement showed a performance cost; see the implementation report for before/after load numbers.
