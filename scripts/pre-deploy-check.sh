#!/usr/bin/env bash
# Pre-deployment validation checklist
# Run before deploying to production:
#   ./scripts/pre-deploy-check.sh
#   ./scripts/pre-deploy-check.sh --compose-file docker-compose.staging.yml  (for staging)
#
# Exit code = number of failed checks (0 = all passed)

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ERRORS=0
WARNINGS=0

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --compose-file|-f) COMPOSE_FILE="$2"; shift 2 ;;
    --help|-h)
      echo "Usage: $0 [--compose-file <file>]"
      echo "  --compose-file, -f  Docker compose file (default: docker-compose.prod.yml)"
      exit 0
      ;;
    *) echo "Unknown option: $1"; exit 2 ;;
  esac
done

# ── Helpers ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

pass()  { echo -e "  ${GREEN}PASS${NC}  $1"; }
fail()  { echo -e "  ${RED}FAIL${NC}  $1"; ERRORS=$((ERRORS + 1)); }
warn()  { echo -e "  ${YELLOW}WARN${NC}  $1"; WARNINGS=$((WARNINGS + 1)); }
info()  { echo -e "  ${BLUE}INFO${NC}  $1"; }
header(){ echo -e "\n${BLUE}━━━ $1 ━━━${NC}"; }

# ── 1. Required Environment Variables ────────────────────────────────────────
header "Required Environment Variables"

for var in SECRET_KEY DB_PASSWORD REDIS_PASSWORD PLATFORM_DOMAIN; do
  if [ -z "${!var:-}" ]; then
    fail "$var is not set"
  else
    pass "$var is set"
  fi
done

# Optional but recommended variables
for var in FLOWER_PASSWORD SENTRY_DSN EMAIL_HOST_PASSWORD; do
  if [ -z "${!var:-}" ]; then
    warn "$var is not set (recommended for production)"
  else
    pass "$var is set"
  fi
done

# ── 2. Security Settings ────────────────────────────────────────────────────
header "Security Settings"

# Check DEBUG is not True
if [ "${DEBUG:-}" = "True" ] || [ "${DEBUG:-}" = "true" ] || [ "${DEBUG:-}" = "1" ]; then
  fail "DEBUG is enabled — must be False for production"
else
  pass "DEBUG is not enabled"
fi

# Check SECRET_KEY is not a weak default
if [ -n "${SECRET_KEY:-}" ]; then
  if [ ${#SECRET_KEY} -lt 50 ]; then
    fail "SECRET_KEY is too short (${#SECRET_KEY} chars, need 50+)"
  elif echo "$SECRET_KEY" | grep -qiE '^(changeme|secret|test|django-insecure)'; then
    fail "SECRET_KEY appears to be a default/test value"
  else
    pass "SECRET_KEY length and pattern OK"
  fi
fi

# Check passwords are not trivial
for var in DB_PASSWORD REDIS_PASSWORD; do
  val="${!var:-}"
  if [ -n "$val" ] && [ ${#val} -lt 12 ]; then
    warn "$var is shorter than 12 characters"
  fi
done

# ── 3. Docker ────────────────────────────────────────────────────────────────
header "Docker"

if command -v docker &>/dev/null; then
  pass "Docker CLI is available"
else
  fail "Docker CLI is not installed"
fi

if docker info &>/dev/null; then
  pass "Docker daemon is running"
else
  fail "Docker daemon is not running (is Docker started?)"
fi

if command -v docker compose &>/dev/null || docker compose version &>/dev/null 2>&1; then
  pass "Docker Compose is available"
else
  fail "Docker Compose is not available"
fi

if [ -f "$COMPOSE_FILE" ]; then
  pass "Compose file exists: $COMPOSE_FILE"
  # Validate compose file syntax
  if docker compose -f "$COMPOSE_FILE" config --quiet 2>/dev/null; then
    pass "Compose file syntax is valid"
  else
    fail "Compose file has syntax errors (run: docker compose -f $COMPOSE_FILE config)"
  fi
else
  fail "Compose file not found: $COMPOSE_FILE"
fi

# Check disk space (warn if less than 5GB free)
DISK_AVAIL_KB=$(df -k / | awk 'NR==2 {print $4}')
DISK_AVAIL_GB=$((DISK_AVAIL_KB / 1048576))
if [ "$DISK_AVAIL_GB" -lt 2 ]; then
  fail "Less than 2 GB disk space available (${DISK_AVAIL_GB} GB free)"
elif [ "$DISK_AVAIL_GB" -lt 5 ]; then
  warn "Low disk space: ${DISK_AVAIL_GB} GB free (recommend 5+ GB)"
else
  pass "Disk space OK: ${DISK_AVAIL_GB} GB free"
fi

# ── 4. Database Connectivity ────────────────────────────────────────────────
header "Database Connectivity"

DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-learnpuddle}"

# Check if PostgreSQL is reachable (only if running outside Docker or if port is exposed)
if command -v pg_isready &>/dev/null; then
  if pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -q 2>/dev/null; then
    pass "PostgreSQL is reachable at $DB_HOST:$DB_PORT"
  else
    warn "PostgreSQL is not reachable at $DB_HOST:$DB_PORT (may be normal if using Docker networking)"
  fi
else
  info "pg_isready not available — skipping direct PostgreSQL check"
fi

# Check if the db container is healthy (if compose services are running)
if docker compose -f "$COMPOSE_FILE" ps --format json 2>/dev/null | python3 -c "
import sys, json
for line in sys.stdin:
    svc = json.loads(line)
    if svc.get('Service') == 'db':
        health = svc.get('Health', '')
        print(health)
        sys.exit(0 if health == 'healthy' else 1)
sys.exit(2)
" 2>/dev/null; then
  pass "Database container is healthy"
else
  info "Database container not running yet (will start on deploy)"
fi

# ── 5. Redis Connectivity ───────────────────────────────────────────────────
header "Redis Connectivity"

if command -v redis-cli &>/dev/null; then
  REDIS_HOST="${REDIS_HOST:-redis}"
  REDIS_PORT="${REDIS_PORT:-6379}"
  if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -a "${REDIS_PASSWORD:-}" ping 2>/dev/null | grep -q PONG; then
    pass "Redis is reachable at $REDIS_HOST:$REDIS_PORT"
  else
    warn "Redis is not reachable at $REDIS_HOST:$REDIS_PORT (may be normal if using Docker networking)"
  fi
else
  info "redis-cli not available — skipping direct Redis check"
fi

# ── 6. Django Checks ────────────────────────────────────────────────────────
header "Django Checks"

# Check if migrations are up to date (only if web container is running)
if docker compose -f "$COMPOSE_FILE" ps --status running 2>/dev/null | grep -q web; then
  if docker compose -f "$COMPOSE_FILE" exec -T web python manage.py migrate --check --noinput 2>/dev/null; then
    pass "All migrations are applied"
  else
    warn "Pending migrations detected — will be applied during deploy"
  fi

  # Check if static files are collected
  if docker compose -f "$COMPOSE_FILE" exec -T web python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.conf import settings
static_root = getattr(settings, 'STATIC_ROOT', '/app/staticfiles')
files = os.listdir(static_root) if os.path.exists(static_root) else []
exit(0 if len(files) > 0 else 1)
" 2>/dev/null; then
    pass "Static files are collected"
  else
    warn "Static files directory is empty — collectstatic will run during deploy"
  fi
else
  info "Web container is not running — skipping Django runtime checks"
fi

# ── 7. SSL/TLS ──────────────────────────────────────────────────────────────
header "SSL/TLS"

DOMAIN="${PLATFORM_DOMAIN:-}"
if [ -n "$DOMAIN" ]; then
  # Check if SSL certs exist locally
  if [ -d "nginx/ssl" ] && ls nginx/ssl/*.pem &>/dev/null 2>&1; then
    pass "SSL certificates found in nginx/ssl/"
  elif docker volume ls --format '{{.Name}}' 2>/dev/null | grep -q certbot; then
    pass "Certbot volume exists (Let's Encrypt)"
  else
    warn "No SSL certificates detected — ensure HTTPS is configured"
  fi

  # Quick DNS check
  if command -v dig &>/dev/null; then
    if dig +short "$DOMAIN" 2>/dev/null | grep -q .; then
      pass "DNS resolves for $DOMAIN"
    else
      warn "DNS does not resolve for $DOMAIN"
    fi
  elif command -v nslookup &>/dev/null; then
    if nslookup "$DOMAIN" &>/dev/null; then
      pass "DNS resolves for $DOMAIN"
    else
      warn "DNS does not resolve for $DOMAIN"
    fi
  fi
fi

# ── 8. Required Files ───────────────────────────────────────────────────────
header "Required Files"

for f in backend/Dockerfile nginx/nginx.conf; do
  if [ -f "$f" ]; then
    pass "$f exists"
  else
    fail "$f is missing"
  fi
done

# Check .env file exists (but never display its contents)
if [ -f ".env" ]; then
  pass ".env file exists"
else
  warn ".env file not found — environment variables must be set another way"
fi

# Check no .env file will be accidentally committed
if [ -f ".gitignore" ]; then
  if grep -q '\.env' .gitignore 2>/dev/null; then
    pass ".env is in .gitignore"
  else
    warn ".env is NOT in .gitignore — risk of committing secrets"
  fi
fi

# ── 9. Image Availability ───────────────────────────────────────────────────
header "Docker Images"

# Check if required images can be built or are already present
for svc in web worker asgi; do
  IMAGE=$(docker compose -f "$COMPOSE_FILE" config --format json 2>/dev/null | \
    python3 -c "import sys,json; c=json.load(sys.stdin); svc=c.get('services',{}).get('$svc',{}); print(svc.get('image','build-required'))" 2>/dev/null || echo "unknown")
  if [ "$IMAGE" = "build-required" ] || [ "$IMAGE" = "unknown" ]; then
    info "$svc: will be built from Dockerfile"
  elif docker image inspect "$IMAGE" &>/dev/null; then
    pass "$svc: image $IMAGE is available locally"
  else
    info "$svc: image $IMAGE not yet pulled (will be pulled during deploy)"
  fi
done

# ── Summary ──────────────────────────────────────────────────────────────────
header "Summary"

echo ""
if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
  echo -e "  ${GREEN}All checks passed. Ready to deploy.${NC}"
elif [ $ERRORS -eq 0 ]; then
  echo -e "  ${YELLOW}${WARNINGS} warning(s), 0 errors. Review warnings before deploying.${NC}"
else
  echo -e "  ${RED}${ERRORS} error(s), ${WARNINGS} warning(s). Fix errors before deploying.${NC}"
fi
echo ""

exit $ERRORS
