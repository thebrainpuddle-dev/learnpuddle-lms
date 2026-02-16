#!/bin/bash
# Run deployment from your Mac (requires SSH access to droplet)
# Usage: ./scripts/run-deploy-from-mac.sh YOUR_DROPLET_IP
# Example: ./scripts/run-deploy-from-mac.sh 64.227.185.164

set -e

DROPLET_IP="${1:?Usage: $0 YOUR_DROPLET_IP}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Deploying to $DROPLET_IP ==="

# 1. Copy .env to droplet
if [ -f "$PROJECT_ROOT/.env.deploy" ]; then
    echo "Copying .env.deploy to droplet..."
    scp "$PROJECT_ROOT/.env.deploy" "root@$DROPLET_IP:/opt/lms/.env"
else
    echo "WARNING: .env.deploy not found. Ensure .env exists on droplet."
fi

# 2. Run deploy script on droplet
echo "Running deploy on droplet..."
ssh "root@$DROPLET_IP" "cd /opt/lms && chmod +x scripts/deploy-droplet.sh && ./scripts/deploy-droplet.sh"

echo ""
echo "=== Done! Check https://learnpuddle.com/health/ ==="
