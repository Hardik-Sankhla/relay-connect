"""Tests for relay.protocol — message construction and parsing."""

import json
import pytest
from relay import protocol as proto
from relay.protocol import MsgType


class TestProtocolSerialization:
    def test_make_includes_type(self):
        raw = proto.make(MsgType.PING)
        msg = json.loads(raw)
        assert msg["type"] == "PING"

    def test_make_includes_timestamp(self):
        import time
        before = time.time()
        raw = proto.make(MsgType.PING)
        after = time.time()
        msg = json.loads(raw)
        assert before <= msg["ts"] <= after

    def test_make_includes_kwargs(self):
        raw = proto.make(MsgType.AUTH, client_id="abc", token="tok")
        msg = json.loads(raw)
        assert msg["client_id"] == "abc"
        assert msg["token"] == "tok"

    def test_parse_round_trip(self):
        raw = proto.make(MsgType.AUTH, client_id="test")
        msg = proto.parse(raw)
        assert msg["type"] == "AUTH"
        assert msg["client_id"] == "test"

    def test_msg_type_helper(self):
        raw = proto.make(MsgType.AUTH_OK, client_id="x")
        msg = proto.parse(raw)
        assert proto.msg_type(msg) == MsgType.AUTH_OK

    def test_invalid_type_raises(self):
        raw = json.dumps({"type": "NOT_A_REAL_TYPE"})
        msg = proto.parse(raw)
        with pytest.raises(ValueError):
            proto.msg_type(msg)


class TestConvenienceConstructors:
    def _msg(self, raw: str) -> dict:
        return proto.parse(raw)

    def test_auth(self):
        msg = self._msg(proto.auth("client-1", "secret"))
        assert msg["type"] == "AUTH"
        assert msg["client_id"] == "client-1"
        assert msg["token"] == "secret"

    def test_auth_ok(self):
        msg = self._msg(proto.auth_ok("client-1"))
        assert msg["type"] == "AUTH_OK"
        assert msg["client_id"] == "client-1"

    def test_auth_fail(self):
        msg = self._msg(proto.auth_fail("bad token"))
        assert msg["type"] == "AUTH_FAIL"
        assert msg["reason"] == "bad token"

    def test_agent_hello(self):
        msg = self._msg(proto.agent_hello("prod-1", ["web", "prod"], "0.1.0"))
        assert msg["type"] == "AGENT_HELLO"
        assert msg["agent_name"] == "prod-1"
        assert "web" in msg["tags"]

    def test_heartbeat(self):
        msg = self._msg(proto.heartbeat("prod-1", load=1.5, uptime=3600.0))
        assert msg["type"] == "HEARTBEAT"
        assert msg["load"] == 1.5

    def test_tunnel_ready(self):
        msg = self._msg(proto.tunnel_ready("sess-abc", "prod-1"))
        assert msg["type"] == "TUNNEL_READY"
        assert msg["session_id"] == "sess-abc"
        assert msg["agent_name"] == "prod-1"

    def test_tunnel_fail(self):
        msg = self._msg(proto.tunnel_fail("agent offline"))
        assert msg["type"] == "TUNNEL_FAIL"
        assert "agent offline" in msg["reason"]

    def test_error(self):
        msg = self._msg(proto.error("AGENT_NOT_FOUND", "no agent"))
        assert msg["type"] == "ERROR"
        assert msg["code"] == "AGENT_NOT_FOUND"

    def test_ping_pong(self):
        assert proto.parse(proto.ping())["type"] == "PING"
        assert proto.parse(proto.pong())["type"] == "PONG"

    def test_list_agents(self):
        assert proto.parse(proto.list_agents())["type"] == "LIST_AGENTS"

    def test_agent_list(self):
        agents = [{"name": "prod-1", "tags": []}]
        msg = proto.parse(proto.agent_list(agents))
        assert msg["type"] == "AGENT_LIST"
        assert msg["agents"][0]["name"] == "prod-1"

    def test_exec_cmd(self):
        msg = self._msg(proto.exec_cmd("sess-1", "uptime"))
        assert msg["type"] == "EXEC_CMD"
        assert msg["command"] == "uptime"

    def test_exec_output(self):
        msg = self._msg(proto.exec_output("hello", "warn", 0))
        assert msg["type"] == "EXEC_OUTPUT"
        assert msg["stdout"] == "hello"
        assert msg["exit_code"] == 0
