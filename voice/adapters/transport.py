#
# VoiceClaw — voice/adapters/transport.py
# SPDX-License-Identifier: MIT
#

"""WebRTC transport adapter.

Thin wrapper around Pipecat's SmallWebRTCTransport that:
  - Applies VoiceClaw's standard TransportParams (audio-only, in + out)
  - Provides a create_connection() helper used by the FastAPI /offer handler
  - Exposes connection lifecycle events (connected / disconnected) for the server

All WebRTC config is intentionally minimal — we only need audio for voice.
"""

from typing import Awaitable, Callable, Optional

from loguru import logger
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import IceServer, SmallWebRTCConnection
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

# Public STUN server — sufficient for local dev and Railway (no TURN needed for
# server-to-browser when both are on public IPs; revisit if NAT issues arise).
_DEFAULT_ICE_SERVERS = [
    IceServer(urls="stun:stun.l.google.com:19302"),
]

# Standard TransportParams for VoiceClaw: audio-only bidirectional.
_VOICECLAW_TRANSPORT_PARAMS = TransportParams(
    audio_in_enabled=True,
    audio_out_enabled=True,
)


async def create_connection(
    sdp: str,
    type: str,
    ice_servers: Optional[list[IceServer]] = None,
) -> SmallWebRTCConnection:
    """Initialise a SmallWebRTCConnection from a browser SDP offer.

    Called by the FastAPI POST /offer handler. Returns the connection object;
    the pc_id is available via connection.pc_id for session tracking.

    Args:
        sdp: SDP offer string from the browser.
        type: SDP type string (should be "offer").
        ice_servers: ICE server list. Defaults to Google public STUN.

    Returns:
        Initialised SmallWebRTCConnection ready to attach to a transport.
    """
    servers = ice_servers or _DEFAULT_ICE_SERVERS
    connection = SmallWebRTCConnection(servers)
    await connection.initialize(sdp=sdp, type=type)
    logger.info(f"WebRTC connection initialised: pc_id={connection.pc_id}")
    return connection


def create_transport(
    connection: SmallWebRTCConnection,
    on_connected: Optional[Callable[..., Awaitable[None]]] = None,
    on_disconnected: Optional[Callable[..., Awaitable[None]]] = None,
) -> SmallWebRTCTransport:
    """Create a SmallWebRTCTransport with VoiceClaw's standard params.

    Registers optional connected/disconnected event handlers on the transport
    so the server can start / stop the pipeline task on connection events.

    Args:
        connection: Initialised WebRTC connection from create_connection().
        on_connected: Async callback fired when the browser connects.
        on_disconnected: Async callback fired when the browser disconnects.

    Returns:
        Configured SmallWebRTCTransport ready to be used in a Pipeline.
    """
    transport = SmallWebRTCTransport(
        webrtc_connection=connection,
        params=_VOICECLAW_TRANSPORT_PARAMS,
    )

    if on_connected is not None:
        transport.event_handler("on_client_connected")(on_connected)

    if on_disconnected is not None:
        transport.event_handler("on_client_disconnected")(on_disconnected)

    return transport
