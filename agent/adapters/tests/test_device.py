#
# VoiceClaw — agent/adapters/tests/test_device.py
# SPDX-License-Identifier: MIT
#

"""Tests for device identity and payload signing.

Verifies that our Python implementation produces values compatible with
the TypeScript reference in agent/upstream/openclaw/src/infra/device-identity.ts
and agent/upstream/openclaw/src/gateway/device-auth.ts.
"""

import base64
import hashlib
import json
import tempfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from adapters.device import (
    DeviceIdentity,
    build_auth_payload_v3,
    load_or_create_identity,
    public_key_base64url,
    sign_payload,
)


def _b64url_decode(s: str) -> bytes:
    padded = s + "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode(padded.replace("-", "+").replace("_", "/"))


# ---------------------------------------------------------------------------
# Identity generation and persistence
# ---------------------------------------------------------------------------


def test_load_or_create_generates_new_identity(tmp_path):
    identity_path = tmp_path / "device.json"
    identity = load_or_create_identity(path=identity_path)

    assert len(identity.device_id) == 64, "device_id should be 64-char hex"
    assert identity.public_key_pem.startswith("-----BEGIN PUBLIC KEY-----")
    assert identity.private_key_pem.startswith("-----BEGIN PRIVATE KEY-----")
    assert identity_path.exists()
    assert oct(identity_path.stat().st_mode)[-3:] == "600"


def test_load_or_create_is_idempotent(tmp_path):
    path = tmp_path / "device.json"
    first = load_or_create_identity(path=path)
    second = load_or_create_identity(path=path)

    assert first.device_id == second.device_id
    assert first.public_key_pem == second.public_key_pem


def test_stored_json_structure(tmp_path):
    path = tmp_path / "device.json"
    identity = load_or_create_identity(path=path)
    data = json.loads(path.read_text())

    assert data["version"] == 1
    assert data["deviceId"] == identity.device_id
    assert "createdAtMs" in data


# ---------------------------------------------------------------------------
# Public key encoding
# ---------------------------------------------------------------------------


def test_public_key_base64url_is_32_bytes(tmp_path):
    identity = load_or_create_identity(path=tmp_path / "d.json")
    b64 = public_key_base64url(identity)
    raw = _b64url_decode(b64)
    assert len(raw) == 32, "Ed25519 raw public key must be 32 bytes"


def test_device_id_matches_sha256_of_raw_public_key(tmp_path):
    identity = load_or_create_identity(path=tmp_path / "d.json")
    b64 = public_key_base64url(identity)
    raw = _b64url_decode(b64)
    expected_id = hashlib.sha256(raw).hexdigest()
    assert identity.device_id == expected_id


def test_public_key_base64url_no_padding(tmp_path):
    identity = load_or_create_identity(path=tmp_path / "d.json")
    b64 = public_key_base64url(identity)
    assert "=" not in b64, "base64url should have no padding"


# ---------------------------------------------------------------------------
# Signature payload construction
# ---------------------------------------------------------------------------


def test_build_auth_payload_v3_format():
    payload = build_auth_payload_v3(
        device_id="abc",
        client_id="voiceclaw",
        client_mode="operator",
        role="operator",
        scopes=["operator.read", "operator.write"],
        signed_at_ms=1700000000000,
        token="mytoken",
        nonce="testnonce",
        platform="linux",
        device_family="",
    )
    assert payload == "v3|abc|voiceclaw|operator|operator|operator.read,operator.write|1700000000000|mytoken|testnonce|linux|"


def test_build_auth_payload_v3_empty_scopes():
    payload = build_auth_payload_v3(
        device_id="id",
        client_id="vc",
        client_mode="operator",
        role="operator",
        scopes=[],
        signed_at_ms=0,
        token="",
        nonce="n",
    )
    parts = payload.split("|")
    assert parts[5] == "", "empty scopes → empty string at position 5"


def test_build_auth_payload_v3_no_token():
    payload = build_auth_payload_v3(
        device_id="id",
        client_id="vc",
        client_mode="operator",
        role="operator",
        scopes=["operator.read"],
        signed_at_ms=123,
        token="",
        nonce="n",
    )
    parts = payload.split("|")
    assert parts[7] == "", "no token → empty string at position 7"


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------


def test_sign_payload_produces_valid_ed25519_signature(tmp_path):
    identity = load_or_create_identity(path=tmp_path / "d.json")
    message = "v3|testdevice|voiceclaw|operator|operator||0||nonce|linux|"

    sig_b64 = sign_payload(identity, message)

    # Verify the signature using the public key
    raw_sig = _b64url_decode(sig_b64)
    pub = load_pem_public_key(identity.public_key_pem.encode())
    assert isinstance(pub, Ed25519PublicKey)
    # This raises if the signature is invalid
    pub.verify(raw_sig, message.encode("utf-8"))


def test_sign_payload_produces_no_padding(tmp_path):
    identity = load_or_create_identity(path=tmp_path / "d.json")
    sig = sign_payload(identity, "test")
    assert "=" not in sig
