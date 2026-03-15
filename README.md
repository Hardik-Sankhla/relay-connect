# relay-connect

**Dead-simple, secure remote connections and deploys. Zero open ports. Zero stored passwords.**

## 30-second setup

### On your laptop (Windows/Mac/Linux):
```bash
python -m pip install git+https://github.com/Hardik-Sankhla/relay-connect.git
relay wizard
```

### On your Android phone (Termux):
```bash
pkg install python
pip install git+https://github.com/Hardik-Sankhla/relay-connect.git
relay wizard
```

That's it. Follow the on-screen instructions. The wizard handles tokens, IPs,
firewall guidance, and QR codes automatically.

No manual `relay add` is required anymore. Commands like `relay ssh my-phone`
auto-register a profile if one doesn't exist.

## How to use it (daily flow)

1. Start relay server on your laptop in one terminal:
```bash
relay server start --host 0.0.0.0 --port 8765
```
2. Start agent on your remote device (for example Termux):
```bash
relay-agent --relay ws://YOUR_LAPTOP_IP:8765 --name my-phone --tags termux
```
3. Use from your laptop (profile is auto-created if missing):
```bash
relay status
relay ssh my-phone
relay exec my-phone "uname -a"
relay deploy ./scripts my-phone
```
4. Diagnose setup issues quickly:
```bash
relay doctor --relay ws://YOUR_LAPTOP_IP:8765
```

---

## The problem it solves

Every deploy today is:

1. Open terminal
2. Remember exact IP / hostname
3. Manage SSH keys across machines
4. Open port 22 to the internet (attack surface)
5. Write `rsync` / `scp` flags you never remember
6. Restart the service manually
7. Repeat for every server

**relay-connect collapses this to one command.**

---

## How it works

```
  Your laptop              Relay (mediator)           Remote server
  ─────────────            ────────────────           ─────────────
  relay deploy  ──TLS──→  broker + cert issuer  ←──  relay-agent
  relay ssh               session logging             (dials outbound)
```

**Security properties:**

| Property | How |
|---|---|
| No open ports on servers | Agents dial **outbound** — nothing to attack |
| No stored passwords | Short-lived Ed25519 session certs (15-min TTL) |
| Leaked creds are useless | Cert expired by the time anyone can use it |
| Full audit trail | Every session logged: who, what server, when |
| Relay never has your keys | It routes; it doesn't store private keys |

---

## Installation

`relay-connect` is currently installed from GitHub source (not from PyPI).

### Option A: Install from GitHub (recommended)

```bash
python -m pip install git+https://github.com/Hardik-Sankhla/relay-connect.git
```

### Option B: Install from local clone (for contributors)

```bash
python -m pip install -e ".[dev]"
```

Requirements: Python 3.10+, `websockets`, `click`, `cryptography`

Termux note: cryptography wheels are available for Android; no Rust toolchain required.

Windows note: if `relay` is not recognized right after install, open a new
PowerShell window. In a project venv, use `.\\.venv\\Scripts\\relay.exe`.

---

## Quick start (local test in 3 terminals)

**Terminal 1 — relay server:**
```bash
relay server start --port 8765
```

**Terminal 2 — agent (simulates a remote server):**
```bash
relay-agent --relay ws://localhost:8765 --name prod-1 --tags dev
```

**Terminal 3 — client (your laptop):**
```bash
relay init
relay status                              # check prod-1 is online
relay exec prod-1 "uname -a"
relay deploy ./myapp prod-1
relay ssh prod-1
```

`relay ssh`, `relay exec`, `relay deploy`, and `relay ping` auto-register a
profile when one does not exist.

---

## Guided setup (Termux)

If you want the simplest path for a non-technical user, run:

```bash
relay wizard
```

This starts an interactive setup and shows a QR code to connect your phone.

---

## Connecting to Termux (Android)

This replaces the manual `ssh -p 8022 u0_a352@192.168.1.37` workflow.

**On Termux (your phone):**
```bash
pkg install python git
python -m pip install git+https://github.com/Hardik-Sankhla/relay-connect.git
relay-agent --relay ws://YOUR_LAPTOP_IP:8765 --name my-phone --tags termux
```

**On your laptop:**
```bash
relay init
relay server start                        # keeps running in one terminal
relay ssh my-phone                        # interactive shell on your phone
relay deploy ./scripts my-phone           # push files to phone
relay exec my-phone "ls ~/projects"
```

**Auto-start on Termux boot (Termux:Boot app required):**
```bash
bash scripts/setup_termux.sh
```

---

## CLI reference

### `relay init`
Initialise config at `~/.relay/config.json`.
```bash
relay init
relay init --relay-url ws://relay.mycompany.com:8765
```

### `relay add <name>`
Register a remote server profile manually (optional; commands can auto-register).
```bash
relay add prod-1
relay add prod-1 --relay-url ws://relay.example.com:8765
relay add prod-1 --deploy-path /var/www/app --post-deploy "systemctl restart myapp"
relay add my-phone --ssh-user u0_a352 --tags termux,android
```

### `relay list`
List all registered server profiles.
```bash
relay list
```

### `relay status`
Check relay connectivity and which agents are online.
```bash
relay status
```

### `relay wizard`
Interactive setup for laptop or Termux with QR/token guidance.
```bash
relay wizard
```

### `relay doctor`
Runs environment and relay connectivity diagnostics.
```bash
relay doctor
relay doctor --relay ws://192.168.1.36:8765
```

### `relay ping <name>`
Measure latency to relay and agent.
```bash
relay ping prod-1
relay ping prod-1 --count 5
```

### `relay ssh <name>`
Interactive shell through the relay.
```bash
relay ssh prod-1
relay ssh prod-1 -c "uptime && df -h"
```

### `relay exec <name> <command>`
Run a command on a remote server.
```bash
relay exec prod-1 "systemctl restart myapp"
relay exec prod-1 "tail -n 100 /var/log/myapp/app.log"
relay exec prod-1 "docker ps"
```

### `relay deploy <path> <name>`
Deploy a file or directory to a remote server.
```bash
relay deploy ./dist prod-1
relay deploy ./dist prod-1 --deploy-path /var/www/html
relay deploy ./dist prod-1 --post-deploy "nginx -s reload"
relay deploy ./app.tar.gz prod-1
```

### `relay server start`
Start the relay mediator server.
```bash
relay server start
relay server start --host 0.0.0.0 --port 8765 --token MY_SECRET_TOKEN
RELAY_TOKEN=mysecret relay server start
```

### `relay agent start` / `relay-agent`
Start the relay agent on a remote machine.
```bash
relay agent start --relay ws://relay.example.com:8765 --name prod-1
relay-agent --relay ws://relay.example.com:8765 --name prod-1 --tags prod,us-east
```

### `relay logs`
Tail the relay audit log.
```bash
relay logs
relay logs --tail 100
relay logs --follow
```

---

## Python SDK

```python
from relay import RelayClient

async with RelayClient("ws://localhost:8765", client_id="dev", token="mytoken") as rc:
    # List online agents
    agents = await rc.list_agents()

    # Run a command
    result = await rc.exec("prod-1", "uptime")
    print(result.stdout)           # stdout string
    print(result.exit_code)        # int
    print(result.ok)               # True if exit_code == 0

    # Deploy files
    result = await rc.deploy(
        local_path="./dist",
        agent_name="prod-1",
        deploy_path="/var/www/app",
        post_deploy="systemctl restart myapp",
        progress=True,
    )
    print(result.path)             # remote path
    print(result.bytes_written)    # bytes transferred
    print(result.elapsed)          # seconds

    # Get session cert (cached, 15-min TTL)
    cert = await rc.get_cert("prod-1")
    print(cert.time_remaining())   # seconds until expiry

    # Ping
    latency = await rc.ping()      # seconds
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `RELAY_TOKEN` | `dev-token` | Auth token for relay server |
| `RELAY_CLIENT_ID` | `dev-client` | Your client identity |
| `RELAY_URL` | `ws://localhost:8765` | Relay server URL |

---

## Configuration

Config lives at `~/.relay/config.json` (chmod 600).

```json
{
  "default_relay_url": "ws://localhost:8765",
  "client_id": "client-abc123",
  "cert_ttl": 900,
  "servers": {
    "prod-1": {
      "name": "prod-1",
      "relay_url": "ws://relay.example.com:8765",
      "deploy_path": "/var/www/app",
      "post_deploy": "systemctl restart myapp",
      "ssh_user": "deploy",
      "tags": ["prod", "us-east"]
    }
  }
}
```

---

## Security model

### Certificate lifecycle
```
Client requests cert → Relay issues Ed25519-signed JWT (15 min TTL)
                      → Client opens tunnel with cert
                      → Agent verifies cert signature + expiry
                      → Tunnel established
                      → Cert expires → tunnel must re-auth
```

### Threat model

| Attack | Mitigation |
|---|---|
| Port scanning / brute force | Servers have zero open ports |
| Stolen session token | Expires in 15 minutes (configurable) |
| MITM on relay | WSS (TLS) in production |
| Compromised relay | Relay never has server private keys |
| Replay attack | Cert contains unique session ID |

### Production hardening checklist

- [ ] Run relay behind TLS (`wss://`) — use nginx or Caddy as a TLS proxy
- [ ] Set `RELAY_TOKEN` to a strong random secret (32+ chars)
- [ ] Store token in environment / secrets manager, not in code
- [ ] Configure `allowed_commands` on agent for restricted servers
- [ ] Reduce `cert_ttl` for highly sensitive servers (e.g. 300s)
- [ ] Review audit logs at `~/.relay/logs/audit.log` regularly
- [ ] Keep relay server and agent updated

---

## Testing

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
bash scripts/run_tests.sh

# Or with pytest directly
pytest tests/ -v

# Run only unit tests (fast, no server needed)
pytest tests/test_crypto.py tests/test_protocol.py tests/test_config.py -v

# Run integration tests (starts real server + agent)
pytest tests/test_integration.py -v

# Coverage
pytest tests/ --cov=relay --cov-report=term-missing
```

---

## VS Code / Copilot development

Open the project in VS Code. The `.vscode/` directory includes:

- **`launch.json`** — debug configurations for server, agent, and client
- **`tasks.json`** — tasks for starting server, agent, running tests
- **`settings.json`** — Python interpreter, test discovery

**Recommended workflow with Copilot:**

1. Open `relay/` — Copilot can suggest completions across all modules
2. Run `Tasks: Run Test Task` to execute the suite
3. Use the debug configurations to step through server ↔ agent ↔ client messages
4. The `examples/` folder is a good Copilot playground for trying the SDK

**Copilot prompt starters included in `docs/copilot_prompts.md`.**

---

## Architecture deep-dive

See `docs/ARCHITECTURE.md` for full design rationale, message flow diagrams, and extension points.

## Beginner guide

See `docs/NOOB_GUIDE.md` for a step-by-step walkthrough with troubleshooting.

---

## Roadmap

- [ ] WSS (TLS) support for relay server
- [ ] OAuth / GitHub SSO authentication
- [ ] Web dashboard for session monitoring
- [ ] Windows agent support
- [ ] `relay tunnel` — local port forwarding through relay
- [ ] Multi-relay federation (multiple relay servers)
- [ ] Rate limiting and per-client ACLs
- [ ] Prometheus metrics endpoint

---

## License

Apache 2.0 — see `LICENSE`.
