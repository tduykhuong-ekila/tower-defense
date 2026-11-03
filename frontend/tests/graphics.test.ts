import test from "node:test";
import assert from "node:assert/strict";
import {
  canPlaceTower,
  isPointerClick,
  movementEdges,
  projectMap,
  ServerMap,
  teamIndex,
} from "../src/game/map";
import { useMatchStore } from "../src/stores/matchStore";
import { ServerEnvelope } from "../src/types/realtime";
const map: ServerMap = {
  num_teams: 8,
  team_ids: Array.from({ length: 8 }, (_, i) => `t${i + 1}`),
  nodes: Array.from({ length: 8 }, (_, i) => ({
    node_id: `node_base_t${i + 1}`,
    node_type: "base",
    team_index: i + 1,
    is_passable: true,
    x: 400 * Math.cos((i * Math.PI) / 4),
    y: 400 * Math.sin((i * Math.PI) / 4),
  })),
  edges: [{ from: "node_base_t1", to: "node_base_t2" }],
};
const event = (
  type: string,
  sequence: number,
  payload: unknown,
): ServerEnvelope => ({
  event_id: `e${sequence}`,
  match_id: "m1",
  event_type: type,
  sequence_number: sequence,
  server_timestamp: "2026-10-16T00:00:00Z",
  payload,
});
test("projects every server branch, preserving IDs and team ownership for eight teams", () => {
  const projected = projectMap(map);
  assert.equal(projected.size, 8);
  assert.equal(teamIndex(map, "t8"), 7);
  for (const n of projected.values()) {
    assert.ok(n.worldX >= 0 && n.worldX <= 1600);
    assert.ok(n.worldY >= 0 && n.worldY <= 1040);
  }
  assert.equal(movementEdges(map).length, 1);
});
test("build validation rejects foreign, occupied and nonexistent slots, permits destroyed slot reuse", () => {
  const slots = ["node_tower_t1_slot1"];
  assert.ok(canPlaceTower(slots[0], slots, []));
  assert.ok(!canPlaceTower("node_tower_t2_slot1", slots, []));
  assert.ok(
    !canPlaceTower(slots[0], slots, [
      { current_node_id: slots[0], entity_kind: "TOWER", status: "ACTIVE" },
    ]),
  );
  assert.ok(
    canPlaceTower(slots[0], slots, [
      { current_node_id: slots[0], entity_kind: "TOWER", status: "DESTROYED" },
    ]),
  );
});
test("camera drag and multi-touch never become placement clicks", () => {
  assert.ok(isPointerClick({ x: 10, y: 10 }, { x: 12, y: 11 }));
  assert.ok(!isPointerClick({ x: 10, y: 10 }, { x: 20, y: 10 }));
  assert.ok(!isPointerClick({ x: 10, y: 10 }, { x: 10, y: 10 }, true));
});
test("deployment upserts by ID, uses real server HP and ignores duplicate and stale events", () => {
  useMatchStore.getState().reset();
  useMatchStore.getState().setCurrentTeamId("t1");
  const payload = {
    entity_id: "u1",
    team_id: "t1",
    unit_code: "infantry",
    current_hp: 40,
    max_hp: 40,
    current_node_id: "node_spawn_t1",
    coins_after: 85,
    status: "QUEUED",
  };
  useMatchStore.getState().applyEvent(event("UNIT_DEPLOYED", 1, payload));
  useMatchStore.getState().applyEvent(event("UNIT_DEPLOYED", 2, payload));
  useMatchStore
    .getState()
    .applyEvent(event("COINS_UPDATED", 1, { team_id: "t1", new_balance: 999 }));
  const state = useMatchStore.getState();
  assert.equal(state.entities.length, 1);
  assert.equal(state.entities[0].current_hp, 40);
  assert.equal(state.coins, 85);
});
test("combat reconciliation follows server movement, HP, destruction, shield and income", () => {
  useMatchStore.getState().reset();
  useMatchStore.getState().setCurrentTeamId("t1");
  useMatchStore.setState({
    teams: [
      {
        id: "t2",
        name: "Enemy",
        base_hp: 500,
        initial_base_hp: 500,
        base_shield: 0,
        status: "ACTIVE",
      },
    ],
  });
  useMatchStore
    .getState()
    .applyEvent(
      event("UNIT_DEPLOYED", 1, {
        entity_id: "u1",
        team_id: "t1",
        unit_code: "infantry",
        current_hp: 40,
        max_hp: 40,
        current_node_id: "node_spawn_t1",
        coins_after: 85,
      }),
    );
  useMatchStore.getState().applyEvent(
    event("COMBAT_RESOLVED", 2, {
      round_number: 1,
      events: [
        { type: "UNIT_MOVED", entity_id: "u1", to_node: "node_lane_t1_2" },
        {
          type: "TOWER_ATTACKED",
          target_entity_id: "u1",
          target_hp_remaining: 25,
        },
        { type: "BASE_DAMAGED", target_team_id: "t2", base_hp_remaining: 490 },
        { type: "SHIELD_GENERATED", team_id: "t2", shield_amount: 40 },
        { type: "INCOME_AWARDED", team_id: "t1", new_balance: 95 },
      ],
    }),
  );
  let state = useMatchStore.getState();
  assert.equal(state.entities[0].current_node_id, "node_lane_t1_2");
  assert.equal(state.entities[0].current_hp, 25);
  assert.equal(state.teams[0].base_hp, 490);
  assert.equal(state.teams[0].base_shield, 40);
  assert.equal(state.coins, 95);
  state.applyEvent(
    event("COMBAT_RESOLVED", 3, {
      round_number: 2,
      events: [
        { type: "ENTITY_DESTROYED", entity_id: "u1" },
        { type: "TEAM_ELIMINATED", team_id: "t2" },
      ],
    }),
  );
  state = useMatchStore.getState();
  assert.equal(state.entities.length, 0);
  assert.equal(state.teams[0].status, "ELIMINATED");
  assert.equal(state.teams[0].base_hp, 0);
});
