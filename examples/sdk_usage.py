"""
examples/sdk_usage.py — relay-connect Python SDK reference examples.

Shows every major SDK operation with inline documentation.
"""

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from relay.client import RelayClient
from relay.exceptions import AgentNotFoundError, AuthError, DeployError


RELAY_URL = os.environ.get("RELAY_URL", "ws://localhost:8765")
TOKEN = os.environ.get("RELAY_TOKEN", "dev-token")
CLIENT_ID = os.environ.get("RELAY_CLIENT_ID", "sdk-example")
AGENT = os.environ.get("RELAY_AGENT", "demo-server")


async def example_connect_and_ping():
    """Connect to relay and measure latency."""
    print("── Connect & ping ──")
    async with RelayClient(RELAY_URL, CLIENT_ID, TOKEN) as rc:
        ms = await rc.ping() * 1000
        print(f"  Relay latency: {ms:.1f}ms")


async def example_list_agents():
    """List all agents currently connected to the relay."""
    print("── List agents ──")
    async with RelayClient(RELAY_URL, CLIENT_ID, TOKEN) as rc:
        agents = await rc.list_agents()
        if not agents:
            print("  No agents online")
        for a in agents:
            print(f"  • {a['name']}  tags={a.get('tags', [])}  v{a.get('version', '?')}")


async def example_exec():
    """Run a command on a remote agent."""
    print("── Remote exec ──")
    async with RelayClient(RELAY_URL, CLIENT_ID, TOKEN) as rc:
        # Simple command
        result = await rc.exec(AGENT, "echo hello")
        print(f"  stdout: {result.stdout.strip()}")
        print(f"  exit:   {result.exit_code}")

        # Check system info
        result = await rc.exec(AGENT, "uname -a && uptime")
        print(f"  system: {result.stdout.strip()[:80]}")

        # Capture exit code for scripting
        result = await rc.exec(AGENT, "test -f /etc/os-release && cat /etc/os-release | head -3")
        if result.ok:
            print(f"  OS: {result.stdout.strip()[:100]}")


async def example_deploy_file():
    """Deploy a single file to a remote agent."""
    print("── Deploy single file ──")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
        f.write(f"<h1>Deployed at {time.ctime()}</h1>\n")
        src = f.name

    async with RelayClient(RELAY_URL, CLIENT_ID, TOKEN) as rc:
        result = await rc.deploy(
            local_path=src,
            agent_name=AGENT,
            deploy_path="/tmp/relay-example",
            progress=True,
        )
        print(f"\n  Path:    {result.path}")
        print(f"  Bytes:   {result.bytes_written}")
        print(f"  Elapsed: {result.elapsed:.2f}s")


async def example_deploy_directory():
    """Deploy a whole directory (e.g. a built web app)."""
    print("── Deploy directory ──")
    with tempfile.TemporaryDirectory() as src_dir:
        # Simulate a built app
        Path(src_dir, "index.html").write_text("<html><body>Hello World</body></html>")
        Path(src_dir, "style.css").write_text("body { font-family: sans-serif }")
        Path(src_dir, "app.js").write_text("console.log('relay deployed')")

        async with RelayClient(RELAY_URL, CLIENT_ID, TOKEN) as rc:
            result = await rc.deploy(
                local_path=src_dir,
                agent_name=AGENT,
                deploy_path="/tmp/relay-app",
                post_deploy="echo 'Deployed! Restarting would happen here.'",
                progress=True,
            )
            print(f"\n  Result: {result}")


async def example_deploy_with_restart():
    """Deploy + automatically restart a service."""
    print("── Deploy + restart ──")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("print('app v2 running')\n")
        src = f.name

    async with RelayClient(RELAY_URL, CLIENT_ID, TOKEN) as rc:
        result = await rc.deploy(
            local_path=src,
            agent_name=AGENT,
            deploy_path="/tmp/relay-myapp",
            # This runs on the remote server after deploy completes
            post_deploy="echo 'service restart would happen here'",
            progress=True,
        )
        print(f"\n  Deployed + hook ran: {result.path}")


async def example_error_handling():
    """Handle errors gracefully."""
    print("── Error handling ──")
    async with RelayClient(RELAY_URL, CLIENT_ID, TOKEN) as rc:
        try:
            cert = await rc.get_cert("nonexistent-server")
        except AgentNotFoundError as e:
            print(f"  AgentNotFoundError (expected): {e}")

        try:
            result = await rc.exec(AGENT, "exit 1")
            if not result.ok:
                print(f"  Command failed with exit {result.exit_code} (expected)")
        except Exception as e:
            print(f"  Unexpected error: {e}")


async def example_cert_caching():
    """Certs are cached and reused until near-expiry."""
    print("── Cert caching ──")
    async with RelayClient(RELAY_URL, CLIENT_ID, TOKEN) as rc:
        cert1 = await rc.get_cert(AGENT)
        cert2 = await rc.get_cert(AGENT)  # should be same cert
        print(f"  Session IDs match: {cert1.session_id == cert2.session_id}")
        print(f"  Time remaining: {cert1.time_remaining():.0f}s")

        cert3 = await rc.get_cert(AGENT, force=True)  # force new cert
        print(f"  Forced new cert: {cert1.session_id != cert3.session_id}")


async def main():
    print("\n" + "═" * 50)
    print("  relay-connect SDK examples")
    print("═" * 50 + "\n")

    # Each example is independent — skip if agent not online
    async with RelayClient(RELAY_URL, CLIENT_ID, TOKEN) as rc:
        agents = await rc.list_agents()
        agent_online = any(a["name"] == AGENT for a in agents)

    examples = [
        ("connect_and_ping", example_connect_and_ping, False),
        ("list_agents", example_list_agents, False),
        ("exec", example_exec, True),
        ("deploy_file", example_deploy_file, True),
        ("deploy_directory", example_deploy_directory, True),
        ("deploy_with_restart", example_deploy_with_restart, True),
        ("error_handling", example_error_handling, False),
        ("cert_caching", example_cert_caching, True),
    ]

    for name, fn, needs_agent in examples:
        if needs_agent and not agent_online:
            print(f"── {name} ── (skipped — agent '{AGENT}' not online)")
            continue
        try:
            await fn()
        except Exception as e:
            print(f"  [error in {name}]: {e}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
