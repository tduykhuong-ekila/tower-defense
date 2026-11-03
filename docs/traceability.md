# Requirements Traceability Matrix (RTM)

> Tài liệu ma trận truy xuất nguồn gốc yêu cầu (Traceability Matrix) kết nối các yêu cầu chức năng (FR-01 → FR-10) và các tình huống tích hợp (Scenario A → H) tới các thành phần mã nguồn, API, WebSocket và Kiểm thử tự động.

## 1. Ma Trận Yêu Cầu Chức Năng (Functional Requirements)

| Mã FR | Tên Yêu Cầu | Backend Module | Frontend Component / Screen | Database Models | API Endpoints | WebSocket Events | Test Cases Trọng Tâm |
|:---|:---|:---|:---|:---|:---|:---|:---|
| **FR-01** | Lobby Management | `apps.matches.services.MatchService` | `pages/LobbyPage.tsx`<br>`pages/JoinMatchPage.tsx` | `Match`, `Team`, `TeamMember` | `POST /matches/`<br>`GET /matches/{id}/`<br>`POST /matches/{id}/join/`<br>`POST /matches/{id}/start/` | `MATCH_STATE_SNAPSHOT`<br>`MATCH_PHASE_CHANGED`<br>`READY_CHANGED` | `test_create_match`<br>`test_join_match_with_unique_code`<br>`test_unauthorized_lobby_edit` |
| **FR-02** | Team Dashboard | `apps.teams.services.TeamService` | `pages/BattlePage.tsx`<br>`components/game/TeamStatus.tsx` | `Team`, `TeamMember`, `GameEntity` | `GET /matches/{id}/teams/{team_id}/state/` | `MATCH_STATE_SNAPSHOT`<br>`COINS_UPDATED`<br>`BASE_DAMAGED` | `test_team_state_isolation`<br>`test_reconnect_snapshot_accuracy` |
| **FR-03** | Question Engine | `apps.questions.services.QuestionService`<br>`apps.questions.validators` | `components/game/QuestionModal.tsx` | `Question`, `TeamQuestion` | `GET /matches/{id}/questions/current/`<br>`POST /matches/{id}/questions/{id}/answer/` | `QUESTION_ASSIGNED`<br>`ANSWER_RESULT` | `test_answer_validation`<br>`test_expired_question_rejection`<br>`test_no_answer_leak_in_payload` |
| **FR-04** | Reward Selection | `apps.rewards.services.RewardService` | `components/game/RewardModal.tsx`<br>`components/game/UnlockSelection.tsx` | `RewardClaim`, `TeamUnlock`, `UnitType` | `POST /matches/{id}/rewards/claim/` | `REWARD_OPTIONS`<br>`REWARD_APPLIED` | `test_claim_coin_reward`<br>`test_claim_unlock_reward`<br>`test_all_units_unlocked_disable`<br>`test_idempotent_duplicate_claim` |
| **FR-05** | Economy System | `apps.economy.services.EconomyService` | `components/game/BattleBoard.tsx` (Top bar coin balance) | `CoinTransaction`, `Team` | (Được gọi nội bộ bởi Deploy/Build/Reward endpoints) | `COINS_UPDATED` | `test_prevent_negative_balance`<br>`test_atomic_deduction`<br>`test_passive_income_round` |
| **FR-06** | Unit & Structure Management | `apps.units.services.UnitService`<br>`apps.units.services.ConstructionService` | `components/game/UnitCard.tsx`<br>`components/game/TowerCard.tsx` | `UnitType`, `GameEntity`, `GameAction` | `POST /matches/{id}/actions/deploy/`<br>`POST /matches/{id}/actions/build/`<br>`POST /matches/{id}/actions/upgrade/`<br>`POST /matches/{id}/actions/repair/` | `UNIT_DEPLOYED`<br>`TOWER_BUILT`<br>`ACTION_ACCEPTED`<br>`ACTION_REJECTED` | `test_deploy_locked_unit_rejected`<br>`test_unit_and_tower_capacity_limits`<br>`test_invalid_placement_node` |
| **FR-07** | Combat Engine | `apps.combat.engine.CombatEngine`<br>`movement.py`, `targeting.py`, `damage.py` | `game/PhaserGame.tsx`<br>`game/scenes/BattleScene.ts`<br>`components/game/CombatLog.tsx` | `GameEntity`, `MatchEvent` | (Kích hoạt theo round tick nội bộ của server) | `COMBAT_RESOLVED`<br>`ENTITY_DESTROYED`<br>`BASE_DAMAGED`<br>`BASE_DESTROYED` | `test_deterministic_combat_resolution`<br>`test_tower_range_and_priority`<br>`test_shield_absorption_before_hp`<br>`test_base_elimination` |
| **FR-08** | Realtime Synchronization | `apps.realtime.consumers.MatchConsumer`<br>`apps.realtime.events` | `services/websocket.ts`<br>`stores/matchStore.ts` | `MatchEvent` | `GET /matches/{id}/events/` | Toàn bộ 19 sự kiện server định nghĩa trong §21 | `test_ws_auth_and_team_filtering`<br>`test_monotonic_sequence_numbers`<br>`test_sequence_gap_detection` |
| **FR-09** | Host Console | `apps.matches.services.MatchService` | `pages/HostDashboardPage.tsx` | `Match`, `Team`, `MatchEvent` | `POST /matches/{id}/pause/`<br>`POST /matches/{id}/resume/`<br>`POST /matches/{id}/end/` | `MATCH_PAUSED`<br>`MATCH_RESUMED`<br>`MATCH_ENDED` | `test_host_only_action_authorization`<br>`test_pause_freezes_combat_and_income`<br>`test_administrative_override_logged` |
| **FR-10** | Results & Leaderboard | `apps.combat.scoring.ScoringService` | `pages/ResultsPage.tsx`<br>`components/game/Leaderboard.tsx` | `MatchResult` | `GET /matches/{id}/results/` | `LEADERBOARD_UPDATED`<br>`MATCH_ENDED` | `test_final_ranking_and_tiebreakers`<br>`test_defeated_teams_preserved_in_results`<br>`test_awards_calculation` |

---

## 2. Ma Trận Kịch Bản Tích Hợp (Integration Scenarios §28)

| Kịch Bản | Mô tả Kiểm Thử | Tệp Test Tự Động Thực Hiện |
|:---|:---|:---|
| **Scenario A** | Trả lời đúng → Nhận Coin → Coin cộng chính xác 1 lần, không thể nhận lần hai | `tests/test_rewards.py::test_scenario_a_correct_answer_to_coins` |
| **Scenario B** | Trả lời đúng → Mở khóa Tank → Tank khả dụng, không trừ coin, mua được khi đủ tiền | `tests/test_rewards.py::test_scenario_b_correct_answer_to_unlock` |
| **Scenario C** | Mở khóa toàn bộ đơn vị → Tùy chọn Unlock bị vô hiệu hóa, Coin vẫn nhận bình thường | `tests/test_rewards.py::test_scenario_c_all_units_unlocked_disable` |
| **Scenario D** | Không đủ coin khi Deploy/Build → Bị từ chối, coin giữ nguyên, không tạo entity | `tests/test_economy.py::test_scenario_d_insufficient_coins` |
| **Scenario E** | Hai request chọn thưởng gửi đồng thời → Chỉ đúng 1 phần thưởng được chấp nhận (Atomic) | `tests/test_rewards.py::test_scenario_e_simultaneous_claim_requests` |
| **Scenario F** | Combat vòng đời: Deploy → Di chuyển lane → Tower bắn → Unit chết / chạm Base → Gây damage Base | `tests/test_combat.py::test_scenario_f_full_combat_loop` |
| **Scenario G** | Mất kết nối & Tái kết nối → Nhận Snapshot mới nhất, không bị replay lại action cũ | `tests/test_realtime.py::test_scenario_g_reconnection_and_snapshot` |
| **Scenario H** | Kết thúc trận (Hết giờ / Căn cứ bị phá) → Finalize snapshot bất biến duy nhất | `tests/test_matches.py::test_scenario_h_match_completion_and_results` |
