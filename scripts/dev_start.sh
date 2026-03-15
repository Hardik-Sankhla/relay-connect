#!/usr/bin/env bash
# scripts/dev_start.sh — start server + agent + run quickstart demo
# Great for testing everything at once.
# Run: bash scripts/dev_start.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PORT=8765
TOKEN="dev-token"

echo ""
echo "  relay-connect — dev start"
echo ""

# Kill any existing relay processes
pkill -f "relay server" 2>/dev/null || true
pkill -f "relay-agent" 2>/dev/null || true
sleep 0.3

# Start relay server in background
echo "  Starting relay server on ws://127.0.0.1:${PORT}..."
RELAY_TOKEN="${TOKEN}" relay server start --host 127.0.0.1 --port "${PORT}" &
SERVER_PID=$!
sleep 0.5

# Start agent in background
echo "  Starting demo agent..."
RELAY_TOKEN="${TOKEN}" relay-agent \
  --relay "ws://127.0.0.1:${PORT}" \
  --name "demo-server" \
  --tags "dev,local" &
AGENT_PID=$!
sleep 0.5

echo "  Server PID: ${SERVER_PID}"
echo "  Agent PID:  ${AGENT_PID}"
echo ""
echo "  Running quickstart demo..."
echo ""

# Run quickstart
cd "${REPO_DIR}"
RELAY_URL="ws://127.0.0.1:${PORT}" \
RELAY_TOKEN="${TOKEN}" \
RELAY_CLIENT_ID="dev-laptop" \
RELAY_AGENT="demo-server" \
python examples/quickstart.py

# Cleanup
kill "${SERVER_PID}" "${AGENT_PID}" 2>/dev/null || true
echo "  Processes stopped."
echo ""
