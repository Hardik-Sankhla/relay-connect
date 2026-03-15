# Troubleshooting relay-connect

---

## "relay: command not found" after pip install

```bash
# Make sure pip's script dir is in your PATH
export PATH="$HOME/.local/bin:$PATH"

# Or install in a venv
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
relay --version
```

---

## "No module named websockets"

```bash
pip install websockets cryptography click
```

On Termux:
```bash
pkg install python
pip install relay-connect
```

---

## "ModuleNotFoundError: No module named 'relay'"

You're running from outside the project dir. Either:
```bash
pip install -e .           # install in editable mode
# or
cd relay-connect && python -m relay --version
```

---

## Agent connects but doesn't appear in `relay list`

1. Check agent terminal for errors — it should print `"Agent 'X' registered with relay"`
2. Make sure `--name` on the agent matches what you used in `relay add`
3. Try `relay status` — it queries the relay directly
4. Check the relay audit log: `relay logs`

---

## "AUTH_FAIL: Invalid token"

The token on the client must match the token the server was started with.

```bash
# Server:
RELAY_TOKEN=mysecret relay server start

# Client:
RELAY_TOKEN=mysecret relay exec prod-1 "uptime"
```

Set it permanently:
```bash
echo "export RELAY_TOKEN=mysecret" >> ~/.bashrc
```

---

## "AgentNotFoundError: Agent 'prod-1' not connected"

The agent is offline or hasn't registered yet. Check:
1. Is `relay-agent` running on the remote machine?
2. Can the remote machine reach your relay server? Try `curl http://RELAY_IP:8765` — should get a WebSocket upgrade error (not connection refused)
3. Check firewall: port 8765 must be open inbound on the relay server

---

## "Certificate expired" errors

The default cert TTL is 15 minutes. If your clocks are out of sync between machines, certs may appear expired immediately.

```bash
# Sync your clock (Linux)
timedatectl set-ntp true

# Check clock skew
date && ssh user@server "date"
```

Or increase TTL in `~/.relay/config.json`:
```json
{ "cert_ttl": 3600 }
```

---

## Termux: "Connection refused" when agent tries to reach relay

The relay runs on your laptop. Your phone and laptop must be on the same WiFi network (or the laptop must have a public IP).

```bash
# Find your laptop's local IP
ip route get 1 | awk '{print $7}'   # Linux
ipconfig getifaddr en0               # macOS
```

Then on Termux:
```bash
relay-agent --relay ws://192.168.1.42:8765 --name my-phone
```

---

## Termux: agent keeps disconnecting

Termux background processes get killed by Android's battery optimisation.

Fix:
1. Long-press the Termux notification → "Wakelock" → acquire wakelock
2. Or: Settings → Battery → Termux → Unrestricted
3. Or use Termux:Boot to auto-start: `bash scripts/setup_termux.sh`

---

## Integration tests failing with "asyncio fixture not found"

Install pytest-asyncio:
```bash
pip install pytest-asyncio
```

Make sure `pyproject.toml` has:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

---

## "websockets.exceptions.ConnectionClosedError" in tests

This is normal if a test ends while the server is still sending. The integration tests handle cleanup in fixtures. If it persists, increase the sleep time in the test fixture:

```python
await asyncio.sleep(0.5)   # increase to 1.0
```

---

## Deploy succeeds but files not found on remote

The deploy puts files in `--deploy-path` (default `/tmp/relay-deploy`).
Check:
```bash
relay exec prod-1 "ls /tmp/relay-deploy/"
```

Archives are extracted in place. If you deployed `./dist`, look for `/tmp/relay-deploy/dist/`.

---

## How to reset everything

```bash
rm -rf ~/.relay/          # removes config, keys, logs
relay init                # fresh start
```

---

## Enabling debug logging

```bash
relay --debug exec prod-1 "uptime"
relay --debug server start
relay-agent --debug --relay ws://... --name x
```

Or set log level in config:
```json
{ "log_level": "DEBUG" }
```
