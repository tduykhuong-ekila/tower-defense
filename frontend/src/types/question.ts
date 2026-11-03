import { RewardOptions } from './reward';

export interface QuestionProgress {
  answered: number; correct: number; total: number; remaining: number;
  exhausted: boolean; pending_reward_id: string | null;
}

export type QuestionType =
  | 'MULTIPLE_CHOICE'
  | 'SHORT_TEXT'
  | 'PUZZLE'
  | 'MEMORY'
  | 'DECODE';

export type QuestionStatus =
  | 'PENDING_QUESTION'
  | 'ANSWER_SUBMITTED'
  | 'ANSWER_CORRECT'
  | 'ANSWER_INCORRECT'
  | 'PENDING_REWARD'
  | 'REWARD_CLAIMED'
  | 'EXPIRED';

export interface QuestionOption {
  key: string;
  text: string;
}

export interface Question {
  id: string;
  type: QuestionType;
  category: string;
  difficulty: 'EASY' | 'MEDIUM' | 'HARD';
  content: string;
  options?: Array<QuestionOption | string>;
  time_limit_seconds: number;
  explanation?: string;
}

export interface TeamQuestion {
  id: string;
  match_id: string;
  team_id: string;
  sequence_number: number;
  status: QuestionStatus;
  assigned_at: string;
  expires_at: string;
  timer?: {status: "NOT_STARTED" | "RUNNING" | "PAUSED" | "EXPIRED" | "COMPLETED"; remaining_ms: number; version: number; server_now: string; deadline_at?: string | null};
  submitted_at?: string | null;
  submitted_answer?: string;
  is_correct?: boolean | null;
  question: Question;
  time_remaining_seconds: number;
  reward_options?: RewardOptions | null;
}

// Backwards-compatible alias
export type TeamQuestionState = TeamQuestion;
