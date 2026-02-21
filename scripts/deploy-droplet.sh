#!/bin/bash
# LearnPuddle Droplet Deployment Script
# Run this ON the Droplet after cloning the repo.
# Usage: ./scripts/deploy-droplet.sh [REPO_URL]
#
# Example: ./scripts/deploy-droplet.sh https://github.com/thebrainpuddle-dev/learnpuddle-lms.git

set -e

REPO_URL="${1:-https://github.com/thebrainpuddle-dev/learnpuddle-lms.git}"
APP_DIR="/opt/lms"

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
        cd "$APP_DIR" && git pull
    else
        echo "Cloning repo..."
        mkdir -p "$(dirname $APP_DIR)"
        git clone "$REPO_URL" "$APP_DIR"
        cd "$APP_DIR"
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

# Step 4: Start DB + Redis
echo "Starting database and Redis..."
docker compose -f docker-compose.prod.yml up -d db redis

echo "Waiting 20s for DB to be ready..."
sleep 20

# Step 5: Migrations
echo "Running migrations..."
docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate --noinput

echo "Collecting static files (run as root to fix volume permissions)..."
docker compose -f docker-compose.prod.yml run --rm -u root web python manage.py collectstatic --noinput

# Step 6: Create superadmin (if not exists)
echo ""
echo "Create superadmin user (email: admin@learnpuddle.com recommended):"
docker compose -f docker-compose.prod.yml run --rm web python manage.py createsuperuser || true

# Step 7: Start all services
echo "Starting all services..."
docker compose -f docker-compose.prod.yml up -d

DOMAIN="$(awk -F= '/^PLATFORM_DOMAIN=/{print $2}' .env 2>/dev/null | tail -1 | tr -d '\r')"
if [ -z "$DOMAIN" ]; then DOMAIN="localhost"; fi
echo "Running origin health checks via domain: $DOMAIN"
./scripts/check-origin-health.sh docker-compose.prod.yml "$DOMAIN"

echo ""
echo "=== Deployment complete! ==="
echo "Check: curl -s http://localhost/health/"
echo "Site: https://learnpuddle.com"
