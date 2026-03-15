"""
relay.server — the relay mediator server.

What it does:
  1. Listens for agent connections (outbound from servers — no open ports on servers)
  2. Listens for client connections (your laptop / CI)
  3. Authenticates clients (token-based; extensible to OAuth/SSO)
  4. Issues short-lived session certificates (15-min TTL)
  5. Routes client ↔ agent traffic through the broker
  6. Logs every session with timestamp, client, agent, actions

Run:
  python -m relay.server --host 0.0.0.0 --port 8765
  relay server start --port 8765

Security properties:
  - Servers never expose port 22 to the internet
  - The relay never stores server private keys
  - All certs expire; leaked creds are useless after TTL
  - Full audit log of every connection
"""

import asyncio
import base64
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Set

try:
    import websockets
    from websockets.server import WebSocketServerProtocol
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

from relay import protocol as proto
from relay.crypto import SessionCert, generate_keypair, load_private_key
from relay.config import DEFAULT_DEPLOY_PATH
from relay.exceptions import AuthError

logger = logging.getLogger("relay.server")


# ---------------------------------------------------------------------------
# Session / Agent tracking
# ---------------------------------------------------------------------------

@dataclass
class AgentConnection:
    name: str
    ws: object  # WebSocketServerProtocol
    tags: list
    version: str
    connected_at: float = field(default_factory=time.time)
    session_ids: Set[str] = field(default_factory=set)

    def info(self) -> dict:
        return {
            "name": self.name,
            "tags": self.tags,
            "version": self.version,
            "connected_at": self.connected_at,
            "sessions": list(self.session_ids),
        }


@dataclass
class ClientConnection:
    client_id: str
    ws: object
    authenticated: bool = False
    connected_at: float = field(default_factory=time.time)


@dataclass
class Session:
    session_id: str
    client_id: str
    agent_name: str
    cert: SessionCert
    opened_at: float = field(default_factory=time.time)
    closed_at: Optional[float] = None


# ---------------------------------------------------------------------------
# Relay server core
# ---------------------------------------------------------------------------

class RelayServer:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        token: str = "",
        keys_dir: Optional[Path] = None,
        log_dir: Optional[Path] = None,
        cert_ttl: int = 900,
        require_auth: bool = True,
    ):
        self.host = host
        self.port = port
        self.token = token or os.environ.get("RELAY_TOKEN", "dev-token")
        self.cert_ttl = cert_ttl
        self.require_auth = require_auth

        self.keys_dir = Path(keys_dir or (Path.home() / ".relay" / "keys"))
        self.log_dir = Path(log_dir or (Path.home() / ".relay" / "logs"))
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self._agents: Dict[str, AgentConnection] = {}
        self._clients: Dict[str, ClientConnection] = {}
        self._sessions: Dict[str, Session] = {}

        # pending maps for routing
        self._tunnel_pending: Dict[str, object] = {}
        self._exec_pending: Dict[str, object] = {}
        self._deploy_pending: Dict[str, object] = {}
        self._shell_clients: Dict[str, object] = {}
        self._shell_agents: Dict[str, object] = {}

        self._signing_key = None
        self._public_key = None
        self._load_or_create_keys()

        # Audit log
        self._audit_log = open(self.log_dir / "audit.log", "a", buffering=1)
        self._audit("SERVER_START", {"host": host, "port": port})

    def _load_or_create_keys(self):
        priv_path = self.keys_dir / "relay_private.pem"
        pub_path = self.keys_dir / "relay_public.pem"
        try:
            from relay.crypto import load_private_key, load_public_key, CRYPTO_AVAILABLE
            if CRYPTO_AVAILABLE and priv_path.exists():
                self._signing_key = load_private_key(priv_path)
                self._public_key = load_public_key(pub_path)
                logger.info("Loaded relay keypair from %s", self.keys_dir)
            elif CRYPTO_AVAILABLE:
                self._signing_key, self._public_key = generate_keypair(
                    save_dir=self.keys_dir, name="relay"
                )
                logger.info("Generated new relay keypair at %s", self.keys_dir)
            else:
                logger.warning("cryptography not installed — using test-only HMAC certs")
                self._signing_key = b"test-only-hmac-key"
                self._public_key = None
        except Exception as e:
            logger.error("Key init failed: %s", e)
            self._signing_key = b"test-only-hmac-key"
            self._public_key = None

    def _audit(self, event: str, data: dict):
        record = {
            "ts": time.time(),
            "event": event,
            **data,
        }
        self._audit_log.write(json.dumps(record) + "\n")

    # ------------------------------------------------------------------
    # Main handler — dispatches by role (agent vs client)
    # ------------------------------------------------------------------

    async def handler(self, ws, path="/"):
        client_addr = ws.remote_address
        logger.info("New connection from %s path=%s", client_addr, path)

        # First message determines role
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=10)
            msg = proto.parse(raw)
            mtype = proto.msg_type(msg)
        except asyncio.TimeoutError:
            await ws.close(1008, "no hello received")
            return
        except Exception as e:
            logger.warning("Bad first message from %s: %s", client_addr, e)
            return

        if mtype == proto.MsgType.AGENT_HELLO:
            await self._handle_agent(ws, msg)
        elif mtype == proto.MsgType.AUTH:
            await self._handle_client(ws, msg)
        else:
            await ws.send(proto.error("BAD_HELLO", f"Expected AUTH or AGENT_HELLO, got {mtype}"))

    # ------------------------------------------------------------------
    # Agent connection lifecycle
    # ------------------------------------------------------------------

    async def _handle_agent(self, ws, hello_msg: dict):
        agent_name = hello_msg.get("agent_name", "")
        if not agent_name:
            await ws.send(proto.error("BAD_AGENT", "agent_name required"))
            return

        agent = AgentConnection(
            name=agent_name,
            ws=ws,
            tags=hello_msg.get("tags", []),
            version=hello_msg.get("version", "unknown"),
        )
        self._agents[agent_name] = agent
        logger.info("Agent '%s' connected (v%s tags=%s)", agent_name, agent.version, agent.tags)
        self._audit("AGENT_CONNECT", {"agent": agent_name, "tags": agent.tags})

        try:
            async for raw in ws:
                msg = proto.parse(raw)
                mtype = proto.msg_type(msg)

                if mtype == proto.MsgType.HEARTBEAT:
                    # Just acknowledge, update bookkeeping
                    pass

                elif mtype == proto.MsgType.AGENT_READY:
                    session_id = msg.get("session_id", "")
                    if session_id in self._tunnel_pending:
                        client_ws = self._tunnel_pending.pop(session_id)
                        agent.session_ids.add(session_id)
                        await client_ws.send(proto.tunnel_ready(session_id, agent_name))
                        logger.info("Tunnel ready: session=%s agent=%s", session_id, agent_name)
                        self._audit("TUNNEL_OPEN", {"session_id": session_id, "agent": agent_name})

                elif mtype == proto.MsgType.EXEC_OUTPUT:
                    # Forward execution output back to any waiting client
                    session_id = msg.get("session_id", "")
                    client_ws = self._exec_pending.pop(session_id, None)
                    if client_ws:
                        await self._forward_raw(client_ws, raw)

                elif mtype == proto.MsgType.DEPLOY_ACK:
                    session_id = msg.get("session_id", "")
                    client_ws = self._deploy_pending.get(session_id)
                    if client_ws:
                        await self._forward_raw(client_ws, raw)

                elif mtype == proto.MsgType.DEPLOY_DONE:
                    session_id = msg.get("session_id", "")
                    client_ws = self._deploy_pending.pop(session_id, None)
                    if client_ws:
                        await self._forward_raw(client_ws, raw)

                elif mtype == proto.MsgType.SHELL_READY:
                    session_id = msg.get("session_id", "")
                    client_ws = self._shell_clients.get(session_id)
                    if client_ws:
                        await self._forward_raw(client_ws, raw)

                elif mtype == proto.MsgType.SHELL_DATA:
                    session_id = msg.get("session_id", "")
                    client_ws = self._shell_clients.get(session_id)
                    if client_ws:
                        await self._forward_raw(client_ws, raw)

                elif mtype == proto.MsgType.SHELL_EXIT:
                    session_id = msg.get("session_id", "")
                    client_ws = self._shell_clients.pop(session_id, None)
                    self._shell_agents.pop(session_id, None)
                    if client_ws:
                        await self._forward_raw(client_ws, raw)

        except Exception as e:
            logger.info("Agent '%s' disconnected: %s", agent_name, e)
        finally:
            self._agents.pop(agent_name, None)
            self._audit("AGENT_DISCONNECT", {"agent": agent_name})

    # ------------------------------------------------------------------
    # Client connection lifecycle
    # ------------------------------------------------------------------

    async def _handle_client(self, ws, auth_msg: dict):
        client_id = auth_msg.get("client_id", "")
        token = auth_msg.get("token", "")

        if self.require_auth and token != self.token:
            prefix = (token or "")[:8]
            await ws.send(proto.auth_fail(
                "Wrong token. Make sure RELAY_TOKEN matches on both machines. "
                f"Your token: {prefix}..."
            ))
            logger.warning("Auth failed for client_id=%s", client_id)
            self._audit("AUTH_FAIL", {"client_id": client_id})
            return

        if not client_id:
            client_id = f"anon-{int(time.time())}"

        conn = ClientConnection(client_id=client_id, ws=ws, authenticated=True)
        self._clients[client_id] = conn
        await ws.send(proto.auth_ok(client_id))
        logger.info("Client '%s' authenticated", client_id)
        self._audit("AUTH_OK", {"client_id": client_id, "addr": str(ws.remote_address)})

        try:
            async for raw in ws:
                await self._dispatch_client_msg(conn, proto.parse(raw), raw)
        except Exception as e:
            logger.info("Client '%s' disconnected: %s", client_id, e)
        finally:
            self._clients.pop(client_id, None)

    async def _dispatch_client_msg(self, conn: ClientConnection, msg: dict, raw: str):
        mtype = proto.msg_type(msg)

        if mtype == proto.MsgType.PING:
            await conn.ws.send(proto.pong())

        elif mtype == proto.MsgType.LIST_AGENTS:
            agents = [a.info() for a in self._agents.values()]
            await conn.ws.send(proto.agent_list(agents))

        elif mtype == proto.MsgType.REQUEST_CERT:
            agent_name = msg.get("agent_name", "")
            if agent_name not in self._agents:
                await conn.ws.send(proto.error("AGENT_NOT_FOUND", f"Agent '{agent_name}' not connected"))
                return
            cert = SessionCert.issue(
                agent_name=agent_name,
                client_id=conn.client_id,
                signing_key=self._signing_key,
                ttl=self.cert_ttl,
            )
            await conn.ws.send(proto.cert_issued(cert.to_dict()))
            self._audit("CERT_ISSUED", {"client": conn.client_id, "agent": agent_name, "session": cert.session_id})

        elif mtype == proto.MsgType.OPEN_TUNNEL:
            agent_name = msg.get("agent_name", "")
            cert_dict = msg.get("cert", {})
            await self._open_tunnel(conn, agent_name, cert_dict)

        elif mtype == proto.MsgType.EXEC:
            agent_name = msg.get("agent_name", "")
            command = msg.get("command", "")
            cert_dict = msg.get("cert", {})
            await self._exec_on_agent(conn, agent_name, cert_dict, command)

        elif mtype == proto.MsgType.DEPLOY:
            agent_name = msg.get("agent_name", "")
            cert_dict = msg.get("cert", {})
            await self._forward_deploy(conn, agent_name, cert_dict, msg)

        elif mtype == proto.MsgType.SHELL_OPEN:
            agent_name = msg.get("agent_name", "")
            cert_dict = msg.get("cert", {})
            await self._open_shell(conn, agent_name, cert_dict, msg)

        elif mtype == proto.MsgType.SHELL_DATA:
            session_id = msg.get("session_id", "")
            agent_ws = self._shell_agents.get(session_id)
            if agent_ws:
                await self._forward_raw(agent_ws, raw)

        elif mtype == proto.MsgType.SHELL_RESIZE:
            session_id = msg.get("session_id", "")
            agent_ws = self._shell_agents.get(session_id)
            if agent_ws:
                await self._forward_raw(agent_ws, raw)

    async def _open_tunnel(self, conn: ClientConnection, agent_name: str, cert_dict: dict):
        if agent_name not in self._agents:
            await conn.ws.send(proto.tunnel_fail(f"Agent '{agent_name}' not connected"))
            return

        cert = SessionCert.from_dict(cert_dict)
        if not cert.is_valid():
            await conn.ws.send(proto.tunnel_fail("Certificate expired"))
            return

        session_id = cert.session_id
        agent = self._agents[agent_name]

        # register pending tunnel (agent will call AGENT_READY to complete)
        self._tunnel_pending[session_id] = conn.ws
        self._sessions[session_id] = Session(
            session_id=session_id,
            client_id=conn.client_id,
            agent_name=agent_name,
            cert=cert,
        )

        # tell agent to get ready
        await agent.ws.send(proto.route(session_id, conn.client_id, cert_dict))
        logger.info("Routing session=%s to agent=%s", session_id, agent_name)

    async def _exec_on_agent(self, conn: ClientConnection, agent_name: str, cert_dict: dict, command: str):
        if agent_name not in self._agents:
            await conn.ws.send(proto.error("AGENT_NOT_FOUND", f"Agent '{agent_name}' not connected"))
            return
        cert = SessionCert.from_dict(cert_dict)
        if not cert.is_valid():
            await conn.ws.send(proto.error("CERT_EXPIRED", "Certificate expired"))
            return

        agent = self._agents[agent_name]
        session_id = cert.session_id

        # store client ws for reply routing
        self._exec_pending[session_id] = conn.ws

        msg = proto.make(proto.MsgType.EXEC_CMD, session_id=session_id, command=command)
        await agent.ws.send(msg)
        self._audit("EXEC", {"client": conn.client_id, "agent": agent_name, "command": command})

    async def _forward_deploy(self, conn: ClientConnection, agent_name: str, cert_dict: dict, msg: dict):
        if agent_name not in self._agents:
            await conn.ws.send(proto.error("AGENT_NOT_FOUND", f"Agent '{agent_name}' not connected"))
            return
        cert = SessionCert.from_dict(cert_dict)
        if not cert.is_valid():
            await conn.ws.send(proto.error("CERT_EXPIRED", "Certificate expired"))
            return

        agent = self._agents[agent_name]
        # Forward the deploy chunk directly to agent
        fwd = proto.make(
            proto.MsgType.DEPLOY_CHUNK,
            session_id=cert.session_id,
            filename=msg.get("filename", ""),
            chunk_index=msg.get("chunk_index", 0),
            total_chunks=msg.get("total_chunks", 1),
            data_b64=msg.get("data_b64", ""),
            deploy_path=msg.get("deploy_path", DEFAULT_DEPLOY_PATH),
            post_deploy=msg.get("post_deploy", ""),
        )
        await agent.ws.send(fwd)
        # Track deploy sessions separately for ACK/DONE routing
        self._deploy_pending[cert.session_id] = conn.ws

        if msg.get("chunk_index", 0) == msg.get("total_chunks", 1) - 1:
            self._audit("DEPLOY", {
                "client": conn.client_id,
                "agent": agent_name,
                "file": msg.get("filename", ""),
                "chunks": msg.get("total_chunks", 1),
            })

    async def _open_shell(self, conn: ClientConnection, agent_name: str, cert_dict: dict, msg: dict):
        if agent_name not in self._agents:
            await conn.ws.send(proto.error("AGENT_NOT_FOUND", f"Agent '{agent_name}' not connected"))
            return
        cert = SessionCert.from_dict(cert_dict)
        if not cert.is_valid():
            await conn.ws.send(proto.error("CERT_EXPIRED", "Certificate expired"))
            return

        session_id = cert.session_id
        agent = self._agents[agent_name]

        self._shell_clients[session_id] = conn.ws
        self._shell_agents[session_id] = agent.ws

        await agent.ws.send(proto.make(
            proto.MsgType.SHELL_OPEN,
            session_id=session_id,
            rows=msg.get("rows", 24),
            cols=msg.get("cols", 80),
            term=msg.get("term", "xterm-256color"),
        ))
        self._audit("SHELL_OPEN", {"client": conn.client_id, "agent": agent_name, "session": session_id})

    async def _forward_raw(self, client_ws, raw: str):
        try:
            await client_ws.send(raw)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Start / stop
    # ------------------------------------------------------------------

    async def start(self):
        if not WEBSOCKETS_AVAILABLE:
            raise RuntimeError("websockets package required. Run: pip install websockets")
        logger.info("Relay server starting on ws://%s:%d", self.host, self.port)
        print(f"\n  Relay server running on ws://{self.host}:{self.port}")
        print(f"  Token: {self.token}")
        print(f"  Keys:  {self.keys_dir}")
        print(f"  Logs:  {self.log_dir}\n")
        async with websockets.serve(self.handler, self.host, self.port):
            await asyncio.Future()  # run forever

    def run(self):
        asyncio.run(self.start())


def run_server(host="0.0.0.0", port=8765, token="", require_auth=True):
    server = RelayServer(host=host, port=port, token=token, require_auth=require_auth)
    server.run()


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="relay mediator server")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--token", default="")
    p.add_argument("--no-auth", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    run_server(args.host, args.port, args.token, require_auth=not args.no_auth)
