import test from "node:test";
import assert from "node:assert/strict";
import { useMatchStore } from "../src/stores/matchStore";

test("combat kill rewards update the team's balance and replay never adds coins twice", () => {
  useMatchStore.getState().reset();
  useMatchStore.setState({ currentTeamId: "a", coins: 100 });
  const event = {
    match_id: "m", event_id: "reward-1", sequence_number: 1,
    event_type: "COMBAT_TICK", server_timestamp: "",
    payload: { events: [
      { type: "KILL_REWARD_AWARDED", team_id: "a", amount: 4, new_balance: 104 },
      { type: "KILL_REWARD_AWARDED", team_id: "a", amount: 7, new_balance: 111 },
      { type: "KILL_REWARD_AWARDED", team_id: "b", amount: 12, new_balance: 112 },
    ] },
  };
  useMatchStore.getState().applyEvent(event);
  assert.equal(useMatchStore.getState().coins, 111);
  useMatchStore.getState().applyEvent(event);
  assert.equal(useMatchStore.getState().coins, 111);
  useMatchStore.getState().reset();
});
