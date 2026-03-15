# QUICKSTART — relay-connect

Get from zero to a working relay tunnel in under 5 minutes.

---

## Step 1 — Install

```bash
# From the repo folder:
cd relay-connect

# Dev install
pip install -e ".[dev]"

# Verify:
relay --version
relay-agent --version
```

---

## Step 2 — Test everything locally (3 terminals)

**Terminal 1 — start the relay server:**
```bash
RELAY_TOKEN=dev-token relay server start
```
You should see:
```
  Relay server running on ws://0.0.0.0:8765
  Token: dev-token
```

**Terminal 2 — start a demo agent:**
```bash
relay-agent --relay ws://localhost:8765 --name demo-server --tags dev
```
You should see:
```
  Starting relay-agent 'demo-server' → ws://localhost:8765
```

**Terminal 3 — connect and test:**
```bash
# Initialise config
relay init

# Check it's online
RELAY_TOKEN=dev-token relay status

# Run a command
RELAY_TOKEN=dev-token relay exec demo-server "uname -a"

# Deploy a directory
RELAY_TOKEN=dev-token relay deploy ./examples demo-server

# Interactive shell
RELAY_TOKEN=dev-token relay ssh demo-server
```

Note: `relay ssh`, `relay exec`, `relay deploy`, and `relay ping` auto-register
the profile if it does not already exist in your config.

---

## Step 3 — Connect your Termux phone

The easiest path is a guided setup:

```bash
relay wizard
```

If you prefer manual steps, follow below.

**On your phone in Termux:**
```bash
pkg install python git

# Install from GitHub (project is not on PyPI yet)
python -m pip install git+https://github.com/Hardik-Sankhla/relay-connect.git

relay-agent --relay ws://YOUR_LAPTOP_IP:8765 --name my-phone --tags termux
```

**On your laptop:**
```bash
RELAY_TOKEN=dev-token relay status           # my-phone should appear
RELAY_TOKEN=dev-token relay ssh my-phone     # shell on your phone!
RELAY_TOKEN=dev-token relay exec my-phone "ls ~"
RELAY_TOKEN=dev-token relay deploy ./scripts my-phone
```

If you want to set custom tags, deploy path, or post-deploy hook in advance,
you can still run `relay add my-phone --tags termux` manually.

---

## Step 4 — Run the full test suite

```bash
# Unit tests (fast, no server needed)
pytest tests/test_crypto.py tests/test_protocol.py tests/test_config.py tests/test_cli.py tests/test_regressions.py -v

# Integration tests (starts real server + agent automatically)
pytest tests/test_integration.py -v

# All tests + coverage
pytest tests/ --cov=relay --cov-report=term-missing
```

---

## Step 5 — Open in VS Code with Copilot

```bash
code .
```

Then:
- **Run → Start Debugging** → pick "Relay: Start Server"
- Open another debug session → "Relay: Start Agent (demo-server)"
- Use **Tasks** (Ctrl+Shift+P → Tasks: Run Task) → "relay: run all tests"
- Open `docs/copilot_prompts.md` for Copilot Chat prompts to explore the codebase

---

## Environment variables cheatsheet

```bash
export RELAY_TOKEN=dev-token          # auth token (required)
export RELAY_URL=ws://localhost:8765  # relay server URL
export RELAY_CLIENT_ID=my-laptop     # your identity
export RELAY_AGENT=demo-server       # default agent for examples
```

Or put them in `~/.relay/.env` and source it:
```bash
source ~/.relay/.env
```

---

## One-command demo

```bash
python examples/quickstart.py
```

This starts server + agent + client all in one script and runs exec + deploy end-to-end.

---

## File layout

```
relay-connect/
├── relay/              ← Python package (the actual code)
│   ├── server.py       ← relay mediator server
│   ├── agent.py        ← server-side agent daemon
│   ├── client.py       ← Python SDK
│   ├── cli.py          ← CLI commands (relay / relay-agent)
│   ├── crypto.py       ← Ed25519 cert issuance + verification
│   ├── protocol.py     ← WebSocket message types
│   └── config.py       ← profile management (~/.relay/config.json)
├── tests/              ← pytest test suite
│   ├── test_crypto.py
│   ├── test_protocol.py
│   ├── test_config.py
│   ├── test_cli.py
│   ├── test_regressions.py
│   └── test_integration.py  ← full server+agent+client tests
├── examples/           ← runnable demos
│   ├── quickstart.py   ← all-in-one demo
│   ├── sdk_usage.py    ← SDK reference examples
│   └── termux_connect.py   ← Termux-specific demo
├── docs/               ← documentation
│   ├── ARCHITECTURE.md
│   └── copilot_prompts.md
├── scripts/            ← shell setup helpers
│   ├── setup_laptop.sh
│   ├── setup_termux.sh
│   ├── dev_start.sh
│   └── run_tests.sh
├── .vscode/            ← VS Code debug + tasks config
├── pyproject.toml      ← packaging + test config
└── QUICKSTART.md       ← this file
```
