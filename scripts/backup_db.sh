#!/usr/bin/env bash
# =============================================================================
# scripts/backup_db.sh
# Creates a timestamped, gzipped PostgreSQL backup.
# Usage: ./scripts/backup_db.sh [output_dir]
# =============================================================================

set -eo pipefail

BACKUP_DIR="${1:-./backups}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/db_backup_${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"

DB_USER="${POSTGRES_USER:-tower}"
DB_NAME="${POSTGRES_DB:-tower_defense_db}"

echo "==> Starting database backup for '${DB_NAME}'..."

# Check if running container exists
if docker ps --format '{{.Names}}' | grep -qE "^tower_defense_(prod_)?postgres$"; then
    CONTAINER_NAME="$(docker ps --format '{{.Names}}' | grep -E '^tower_defense_(prod_)?postgres$' | head -n 1)"
    echo "==> Detected running Postgres container: ${CONTAINER_NAME}"
    docker exec -t "${CONTAINER_NAME}" pg_dump -U "${DB_USER}" -d "${DB_NAME}" --clean --if-exists | gzip > "${BACKUP_FILE}"
elif command -v pg_dump >/dev/null 2>&1; then
    echo "==> Using local pg_dump..."
    pg_dump -U "${DB_USER}" -d "${DB_NAME}" -h "${DB_HOST:-localhost}" -p "${DB_PORT:-5433}" --clean --if-exists | gzip > "${BACKUP_FILE}"
else
    echo "ERROR: Neither docker container (tower_defense_postgres) nor local pg_dump was found." >&2
    exit 1
fi

FILE_SIZE="$(du -h "${BACKUP_FILE}" | cut -f1)"
echo "==> Backup completed successfully!"
echo "    File: ${BACKUP_FILE} (${FILE_SIZE})"
