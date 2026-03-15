"""Tests for relay.config — profile management."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from relay.config import (
    DEFAULT_DEPLOY_PATH,
    RelayConfig,
    ServerProfile,
    add_server,
    get_server,
    init_config,
    list_servers,
    load_config,
    remove_server,
    save_config,
)
from relay.exceptions import ConfigError


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Redirect config to a temp directory."""
    import relay.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cfg_mod, "CONFIG_FILE", tmp_path / "config.json")
    return tmp_path


class TestServerProfile:
    def test_defaults(self):
        p = ServerProfile(name="prod-1")
        assert p.agent_name == "prod-1"
        assert p.deploy_path == DEFAULT_DEPLOY_PATH
        assert isinstance(p.tags, list)

    def test_default_deploy_path_uses_tempdir(self):
        expected = str(Path(tempfile.gettempdir()) / "relay-deploy")
        assert DEFAULT_DEPLOY_PATH == expected

    def test_to_dict_round_trip(self):
        p = ServerProfile(name="srv", tags=["web"], description="test server")
        d = p.to_dict()
        p2 = ServerProfile.from_dict(d)
        assert p2.name == "srv"
        assert p2.tags == ["web"]

    def test_agent_name_defaults_to_name(self):
        p = ServerProfile(name="staging")
        assert p.agent_name == "staging"

    def test_custom_agent_name(self):
        p = ServerProfile(name="my-server", agent_name="custom-agent")
        assert p.agent_name == "custom-agent"


class TestRelayConfig:
    def test_empty_config(self):
        cfg = RelayConfig()
        assert cfg.servers == {}

    def test_to_dict_round_trip(self):
        cfg = RelayConfig(
            default_relay_url="ws://relay.example.com:8765",
            client_id="client-xyz",
            cert_ttl=600,
        )
        d = cfg.to_dict()
        cfg2 = RelayConfig.from_dict(d)
        assert cfg2.default_relay_url == "ws://relay.example.com:8765"
        assert cfg2.client_id == "client-xyz"
        assert cfg2.cert_ttl == 600

    def test_servers_in_dict(self):
        cfg = RelayConfig()
        cfg.servers["prod-1"] = ServerProfile(name="prod-1")
        d = cfg.to_dict()
        cfg2 = RelayConfig.from_dict(d)
        assert "prod-1" in cfg2.servers


class TestConfigIO:
    def test_load_nonexistent_returns_defaults(self, tmp_config):
        cfg = load_config()
        assert cfg.servers == {}

    def test_save_and_load(self, tmp_config):
        cfg = RelayConfig(client_id="test-client")
        save_config(cfg)
        loaded = load_config()
        assert loaded.client_id == "test-client"

    def test_config_file_has_restricted_perms(self, tmp_config):
        cfg = RelayConfig(client_id="x")
        save_config(cfg)
        import relay.config as cfg_mod
        mode = cfg_mod.CONFIG_FILE.stat().st_mode & 0o777
        if os.name == "nt":
            assert mode & 0o200
        else:
            assert mode == 0o600

    def test_add_and_get_server(self, tmp_config):
        profile = ServerProfile(name="staging")
        add_server(profile)
        retrieved = get_server("staging")
        assert retrieved.name == "staging"

    def test_get_unknown_server_raises(self, tmp_config):
        with pytest.raises(ConfigError):
            get_server("nonexistent")

    def test_remove_server(self, tmp_config):
        add_server(ServerProfile(name="test-srv"))
        remove_server("test-srv")
        with pytest.raises(ConfigError):
            get_server("test-srv")

    def test_remove_nonexistent_raises(self, tmp_config):
        with pytest.raises(ConfigError):
            remove_server("nope")

    def test_list_servers_empty(self, tmp_config):
        assert list_servers() == []

    def test_list_servers_populated(self, tmp_config):
        add_server(ServerProfile(name="a"))
        add_server(ServerProfile(name="b"))
        names = [s.name for s in list_servers()]
        assert "a" in names
        assert "b" in names

    def test_init_config_creates_client_id(self, tmp_config):
        cfg = init_config()
        assert cfg.client_id.startswith("client-")

    def test_invalid_json_raises_config_error(self, tmp_config):
        import relay.config as cfg_mod
        cfg_mod.CONFIG_FILE.write_text("not valid json {{")
        with pytest.raises(ConfigError):
            load_config()
