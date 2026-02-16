#!/bin/bash
# LearnPuddle Droplet Deployment Script
# Run this ON the Droplet after cloning the repo.
# Usage: ./scripts/deploy-droplet.sh [REPO_URL]
#
# Example: ./scripts/deploy-droplet.sh https://github.com/your-org/LMS.git

set -e

REPO_URL="${1:-}"
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
        echo "Usage: $0 https://github.com/your-org/LMS.git"
        exit 1
    fi
    cd "$APP_DIR"
fi

# Step 3: Check .env exists
if [ ! -f .env ]; then
    echo ""
    echo "ERROR: .env file not found!"
    echo "Create it: cp .env.production.example .env"
    echo "Then edit: nano .env"
    echo ""
    exit 1
fi

# Step 4: Start DB + Redis
echo "Starting database and Redis..."
docker compose -f docker-compose.prod.yml up -d db redis

echo "Waiting 15s for DB to be ready..."
sleep 15

# Step 5: Migrations
echo "Running migrations..."
docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate --noinput

echo "Collecting static files..."
docker compose -f docker-compose.prod.yml run --rm web python manage.py collectstatic --noinput

# Step 6: Create superadmin (if not exists)
echo ""
echo "Create superadmin user (email: admin@learnpuddle.com recommended):"
docker compose -f docker-compose.prod.yml run --rm web python manage.py createsuperuser || true

# Step 7: Start all services
echo "Starting all services..."
docker compose -f docker-compose.prod.yml up -d

echo ""
echo "=== Deployment complete! ==="
echo "Check: curl -s http://localhost/health/"
echo "Site: https://learnpuddle.com"
