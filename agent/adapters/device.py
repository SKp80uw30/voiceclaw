#
# VoiceClaw — agent/adapters/device.py
# SPDX-License-Identifier: MIT
#

"""Device identity for the OpenClaw gateway protocol.

OpenClaw requires every client to carry a stable Ed25519 device identity.
The gateway issues a challenge nonce at connect time; the client must sign it
before the handshake completes. This module mirrors the logic in
agent/upstream/openclaw/src/infra/device-identity.ts exactly.

Signature payload format (v3 — preferred):
  "v3|{deviceId}|{clientId}|{clientMode}|{role}|{scopes,}|{signedAtMs}|{token}|{nonce}|{platform}|{deviceFamily}"

All fields joined with "|".  scopes joined with ",".  Empty optional fields
become "".

Public key wire format: raw 32-byte Ed25519 public key, base64url-encoded
(no padding).

Device ID: SHA-256 of the raw 32-byte public key, hex-encoded.

Storage: JSON file at path $VOICECLAW_DEVICE_KEY_PATH or
~/.voiceclaw/identity/device.json  with structure:
  { version: 1, deviceId, publicKeyPem, privateKeyPem, createdAtMs }
"""

import base64
import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

_DEFAULT_IDENTITY_PATH = Path.home() / ".voiceclaw" / "identity" / "device.json"

VOICECLAW_CLIENT_ID = "voiceclaw"
VOICECLAW_CLIENT_VERSION = "0.1.0"
VOICECLAW_PLATFORM = "linux"  # overridden at connect time if needed


@dataclass(frozen=True)
class DeviceIdentity:
    """Stable Ed25519 device identity for the OpenClaw gateway.

    Parameters:
        device_id: SHA-256 hex fingerprint of the raw public key.
        public_key_pem: PEM-encoded SPKI public key.
        private_key_pem: PEM-encoded PKCS8 private key.
    """

    device_id: str
    public_key_pem: str
    private_key_pem: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _b64url(data: bytes) -> str:
    """Base64url-encode without padding (matches JS base64UrlEncode)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _raw_public_key_bytes(public_key: Ed25519PublicKey) -> bytes:
    """Extract the 32-byte raw key from a public key object."""
    return public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)


def _device_id_from_raw(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _generate_identity() -> DeviceIdentity:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()
    private_pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()
    raw = _raw_public_key_bytes(public_key)
    device_id = _device_id_from_raw(raw)
    return DeviceIdentity(device_id=device_id, public_key_pem=public_pem, private_key_pem=private_pem)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_or_create_identity(
    path: Path | None = None,
) -> DeviceIdentity:
    """Load the device identity from disk, generating one if absent.

    The identity file is created with mode 0o600 (owner read/write only).

    Args:
        path: Path to the identity JSON file. Defaults to
            $VOICECLAW_DEVICE_KEY_PATH or ~/.voiceclaw/identity/device.json.

    Returns:
        Loaded or freshly generated DeviceIdentity.
    """
    resolved = path or Path(os.getenv("VOICECLAW_DEVICE_KEY_PATH", str(_DEFAULT_IDENTITY_PATH)))

    if resolved.exists():
        try:
            data = json.loads(resolved.read_text())
            if (
                data.get("version") == 1
                and isinstance(data.get("deviceId"), str)
                and isinstance(data.get("publicKeyPem"), str)
                and isinstance(data.get("privateKeyPem"), str)
            ):
                return DeviceIdentity(
                    device_id=data["deviceId"],
                    public_key_pem=data["publicKeyPem"],
                    private_key_pem=data["privateKeyPem"],
                )
        except Exception:
            pass  # corrupt file — regenerate below

    identity = _generate_identity()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(
        json.dumps(
            {
                "version": 1,
                "deviceId": identity.device_id,
                "publicKeyPem": identity.public_key_pem,
                "privateKeyPem": identity.private_key_pem,
                "createdAtMs": int(time.time() * 1000),
            },
            indent=2,
        )
        + "\n"
    )
    resolved.chmod(0o600)
    return identity


def public_key_base64url(identity: DeviceIdentity) -> str:
    """Return the base64url-encoded raw 32-byte public key.

    This is the value sent as ``device.publicKey`` in the connect request.

    Args:
        identity: Device identity.

    Returns:
        Base64url-encoded raw public key (no padding).
    """
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    pub = load_pem_public_key(identity.public_key_pem.encode())
    assert isinstance(pub, Ed25519PublicKey)
    return _b64url(_raw_public_key_bytes(pub))


def build_auth_payload_v3(
    *,
    device_id: str,
    client_id: str,
    client_mode: str,
    role: str,
    scopes: list[str],
    signed_at_ms: int,
    token: str,
    nonce: str,
    platform: str = "",
    device_family: str = "",
) -> str:
    """Build the v3 signature payload string.

    Mirrors ``buildDeviceAuthPayloadV3`` from
    agent/upstream/openclaw/src/gateway/device-auth.ts.

    Args:
        device_id: Hex SHA-256 fingerprint of the raw public key.
        client_id: Client identifier string (e.g. ``"voiceclaw"``).
        client_mode: Client mode (``"operator"``).
        role: Connection role (``"operator"``).
        scopes: List of requested scopes.
        signed_at_ms: Unix timestamp in milliseconds at signing time.
        token: Gateway auth token (empty string if none).
        nonce: Challenge nonce from the gateway.
        platform: Platform string (e.g. ``"linux"``), or empty.
        device_family: Device family string, or empty.

    Returns:
        The pipe-delimited v3 payload string ready for signing.
    """
    return "|".join(
        [
            "v3",
            device_id,
            client_id,
            client_mode,
            role,
            ",".join(scopes),
            str(signed_at_ms),
            token,
            nonce,
            platform or "",
            device_family or "",
        ]
    )


def sign_payload(identity: DeviceIdentity, payload: str) -> str:
    """Sign a string payload with the device private key.

    Mirrors ``signDevicePayload`` from
    agent/upstream/openclaw/src/infra/device-identity.ts.

    Args:
        identity: Device identity containing the private key.
        payload: UTF-8 string to sign.

    Returns:
        Base64url-encoded Ed25519 signature (no padding).
    """
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    priv = load_pem_private_key(identity.private_key_pem.encode(), password=None)
    assert isinstance(priv, Ed25519PrivateKey)
    sig = priv.sign(payload.encode("utf-8"))
    return _b64url(sig)
