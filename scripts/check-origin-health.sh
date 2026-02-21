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

retry() {
  local attempts="$1"
  local sleep_seconds="$2"
  local label="$3"
  shift 3

  local i=1
  while [[ $i -le $attempts ]]; do
    if "$@"; then
      echo "[ok] $label"
      return 0
    fi
    echo "[retry $i/$attempts] $label"
    sleep "$sleep_seconds"
    i=$((i + 1))
  done

  echo "[fail] $label"
  return 1
}

check_web_container_live() {
  compose exec -T web python -c "import sys,urllib.request;
urls=['http://localhost:8000/health/live/','http://localhost:8000/health/'];
ok=False;
for u in urls:
    try:
        urllib.request.urlopen(u, timeout=5);
        ok=True;
        break
    except Exception:
        pass
sys.exit(0 if ok else 1)"
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

  echo "== web container liveness =="
  retry 12 5 "web /health/live/" check_web_container_live

  echo "== nginx edge checks =="
  if ! retry 12 5 "nginx /health/live/" check_nginx_path "/health/live/"; then
    retry 6 3 "nginx /health/" check_nginx_path "/health/"
  fi
  retry 12 5 "nginx /api/tenants/theme/" check_nginx_path "/api/tenants/theme/"
  retry 8 3 "nginx login endpoint status class" check_login_endpoint_code
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
