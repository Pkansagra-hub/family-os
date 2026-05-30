"""Prompt dump path helpers.

Prompt dumps are intentionally grouped by session and actor so postmortems can
inspect one conversation without root-folder noise from other sessions.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

PROMPT_DUMP_ROOT = Path(__file__).resolve().parents[2] / "data" / "prompt_dumps"

_SAFE_SEGMENT_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def prompt_dump_segment(value: Any, *, default: str) -> str:
    """Return a filesystem-safe folder or filename segment."""
    raw = str(value or "").strip() or default
    segment = _SAFE_SEGMENT_RE.sub("_", raw).strip("._-")
    return (segment or default)[:120]


def prompt_dump_dir(root: Path, *, session_id: str | None, actor: str) -> Path:
    """Return the per-session, per-actor prompt dump directory."""
    session_segment = prompt_dump_segment(session_id, default="no_session")
    actor_segment = prompt_dump_segment(actor, default="unknown")
    return root / session_segment / actor_segment
