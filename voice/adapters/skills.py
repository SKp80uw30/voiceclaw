#
# VoiceClaw — voice/adapters/skills.py
# SPDX-License-Identifier: MIT
#

"""Voice Bridge Skill loader.

Scans the skills/ directory at the repo root for SKILL.md files and returns
their concatenated content as a system prompt string to inject into the LLM.

Each skill lives in its own subdirectory:
    skills/
        calendar-voice-bridge/SKILL.md
        skill-builder/SKILL.md

All SKILL.md files are concatenated in alphabetical order. Empty or missing
skills directories produce an empty string (no system prompt addition).
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

# Default: skills/ at the repo root (two levels up from this file).
_DEFAULT_SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"


def load_skills(skills_dir: Path | None = None) -> str:
    """Load and concatenate all SKILL.md files from the skills directory.

    Args:
        skills_dir: Path to the skills directory. Defaults to skills/ at repo root.

    Returns:
        Concatenated skill content as a single string, or empty string if none found.
    """
    directory = skills_dir or _DEFAULT_SKILLS_DIR

    if not directory.exists():
        logger.debug(f"Skills directory not found: {directory} — no skills loaded")
        return ""

    skill_files = sorted(directory.glob("*/SKILL.md"))

    if not skill_files:
        logger.debug(f"No SKILL.md files found in {directory}")
        return ""

    parts: list[str] = []
    for path in skill_files:
        try:
            content = path.read_text(encoding="utf-8").strip()
            if content:
                parts.append(content)
                logger.debug(f"Loaded skill: {path.parent.name}")
        except OSError as e:
            logger.warning(f"Could not read {path}: {e}")

    result = "\n\n---\n\n".join(parts)
    logger.info(f"Loaded {len(parts)} skill(s) from {directory}")
    return result
