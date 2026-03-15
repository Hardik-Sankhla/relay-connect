"""Tests for relay.crypto — cert issuance, verification, expiry."""

import time
import pytest

# Skip if cryptography not installed but still test fallback path
try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    CRYPTO_OK = True
except ImportError:
    CRYPTO_OK = False

from relay.crypto import SessionCert


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_test_key():
    """Return a signing key for tests — real Ed25519 or bytes fallback."""
    if CRYPTO_OK:
        return Ed25519PrivateKey.generate()
    return b"test-fallback-key-32-bytes-padded"


# ---------------------------------------------------------------------------
# SessionCert
# ---------------------------------------------------------------------------

class TestSessionCert:
    def test_issue_creates_cert(self):
        key = make_test_key()
        cert = SessionCert.issue(
            agent_name="prod-1",
            client_id="dev-client",
            signing_key=key,
        )
        assert cert.agent_name == "prod-1"
        assert cert.client_id == "dev-client"
        assert cert.session_id != ""
        assert cert.signature != ""

    def test_is_valid_within_ttl(self):
        key = make_test_key()
        cert = SessionCert.issue("srv", "cli", key)
        assert cert.is_valid()

    def test_is_expired_past_ttl(self):
        key = make_test_key()
        cert = SessionCert.issue("srv", "cli", key, ttl=0)
        time.sleep(0.01)
        assert not cert.is_valid()

    def test_time_remaining_positive(self):
        key = make_test_key()
        cert = SessionCert.issue("srv", "cli", key, ttl=900)
        rem = cert.time_remaining()
        assert rem > 890  # just issued, should have nearly full TTL

    def test_time_remaining_zero_after_expiry(self):
        key = make_test_key()
        cert = SessionCert.issue("srv", "cli", key, ttl=0)
        time.sleep(0.01)
        assert cert.time_remaining() == 0.0

    def test_to_dict_and_from_dict(self):
        key = make_test_key()
        cert = SessionCert.issue("srv", "cli", key)
        d = cert.to_dict()
        cert2 = SessionCert.from_dict(d)
        assert cert2.session_id == cert.session_id
        assert cert2.agent_name == cert.agent_name
        assert cert2.signature == cert.signature

    def test_payload_is_deterministic(self):
        key = make_test_key()
        cert = SessionCert.issue("srv", "cli", key)
        p1 = cert._payload_bytes()
        p2 = cert._payload_bytes()
        assert p1 == p2

    @pytest.mark.skipif(not CRYPTO_OK, reason="cryptography not installed")
    def test_verify_valid_cert(self):
        key = Ed25519PrivateKey.generate()
        pub = key.public_key()
        cert = SessionCert.issue("srv", "cli", key)
        assert cert.verify(pub)

    @pytest.mark.skipif(not CRYPTO_OK, reason="cryptography not installed")
    def test_verify_tampered_cert_fails(self):
        key = Ed25519PrivateKey.generate()
        pub = key.public_key()
        cert = SessionCert.issue("srv", "cli", key)
        # tamper with agent name
        cert.agent_name = "evil-server"
        assert not cert.verify(pub)

    @pytest.mark.skipif(not CRYPTO_OK, reason="cryptography not installed")
    def test_verify_wrong_key_fails(self):
        key1 = Ed25519PrivateKey.generate()
        key2 = Ed25519PrivateKey.generate()
        cert = SessionCert.issue("srv", "cli", key1)
        assert not cert.verify(key2.public_key())

    @pytest.mark.skipif(not CRYPTO_OK, reason="cryptography not installed")
    def test_verify_expired_cert_fails(self):
        key = Ed25519PrivateKey.generate()
        pub = key.public_key()
        cert = SessionCert.issue("srv", "cli", key, ttl=0)
        time.sleep(0.01)
        assert not cert.verify(pub)

    def test_default_ttl_is_15_minutes(self):
        assert SessionCert.TTL_SECONDS == 900

    def test_unique_session_ids(self):
        key = make_test_key()
        ids = {SessionCert.issue("srv", "cli", key).session_id for _ in range(20)}
        assert len(ids) == 20  # all unique
