# Level 4 data migration

Migration `units.0013_three_upgrade_levels` converts existing paid Level 4 state before adding Level 1–3 constraints. Deploy backend and frontend as one release, apply `python manage.py migrate`, then restart WebSocket workers and have connected clients reconnect so every player receives the converted authoritative snapshot. Do not run mixed old and new workers during this migration.

The migration finds every team/type pair with a Level 4 team record or entity. It sets the team record and all entities of that pair to Level 3. For living active, queued or disabled entities, it computes the Level 3 maximum HP from the same base-HP policy as the service and preserves current HP as a fraction of the old maximum, rounded to nearest integer and capped at the new maximum. Destroyed entities remain at zero HP. Level 3 combat damage and attack rate take effect from the new level; per-entity range and movement state are not reset. No entity is respawned or relocated.

Historical purchase transactions and match events are retained for audit. The migration makes no charges or refunds. It is idempotent: after conversion, repeating its data operation finds no Level 4 pair to process. A regression test migrates a paid Level 4 Infantry record with both a wounded live unit and a destroyed unit, verifies HP preservation and the new constraints, and runs the conversion a second time.

The older entity table did not constrain the lower bound. If an entity has a nonpositive saved level, the migration changes that value to Level 1 without changing HP; the preexisting modifier calculation already treated it as Level 1.

The old migrations retain their historical Level 4 definitions so a fresh database can replay its migration chain; `0013` is the authoritative end state. The old Level 4 equipment assets may remain as inert static files, but they are no longer loaded or selected by the game. Existing active clients must reconnect after deployment because a database migration cannot send them a live WebSocket event.

## Local data audit

The workspace's `backend/db.sqlite3` was inspected read-only before deployment. It has no `units_teamunitupgrade` table and no saved `units_gameentity` rows, so there was no local Level 4 record to convert. No persistent workspace database was migrated for QA; migration tests used isolated databases. A production database was not available in this workspace, so its Level 4 count is unknown until deployment. The migration test covered actual Level 4 records on both SQLite and PostgreSQL.
