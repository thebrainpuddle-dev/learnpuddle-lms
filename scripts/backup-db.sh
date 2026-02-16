#!/usr/bin/env bash
# scripts/backup-db.sh
# Automated PostgreSQL backup for production.
#
# Usage:
#   ./scripts/backup-db.sh                    # local backup only
#   BACKUP_S3_BUCKET=my-bucket ./scripts/backup-db.sh  # upload to S3
#
# Schedule via cron:
#   0 2 * * * /opt/lms/scripts/backup-db.sh >> /var/log/lms-backup.log 2>&1
#
# Or via docker compose:
#   docker compose -f docker-compose.prod.yml exec -T db \
#     pg_dump -U postgres lms_db | gzip > /backups/lms_$(date +%Y%m%d_%H%M%S).sql.gz

set -euo pipefail

# Configuration (override via environment)
DB_CONTAINER="${DB_CONTAINER:-db}"
DB_USER="${DB_USER:-learnpuddle}"
DB_NAME="${DB_NAME:-learnpuddle_db}"
BACKUP_DIR="${BACKUP_DIR:-/opt/lms/backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
BACKUP_S3_BUCKET="${BACKUP_S3_BUCKET:-}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="lms_${TIMESTAMP}.sql.gz"

echo "[$(date)] Starting database backup..."

# Create backup directory
mkdir -p "${BACKUP_DIR}"

# Dump database (via docker exec into the postgres container)
docker compose -f "${COMPOSE_FILE}" exec -T "${DB_CONTAINER}" \
    pg_dump -U "${DB_USER}" "${DB_NAME}" | gzip > "${BACKUP_DIR}/${BACKUP_FILE}"

FILESIZE=$(du -h "${BACKUP_DIR}/${BACKUP_FILE}" | cut -f1)
echo "[$(date)] Backup created: ${BACKUP_FILE} (${FILESIZE})"

# Upload to S3 if bucket is configured
if [ -n "${BACKUP_S3_BUCKET}" ]; then
    echo "[$(date)] Uploading to s3://${BACKUP_S3_BUCKET}/db-backups/${BACKUP_FILE}..."
    aws s3 cp "${BACKUP_DIR}/${BACKUP_FILE}" "s3://${BACKUP_S3_BUCKET}/db-backups/${BACKUP_FILE}"
    echo "[$(date)] Upload complete."
fi

# Cleanup old local backups
echo "[$(date)] Removing local backups older than ${BACKUP_RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -name "lms_*.sql.gz" -mtime +${BACKUP_RETENTION_DAYS} -delete

echo "[$(date)] Backup complete."
