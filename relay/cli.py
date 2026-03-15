"""
relay.cli — command-line interface.

Commands:
  relay init                        initialise config
  relay server start                start relay mediator
  relay agent start --name X        start agent on this machine
  relay add <name> [--relay URL]    register a server profile
  relay remove <name>               remove a server profile
  relay list                        list registered servers + online status
  relay ssh <name>                  interactive SSH shell (via relay tunnel)
  relay deploy <path> <name>        deploy files to server
  relay exec <name> <cmd>           run a command on server
  relay ping <name>                 latency check
  relay logs                        tail relay audit log
  relay status                      relay + agent health
"""

import asyncio
import json
import logging
import os
import platform
import secrets
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import click

from relay import __version__
from relay.config import (
    add_server,
    get_server,
    init_config,
    list_servers,
    load_config,
    remove_server,
    ServerProfile,
    save_config,
    DEFAULT_DEPLOY_PATH,
    CONFIG_DIR,
)
from relay.exceptions import RelayError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """Run async coroutine in sync context."""
    return asyncio.run(coro)


def _success(msg: str):
    click.echo(click.style("  ✓ " + msg, fg="green"))


def _fail(msg: str):
    click.echo(click.style("  ✗ " + msg, fg="red"), err=True)


def _info(msg: str):
    click.echo(click.style("  → " + msg, fg="cyan"))


def _bold(msg: str):
    click.echo(click.style(msg, bold=True))


def _get_local_ipv4() -> str:
    """Best-effort local IPv4 for LAN connectivity."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def _is_termux() -> bool:
    return bool(os.environ.get("TERMUX_VERSION") or "com.termux" in os.environ.get("PREFIX", ""))


def _has_display() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") or os.name == "nt")


def _open_firewall(port: int) -> None:
    if _is_windows():
        result = subprocess.run(
            [
                "netsh",
                "advfirewall",
                "firewall",
                "add",
                "rule",
                "name=relay-connect",
                "dir=in",
                "action=allow",
                "protocol=TCP",
                f"localport={port}",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            _info("⚠ Could not open firewall automatically. Run this as Administrator:")
            _info("netsh advfirewall firewall add rule name=relay-connect dir=in action=allow protocol=TCP localport=8765")
        return

    if platform.system() == "Linux":
        if shutil.which("ufw"):
            status = subprocess.run(["ufw", "status"], capture_output=True, text=True)
            if "Status: active" in status.stdout:
                subprocess.run(["ufw", "allow", f"{port}/tcp"], check=False)
        return

    if platform.system() == "Darwin":
        _info("macOS firewall: run one of these (admin):")
        _info(f"sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add $(which relay)")
        _info(f"sudo /usr/libexec/ApplicationFirewall/socketfilterfw --unblockapp $(which relay)")


def _print_qr(payload: str) -> None:
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(payload)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    except Exception:
        _info("QR code unavailable — copy this string to your phone:")
        click.echo(payload)


def _is_windows() -> bool:
    return os.name == "nt"


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(__version__, prog_name="relay")
@click.option("--debug", is_flag=True, default=False, help="Enable debug logging")
def cli(debug: bool):
    """relay-connect — dead-simple secure remote connections."""
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(level=level, format="%(name)s %(levelname)s %(message)s")


# ---------------------------------------------------------------------------
# relay init
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--relay-url", default="ws://localhost:8765", help="Relay server URL")
@click.option("--client-id", default="", help="Your client identity")
def init(relay_url: str, client_id: str):
    """Initialise relay config at ~/.relay/config.json"""
    cfg = init_config(relay_url=relay_url, client_id=client_id)
    _success(f"Config initialised at ~/.relay/config.json")
    _info(f"Relay URL:  {cfg.default_relay_url}")
    _info(f"Client ID:  {cfg.client_id}")
    _info("Run 'relay add <name>' to register your first server")


# ---------------------------------------------------------------------------
# relay setup
# ---------------------------------------------------------------------------

@cli.command("setup")
@click.option("--termux", is_flag=True, default=False, help="Show Termux-friendly steps")
@click.option("--agent-name", default="my-phone", help="Agent name for phone/device")
@click.option("--tags", default="termux", help="Comma-separated tags")
@click.option("--relay-port", default=8765, help="Relay server port")
def setup_cmd(termux: bool, agent_name: str, tags: str, relay_port: int):
    """Guided setup for non-technical users."""
    local_ip = _get_local_ipv4()
    tag_list = ",".join([t.strip() for t in tags.split(",") if t.strip()]) or "termux"

    _bold("\nrelay-connect setup")
    _info("Step 1: start the relay server on your laptop")
    if _is_windows():
        click.echo(f"  $env:RELAY_TOKEN=\"dev-token\"")
        click.echo(f"  relay server start --host 0.0.0.0 --port {relay_port}")
        click.echo("\n  If the phone cannot connect, open the firewall (Admin PowerShell):")
        click.echo(f"  New-NetFirewallRule -DisplayName \"relay-connect {relay_port}\" -Direction Inbound -Protocol TCP -LocalPort {relay_port} -Action Allow")
    else:
        click.echo(f"  export RELAY_TOKEN=dev-token")
        click.echo(f"  relay server start --host 0.0.0.0 --port {relay_port}")

    if termux:
        _info("\nStep 2: install and start the agent on Termux")
        click.echo("  pkg install -y python git")
        click.echo("  python -m pip install --upgrade pip setuptools wheel")
        click.echo("  python -m pip install git+https://github.com/Hardik-Sankhla/relay-connect.git")
        click.echo(f"  relay-agent --relay ws://{local_ip}:{relay_port} --name {agent_name} --tags {tag_list}")

        _info("\nStep 3: connect from your laptop")
        click.echo(f"  relay add {agent_name} --tags {tag_list}")
        click.echo("  relay status")
        click.echo(f"  relay ssh {agent_name}")
        _info("If status shows no agents online, confirm same Wi-Fi and firewall rules.")
    else:
        _info("\nTip: add --termux for a guided phone setup")


@cli.command("wizard")
@click.option("--port", default=8765, help="Relay server port")
@click.option("--agent-name", default="", help="Suggested agent name")
@click.option("--dry-run", is_flag=True, default=False, help="Show actions without executing")
def wizard_cmd(port: int, agent_name: str, dry_run: bool):
    """One-command setup for beginners (auto config + QR)."""
    is_termux = _is_termux()

    if is_termux:
        _wizard_termux(port=port, agent_name=agent_name, dry_run=dry_run)
        return

    # Laptop/server role
    token = secrets.token_urlsafe(24)
    local_ip = _get_local_ipv4()
    name = agent_name or socket.gethostname()
    relay_url = f"ws://{local_ip}:{port}"

    _bold("\nrelay-connect wizard")
    _info(f"Detected role: laptop/server")
    _info(f"Relay URL: {relay_url}")

    # Save env
    env_path = CONFIG_DIR / ".env"
    if not dry_run:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        env_path.write_text(
            f"RELAY_TOKEN={token}\nRELAY_URL={relay_url}\nRELAY_CLIENT_ID={socket.gethostname()}\n"
        )
    _success(f"Saved {env_path}")

    # Start server
    if not dry_run:
        cmd = [sys.executable, "-m", "relay", "server", "start", "--host", "0.0.0.0", "--port", str(port)]
        env = os.environ.copy()
        env["RELAY_TOKEN"] = token
        if _is_windows():
            flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            subprocess.Popen(cmd, env=env, creationflags=flags)
        else:
            subprocess.Popen(cmd, env=env, start_new_session=True)
    _success("Relay server started in background")

    # Firewall
    if not dry_run:
        _open_firewall(port)

    payload = f"relay-connect://{local_ip}:{port}?token={token}&name={name}"
    _bold("\nScan this QR on your phone:")
    _print_qr(payload)
    click.echo(f"\n{payload}\n")

    _info("On your phone, run: relay wizard")


def _wizard_termux(port: int, agent_name: str, dry_run: bool):
    _bold("\nrelay-connect wizard (Termux)")
    _info("Paste the QR string from your laptop (or scan it):")
    payload = click.prompt("  relay-connect://...", prompt_suffix=" ")

    try:
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(payload)
        token = parse_qs(parsed.query).get("token", [""])[0]
        name = parse_qs(parsed.query).get("name", [""])[0]
        host = parsed.hostname or ""
        port = parsed.port or port
    except Exception:
        _fail("Could not parse QR string. Make sure it starts with relay-connect://")
        sys.exit(1)

    if not (host and token):
        _fail("Missing host or token in QR string")
        sys.exit(1)

    agent_name = agent_name or name or "my-phone"
    relay_url = f"ws://{host}:{port}"

    if not dry_run:
        _termux_install_if_needed()

        # Save env for convenience
        env_path = Path.home() / ".relay" / ".env"
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text(f"RELAY_TOKEN={token}\nRELAY_URL={relay_url}\n")

        _termux_boot_script(relay_url, token, agent_name)

        if shutil.which("termux-wake-lock"):
            subprocess.run(["termux-wake-lock"], check=False)

    _success("Termux setup complete")
    _info("Starting agent now...")
    if not dry_run:
        os.environ["RELAY_TOKEN"] = token
        subprocess.run(["relay-agent", "--relay", relay_url, "--name", agent_name, "--tags", "termux"], check=False)


def _termux_install_if_needed():
    if shutil.which("pkg"):
        subprocess.run(["pkg", "install", "-y", "python", "git"], check=False)
    pip_cmd = [sys.executable, "-m", "pip", "install"]
    if _is_termux():
        pip_cmd.append("--break-system-packages")
    subprocess.run(pip_cmd + ["--upgrade", "pip", "setuptools", "wheel"], check=False)
    subprocess.run(pip_cmd + ["git+https://github.com/Hardik-Sankhla/relay-connect.git"], check=False)


def _termux_boot_script(relay_url: str, token: str, agent_name: str):
    boot_dir = Path.home() / ".termux" / "boot"
    boot_dir.mkdir(parents=True, exist_ok=True)
    script = boot_dir / "relay-agent.sh"
    script.write_text(
        "#!/data/data/com.termux/files/usr/bin/bash\n"
        f"export RELAY_TOKEN=\"{token}\"\n"
        f"exec relay-agent --relay \"{relay_url}\" --name \"{agent_name}\" --tags \"termux\" --persistent\n"
    )
    script.chmod(0o755)


@cli.command("termux-setup")
@click.option("--relay", "relay_url", default="", help="Relay server URL")
@click.option("--name", "agent_name", default="my-phone", help="Agent name")
@click.option("--token", default="", help="Relay token")
def termux_setup_cmd(relay_url: str, agent_name: str, token: str):
    """Automate Termux setup (install + autostart)."""
    if not _is_termux():
        _fail("This command is for Termux on Android.")
        sys.exit(1)

    _termux_install_if_needed()
    if relay_url and token:
        _termux_boot_script(relay_url, token, agent_name)
        if shutil.which("termux-wake-lock"):
            subprocess.run(["termux-wake-lock"], check=False)
        _success("Termux setup complete. Starting agent...")
        os.environ["RELAY_TOKEN"] = token
        subprocess.run(["relay-agent", "--relay", relay_url, "--name", agent_name, "--tags", "termux", "--persistent"], check=False)
    else:
        _info("Run: relay wizard  (on your phone) for QR-based setup")


@cli.command("doctor")
@click.option("--relay", "relay_url", default="", help="Relay server URL")
def doctor_cmd(relay_url: str):
    """Diagnose common setup problems."""
    from relay import __version__
    cfg = load_config()
    relay_url = relay_url or cfg.default_relay_url
    _bold("\nrelay doctor")

    def check(label: str, ok: bool, fix: str = ""):
        mark = "✓" if ok else "✗"
        click.echo(f"  {mark} {label}")
        if not ok and fix:
            click.echo(f"    {fix}")

    check("Python >= 3.10", sys.version_info >= (3, 10))
    try:
        import websockets  # noqa: F401
        websockets_ok = True
    except Exception:
        websockets_ok = False
    check("websockets installed", websockets_ok, "pip install websockets")
    try:
        import cryptography  # noqa: F401
        crypto_ok = True
    except Exception:
        crypto_ok = False
    check("cryptography installed", crypto_ok, "pip install cryptography")
    check("Config exists", (CONFIG_DIR / "config.json").exists(), "Run: relay init")

    # DNS + TCP
    try:
        host = relay_url.split("//", 1)[-1].split(":", 1)[0]
        socket.gethostbyname(host)
        dns_ok = True
    except Exception:
        dns_ok = False
    check("Relay hostname resolves", dns_ok, "Check relay URL / DNS")

    try:
        host_port = relay_url.split("//", 1)[-1]
        host, port = host_port.split(":")
        port = int(port)
        sock = socket.create_connection((host, port), timeout=3)
        sock.close()
        tcp_ok = True
    except Exception:
        tcp_ok = False
    check("TCP connect to relay", tcp_ok, "Check relay server + firewall")

    # WebSocket auth
    auth_ok = False
    try:
        async def _auth_check():
            from relay.client import RelayClient
            async with RelayClient(relay_url=relay_url, client_id=cfg.client_id, token=os.environ.get("RELAY_TOKEN", "")) as rc:
                await rc.ping()
        asyncio.run(_auth_check())
        auth_ok = True
    except Exception:
        auth_ok = False
    check("WebSocket auth", auth_ok, "Check RELAY_TOKEN matches on both machines")

    # Agent online
    agents_ok = False
    try:
        async def _agent_check():
            from relay.client import RelayClient
            async with RelayClient(relay_url=relay_url, client_id=cfg.client_id, token=os.environ.get("RELAY_TOKEN", "")) as rc:
                agents = await rc.list_agents()
                return len(agents) > 0
        agents_ok = asyncio.run(_agent_check())
    except Exception:
        agents_ok = False
    check("At least one agent online", agents_ok, "Run relay-agent on the remote machine")

    if _is_windows():
        result = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule", "name=relay-connect"],
            capture_output=True,
            text=True,
        )
        check("Windows firewall rule", result.returncode == 0, "Run as Admin: netsh advfirewall firewall add rule name=relay-connect dir=in action=allow protocol=TCP localport=8765")

    if _is_termux():
        boot_ok = (Path.home() / ".termux" / "boot" / "relay-agent.sh").exists()
        check("Termux boot script", boot_ok, "Run: relay wizard (on phone)")
        check("termux-wake-lock available", bool(shutil.which("termux-wake-lock")), "pkg install termux-api")


# ---------------------------------------------------------------------------
# relay add
# ---------------------------------------------------------------------------

@cli.command("add")
@click.argument("name")
@click.option("--relay-url", default="", help="Override relay URL for this server")
@click.option("--deploy-path", default=DEFAULT_DEPLOY_PATH, help="Remote deploy directory")
@click.option("--post-deploy", default="", help="Shell command to run after deploy")
@click.option("--ssh-user", default="", help="SSH user on remote server")
@click.option("--tags", default="", help="Comma-separated tags")
@click.option("--description", default="", help="Human description")
def add(name, relay_url, deploy_path, post_deploy, ssh_user, tags, description):
    """Register a remote server profile."""
    cfg = load_config()
    url = relay_url or cfg.default_relay_url

    profile = ServerProfile(
        name=name,
        relay_url=url,
        agent_name=name,
        deploy_path=deploy_path,
        post_deploy=post_deploy,
        ssh_user=ssh_user or os.environ.get("USER", "relay"),
        tags=[t.strip() for t in tags.split(",") if t.strip()],
        description=description,
    )
    add_server(profile)
    _success(f"Server '{name}' registered")
    _info(f"Relay: {url}")
    _info(f"Deploy path: {deploy_path}")
    if post_deploy:
        _info(f"Post-deploy: {post_deploy}")


# ---------------------------------------------------------------------------
# relay remove
# ---------------------------------------------------------------------------

@cli.command("remove")
@click.argument("name")
@click.confirmation_option(prompt=f"Remove server?")
def remove(name: str):
    """Remove a server profile."""
    remove_server(name)
    _success(f"Server '{name}' removed")


# ---------------------------------------------------------------------------
# relay list
# ---------------------------------------------------------------------------

@cli.command("list")
@click.option("--check-online", is_flag=True, default=False, help="Ping relay to check online status")
def list_cmd(check_online: bool):
    """List all registered server profiles."""
    servers = list_servers()
    if not servers:
        click.echo("No servers registered. Run: relay add <name>")
        return

    _bold(f"\n{'NAME':<16} {'RELAY':<35} {'DEPLOY PATH':<25} TAGS")
    click.echo("─" * 90)
    for s in servers:
        tags = ", ".join(s.tags) if s.tags else "—"
        click.echo(f"  {s.name:<14} {s.relay_url:<35} {s.deploy_path:<25} {tags}")
    click.echo()


# ---------------------------------------------------------------------------
# relay server
# ---------------------------------------------------------------------------

@cli.group("server")
def server_group():
    """Manage the relay mediator server."""


@server_group.command("start")
@click.option("--host", default="0.0.0.0", help="Bind host")
@click.option("--port", default=8765, help="Listen port")
@click.option("--token", default="", help="Auth token (default: RELAY_TOKEN env or 'dev-token')")
@click.option("--no-auth", is_flag=True, default=False, help="Disable auth (dev only)")
def server_start(host: str, port: int, token: str, no_auth: bool):
    """Start the relay mediator server."""
    from relay.server import run_server
    token = token or os.environ.get("RELAY_TOKEN", "dev-token")
    _info(f"Starting relay server on ws://{host}:{port}")
    if no_auth:
        click.echo(click.style("  WARNING: auth disabled — use only for local testing", fg="yellow"))
    run_server(host=host, port=port, token=token, require_auth=not no_auth)


# ---------------------------------------------------------------------------
# relay agent
# ---------------------------------------------------------------------------

@cli.group("agent")
def agent_group():
    """Manage the relay agent (install on remote servers)."""


@agent_group.command("start")
@click.option("--relay", "relay_url", default="ws://localhost:8765", help="Relay server URL")
@click.option("--name", required=True, help="Agent name (must match server profile name)")
@click.option("--tags", default="", help="Comma-separated tags (e.g. prod,us-east)")
@click.option("--deploy-base", default="/tmp/relay-deploy", help="Base dir for deployed files")
@click.option("--pubkey", default="", help="Path to relay server public key (for cert verification)")
def agent_start(relay_url: str, name: str, tags: str, deploy_base: str, pubkey: str):
    """Start relay agent on this machine (connects outbound to relay)."""
    from relay.agent import RelayAgent
    _info(f"Starting agent '{name}' → {relay_url}")
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    agent = RelayAgent(
        relay_url=relay_url,
        agent_name=name,
        tags=tag_list,
        deploy_base=deploy_base,
        relay_pubkey_path=Path(pubkey) if pubkey else None,
    )
    asyncio.run(agent.run())


# ---------------------------------------------------------------------------
# relay ping
# ---------------------------------------------------------------------------

@cli.command("ping")
@click.argument("name")
@click.option("--count", default=3, help="Number of pings")
def ping_cmd(name: str, count: int):
    """Ping relay and agent to measure latency."""
    try:
        server = get_server(name)
    except RelayError as e:
        _fail(str(e))
        sys.exit(1)

    async def _ping():
        from relay.client import RelayClient
        cfg = load_config()
        async with RelayClient(
            relay_url=server.relay_url,
            client_id=cfg.client_id,
            token=os.environ.get("RELAY_TOKEN", "dev-token"),
        ) as rc:
            times = []
            for i in range(count):
                t = await rc.ping()
                times.append(t * 1000)
                _info(f"ping {i+1}: {t*1000:.1f}ms")
                if i < count - 1:
                    await asyncio.sleep(0.5)
            avg = sum(times) / len(times)
            _success(f"avg {avg:.1f}ms over {count} pings")

    _run(_ping())


# ---------------------------------------------------------------------------
# relay exec
# ---------------------------------------------------------------------------

@cli.command("exec")
@click.argument("name")
@click.argument("command", nargs=-1, required=True)
def exec_cmd(name: str, command: tuple):
    """Execute a command on a remote server via the relay."""
    cmd = " ".join(command)
    try:
        server = get_server(name)
    except RelayError as e:
        _fail(str(e))
        sys.exit(1)

    async def _exec():
        from relay.client import RelayClient
        cfg = load_config()
        async with RelayClient(
            relay_url=server.relay_url,
            client_id=cfg.client_id,
            token=os.environ.get("RELAY_TOKEN", "dev-token"),
        ) as rc:
            _info(f"exec on '{name}': {cmd}")
            result = await rc.exec(name, cmd)
            if result.stdout:
                click.echo(result.stdout, nl=False)
            if result.stderr:
                click.echo(click.style(result.stderr, fg="red"), nl=False, err=True)
            return result.exit_code

    exit_code = _run(_exec())
    sys.exit(exit_code)


# ---------------------------------------------------------------------------
# relay deploy
# ---------------------------------------------------------------------------

@cli.command("deploy")
@click.argument("path")
@click.argument("name")
@click.option("--deploy-path", default="", help="Override remote deploy directory")
@click.option("--post-deploy", default="", help="Override post-deploy command")
@click.option("--no-progress", is_flag=True, default=False)
def deploy_cmd(path: str, name: str, deploy_path: str, post_deploy: str, no_progress: bool):
    """Deploy files or a directory to a remote server."""
    try:
        server = get_server(name)
    except RelayError as e:
        _fail(str(e))
        sys.exit(1)

    dest = deploy_path or server.deploy_path
    hook = post_deploy or server.post_deploy

    async def _deploy():
        from relay.client import RelayClient
        cfg = load_config()
        _info(f"Deploying {path} → {name}:{dest}")
        if hook:
            _info(f"Post-deploy hook: {hook}")

        async with RelayClient(
            relay_url=server.relay_url,
            client_id=cfg.client_id,
            token=os.environ.get("RELAY_TOKEN", "dev-token"),
        ) as rc:
            result = await rc.deploy(
                local_path=path,
                agent_name=name,
                deploy_path=dest,
                post_deploy=hook,
                progress=not no_progress,
            )
            _success(f"Deploy complete in {result.elapsed:.1f}s")
            _info(f"Remote path: {result.path}")
            _info(f"Bytes written: {result.bytes_written:,}")

    try:
        _run(_deploy())
    except RelayError as e:
        _fail(str(e))
        sys.exit(1)


# ---------------------------------------------------------------------------
# relay ssh
# ---------------------------------------------------------------------------

@cli.command("ssh")
@click.argument("name")
@click.option("--command", "-c", default="", help="Run single command instead of interactive shell")
def ssh_cmd(name: str, command: str):
    """Open an interactive SSH shell through the relay tunnel."""
    try:
        server = get_server(name)
    except RelayError as e:
        _fail(str(e))
        sys.exit(1)

    _info(f"Opening shell on '{name}' via relay...")
    _info("(Commands are forwarded through the relay — no direct SSH port needed)")

    try:
        import paramiko  # noqa: F401
        paramiko_available = True
    except Exception:
        paramiko_available = False

    async def _ssh():
        from relay.client import RelayClient
        cfg = load_config()

        async with RelayClient(
            relay_url=server.relay_url,
            client_id=cfg.client_id,
            token=os.environ.get("RELAY_TOKEN", "dev-token"),
        ) as rc:
            if command:
                result = await rc.exec(name, command)
                if result.stdout:
                    click.echo(result.stdout, nl=False)
                if result.stderr:
                    click.echo(result.stderr, nl=False, err=True)
                return result.exit_code
            else:
                if not paramiko_available:
                    _info("⚠ Interactive mode limited — install relay-connect[ssh] for full PTY")
                    click.echo(click.style(
                        f"\n  [relay-shell: basic mode — install relay-connect[ssh] for full PTY]\n",
                        fg="yellow",
                    ))
                    while True:
                        try:
                            cmd = click.prompt(f"  {name}$ ", prompt_suffix="")
                        except (EOFError, KeyboardInterrupt):
                            click.echo("\n  Disconnected.")
                            break
                        if cmd.strip() in ("exit", "quit"):
                            click.echo("  Disconnected.")
                            break
                        if not cmd.strip():
                            continue
                        result = await rc.exec(name, cmd)
                        if result.stdout:
                            click.echo(result.stdout, nl=False)
                        if result.stderr:
                            click.echo(click.style(result.stderr, fg="yellow"), nl=False)
                    return 0

                click.echo(click.style(f"\n  Connected to '{name}'. Type 'exit' to quit.\n", fg="green"))
                return await rc.shell(name)

    try:
        exit_code = _run(_ssh())
        sys.exit(exit_code or 0)
    except RelayError as e:
        _fail(str(e))
        sys.exit(1)


# ---------------------------------------------------------------------------
# relay status
# ---------------------------------------------------------------------------

@cli.command("status")
def status_cmd():
    """Show relay connectivity and registered agent status."""
    servers = list_servers()
    if not servers:
        click.echo("No servers registered.")
        return

    async def _check():
        from relay.client import RelayClient
        cfg = load_config()

        relay_urls = {s.relay_url for s in servers}
        for url in relay_urls:
            click.echo(f"\n  Relay: {url}")
            try:
                async with RelayClient(
                    relay_url=url,
                    client_id=cfg.client_id,
                    token=os.environ.get("RELAY_TOKEN", "dev-token"),
                    timeout=5,
                ) as rc:
                    latency = await rc.ping()
                    agents = await rc.list_agents()
                    _success(f"Connected (latency {latency*1000:.0f}ms)")
                    if agents:
                        _bold("  Online agents:")
                        for a in agents:
                            tags = ", ".join(a.get("tags", []))
                            click.echo(f"    • {a['name']}  tags=[{tags}]  v{a.get('version','?')}")
                    else:
                        _info("No agents online")
            except Exception as e:
                _fail(f"Cannot reach relay: {e}")

    _run(_check())


# ---------------------------------------------------------------------------
# relay logs
# ---------------------------------------------------------------------------

@cli.command("logs")
@click.option("--tail", default=50, help="Number of recent lines to show")
@click.option("--follow", "-f", is_flag=True, default=False, help="Follow log output")
def logs_cmd(tail: int, follow: bool):
    """Show relay audit logs."""
    from relay.config import CONFIG_DIR
    audit = CONFIG_DIR / "logs" / "audit.log"

    if not audit.exists():
        click.echo("No audit log found. Start the relay server first.")
        return

    import json

    def format_line(line: str) -> str:
        try:
            r = json.loads(line)
            ts = time.strftime("%H:%M:%S", time.localtime(r.get("ts", 0)))
            event = r.get("event", "?")
            rest = {k: v for k, v in r.items() if k not in ("ts", "event")}
            return f"  {ts}  {click.style(event, bold=True, fg='cyan')}  {rest}"
        except Exception:
            return "  " + line.strip()

    lines = audit.read_text().strip().splitlines()
    for line in lines[-tail:]:
        click.echo(format_line(line))

    if follow:
        import time as _time
        click.echo(click.style("  (following — Ctrl+C to stop)", fg="yellow"))
        with open(audit) as f:
            f.seek(0, 2)
            while True:
                line = f.readline()
                if line:
                    click.echo(format_line(line))
                else:
                    _time.sleep(0.5)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    cli()


if __name__ == "__main__":
    main()
