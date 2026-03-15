"""
examples/quickstart.py — full end-to-end demo in one script.

Starts a relay server + agent in background threads, then uses the
Python SDK to exec a command and deploy a file.

Run:
  python examples/quickstart.py
"""

import asyncio
import sys
import tempfile
import threading
import time
from pathlib import Path

# Make sure local relay package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from relay.server import RelayServer
from relay.agent import RelayAgent
from relay.client import RelayClient

RELAY_PORT = 8765
RELAY_URL = f"ws://127.0.0.1:{RELAY_PORT}"
AGENT_NAME = "demo-server"
TOKEN = "demo-token"
CLIENT_ID = "demo-client"


def start_server():
    import asyncio
    server = RelayServer(
        host="127.0.0.1",
        port=RELAY_PORT,
        token=TOKEN,
        require_auth=True,
        cert_ttl=60,
    )
    asyncio.run(server.start())


def start_agent():
    import asyncio
    agent = RelayAgent(
        relay_url=RELAY_URL,
        agent_name=AGENT_NAME,
        tags=["demo"],
        reconnect_delay=2,
    )
    asyncio.run(agent.run())


async def main():
    print("\n" + "═" * 55)
    print("  relay-connect  quickstart demo")
    print("═" * 55)

    # ── 1. Start relay server ──
    print("\n[1/4] Starting relay server...")
    srv_thread = threading.Thread(target=start_server, daemon=True)
    srv_thread.start()
    await asyncio.sleep(0.5)
    print("  ✓ Relay server on", RELAY_URL)

    # ── 2. Start agent ──
    print("\n[2/4] Starting agent...")
    agt_thread = threading.Thread(target=start_agent, daemon=True)
    agt_thread.start()
    await asyncio.sleep(0.5)
    print(f"  ✓ Agent '{AGENT_NAME}' connected")

    # ── 3. Connect client ──
    print("\n[3/4] Connecting client...")
    async with RelayClient(RELAY_URL, CLIENT_ID, TOKEN) as rc:
        latency = await rc.ping()
        print(f"  ✓ Connected (latency {latency*1000:.1f}ms)")

        agents = await rc.list_agents()
        print(f"  ✓ Online agents: {[a['name'] for a in agents]}")

        # ── 4. Exec + deploy ──
        print("\n[4/4] Running commands & deploying...")

        result = await rc.exec(AGENT_NAME, "uname -a")
        print(f"\n  $ uname -a")
        print(f"  {result.stdout.strip()}")

        result = await rc.exec(AGENT_NAME, "echo 'relay tunnel works!'")
        print(f"\n  $ echo 'relay tunnel works!'")
        print(f"  {result.stdout.strip()}")

        result = await rc.exec(AGENT_NAME, "python3 --version || python --version")
        print(f"\n  $ python --version")
        print(f"  {result.stdout.strip() or result.stderr.strip()}")

        # Deploy a file
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            f.write("Hello from relay-connect deploy!\nTimestamp: " + str(time.time()))
            src = f.name

        print(f"\n  Deploying {src}...")
        result = await rc.deploy(src, AGENT_NAME, deploy_path="/tmp/relay-demo", progress=True)
        print(f"  ✓ Deploy complete: {result.path} ({result.bytes_written} bytes, {result.elapsed:.2f}s)")

    print("\n" + "═" * 55)
    print("  All done. relay-connect works!")
    print("═" * 55 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
