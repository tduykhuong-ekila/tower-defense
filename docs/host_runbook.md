# Tower Defense — Host & Tournament Organizer Runbook

> Target Audience: Match Hosts, Event Organizers, Game Masters.
> Source: `GDD_PRD.md` §2.1, §4, §10, §11, §19, §32 Step 5.

---

## 1. Tournament Operations Timeline & Checklist

### T-60 Minutes: Infrastructure & Sound/Display Check
- [ ] Ensure Docker stack is healthy: `docker compose -f docker-compose.prod.yml ps`.
- [ ] Connect host projector / arena display to [http://localhost/#/spectate](http://localhost/#/spectate).
- [ ] Verify audio output for battle sound effects and UI notifications.
- [ ] Test network connectivity for player devices (Wi-Fi access point bandwidth).

### T-30 Minutes: Match Creation & Seeding
- [ ] Open Host Dashboard at [http://localhost/#/host](http://localhost/#/host).
- [ ] Create a new tournament match or seed sample data:
  ```bash
  python manage.py seed_demo --reset
  ```
- [ ] Note down the **Room Code** (e.g. `DEMO24`) and display it on the main hall projector.
- [ ] Confirm preset configuration: Standard 30m (30-minute duration, 30s combat round interval, 8 questions per team).

### T-15 Minutes: Team Check-In & Role Assignment
- [ ] Teams arrive and open the web application on their laptops/tablets.
- [ ] Each team selects their designated slot (e.g., Red Dragons, Blue Phoenix, Green Titans, Golden Wolves).
- [ ] Confirm each team has:
  - **1 Mentor (Team Lead):** Answers questions, claims unlocks, deploys units, builds towers, triggers EMP/Scout.
  - **1–3 Mentees:** Answers questions, discusses strategy, assists in quiz rounds.
- [ ] Host dashboard verifies that all 4 teams show active status and green readiness indicators.

### T-0 Minutes: Match Launch
- [ ] Announce rules and countdown.
- [ ] Host clicks **"Bắt Đầu Trận Đấu" (Start Match)** in the Host Console.
- [ ] The game transitions into `PREPARATION` phase (3 minutes planning & first question assignment).

---

## 2. In-Match Operations & Control Panel

### 2.1 Pausing & Resuming the Match
If an emergency occurs (e.g. fire alarm, Wi-Fi router reboot, physical venue issue):
1. In the Host Console, click **"Tạm Dừng Trận Đấu" (Pause Match)**.
2. The backend immediately:
   - Freezes all combat round timers.
   - Pauses passive coin income generation.
   - Blocks participant deploy and construction actions.
   - Broadcasts `MATCH_PAUSED` event to all connected screens.
3. Once the issue is resolved, click **"Tiếp Tục Trận Đấu" (Resume Match)**.

### 2.2 Adjusting Round Pace
- By default, combat rounds auto-resolve every 30 seconds.
- In manual or presentation mode, the Host can trigger manual rounds using the **"Giải Quyết Round Ngay" (Resolve Round Now)** button.

### 2.3 Emergency Match Termination
If the event must conclude immediately:
- Click **"Kết Thúc Trận Đấu" (End Match)**.
- The authoritative Scoring Service triggers final leaderboard calculation, awards, and displays the Results Screen.

---

## 3. Incident Management & Troubleshooting Guide

| Issue / Symptom | Probable Cause | Corrective Action |
|-----------------|----------------|-------------------|
| **Player disconnected or closed browser tab** | Network hiccup or accidental reload | Instruct player to re-open the URL and enter the Room Code with the exact same display name. The backend automatically re-authenticates the session via participant token stored in browser `localStorage`. |
| **Participant screen out of sync with projector** | Missed WebSocket packets during Wi-Fi packet drop | The frontend will automatically detect sequence gaps and request event replay. If necessary, click the "Đồng Bộ Lại" (Resync) button or press `F5` to fetch a fresh server snapshot. |
| **Backend crashed or server restarted mid-match** | System reboot or power failure | Restart the Daphne container (`docker compose up -d backend`). Match state and entity HP are persisted in PostgreSQL. Upon boot, the server reloads active matches and continues the round schedule seamlessly. |
| **Team claims they cannot buy a unit or tower** | Insufficient coins or missing unlock | Check the Team State tab on the Host Dashboard: verify if the unit requires an unlock or if the team reached the 5-unit / 3-tower territory limit. |
| **Question timer expired before team answered** | Time elapsed (default 60s) | The system automatically marks expired questions as `EXPIRED` (0 coins) and assigns the next sequential question after grace period. |
| **Tied scores at match completion** | Two teams have identical final points | The ranking algorithm applies deterministic tie-breaking: 1) Lowest initial team index; 2) Most surviving towers; 3) Remaining base HP. All tie-break reasons are documented in the Results screen. |

---

## 4. Post-Match Protocol & Leaderboard Presentation

1. The Results Screen displays:
   - **Champion Team** with gold trophy presentation.
   - **Full Leaderboard** (Rank 1 to 4) with detailed score breakdowns: Base Destroyed, Damage Dealt, Remaining HP, Correct Answers, Surviving Towers, Coins.
   - **Special Awards:** *First Blood, Iron Fortress, Tactical Genius, Speed Demon, Comeback King*.
2. Export match data or create a database backup for post-event records:
   ```bash
   ./scripts/backup_db.sh ./tournament_archives
   ```
