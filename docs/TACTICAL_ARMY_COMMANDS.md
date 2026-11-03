# Tactical army commands

During active continuous matches, players can control living mobile troops owned by their team: initial gathering permits retargeting, WAR permits attack and retreat, and later resupply permits retreat. Infantry, Tanks and Artillery retain their existing speeds, stats, HP, levels and cooldowns.

## Controls

See `MAP_FIRST_ARMY_COMMANDS.md` for the current compact map-first UI and validation.

- Click friendly troops to select; Shift/Ctrl/Cmd-click toggles membership.
- In the Command context, left-drag selects a rectangle, modifier-drag adds, and Space-drag or middle-drag pans. Outside this context, normal camera dragging is retained.
- Touch supports explicit **Chọn thêm** and **Khoanh vùng** tools. Rectangle mode exits after selection; ordinary drag pans and pinch zoom preserves selection.
- Empty-terrain click, **Bỏ chọn**, or Escape clears selection, except that additive touch mode preserves the group when tapping empty terrain.
- One row shows selected count/composition. The next row contains order, destination and **Thực hiện**; there are no mandatory group-picking steps.
- Clicking a live enemy base with a selected army fills its attack destination; only **Thực hiện** sends the command. Deployment targets remain independent.
- Additional selection shortcuts, type upgrades and **Rút toàn quân…** live in the options dialog.
- Retreat of the selected group goes home without healing. All-army confirmation freezes eligible IDs and warns that troops remain vulnerable; newly deployed troops are excluded.
- Existing stable Phaser sprite instances and selection rings are retained.

## Contract

`POST /api/v1/matches/{match_id}/actions/army/`, using the existing participant or host authentication.

```json
{
  "command_type": "RETARGET",
  "unit_ids": ["<unit UUID>", "<unit UUID>"],
  "target_team_id": "<enemy team UUID>",
  "idempotency_key": "<unique request ID>"
}
```

```json
{
  "command_type": "RETREAT_ALL",
  "idempotency_key": "<unique request ID>"
}
```

Optional `expected_command_version` rejects stale commands against the match's current army-command version. The server derives team ownership from authentication; it never accepts authoritative client paths. RETARGET validates every selected entity, rejects the entire request if any is invalid, and requires an active enemy base in the same match. RETREAT_ALL accepts explicit selected unit IDs and rejects arbitrary destination targets; omitting IDs uses all eligible mobile troops at acceptance. The frontend always supplies a nonempty frozen list so selected-only actions cannot fall back to all troops. Towers and opponents are excluded.

The response includes the existing serialized `GameAction`, `affected_count`, monotonic `command_version`, full `entity_updates`, simulation time, and tick interval. A retry with the same key and normalized request returns its original acknowledgement without replaying the command; reusing the key for a different request fails. Duplicate IDs in selections are normalized.

## Movement and priority

`ArmyCommandService` holds the same match-row lock used by ticks, deployments and snapshots. The transaction validates, calculates every route, updates the complete selection, persists the existing `GameAction`, and records its event. Broadcasting occurs after commit through the existing outbox.

For a troop partway along an edge, both endpoints are evaluated using remaining edge distance plus the legal road path to the destination. The chosen first edge may run in reverse. All subsequent edges come from the existing passable, bidirectional graph. World position, cosmetic crowd offset, movement-speed reference and attack cooldown survive the transition. No teleport, healing, new routing engine, convoy leader or return queue is introduced.

Persisted `simulation_state.order` has these semantics:

| Order | Movement and combat |
| --- | --- |
| ATTACK (also the default for existing/new deployments) | Follow the strategic enemy objective and use ordinary nearby hostile acquisition. |
| RETREAT | Follow the home spawn/rally route; clear obsolete attack targets and initiate no attacks. Enemy attacks still apply. |
| AT_RALLY | Remain alive at the rally point without automatic enemy targeting. An explicit RETARGET can send the troop out again. |

Retarget overrides earlier attack/retreat/at-rally orders only for the selection. Retreat overrides orders for all currently eligible team troops. Troops deployed afterward follow their normal deployment objective. Death and match completion take precedence. Nearly simultaneous team commands are serialized by the match lock; the last accepted applicable command wins, with event sequences and command versions recording that order.

## Realtime

- `UNITS_RETARGETED`: full selected entity updates, command version and affected count.
- `ARMY_RETREAT_ORDERED`: full returning entity updates, command version and affected count.
- Existing `COMBAT_TICK`: subsequent movement, combat, arrival and idle updates; `UNIT_RETURNED` is a nested arrival event.
- Existing snapshots retain complete command state and physical positions for reconnects.

The frontend applies command deltas through the existing tick reconciliation path. Stable IDs and MotionTrack interpolation retain sprites, equipment and locomotion instead of recreating entities. Commands use REST; delivery to every connected client uses the established match WebSocket stream.
