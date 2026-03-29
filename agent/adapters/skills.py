#
# VoiceClaw — agent/adapters/skills.py
# SPDX-License-Identifier: MIT
#

"""Voice Bridge Skill loader.

Scans the skills/ directory at the repo root for SKILL.md files and returns
their content to be prepended to OpenClaw chat messages as context.

Phase 1: loads ALL skills unconditionally.
Phase 2: intent-based selection — load only skills relevant to the transcript.

Skills directory layout (from repo root):
  skills/
    skill-builder/SKILL.md
    calendar-voice-bridge/SKILL.md
    email-voice-bridge/SKILL.md
    ...

Environment variables:
  VOICECLAW_SKILLS_DIR — override default skills directory path.
"""

import os
from pathlib import Path

from loguru import logger

_DEFAULT_SKILLS_RELATIVE_PATH = "skills"


def _default_skills_dir() -> Path:
    """Locate the skills/ directory relative to this file's repo root."""
    # agent/adapters/skills.py → agent/ → repo root
    repo_root = Path(__file__).parent.parent.parent
    return repo_root / _DEFAULT_SKILLS_RELATIVE_PATH


def load_skills(skills_dir: Path | None = None) -> str:
    """Load all SKILL.md files and return them as a single context string.

    Each skill is preceded by a header marking its name, so the agent can
    distinguish between them in the context.

    Args:
        skills_dir: Override the skills directory. Defaults to
            $VOICECLAW_SKILLS_DIR or skills/ at the repo root.

    Returns:
        A string containing all skill content, or an empty string if no
        skills are found.
    """
    resolved = skills_dir or Path(
        os.getenv("VOICECLAW_SKILLS_DIR", str(_default_skills_dir()))
    )

    if not resolved.exists():
        logger.warning(f"SkillLoader: skills directory not found: {resolved}")
        return ""

    skill_files = sorted(resolved.glob("*/SKILL.md"))
    if not skill_files:
        logger.debug(f"SkillLoader: no SKILL.md files found in {resolved}")
        return ""

    parts: list[str] = []
    for skill_path in skill_files:
        try:
            content = skill_path.read_text(encoding="utf-8").strip()
            skill_name = skill_path.parent.name
            parts.append(f"## Voice Bridge Skill: {skill_name}\n\n{content}")
            logger.debug(f"SkillLoader: loaded {skill_path.name} from {skill_name}/")
        except OSError as exc:
            logger.warning(f"SkillLoader: could not read {skill_path}: {exc}")

    if not parts:
        return ""

    header = (
        "The following Voice Bridge Skills are active. "
        "Use them to interpret the user's spoken intent and call the appropriate tools.\n\n"
    )
    return header + "\n\n---\n\n".join(parts)
