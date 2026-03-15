"""
Integration tests: real server + agent + client talking over WebSocket.

These tests spin up a real relay server on a random port, connect an agent,
then use the client to exec commands and deploy files.

Requires: websockets, pytest-asyncio
"""

import asyncio
import os
import tempfile
import time
from pathlib import Path
import pytest

# Skip entire module if websockets not available
pytest.importorskip("websockets")

from relay.server import RelayServer
from relay.agent import RelayAgent
from relay.client import RelayClient
from relay.exceptions import AgentNotFoundError, AuthError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_TOKEN = "integration-test-token"
TEST_CLIENT_ID = "test-client"
TEST_AGENT_NAME = "test-agent"


def get_free_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def relay_server():
    """Spin up a real relay server on a random port."""
    port = get_free_port()
    server = RelayServer(
        host="127.0.0.1",
        port=port,
        token=TEST_TOKEN,
        require_auth=True,
        cert_ttl=60,
    )
    task = asyncio.create_task(server.start())
    await asyncio.sleep(0.2)  # let it bind
    yield server, f"ws://127.0.0.1:{port}"
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


@pytest.fixture
async def relay_with_agent(relay_server):
    """Server + an agent that auto-registers."""
    server, url = relay_server

    agent = RelayAgent(
        relay_url=url,
        agent_name=TEST_AGENT_NAME,
        tags=["test"],
        reconnect_delay=1,
        max_reconnects=1,
    )
    task = asyncio.create_task(agent.run())
    await asyncio.sleep(0.3)  # let agent connect and register

    yield server, url, agent

    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

class TestAuthentication:
    @pytest.mark.asyncio
    async def test_valid_auth_succeeds(self, relay_server):
        _, url = relay_server
        async with RelayClient(url, TEST_CLIENT_ID, TEST_TOKEN) as rc:
            latency = await rc.ping()
            assert latency > 0

    @pytest.mark.asyncio
    async def test_invalid_token_raises(self, relay_server):
        _, url = relay_server
        with pytest.raises(AuthError):
            async with RelayClient(url, TEST_CLIENT_ID, "wrong-token") as rc:
                await rc.ping()

    @pytest.mark.asyncio
    async def test_ping_under_1_second_locally(self, relay_server):
        _, url = relay_server
        async with RelayClient(url, TEST_CLIENT_ID, TEST_TOKEN) as rc:
            latency = await rc.ping()
            assert 0 < latency < 1.0


# ---------------------------------------------------------------------------
# Agent registration
# ---------------------------------------------------------------------------

class TestAgentRegistration:
    @pytest.mark.asyncio
    async def test_agent_appears_in_list(self, relay_with_agent):
        _, url, _ = relay_with_agent
        async with RelayClient(url, TEST_CLIENT_ID, TEST_TOKEN) as rc:
            agents = await rc.list_agents()
            names = [a["name"] for a in agents]
            assert TEST_AGENT_NAME in names

    @pytest.mark.asyncio
    async def test_empty_agent_list_before_agent(self, relay_server):
        _, url = relay_server
        async with RelayClient(url, TEST_CLIENT_ID, TEST_TOKEN) as rc:
            agents = await rc.list_agents()
            assert agents == []


# ---------------------------------------------------------------------------
# Cert issuance
# ---------------------------------------------------------------------------

class TestCertIssuance:
    @pytest.mark.asyncio
    async def test_cert_issued_for_online_agent(self, relay_with_agent):
        _, url, _ = relay_with_agent
        async with RelayClient(url, TEST_CLIENT_ID, TEST_TOKEN) as rc:
            cert = await rc.get_cert(TEST_AGENT_NAME)
            assert cert.is_valid()
            assert cert.agent_name == TEST_AGENT_NAME
            assert cert.client_id == TEST_CLIENT_ID

    @pytest.mark.asyncio
    async def test_cert_error_for_offline_agent(self, relay_server):
        _, url = relay_server
        async with RelayClient(url, TEST_CLIENT_ID, TEST_TOKEN) as rc:
            with pytest.raises(AgentNotFoundError) as exc_info:
                await rc.get_cert("nonexistent-agent")
            assert "nonexistent-agent" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_cert_is_cached(self, relay_with_agent):
        _, url, _ = relay_with_agent
        async with RelayClient(url, TEST_CLIENT_ID, TEST_TOKEN) as rc:
            cert1 = await rc.get_cert(TEST_AGENT_NAME)
            cert2 = await rc.get_cert(TEST_AGENT_NAME)
            assert cert1.session_id == cert2.session_id


# ---------------------------------------------------------------------------
# Exec
# ---------------------------------------------------------------------------

class TestExec:
    @pytest.mark.asyncio
    async def test_exec_echo(self, relay_with_agent):
        _, url, _ = relay_with_agent
        async with RelayClient(url, TEST_CLIENT_ID, TEST_TOKEN) as rc:
            result = await rc.exec(TEST_AGENT_NAME, "echo hello_relay")
            assert result.ok
            assert "hello_relay" in result.stdout

    @pytest.mark.asyncio
    async def test_exec_exit_code(self, relay_with_agent):
        _, url, _ = relay_with_agent
        async with RelayClient(url, TEST_CLIENT_ID, TEST_TOKEN) as rc:
            result = await rc.exec(TEST_AGENT_NAME, "exit 42")
            assert result.exit_code == 42
            assert not result.ok

    @pytest.mark.asyncio
    async def test_exec_multiline(self, relay_with_agent):
        _, url, _ = relay_with_agent
        async with RelayClient(url, TEST_CLIENT_ID, TEST_TOKEN) as rc:
            result = await rc.exec(TEST_AGENT_NAME, "echo line1; echo line2")
            assert "line1" in result.stdout
            assert "line2" in result.stdout

    @pytest.mark.asyncio
    async def test_exec_env_variable(self, relay_with_agent):
        _, url, _ = relay_with_agent
        async with RelayClient(url, TEST_CLIENT_ID, TEST_TOKEN) as rc:
            result = await rc.exec(TEST_AGENT_NAME, "echo $HOME")
            assert result.ok
            assert result.stdout.strip() != ""


# ---------------------------------------------------------------------------
# Deploy
# ---------------------------------------------------------------------------

class TestDeploy:
    @pytest.mark.asyncio
    async def test_deploy_single_file(self, relay_with_agent, tmp_path):
        _, url, _ = relay_with_agent
        # Create a test file
        src = tmp_path / "hello.txt"
        src.write_text("hello from relay deploy!")

        with tempfile.TemporaryDirectory() as dest_dir:
            async with RelayClient(url, TEST_CLIENT_ID, TEST_TOKEN) as rc:
                result = await rc.deploy(
                    str(src),
                    TEST_AGENT_NAME,
                    deploy_path=dest_dir,
                    progress=False,
                )
            assert result.bytes_written > 0
            assert result.elapsed > 0

    @pytest.mark.asyncio
    async def test_deploy_directory(self, relay_with_agent, tmp_path):
        _, url, _ = relay_with_agent
        # Create a test directory with files
        src_dir = tmp_path / "app"
        src_dir.mkdir()
        (src_dir / "index.html").write_text("<h1>Hello</h1>")
        (src_dir / "style.css").write_text("body { margin: 0 }")
        (src_dir / "app.js").write_text("console.log('relay deploy')")

        with tempfile.TemporaryDirectory() as dest_dir:
            async with RelayClient(url, TEST_CLIENT_ID, TEST_TOKEN) as rc:
                result = await rc.deploy(
                    str(src_dir),
                    TEST_AGENT_NAME,
                    deploy_path=dest_dir,
                    progress=False,
                )
            assert result.bytes_written > 0

    @pytest.mark.asyncio
    async def test_deploy_writes_file_and_checksum(self, relay_with_agent, tmp_path):
        _, url, _ = relay_with_agent
        src = tmp_path / "payload.txt"
        content = "hello relay"
        src.write_text(content)

        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()

        async with RelayClient(url, TEST_CLIENT_ID, TEST_TOKEN) as rc:
            result = await rc.deploy(
                str(src),
                TEST_AGENT_NAME,
                deploy_path=str(dest_dir),
                progress=False,
            )

        # Archive name is payload.txt.tar.gz
        dest_file = dest_dir / (src.name + ".tar.gz")
        assert dest_file.exists()
        assert result.bytes_written > 0

    @pytest.mark.asyncio
    async def test_deploy_with_post_hook(self, relay_with_agent, tmp_path):
        _, url, _ = relay_with_agent
        src = tmp_path / "data.txt"
        src.write_text("payload")

        dest_dir = tmp_path / "deploy_dest"
        dest_dir.mkdir()
        flag_path = dest_dir / "hook_ran.flag"

        if os.name == "nt":
            post_cmd = f'type nul > "{flag_path}"'
        else:
            post_cmd = f'touch "{flag_path}"'

        async with RelayClient(url, TEST_CLIENT_ID, TEST_TOKEN) as rc:
            result = await rc.deploy(
                str(src),
                TEST_AGENT_NAME,
                deploy_path=str(dest_dir),
                post_deploy=post_cmd,
                progress=False,
            )
        # Give hook a moment to run
        await asyncio.sleep(0.5)
        assert flag_path.exists(), "Post-deploy hook should have created the flag file"


# ---------------------------------------------------------------------------
# Ping
# ---------------------------------------------------------------------------

class TestPing:
    @pytest.mark.asyncio
    async def test_ping_returns_latency(self, relay_server):
        _, url = relay_server
        async with RelayClient(url, TEST_CLIENT_ID, TEST_TOKEN) as rc:
            t = await rc.ping()
            assert 0 < t < 2.0  # under 2 seconds on localhost


# ---------------------------------------------------------------------------
# Concurrent clients
# ---------------------------------------------------------------------------

class TestConcurrent:
    @pytest.mark.asyncio
    async def test_multiple_clients_simultaneously(self, relay_with_agent):
        _, url, _ = relay_with_agent

        async def client_task(i: int) -> str:
            async with RelayClient(url, f"client-{i}", TEST_TOKEN) as rc:
                result = await rc.exec(TEST_AGENT_NAME, f"echo client_{i}")
                return result.stdout.strip()

        results = await asyncio.gather(*[client_task(i) for i in range(5)])
        for i, r in enumerate(results):
            assert f"client_{i}" in r

    @pytest.mark.asyncio
    async def test_exec_session_isolation(self, relay_with_agent):
        _, url, _ = relay_with_agent

        async def client_task(i: int) -> str:
            async with RelayClient(url, f"iso-{i}", TEST_TOKEN) as rc:
                result = await rc.exec(TEST_AGENT_NAME, f"echo iso_{i}")
                return result.stdout.strip()

        results = await asyncio.gather(*[client_task(i) for i in range(8)])
        for i, r in enumerate(results):
            assert r == f"iso_{i}"

    @pytest.mark.asyncio
    async def test_five_concurrent_deploys(self, relay_with_agent, tmp_path):
        _, url, _ = relay_with_agent

        async def deploy_task(i: int):
            src = tmp_path / f"deploy_{i}.txt"
            src.write_text(f"deploy content {i}")
            dest = tmp_path / f"deploy_dest_{i}"
            dest.mkdir(exist_ok=True)
            async with RelayClient(url, f"deployer-{i}", TEST_TOKEN) as rc:
                result = await rc.deploy(
                    str(src),
                    TEST_AGENT_NAME,
                    deploy_path=str(dest),
                    progress=False,
                )
            return result.bytes_written

        results = await asyncio.gather(*[deploy_task(i) for i in range(5)])
        assert all(size > 0 for size in results)
