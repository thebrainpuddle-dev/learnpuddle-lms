#!/bin/bash
# LearnPuddle Droplet Deployment Script
# Run this ON the Droplet after cloning the repo.
# Usage: ./scripts/deploy-droplet.sh [REPO_URL]
#
# Example: ./scripts/deploy-droplet.sh https://github.com/thebrainpuddle-dev/learnpuddle-lms.git

set -euo pipefail

REPO_URL="${1:-https://github.com/thebrainpuddle-dev/learnpuddle-lms.git}"
APP_DIR="/opt/lms"
BRANCH="${DEPLOY_BRANCH:-main}"
COMPOSE="docker compose --env-file .env -f docker-compose.prod.yml"

echo "=== LearnPuddle Droplet Deployment ==="

# Step 1: Server setup (if Docker not installed)
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    apt update && apt upgrade -y
    curl -fsSL https://get.docker.com | sh
    apt install -y docker-compose-plugin
fi

# Step 2: Clone or update repo
if [ -n "$REPO_URL" ]; then
    if [ -d "$APP_DIR/.git" ]; then
        echo "Updating existing repo..."
        cd "$APP_DIR"
        git fetch origin "$BRANCH"
        git checkout "$BRANCH"
        git pull --ff-only origin "$BRANCH"
    else
        echo "Cloning repo..."
        mkdir -p "$(dirname $APP_DIR)"
        git clone "$REPO_URL" "$APP_DIR"
        cd "$APP_DIR"
        git checkout "$BRANCH"
    fi
else
    if [ ! -d "$APP_DIR" ]; then
        echo "Error: No repo URL provided and $APP_DIR does not exist."
        echo "Usage: $0 https://github.com/thebrainpuddle-dev/learnpuddle-lms.git"
        exit 1
    fi
    cd "$APP_DIR"
fi

# Step 3: Check .env exists (create from template if missing)
if [ ! -f .env ]; then
    if [ -f .env.production.example ]; then
        cp .env.production.example .env
        echo "Created .env from .env.production.example - EDIT IT: nano .env"
        exit 1
    elif [ -f .env.example ]; then
        cp .env.example .env
        echo "Created .env from .env.example - EDIT IT: nano .env"
        exit 1
    else
        echo "ERROR: No .env and no template found. Copy .env.deploy from your Mac:"
        echo "  scp .env.deploy root@64.227.185.164:/opt/lms/.env  # Replace IP if different"
        exit 1
    fi
fi

echo "Deploying commit: $(git rev-parse --short HEAD)"

# Step 4: Start DB + Redis
echo "Starting database and Redis..."
$COMPOSE up -d db redis

echo "Waiting 20s for DB to be ready..."
sleep 20

# Step 5: Build images that serve backend/frontend code
echo "Building web and nginx images..."
$COMPOSE build web nginx

# Step 5: Migrations
echo "Running migrations..."
$COMPOSE run --rm web python manage.py migrate --noinput

echo "Collecting static files (run as root to fix volume permissions)..."
$COMPOSE run --rm -u root web python manage.py collectstatic --noinput

# Step 6: Superadmin bootstrap (non-blocking)
echo ""
if [ -n "${DJANGO_SUPERUSER_EMAIL:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
  echo "Creating superadmin via env vars if missing..."
  DJANGO_SUPERUSER_EMAIL="$DJANGO_SUPERUSER_EMAIL" \
  DJANGO_SUPERUSER_PASSWORD="$DJANGO_SUPERUSER_PASSWORD" \
  $COMPOSE run --rm web python manage.py createsuperuser --noinput || true
else
  if $COMPOSE run --rm web python manage.py shell -c "from django.contrib.auth import get_user_model; import sys; U=get_user_model(); sys.exit(0 if U.objects.filter(is_superuser=True).exists() else 1)"; then
    echo "Superadmin already exists; skipping interactive createsuperuser step."
  else
    echo "No superadmin found. Create one manually when ready:"
    echo "  $COMPOSE run --rm web python manage.py createsuperuser"
  fi
fi

# Step 7: Start all services
echo "Starting all services (force recreate to ensure new frontend bundle is served)..."
$COMPOSE up -d --force-recreate

DOMAIN="$(awk -F= '/^PLATFORM_DOMAIN=/{print $2}' .env 2>/dev/null | tail -1 | tr -d '\r')"
if [ -z "$DOMAIN" ]; then DOMAIN="localhost"; fi
echo "Running origin health checks via domain: $DOMAIN"
./scripts/check-origin-health.sh docker-compose.prod.yml "$DOMAIN"
echo "Frontend bundle at origin:"
curl -sSL -H "Host: $DOMAIN" http://127.0.0.1/ | grep -oE '/static/js/main\.[a-z0-9]+\.js' | head -n1 || true

echo ""
echo "=== Deployment complete! ==="
echo "Check: curl -s http://localhost/health/"
echo "Site: https://learnpuddle.com"
