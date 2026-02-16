#!/usr/bin/env bash
# scripts/restore-db.sh
# Database restore script for LMS Platform.
#
# Usage:
#   ./scripts/restore-db.sh /path/to/backup.sql.gz      # restore from local file
#   ./scripts/restore-db.sh s3://bucket/db-backups/backup.sql.gz  # restore from S3
#   ./scripts/restore-db.sh --list                      # list available backups
#   ./scripts/restore-db.sh --list-s3                   # list S3 backups
#
# Safety Features:
#   - Confirmation prompt before destructive operations
#   - Automatic backup of current database before restore
#   - Integrity verification of backup file
#   - Dry-run mode for testing
#
# Environment Variables:
#   DB_CONTAINER    - Docker container name (default: db)
#   DB_USER         - PostgreSQL user (default: postgres)
#   DB_NAME         - Database name (default: lms_db)
#   BACKUP_DIR      - Local backup directory (default: /opt/lms/backups)
#   BACKUP_S3_BUCKET - S3 bucket for backups (optional)
#   COMPOSE_FILE    - Docker compose file (default: docker-compose.prod.yml)
#   FORCE           - Skip confirmation prompts (default: false)
#   DRY_RUN         - Don't actually restore, just validate (default: false)

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration (override via environment)
DB_CONTAINER="${DB_CONTAINER:-db}"
DB_USER="${DB_USER:-postgres}"
DB_NAME="${DB_NAME:-lms_db}"
BACKUP_DIR="${BACKUP_DIR:-/opt/lms/backups}"
BACKUP_S3_BUCKET="${BACKUP_S3_BUCKET:-}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
FORCE="${FORCE:-false}"
DRY_RUN="${DRY_RUN:-false}"

log_info() {
    echo -e "${GREEN}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1" >&2
}

show_help() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS] <backup-file>

Restore LMS database from a backup file.

Arguments:
  backup-file       Path to backup file (.sql.gz) or S3 URI (s3://bucket/path)

Options:
  --list            List available local backups
  --list-s3         List available S3 backups (requires BACKUP_S3_BUCKET)
  --dry-run         Validate backup without restoring
  --force           Skip confirmation prompts
  -h, --help        Show this help message

Examples:
  # Restore from local file
  $(basename "$0") /opt/lms/backups/lms_20240115_020000.sql.gz

  # Restore from S3
  $(basename "$0") s3://my-bucket/db-backups/lms_20240115_020000.sql.gz

  # List local backups
  $(basename "$0") --list

  # Dry run (validate only)
  DRY_RUN=true $(basename "$0") /path/to/backup.sql.gz

Environment Variables:
  DB_CONTAINER      Docker container name (default: db)
  DB_USER           PostgreSQL user (default: postgres)
  DB_NAME           Database name (default: lms_db)
  BACKUP_DIR        Local backup directory (default: /opt/lms/backups)
  BACKUP_S3_BUCKET  S3 bucket for backups
  COMPOSE_FILE      Docker compose file (default: docker-compose.prod.yml)
  FORCE             Skip confirmation prompts (set to 'true')
  DRY_RUN           Validate without restoring (set to 'true')

EOF
}

list_local_backups() {
    log_info "Available local backups in ${BACKUP_DIR}:"
    echo ""
    if [ -d "${BACKUP_DIR}" ]; then
        ls -lhS "${BACKUP_DIR}"/lms_*.sql.gz 2>/dev/null || echo "No backups found."
    else
        log_warn "Backup directory does not exist: ${BACKUP_DIR}"
    fi
}

list_s3_backups() {
    if [ -z "${BACKUP_S3_BUCKET}" ]; then
        log_error "BACKUP_S3_BUCKET is not set"
        exit 1
    fi
    
    log_info "Available S3 backups in s3://${BACKUP_S3_BUCKET}/db-backups/:"
    echo ""
    aws s3 ls "s3://${BACKUP_S3_BUCKET}/db-backups/" --human-readable || {
        log_error "Failed to list S3 backups. Check AWS credentials and bucket permissions."
        exit 1
    }
}

verify_backup_integrity() {
    local backup_file="$1"
    log_info "Verifying backup integrity..."
    
    # Check if file exists
    if [ ! -f "${backup_file}" ]; then
        log_error "Backup file not found: ${backup_file}"
        return 1
    fi
    
    # Check if it's a valid gzip file
    if ! gzip -t "${backup_file}" 2>/dev/null; then
        log_error "Backup file is not a valid gzip file"
        return 1
    fi
    
    # Check if it contains SQL
    if ! zcat "${backup_file}" | head -100 | grep -q "PostgreSQL database dump"; then
        log_warn "Backup file may not be a valid PostgreSQL dump"
    fi
    
    local size=$(du -h "${backup_file}" | cut -f1)
    log_info "Backup file verified: ${backup_file} (${size})"
    return 0
}

create_pre_restore_backup() {
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local pre_backup_file="${BACKUP_DIR}/lms_pre_restore_${timestamp}.sql.gz"
    
    log_info "Creating backup of current database before restore..."
    mkdir -p "${BACKUP_DIR}"
    
    docker compose -f "${COMPOSE_FILE}" exec -T "${DB_CONTAINER}" \
        pg_dump -U "${DB_USER}" "${DB_NAME}" | gzip > "${pre_backup_file}"
    
    local size=$(du -h "${pre_backup_file}" | cut -f1)
    log_info "Pre-restore backup created: ${pre_backup_file} (${size})"
}

download_from_s3() {
    local s3_uri="$1"
    local local_file="${BACKUP_DIR}/$(basename "${s3_uri}")"
    
    log_info "Downloading backup from S3: ${s3_uri}"
    aws s3 cp "${s3_uri}" "${local_file}"
    
    echo "${local_file}"
}

restore_database() {
    local backup_file="$1"
    
    log_info "Restoring database from: ${backup_file}"
    
    # Stop dependent services
    log_info "Stopping web and worker containers..."
    docker compose -f "${COMPOSE_FILE}" stop web worker beat 2>/dev/null || true
    
    # Drop and recreate database
    log_info "Dropping and recreating database ${DB_NAME}..."
    docker compose -f "${COMPOSE_FILE}" exec -T "${DB_CONTAINER}" \
        psql -U "${DB_USER}" -c "DROP DATABASE IF EXISTS ${DB_NAME};"
    
    docker compose -f "${COMPOSE_FILE}" exec -T "${DB_CONTAINER}" \
        psql -U "${DB_USER}" -c "CREATE DATABASE ${DB_NAME};"
    
    # Restore from backup
    log_info "Restoring data..."
    zcat "${backup_file}" | docker compose -f "${COMPOSE_FILE}" exec -T "${DB_CONTAINER}" \
        psql -U "${DB_USER}" -d "${DB_NAME}" --quiet
    
    # Restart services
    log_info "Restarting services..."
    docker compose -f "${COMPOSE_FILE}" up -d web worker beat
    
    log_info "Database restore complete!"
}

confirm_restore() {
    if [ "${FORCE}" = "true" ]; then
        return 0
    fi
    
    echo ""
    echo -e "${RED}WARNING: This will DESTROY the current database and replace it with the backup.${NC}"
    echo ""
    echo "Database: ${DB_NAME}"
    echo "Backup: $1"
    echo ""
    read -p "Are you sure you want to proceed? (yes/no): " confirm
    
    if [ "${confirm}" != "yes" ]; then
        log_info "Restore cancelled."
        exit 0
    fi
}

main() {
    # Parse arguments
    case "${1:-}" in
        -h|--help)
            show_help
            exit 0
            ;;
        --list)
            list_local_backups
            exit 0
            ;;
        --list-s3)
            list_s3_backups
            exit 0
            ;;
        --dry-run)
            DRY_RUN="true"
            shift
            ;;
        --force)
            FORCE="true"
            shift
            ;;
    esac
    
    # Check for backup file argument
    local backup_source="${1:-}"
    if [ -z "${backup_source}" ]; then
        log_error "No backup file specified"
        show_help
        exit 1
    fi
    
    local backup_file=""
    
    # Handle S3 URI
    if [[ "${backup_source}" == s3://* ]]; then
        mkdir -p "${BACKUP_DIR}"
        backup_file=$(download_from_s3 "${backup_source}")
    else
        backup_file="${backup_source}"
    fi
    
    # Verify backup integrity
    if ! verify_backup_integrity "${backup_file}"; then
        exit 1
    fi
    
    # Dry run mode
    if [ "${DRY_RUN}" = "true" ]; then
        log_info "Dry run complete. Backup file is valid."
        exit 0
    fi
    
    # Confirm restore
    confirm_restore "${backup_file}"
    
    # Create pre-restore backup
    create_pre_restore_backup
    
    # Perform restore
    restore_database "${backup_file}"
    
    # Cleanup downloaded S3 file
    if [[ "${backup_source}" == s3://* ]]; then
        rm -f "${backup_file}"
        log_info "Cleaned up temporary download."
    fi
    
    echo ""
    log_info "Restore completed successfully!"
    echo ""
    echo "Next steps:"
    echo "  1. Verify the application is working correctly"
    echo "  2. Check logs: docker compose -f ${COMPOSE_FILE} logs -f web"
    echo "  3. If issues occur, restore from pre-restore backup in ${BACKUP_DIR}"
}

main "$@"
