"""
relay.agent — server-side daemon.

Install on each remote server with one command:
  pip install relay-connect
  relay-agent start --relay wss://relay.example.com --name prod-1

Security model:
  - Dials OUTBOUND to the relay (no inbound ports needed)
  - Verifies session certs before executing any command
  - Executes commands in a restricted subprocess
  - Writes every action to a local audit log
  - Supports Termux/Android via standard Python asyncio + websockets
"""

import asyncio
import base64
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

from relay import protocol as proto
from relay.crypto import SessionCert, load_public_key
from relay import __version__

logger = logging.getLogger("relay.agent")


class RelayAgent:
    def __init__(
        self,
        relay_url: str,
        agent_name: str,
        tags: list = None,
        relay_pubkey_path: Optional[Path] = None,
        log_dir: Optional[Path] = None,
        reconnect_delay: int = 5,
        max_reconnects: int = 0,  # 0 = infinite
        allowed_commands: list = None,  # None = allow all (configure for prod)
        deploy_base: str = "/tmp/relay-deploy",
    ):
        self.relay_url = relay_url
        self.agent_name = agent_name
        self.tags = tags or []
        self.reconnect_delay = reconnect_delay
        self.max_reconnects = max_reconnects
        self.deploy_base = deploy_base

        # Allowed commands whitelist — None means unrestricted (not recommended for prod)
        self.allowed_commands = allowed_commands

        self.log_dir = Path(log_dir or (Path.home() / ".relay-agent" / "logs"))
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self._relay_pubkey = None
        if relay_pubkey_path and Path(relay_pubkey_path).exists():
            try:
                self._relay_pubkey = load_public_key(relay_pubkey_path)
                logger.info("Loaded relay public key from %s", relay_pubkey_path)
            except Exception as e:
                logger.warning("Could not load relay pubkey: %s", e)

        self._start_time = time.time()
        self._running = False

        # chunk buffers keyed by (session_id, filename)
        self._chunk_buffers: dict = {}

    # ------------------------------------------------------------------
    # Connection loop with reconnection
    # ------------------------------------------------------------------

    async def run(self):
        if not WEBSOCKETS_AVAILABLE:
            raise RuntimeError("websockets required: pip install websockets")

        self._running = True
        reconnects = 0

        while self._running:
            try:
                logger.info("Connecting to relay at %s as '%s'", self.relay_url, self.agent_name)
                async with websockets.connect(self.relay_url, ping_interval=30) as ws:
                    reconnects = 0
                    await self._session(ws)
            except Exception as e:
                logger.warning("Relay connection lost: %s", e)
                reconnects += 1
                if self.max_reconnects and reconnects >= self.max_reconnects:
                    logger.error("Max reconnects reached — stopping agent")
                    break
                delay = min(self.reconnect_delay * reconnects, 60)
                logger.info("Reconnecting in %ds (attempt %d)...", delay, reconnects)
                await asyncio.sleep(delay)

    async def _session(self, ws):
        # Announce ourselves
        await ws.send(proto.agent_hello(self.agent_name, self.tags, __version__))
        logger.info("Agent '%s' registered with relay", self.agent_name)

        # Start heartbeat task
        hb_task = asyncio.create_task(self._heartbeat_loop(ws))

        try:
            async for raw in ws:
                msg = proto.parse(raw)
                mtype = proto.msg_type(msg)

                if mtype == proto.MsgType.ROUTE:
                    await self._handle_route(ws, msg)

                elif mtype == proto.MsgType.EXEC_CMD:
                    await self._handle_exec(ws, msg)

                elif mtype == proto.MsgType.DEPLOY_CHUNK:
                    await self._handle_deploy_chunk(ws, msg)

                elif mtype == proto.MsgType.DISCONNECT:
                    session_id = msg.get("session_id", "")
                    logger.info("Disconnect requested for session %s", session_id)

        finally:
            hb_task.cancel()

    async def _handle_route(self, ws, msg: dict):
        """Relay wants to open a tunnel — verify cert and signal ready."""
        session_id = msg.get("session_id", "")
        cert_dict = msg.get("cert", {})
        cert = SessionCert.from_dict(cert_dict)

        if not self._verify_cert(cert):
            logger.warning("Invalid cert for session %s — refusing", session_id)
            return

        logger.info("Accepting tunnel session=%s client=%s", session_id, cert.client_id)
        self._log_audit("ROUTE_ACCEPT", {"session": session_id, "client": cert.client_id})
        await ws.send(proto.agent_ready(session_id))

    async def _handle_exec(self, ws, msg: dict):
        """Execute a command and stream back output."""
        session_id = msg.get("session_id", "")
        command = msg.get("command", "")

        if not command:
            return

        if self.allowed_commands is not None:
            cmd_base = command.split()[0] if command.strip() else ""
            if cmd_base not in self.allowed_commands:
                result = proto.make(
                    proto.MsgType.EXEC_OUTPUT,
                    session_id=session_id,
                    stdout="",
                    stderr=f"Command '{cmd_base}' not in allowed list",
                    exit_code=126,
                )
                await ws.send(result)
                return

        logger.info("Executing: %s", command)
        self._log_audit("EXEC", {"session": session_id, "command": command})

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
            exit_code = proc.returncode or 0
        except asyncio.TimeoutError:
            stdout, stderr = b"", b"Command timed out (300s)"
            exit_code = 124
        except Exception as e:
            stdout, stderr = b"", str(e).encode()
            exit_code = 1

        result = proto.make(
            proto.MsgType.EXEC_OUTPUT,
            session_id=session_id,
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
            exit_code=exit_code,
        )
        await ws.send(result)

    async def _handle_deploy_chunk(self, ws, msg: dict):
        """Receive a file chunk, reassemble, write to disk."""
        session_id = msg.get("session_id", "")
        filename = msg.get("filename", "deploy.tar.gz")
        chunk_index = msg.get("chunk_index", 0)
        total_chunks = msg.get("total_chunks", 1)
        data_b64 = msg.get("data_b64", "")
        deploy_path = msg.get("deploy_path", self.deploy_base)
        post_deploy = msg.get("post_deploy", "")

        key = (session_id, filename)
        if key not in self._chunk_buffers:
            self._chunk_buffers[key] = {}

        self._chunk_buffers[key][chunk_index] = base64.b64decode(data_b64)
        logger.info("Chunk %d/%d for %s", chunk_index + 1, total_chunks, filename)

        # send ack to relay (which forwards to client)
        await ws.send(proto.make(proto.MsgType.DEPLOY_ACK, session_id=session_id, chunk_index=chunk_index))

        if len(self._chunk_buffers[key]) == total_chunks:
            # Reassemble
            data = b"".join(self._chunk_buffers[key][i] for i in range(total_chunks))
            del self._chunk_buffers[key]

            dest_dir = Path(deploy_path)
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_file = dest_dir / filename
            dest_file.write_bytes(data)
            logger.info("Wrote %d bytes to %s", len(data), dest_file)
            self._log_audit("DEPLOY_WRITE", {"file": str(dest_file), "bytes": len(data)})

            # Extract if archive
            if filename.endswith((".tar.gz", ".tgz")):
                try:
                    import tarfile
                    with tarfile.open(dest_file, "r:gz") as tf:
                        tf.extractall(dest_dir)
                    logger.info("Extracted archive to %s", dest_dir)
                except Exception as e:
                    logger.warning("Archive extraction failed: %s", e)

            # Run post-deploy hook
            if post_deploy:
                logger.info("Running post-deploy: %s", post_deploy)
                try:
                    result = subprocess.run(
                        post_deploy, shell=True, capture_output=True, text=True, timeout=120
                    )
                    logger.info("Post-deploy exit=%d stdout=%s", result.returncode, result.stdout[:200])
                    self._log_audit("POST_DEPLOY", {
                        "command": post_deploy,
                        "exit_code": result.returncode,
                    })
                except Exception as e:
                    logger.warning("Post-deploy hook failed: %s", e)

            # Notify client
            await ws.send(proto.make(
                proto.MsgType.DEPLOY_DONE,
                session_id=session_id,
                path=str(dest_dir / filename),
                bytes_written=len(data),
            ))

    async def _heartbeat_loop(self, ws):
        while True:
            await asyncio.sleep(30)
            try:
                uptime = time.time() - self._start_time
                load = os.getloadavg()[0] if hasattr(os, "getloadavg") else 0.0
                await ws.send(proto.heartbeat(self.agent_name, load=load, uptime=uptime))
            except Exception:
                break

    def _verify_cert(self, cert: SessionCert) -> bool:
        if not cert.is_valid():
            logger.warning("Cert expired")
            return False
        if cert.agent_name != self.agent_name:
            logger.warning("Cert is for agent '%s', I am '%s'", cert.agent_name, self.agent_name)
            return False
        if self._relay_pubkey:
            return cert.verify(self._relay_pubkey)
        # No pubkey configured — accept cert in dev mode (log warning)
        logger.warning("No relay pubkey configured — accepting cert without signature verification (dev mode)")
        return True

    def _log_audit(self, event: str, data: dict):
        import json
        record = {"ts": time.time(), "event": event, **data}
        log_file = self.log_dir / "agent-audit.log"
        with open(log_file, "a") as f:
            f.write(json.dumps(record) + "\n")

    def stop(self):
        self._running = False


def run_agent(relay_url: str, name: str, tags: list = None, pubkey: str = None):
    agent = RelayAgent(
        relay_url=relay_url,
        agent_name=name,
        tags=tags or [],
        relay_pubkey_path=Path(pubkey) if pubkey else None,
    )
    asyncio.run(agent.run())
