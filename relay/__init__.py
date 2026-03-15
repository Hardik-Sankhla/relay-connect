"""
relay-connect — dead-simple, secure remote connection and deploy tool.

Architecture:
  relay server  — mediator / broker (you host this, or use relay.sh hosted)
  relay agent   — tiny daemon on each remote server (dials outbound, no open ports)
  relay client  — CLI + Python SDK on your laptop / CI

Quick start:
  pip install relay-connect
  relay server start                    # run mediator locally for testing
  relay agent start --relay ws://localhost:8765 --name prod-1
  relay deploy ./dist prod-1            # push files
  relay ssh prod-1                      # interactive shell
"""

__version__ = "0.1.0"
__author__ = "relay-connect contributors"
__license__ = "Apache-2.0"

from relay.client import RelayClient
from relay.exceptions import (
    RelayError,
    AuthError,
    AgentNotFoundError,
    TunnelError,
    CertExpiredError,
)

__all__ = [
    "RelayClient",
    "RelayError",
    "AuthError",
    "AgentNotFoundError",
    "TunnelError",
    "CertExpiredError",
]
