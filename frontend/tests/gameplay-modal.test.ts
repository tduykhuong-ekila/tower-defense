import { useMatchStore } from "../src/stores/matchStore";
import test from "node:test";
import assert from "node:assert/strict";
import { visibleGameplayModal } from "../src/game/gameplayModal";
import type { TeamQuestion } from "../src/types/question";
import type { RewardOptions } from "../src/types/reward";

const question = {id: "q", status: "PENDING_REWARD"} as TeamQuestion;
const reward = {team_question_id: "q"} as RewardOptions;

test("expiration and claimed rewards remain visible as explicit results", () => {
  assert.equal(visibleGameplayModal("REWARD", null, null), null);
  assert.equal(visibleGameplayModal("REWARD", question, null), "REWARD");
  assert.equal(visibleGameplayModal("REWARD", {...question, status: "EXPIRED"}, reward), "QUESTION");
  assert.equal(visibleGameplayModal("QUESTION", {...question, status: "REWARD_CLAIMED"}, null), "QUESTION");
  assert.equal(visibleGameplayModal("REWARD", question, {...reward, team_question_id: "older"}), "REWARD");
});

test("valid question and reward dialogs still block battlefield input while visible", () => {
  assert.equal(visibleGameplayModal("QUESTION", {...question, status: "PENDING_QUESTION"}, null), "QUESTION");
  assert.equal(visibleGameplayModal("QUESTION", {...question, status: "ANSWER_INCORRECT"}, null), "QUESTION");
  assert.equal(visibleGameplayModal("REWARD", question, reward), "REWARD");
  assert.equal(visibleGameplayModal(null, question, reward), null);
});


test("combat victory and match-ended events retain content for an explicit terminal dialog", () => {
  const store = useMatchStore.getState(); store.reset(); store.setCurrentTeamId("a");
  const q = {...question, team_id: "a", status: "PENDING_QUESTION"} as TeamQuestion;
  useMatchStore.setState({currentQuestion: q, match: {id: "m", status: "ACTIVE", phase: "WAR", configuration: {}} as any});
  store.applyEvent({match_id: "m", event_id: "1", sequence_number: 1, server_timestamp: "", event_type: "COMBAT_RESOLVED", payload: {round_number: 1, is_match_over: true, events: []}});
  assert.equal(useMatchStore.getState().currentQuestion, q);
  store.applyEvent({match_id: "m", event_id: "2", sequence_number: 2, server_timestamp: "", event_type: "MATCH_ENDED", payload: {}});
  assert.equal(useMatchStore.getState().currentQuestion, q);
  assert.equal(useMatchStore.getState().match?.status, "FINISHED");
  assert.equal(visibleGameplayModal("QUESTION", q, null), "QUESTION");
  store.reset();
});
