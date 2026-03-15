#!/usr/bin/env bash
# scripts/setup_laptop.sh — one-command laptop setup
# Run: bash scripts/setup_laptop.sh

set -euo pipefail

RELAY_PORT="${RELAY_PORT:-8765}"
RELAY_TOKEN="${RELAY_TOKEN:-$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')}"

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║     relay-connect  laptop setup      ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# ── 1. Install ──
echo "  [1/4] Installing relay-connect..."
pip install -e "$(dirname "$0")/.." --quiet
echo "  ✓ Installed"

# ── 2. Init config ──
echo ""
echo "  [2/4] Initialising config..."
relay init --relay-url "ws://0.0.0.0:${RELAY_PORT}" 2>/dev/null || true
echo "  ✓ Config at ~/.relay/config.json"

# ── 3. Save token ──
echo ""
echo "  [3/4] Saving relay token..."
RELAY_CFG="$HOME/.relay"
mkdir -p "$RELAY_CFG"
echo "RELAY_TOKEN=${RELAY_TOKEN}" > "$RELAY_CFG/.env"
chmod 600 "$RELAY_CFG/.env"
echo "  ✓ Token saved to ~/.relay/.env"

# ── 4. Print next steps ──
echo ""
echo "  [4/4] Setup complete!"
echo ""
echo "  ┌─ Next steps ──────────────────────────────────────────────────┐"
echo "  │                                                               │"
echo "  │  On your laptop (start the relay server):                     │"
echo "  │    RELAY_TOKEN=${RELAY_TOKEN:0:12}...  relay server start                 │"
echo "  │                                                               │"
echo "  │  On each remote server / Termux (start the agent):           │"
echo "  │    pip install relay-connect                                  │"
echo "  │    relay-agent --relay ws://YOUR_LAPTOP_IP:${RELAY_PORT} --name prod-1  │"
echo "  │                                                               │"
echo "  │  Back on your laptop (register + connect):                   │"
echo "  │    relay add prod-1                                           │"
echo "  │    relay ssh prod-1                                           │"
echo "  │    relay deploy ./dist prod-1                                 │"
echo "  │                                                               │"
echo "  └───────────────────────────────────────────────────────────────┘"
echo ""
echo "  RELAY_TOKEN (keep safe): ${RELAY_TOKEN}"
echo ""
