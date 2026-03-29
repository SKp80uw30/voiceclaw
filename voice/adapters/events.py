#
# VoiceClaw — voice/adapters/events.py
# SPDX-License-Identifier: MIT
#

"""OrbState enum and pipeline observer that maps Pipecat frame types to orb states.

The observer attaches to a PipelineTask without modifying the pipeline itself.
When a relevant frame is seen it fires the on_state_change callback, which the
FastAPI server uses to push SSE events to the PWA.

Frame → OrbState mapping (canonical — mirrors voice/CLAUDE.md):

    VADUserStartedSpeakingFrame      → listening
    UserStoppedSpeakingFrame         → thinking
    LLMFullResponseStartFrame        → thinking  (confirms thinking after VAD stop)
    FunctionCallsStartedFrame        → tool_running
    FunctionCallInProgressFrame      → tool_running
    TTSStartedFrame                  → speaking
    TTSStoppedFrame                  → idle
    BotStoppedSpeakingFrame          → idle
    on_pipeline_started              → idle       (initial state on connect)
"""

from enum import Enum
from typing import Awaitable, Callable

from pipecat.frames.frames import (
    BotStoppedSpeakingFrame,
    FunctionCallInProgressFrame,
    FunctionCallsStartedFrame,
    LLMFullResponseStartFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
    UserStoppedSpeakingFrame,
    VADUserStartedSpeakingFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed


class OrbState(str, Enum):
    """Five states for the VoiceClaw floating orb UI.

    Using str mixin so values serialise directly to JSON in SSE events.
    """

    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    TOOL_RUNNING = "tool_running"
    SPEAKING = "speaking"


# Map from Pipecat frame type to the OrbState it triggers.
# Evaluated in on_push_frame; first match wins.
_FRAME_STATE_MAP: dict[type, OrbState] = {
    VADUserStartedSpeakingFrame: OrbState.LISTENING,
    UserStoppedSpeakingFrame: OrbState.THINKING,
    LLMFullResponseStartFrame: OrbState.THINKING,
    FunctionCallsStartedFrame: OrbState.TOOL_RUNNING,
    FunctionCallInProgressFrame: OrbState.TOOL_RUNNING,
    TTSStartedFrame: OrbState.SPEAKING,
    TTSStoppedFrame: OrbState.IDLE,
    BotStoppedSpeakingFrame: OrbState.IDLE,
}


class OrbStateObserver(BaseObserver):
    """Pipeline observer that fires on_state_change when orb-relevant frames pass through.

    Attach to PipelineTask via the observers= parameter. Does not modify the
    pipeline or intercept any frames.

    Event handlers available:

    - on_state_change(state: OrbState): Called whenever the orb state transitions.

    Example::

        observer = OrbStateObserver(on_state_change=handle_state)
        task = PipelineTask(pipeline, observers=[observer])
    """

    def __init__(
        self,
        on_state_change: Callable[[OrbState], Awaitable[None]],
    ):
        """Initialise the observer.

        Args:
            on_state_change: Async callback invoked on every state transition.
                Receives the new OrbState value.
        """
        super().__init__()
        self._on_state_change = on_state_change
        self._current_state: OrbState | None = None

    async def on_pipeline_started(self) -> None:
        """Set initial orb state to idle when the pipeline comes up."""
        await self._transition(OrbState.IDLE)

    async def on_push_frame(self, data: FramePushed) -> None:
        """Check each pushed frame against the mapping and fire transitions.

        Args:
            data: Frame transfer event from the pipeline.
        """
        new_state = _FRAME_STATE_MAP.get(type(data.frame))
        if new_state is not None:
            await self._transition(new_state)

    async def _transition(self, new_state: OrbState) -> None:
        """Fire the callback only when the state actually changes.

        Args:
            new_state: Candidate next state.
        """
        if new_state != self._current_state:
            self._current_state = new_state
            await self._on_state_change(new_state)
