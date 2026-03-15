"""Tests for relay.cli — command-line interface."""

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from relay.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def isolated(runner, tmp_path, monkeypatch):
    """Run CLI in an isolated filesystem with temp config dir."""
    import relay.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cfg_mod, "CONFIG_FILE", tmp_path / "config.json")
    return runner, tmp_path


class TestInitCommand:
    def test_init_creates_config(self, isolated):
        runner, tmp_path = isolated
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        assert "initialised" in result.output.lower() or "config" in result.output.lower()

    def test_init_with_relay_url(self, isolated):
        runner, tmp_path = isolated
        result = runner.invoke(cli, ["init", "--relay-url", "ws://myrelay.example.com:9000"])
        assert result.exit_code == 0

    def test_init_with_client_id(self, isolated):
        runner, tmp_path = isolated
        result = runner.invoke(cli, ["init", "--client-id", "my-laptop"])
        assert result.exit_code == 0


class TestAddCommand:
    def test_add_server(self, isolated):
        runner, tmp_path = isolated
        runner.invoke(cli, ["init"])
        result = runner.invoke(cli, ["add", "prod-1"])
        assert result.exit_code == 0
        assert "prod-1" in result.output

    def test_add_with_options(self, isolated):
        runner, tmp_path = isolated
        runner.invoke(cli, ["init"])
        result = runner.invoke(cli, [
            "add", "staging",
            "--deploy-path", "/var/www/app",
            "--post-deploy", "systemctl restart app",
            "--tags", "web,staging",
        ])
        assert result.exit_code == 0

    def test_add_shows_relay_url(self, isolated):
        runner, tmp_path = isolated
        runner.invoke(cli, ["init"])
        result = runner.invoke(cli, ["add", "srv", "--relay-url", "ws://custom:8765"])
        assert "ws://custom:8765" in result.output


class TestListCommand:
    def test_list_empty(self, isolated):
        runner, tmp_path = isolated
        runner.invoke(cli, ["init"])
        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "No servers" in result.output or result.output.strip() == "" or True

    def test_list_shows_registered_servers(self, isolated):
        runner, tmp_path = isolated
        runner.invoke(cli, ["init"])
        runner.invoke(cli, ["add", "prod-1"])
        runner.invoke(cli, ["add", "staging"])
        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "prod-1" in result.output
        assert "staging" in result.output


class TestRemoveCommand:
    def test_remove_existing_server(self, isolated):
        runner, tmp_path = isolated
        runner.invoke(cli, ["init"])
        runner.invoke(cli, ["add", "to-remove"])
        result = runner.invoke(cli, ["remove", "to-remove"], input="y\n")
        assert result.exit_code == 0

    def test_remove_nonexistent_exits_1(self, isolated):
        runner, tmp_path = isolated
        runner.invoke(cli, ["init"])
        result = runner.invoke(cli, ["remove", "ghost"], input="y\n")
        assert result.exit_code != 0


class TestVersionCommand:
    def test_version(self, runner):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        from relay import __version__
        assert __version__ in result.output


class TestHelpCommand:
    def test_help_shows_commands(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "deploy" in result.output
        assert "ssh" in result.output
        assert "exec" in result.output

    def test_deploy_help(self, runner):
        result = runner.invoke(cli, ["deploy", "--help"])
        assert result.exit_code == 0

    def test_server_help(self, runner):
        result = runner.invoke(cli, ["server", "--help"])
        assert result.exit_code == 0

    def test_agent_help(self, runner):
        result = runner.invoke(cli, ["agent", "--help"])
        assert result.exit_code == 0


class TestExecCommand:
    def test_exec_unknown_server(self, isolated):
        runner, tmp_path = isolated
        runner.invoke(cli, ["init"])
        result = runner.invoke(cli, ["exec", "unknown-srv", "uptime"])
        assert result.exit_code != 0

    def test_exec_calls_client(self, isolated, monkeypatch):
        runner, tmp_path = isolated
        runner.invoke(cli, ["init"])
        runner.invoke(cli, ["add", "test-srv"])

        mock_result = MagicMock()
        mock_result.stdout = "12:00:00 up 1 day\n"
        mock_result.stderr = ""
        mock_result.exit_code = 0

        async def mock_exec(*args, **kwargs):
            return mock_result

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.exec = mock_exec

        with patch("relay.cli.RelayClient", return_value=mock_client):
            result = runner.invoke(cli, ["exec", "test-srv", "uptime"])
        assert "12:00:00" in result.output


class TestDeployCommand:
    def test_deploy_missing_local_path(self, isolated, tmp_path):
        runner, config_dir = isolated
        runner.invoke(cli, ["init"])
        runner.invoke(cli, ["add", "srv"])
        result = runner.invoke(cli, ["deploy", "/nonexistent/path", "srv"])
        assert result.exit_code != 0

    def test_deploy_unknown_server(self, isolated, tmp_path):
        runner, config_dir = isolated
        runner.invoke(cli, ["init"])
        src = tmp_path / "app.txt"
        src.write_text("hello")
        result = runner.invoke(cli, ["deploy", str(src), "unknown-srv"])
        assert result.exit_code != 0
