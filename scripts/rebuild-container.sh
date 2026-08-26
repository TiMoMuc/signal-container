#!/usr/bin/env bash
# rebuild-container.sh — rebuild signal-cli Docker image and restart containers
#
# Purpose: Signal servers change every ~3 months, requiring signal-cli updates.
#          This script rebuilds the container (which downloads the latest signal-cli)
#          and restarts all services to ensure continued operation.
#
# Usage:
#   ./scripts/rebuild-container.sh
#
# When run by the scheduler (launchd / systemd):
#   - Logs to ~/Library/Logs/signal-container-rebuild.log
#   - Runs monthly to stay ahead of the 3-month expiration

set -euo pipefail

# Determine the directory where this script lives, then move to the project root.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Log file location
LOG="$HOME/Library/Logs/signal-container-rebuild.log"

# Create log directory if it doesn't exist
mkdir -p "$(dirname "$LOG")"

# Redirect all output to log file
exec >> "$LOG" 2>&1

echo ""
echo "=========================================="
echo "signal-cli container rebuild started: $(date)"
echo "=========================================="

# Navigate to the project directory
cd "$PROJECT_DIR"
echo "Working directory: $(pwd)"

if [ ! -f docker-compose.yml ]; then
    echo "ERROR: docker-compose.yml not found in $PROJECT_DIR"
    exit 1
fi

# Prefer modern Docker Compose v2, but fall back to docker-compose if needed.
if docker compose version >/dev/null 2>&1; then
    COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE=(docker-compose)
else
    echo "ERROR: Neither 'docker compose' nor 'docker-compose' is available."
    exit 1
fi

echo "Compose command: ${COMPOSE[*]}"

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    echo "ERROR: Docker is not running. Please start Docker Desktop."
    exit 1
fi

# Check current signal-cli version in container (if it exists)
echo ""
echo "Checking current signal-cli version..."
if docker images signal-cli:latest -q | grep -q .; then
    CURRENT_VERSION=$(docker run --rm signal-cli:latest --version 2>/dev/null | awk '{print $NF}' || echo "unknown")
    echo "Current version: $CURRENT_VERSION"
else
    CURRENT_VERSION="none"
    echo "No existing signal-cli image found."
fi

# Pull latest code (if this is a git repo)
if [ -d .git ]; then
    echo ""
    echo "Pulling latest changes from git repository..."
    git pull origin main || git pull origin master || echo "Note: Could not pull from git (may not be on main/master branch)"
fi

# Stop running containers
echo ""
echo "Stopping existing containers..."
"${COMPOSE[@]}" down || true

# Remove old image to force a fresh build
echo ""
echo "Removing old signal-cli image..."
docker rmi signal-cli:latest 2>/dev/null || echo "No old image to remove."

# Rebuild the image (this downloads the latest signal-cli release)
echo ""
echo "Rebuilding signal-cli image (this downloads the latest signal-cli)..."
"${COMPOSE[@]}" build --no-cache

# Check new version
echo ""
echo "Checking new signal-cli version..."
NEW_VERSION=$(docker run --rm signal-cli:latest --version 2>/dev/null | awk '{print $NF}' || echo "unknown")
echo "New version: $NEW_VERSION"

# Start containers
echo ""
echo "Starting containers..."
"${COMPOSE[@]}" up -d

# Wait a moment for the container to stabilize
sleep 5

# Check container status
echo ""
echo "Container status:"
"${COMPOSE[@]}" ps

# Check recent logs
echo ""
echo "Recent container logs:"
"${COMPOSE[@]}" logs --tail=20

echo ""
echo "=========================================="
echo "Rebuild completed successfully: $(date)"
echo "=========================================="
echo ""

# Optional: Send a notification to Signal note-to-self
# Uncomment if you want to be notified when updates happen
# SIGNAL_HTTP=${SIGNAL_HTTP:-http://localhost:8088}
# SIGNAL_ACCOUNT=${SIGNAL_ACCOUNT:-+15551234567}
# curl -s -X POST "$SIGNAL_HTTP/api/v1/rpc" \
#   -H "Content-Type: application/json" \
#   -d "{
#     \"jsonrpc\": \"2.0\",
#     \"method\": \"send\",
#     \"params\": {
#       \"noteToSelf\": true,
#       \"message\": \"✅ Signal container rebuilt successfully\nOld: $CURRENT_VERSION\nNew: $NEW_VERSION\"
#     },
#     \"id\": 1
#   }" || echo "Could not send Signal notification"

exit 0
