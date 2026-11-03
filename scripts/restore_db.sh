#!/usr/bin/env bash
# =============================================================================
# scripts/restore_db.sh
# Restores a PostgreSQL database from a .sql or .sql.gz dump.
# Usage: ./scripts/restore_db.sh <backup_file.sql[.gz]> [--force]
# =============================================================================

set -eo pipefail

BACKUP_FILE="$1"
FORCE_FLAG="$2"

if [ -z "${BACKUP_FILE}" ] || [ ! -f "${BACKUP_FILE}" ]; then
    echo "Usage: $0 <path_to_backup.sql[.gz]> [--force]" >&2
    echo "Error: Backup file '${BACKUP_FILE}' does not exist." >&2
    exit 1
fi

DB_USER="${POSTGRES_USER:-tower}"
DB_NAME="${POSTGRES_DB:-tower_defense_db}"

if [ "${FORCE_FLAG}" != "--force" ] && [ "${FORCE_FLAG}" != "-y" ]; then
    echo "WARNING: This will overwrite data in database '${DB_NAME}'!"
    read -r -p "Are you sure you want to proceed? [y/N]: " confirm
    if [[ ! "${confirm}" =~ ^[yY]([eE][sS])?$ ]]; then
        echo "Restore cancelled."
        exit 0
    fi
fi

echo "==> Restoring database '${DB_NAME}' from '${BACKUP_FILE}'..."

DECOMPRESS_CMD="cat"
if [[ "${BACKUP_FILE}" == *.gz ]]; then
    DECOMPRESS_CMD="gunzip -c"
fi

if docker ps --format '{{.Names}}' | grep -qE "^tower_defense_(prod_)?postgres$"; then
    CONTAINER_NAME="$(docker ps --format '{{.Names}}' | grep -E '^tower_defense_(prod_)?postgres$' | head -n 1)"
    echo "==> Restoring via container: ${CONTAINER_NAME}..."
    ${DECOMPRESS_CMD} "${BACKUP_FILE}" | docker exec -i "${CONTAINER_NAME}" psql -U "${DB_USER}" -d "${DB_NAME}"
elif command -v psql >/dev/null 2>&1; then
    echo "==> Restoring via local psql..."
    ${DECOMPRESS_CMD} "${BACKUP_FILE}" | psql -U "${DB_USER}" -d "${DB_NAME}" -h "${DB_HOST:-localhost}" -p "${DB_PORT:-5433}"
else
    echo "ERROR: Neither docker container (tower_defense_postgres) nor local psql was found." >&2
    exit 1
fi

echo "==> Database restore completed successfully!"
