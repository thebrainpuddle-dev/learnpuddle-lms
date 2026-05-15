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
DEPLOY_SHA="${DEPLOY_SHA:-}"
REGISTRY="${REGISTRY:-ghcr.io/thebrainpuddle-dev/learnpuddle-lms}"

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

if [ -z "$DEPLOY_SHA" ]; then
    DEPLOY_SHA="$(git rev-parse HEAD)"
fi
echo "Deploying commit: ${DEPLOY_SHA}"

# Step 4: Pull immutable CI-built app images by default. Set
# BUILD_ON_DROPLET=true only for an explicit emergency fallback; normal
# production deploys should not compile backend/frontend images on the droplet.
if [ "${BUILD_ON_DROPLET:-false}" = "true" ]; then
    echo "BUILD_ON_DROPLET=true: building web and nginx images locally..."
    $COMPOSE build web nginx
else
    echo "Pulling CI-built backend and nginx images from ${REGISTRY}..."
    echo "If this fails with an auth error, run: docker login ghcr.io"
    docker pull "${REGISTRY}/backend:${DEPLOY_SHA}"
    docker tag "${REGISTRY}/backend:${DEPLOY_SHA}" lms-backend:latest
    docker pull "${REGISTRY}/nginx:${DEPLOY_SHA}"
    docker tag "${REGISTRY}/nginx:${DEPLOY_SHA}" lms-nginx:latest
fi

# Step 5: Start DB + Redis
echo "Starting database and Redis..."
$COMPOSE pull db redis
$COMPOSE up -d db redis

echo "Waiting 20s for DB to be ready..."
sleep 20

# Step 6: Migrations
echo "Running migrations..."
$COMPOSE run --rm -T web python manage.py migrate --noinput

echo "Collecting static files (run as root to fix volume permissions)..."
$COMPOSE run --rm -T -u root web python manage.py collectstatic --noinput

# Step 7: Superadmin bootstrap (non-blocking)
echo ""
if [ -n "${DJANGO_SUPERUSER_EMAIL:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
  echo "Creating superadmin via env vars if missing..."
  DJANGO_SUPERUSER_EMAIL="$DJANGO_SUPERUSER_EMAIL" \
  DJANGO_SUPERUSER_PASSWORD="$DJANGO_SUPERUSER_PASSWORD" \
  $COMPOSE run --rm -T web python manage.py createsuperuser --noinput || true
else
  if $COMPOSE run --rm -T web python manage.py shell -c "from django.contrib.auth import get_user_model; import sys; U=get_user_model(); sys.exit(0 if U.objects.filter(is_superuser=True).exists() else 1)"; then
    echo "Superadmin already exists; skipping interactive createsuperuser step."
  else
    echo "No superadmin found. Create one manually when ready:"
    echo "  $COMPOSE run --rm web python manage.py createsuperuser"
  fi
fi

# Step 8: Start all services
echo "Starting all services..."
$COMPOSE up -d --remove-orphans

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
