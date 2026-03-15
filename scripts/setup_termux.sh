#!/data/data/com.termux/files/usr/bin/bash
# scripts/setup_termux.sh — install and start relay-agent on Termux (Android)
# Run on Termux: bash scripts/setup_termux.sh

set -euo pipefail

RELAY_URL="${RELAY_URL:-ws://192.168.1.100:8765}"
AGENT_NAME="${AGENT_NAME:-my-phone}"
RELAY_TOKEN="${RELAY_TOKEN:-dev-token}"

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║    relay-connect  Termux setup       ║"
echo "  ╚══════════════════════════════════════╝"
echo ""
echo "  Relay URL:  ${RELAY_URL}"
echo "  Agent name: ${AGENT_NAME}"
echo ""

# ── 1. Update & install Python deps ──
echo "  [1/4] Installing packages..."
pkg update -y -q 2>/dev/null || true
pkg install -y python 2>/dev/null || true
echo "  ✓ Python: $(python --version)"

# ── 2. Install relay-connect ──
echo ""
echo "  [2/4] Installing relay-connect..."
python -m pip install --upgrade pip setuptools wheel --quiet 2>/dev/null || true
python -m pip install git+https://github.com/Hardik-Sankhla/relay-connect.git --quiet
echo "  ✓ relay-connect installed"

# ── 3. Create start script ──
echo ""
echo "  [3/4] Creating start script..."
START_SCRIPT="$HOME/start-relay-agent.sh"
cat > "$START_SCRIPT" <<SCRIPT
#!/data/data/com.termux/files/usr/bin/bash
export RELAY_TOKEN="${RELAY_TOKEN}"
exec relay-agent \\
  --relay "${RELAY_URL}" \\
  --name "${AGENT_NAME}" \\
  --tags "termux,android" \\
  --deploy-base "\$HOME/relay-deploy"
SCRIPT
chmod +x "$START_SCRIPT"
echo "  ✓ Start script: $START_SCRIPT"

# ── 4. Optionally install Termux:Boot autostart ──
BOOT_DIR="$HOME/.termux/boot"
if [ -d "$BOOT_DIR" ]; then
  echo ""
  echo "  [4/4] Installing Termux:Boot autostart..."
  cp "$START_SCRIPT" "$BOOT_DIR/relay-agent.sh"
  echo "  ✓ Will auto-start on boot"
else
  echo ""
  echo "  [4/4] Termux:Boot not found (optional)"
  echo "  Install Termux:Boot from F-Droid for auto-start on phone reboot"
fi

echo ""
echo "  ┌─ Setup complete ────────────────────────────────────┐"
echo "  │                                                     │"
echo "  │  Start the agent:                                   │"
echo "  │    ~/start-relay-agent.sh                          │"
echo "  │                                                     │"
echo "  │  Or manually:                                       │"
echo "  │    relay-agent --relay ${RELAY_URL}  │"
echo "  │                --name ${AGENT_NAME}                 │"
echo "  │                                                     │"
echo "  │  Then from your laptop:                             │"
echo "  │    relay add ${AGENT_NAME}                          │"
echo "  │    relay ssh ${AGENT_NAME}                          │"
echo "  │    relay deploy ./myapp ${AGENT_NAME}               │"
echo "  └─────────────────────────────────────────────────────┘"
echo ""
