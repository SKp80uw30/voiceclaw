#
# VoiceClaw — voice/adapters/tests/test_events.py
# SPDX-License-Identifier: MIT
#

"""Tests for OrbStateObserver and OrbState transitions.

Uses Pipecat's test utilities to construct minimal FramePushed events and
verify the observer fires the correct OrbState for each mapped frame type.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.events import OrbState, OrbStateObserver
from pipecat.frames.frames import (
    BotStoppedSpeakingFrame,
    FunctionCallFromLLM,
    FunctionCallInProgressFrame,
    FunctionCallsStartedFrame,
    LLMFullResponseStartFrame,
    TextFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
    UserStoppedSpeakingFrame,
    VADUserStartedSpeakingFrame,
)
from pipecat.observers.base_observer import FramePushed
from pipecat.processors.frame_processor import FrameDirection


def _make_pushed(frame) -> FramePushed:
    """Build a minimal FramePushed event for the given frame."""
    src = MagicMock()
    dst = MagicMock()
    return FramePushed(
        source=src,
        destination=dst,
        frame=frame,
        direction=FrameDirection.DOWNSTREAM,
        timestamp=0,
    )


@pytest.mark.asyncio
async def test_pipeline_started_sets_idle():
    callback = AsyncMock()
    observer = OrbStateObserver(on_state_change=callback)

    await observer.on_pipeline_started()

    callback.assert_awaited_once_with(OrbState.IDLE)


@pytest.mark.parametrize(
    "frame_cls, expected_state",
    [
        (VADUserStartedSpeakingFrame, OrbState.LISTENING),
        (UserStoppedSpeakingFrame, OrbState.THINKING),
        (LLMFullResponseStartFrame, OrbState.THINKING),
        (
            lambda: FunctionCallsStartedFrame(
                function_calls=[FunctionCallFromLLM("test_fn", "call_1", {}, None)]
            ),
            OrbState.TOOL_RUNNING,
        ),
        (
            lambda: FunctionCallInProgressFrame(
                function_name="test_fn", tool_call_id="call_1", arguments={}
            ),
            OrbState.TOOL_RUNNING,
        ),
        (TTSStartedFrame, OrbState.SPEAKING),
        (TTSStoppedFrame, OrbState.IDLE),
        (BotStoppedSpeakingFrame, OrbState.IDLE),
    ],
)
@pytest.mark.asyncio
async def test_frame_triggers_correct_state(frame_cls, expected_state):
    callback = AsyncMock()
    observer = OrbStateObserver(on_state_change=callback)

    await observer.on_push_frame(_make_pushed(frame_cls()))

    callback.assert_awaited_once_with(expected_state)


@pytest.mark.asyncio
async def test_unmapped_frame_does_not_fire_callback():
    callback = AsyncMock()
    observer = OrbStateObserver(on_state_change=callback)

    await observer.on_push_frame(_make_pushed(TextFrame("hello")))

    callback.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_state_does_not_fire_callback_twice():
    """Callback must not fire when state does not actually change."""
    callback = AsyncMock()
    observer = OrbStateObserver(on_state_change=callback)

    await observer.on_push_frame(_make_pushed(TTSStartedFrame()))
    await observer.on_push_frame(_make_pushed(TTSStartedFrame()))

    # Only the first transition should fire
    assert callback.await_count == 1


@pytest.mark.asyncio
async def test_full_conversation_state_sequence():
    """Verify a typical listening→thinking→speaking→idle sequence."""
    states: list[OrbState] = []

    async def capture(state: OrbState) -> None:
        states.append(state)

    observer = OrbStateObserver(on_state_change=capture)

    await observer.on_pipeline_started()
    await observer.on_push_frame(_make_pushed(VADUserStartedSpeakingFrame()))
    await observer.on_push_frame(_make_pushed(UserStoppedSpeakingFrame()))
    await observer.on_push_frame(_make_pushed(TTSStartedFrame()))
    await observer.on_push_frame(_make_pushed(TTSStoppedFrame()))

    assert states == [
        OrbState.IDLE,
        OrbState.LISTENING,
        OrbState.THINKING,
        OrbState.SPEAKING,
        OrbState.IDLE,
    ]
