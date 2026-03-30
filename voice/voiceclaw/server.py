#
# VoiceClaw — voice/voiceclaw/server.py
# SPDX-License-Identifier: MIT
#

"""FastAPI entry point for the VoiceClaw Pipecat server.

Exposes:
  GET  /           — serves the PWA static files
  POST /offer      — WebRTC SDP offer/answer via SmallWebRTCRequestHandler
  PATCH /offer     — ICE candidate trickle via SmallWebRTCRequestHandler
  GET  /state/{pc_id} — SSE stream of OrbState events for the PWA orb UI

On a new WebRTC connection the server:
  1. SmallWebRTCRequestHandler processes the SDP offer
  2. Creates a VoiceClawSession (OpenClaw gateway client)
  3. Creates a VoiceClawPipeline (Pipecat audio pipeline)
  4. Wires session.send_transcript → pipeline.on_transcript
  5. Broadcasts OrbState transitions via SSE
  6. Runs the pipeline in a background task until the connection closes

The /offer endpoint is compatible with @pipecat-ai/client-react and
@pipecat-ai/small-webrtc-transport.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, AsyncGenerator

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env", override=False)

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from adapters.events import OrbState
from adapters.pipeline import VoiceClawPipeline
from adapters.transport import _DEFAULT_ICE_SERVERS, create_transport
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.request_handler import (
    ConnectionMode,
    IceCandidate,
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)

from voiceclaw.session import VoiceClawSession


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_PWA_STATIC_DIR = Path(
    os.getenv("VOICECLAW_PWA_DIR", str(Path(__file__).parent.parent.parent / "pwa"))
)

_OPENCLAW_GATEWAY_URL = os.getenv("OPENCLAW_GATEWAY_URL", "ws://localhost:18789")


# ---------------------------------------------------------------------------
# Per-session state
# ---------------------------------------------------------------------------


@dataclass
class VoiceSession:
    """Holds all state for one WebRTC / voice session."""

    pc_id: str
    pipeline: VoiceClawPipeline
    session: VoiceClawSession
    sse_queue: asyncio.Queue[OrbState | None] = field(default_factory=asyncio.Queue)
    pipeline_task: asyncio.Task | None = None
    done_event: asyncio.Event = field(default_factory=asyncio.Event)


_sessions: dict[str, VoiceSession] = {}
_sessions_lock = asyncio.Lock()

_webrtc_handler: SmallWebRTCRequestHandler | None = None


# ---------------------------------------------------------------------------
# SSE broadcaster
# ---------------------------------------------------------------------------


async def _sse_state_stream(pc_id: str) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted OrbState events for one browser connection."""
    session = _sessions.get(pc_id)
    if session is None:
        return

    yield "event: open\n\n"
    while True:
        state = await session.sse_queue.get()
        if state is None:
            break
        yield f"data: {state.value}\n\n"


# ---------------------------------------------------------------------------
# Pipeline bootstrap (runs in background after /offer returns)
# ---------------------------------------------------------------------------


async def _start_pipeline(
    pc_id: str,
    connection: SmallWebRTCConnection,
    gateway_url: str,
) -> None:
    """Create transport, pipeline, and session; wait for the WebRTC lifecycle.

    Executed as a background task after the SDP answer is returned to the
    browser.  The gateway connection and pipeline run are deferred to
    _on_connected so they only start after the WebRTC data channel is open.
    This avoids a race where a fast gateway failure tears down the session
    before the WebRTC handshake completes.
    """
    logger.info(f"VoiceClaw server: bootstrapping pipeline pc_id={pc_id!r}")

    voice_session: VoiceSession | None = None

    try:
        oc_session = VoiceClawSession(
            connection_id=pc_id,
            gateway_url=gateway_url,
        )

        sse_queue: asyncio.Queue[OrbState | None] = asyncio.Queue()

        async def on_state_change(state: OrbState) -> None:
            await sse_queue.put(state)

        async def _on_connected_cb(_t, _conn) -> None:
            await _on_connected(pc_id, _conn)

        async def _on_disconnected_cb(_t, _conn) -> None:
            await _on_disconnected(pc_id, _conn)

        transport = create_transport(
            connection=connection,
            on_connected=_on_connected_cb,
            on_disconnected=_on_disconnected_cb,
        )

        pipeline = VoiceClawPipeline(
            transport=transport,
            on_state_change=on_state_change,
            on_transcript=oc_session.send_transcript,
        )

        voice_session = VoiceSession(
            pc_id=pc_id,
            pipeline=pipeline,
            session=oc_session,
            sse_queue=sse_queue,
        )

        async with _sessions_lock:
            _sessions[pc_id] = voice_session

        # Start the pipeline immediately. Running the pipeline sends StartFrame
        # through the transport, which calls connection.connect() internally —
        # that is the only thing that fires the "connected" event on the
        # SmallWebRTCConnection, which then calls _on_connected_cb → session.start().
        voice_session.pipeline_task = asyncio.create_task(
            voice_session.pipeline.start(),
            name=f"pipeline-{pc_id}",
        )

        # Block until _on_disconnected signals that the WebRTC session is over.
        await voice_session.done_event.wait()

    except KeyError as exc:
        logger.error(
            f"VoiceClaw server: missing environment variable {exc} — "
            f"pipeline cannot start pc_id={pc_id!r}. "
            f"Set required keys in .env"
        )
    except Exception as exc:
        logger.error(f"VoiceClaw server: pipeline error pc_id={pc_id!r}: {exc}")
    finally:
        popped = _sessions.pop(pc_id, None)
        if popped is not None:
            await _teardown_session(popped)


# ---------------------------------------------------------------------------
# Connection lifecycle callbacks
# ---------------------------------------------------------------------------


async def _on_connected(pc_id: str, connection: SmallWebRTCConnection) -> None:
    """Called by the transport when the WebRTC data channel is open.

    Connects the OpenClaw gateway for this session. The pipeline is already
    running at this point (it was started immediately after creation — that
    startup is what triggers connection.connect() which fires this event).
    Gateway failure is logged but does not abort the session — each transcript
    call will surface the error if the gateway is unavailable.
    """
    logger.info(f"VoiceClaw server: WebRTC connected pc_id={pc_id!r}")
    voice_session = _sessions.get(pc_id)
    if voice_session is None:
        logger.warning(f"No session for pc_id={pc_id!r} — ignoring on_connected")
        return

    try:
        await voice_session.session.start()
        logger.info(f"VoiceClaw server: gateway connected pc_id={pc_id!r}")
    except Exception as exc:
        logger.error(
            f"VoiceClaw server: gateway connection failed pc_id={pc_id!r}: {exc} "
            f"— bot cannot respond until gateway is available"
        )


async def _on_disconnected(pc_id: str, connection: SmallWebRTCConnection) -> None:
    """Called by the transport when the WebRTC connection closes."""
    logger.info(f"VoiceClaw server: WebRTC disconnected pc_id={pc_id!r}")
    voice_session = _sessions.get(pc_id)
    if voice_session is not None:
        voice_session.done_event.set()


async def _teardown_session(session: VoiceSession) -> None:
    """Cancel the pipeline and close the OpenClaw gateway session."""
    if session.pipeline_task is not None:
        session.pipeline_task.cancel()
        try:
            await session.pipeline_task
        except asyncio.CancelledError:
            pass

    await session.pipeline.stop()
    await session.session.stop()
    await session.sse_queue.put(None)

    logger.info(f"VoiceClaw server: session torn down pc_id={session.pc_id!r}")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle: startup and shutdown."""
    global _webrtc_handler

    logger.info("VoiceClaw server starting up")

    ice_servers = _DEFAULT_ICE_SERVERS
    _webrtc_handler = SmallWebRTCRequestHandler(
        ice_servers=ice_servers,
        connection_mode=ConnectionMode.MULTIPLE,
    )

    yield

    logger.info("VoiceClaw server shutting down")
    if _webrtc_handler is not None:
        await _webrtc_handler.close()

    async with _sessions_lock:
        for session in list(_sessions.values()):
            await _teardown_session(session)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="VoiceClaw",
    description="Voice-first AI agent — Pipecat voice pipeline + OpenClaw gateway",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", response_model=None)
async def serve_pwa() -> Response:
    """Serve the PWA index.html (or a redirect to the WebRTC client page)."""
    index_path = _PWA_STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return Response(
        content="<html><body>"
        "<h1>VoiceClaw</h1>"
        "<p>PWA not built yet. Run: cd pwa && npm install && npm run dev</p>"
        "</body></html>",
        media_type="text/html",
    )


if (_PWA_STATIC_DIR / "assets").exists():
    app.mount(
        "/assets",
        StaticFiles(directory=str(_PWA_STATIC_DIR / "assets"), html=False),
        name="pwa-assets",
    )

    @app.get("/{filename}")
    async def serve_root_file(filename: str) -> Response:
        p = _PWA_STATIC_DIR / filename
        if p.exists() and p.is_file():
            return FileResponse(p)
        raise HTTPException(status_code=404)


@app.post("/offer")
async def handle_offer(
    request: Annotated[SmallWebRTCRequest, SmallWebRTCRequest],
) -> dict:
    """Accept a WebRTC SDP offer and set up the voice session.

    Compatible with @pipecat-ai/client-react and
    @pipecat-ai/small-webrtc-transport.

    Returns the SDP answer and pc_id immediately while starting the
    voice pipeline in the background.
    """
    if _webrtc_handler is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    async def callback(connection: SmallWebRTCConnection) -> None:
        pc_id = connection.pc_id
        asyncio.create_task(
            _start_pipeline(pc_id, connection, _OPENCLAW_GATEWAY_URL),
            name=f"bootstrap-{pc_id}",
        )

    try:
        answer = await _webrtc_handler.handle_web_request(request, callback)
        if answer is None:
            raise HTTPException(status_code=500, detail="Failed to generate SDP answer")
        return answer
    except Exception as exc:
        logger.error(f"VoiceClaw server: /offer error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.patch("/offer")
async def handle_ice_candidate(
    request: Annotated[SmallWebRTCPatchRequest, SmallWebRTCPatchRequest],
) -> dict:
    """Handle trickle ICE candidates from the browser.

    Compatible with @pipecat-ai/client-react and
    @pipecat-ai/small-webrtc-transport.
    """
    if _webrtc_handler is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    try:
        await _webrtc_handler.handle_patch_request(request)
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"VoiceClaw server: PATCH /offer error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/state/{pc_id}")
async def stream_state(pc_id: str) -> StreamingResponse:
    """Stream OrbState events to the PWA orb via SSE.

    The browser opens this SSE stream immediately after receiving the /offer
    response, using the same pc_id.
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for line in _sse_state_stream(pc_id):
                yield line
        except GeneratorExit:
            pass
        finally:
            logger.debug(f"SSE stream closed for pc_id={pc_id!r}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
