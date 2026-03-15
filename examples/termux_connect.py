"""
examples/termux_connect.py — connect your laptop to Termux (Android) via relay.

This replaces the manual SSH workflow:
  OLD: ssh -i ~/.ssh/termux_key -p 8022 u0_a352@192.168.1.37
  NEW: relay ssh my-phone

SETUP (one-time):

  On Termux (your phone):
    pkg install python
    pip install relay-connect websockets cryptography click
    relay-agent --relay ws://YOUR_LAPTOP_IP:8765 --name my-phone --tags termux,android

  On your laptop:
    pip install relay-connect
    relay init
    relay server start                    # in one terminal
    relay add my-phone --ssh-user u0_a352
    relay ssh my-phone                    # in another terminal

This script demonstrates the SDK version of the same flow.
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from relay.client import RelayClient

# ── Configure these ──
RELAY_URL = os.environ.get("RELAY_URL", "ws://localhost:8765")
TOKEN = os.environ.get("RELAY_TOKEN", "dev-token")
CLIENT_ID = os.environ.get("RELAY_CLIENT_ID", "my-laptop")
PHONE_AGENT = os.environ.get("RELAY_AGENT", "my-phone")


async def demo():
    print(f"\n  Connecting to relay: {RELAY_URL}")
    print(f"  Target agent: {PHONE_AGENT}\n")

    async with RelayClient(RELAY_URL, CLIENT_ID, TOKEN) as rc:
        # Check what's online
        agents = await rc.list_agents()
        online_names = [a["name"] for a in agents]
        print(f"  Online agents: {online_names}")

        if PHONE_AGENT not in online_names:
            print(f"\n  ✗ Agent '{PHONE_AGENT}' is not online.")
            print(f"  Start it on Termux with:")
            print(f"    relay-agent --relay {RELAY_URL} --name {PHONE_AGENT} --tags termux")
            return

        # Run some Termux-friendly commands
        commands = [
            "uname -a",
            "whoami",
            "pwd",
            "ls ~",
            "echo 'Hello from Termux via relay!'",
        ]

        for cmd in commands:
            print(f"  $ {cmd}")
            result = await rc.exec(PHONE_AGENT, cmd)
            if result.stdout:
                for line in result.stdout.strip().splitlines():
                    print(f"    {line}")
            if result.stderr:
                print(f"    [stderr] {result.stderr.strip()}")
            print()

        # Deploy a file to Termux
        print("  Deploying a test file to Termux ~/relay-test/...")
        import tempfile, time
        with tempfile.NamedTemporaryFile(suffix=".sh", delete=False, mode="w") as f:
            f.write(f"""#!/data/data/com.termux/files/usr/bin/bash
# Deployed by relay-connect at {time.ctime()}
echo "Hello from relay deployed script!"
echo "Running on: $(uname -n)"
""")
            src = f.name

        result = await rc.deploy(
            src,
            PHONE_AGENT,
            deploy_path=os.path.expanduser("~/relay-test"),
            progress=True,
        )
        print(f"\n  ✓ Deployed to {result.path}")

        # Execute the deployed script
        await asyncio.sleep(0.3)
        result = await rc.exec(PHONE_AGENT, f"bash ~/relay-test/{Path(src).name}.tar.gz 2>/dev/null || ls ~/relay-test/")
        print(f"  Remote files: {result.stdout.strip()}")

    print("\n  Done! Your laptop and Termux are connected via relay.\n")


if __name__ == "__main__":
    asyncio.run(demo())
