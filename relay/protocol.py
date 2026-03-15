"""
relay.protocol — shared wire protocol (JSON over WebSocket).

Every message is a JSON object with a "type" field.

Client → Relay:
  AUTH          {type, client_id, token}
  REQUEST_CERT  {type, agent_name}
  OPEN_TUNNEL   {type, agent_name, cert}
  DEPLOY        {type, agent_name, cert, filename, size, chunk_index, total_chunks, data_b64}
  EXEC          {type, agent_name, cert, command}
  LIST_AGENTS   {type}
  PING          {type}

Relay → Client:
  AUTH_OK       {type, client_id}
  AUTH_FAIL     {type, reason}
  CERT_ISSUED   {type, cert}
  TUNNEL_READY  {type, session_id, agent_name}
  TUNNEL_FAIL   {type, reason}
  AGENT_LIST    {type, agents: [{name, connected_at, tags}]}
  DEPLOY_ACK    {type, chunk_index}
  DEPLOY_DONE   {type, path, bytes_written}
  EXEC_OUTPUT   {type, stdout, stderr, exit_code}
  ERROR         {type, code, reason}
  PONG          {type}

Agent → Relay:
  AGENT_HELLO   {type, agent_name, tags, version}
  AGENT_READY   {type, session_id}
  AGENT_BYE     {type, agent_name}
  HEARTBEAT     {type, agent_name, load, uptime}

Relay → Agent:
  ROUTE         {type, session_id, client_id, cert}
  DEPLOY_CHUNK  {type, session_id, filename, chunk_index, total_chunks, data_b64}
  EXEC_CMD      {type, session_id, command}
  DISCONNECT    {type, session_id, reason}
"""

import json
import time
from enum import Enum
from typing import Any, Dict, Optional


class MsgType(str, Enum):
    # Client → Relay
    AUTH = "AUTH"
    REQUEST_CERT = "REQUEST_CERT"
    OPEN_TUNNEL = "OPEN_TUNNEL"
    DEPLOY = "DEPLOY"
    EXEC = "EXEC"
    LIST_AGENTS = "LIST_AGENTS"
    PING = "PING"

    # Relay → Client
    AUTH_OK = "AUTH_OK"
    AUTH_FAIL = "AUTH_FAIL"
    CERT_ISSUED = "CERT_ISSUED"
    TUNNEL_READY = "TUNNEL_READY"
    TUNNEL_FAIL = "TUNNEL_FAIL"
    AGENT_LIST = "AGENT_LIST"
    DEPLOY_ACK = "DEPLOY_ACK"
    DEPLOY_DONE = "DEPLOY_DONE"
    EXEC_OUTPUT = "EXEC_OUTPUT"
    ERROR = "ERROR"
    PONG = "PONG"

    # Agent → Relay
    AGENT_HELLO = "AGENT_HELLO"
    AGENT_READY = "AGENT_READY"
    AGENT_BYE = "AGENT_BYE"
    HEARTBEAT = "HEARTBEAT"

    # Relay → Agent
    ROUTE = "ROUTE"
    DEPLOY_CHUNK = "DEPLOY_CHUNK"
    EXEC_CMD = "EXEC_CMD"
    DISCONNECT = "DISCONNECT"


def make(msg_type: MsgType, **kwargs) -> str:
    """Serialise a protocol message to JSON string."""
    payload: Dict[str, Any] = {"type": msg_type.value, "ts": time.time()}
    payload.update(kwargs)
    return json.dumps(payload)


def parse(raw: str) -> Dict[str, Any]:
    """Deserialise a protocol message from JSON string."""
    return json.loads(raw)


def msg_type(msg: Dict[str, Any]) -> MsgType:
    return MsgType(msg["type"])


# ---------------------------------------------------------------------------
# Convenience constructors
# ---------------------------------------------------------------------------

def auth(client_id: str, token: str = "") -> str:
    return make(MsgType.AUTH, client_id=client_id, token=token)


def auth_ok(client_id: str) -> str:
    return make(MsgType.AUTH_OK, client_id=client_id)


def auth_fail(reason: str) -> str:
    return make(MsgType.AUTH_FAIL, reason=reason)


def request_cert(agent_name: str) -> str:
    return make(MsgType.REQUEST_CERT, agent_name=agent_name)


def cert_issued(cert_dict: dict) -> str:
    return make(MsgType.CERT_ISSUED, cert=cert_dict)


def open_tunnel(agent_name: str, cert_dict: dict) -> str:
    return make(MsgType.OPEN_TUNNEL, agent_name=agent_name, cert=cert_dict)


def tunnel_ready(session_id: str, agent_name: str) -> str:
    return make(MsgType.TUNNEL_READY, session_id=session_id, agent_name=agent_name)


def tunnel_fail(reason: str) -> str:
    return make(MsgType.TUNNEL_FAIL, reason=reason)


def agent_hello(agent_name: str, tags: list, version: str = "0.1.0") -> str:
    return make(MsgType.AGENT_HELLO, agent_name=agent_name, tags=tags, version=version)


def agent_ready(session_id: str) -> str:
    return make(MsgType.AGENT_READY, session_id=session_id)


def heartbeat(agent_name: str, load: float = 0.0, uptime: float = 0.0) -> str:
    return make(MsgType.HEARTBEAT, agent_name=agent_name, load=load, uptime=uptime)


def route(session_id: str, client_id: str, cert_dict: dict) -> str:
    return make(MsgType.ROUTE, session_id=session_id, client_id=client_id, cert=cert_dict)


def exec_cmd(session_id: str, command: str) -> str:
    return make(MsgType.EXEC_CMD, session_id=session_id, command=command)


def exec_output(stdout: str, stderr: str, exit_code: int) -> str:
    return make(MsgType.EXEC_OUTPUT, stdout=stdout, stderr=stderr, exit_code=exit_code)


def error(code: str, reason: str) -> str:
    return make(MsgType.ERROR, code=code, reason=reason)


def ping() -> str:
    return make(MsgType.PING)


def pong() -> str:
    return make(MsgType.PONG)


def list_agents() -> str:
    return make(MsgType.LIST_AGENTS)


def agent_list(agents: list) -> str:
    return make(MsgType.AGENT_LIST, agents=agents)
