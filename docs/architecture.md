# Tower Defense — Architecture & System Design Guide

> Source: `GDD_PRD.md` §1–4, §19, Architectural Decisions D1–D14.

---

## 1. High-Level System Architecture

The game follows a **server-authoritative multiplayer architecture**. All game logic (combat calculations, movement, scoring, coin economy, and victory evaluation) executes strictly on the backend. The frontend clients (Mentor, Mentee, Host, Spectator) act as thin presentation layers powered by React and Phaser 3.

```mermaid
graph TD
    subgraph Clients["Frontend Clients (React 18 + Phaser 3 + Zustand)"]
        Host["Host Dashboard<br/>/host/match/:id"]
        Mentor["Mentor Terminal<br/>/play/:id (Leader)"]
        Mentee["Mentee Terminal<br/>/play/:id (Member)"]
        Spectator["Spectator Arena<br/>/spectate/:id"]
    end

    subgraph Ingress["Reverse Proxy & Gateway"]
        Nginx["Nginx Reverse Proxy<br/>Port 80 / 443<br/>HTTP + WebSocket Upgrade"]
    end

    subgraph Backend["Backend Services (Django 5 + Daphne ASGI)"]
        Daphne["Daphne ASGI Server<br/>Port 8000"]
        REST["Django REST Framework<br/>Authoritative API"]
        Channels["Django Channels 4<br/>WebSocket Consumer"]
        CombatSvc["Combat Engine & Service<br/>authoritative 12-step round"]
        EconSvc["Economy & Reward Service<br/>audit ledger & idempotency"]
        QuestionSvc["Question Service<br/>sanitized payloads"]
    end

    subgraph DataTier["Data & Communication Tier"]
        Postgres[(PostgreSQL 16<br/>Authoritative State & Ledger)]
        Redis[(Redis 7<br/>Channel Layer & Sync Queue)]
    end

    Host -->|HTTP / WS| Nginx
    Mentor -->|HTTP / WS| Nginx
    Mentee -->|HTTP / WS| Nginx
    Spectator -->|HTTP / WS| Nginx

    Nginx -->|/api/*| Daphne
    Nginx -->|/ws/*| Daphne
    Nginx -->|/*| Nginx

    Daphne --> REST
    Daphne --> Channels

    REST --> CombatSvc
    REST --> EconSvc
    REST --> QuestionSvc

    CombatSvc --> Postgres
    EconSvc --> Postgres
    QuestionSvc --> Postgres

    Channels --> Redis
    Channels --> Postgres
    CombatSvc --> Redis
```

---

## 2. Realtime Event Delivery & Monotonic Sequence Numbering

To guarantee deterministic client rendering and seamless reconnection without state corruption, all realtime events follow a strictly **monotonic sequence number** per match.

### 2.1 Event Sequence Protocol

```mermaid
sequenceDiagram
    participant Client as React Client (Zustand store)
    participant WS as WebSocket Consumer
    participant Redis as Redis Channel Layer
    participant DB as Postgres (MatchEvent log)

    Note over Client, DB: Regular Realtime Flow
    WS->>Client: Event Envelope (sequence_number: N)
    Client->>Client: Apply Event if seq == expected_seq (N)
    Client->>Client: expected_seq = N + 1

    Note over Client, DB: Gap Detection & Resync Flow (e.g. WiFi hiccup)
    WS--xClient: Missed Event (sequence_number: N+1)
    WS->>Client: Event Envelope (sequence_number: N+2)
    Client->>Client: Detect Gap: received N+2, expected N+1
    Client->>WS: Send SYNC request {last_received_sequence: N}
    WS->>DB: Query MatchEvent where sequence_number > N
    DB-->>WS: Return missed events [N+1, N+2]
    WS->>Client: Stream missed events in order
    Client->>Client: Replay events monotonically
```

### 2.2 Event Envelope Structure

Every message broadcast over WebSocket or retrieved via the event replay REST API conforms to the standard envelope:

```json
{
  "event_id": "c1f7a049-74d6-4e50-93dc-8e5fbb77f101",
  "match_id": "dae220db-742d-49d7-b8ee-3207b66af63f",
  "sequence_number": 42,
  "timestamp": "2026-10-16T08:30:00.123456Z",
  "event_type": "COMBAT_RESOLVED",
  "is_private": false,
  "team_id": null,
  "payload": {
    "round_number": 3,
    "events": [
      {
        "type": "TOWER_ATTACKED",
        "tower_id": "tow_1",
        "target_entity_id": "u_2",
        "damage": 25
      }
    ],
    "eliminated_teams": [],
    "winner_team_id": null,
    "is_match_over": false
  }
}
```

---

## 3. Authoritative Combat Round Lifecycle (12-Step Pipeline)

Combat rounds execute periodically (default every 30s) or on manual Host trigger. The execution follows the authoritative 12-step sequence defined in `GDD_PRD.md` §10.1:

```mermaid
flowchart TD
    Step1["1. Close Planning Window (Lock Actions)"] --> Step2["2. Validate Queued Actions (Capacity, Unlocks, Coins)"]
    Step2 --> Step3["3. Deduct/Confirm Coins & Mark Actions Accepted"]
    Step3 --> Step4["4. Spawn New Combat Units (QUEUED -> ACTIVE at spawn node)"]
    Step4 --> Step5["5. Advance Movement along Predefined March Paths"]
    Step5 --> Step6["6. Resolve Defensive Tower Attacks (D5 Targeting Priority)"]
    Step6 --> Step7["7. Resolve Combat Unit Attacks & Range Checks"]
    Step7 --> Step8["8. Apply Shield Effects & Base Damage"]
    Step8 --> Step9["9. Remove Destroyed Units & Structures"]
    Step9 --> Step10["10. Check Elimination & Match Victory Conditions"]
    Step10 --> Step11["11. Award Passive Base Income to Active Teams"]
    Step11 --> Step12["12. Commit Transaction & Broadcast Monotonic Event Log"]
```

---

## 4. Security & Hardening Boundaries

1. **Answer Masking:** Questions sent to participants (`/questions/current/`, `/questions/all/`) omit `answer_key`, `explanation`, and `answer_validator_type`. Correct answers are never exposed to the browser.
2. **Double-Spend & Race Protection:** All coin operations use `select_for_update()` inside database transactions, with immutable ledger audit entries in `CoinTransaction`.
3. **Action Authorization:** Every action endpoint verifies participant role (Mentors only for special actions, Spectators blocked from state changes) and checks that the team belongs to the authenticated token.
4. **Graceful Degradation:** If Redis becomes temporarily unavailable, the system logs a controlled warning and falls back to HTTP snapshot polling, preventing crash loops.
