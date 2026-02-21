#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <compose-file> [domain]"
  exit 2
fi

COMPOSE_FILE="$1"
DOMAIN="${2:-localhost}"

compose() {
  docker compose -f "$COMPOSE_FILE" "$@"
}

check_web_container_health() {
  compose exec -T web python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/', timeout=5)"
}

check_nginx_path() {
  local path="$1"
  curl -fsS --max-time 10 -H "Host: $DOMAIN" "http://127.0.0.1${path}" >/dev/null
}

check_login_endpoint_code() {
  local code
  code="$(curl -sS --max-time 12 -o /tmp/login-check.json -w '%{http_code}' \
    -H "Host: $DOMAIN" \
    -H "Content-Type: application/json" \
    -X POST "http://127.0.0.1/api/users/auth/login/" \
    --data '{"email":"healthcheck@example.test","password":"not-a-real-password","portal":"tenant"}')"

  case "$code" in
    200|400|401|403|429) return 0 ;;
    *) echo "Unexpected login status code: $code"; return 1 ;;
  esac
}

run_checks() {
  echo "== docker compose ps =="
  compose ps
  echo "== web container health =="
  check_web_container_health
  echo "== nginx /health/ =="
  check_nginx_path "/health/"
  echo "== nginx /api/tenants/theme/ =="
  check_nginx_path "/api/tenants/theme/"
  echo "== nginx /api/users/auth/login/ status =="
  check_login_endpoint_code
}

echo "Running origin checks via domain: $DOMAIN"
if run_checks; then
  echo "Origin checks passed"
  exit 0
fi

echo "Origin checks failed, restarting nginx once and retrying..."
compose restart nginx
sleep 8
run_checks
echo "Origin checks passed after nginx restart"
