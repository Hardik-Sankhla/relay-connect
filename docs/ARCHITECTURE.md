# relay-connect — Architecture

## Overview

relay-connect has three components that communicate over WebSocket:

```
┌─────────────────┐        ┌──────────────────────┐        ┌─────────────────┐
│  relay client   │        │   relay server        │        │  relay agent    │
│  (your laptop)  │──TLS──▶│   (the mediator)     │◀──TLS──│  (remote server)│
│  relay deploy   │        │   cert issuer         │        │  dials OUTBOUND │
│  relay ssh      │        │   session broker      │        │  no open ports  │
│  relay exec     │        │   audit logger        │        │  executes cmds  │
└─────────────────┘        └──────────────────────┘        └─────────────────┘
```

---

## Component responsibilities

### relay server (mediator)

The relay is the heart. It:

1. **Accepts agent connections** — agents dial outbound to the relay. The relay stores a registry of connected agents.
2. **Accepts client connections** — your laptop connects and authenticates with a token.
3. **Issues session certificates** — Ed25519-signed JWTs with a 15-minute TTL. The relay signs; it never stores server private keys.
4. **Routes traffic** — client sends a command; relay forwards it to the named agent; agent's response comes back.
5. **Logs every session** — JSONL audit log with timestamps, client identity, agent name, command.

The relay never stores:
- Server private keys
- Passwords
- Session data after the session ends

### relay agent

The agent runs on each remote server (or Termux phone). It:

1. **Dials outbound** to the relay over a persistent WebSocket with auto-reconnect.
2. **Registers itself** by name with the relay.
3. **Verifies certs** before accepting any session (checks Ed25519 signature + expiry).
4. **Executes commands** in a subprocess, streams back stdout/stderr/exit_code.
5. **Receives file chunks**, reassembles them, writes to disk, and runs a post-deploy hook.
6. **Sends heartbeats** every 30 seconds so the relay knows it's alive.

Zero inbound ports are required. No port 22 needs to be open.

### relay client (SDK + CLI)

The client is your developer-facing interface:

1. **Authenticates** with the relay using a shared token (extensible to OAuth).
2. **Requests session certs** for each server it wants to talk to.
3. **Issues commands** — exec, deploy, tunnel — which are routed through the relay to the agent.
4. **Caches certs** until near-expiry to avoid unnecessary round trips.

---

## Wire protocol

All messages are JSON objects sent over WebSocket. Every message has:
- `type` — one of the enum values in `relay/protocol.py`
- `ts` — Unix timestamp

### Connection handshake

```
Client                    Relay                     Agent
  │                         │                         │
  │  AUTH {client_id, token}│                         │
  │────────────────────────▶│                         │
  │  AUTH_OK                │                         │
  │◀────────────────────────│                         │
  │                         │  AGENT_HELLO {name,tags}│
  │                         │◀────────────────────────│
  │  REQUEST_CERT {agent}   │                         │
  │────────────────────────▶│                         │
  │  CERT_ISSUED {cert}     │                         │
  │◀────────────────────────│                         │
  │  EXEC {agent,cert,cmd}  │                         │
  │────────────────────────▶│  EXEC_CMD {session,cmd} │
  │                         │────────────────────────▶│
  │  EXEC_OUTPUT {stdout…}  │  EXEC_OUTPUT {stdout…}  │
  │◀────────────────────────│◀────────────────────────│
```

### Deploy flow

```
Client                    Relay                     Agent
  │  DEPLOY {chunk 0/N}    │                         │
  │────────────────────────▶│  DEPLOY_CHUNK           │
  │  DEPLOY_ACK             │────────────────────────▶│
  │◀────────────────────────│  DEPLOY_ACK             │
  │  DEPLOY {chunk 1/N}…   │◀────────────────────────│
  │  …                      │  …                      │
  │  DEPLOY {chunk N/N}    │  DEPLOY_CHUNK (last)    │
  │────────────────────────▶│────────────────────────▶│
  │                         │                         │ (extract + run hook)
  │  DEPLOY_DONE            │  DEPLOY_DONE            │
  │◀────────────────────────│◀────────────────────────│
```

---

## Certificate design

Session certs are dataclass objects serialised to JSON (not X.509 — intentionally simpler):

```python
@dataclass
class SessionCert:
    issued_at: float
    expires_at: float      # issued_at + 900 seconds
    agent_name: str        # which server
    client_id: str         # who requested it
    session_id: str        # unique random ID
    signature: str         # Ed25519 sig over JSON payload
```

The relay signs with its Ed25519 private key. Agents verify with the relay's public key. The relay public key is distributed to agents at setup time (or via the cert itself in hosted mode).

**Why not use SSH certificates or X.509?**
- SSH certs require `sshd` on the remote side — we don't want that dependency on Termux
- X.509 is overkill for a 15-minute token
- Our JSON cert is trivially auditable and portable across platforms

---

## Key storage

```
~/.relay/
├── config.json          # client profiles (chmod 600)
├── keys/
│   ├── relay_private.pem   # relay signing key (chmod 600, only on relay server)
│   └── relay_public.pem    # relay verification key (distributed to agents)
└── logs/
    └── audit.log           # JSONL session log
```

---

## Extending relay-connect

### Adding OAuth / SSO

In `server.py`, `_handle_client()` currently checks `token == self.token`. Replace this with:

```python
async def _authenticate_client(self, token: str) -> str:
    # Call your OAuth provider's token introspection endpoint
    # Return client_id on success, raise AuthError on failure
    ...
```

### Adding per-client ACLs

In `server.py`, add an ACL lookup before `_open_tunnel`:

```python
if not self.acl.allows(conn.client_id, agent_name):
    await conn.ws.send(proto.error("FORBIDDEN", "ACL denied"))
    return
```

### Adding WSS (TLS)

Use a TLS reverse proxy (nginx, Caddy) in front of the relay:

```nginx
# nginx example
server {
    listen 443 ssl;
    server_name relay.example.com;
    location / {
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

Or pass `ssl_context` to `websockets.serve()` directly.

### Command whitelisting on agent

For production servers, restrict what commands can be run:

```bash
relay-agent --name prod-1 --allowed-commands "systemctl,docker,nginx"
```

Or in Python:
```python
agent = RelayAgent(
    agent_name="prod-1",
    allowed_commands=["systemctl", "docker", "nginx", "ls", "cat"],
)
```

---

## Comparison with existing tools

| Tool | relay-connect | Tailscale | Cloudflare Tunnel | Teleport |
|---|---|---|---|---|
| Setup complexity | pip install | moderate | moderate | high |
| Hosted option | self-host | yes | yes | yes |
| Deploy built-in | yes | no | no | partial |
| Python SDK | yes | no | no | partial |
| Termux support | yes | partial | no | no |
| Open source | yes | partial | no | yes |
| Cert TTL | configurable | N/A | N/A | configurable |

relay-connect's gap: the **developer UX layer**. Tailscale/Cloudflare solve the networking; relay-connect adds `relay deploy` and `relay ssh` with a one-line install.
