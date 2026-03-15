"""
relay.config — configuration management.

Config lives at ~/.relay/config.json
Each named "server" entry stores:
  - name        : human alias  (e.g. "prod-1")
  - relay_url   : ws://...  or  wss://...
  - agent_name  : must match what the agent registered with
  - client_id   : your identity token / API key
  - deploy_path : default remote deploy path
  - post_deploy : shell command to run after deploy (e.g. "systemctl restart myapp")
  - ssh_user    : remote user for SSH sessions (default: current user)
  - tags        : list of arbitrary labels
"""

import json
import os
import tempfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

from relay.exceptions import ConfigError


_default_config_root = Path(os.environ.get("APPDATA", "")) if os.name == "nt" else None
CONFIG_DIR = (_default_config_root / "relay" if _default_config_root else Path.home() / ".relay")
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_RELAY_URL = "ws://localhost:8765"
DEFAULT_DEPLOY_PATH = str(Path(tempfile.gettempdir()) / "relay-deploy")


@dataclass
class ServerProfile:
    name: str
    relay_url: str = DEFAULT_RELAY_URL
    agent_name: str = ""          # auto-set to name if empty
    client_id: str = ""
    deploy_path: str = DEFAULT_DEPLOY_PATH
    post_deploy: str = ""
    ssh_user: str = ""
    tags: List[str] = field(default_factory=list)
    description: str = ""

    def __post_init__(self):
        if not self.agent_name:
            self.agent_name = self.name
        if not self.ssh_user:
            self.ssh_user = os.environ.get("USER", "relay")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ServerProfile":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class RelayConfig:
    servers: Dict[str, ServerProfile] = field(default_factory=dict)
    default_relay_url: str = DEFAULT_RELAY_URL
    client_id: str = ""
    log_level: str = "INFO"
    cert_ttl: int = 900            # seconds
    connect_timeout: int = 10      # seconds
    transfer_chunk: int = 65536    # bytes

    def to_dict(self) -> dict:
        return {
            "servers": {k: v.to_dict() for k, v in self.servers.items()},
            "default_relay_url": self.default_relay_url,
            "client_id": self.client_id,
            "log_level": self.log_level,
            "cert_ttl": self.cert_ttl,
            "connect_timeout": self.connect_timeout,
            "transfer_chunk": self.transfer_chunk,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RelayConfig":
        servers = {
            k: ServerProfile.from_dict(v)
            for k, v in d.get("servers", {}).items()
        }
        return cls(
            servers=servers,
            default_relay_url=d.get("default_relay_url", DEFAULT_RELAY_URL),
            client_id=d.get("client_id", ""),
            log_level=d.get("log_level", "INFO"),
            cert_ttl=d.get("cert_ttl", 900),
            connect_timeout=d.get("connect_timeout", 10),
            transfer_chunk=d.get("transfer_chunk", 65536),
        )


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------

def load_config() -> RelayConfig:
    if not CONFIG_FILE.exists():
        return RelayConfig()
    try:
        data = json.loads(CONFIG_FILE.read_text())
        return RelayConfig.from_dict(data)
    except Exception as exc:
        raise ConfigError(f"Cannot parse config at {CONFIG_FILE}: {exc}") from exc


def save_config(cfg: RelayConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg.to_dict(), indent=2))
    CONFIG_FILE.chmod(0o600)


def get_server(name: str) -> ServerProfile:
    cfg = load_config()
    if name not in cfg.servers:
        raise ConfigError(
            f"Server '{name}' not found. Run: relay add {name}  to register it."
        )
    return cfg.servers[name]


def add_server(profile: ServerProfile) -> None:
    cfg = load_config()
    cfg.servers[profile.name] = profile
    save_config(cfg)


def remove_server(name: str) -> None:
    cfg = load_config()
    if name not in cfg.servers:
        raise ConfigError(f"Server '{name}' not found.")
    del cfg.servers[name]
    save_config(cfg)


def list_servers() -> List[ServerProfile]:
    cfg = load_config()
    return list(cfg.servers.values())


def init_config(relay_url: str = DEFAULT_RELAY_URL, client_id: str = "") -> RelayConfig:
    """Create a fresh config file with defaults."""
    cfg = RelayConfig(
        default_relay_url=relay_url,
        client_id=client_id or _generate_client_id(),
    )
    save_config(cfg)
    return cfg


def _generate_client_id() -> str:
    import secrets
    return "client-" + secrets.token_urlsafe(12)
