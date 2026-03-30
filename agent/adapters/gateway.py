#
# VoiceClaw — agent/adapters/gateway.py
# SPDX-License-Identifier: MIT
#

"""OpenClaw gateway WebSocket client.

Implements the full gateway handshake and chat protocol documented in
agent/upstream/openclaw/docs/gateway/protocol.md and in agent/CLAUDE.md.

Protocol summary:
  1. Connect WS to ws://{host}:{port}
  2. Receive connect.challenge event  { nonce, ts }
  3. Send connect request  { method:"connect", params:{ ... device, auth, ... } }
  4. Receive hello-ok response
  5. For each turn:
     a. Send chat.send  { sessionKey, message, idempotencyKey }
     b. Receive chat events  { state:"delta", message:{ text } }  (streaming)
     c. Receive chat event   { state:"final" }  → return accumulated text

Environment variables consumed:
  OPENCLAW_GATEWAY_URL   — ws://localhost:18789  (default)
  OPENCLAW_GATEWAY_TOKEN — optional auth token (set if gateway uses --token)
"""

import asyncio
import os
import time
import uuid
from typing import Optional

import websockets
import websockets.asyncio.client as ws_client
from loguru import logger

from .device import (
    VOICECLAW_CLIENT_ID,
    VOICECLAW_CLIENT_VERSION,
    VOICECLAW_PLATFORM,
    DeviceIdentity,
    build_auth_payload_v3,
    public_key_base64url,
    sign_payload,
)

try:
    import orjson as _json_lib

    def _dumps(obj) -> str:
        return _json_lib.dumps(obj).decode()

    def _loads(s: str) -> dict:
        return _json_lib.loads(s)

except ImportError:
    import json as _json_lib  # type: ignore[no-redef]

    def _dumps(obj) -> str:
        return _json_lib.dumps(obj)

    def _loads(s: str) -> dict:
        return _json_lib.loads(s)


# OpenClaw gateway protocol version (from src/gateway/protocol/schema/protocol-schemas.ts)
_PROTOCOL_VERSION = 3

_DEFAULT_GATEWAY_URL = "ws://localhost:18789"
_SCOPES = ["operator.read", "operator.write"]
_ROLE = "operator"
_CLIENT_MODE = "backend"

# How long to wait for the gateway to respond (connect + chat turns)
_CONNECT_TIMEOUT_S = 10.0
_CHAT_TIMEOUT_S = 60.0

# Set OPENCLAW_DEVICE_AUTH_DISABLED=true when the gateway is configured with
# gateway.controlUi.dangerouslyDisableDeviceAuth=true (e.g. in Docker dev).
# In that case the device object is omitted from the handshake since the
# voice server has no persistent Ed25519 identity across container restarts.
_DISABLE_DEVICE_AUTH = os.getenv("OPENCLAW_DEVICE_AUTH_DISABLED", "").lower() in (
    "1",
    "true",
    "yes",
)


class GatewayError(Exception):
    """Raised when the OpenClaw gateway returns an error response."""


class OpenClawGatewayClient:
    """WebSocket client for the OpenClaw gateway protocol.

    Manages one persistent connection per VoiceClaw voice session.
    Thread-safe for sequential use within a single asyncio task.

    Usage::

        client = OpenClawGatewayClient(identity=identity, session_key="vc-abc123")
        await client.connect()
        response = await client.chat_send("what's on my calendar?")
        await client.close()

    Or as an async context manager::

        async with OpenClawGatewayClient(identity, "vc-abc123") as client:
            response = await client.chat_send("hello")
    """

    def __init__(
        self,
        identity: DeviceIdentity,
        session_key: str,
        gateway_url: Optional[str] = None,
        gateway_token: Optional[str] = None,
    ):
        """Initialise the gateway client.

        Args:
            identity: Device identity for challenge-response auth.
            session_key: OpenClaw session key for this voice session.
            gateway_url: WebSocket URL of the gateway. Defaults to
                $OPENCLAW_GATEWAY_URL or ws://localhost:18789.
            gateway_token: Auth token for the gateway. Defaults to
                $OPENCLAW_GATEWAY_TOKEN (may be empty/None for no-auth setups).
        """
        self._identity = identity
        self._session_key = session_key
        self._url = gateway_url or os.getenv("OPENCLAW_GATEWAY_URL", _DEFAULT_GATEWAY_URL)
        self._token = gateway_token or os.getenv("OPENCLAW_GATEWAY_TOKEN", "")
        self._ws: Optional[ws_client.ClientConnection] = None
        self._pending: dict[str, asyncio.Future] = {}
        self._chat_listeners: dict[str, asyncio.Queue] = {}
        self._recv_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Establish the WebSocket connection and complete the handshake.

        Raises:
            GatewayError: If the handshake fails.
            asyncio.TimeoutError: If the gateway does not respond in time.
        """
        logger.info(f"OpenClawGateway: connecting to {self._url}")
        self._ws = await ws_client.connect(self._url)

        # Start background receiver before initiating the handshake so we
        # don't miss the challenge event.
        self._recv_task = asyncio.create_task(self._recv_loop(), name="gateway-recv")

        await asyncio.wait_for(self._handshake(), timeout=_CONNECT_TIMEOUT_S)
        logger.info(f"OpenClawGateway: connected (session={self._session_key!r})")

    async def close(self) -> None:
        """Close the WebSocket connection gracefully."""
        if self._recv_task:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.close()
        logger.info("OpenClawGateway: closed")

    async def __aenter__(self) -> "OpenClawGatewayClient":
        await self.connect()
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    async def chat_send(self, message: str) -> str:
        """Send a message to OpenClaw and return the full spoken response text.

        Sends ``chat.send`` and collects ``chat`` events until ``state="final"``.
        Delta text chunks are accumulated and returned as a single string.

        Args:
            message: The user message text (transcript or skills-prefixed).

        Returns:
            Accumulated assistant response text. Empty string if no text was
            produced (e.g. the agent ran a tool with no spoken reply).

        Raises:
            GatewayError: If the gateway returns an error.
            asyncio.TimeoutError: If the agent does not respond in time.
        """
        run_id = str(uuid.uuid4())
        queue: asyncio.Queue = asyncio.Queue()
        self._chat_listeners[run_id] = queue

        try:
            # Send the message
            await self._request(
                "chat.send",
                {
                    "sessionKey": self._session_key,
                    "message": message,
                    "idempotencyKey": run_id,
                },
            )

            # Collect delta events until final
            return await asyncio.wait_for(
                self._collect_chat_response(queue),
                timeout=_CHAT_TIMEOUT_S,
            )
        finally:
            self._chat_listeners.pop(run_id, None)

    # ------------------------------------------------------------------
    # Internal: handshake
    # ------------------------------------------------------------------

    async def _handshake(self) -> None:
        """Complete the challenge/response connect handshake."""
        # Step 1: wait for the challenge event
        challenge_fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending["__challenge__"] = challenge_fut
        challenge = await challenge_fut
        nonce: str = challenge["nonce"]

        # Step 2: build connect params
        connect_params: dict = {
            "minProtocol": _PROTOCOL_VERSION,
            "maxProtocol": _PROTOCOL_VERSION,
            "client": {
                "id": VOICECLAW_CLIENT_ID,
                "version": VOICECLAW_CLIENT_VERSION,
                "platform": VOICECLAW_PLATFORM,
                "mode": _CLIENT_MODE,
            },
            "role": _ROLE,
            "scopes": _SCOPES,
            "caps": [],
            "commands": [],
            "permissions": {},
            "auth": {"token": self._token} if self._token else {},
            "locale": "en-US",
            "userAgent": f"voiceclaw/{VOICECLAW_CLIENT_VERSION}",
        }

        # Include device identity only when device auth is enabled.
        # When OPENCLAW_DEVICE_AUTH_DISABLED=true (Docker dev with
        # gateway.controlUi.dangerouslyDisableDeviceAuth=true), the
        # device object is omitted because the voice server has no
        # persistent Ed25519 identity across container restarts.
        if not _DISABLE_DEVICE_AUTH:
            signed_at_ms = int(time.time() * 1000)
            payload_str = build_auth_payload_v3(
                device_id=self._identity.device_id,
                client_id=VOICECLAW_CLIENT_ID,
                client_mode=_CLIENT_MODE,
                role=_ROLE,
                scopes=_SCOPES,
                signed_at_ms=signed_at_ms,
                token=self._token,
                nonce=nonce,
                platform=VOICECLAW_PLATFORM,
            )
            signature = sign_payload(self._identity, payload_str)
            connect_params["device"] = {
                "id": self._identity.device_id,
                "publicKey": public_key_base64url(self._identity),
                "signature": signature,
                "signedAt": signed_at_ms,
                "nonce": nonce,
            }

        await self._request("connect", connect_params)
        logger.debug("OpenClawGateway: handshake complete")

    # ------------------------------------------------------------------
    # Internal: messaging
    # ------------------------------------------------------------------

    async def _request(self, method: str, params: dict) -> dict:
        """Send a request frame and await its response.

        Args:
            method: Gateway method name (e.g. ``"connect"``, ``"chat.send"``).
            params: Method parameters dict.

        Returns:
            The response payload dict.

        Raises:
            GatewayError: If ``ok`` is False in the response.
        """
        req_id = str(uuid.uuid4())
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = fut

        frame = _dumps({"type": "req", "id": req_id, "method": method, "params": params})
        await self._ws.send(frame)

        res = await fut
        if not res.get("ok"):
            raise GatewayError(f"Gateway error for {method}: {res.get('error')}")
        return res.get("payload", {})

    async def _collect_chat_response(self, queue: asyncio.Queue) -> str:
        """Collect chat delta events until final.

        Args:
            queue: The queue registered for this run_id's chat events.

        Returns:
            Concatenated text from all delta events.
        """
        chunks: list[str] = []
        while True:
            event = await queue.get()
            state = event.get("state")
            if state == "delta":
                msg = event.get("message") or {}
                text = msg.get("text") if isinstance(msg, dict) else None
                if isinstance(text, str) and text:
                    chunks.append(text)
            elif state == "final":
                break
            elif state in ("error", "aborted"):
                err = event.get("errorMessage", "unknown error")
                raise GatewayError(f"Chat run ended with state={state!r}: {err}")
        return "".join(chunks)

    # ------------------------------------------------------------------
    # Internal: receive loop
    # ------------------------------------------------------------------

    async def _recv_loop(self) -> None:
        """Background task: route incoming WebSocket frames to waiters."""
        try:
            async for raw in self._ws:
                try:
                    msg = _loads(raw)
                except Exception:
                    logger.warning(f"OpenClawGateway: unparseable frame: {raw!r:.120}")
                    continue
                self._dispatch(msg)
        except (websockets.exceptions.ConnectionClosedOK, asyncio.CancelledError):
            pass
        except Exception as exc:
            logger.error(f"OpenClawGateway: recv_loop error: {exc}")
        finally:
            # Fail all pending futures so callers aren't stuck
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(GatewayError("WebSocket connection closed"))

    def _dispatch(self, msg: dict) -> None:
        """Route a parsed frame to the correct waiter.

        Args:
            msg: Parsed JSON frame dict.
        """
        frame_type = msg.get("type")

        if frame_type == "event":
            event_name = msg.get("event")
            payload = msg.get("payload", {})

            if event_name == "connect.challenge":
                fut = self._pending.pop("__challenge__", None)
                if fut and not fut.done():
                    fut.set_result(payload)

            elif event_name == "chat":
                # Route to all chat listeners — they filter by runId themselves,
                # but since we use a per-run_id idempotency key the gateway
                # scopes events per run.  For simplicity, broadcast to all
                # active listeners (there will usually be only one).
                for queue in self._chat_listeners.values():
                    queue.put_nowait(payload)

        elif frame_type == "res":
            req_id = msg.get("id")
            fut = self._pending.pop(req_id, None)
            if fut and not fut.done():
                fut.set_result(msg)
