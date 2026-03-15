"""Entry point for the relay-agent command."""
import asyncio
import click
import os
from pathlib import Path
from relay.agent import RelayAgent
from relay import __version__


@click.command()
@click.version_option(__version__, prog_name="relay-agent")
@click.option("--relay", "relay_url", default="ws://localhost:8765", help="Relay server URL")
@click.option("--name", required=True, help="Agent name (must match profile on client)")
@click.option("--tags", default="", help="Comma-separated tags")
@click.option("--deploy-base", default="/tmp/relay-deploy", help="Base directory for deployments")
@click.option("--pubkey", default="", help="Path to relay server public key PEM")
@click.option("--debug", is_flag=True, default=False)
def main(relay_url, name, tags, deploy_base, pubkey, debug):
    """
    Start the relay agent on this machine.

    The agent dials OUTBOUND to the relay server.
    No inbound ports are needed on this machine.

    Example:
      relay-agent --relay wss://relay.example.com --name prod-1
      relay-agent --relay ws://localhost:8765 --name my-phone --tags termux,android
    """
    import logging
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    agent = RelayAgent(
        relay_url=relay_url,
        agent_name=name,
        tags=tag_list,
        deploy_base=deploy_base,
        relay_pubkey_path=Path(pubkey) if pubkey else None,
    )
    click.echo(f"  Starting relay-agent '{name}' → {relay_url}")
    click.echo(f"  Deploy base: {deploy_base}")
    if tag_list:
        click.echo(f"  Tags: {', '.join(tag_list)}")
    click.echo("  Press Ctrl+C to stop\n")
    asyncio.run(agent.run())


if __name__ == "__main__":
    main()
