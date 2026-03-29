#
# VoiceClaw — agent/adapters/session.py
# SPDX-License-Identifier: MIT
#

"""Per-voice-session lifecycle manager.

One VoiceClawSession is created for each WebRTC connection (identified by the
SmallWebRTC pc_id). It owns:
  - An OpenClawGatewayClient (the WebSocket connection to OpenClaw)
  - The session key used for that client's chat turns
  - The on_transcript callback wired into VoiceClawPipeline

Responsibilities:
  1. Derive a stable OpenClaw session key from the WebRTC connection ID.
  2. Load Voice Bridge Skills and prepend them to every chat message.
  3. Connect/disconnect the gateway client with the session.
  4. Expose send_transcript(text) → str for the Pipecat OpenClawBridgeProcessor.
"""

import os
from pathlib import Path
from typing import Optional

from loguru import logger

from adapters.device import DeviceIdentity, load_or_create_identity
from adapters.gateway import OpenClawGatewayClient
from adapters.skills import load_skills


def _session_key_from_connection_id(connection_id: str) -> str:
    """Derive a stable OpenClaw session key from a WebRTC pc_id.

    Uses a human-readable prefix so sessions are identifiable in the OpenClaw
    UI. Truncated to 64 characters to stay within OpenClaw's key constraints.

    Args:
        connection_id: SmallWebRTC pc_id (e.g. "abc123def456").

    Returns:
        Session key string (e.g. "voiceclaw-abc123def456").
    """
    return f"voiceclaw-{connection_id}"[:64]


class VoiceClawSession:
    """Manages a single voice session's lifecycle with OpenClaw.

    Instantiated by the FastAPI server when a WebRTC connection is established.
    Closed when the WebRTC connection ends.

    Usage::

        session = VoiceClawSession(connection_id="abc123")
        await session.start()

        # wire to VoiceClawPipeline
        pipeline = VoiceClawPipeline(
            transport=transport,
            on_state_change=push_sse_event,
            on_transcript=session.send_transcript,
        )

        # ... later
        await session.stop()
    """

    def __init__(
        self,
        connection_id: str,
        identity: Optional[DeviceIdentity] = None,
        skills_dir: Optional[Path] = None,
        gateway_url: Optional[str] = None,
        gateway_token: Optional[str] = None,
    ):
        """Initialise the session.

        Args:
            connection_id: WebRTC pc_id that identifies this session.
            identity: Device identity for OpenClaw auth. Loaded from disk if
                not provided.
            skills_dir: Override the skills directory. Defaults to skills/ at
                the repo root.
            gateway_url: Override the OpenClaw gateway URL.
            gateway_token: Override the OpenClaw gateway auth token.
        """
        self._connection_id = connection_id
        self._session_key = _session_key_from_connection_id(connection_id)
        self._identity = identity or load_or_create_identity()
        self._skills_context = load_skills(skills_dir)
        self._gateway = OpenClawGatewayClient(
            identity=self._identity,
            session_key=self._session_key,
            gateway_url=gateway_url,
            gateway_token=gateway_token,
        )
        logger.info(
            f"VoiceClawSession: created "
            f"connection={connection_id!r} session_key={self._session_key!r}"
        )

    async def start(self) -> None:
        """Connect to the OpenClaw gateway.

        Raises:
            GatewayError: If the connection or handshake fails.
        """
        await self._gateway.connect()

    async def stop(self) -> None:
        """Disconnect from the OpenClaw gateway."""
        await self._gateway.close()
        logger.info(f"VoiceClawSession: stopped connection={self._connection_id!r}")

    async def send_transcript(self, transcript: str) -> str:
        """Route a final transcript to OpenClaw and return the spoken response.

        Prepends all loaded Voice Bridge Skills to the message so the agent has
        full context for tool selection and response generation.

        This method is passed as ``on_transcript`` to ``VoiceClawPipeline``.

        Args:
            transcript: Final transcript text from Deepgram STT.

        Returns:
            Spoken response text from OpenClaw (empty string if the agent
            produces no textual reply, e.g. tool-only turn).
        """
        message = _build_message(self._skills_context, transcript)
        logger.debug(
            f"VoiceClawSession: sending transcript to OpenClaw "
            f"(session={self._session_key!r}, len={len(transcript)})"
        )
        response = await self._gateway.chat_send(message)
        logger.debug(
            f"VoiceClawSession: received response "
            f"(session={self._session_key!r}, len={len(response)})"
        )
        return response

    @property
    def session_key(self) -> str:
        """The OpenClaw session key for this voice session."""
        return self._session_key


def _build_message(skills_context: str, transcript: str) -> str:
    """Combine skills context and transcript into a single chat message.

    Args:
        skills_context: Pre-loaded skills content (may be empty string).
        transcript: User's spoken transcript.

    Returns:
        Full message string ready for chat.send.
    """
    if not skills_context:
        return transcript
    return f"{skills_context}\n\n---\n\nUser said: {transcript}"
