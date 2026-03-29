#
# VoiceClaw — agent/adapters/tests/test_skills.py
# SPDX-License-Identifier: MIT
#

"""Tests for the Voice Bridge Skill loader."""

from pathlib import Path

from adapters.session import _build_message
from adapters.skills import load_skills


def _write_skill(skills_dir: Path, name: str, content: str) -> None:
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(content)


def test_load_skills_returns_empty_for_missing_dir(tmp_path):
    result = load_skills(tmp_path / "nonexistent")
    assert result == ""


def test_load_skills_returns_empty_when_no_skill_files(tmp_path):
    result = load_skills(tmp_path)
    assert result == ""


def test_load_skills_loads_single_skill(tmp_path):
    _write_skill(tmp_path, "calendar-voice-bridge", "# Calendar Skill\nBook meetings.")
    result = load_skills(tmp_path)
    assert "calendar-voice-bridge" in result
    assert "Book meetings." in result


def test_load_skills_loads_multiple_skills(tmp_path):
    _write_skill(tmp_path, "calendar-voice-bridge", "Calendar content")
    _write_skill(tmp_path, "email-voice-bridge", "Email content")
    result = load_skills(tmp_path)
    assert "calendar-voice-bridge" in result
    assert "email-voice-bridge" in result
    assert "Calendar content" in result
    assert "Email content" in result


def test_load_skills_includes_header(tmp_path):
    _write_skill(tmp_path, "my-skill", "Skill content")
    result = load_skills(tmp_path)
    assert "Voice Bridge Skill" in result


def test_load_skills_sorted_alphabetically(tmp_path):
    _write_skill(tmp_path, "zzz-skill", "ZZZ content")
    _write_skill(tmp_path, "aaa-skill", "AAA content")
    result = load_skills(tmp_path)
    aaa_pos = result.index("aaa-skill")
    zzz_pos = result.index("zzz-skill")
    assert aaa_pos < zzz_pos


def test_build_message_with_skills():
    msg = _build_message("Skill context", "set a meeting tomorrow")
    assert "Skill context" in msg
    assert "set a meeting tomorrow" in msg
    assert "User said:" in msg


def test_build_message_without_skills():
    msg = _build_message("", "just a transcript")
    assert msg == "just a transcript"
