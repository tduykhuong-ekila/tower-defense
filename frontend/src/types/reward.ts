export type RewardType = 'COIN' | 'UNLOCK';

export interface EligibleUnit {
  id: string;
  code: string;
  name: string;
  category: 'UNIT' | 'TOWER' | 'SPECIAL';
  description: string;
  cost: number;
  hp: number;
  damage: number;
  range: number;
  movement?: number;
  movement_speed?: number;
  strategic_role?: string;
}

export interface RewardOptions {
  team_question_id: string;
  coin_amount: number | null;
  coin_distribution?: Array<{ amount: number; probability_percent: number }>;
  unlock_available: boolean;
  message: string;
  eligible_units: EligibleUnit[];
}

export interface RewardClaim {
  id: string;
  team_question_id: string;
  team_id: string;
  reward_type: RewardType;
  coin_amount: number;
  unlocked_unit?: EligibleUnit | null;
  team_coins: number;
  unlocked_unit_codes: string[];
  status: string;
  idempotency_key?: string;
  claimed_at: string;
}
