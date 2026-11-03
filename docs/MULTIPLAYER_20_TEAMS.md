# Running a 20-team match

Create a match and set minimum/maximum teams in the creation form. Both accept every integer from 2 to 20. In the lobby, the host can edit these settings before starting; capacity cannot drop below teams already present. Existing defaults remain minimum four, maximum eight. A twenty-team match requires explicitly choosing maximum twenty.

Each team retains one shared base, coin balance, unlock set, questions and actions. Default membership is 2–4 participants: at most one mentor plus mentees. Twenty full teams therefore support 80 participants, plus host and spectators. Members still use their own tokens; no one-player-per-team conversion is introduced.

Lobby cards display stable number, symbol, color, members and readiness. The server checks team count, ready flags and minimum membership at start. Maximum capacity, duplicate mentors, foreign slots, own/eliminated targets, insufficient coins and per-team entity limits remain server enforced.

In battle:

- Use **Các đội** or the target button to search by name/number, filter active enemies or your team, and sort by HP, score or number.
- Choosing a living enemy selects its target, shows the route and focuses its base. Inspecting your own or an eliminated base does not select it as an attack target.
- Use the minimap to select any base or pan to a location. White outline identifies your base, yellow identifies the target, × marks eliminated bases. Its rectangle follows the camera; the orange marker locates the most recent combat.
- Minimap buttons fit the entire arena or focus your base, selected target or combat. Its heading collapses the panel. Arrow keys move the minimap viewport; Enter/Space selects a focused base.
- At overview scale, numbered base labels and troop counts replace fine detail. Zoom in for individual units and HP bars.
- Results retain all teams, including eliminated teams and shared ranks, in a scrollable table.

Commands and balances stay authoritative. Correct answers grant a choice of exactly the existing configured reward (default +20 coins) or an unlock; deployment still costs coins and each question can be claimed only once. No Action Tokens were added.

For manual combat, send `POST /api/v1/matches/{id}/combat/resolve/` with `{"expected_round": 1}` and the host credential. Retrying that round returns its stored result. The frontend supplies the current round. Legacy API callers omitting the field resolve the round visible when the HTTP request begins; internal service callers omitting it deliberately resolve the next round.

A reconnect receives fresh public entities and team data plus only that team's private question, coins, members and unlocks. Snapshot question UUID fields are explicitly serialized to strings for standard Channels JSON. Public match details omit live balances, and nested public combat/deployment balances are projected per viewer before socket delivery. Tests include all 80 participants, two spectators and host, private delivery, read-only spectators and reconnect with active questions.

Use PostgreSQL and Redis for a multi-process deployment. The local benchmark and development preview use SQLite and one in-memory channel layer; they are not a Redis/TCP deployment stress certification.

## Persistent local preview

The original preview used a temporary SQLite file. If that file is cleared, its old match URL cannot be restored from the source alone. The preview now has dedicated settings and an idempotent seeding command; its database and generated local fixture credentials are stored under `backend/.local/`, excluded from source control. This does not use the regular development database.

In a backend terminal:

```sh
cd backend
.venv/bin/python manage.py migrate --settings=config.settings.preview
.venv/bin/python manage.py seed_arena --settings=config.settings.preview --teams 20 --near-capacity
DJANGO_SETTINGS_MODULE=config.settings.preview .venv/bin/daphne -b 127.0.0.1 -p 8001 config.asgi:application
```

In a frontend terminal:

```sh
cd frontend
API_PROXY_TARGET=http://127.0.0.1:8001 npm run dev -- --port 5174
```

The seed command prints a room code and join link. Repeating it reuses that preview and preserves match progress; it also ensures the existing demo question bank is available. Use `--players 4` for 80 participants or omit `--near-capacity` for the standard entity count. Extra humans can join the default two-person teams because local previews explicitly allow late joins. The command refuses to seed a regular database configuration. Generated host credentials are stored in a local file with owner-only permissions and are not printed. Services still need to be restarted after the machine or terminal session stops; the database survives those restarts.
