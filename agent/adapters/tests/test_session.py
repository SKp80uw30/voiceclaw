#
# VoiceClaw — agent/adapters/tests/test_session.py
# SPDX-License-Identifier: MIT
#

"""Tests for VoiceClawSession — session key derivation and message building."""

from adapters.session import _build_message, _session_key_from_connection_id


def test_session_key_includes_connection_id():
    key = _session_key_from_connection_id("abc123")
    assert "abc123" in key


def test_session_key_max_64_chars():
    long_id = "x" * 100
    key = _session_key_from_connection_id(long_id)
    assert len(key) <= 64


def test_session_key_has_voiceclaw_prefix():
    key = _session_key_from_connection_id("myconn")
    assert key.startswith("voiceclaw-")


def test_build_message_no_skills():
    msg = _build_message("", "hello world")
    assert msg == "hello world"


def test_build_message_with_skills_contains_transcript():
    msg = _build_message("skill context here", "schedule a meeting")
    assert "schedule a meeting" in msg
    assert "skill context here" in msg


def test_build_message_with_skills_separates_sections():
    msg = _build_message("skill context here", "schedule a meeting")
    assert "---" in msg
    assert "User said:" in msg
