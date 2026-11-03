import test from 'node:test';
import assert from 'node:assert/strict';
import { renderToStaticMarkup } from 'react-dom/server';
import { createElement } from 'react';
import { QuestionBankUpload } from '../src/components/QuestionBankUpload';
import { actionAvailability } from '../src/game/actionAvailability';
import { useMatchStore } from '../src/stores/matchStore';

const event = (type: string, seq: number, payload: any) => ({ event_id: String(seq), match_id: 'm', event_type: type, sequence_number: seq, server_timestamp: '', payload });

test('creation upload offers the actual XLSX format and a labelled file input', () => {
  const html = renderToStaticMarkup(createElement(QuestionBankUpload, { onChange: () => {} }));
  assert.match(html, /accept=".xlsx"/);
  assert.match(html, /Tệp ngân hàng câu hỏi/);
  assert.match(html, /STT · Câu hỏi · A–D · Đáp án/);
});

test('quiz eligibility persists across major rounds but honors pause, spectator and completion', () => {
  const context: any = { match: { status: 'ACTIVE', phase: 'WAR', configuration: { gameplay_mode: 'CONTINUOUS', current_round: 3, timer_state: { round_phase: 'BATTLE' } } }, team: { id: 'a', status: 'ACTIVE' }, spectator: false, connection: 'connected', modal: false, pending: false };
  for (const action of ['ANSWER_QUESTION', 'CLAIM_REWARD']) {
    assert.equal(actionAvailability(context, action).allowed, true);
    for (const status of ['PAUSED', 'FINISHED', 'LOBBY']) assert.equal(actionAvailability({ ...context, match: { ...context.match, status } }, action).allowed, false);
    assert.equal(actionAvailability({ ...context, spectator: true }, action).allowed, false);
    assert.equal(actionAvailability({ ...context, modal: true }, action).allowed, false);
  }
});

test('team quiz events carry recoverable question data without touching battlefield or combat clock', () => {
  const store = useMatchStore.getState(); store.reset(); store.setCurrentTeamId('a');
  store.applyEvent(event('UNIT_DEPLOYED', 1, { entity_id: 'unit', team_id: 'a', current_hp: 80, max_hp: 80 }));
  const entities = useMatchStore.getState().entities;
  const question: any = { id: 'q', team_id: 'a', status: 'PENDING_QUESTION', question: { content: 'Question', options: [] } };
  const progress = { answered: 0, correct: 0, total: 20, remaining: 20, exhausted: false, pending_reward_id: null };
  store.applyEvent(event('QUESTION_ASSIGNED', 2, { team_id: 'a', question_state: question, question_progress: progress }));
  assert.equal(useMatchStore.getState().currentQuestion?.id, 'q');
  store.applyEvent(event('COMBAT_TICK', 3, { entity_updates: [], events: [] }));
  assert.equal(useMatchStore.getState().lastQuestionSequence, 2);
  const answered = { ...question, status: 'PENDING_REWARD', reward_options: { team_question_id: 'q', coin_amount: 20 } };
  store.applyEvent(event('QUESTION_ANSWERED_CORRECT', 4, { team_id: 'a', question_state: answered, question_progress: { ...progress, answered: 1, correct: 1 } }));
  assert.equal(useMatchStore.getState().pendingReward?.coin_amount, 20);
  assert.equal(useMatchStore.getState().questionProgress?.answered, 1);
  assert.deepEqual(useMatchStore.getState().entities, entities);
  const own = useMatchStore.getState().currentQuestion;
  store.applyEvent(event('REWARD_CLAIMED', 5, { team_id: 'b', balance_after: 999, unlocked_unit_code: 'tank', question_progress: { answered: 20 } }));
  assert.equal(useMatchStore.getState().currentQuestion, own);
  assert.equal(useMatchStore.getState().coins, 100);
  assert.equal(useMatchStore.getState().questionProgress?.answered, 1);
  store.applyEvent(event('QUESTION_ANSWERED_INCORRECT', 4, { team_id: 'a', question_state: question }));
  assert.equal(useMatchStore.getState().currentQuestion, own);
  store.reset();
});
