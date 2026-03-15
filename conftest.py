"""pytest configuration for relay-connect tests."""

import asyncio
import sys
from pathlib import Path

import pytest

# Ensure relay package is importable from the repo root
sys.path.insert(0, str(Path(__file__).parent))


# ---------------------------------------------------------------------------
# asyncio mode configuration
# ---------------------------------------------------------------------------

# pytest-asyncio 0.23+ requires explicit asyncio_mode setting.
# Set in pyproject.toml: asyncio_mode = "auto"
# This conftest also handles the event loop policy for Python 3.12+


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default event loop policy."""
    return asyncio.DefaultEventLoopPolicy()


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def relay_token():
    return "test-token-12345"


@pytest.fixture
def client_id():
    return "test-client"


@pytest.fixture
def agent_name():
    return "test-agent"
