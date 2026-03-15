"""
relay.client — Python SDK for the relay developer client.

Usage (SDK):
    from relay import RelayClient

    async with RelayClient("ws://localhost:8765", client_id="dev", token="mytoken") as rc:
        await rc.connect()
        agents = await rc.list_agents()
        result = await rc.exec("prod-1", "uptime")
        await rc.deploy("./dist", "prod-1", deploy_path="/var/www/app")

Usage (sync wrapper):
    rc = RelayClient.sync("ws://localhost:8765", token="mytoken")
    rc.deploy_sync("./dist", "prod-1")
"""

import asyncio
import base64
import logging
import os
import tarfile
import tempfile
import time
from io import BytesIO
from pathlib import Path
from typing import AsyncIterator, Dict, List, Optional

try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

from relay import protocol as proto
from relay.crypto import SessionCert
from relay.exceptions import (
    AgentNotFoundError,
    AuthError,
    CertExpiredError,
    DeployError,
    TunnelError,
)

logger = logging.getLogger("relay.client")

CHUNK_SIZE = 65536  # 64KB chunks


class ExecResult:
    def __init__(self, stdout: str, stderr: str, exit_code: int):
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.ok = exit_code == 0

    def __repr__(self):
        return f"ExecResult(exit={self.exit_code}, stdout={self.stdout[:80]!r})"


class DeployResult:
    def __init__(self, path: str, bytes_written: int, elapsed: float):
        self.path = path
        self.bytes_written = bytes_written
        self.elapsed = elapsed

    def __repr__(self):
        return f"DeployResult(path={self.path!r}, bytes={self.bytes_written}, elapsed={self.elapsed:.2f}s)"


class RelayClient:
    """
    Async relay client.

    async with RelayClient(url, client_id, token) as rc:
        ...
    """

    def __init__(
        self,
        relay_url: str = "ws://localhost:8765",
        client_id: str = "",
        token: str = "",
        timeout: int = 30,
        chunk_size: int = CHUNK_SIZE,
    ):
        self.relay_url = relay_url
        self.client_id = client_id or os.environ.get("RELAY_CLIENT_ID", "dev-client")
        self.token = token or os.environ.get("RELAY_TOKEN", "dev-token")
        self.timeout = timeout
        self.chunk_size = chunk_size

        self._ws = None
        self._cert_cache: Dict[str, SessionCert] = {}

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *_):
        await self.disconnect()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    async def connect(self):
        if not WEBSOCKETS_AVAILABLE:
            raise RuntimeError("websockets required: pip install websockets")
        self._ws = await websockets.connect(self.relay_url, ping_interval=20)
        await self._authenticate()

    async def disconnect(self):
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def _authenticate(self):
        await self._ws.send(proto.auth(self.client_id, self.token))
        raw = await asyncio.wait_for(self._ws.recv(), timeout=self.timeout)
        msg = proto.parse(raw)
        mtype = proto.msg_type(msg)
        if mtype == proto.MsgType.AUTH_FAIL:
            raise AuthError(msg.get("reason", "Auth failed"))
        if mtype != proto.MsgType.AUTH_OK:
            raise AuthError(f"Unexpected response: {mtype}")
        logger.info("Authenticated as %s", self.client_id)

    # ------------------------------------------------------------------
    # Cert management
    # ------------------------------------------------------------------

    async def get_cert(self, agent_name: str, force: bool = False) -> SessionCert:
        """Get (or reuse cached) session cert for an agent."""
        cached = self._cert_cache.get(agent_name)
        if cached and cached.is_valid() and cached.time_remaining() > 60 and not force:
            return cached

        await self._ws.send(proto.request_cert(agent_name))
        raw = await asyncio.wait_for(self._ws.recv(), timeout=self.timeout)
        msg = proto.parse(raw)
        mtype = proto.msg_type(msg)

        if mtype == proto.MsgType.ERROR:
            raise AgentNotFoundError(msg.get("reason", f"Agent '{agent_name}' not found"))
        if mtype != proto.MsgType.CERT_ISSUED:
            raise TunnelError(f"Expected CERT_ISSUED, got {mtype}")

        cert = SessionCert.from_dict(msg["cert"])
        self._cert_cache[agent_name] = cert
        logger.info("Got cert for %s, expires in %.0fs", agent_name, cert.time_remaining())
        return cert

    # ------------------------------------------------------------------
    # List agents
    # ------------------------------------------------------------------

    async def list_agents(self) -> List[dict]:
        await self._ws.send(proto.list_agents())
        raw = await asyncio.wait_for(self._ws.recv(), timeout=self.timeout)
        msg = proto.parse(raw)
        return msg.get("agents", [])

    # ------------------------------------------------------------------
    # Ping
    # ------------------------------------------------------------------

    async def ping(self) -> float:
        t = time.time()
        await self._ws.send(proto.ping())
        raw = await asyncio.wait_for(self._ws.recv(), timeout=self.timeout)
        return time.time() - t

    # ------------------------------------------------------------------
    # Exec
    # ------------------------------------------------------------------

    async def exec(self, agent_name: str, command: str) -> ExecResult:
        """Run a shell command on the named agent, return output."""
        cert = await self.get_cert(agent_name)
        msg = proto.make(
            proto.MsgType.EXEC,
            agent_name=agent_name,
            cert=cert.to_dict(),
            command=command,
        )
        await self._ws.send(msg)

        # Wait for output (may receive acks / other messages first)
        while True:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=self.timeout)
            reply = proto.parse(raw)
            mtype = proto.msg_type(reply)
            if mtype == proto.MsgType.EXEC_OUTPUT:
                return ExecResult(
                    stdout=reply.get("stdout", ""),
                    stderr=reply.get("stderr", ""),
                    exit_code=reply.get("exit_code", 0),
                )
            elif mtype == proto.MsgType.ERROR:
                raise TunnelError(reply.get("reason", "exec error"))

    # ------------------------------------------------------------------
    # Deploy (file / directory → remote)
    # ------------------------------------------------------------------

    async def deploy(
        self,
        local_path: str,
        agent_name: str,
        deploy_path: str = "/tmp/relay-deploy",
        post_deploy: str = "",
        progress: bool = True,
    ) -> DeployResult:
        """
        Send local_path (file or directory) to agent.

        The path is tarred + gzipped, sent in chunks, extracted on the
        remote side, and post_deploy hook runs if provided.
        """
        start = time.time()
        local = Path(local_path)
        if not local.exists():
            raise DeployError(f"Local path does not exist: {local}")

        # Pack into tar.gz in memory
        buf = BytesIO()
        archive_name = local.name + ".tar.gz"
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            if local.is_dir():
                tf.add(local, arcname=local.name)
            else:
                tf.add(local, arcname=local.name)
        data = buf.getvalue()
        total_size = len(data)

        cert = await self.get_cert(agent_name)
        total_chunks = (total_size + self.chunk_size - 1) // self.chunk_size

        logger.info(
            "Deploying %s → %s (%d bytes, %d chunks)",
            local_path, agent_name, total_size, total_chunks,
        )

        bytes_acked = 0
        for i in range(total_chunks):
            chunk = data[i * self.chunk_size: (i + 1) * self.chunk_size]
            chunk_b64 = base64.b64encode(chunk).decode()

            msg = proto.make(
                proto.MsgType.DEPLOY,
                agent_name=agent_name,
                cert=cert.to_dict(),
                filename=archive_name,
                chunk_index=i,
                total_chunks=total_chunks,
                data_b64=chunk_b64,
                deploy_path=deploy_path,
                post_deploy=post_deploy if i == total_chunks - 1 else "",
            )
            await self._ws.send(msg)

            # Wait for ACK
            ack_received = False
            while not ack_received:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=60)
                reply = proto.parse(raw)
                mtype = proto.msg_type(reply)
                if mtype == proto.MsgType.DEPLOY_ACK:
                    ack_received = True
                    bytes_acked += len(chunk)
                    if progress:
                        pct = int(100 * bytes_acked / total_size)
                        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
                        print(f"\r  Uploading [{bar}] {pct}%  {bytes_acked}/{total_size}B", end="", flush=True)
                elif mtype == proto.MsgType.DEPLOY_DONE:
                    if progress:
                        print()
                    elapsed = time.time() - start
                    return DeployResult(
                        path=reply.get("path", deploy_path),
                        bytes_written=reply.get("bytes_written", total_size),
                        elapsed=elapsed,
                    )
                elif mtype == proto.MsgType.ERROR:
                    raise DeployError(reply.get("reason", "deploy error"))

        # Wait for DEPLOY_DONE
        while True:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=120)
            reply = proto.parse(raw)
            mtype = proto.msg_type(reply)
            if mtype == proto.MsgType.DEPLOY_DONE:
                if progress:
                    print()
                elapsed = time.time() - start
                return DeployResult(
                    path=reply.get("path", deploy_path),
                    bytes_written=reply.get("bytes_written", total_size),
                    elapsed=elapsed,
                )
            elif mtype == proto.MsgType.ERROR:
                raise DeployError(reply.get("reason", "deploy error"))

    # ------------------------------------------------------------------
    # Open tunnel (for SSH forwarding via paramiko)
    # ------------------------------------------------------------------

    async def open_tunnel(self, agent_name: str) -> str:
        """Request a tunnel to agent. Returns session_id on success."""
        cert = await self.get_cert(agent_name)
        await self._ws.send(proto.open_tunnel(agent_name, cert.to_dict()))

        while True:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=self.timeout)
            msg = proto.parse(raw)
            mtype = proto.msg_type(msg)
            if mtype == proto.MsgType.TUNNEL_READY:
                return msg.get("session_id", "")
            elif mtype == proto.MsgType.TUNNEL_FAIL:
                raise TunnelError(msg.get("reason", "tunnel failed"))
            elif mtype == proto.MsgType.ERROR:
                raise TunnelError(msg.get("reason", "error"))

    # ------------------------------------------------------------------
    # Sync convenience wrapper (for scripts)
    # ------------------------------------------------------------------

    def run_sync(self, coro):
        """Run a coroutine synchronously. Useful in scripts."""
        return asyncio.run(coro)
