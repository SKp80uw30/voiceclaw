#
# VoiceClaw — voice/adapters/pipeline.py
# SPDX-License-Identifier: MIT
#

"""VoiceClawPipeline — assembles the full Pipecat voice pipeline.

Pipeline chain:

    transport.input()
        → DeepgramSTTService          (speech → transcript)
        → OpenClawBridgeProcessor     (transcript → OpenClaw → spoken text)
        → CartesiaTTSService          (spoken text → audio)
        → transport.output()

The OpenClawBridgeProcessor replaces the LLM slot. It calls the on_transcript
callback (which the server uses to route to the OpenClaw gateway) and emits
LLMFullResponseStartFrame / LLMFullResponseEndFrame around the response so
OrbState transitions fire correctly.

All API keys and model configuration are read from environment variables.
No credentials are accepted as constructor arguments.

Environment variables consumed:
    DEEPGRAM_API_KEY      — required
    CARTESIA_API_KEY      — required
    CARTESIA_VOICE_ID     — optional, defaults to a sensible English voice
    OPENROUTER_API_KEY    — present in env for OpenClaw to use; not used here
    OPENCLAW_MODEL        — present in env for OpenClaw to use; not used here
"""

import asyncio
import os
from typing import Awaitable, Callable, Optional

from loguru import logger
from pipecat.frames.frames import (
    EndFrame,
    Frame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    TextFrame,
    TranscriptionFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

from adapters.events import OrbState, OrbStateObserver

# Default Cartesia voice: Barbershop Man (neutral, clear English).
# Override with CARTESIA_VOICE_ID env var.
_DEFAULT_CARTESIA_VOICE_ID = "a0e99841-438c-4a64-b679-ae501e7d6091"


class OpenClawBridgeProcessor(FrameProcessor):
    """Routes final transcriptions to OpenClaw and pushes spoken text to TTS.

    Sits in the pipeline between STT and TTS in place of a local LLM.
    Passes all non-transcription frames through unchanged.

    On receiving a TranscriptionFrame:
      1. Pushes LLMFullResponseStartFrame  (triggers thinking → speaking transition)
      2. Calls on_transcript(text) → awaits spoken response text from OpenClaw
      3. Pushes TextFrame(response)        (consumed by CartesiaTTSService)
      4. Pushes LLMFullResponseEndFrame

    InterimTranscriptionFrames are passed through untouched (Pipecat uses them
    for barge-in detection; we do not route partial transcripts to OpenClaw).
    """

    def __init__(
        self,
        on_transcript: Callable[[str], Awaitable[str]],
        **kwargs,
    ):
        """Initialise the bridge processor.

        Args:
            on_transcript: Async callback that receives the final transcript text
                and returns the spoken response text from OpenClaw.
            **kwargs: Additional arguments forwarded to FrameProcessor.
        """
        super().__init__(**kwargs)
        self._on_transcript = on_transcript

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Handle incoming frames.

        Args:
            frame: The frame to process.
            direction: Pipeline direction (downstream / upstream).
        """
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame):
            await self._handle_transcript(frame.text)
        else:
            await self.push_frame(frame, direction)

    async def _handle_transcript(self, text: str) -> None:
        """Call OpenClaw and push the spoken response downstream.

        Args:
            text: Final transcript text from Deepgram STT.
        """
        logger.debug(f"OpenClawBridge: transcript={text!r}")

        await self.push_frame(LLMFullResponseStartFrame())

        try:
            response_text = await self._on_transcript(text)
            logger.debug(f"OpenClawBridge: response={response_text!r}")
            if response_text:
                await self.push_frame(TextFrame(response_text))
        except Exception as e:
            logger.error(f"OpenClawBridge: error calling OpenClaw: {e}")
            await self.push_error(f"OpenClaw gateway error: {e}", exception=e, fatal=False)

        await self.push_frame(LLMFullResponseEndFrame())


class VoiceClawPipeline:
    """Assembles and owns the full Pipecat voice pipeline for one WebRTC session.

    Instantiated once per browser connection by the FastAPI server. Holds the
    PipelineTask and PipelineRunner for the session lifetime.

    Usage::

        pipeline = VoiceClawPipeline(
            transport=transport,
            on_state_change=push_sse_event,
            on_transcript=call_openclaw_gateway,
        )
        await pipeline.start()
        # ...
        await pipeline.stop()
    """

    def __init__(
        self,
        transport: SmallWebRTCTransport,
        on_state_change: Callable[[OrbState], Awaitable[None]],
        on_transcript: Callable[[str], Awaitable[str]],
    ):
        """Assemble the pipeline from environment variables.

        Args:
            transport: Configured SmallWebRTCTransport for this session.
            on_state_change: Async callback fired on OrbState transitions.
                Receives the new OrbState. Used by the server to push SSE events.
            on_transcript: Async callback fired with final transcript text.
                Must return the spoken response text from OpenClaw.
        """
        self._transport = transport
        self._runner: Optional[PipelineRunner] = None
        self._task: Optional[PipelineTask] = None

        stt = DeepgramSTTService(
            api_key=os.environ["DEEPGRAM_API_KEY"],
        )

        tts = CartesiaTTSService(
            api_key=os.environ["CARTESIA_API_KEY"],
            settings=CartesiaTTSService.Settings(
                voice=os.getenv("CARTESIA_VOICE_ID", _DEFAULT_CARTESIA_VOICE_ID),
            ),
        )

        bridge = OpenClawBridgeProcessor(on_transcript=on_transcript)

        pipeline = Pipeline(
            [
                transport.input(),
                stt,
                bridge,
                tts,
                transport.output(),
            ]
        )

        orb_observer = OrbStateObserver(on_state_change=on_state_change)

        self._task = PipelineTask(
            pipeline,
            params=PipelineParams(
                enable_metrics=True,
                enable_usage_metrics=True,
            ),
            observers=[orb_observer],
        )

        self._runner = PipelineRunner(handle_sigint=False)

    async def start(self) -> None:
        """Run the pipeline. Blocks until the session ends or stop() is called."""
        logger.info("VoiceClawPipeline: starting")
        await self._runner.run(self._task)
        logger.info("VoiceClawPipeline: stopped")

    async def stop(self) -> None:
        """Cancel the pipeline task gracefully.

        Safe to call from connection-closed event handlers.
        """
        if self._task is not None:
            logger.info("VoiceClawPipeline: cancelling task")
            await self._task.cancel()
