#!/bin/bash
# Migrate LMS repo to a new GitHub account
# Run this locally (on your Mac) before deploying.
#
# Usage: ./scripts/migrate-repo.sh https://github.com/NEW_ORG/LMS.git
#    or: ./scripts/migrate-repo.sh git@github.com:NEW_ORG/LMS.git

set -e

NEW_REPO="${1:-}"

if [ -z "$NEW_REPO" ]; then
    echo "Usage: $0 <new-repo-url>"
    echo "Example: $0 https://github.com/your-org/LMS.git"
    exit 1
fi

echo "=== Migrating repo to $NEW_REPO ==="

# Ensure we're in repo root
cd "$(git rev-parse --show-toplevel)"

# Add new remote
git remote add new-origin "$NEW_REPO" 2>/dev/null || git remote set-url new-origin "$NEW_REPO"

# Push main branch
echo "Pushing main branch..."
git push -u new-origin main

# Push develop if it exists
if git show-ref --verify --quiet refs/heads/develop; then
    echo "Pushing develop branch..."
    git push new-origin develop
fi

echo ""
echo "=== Migration complete! ==="
echo "New repo: $NEW_REPO"
echo ""
echo "Optional: Make new-origin the default:"
echo "  git remote remove origin"
echo "  git remote rename new-origin origin"
