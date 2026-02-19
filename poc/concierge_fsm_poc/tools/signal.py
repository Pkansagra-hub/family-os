"""Signal Tool -- Epic 2.1 (SIG-001).

``acknowledge()`` is the single signal tool. It emits intent confirmation to the
user BEFORE any effectful work begins.  Zero SessionState writes -- it is
intentionally side-effect-free on the knowledge graph.

I/O contract (aligned to existing PoC ``_handle_acknowledge`` and plan spec):

    Input:
        ack_type  : "commit" | "progress" | "closure"
        message   : User-facing text (max 150 tokens)
        next_tool : Name of next tool to call, or "none"

    Output dict:
        displayed         : True
        formatted_message : verbatim message string
        display_latency_ms: simulated display time (ms)

    Side effects:
        - Prints Rich Panel to console (styled by ack_type)
        - Appends to module-level _ack_log for test inspection

LLM JSON schema (Gemini function-calling compatible) is exposed as
``ACKNOWLEDGE_SCHEMA`` and consumed by ToolRegistry.
"""

from __future__ import annotations

import time
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# ---------------------------------------------------------------------------
# Module-level console + audit log (shared across calls within a session)
# ---------------------------------------------------------------------------

_console = Console()
_ack_log: list[dict[str, Any]] = []
_ack_called_this_turn: bool = False


def reset_ack_log() -> None:
    """Clear the audit log between test runs / demo sessions."""
    global _ack_called_this_turn
    _ack_log.clear()
    _ack_called_this_turn = False


def get_ack_log() -> list[dict[str, Any]]:
    """Return a copy of the current audit log (for tests and demo summary)."""
    return list(_ack_log)


# ---------------------------------------------------------------------------
# Visual style by ack_type
# ---------------------------------------------------------------------------

_ACK_STYLE: dict[str, tuple[str, str]] = {
    # (border_style, title_prefix)
    "commit": ("bold cyan", "COMMITTING"),
    "progress": ("bold yellow", "IN PROGRESS"),
    "closure": ("bold green", "DONE"),
}

_DISPLAY_LATENCY_MS = 45


# ---------------------------------------------------------------------------
# SIG-001: acknowledge()
# ---------------------------------------------------------------------------


def acknowledge(
    ack_type: str = "progress",
    message: str = "",
    next_tool: str = "none",
) -> dict[str, Any]:
    """Emit intent confirmation to the user before any effectful work.

    MUST be the first tool called in iteration 1.  Effectful tools without
    a preceding acknowledge are considered protocol violations.

    Args:
        ack_type: Semantic type -- ``"commit"`` (state change happening),
            ``"progress"`` (work starting), or ``"closure"`` (branch done).
        message: User-facing confirmation text. Kept under 150 tokens.
        next_tool: Name of the effectful tool to call next, or ``"none"``
            for text-only turns.

    Returns:
        ``{"displayed": True, "formatted_message": str, "display_latency_ms": int}``
    """
    global _ack_called_this_turn
    border, prefix = _ACK_STYLE.get(ack_type, ("blue", ack_type.upper()))
    title = f"[{border}][ACK: {prefix}]"
    if next_tool and next_tool != "none":
        title += f"  -> {next_tool}[/{border}]"

    # Only display the Rich Panel on the FIRST acknowledge per turn.
    # Subsequent calls are silently logged but not displayed, preventing
    # visual spam when the LLM calls acknowledge() multiple times.
    if not _ack_called_this_turn:
        body = Text(message, overflow="fold")
        _console.print(
            Panel(
                body,
                title=title,
                border_style=border,
                padding=(0, 1),
            )
        )
        _ack_called_this_turn = True

    entry: dict[str, Any] = {
        "ack_type": ack_type,
        "message": message,
        "next_tool": next_tool,
        "displayed": True,
        "display_latency_ms": _DISPLAY_LATENCY_MS,
        "timestamp_ms": int(time.time() * 1000),
    }
    _ack_log.append(entry)

    return {
        "displayed": True,
        "formatted_message": message,
        "display_latency_ms": _DISPLAY_LATENCY_MS,
    }


# ---------------------------------------------------------------------------
# Gemini-compatible JSON schema (consumed by ToolRegistry.get_llm_declarations)
# ---------------------------------------------------------------------------

ACKNOWLEDGE_SCHEMA: dict[str, Any] = {
    "name": "acknowledge",
    "description": (
        "Emit intent confirmation to the user before any effectful work. "
        "MUST be the first tool called in iteration 1. "
        "Effectful tools without a preceding acknowledge are REJECTED."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "ack_type": {
                "type": "string",
                "enum": ["commit", "progress", "closure"],
                "description": (
                    "commit: state change happening; "
                    "progress: work starting; "
                    "closure: branch complete"
                ),
            },
            "message": {
                "type": "string",
                "description": "User-facing confirmation text (max 150 tokens)",
            },
            "next_tool": {
                "type": "string",
                "description": (
                    "Name of the effectful tool to call next, or 'none' " "for text-only responses"
                ),
            },
        },
        "required": ["ack_type", "message", "next_tool"],
    },
}
