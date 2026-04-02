#
# VoiceClaw — voice/adapters/pipeline.py
# SPDX-License-Identifier: MIT
#

"""VoiceClawPipeline — assembles the full Pipecat voice pipeline.

Pipeline chain:

    transport.input()
        → DeepgramSTTService          (speech → transcript)
        → context_aggregator.user()   (accumulates conversation turns)
        → OpenAILLMService            (OpenRouter LLM — reasoning + response)
        → context_aggregator.assistant()
        → CartesiaTTSService          (spoken text → audio)
        → transport.output()

The LLM is called via OpenRouter using the OpenAI-compatible API. Skills loaded
from skills/ are injected as the system prompt at session start.

All API keys and model configuration are read from environment variables.

Environment variables consumed:
    DEEPGRAM_API_KEY      — required
    CARTESIA_API_KEY      — required
    CARTESIA_VOICE_ID     — optional, defaults to a sensible English voice
    OPENROUTER_API_KEY    — required
    LLM_MODEL             — required, e.g. anthropic/claude-sonnet-4-6
"""

import os
from pathlib import Path
from typing import Awaitable, Callable, Optional

from loguru import logger
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

from adapters.events import OrbState, OrbStateObserver
from adapters.skills import load_skills

# Default Cartesia voice: Barbershop Man (neutral, clear English).
# Override with CARTESIA_VOICE_ID env var.
_DEFAULT_CARTESIA_VOICE_ID = "a0e99841-438c-4a64-b679-ae501e7d6091"

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

_BASE_SYSTEM_PROMPT = (
    "You are Flow, a voice-first AI assistant. "
    "Keep responses concise and natural for spoken audio — no markdown, "
    "no bullet points, no lists. Speak in clear, complete sentences."
)


class VoiceClawPipeline:
    """Assembles and owns the full Pipecat voice pipeline for one WebRTC session.

    Instantiated once per browser connection by the FastAPI server. Holds the
    PipelineTask and PipelineRunner for the session lifetime.

    Usage::

        pipeline = VoiceClawPipeline(
            transport=transport,
            on_state_change=push_sse_event,
        )
        await pipeline.start()
        # ...
        await pipeline.stop()
    """

    def __init__(
        self,
        transport: SmallWebRTCTransport,
        on_state_change: Callable[[OrbState], Awaitable[None]],
        skills_dir: Optional[Path] = None,
    ):
        """Assemble the pipeline from environment variables.

        Args:
            transport: Configured SmallWebRTCTransport for this session.
            on_state_change: Async callback fired on OrbState transitions.
                Receives the new OrbState. Used by the server to push SSE events.
            skills_dir: Override the skills directory (used in tests).
        """
        self._transport = transport
        self._runner: Optional[PipelineRunner] = None
        self._task: Optional[PipelineTask] = None

        stt = DeepgramSTTService(
            api_key=os.environ["DEEPGRAM_API_KEY"],
        )

        llm = OpenAILLMService(
            api_key=os.environ["OPENROUTER_API_KEY"],
            model=os.environ["LLM_MODEL"],
            base_url=_OPENROUTER_BASE_URL,
        )

        tts = CartesiaTTSService(
            api_key=os.environ["CARTESIA_API_KEY"],
            settings=CartesiaTTSService.Settings(
                voice=os.getenv("CARTESIA_VOICE_ID", _DEFAULT_CARTESIA_VOICE_ID),
            ),
        )

        # Build system prompt: base instructions + any loaded skills
        skills_content = load_skills(skills_dir)
        system_prompt = _BASE_SYSTEM_PROMPT
        if skills_content:
            system_prompt = f"{_BASE_SYSTEM_PROMPT}\n\n{skills_content}"

        context = OpenAILLMContext(
            messages=[{"role": "system", "content": system_prompt}]
        )
        context_aggregator = llm.create_context_aggregator(context)

        logger.info(
            f"VoiceClawPipeline: model={os.environ['LLM_MODEL']!r} "
            f"skills={'yes' if skills_content else 'none'}"
        )

        pipeline = Pipeline(
            [
                transport.input(),
                stt,
                context_aggregator.user(),
                llm,
                tts,
                transport.output(),
                context_aggregator.assistant(),
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
        """Cancel the pipeline task gracefully."""
        if self._task is not None:
            logger.info("VoiceClawPipeline: cancelling task")
            await self._task.cancel()
