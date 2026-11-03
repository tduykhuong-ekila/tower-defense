# TOWER DEFENSE: PROTECT THE BASE
## Game Design Document (GDD) & Product Requirements Document (PRD)

**Version:** 1.0  
**Status:** Ready for implementation  
**Product type:** Multiplayer browser-based strategy game  
**Primary use case:** Team-building game for Mentor–Mentee activities  
**Target audience:** Internal company teams, interns, mentors and mentees

---

# PART I. PRODUCT OVERVIEW

## 1. Product Vision

Tower Defense: Protect the Base là game chiến thuật nhiều đội chơi đồng thời. Mỗi đội sở hữu một căn cứ, ngân sách coin, các đơn vị quân và hệ thống công trình phòng thủ riêng.

Người chơi phải trả lời các câu hỏi để nhận phần thưởng, sau đó lựa chọn giữa:

- Nhận coin để tăng ngân sách chiến đấu.
- Mở khóa lính, xe, trụ phòng thủ hoặc đơn vị đặc biệt mới.

Coin được sử dụng để triển khai quân, xây công trình, nâng cấp hoặc sửa chữa căn cứ. Các đội lựa chọn mục tiêu tấn công, xây dựng chiến thuật phòng thủ và tìm cách phá hủy căn cứ đối thủ.

Game được thiết kế để kết hợp ba yếu tố:

1. **Knowledge:** Khả năng giải quyết câu hỏi và thử thách.
2. **Economy:** Quản lý tài nguyên có giới hạn.
3. **Strategy:** Lựa chọn đơn vị, mục tiêu và thời điểm hành động.

Yếu tố quan trọng nhất là sự phối hợp giữa Mentor và Mentee, thay vì chỉ kiểm tra kiến thức cá nhân.

## 2. Product Goals

### 2.1. Goals

- Cho phép 4–12 đội chơi trong một trận.
- Hỗ trợ một Mentor và từ 1–3 Mentee trong mỗi đội.
- Tạo trải nghiệm cạnh tranh, vui nhộn và dễ theo dõi trên màn hình lớn.
- Sử dụng câu hỏi như cơ chế trao thưởng và phát triển sức mạnh.
- Tạo chiều sâu chiến thuật thông qua coin, mở khóa, tấn công và phòng thủ.
- Tự động hóa tính điểm, xử lý chiến đấu và xác định đội chiến thắng.
- Cho phép quản trị viên cấu hình và tổ chức nhiều trận đấu khác nhau.

### 2.2. Non-goals for MVP

Không triển khai trong phiên bản đầu tiên:

- Matchmaking công khai trên Internet.
- Hệ thống tài khoản xã hội hoặc chat toàn cầu.
- Marketplace, giao dịch hoặc chuyển coin giữa các đội.
- Bản đồ thế giới mở.
- Pathfinding phức tạp hoặc điều khiển quân tự do.
- AI đối thủ tự động.
- Hệ thống xếp hạng dài hạn giữa nhiều mùa giải.
- Thanh toán hoặc vật phẩm mua bằng tiền thật.

## 3. Target Users and Roles

### 3.1. Administrator / Game Host

Người tổ chức trận đấu.

Quyền hạn:

- Tạo phòng chơi.
- Cấu hình trận đấu và bộ câu hỏi.
- Tạo đội và gán thành viên.
- Bắt đầu, tạm dừng, tiếp tục hoặc kết thúc trận.
- Theo dõi trạng thái các đội.
- Quản lý câu hỏi, đơn vị, giá coin và chỉ số chiến đấu.
- Xem lịch sử sự kiện và kết quả.
- Xử lý sự cố theo các quy tắc được ghi nhận.

### 3.2. Mentor

- Tham gia một đội.
- Trao đổi chiến thuật với Mentee.
- Tư vấn trả lời câu hỏi.
- Tham gia quyết định nhận coin hoặc mở khóa.
- Tham gia lựa chọn quân, công trình và mục tiêu.

### 3.3. Mentee

- Trả lời câu hỏi theo vai trò được phân công.
- Đề xuất chiến thuật.
- Tham gia quyết định sử dụng coin.
- Theo dõi trận đấu và phối hợp với Mentor.

### 3.4. Spectator

- Theo dõi bản đồ chiến đấu.
- Xem bảng xếp hạng và lịch sử sự kiện.
- Không được thực hiện hành động làm thay đổi trạng thái trận đấu.

---

# PART II. GAME DESIGN DOCUMENT

## 4. Game Structure

### 4.1. Default Match Configuration

| Parameter | Default |
|---|---|
| Teams per match | 4–8 |
| Players per team | 2–4 |
| Initial base HP | 500 |
| Initial coins | 100 |
| Match duration | 30 minutes |
| Maximum questions per team | 8 |
| Correct-answer coin reward | 20 |
| Base income | 10 coins per completed round |
| Maximum towers per team | 3 |
| Maximum active combat units per team | 5 |
| Maximum deployed units per action | 1 |
| Maximum tower placements per action | 1 |
| Combat resolution | Turn-based |
| Map | Fixed lanes |
| Victory condition | Hybrid elimination and score |

These values must be configurable by the Game Host. The implementation must not hardcode game balance values in frontend components.

### 4.2. Match Phases

A match consists of the following phases:

1. Lobby
2. Preparation
3. Build and Scout
4. War
5. Final Assault
6. Results

The Game Host may configure phase durations, but the default match duration should be approximately 30 minutes.

## 5. Core Gameplay Loop

The gameplay loop is:

**Answer Question → Select Reward → Spend Coins → Execute Actions → Resolve Combat → Update State**

### 5.1. Question Phase

Each team receives a question from the configured question bank.

Supported question types:

- Multiple-choice quiz.
- Quick code or text decoding.
- Logic puzzle.
- Memory challenge.

Each question has:

- Unique question ID.
- Question type.
- Difficulty.
- Question content.
- Answer options when applicable.
- Correct answer or server-side answer validator.
- Time limit.
- Optional explanation.
- Optional category.
- Eligibility and scheduling metadata.

Questions must be presented in a clear and readable interface.

The server is responsible for validating answers. Correct answers must never be exposed to the client before the answer is submitted or the question is closed.

### 5.2. Answering Correctly

When a team submits a correct answer:

1. The server records the answer result.
2. The server marks the question as completed for that team.
3. The server creates a pending reward selection.
4. The frontend displays two choices:
   - Receive coins.
   - Unlock a new unit or structure.
5. The team selects exactly one reward.
6. The server validates and applies the reward.
7. The question reward is marked as claimed.

There is no Action Token system in this game.

A correct answer grants a reward choice, not an automatic combat action.

### 5.3. Answering Incorrectly

When a team submits an incorrect answer:

- The team receives no reward for that question.
- No coins are deducted.
- No unit or structure is unlocked.
- The question is marked as completed.
- The game continues according to the match schedule.

For MVP, each question permits one final answer submission. The team cannot repeatedly guess the same question.

If the timer expires, the answer is treated as incorrect.

### 5.4. Question Limit

Each team may receive a maximum of eight questions per match by default.

The question limit is configurable.

The system must ensure that:

- A question cannot be rewarded more than once for the same team.
- Duplicate requests do not produce duplicate rewards.
- A team cannot claim a reward for a question it did not receive.
- A team cannot receive additional question rewards after the question limit is reached.
- Questions can be distributed fairly across teams.

For MVP, use team-specific question assignments with equivalent difficulty. Shared questions may be supported later as an alternative match configuration.

## 6. Reward Selection System

### 6.1. Reward Option A: Receive Coins

The team receives a configurable amount of coins.

Default reward: **+20 coins**.

Coins can be used for:

- Deploying combat units.
- Constructing defensive towers.
- Upgrading towers.
- Repairing the base.
- Purchasing eligible special abilities.

The coin reward is added immediately after the team confirms its choice.

### 6.2. Reward Option B: Unlock a Unit or Structure

The team selects one eligible unit or structure that it has not unlocked.

Unlocking is free.

Unlocked items remain available until the end of the current match.

Unlocking an item does not automatically deploy it. The team must still pay the item's deployment or construction cost.

For example:

- A team unlocks Tank.
- Tank becomes available in the unit selection menu.
- The team must pay the configured Tank deployment cost before deploying it.

### 6.3. Unlock Eligibility

A unit is eligible for unlocking if all of the following conditions are met:

- It is configured as unlockable.
- It is not a starter unit.
- It is not already unlocked by the team.
- Its prerequisites, if any, have been met.
- It is available in the current match configuration.

When no eligible items remain, the Unlock option must be disabled.

The interface must display a message such as:

"All units unlocked. Receive coins to continue strengthening your base."

The system must not allow the client to submit an invalid unlock request.

### 6.4. Reward Selection UI

After a correct answer, display a reward modal with two cards.

**Card A — Receive Coins**

- Coin icon.
- Reward amount.
- Short explanation.
- Confirm button.

**Card B — Unlock Unit**

- Unlock icon.
- Number of eligible items.
- Short explanation.
- Confirm button.

If the team chooses Unlock Unit, display a second selection view containing all eligible units and structures.

Each item should display:

- Name.
- Icon or image.
- Category.
- Description.
- Main statistics.
- Strategic role.

The player must select one item and confirm.

After a reward is applied, the reward modal closes and the team returns to the game.

### 6.5. Reward State Machine

Recommended states:

- `PENDING_QUESTION`
- `ANSWER_SUBMITTED`
- `ANSWER_CORRECT`
- `ANSWER_INCORRECT`
- `PENDING_REWARD`
- `REWARD_CLAIMED`
- `EXPIRED`

Valid transitions:

- `PENDING_QUESTION` → `ANSWER_SUBMITTED`
- `ANSWER_SUBMITTED` → `ANSWER_CORRECT`
- `ANSWER_SUBMITTED` → `ANSWER_INCORRECT`
- `ANSWER_CORRECT` → `PENDING_REWARD`
- `PENDING_REWARD` → `REWARD_CLAIMED`
- `PENDING_QUESTION` → `EXPIRED`

No other transitions are permitted.

A reward selection must be atomic and idempotent. If the client sends the same request twice, the team must receive the reward only once.

## 7. Coin Economy

### 7.1. Initial Resources

Each team starts with:

- 100 coins.
- 500 base HP.
- Basic Infantry unlocked.
- Basic Machine Gun Tower unlocked.
- Basic repair action available.

The Game Host can configure starter units.

### 7.2. Passive Income

Each team receives 10 coins at the end of every completed combat round.

Passive income is awarded once per round, including when the team has no available questions.

This ensures that teams which answer incorrectly or use their questions early can continue participating.

Passive income must be configurable and may be disabled for specific game modes.

### 7.3. Coin Rules

- Coin balance cannot be negative.
- Coin rewards are applied only by the server.
- Purchasing an item deducts the configured cost atomically.
- Failed purchases do not deduct coins.
- Coin cannot be transferred between teams.
- Unused coins remain available until the match ends.
- Coin balances are visible to the owning team.
- The public spectator board may display balances according to the match's visibility configuration.

### 7.4. Economic Balance

The Game Host should be able to configure:

- Starting coins.
- Correct-answer reward.
- Passive income.
- Unit costs.
- Tower costs.
- Upgrade costs.
- Repair costs.
- Special ability costs.

The system must validate all configuration values before a match begins.

## 8. Units and Structures

All initial statistics are provisional balance values. They must be configurable and tested before the first live event.

### 8.1. Starter Units

#### Infantry

| Attribute | Value |
|---|---:|
| Cost | 15 coins |
| HP | 40 |
| Attack damage | 10 |
| Movement | 1 lane node per round |
| Attack range | 1 node |
| Unlock required | No |

Role: inexpensive frontline unit that pressures defensive structures.

#### Machine Gun Tower

| Attribute | Value |
|---|---:|
| Construction cost | 25 coins |
| HP | 100 |
| Damage | 15 per combat round |
| Range | 2 lane nodes |
| Maximum per team | Included in the 3-tower limit |
| Unlock required | No |

Role: efficient defense against light units.

### 8.2. Unlockable Combat Units

#### Tank

| Attribute | Value |
|---|---:|
| Deployment cost | 35 coins |
| HP | 120 |
| Damage | 25 |
| Movement | 1 node per round |
| Attack range | 1 node |
| Unlock required | Yes |

Role: heavy frontline unit designed to absorb damage.

#### Artillery

| Attribute | Value |
|---|---:|
| Deployment cost | 45 coins |
| HP | 45 |
| Damage | 40 |
| Movement | 1 node per round |
| Attack range | 3 nodes |
| Unlock required | Yes |

Role: ranged damage dealer that attacks from behind frontline units.

Artillery must prioritize valid targets according to the configured targeting rules. It must not attack through arbitrary map barriers unless the map explicitly permits it.

### 8.3. Unlockable Defensive Structures

#### Cannon Tower

| Attribute | Value |
|---|---:|
| Construction cost | 40 coins |
| HP | 150 |
| Damage | 30 per combat round |
| Range | 3 lane nodes |
| Unlock required | Yes |

Role: anti-armor defense.

#### Shield Generator

| Attribute | Value |
|---|---:|
| Construction cost | 30 coins |
| HP | 100 |
| Shield amount | 40 |
| Cooldown | 2 completed combat rounds |
| Unlock required | Yes |

Role: protects the team's base by generating a shield.

For MVP, a Shield Generator creates a temporary base shield of 40 HP. It cannot generate another shield while the previous shield is active. Its cooldown and shield duration must be configurable.

### 8.4. Special Actions

#### Repair Base

- Cost: 20 coins.
- Restores 50 base HP.
- Cannot exceed maximum base HP.
- One repair action per team per round.

#### Upgrade Tower

- Cost: 25 coins.
- Increases tower damage by 25%.
- Applies to one eligible tower.
- Maximum one upgrade per tower in MVP.
- Upgraded statistics persist until the match ends.

#### Scout

- Cost: 10 coins.
- Reveals eligible information about one opponent's defenses.
- The information revealed must be explicitly defined in the match configuration.
- For MVP, scouting may reveal the opponent's unlocked units and defensive structures, but not their pending answer or unrevealed decisions.

#### EMP

- Cost: 30 coins.
- Disables one eligible enemy tower for one combat round.
- Does not destroy the tower.
- Cannot target the base directly.

Special actions should be implemented only after the core combat loop works reliably. The Game Host must be able to disable any special action.

### 8.5. Capacity Limits

Default limits:

- Maximum three defensive towers per team.
- Maximum five active combat units per team.
- Maximum one combat unit deployed per action.
- Maximum one tower constructed per action.
- Maximum one repair action per team per round.
- Maximum one upgrade per tower.

All limits must be enforced server-side.

A unit destroyed in combat no longer counts toward the active unit limit.

## 9. Map Design

### 9.1. MVP Map

Use a fixed-lane map with 4–8 team bases connected through predefined paths.

The map must include:

- One base per team.
- A spawn point for each team.
- Fixed lane nodes.
- Tower placement nodes.
- Valid movement paths.
- Targetable enemy bases.
- A central arena or shared lane section.

Avoid free-form movement and complex pathfinding in MVP.

### 9.2. Movement

Each combat unit follows a predefined path toward its selected target.

At the beginning of a combat resolution:

1. Validate the unit's current target.
2. Determine whether an enemy unit blocks its path.
3. Resolve movement according to the unit's movement attribute.
4. Determine valid targets.
5. Resolve attacks.
6. Update HP and remove destroyed units.
7. Apply damage to bases when units reach valid attack positions.

Units must not move through impassable nodes or bypass the configured lane topology.

### 9.3. Tower Placement

Each team has a limited number of valid tower placement nodes.

The server validates:

- The placement node belongs to the team's permitted territory.
- The node is valid and not occupied.
- The team has not exceeded its tower limit.
- The tower is unlocked.
- The team has enough coins.
- The match is in a phase that permits construction.

Invalid placement requests must return a clear error and must not deduct coins.

### 9.4. Target Selection

A team may choose one enemy base as the target for a newly deployed unit.

The target must:

- Belong to another team.
- Be active and targetable.
- Be reachable through a valid lane.

For MVP, units retain their selected target until the target is destroyed or becomes invalid.

When a target becomes invalid, the unit must be reassigned according to the configured fallback policy or remain idle until the next legal decision phase.

## 10. Combat Resolution

Combat is turn-based.

Each team submits legal actions during the planning phase. The server locks actions when the phase ends and resolves all teams' actions in a deterministic sequence.

### 10.1. Combat Round Sequence

1. Close the planning phase.
2. Validate all queued actions.
3. Deduct coins for accepted purchases.
4. Spawn new combat units.
5. Apply valid movement.
6. Resolve defensive tower attacks.
7. Resolve combat unit attacks.
8. Apply shield effects and base damage.
9. Remove destroyed units and structures.
10. Check elimination and victory conditions.
11. Award passive income.
12. Publish the new authoritative game state.

The exact order of movement and attacks must be implemented consistently. For MVP, use the sequence above and document any exceptions for ranged attacks.

### 10.2. Damage

Damage is calculated server-side.

Base formula:

`final_damage = max(1, floor(base_damage * damage_multiplier))`

The damage multiplier is 1.0 by default.

An upgraded tower uses a multiplier of 1.25.

Armor, critical hits, splash damage and damage types are outside MVP scope.

### 10.3. Targeting

Default tower targeting priority:

1. Enemy unit closest to the defended base.
2. If multiple targets have the same distance, use a deterministic tie-breaker.
3. If no valid enemy unit is in range, the tower does not attack.

A tower cannot attack units outside its configured range.

For MVP, tower attacks occur once per combat round.

### 10.4. Base Damage

When a combat unit reaches the configured base attack position, it deals its attack damage to the target base and is removed from the battlefield.

The system must apply damage to the base shield first, then to base HP.

If a base reaches zero HP, it is marked as destroyed.

### 10.5. Simultaneous Combat

All accepted team actions are locked before combat resolution.

The game engine must use a deterministic processing order so that reconnects, duplicate WebSocket messages or client latency do not change the outcome of the same locked round.

The frontend must not independently determine the combat result.

## 11. Match Phases and Timing

Default phase schedule:

| Phase | Duration | Purpose |
|---|---:|---|
| Preparation | 3 minutes | Configure initial strategy and inspect the map |
| Build and Scout | 7 minutes | Answer questions, unlock units and establish defenses |
| War | 12 minutes | Conduct repeated attacks and defenses |
| Final Assault | 5 minutes | Final strategic decisions |
| Results | 3 minutes | Calculate results and announce winners |

Total: approximately 30 minutes.

The Game Host may adjust phase duration.

Question timers are independent of the overall phase timer. A question must close when its timer expires or when the host pauses the match.

If a team has a pending reward when a phase ends, the server must either allow a short reward-selection grace period or apply a configured default policy. The recommended default is a 15-second grace period, followed by expiration without reward if no selection is made.

The system must not silently grant an arbitrary reward after the team fails to choose.

## 12. Victory Conditions

The match uses a hybrid victory system.

### 12.1. Elimination Victory

A team wins immediately if all other teams have been eliminated, provided that the team itself remains active.

A base is eliminated when its HP reaches zero.

If several bases are destroyed in the same combat resolution, apply the simultaneous-elimination rules configured for the match. The default policy is to compare the final scores of surviving and simultaneously eliminated teams, then use remaining base HP and remaining coins as tie-breakers.

### 12.2. Score Victory

If the match timer expires, calculate each team's final score.

Recommended formula:

- Each enemy base destroyed: +100 points.
- Each 100 HP of damage dealt to enemy bases: +10 points.
- Each 100 HP of remaining base HP: +5 points.
- Each correct answer: +3 points.
- Each surviving tower: +5 points.
- Each 10 remaining coins: +1 point.

For implementation, define all scoring values as configuration.

Do not award both the full destruction bonus and an additional damage bonus for the same damage unless explicitly intended. The recommended rule is to award the destruction bonus separately and calculate damage points based on actual damage dealt, with a clearly documented cap if necessary.

The highest-scoring team wins.

### 12.3. Tie-breaking

Use the following order:

1. Higher final score.
2. More enemy bases destroyed.
3. Higher remaining base HP.
4. Higher remaining coins.
5. Shared victory if all configured tie-breakers are equal.

### 12.4. Defeated Teams

Defeated teams transition to spectator mode.

Their players can continue viewing the battle and final results but cannot deploy units, build towers, answer active team questions or spend coins.

A defeated team must not be removed from the results leaderboard.

A comeback mechanic may be added later but is not required for MVP.

---

# PART III. PRODUCT REQUIREMENTS DOCUMENT

## 13. Functional Requirements

### FR-01: Lobby Management

The system must allow the host to:

- Create a match.
- Generate a unique room code.
- Configure match settings.
- Create teams.
- Assign participants to teams.
- Define Mentor and Mentee roles.
- Start the match when the required teams are ready.

Acceptance criteria:

- Room codes must be unique among active rooms.
- Unauthorized users cannot modify lobby settings.
- The host can remove a participant before the match begins.
- Participants cannot join a match that has already closed to new players unless explicitly permitted.

### FR-02: Team Dashboard

Each team must see:

- Team name and members.
- Base HP and shield.
- Coin balance.
- Available units.
- Unlocked units and structures.
- Remaining questions.
- Active combat units.
- Existing towers.
- Available actions.
- Current target and combat status.

Acceptance criteria:

- Team-specific information is visible only to authorized team members.
- Coin balances and HP update after each authoritative state change.
- The interface handles reconnects without duplicating actions.

### FR-03: Question Engine

The system must:

- Deliver assigned questions.
- Support multiple-choice questions.
- Support short text answers.
- Support logic and memory challenges through extensible question types.
- Enforce timers and answer limits.
- Validate answers on the server.
- Record question history.

Acceptance criteria:

- An expired question cannot be answered.
- A completed question cannot be submitted again.
- The client cannot determine the correct answer by inspecting the initial question payload.
- Questions and rewards are persisted.

### FR-04: Reward Selection

The system must show two options after a correct answer:

1. Receive coins.
2. Unlock an eligible unit or structure.

Acceptance criteria:

- The default coin reward is 20.
- The coin reward is configurable.
- Unlocking costs no coins.
- An unlocked unit becomes available for deployment or construction.
- An unlocked item is not automatically deployed.
- If no eligible unlocks remain, the unlock option is disabled.
- Exactly one reward is granted per correct question.
- Duplicate reward requests do not grant additional coins or unlocks.

### FR-05: Economy

The system must:

- Track each team's coin balance.
- Validate purchases.
- Deduct costs atomically.
- Award passive income.
- Prevent negative balances.
- Record coin transactions.

Acceptance criteria:

- A purchase succeeds only when the team has sufficient coins.
- A failed purchase leaves the balance unchanged.
- Duplicate purchase requests cannot cause duplicate deductions or deployments.
- The transaction history supports auditing.

### FR-06: Unit and Structure Management

The system must support:

- Starter units.
- Unlockable combat units.
- Unlockable towers.
- Configurable statistics.
- Deployment and construction limits.
- Unit and structure upgrades.
- Repair actions.
- Unit destruction.

Acceptance criteria:

- Locked units cannot be deployed.
- Invalid construction nodes are rejected.
- Destroyed units no longer count toward capacity.
- The server validates all costs and limits.

### FR-07: Combat Engine

The system must:

- Process movement.
- Validate targets.
- Resolve tower attacks.
- Resolve unit attacks.
- Apply shield and HP damage.
- Remove destroyed entities.
- Update base status.
- Determine elimination and victory.

Acceptance criteria:

- Combat results are determined exclusively by the server.
- The same locked state and configuration produce deterministic results.
- No unit can attack outside its range.
- No destroyed unit can attack in a subsequent round.
- Base HP cannot fall below zero.
- Invalid targets do not receive damage.

### FR-08: Realtime Synchronization

The system must publish authoritative game updates through WebSockets.

Acceptance criteria:

- Connected clients receive game-state updates.
- Reconnected clients receive a current snapshot.
- Events include a unique event ID and game version or sequence number.
- Duplicate events do not cause duplicate UI effects or actions.
- A temporary disconnection does not pause the entire match automatically.

### FR-09: Host Console

The host must be able to:

- Start, pause, resume and end a match.
- View team status.
- View the current phase.
- View question and reward status.
- Review the event log.
- Configure eligible match settings before starting.
- Inspect final scores.

Acceptance criteria:

- Host actions are authorized and logged.
- A paused match does not advance combat timers or passive income.
- Ending a match produces a final result snapshot.

### FR-10: Results and Leaderboard

The system must display:

- Final ranking.
- Team scores.
- Remaining base HP.
- Enemy bases destroyed.
- Damage dealt.
- Correct answers.
- Coins remaining.
- Surviving towers.
- Match duration.

Optional awards:

- Best Strategist.
- Best Defense.
- Best Comeback.
- Knowledge Champion.
- Mentor–Mentee Synergy.

These awards are presentation features and must not change the official match score unless configured.

---

# PART IV. USER INTERFACE AND EXPERIENCE

## 14. Required Screens

### 14.1. Landing Page

Elements:

- Game title and logo.
- Create Match button.
- Join Match button.
- How to Play.
- Optional recent results for authorized users.

### 14.2. Join Match

Elements:

- Room code.
- Player display name.
- Join button.
- Connection status.
- Error messages.

### 14.3. Lobby

Elements:

- Room code.
- Team cards.
- Participant list.
- Mentor/Mentee labels.
- Ready status.
- Match configuration summary.
- Host-only start controls.

### 14.4. Main Battle Board

The primary game screen should contain:

**Top bar**
- Match timer.
- Current phase.
- Team name.
- Coin balance.
- Base HP and shield.

**Center**
- Battlefield map.
- Team bases.
- Fixed lanes.
- Moving units.
- Towers.
- Attack and damage animations.

**Side panel**
- Selected unit details.
- Available units and towers.
- Construction options.
- Target selection.
- Available special actions.

**Bottom panel**
- Recent battle events.
- Question status.
- Action history.
- Current objective.

The board should be responsive and readable on a desktop browser and on a projected screen.

### 14.5. Question Modal

Elements:

- Question text.
- Answer choices or input.
- Countdown timer.
- Submit button.
- Submission state.
- Result feedback.

Do not display the correct answer before the team has submitted or the question has expired.

### 14.6. Reward Selection Modal

Display two cards:

**Receive Coins**
- Reward amount.
- Short description.
- Confirm action.

**Unlock Unit**
- Number of eligible items.
- Unlock selection interface.
- Disabled state when no items are eligible.

Prevent repeated clicks while a reward request is being processed.

### 14.7. Unit Selection

Display a grid of eligible units and structures.

Each card includes:

- Icon.
- Name.
- Category.
- Description.
- HP.
- Damage.
- Range.
- Cost.
- Unlock status.

Separate the states:

- Locked.
- Available to unlock.
- Unlocked and affordable.
- Unlocked but unaffordable.
- Deployed or constructed.
- Destroyed.

### 14.8. Host Dashboard

Include:

- Match controls.
- Team status table.
- Remaining question counts.
- Pending reward selections.
- Coin balances.
- Base HP.
- Combat log.
- Match configuration.
- Final result summary.

### 14.9. Results Screen

Include:

- Winner announcement.
- Ranking.
- Team score breakdown.
- Statistics.
- Optional award badges.
- Rematch or return-to-lobby actions.

---

# PART V. TECHNICAL ARCHITECTURE

## 15. Recommended Technology Stack

The default implementation stack is:

### Frontend

- React.
- TypeScript.
- Vite.
- Phaser 3 for the battlefield and game animations.
- CSS modules or the existing project's styling system.
- WebSocket client for realtime updates.

The UI should use Phaser only where canvas-based game rendering provides value. Forms, modals, menus, tables and dashboards should remain normal React components.

### Backend

- Python.
- Django.
- Django REST Framework for HTTP APIs.
- Django Channels for WebSockets.
- ASGI server for asynchronous connections.

### Infrastructure

- PostgreSQL for persistent data.
- Redis for Channels and transient realtime coordination.
- Docker Compose for local development.
- Production deployment configuration documented separately.

Use the versions and conventions already present in the repository when they are compatible with the architecture.

## 16. Architecture Principles

### 16.1. Server-authoritative Game Engine

The backend is the single source of truth.

The client can request an action, but cannot decide:

- Whether an answer is correct.
- Whether a reward is granted.
- Whether a unit is unlocked.
- Whether a purchase succeeds.
- How much damage is dealt.
- Whether a unit is destroyed.
- Whether a base is eliminated.
- Who wins the match.

### 16.2. Separate Domain Logic

Organize game logic into independent services or modules:

- `MatchService`
- `QuestionService`
- `RewardService`
- `EconomyService`
- `UnitService`
- `ConstructionService`
- `CombatEngine`
- `ScoringService`
- `RealtimeService`

Use transactions around critical state changes.

Avoid putting game rules directly inside WebSocket consumers or frontend components.

### 16.3. Realtime Events

Use WebSockets for:

- Match state updates.
- Question delivery.
- Answer results.
- Reward selection.
- Unit deployment.
- Tower construction.
- Combat resolution.
- Base destruction.
- Match phase changes.
- Leaderboard updates.

HTTP APIs should handle lobby creation, administrative configuration, historical results and other request-response operations.

## 17. Suggested Backend Project Structure

Adapt this structure to the existing repository instead of replacing a working project without justification.

```text
backend/
  config/
    settings/
    urls.py
    asgi.py

  apps/
    accounts/
    matches/
      models.py
      serializers.py
      views.py
      services.py
      consumers.py

    teams/
      models.py
      services.py

    questions/
      models.py
      services.py
      validators.py

    rewards/
      models.py
      services.py

    economy/
      models.py
      services.py

    units/
      models.py
      services.py

    combat/
      engine.py
      targeting.py
      movement.py
      damage.py
      scoring.py

    realtime/
      routing.py
      events.py

  tests/
    test_rewards.py
    test_economy.py
    test_units.py
    test_combat.py
    test_matches.py
```

## 18. Suggested Frontend Structure

```text
frontend/
  src/
    app/
    pages/
      LandingPage.tsx
      JoinMatchPage.tsx
      LobbyPage.tsx
      BattlePage.tsx
      HostDashboardPage.tsx
      ResultsPage.tsx

    components/
      game/
        BattleBoard.tsx
        TeamStatus.tsx
        UnitCard.tsx
        TowerCard.tsx
        QuestionModal.tsx
        RewardModal.tsx
        UnlockSelection.tsx
        CombatLog.tsx
        Leaderboard.tsx

    game/
      PhaserGame.tsx
      scenes/
      entities/
      assets/

    services/
      api.ts
      websocket.ts

    stores/
      matchStore.ts

    types/
      match.ts
      question.ts
      reward.ts
      unit.ts
      combat.ts
```

The frontend may use a different state management solution if the repository already has one.

## 19. Database Design

Use UUIDs for primary identifiers where appropriate.

### 19.1. Match

Fields:

- `id`
- `room_code`
- `name`
- `status`
- `phase`
- `configuration`
- `started_at`
- `ended_at`
- `created_by`
- `created_at`
- `updated_at`

### 19.2. Team

Fields:

- `id`
- `match_id`
- `name`
- `initial_base_hp`
- `base_hp`
- `base_shield`
- `coins`
- `score`
- `status`
- `created_at`

### 19.3. TeamMember

Fields:

- `id`
- `team_id`
- `user_id` or guest participant ID
- `display_name`
- `role`
- `joined_at`

### 19.4. Question

Fields:

- `id`
- `type`
- `category`
- `difficulty`
- `content`
- `options`
- `answer_key`
- `answer_validator_type`
- `time_limit_seconds`
- `explanation`
- `is_active`
- `created_at`

Sensitive answer data must not be serialized into participant-facing payloads.

### 19.5. TeamQuestion

Fields:

- `id`
- `match_id`
- `team_id`
- `question_id`
- `sequence_number`
- `status`
- `assigned_at`
- `expires_at`
- `submitted_at`
- `is_correct`

Add a uniqueness constraint to prevent assigning the same question sequence twice to a team within a match.

### 19.6. RewardClaim

Fields:

- `id`
- `team_question_id`
- `team_id`
- `reward_type`
- `coin_amount`
- `unlocked_unit_type_id`
- `status`
- `claimed_at`

A completed reward claim must be unique per team question.

### 19.7. UnitType

Fields:

- `id`
- `code`
- `name`
- `category`
- `description`
- `base_stats`
- `cost`
- `is_starter`
- `is_unlockable`
- `is_active`
- `prerequisites`

Store configurable combat statistics in a validated JSON field or normalized columns, following the existing project's conventions.

### 19.8. TeamUnlock

Fields:

- `id`
- `team_id`
- `unit_type_id`
- `unlocked_at`
- `source_team_question_id`

Add a unique constraint on `(team_id, unit_type_id)`.

### 19.9. GameEntity

Represents deployed units and constructed structures.

Fields:

- `id`
- `match_id`
- `team_id`
- `unit_type_id`
- `entity_kind`
- `current_hp`
- `current_shield`
- `level`
- `status`
- `current_node_id`
- `target_team_id`
- `target_node_id`
- `created_at`
- `destroyed_at`

### 19.10. GameAction

Fields:

- `id`
- `match_id`
- `team_id`
- `actor_id`
- `action_type`
- `payload`
- `status`
- `idempotency_key`
- `created_at`
- `resolved_at`
- `failure_reason`

### 19.11. CoinTransaction

Fields:

- `id`
- `match_id`
- `team_id`
- `amount`
- `transaction_type`
- `reference_type`
- `reference_id`
- `balance_after`
- `created_at`

Use positive amounts for credits and negative amounts for debits, or adopt another consistent accounting convention.

### 19.12. MatchEvent

Fields:

- `id`
- `match_id`
- `sequence_number`
- `event_type`
- `payload`
- `created_at`

This table provides an audit trail for important game events.

### 19.13. MatchResult

Fields:

- `id`
- `match_id`
- `team_id`
- `final_rank`
- `final_score`
- `bases_destroyed`
- `base_damage_dealt`
- `correct_answers`
- `remaining_base_hp`
- `remaining_coins`
- `surviving_towers`
- `created_at`

Store final results as an immutable snapshot after the match is finalized.

---

# PART VI. API AND WEBSOCKET CONTRACTS

## 20. HTTP API

Use versioned endpoints under `/api/v1/`.

Suggested endpoints:

### Matches

- `POST /api/v1/matches/` — create match.
- `GET /api/v1/matches/{match_id}/` — get match metadata.
- `POST /api/v1/matches/{match_id}/join/` — join a match.
- `POST /api/v1/matches/{match_id}/start/` — start match.
- `POST /api/v1/matches/{match_id}/pause/` — pause match.
- `POST /api/v1/matches/{match_id}/resume/` — resume match.
- `POST /api/v1/matches/{match_id}/end/` — end match.

### Questions

- `GET /api/v1/matches/{match_id}/questions/current/`
- `POST /api/v1/matches/{match_id}/questions/{question_id}/answer/`

### Rewards

- `POST /api/v1/matches/{match_id}/rewards/claim/`

Example request:

```json
{
  "team_question_id": "uuid",
  "reward_type": "UNLOCK",
  "unit_type_id": "tank"
}
```

For coin rewards:

```json
{
  "team_question_id": "uuid",
  "reward_type": "COIN"
}
```

The server must determine the configured coin amount. The client must never supply an authoritative reward amount.

### Game Actions

- `POST /api/v1/matches/{match_id}/actions/deploy/`
- `POST /api/v1/matches/{match_id}/actions/build/`
- `POST /api/v1/matches/{match_id}/actions/upgrade/`
- `POST /api/v1/matches/{match_id}/actions/repair/`
- `POST /api/v1/matches/{match_id}/actions/scout/`
- `POST /api/v1/matches/{match_id}/actions/emp/`

### Results

- `GET /api/v1/matches/{match_id}/results/`
- `GET /api/v1/matches/{match_id}/events/`

Every state-changing endpoint must validate the participant's role, team membership, match status, phase and action eligibility.

## 21. WebSocket Protocol

Suggested endpoint:

`/ws/matches/{match_id}/`

Recommended client messages:

- `STATE_SYNC_REQUEST`
- `ANSWER_SUBMITTED`
- `REWARD_SELECTED`
- `DEPLOY_REQUEST`
- `BUILD_REQUEST`
- `UPGRADE_REQUEST`
- `REPAIR_REQUEST`
- `TARGET_SELECTED`
- `READY_CHANGED`

Recommended server messages:

- `MATCH_STATE_SNAPSHOT`
- `MATCH_PHASE_CHANGED`
- `QUESTION_ASSIGNED`
- `ANSWER_RESULT`
- `REWARD_OPTIONS`
- `REWARD_APPLIED`
- `ACTION_ACCEPTED`
- `ACTION_REJECTED`
- `UNIT_DEPLOYED`
- `TOWER_BUILT`
- `COMBAT_RESOLVED`
- `ENTITY_DESTROYED`
- `BASE_DAMAGED`
- `BASE_DESTROYED`
- `COINS_UPDATED`
- `LEADERBOARD_UPDATED`
- `MATCH_PAUSED`
- `MATCH_RESUMED`
- `MATCH_ENDED`

Every server event should include:

- `event_id`
- `match_id`
- `event_type`
- `sequence_number`
- `server_timestamp`
- `payload`

The client must detect missing sequence numbers and request a fresh state snapshot when needed.

Use WebSockets for realtime communication, but retain authenticated HTTP endpoints as the canonical fallback for critical state-changing actions if appropriate for the existing architecture.

---

# PART VII. SECURITY AND RELIABILITY

## 22. Authorization

- Only the host can control match lifecycle.
- Only authorized participants can submit answers for their assigned team.
- Team members can act only on behalf of their own team.
- Spectators cannot change match state.
- A user cannot claim another team's reward.
- Administrative configuration endpoints require elevated permissions.

For guest-based participation, issue an unguessable participant credential and validate it on every protected request. A room code alone must not authorize administrative actions.

## 23. Server-side Validation

Validate every action against the authoritative state.

Examples:

- The match is active.
- The team is not eliminated.
- The team has enough coins.
- The unit is unlocked.
- Capacity limits have not been exceeded.
- The target is valid.
- The placement node is legal.
- The question has not expired.
- The reward has not already been claimed.

## 24. Concurrency and Idempotency

Critical operations must be transactional.

Examples:

- Claiming a reward.
- Deducting coins.
- Deploying a unit.
- Building a tower.
- Resolving a combat round.

Use database locking or conditional updates to prevent two simultaneous requests from spending the same coins.

Every state-changing client action should carry an idempotency key or equivalent unique action identifier.

Repeated requests must not create duplicate entities or rewards.

## 25. Reconnection and Recovery

When a client reconnects:

1. Reauthenticate the participant.
2. Verify room and team membership.
3. Send an authoritative state snapshot.
4. Resume receiving events from the current sequence number.
5. Restore the current question and reward status if applicable.

The server must continue owning the match state even if all clients disconnect temporarily.

For MVP, the host may manually pause a match if the venue experiences significant connectivity issues.

## 26. Audit Logging

Record:

- Match lifecycle changes.
- Question assignments and results.
- Reward claims.
- Coin credits and debits.
- Unit deployments.
- Tower construction.
- Combat results.
- Base destruction.
- Administrative overrides.

Do not log unnecessary secrets or participant authentication credentials.

---

# PART VIII. TESTING AND ACCEPTANCE CRITERIA

## 27. Unit Tests

Implement tests for:

- Question answer validation.
- Question expiration.
- Reward eligibility.
- Coin reward calculation.
- Unlock eligibility.
- Duplicate reward prevention.
- Coin balance validation.
- Unit capacity.
- Tower capacity.
- Target validation.
- Movement.
- Attack range.
- Damage calculation.
- Shield absorption.
- Base destruction.
- Scoring.
- Victory conditions.

## 28. Integration Tests

Test complete workflows:

### Scenario A: Correct Answer → Coins

1. Team receives a question.
2. Team submits the correct answer.
3. Reward modal becomes available.
4. Team chooses coins.
5. Server credits the configured amount.
6. The same reward cannot be claimed again.

Expected result: one coin credit only.

### Scenario B: Correct Answer → Unlock

1. Team receives a question.
2. Team submits the correct answer.
3. Team chooses Unlock.
4. Team selects Tank.
5. Server unlocks Tank.
6. Tank appears in the team's available units.
7. Team can deploy Tank only if it has enough coins.

Expected result: Tank is unlocked without a coin deduction.

### Scenario C: All Units Unlocked

1. Team unlocks every eligible unit.
2. Team answers another question correctly.
3. The reward modal appears.
4. The coin option remains enabled.
5. The unlock option is disabled.
6. The team can still claim the coin reward.

Expected result: no invalid unlock can be submitted.

### Scenario D: Insufficient Coins

1. Team has fewer coins than the unit cost.
2. Team requests deployment.
3. Server rejects the request.
4. Coin balance remains unchanged.
5. No unit is created.

Expected result: no negative balance or free deployment.

### Scenario E: Simultaneous Requests

1. Two requests attempt to claim the same reward.
2. Both reach the backend at approximately the same time.
3. The backend processes the requests transactionally.

Expected result: at most one reward is granted.

### Scenario F: Combat

1. Team A deploys a unit.
2. The unit moves through a valid lane.
3. Team B's tower detects the unit within range.
4. The tower attacks.
5. HP is updated.
6. Destroyed entities are removed.
7. The base receives damage if a unit reaches its attack position.

Expected result: deterministic server-side combat.

### Scenario G: Reconnection

1. A team disconnects during a match.
2. Other teams continue playing.
3. The disconnected team reconnects.
4. The client requests a snapshot.

Expected result: the team sees the correct current state and cannot replay old actions.

### Scenario H: Match Completion

1. A base is destroyed or the timer expires.
2. The server finalizes the match.
3. Scores are calculated.
4. Results are persisted.
5. The leaderboard is displayed.

Expected result: a single consistent final result snapshot.

## 29. End-to-End Acceptance Criteria

The MVP is considered complete when:

- A host can create and start a match.
- Four or more teams can join.
- Each team can answer questions.
- Correct answers present the two reward options.
- Incorrect answers grant no reward.
- The Unlock option is disabled when no eligible items remain.
- Teams can deploy only unlocked units.
- Teams can construct only unlocked towers.
- Purchases deduct the correct coin amount.
- Combat updates are synchronized across clients.
- Bases can be destroyed.
- The game recognizes victory and elimination.
- Final scores and rankings are calculated correctly.
- Unauthorized requests are rejected.
- Duplicate requests cannot duplicate rewards or purchases.
- The game can recover from client disconnections.
- The application runs from the documented setup instructions.
- Automated tests cover all critical game rules.

---

# PART IX. IMPLEMENTATION PLAN

## 30. Development Phases

### Phase 0 — Repository Inspection

Before modifying the codebase, the AI Agent must:

- Inspect the current repository.
- Identify existing frontend and backend frameworks.
- Inspect dependency versions and configuration.
- Identify reusable components and existing authentication.
- Check whether Docker, PostgreSQL and Redis are already configured.
- Document architectural constraints.
- Propose a minimal implementation plan.

Do not replace existing architecture without a documented technical reason.

Deliverables:

- Repository assessment.
- Proposed implementation plan.
- List of files to create or modify.
- Identified risks and assumptions.

### Phase 1 — Domain Model and Match Lifecycle

Implement:

- Match and team models.
- Participant roles.
- Match configuration.
- Lobby.
- Match lifecycle.
- Initial database migrations.
- Basic authorization.
- Match creation and joining APIs.

Deliverable: teams can join a room and start a match.

### Phase 2 — Questions and Rewards

Implement:

- Question bank.
- Question assignment.
- Timers.
- Answer validation.
- Coin reward.
- Unlock reward.
- Reward selection interface.
- Duplicate-claim protection.

Deliverable: the complete question-to-reward loop works.

### Phase 3 — Economy and Units

Implement:

- Coin transactions.
- Starter units.
- Unlockable units.
- Defensive structures.
- Deployment.
- Construction.
- Upgrade.
- Repair.
- Capacity limits.

Deliverable: teams can spend coins and prepare for combat.

### Phase 4 — Combat Engine

Implement:

- Fixed-lane map.
- Unit movement.
- Tower targeting.
- Damage resolution.
- Shield handling.
- Base damage.
- Elimination.
- Victory and scoring.

Deliverable: a complete server-authoritative battle can be simulated.

### Phase 5 — Realtime and Game Board

Implement:

- Django Channels.
- WebSocket authentication and authorization.
- Event sequencing.
- State snapshots.
- Reconnection.
- Phaser battlefield.
- Combat animations.
- Team dashboard.
- Leaderboard.

Deliverable: multiple teams can play the same match in realtime.

### Phase 6 — Host Console and Results

Implement:

- Match controls.
- Administrative monitoring.
- Match configuration.
- Event history.
- Final scoring.
- Results screen.
- Optional awards.

Deliverable: the game can be operated during an actual team-building event.

### Phase 7 — QA and Deployment

Implement:

- Automated tests.
- End-to-end tests.
- Concurrency tests.
- Reconnection tests.
- Responsive UI testing.
- Docker setup.
- Environment configuration.
- Deployment documentation.
- Seed data and sample questions.

Deliverable: a repeatable deployment suitable for internal use.

---

# PART X. INSTRUCTIONS FOR THE AI CODING AGENT

## 31. Execution Instructions

You are a senior full-stack engineer and game systems developer.

Your task is to implement **Tower Defense: Protect the Base**, a multiplayer browser-based strategy game, according to this GDD/PRD.

### Mandatory Rules

1. Inspect the existing repository before writing code.
2. Preserve compatible existing project conventions and architecture.
3. Do not implement Action Tokens. The reward system is exclusively based on choosing coins or unlocking units after a correct answer.
4. Treat the backend as the single source of truth for all game state and combat.
5. Implement the question, reward, economy and combat rules as independently testable domain logic.
6. Do not trust client-provided prices, damage values, answer results, team IDs or reward amounts.
7. Use transactions and idempotency for critical operations.
8. Never expose correct answers in participant-facing question payloads before submission or expiration.
9. Use database constraints for uniqueness rules wherever practical.
10. Keep gameplay configuration separate from presentation code.
11. Do not implement every advanced feature before the core gameplay loop works.
12. Do not leave critical game rules as TODOs or mock-only behavior.
13. Do not claim a test passes unless it has actually been executed.
14. Do not introduce unnecessary dependencies or replace the existing stack without justification.

## 32. Required Agent Workflow

### Step 1: Analyze

Read the repository structure, dependency files, configuration and existing documentation.

Identify:

- Frontend entry point.
- Backend entry point.
- Database setup.
- Authentication approach.
- Existing realtime infrastructure.
- Existing tests.
- Local development workflow.

### Step 2: Plan

Create an implementation plan that maps each PRD requirement to:

- Backend modules.
- Frontend screens.
- Database models.
- API endpoints.
- WebSocket events.
- Automated tests.

Identify unresolved decisions and propose sensible defaults without blocking progress on nonessential questions.

### Step 3: Implement Incrementally

Implement the project in the following order:

1. Domain models and match lifecycle.
2. Questions and reward selection.
3. Economy and unit management.
4. Combat engine.
5. Realtime synchronization.
6. Game board UI.
7. Host console and results.
8. Tests, documentation and deployment.

Keep the project runnable after each major phase.

### Step 4: Verify

Run applicable commands for:

- Dependency installation.
- Database migrations.
- Backend tests.
- Frontend type checking.
- Frontend linting.
- Production build.
- Integration tests.
- End-to-end tests where configured.

Resolve errors caused by the implementation before marking the phase complete.

### Step 5: Document

Provide:

- Architecture overview.
- Setup instructions.
- Environment variables.
- Database migration instructions.
- Seed data instructions.
- How to start the frontend and backend.
- How to create a test match.
- How to add new units.
- How to add questions.
- How to modify balance values.
- Known limitations.
- Test results.

## 33. Final Deliverables

The completed implementation must include:

- A working frontend.
- A working backend.
- Database migrations.
- Seed data for a sample match.
- Sample question bank.
- Starter and unlockable units.
- Coin economy.
- Reward selection.
- Combat engine.
- Realtime synchronization.
- Host dashboard.
- Results screen.
- Automated tests.
- Local development setup.
- Deployment documentation.

## 34. Definition of Done

The project is complete when a host can create a match, multiple teams can join, teams can answer questions and choose between coins and unlocking units, players can purchase and deploy units, towers can defend bases, attacks can destroy bases, and the system can calculate and display a valid winner.

The game must be playable end-to-end without relying on manual database changes or mocked combat outcomes.

**Priority:** Correct game rules and reliable multiplayer state first; visual polish and advanced special abilities second.

**Product principle:** Knowledge unlocks opportunities, coins enable execution, and teamwork determines the winner.
