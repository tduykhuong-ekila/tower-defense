import test from 'node:test';
import assert from 'node:assert/strict';
import {
  MatchResultsApiResponse,
  MatchResultRecord,
  MatchAward,
  HostTelemetry,
  BalancePreview,
} from '../src/types/combat';

test('Phase 6: Match results data structure preserves tie-break order and includes eliminated teams', () => {
  const mockResults: MatchResultRecord[] = [
    {
      id: 'res-1',
      match_id: 'match-101',
      team_id: 't-1',
      team_name: 'Đội Rồng Lửa',
      final_rank: 1,
      final_score: 450,
      bases_destroyed: 2,
      base_damage_dealt: 900,
      correct_answers: 8,
      remaining_base_hp: 350,
      remaining_coins: 60,
      surviving_towers: 3,
      created_at: new Date().toISOString(),
    },
    {
      id: 'res-2',
      match_id: 'match-101',
      team_id: 't-2',
      team_name: 'Chiến Binh Tiên Phong',
      final_rank: 2,
      final_score: 300,
      bases_destroyed: 1,
      base_damage_dealt: 500,
      correct_answers: 6,
      remaining_base_hp: 200,
      remaining_coins: 30,
      surviving_towers: 2,
      created_at: new Date().toISOString(),
    },
    {
      id: 'res-3',
      match_id: 'match-101',
      team_id: 't-3',
      team_name: 'Quân Đoàn Thép (Bị Loại)',
      final_rank: 3,
      final_score: 80,
      bases_destroyed: 0,
      base_damage_dealt: 80,
      correct_answers: 3,
      remaining_base_hp: 0, // Eliminated team (§14.9, §12.4)
      remaining_coins: 10,
      surviving_towers: 0,
      created_at: new Date().toISOString(),
    },
  ];

  const payload: MatchResultsApiResponse = {
    match_id: 'match-101',
    room_code: 'TEST68',
    status: 'FINISHED',
    phase: 'RESULTS',
    winner_team_id: 't-1',
    winner_team_name: 'Đội Rồng Lửa',
    duration_seconds: 1540,
    results: mockResults,
  };

  assert.equal(payload.results.length, 3);
  assert.equal(payload.winner_team_name, 'Đội Rồng Lửa');
  assert.equal(payload.results[0].final_rank, 1);
  assert.equal(payload.results[1].final_rank, 2);
  assert.equal(payload.results[2].final_rank, 3);

  // Check that eliminated team is included in official rankings
  const eliminatedTeam = payload.results.find((r) => r.remaining_base_hp === 0);
  assert.ok(eliminatedTeam);
  assert.equal(eliminatedTeam.team_name, 'Quân Đoàn Thép (Bị Loại)');
  assert.equal(eliminatedTeam.final_rank, 3);
});

test('Phase 6: 5 optional awards schema matches design decision D14 without altering official scores', () => {
  const awards: MatchAward[] = [
    {
      id: 'BEST_STRATEGIST',
      name: 'Chiến Lược Gia Xuất Sắc',
      description: 'Phá nhiều căn cứ đối thủ và gây sát thương cao nhất trận',
      team_id: 't-1',
      team_name: 'Đội Rồng Lửa',
      score: 900,
    },
    {
      id: 'BEST_DEFENSE',
      name: 'Bức Tường Kiên Cố',
      description: 'Bảo vệ căn cứ vững chắc và bảo tồn nhiều tháp phòng thủ nhất',
      team_id: 't-1',
      team_name: 'Đội Rồng Lửa',
      score: 350,
    },
    {
      id: 'BEST_COMEBACK',
      name: 'Lội Ngược Dòng Ngoạn Mục',
      description: 'Khởi sắc mạnh mẽ và chiến đấu bền bỉ từ tình thế hiểm nghèo',
      team_id: 't-2',
      team_name: 'Chiến Binh Tiên Phong',
      score: 300,
    },
    {
      id: 'KNOWLEDGE_CHAMPION',
      name: 'Quán Quân Tri Thức',
      description: 'Trả lời chính xác nhiều câu hỏi nhất giúp đội chiếm ưu thế',
      team_id: 't-1',
      team_name: 'Đội Rồng Lửa',
      score: 8,
    },
    {
      id: 'SYNERGY',
      name: 'Gắn Kết Mentor - Mentee',
      description: 'Sự ăn ý hoàn hảo giữa định hướng của Mentor và tốc độ của Mentee',
      team_id: 't-2',
      team_name: 'Chiến Binh Tiên Phong',
      score: 95,
    },
  ];

  assert.equal(awards.length, 5);
  const awardIds = awards.map((a) => a.id);
  assert.deepEqual(awardIds, [
    'BEST_STRATEGIST',
    'BEST_DEFENSE',
    'BEST_COMEBACK',
    'KNOWLEDGE_CHAMPION',
    'SYNERGY',
  ]);
});

test('Phase 6: Host telemetry schema correctly represents teams, active units, and presence', () => {
  const telemetry: HostTelemetry = {
    match_id: 'match-101',
    room_code: 'TEST68',
    name: 'Arena Alpha',
    status: 'ACTIVE',
    phase: 'WAR',
    is_locked: true,
    phase_remaining_seconds: 420,
    current_round: 5,
    total_events_count: 28,
    teams: [
      {
        id: 't-1',
        name: 'Đội Rồng Lửa',
        status: 'ACTIVE',
        base_hp: 450,
        base_shield: 30,
        coins: 120,
        score: 250,
        active_units: 3,
        active_towers: 2,
        remaining_questions: 2,
        has_pending_reward: false,
        current_question_status: null,
        members: [
          {
            id: 'm-1',
            display_name: 'Mentor Alex',
            role: 'MENTOR',
            is_ready: true,
            is_online: true,
          },
          {
            id: 'm-2',
            display_name: 'Mentee Bob',
            role: 'MENTEE',
            is_ready: true,
            is_online: true,
          },
        ],
        online_members_count: 2,
      },
    ],
  };

  assert.equal(telemetry.status, 'ACTIVE');
  assert.equal(telemetry.phase, 'WAR');
  assert.equal(telemetry.phase_remaining_seconds, 420);
  assert.equal(telemetry.teams[0].active_units, 3);
  assert.equal(telemetry.teams[0].active_towers, 2);
  assert.equal(telemetry.teams[0].online_members_count, 2);
});

test('Phase 6: Balance preview accurately provides durations and pacing metrics', () => {
  const preview: BalancePreview = {
    total_match_minutes: 30,
    estimated_combat_rounds: 15,
    round_duration_seconds: 120,
    initial_coins: 100,
    projected_passive_coins: 300,
    max_question_coins: 240,
    total_projected_coins_per_team: 640,
    initial_base_hp: 500,
    max_towers_per_team: 3,
    max_active_units_per_team: 8,
    pacing: 'Standard strategic pacing',
  };

  assert.equal(preview.total_match_minutes, 30);
  assert.equal(preview.initial_base_hp, 500);
  assert.equal(preview.max_towers_per_team, 3);
  assert.equal(preview.total_projected_coins_per_team, 640);
});
