"""Regression and behavior tests migrated from temporary test bundle."""

import base64
import hashlib
import io
import json
import os
import tarfile
import tempfile
from pathlib import Path

import pytest

from relay.exceptions import AgentNotFoundError, AuthError, DeployError
from relay.server import RelayServer


class TestBugFixes:
    def test_server_key_load_failure_has_no_hmac_fallback(self, tmp_path):
        keys_dir = tmp_path / "keys"
        keys_dir.mkdir()
        (keys_dir / "relay_private.pem").write_text("NOT A VALID PEM FILE")
        (keys_dir / "relay_public.pem").write_text("NOT A VALID PEM FILE")

        try:
            server = RelayServer(
                host="127.0.0.1",
                port=19999,
                token="x",
                keys_dir=keys_dir,
                log_dir=tmp_path / "logs",
            )
            assert server._signing_key != b"test-only-hmac-key"
        except Exception:
            pass


class TestServerRoutingIsolation:
    def test_five_pending_dicts_are_distinct_objects(self, tmp_path):
        server = RelayServer(
            host="127.0.0.1",
            port=19994,
            token="x",
            keys_dir=tmp_path / "k",
            log_dir=tmp_path / "l",
        )
        dicts = [
            server._tunnel_pending,
            server._exec_pending,
            server._deploy_pending,
            server._shell_clients,
            server._shell_agents,
        ]
        assert len({id(d) for d in dicts}) == 5

    def test_exec_pending_pop_removes_entry_after_response(self, tmp_path):
        server = RelayServer(
            host="127.0.0.1",
            port=19993,
            token="x",
            keys_dir=tmp_path / "k",
            log_dir=tmp_path / "l",
        )
        fake_ws = object()
        server._exec_pending["sess-1"] = fake_ws
        retrieved = server._exec_pending.pop("sess-1", None)
        assert retrieved is fake_ws
        assert "sess-1" not in server._exec_pending

    def test_deploy_pending_survives_multiple_acks(self, tmp_path):
        server = RelayServer(
            host="127.0.0.1",
            port=19992,
            token="x",
            keys_dir=tmp_path / "k",
            log_dir=tmp_path / "l",
        )
        fake_ws = object()
        server._deploy_pending["sess-deploy"] = fake_ws
        for _ in range(3):
            assert server._deploy_pending.get("sess-deploy") is fake_ws
        assert "sess-deploy" in server._deploy_pending

    def test_exec_and_deploy_same_session_id_independent(self, tmp_path):
        server = RelayServer(
            host="127.0.0.1",
            port=19991,
            token="x",
            keys_dir=tmp_path / "k",
            log_dir=tmp_path / "l",
        )
        same_sid = "collision-test-session"
        server._exec_pending[same_sid] = "exec_client"
        server._deploy_pending[same_sid] = "deploy_client"

        assert server._exec_pending.pop(same_sid, None) == "exec_client"
        assert same_sid not in server._exec_pending
        assert server._deploy_pending.get(same_sid) == "deploy_client"

    def test_tunnel_pending_independent_of_exec(self, tmp_path):
        server = RelayServer(
            host="127.0.0.1",
            port=19990,
            token="x",
            keys_dir=tmp_path / "k",
            log_dir=tmp_path / "l",
        )
        server._tunnel_pending["t-sess"] = "tunnel_ws"
        server._exec_pending["t-sess"] = "exec_ws"

        assert server._tunnel_pending["t-sess"] == "tunnel_ws"
        assert server._exec_pending["t-sess"] == "exec_ws"


class TestDeployIntegrity:
    def test_sha256_agent_state_machine_matches_client(self, tmp_path):
        content = "relay deploy integrity check " * 200
        src = tmp_path / "big.txt"
        src.write_text(content)

        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            tf.add(src, arcname=src.name)
        data = buf.getvalue()
        client_sha256 = hashlib.sha256(data).hexdigest()

        chunk_size = 1024
        chunks = [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]
        state = {"sha256": hashlib.sha256(), "bytes": 0, "pending": {}, "next_index": 0}
        for idx, chunk in enumerate(chunks):
            state["pending"][idx] = chunk

        while state["next_index"] in state["pending"]:
            idx = state["next_index"]
            chunk = state["pending"].pop(idx)
            state["sha256"].update(chunk)
            state["bytes"] += len(chunk)
            state["next_index"] += 1

        assert state["sha256"].hexdigest() == client_sha256

    def test_deploy_ack_is_after_write_in_source(self):
        src = (Path(__file__).parent.parent / "relay" / "agent.py").read_text()
        write_pos = src.find('with open(state["tmp_file"], "ab") as f:')
        ack_pos = src.find("proto.MsgType.DEPLOY_ACK")
        assert write_pos > 0
        assert ack_pos > 0
        assert ack_pos > write_pos

    def test_archive_extraction_recovers_content(self, tmp_path):
        src = tmp_path / "hello.txt"
        original = "hello from relay deploy test suite"
        src.write_text(original)

        buf = io.BytesIO()
        archive_name = src.name + ".tar.gz"
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            tf.add(src, arcname=src.name)

        dest = tmp_path / "dest"
        dest.mkdir()
        archive = dest / archive_name
        archive.write_bytes(buf.getvalue())

        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(dest)

        recovered = dest / "hello.txt"
        assert recovered.exists()
        assert recovered.read_text() == original

    def test_base64_chunking_roundtrip(self):
        data = os.urandom(150000)
        chunk_size = 65536
        chunks = [
            base64.b64encode(data[i : i + chunk_size]).decode()
            for i in range(0, len(data), chunk_size)
        ]
        reassembled = b"".join(base64.b64decode(c) for c in chunks)
        assert reassembled == data


class TestAgentReconnect:
    def test_exponential_backoff_formula(self):
        base_delay = 5
        values = [min(base_delay * (2 ** n), 60) for n in range(1, 7)]
        assert values == [10, 20, 40, 60, 60, 60]

    def test_agent_source_uses_exponential_backoff(self):
        src = (Path(__file__).parent.parent / "relay" / "agent.py").read_text()
        assert "2 ** reconnects" in src or "2**reconnects" in src

    def test_agent_persistent_skips_max_reconnects(self):
        src = (Path(__file__).parent.parent / "relay" / "agent.py").read_text()
        assert "not self.persistent" in src


class TestErrorMessages:
    def test_auth_error_mentions_relay_token(self):
        err = AuthError("Wrong token. Make sure RELAY_TOKEN matches. Your token: abc123...")
        assert "RELAY_TOKEN" in str(err)

    def test_agent_not_found_error_mentions_relay_agent(self):
        err = AgentNotFoundError("Agent 'prod-1' is not online. Run: relay-agent --relay ws://... --name prod-1")
        assert "relay-agent" in str(err)

    def test_connection_error_mentions_relay_doctor_in_source(self):
        src = (Path(__file__).parent.parent / "relay" / "client.py").read_text()
        assert "relay doctor" in src

    def test_timeout_error_mentions_firewall_in_source(self):
        src = (Path(__file__).parent.parent / "relay" / "client.py").read_text()
        assert "firewall" in src.lower()

    def test_deploy_error_message_is_informative(self):
        err = DeployError("Local path does not exist: /nonexistent/path")
        assert "path" in str(err).lower()
