"""
poc.k1_poc.demo.spinner -- Streaming status feed for demo turns.

Shows a ChatGPT/Claude-style streaming progress feed during turn
processing.  Status messages appear one by one as internal events fire:

    [gear] Processing Turn 1
    [check] LLM generating (9.5s)
    [check] Tool: update_beliefs -> ok (0ms)
    [spin] Generating response... (3.2s)

The last line animates with a braille spinner.  When a new event
arrives, the current line is finalized with a checkmark and a new
spinner line begins.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import time
from typing import Any

from k1.bus.envelope import Envelope
from k1.bus.ports.bus import IBus
from poc.k1_poc.bus.topics import (
    TOPIC_FINAL_RESPONSE,
    TOPIC_RESPONSE_STREAM,
    TOPIC_STATE_UPDATED,
    TOPIC_TASK_COMPLETE,
    TOPIC_TASK_DISPATCH,
    TOPIC_TASK_FAILED,
    TOPIC_TASK_SUSPENDED,
    TOPIC_TOOL_COMPLETED,
    TOPIC_TOOL_STARTED,
    TOPIC_TURN_COMPLETED,
    TOPIC_WEAVE_BATCH,
)
from poc.k1_poc.demo.display import (
    ARROW_R,
    BLUE,
    CHECK,
    CYAN,
    GEAR,
    GRAY,
    GREEN,
    MAGENTA,
    YELLOW,
    colorize,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SPINNER_FRAMES = [
    "\u280b",
    "\u2819",
    "\u2839",
    "\u2838",
    "\u283c",
    "\u2834",
    "\u2826",
    "\u2827",
    "\u2807",
    "\u280f",
]

SPINNER_INTERVAL_S = 0.08

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")

# Human-readable labels for FSM states
_FSM_LABELS: dict[str, tuple[str, str]] = {
    "LISTENING": ("Listening", CYAN),
    "DISPATCHING": ("LLM generating", GREEN),
    "COMPANIONING": ("LLM generating", GREEN),
    "PROGRESSING": ("Executing tools", MAGENTA),
    "DELIVERING": ("Preparing response", GREEN),
    "WEAVING": ("Weaving results", CYAN),
    "CLARIFYING_WORKER": ("Waiting for user (HITL)", YELLOW),
    "PROACTIVE_WAKE": ("Proactive update", CYAN),
}


# ---------------------------------------------------------------------------
# LiveStatusSpinner
# ---------------------------------------------------------------------------


class LiveStatusSpinner:
    """Streaming status feed with animated spinner on the active line.

    Each internal event (FSM transition, tool call, task lifecycle)
    prints a completed checkmark line and starts a new spinner line,
    producing a ChatGPT/Claude-style streaming progress display.
    """

    __slots__ = (
        "_bus",
        "_subscriptions",
        "_running",
        "_task",
        "_frame_idx",
        "_current_text",
        "_event_start_ns",
        "_start_ns",
        "_line_len",
        "_saved_log_level",
        "_turn",
    )

    def __init__(self, bus: IBus) -> None:
        self._bus = bus
        self._subscriptions: list[Any] = []
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._frame_idx = 0
        self._current_text = ""
        self._event_start_ns = 0
        self._start_ns = 0
        self._line_len = 0
        self._saved_log_level: int | None = None
        self._turn = 0

    # -----------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------

    def start(self, *, turn: int = 0) -> None:
        """Begin the streaming status feed.

        Prints a header, subscribes to bus topics, and starts the
        spinner animation task.  Raises root logger to CRITICAL so
        log lines do not interleave with the feed.
        """
        if self._running:
            return
        self._running = True
        self._turn = turn
        self._start_ns = time.monotonic_ns()
        self._event_start_ns = self._start_ns
        self._frame_idx = 0
        self._current_text = colorize("LLM generating", GREEN)
        self._line_len = 0

        # Log suppression disabled for debugging -- see original below.
        # root = logging.getLogger()
        # self._saved_log_level = root.level
        # if root.level < logging.CRITICAL:
        #     root.setLevel(logging.CRITICAL)
        self._saved_log_level = None

        # Print header
        hdr = f"  {colorize(GEAR, CYAN)} {colorize('Processing', CYAN, bold=True)}"
        if turn:
            hdr += colorize(f" Turn {turn}", GRAY)
        sys.stdout.write(hdr + "\n")
        sys.stdout.flush()

        self._subscribe()
        try:
            loop = asyncio.get_running_loop()
            self._task = loop.create_task(self._animate())
        except RuntimeError:
            pass  # No event loop -- sync test mode

    def stop(self) -> None:
        """Stop animation, commit the last line, restore logging."""
        if not self._running:
            return
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
        self._unsubscribe()

        # Commit whatever is currently spinning
        self._commit_current()

        # Restore original log level
        if self._saved_log_level is not None:
            logging.getLogger().setLevel(self._saved_log_level)
            self._saved_log_level = None

    def finish(self, *, response_chars: int = 0) -> None:
        """Stop the spinner and print a 'Response ready' footer.

        Call this instead of stop() when a response has been received
        so the feed ends with a clean summary line.
        """
        if not self._running:
            return
        self.stop()
        suffix = f" ({response_chars} chars)" if response_chars else ""
        done = colorize(f"Response ready{suffix}", GREEN, bold=True)
        sys.stdout.write(f"  {colorize(CHECK, GREEN)} {done}\n")
        sys.stdout.flush()

    async def __aenter__(self) -> "LiveStatusSpinner":
        self.start()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        self.stop()

    # -----------------------------------------------------------------
    # Animation loop
    # -----------------------------------------------------------------

    async def _animate(self) -> None:
        """Redraw the spinner on the current line at SPINNER_INTERVAL_S."""
        try:
            while self._running:
                self._render()
                await asyncio.sleep(SPINNER_INTERVAL_S)
        except asyncio.CancelledError:
            pass

    def _render(self) -> None:
        """Write one spinner frame (overwrites the current line)."""
        frame = SPINNER_FRAMES[self._frame_idx % len(SPINNER_FRAMES)]
        self._frame_idx += 1

        elapsed = (time.monotonic_ns() - self._event_start_ns) / 1e9

        parts = [f"  {colorize(frame, CYAN, bold=True)} {self._current_text}"]
        if elapsed >= 1.0:
            parts.append(f" {colorize(f'({elapsed:.1f}s)', GRAY)}")

        line = "".join(parts)
        visible = len(_ANSI_RE.sub("", line))

        sys.stdout.write(f"\r{line}")
        if visible < self._line_len:
            sys.stdout.write(" " * (self._line_len - visible))
        sys.stdout.flush()
        self._line_len = visible

    def _clear_line(self) -> None:
        """Clear the current spinner line completely."""
        if self._line_len > 0:
            sys.stdout.write("\r" + " " * (self._line_len + 5) + "\r")
            sys.stdout.flush()
            self._line_len = 0

    # -----------------------------------------------------------------
    # Status update helpers
    # -----------------------------------------------------------------

    def _commit_current(self, *, override_text: str | None = None) -> None:
        """Finalize the active spinner line with a checkmark.

        Replaces the spinning character with CHECK and appends
        elapsed time if the activity took more than 0.5 seconds.
        """
        text = override_text if override_text is not None else self._current_text
        if not text:
            return
        self._clear_line()
        elapsed = (time.monotonic_ns() - self._event_start_ns) / 1e9
        parts = [f"  {colorize(CHECK, GREEN)} {text}"]
        if elapsed >= 0.5:
            parts.append(f" {colorize(f'({elapsed:.1f}s)', GRAY)}")
        sys.stdout.write("".join(parts) + "\n")
        sys.stdout.flush()
        self._line_len = 0

    def _set_activity(self, text: str, *, commit_text: str | None = None) -> None:
        """Commit the current line and start a new spinning activity.

        Parameters
        ----------
        text:
            The label for the new activity (will be the spinner line).
        commit_text:
            Optional override for the line being committed.  Use this
            when the completed text differs from what was spinning
            (e.g. adding a tool result suffix).
        """
        self._commit_current(override_text=commit_text)
        self._current_text = text
        self._event_start_ns = time.monotonic_ns()
        if self._running:
            self._render()

    def _insert_line(self, text: str) -> None:
        """Insert a completed checkmark line without changing the spinner.

        The current spinner text stays the same; the inserted line
        appears above it.
        """
        self._clear_line()
        sys.stdout.write(f"  {colorize(CHECK, GREEN)} {text}\n")
        sys.stdout.flush()
        self._line_len = 0
        if self._running and self._current_text:
            self._render()

    # -----------------------------------------------------------------
    # Bus subscriptions
    # -----------------------------------------------------------------

    def _subscribe(self) -> None:
        handlers = {
            TOPIC_STATE_UPDATED: self._on_state_updated,
            TOPIC_TOOL_STARTED: self._on_tool_started,
            TOPIC_TOOL_COMPLETED: self._on_tool_completed,
            TOPIC_TASK_DISPATCH: self._on_task_dispatch,
            TOPIC_TASK_COMPLETE: self._on_task_complete,
            TOPIC_TASK_FAILED: self._on_task_failed,
            TOPIC_TASK_SUSPENDED: self._on_task_suspended,
            TOPIC_FINAL_RESPONSE: self._on_response,
            TOPIC_WEAVE_BATCH: self._on_response,
            TOPIC_TURN_COMPLETED: self._on_response,
            TOPIC_RESPONSE_STREAM: self._on_stream,
        }
        for topic, handler in handlers.items():
            sub = self._bus.subscribe(topic, handler)
            self._subscriptions.append(sub)

    def _unsubscribe(self) -> None:
        for sub in self._subscriptions:
            try:
                self._bus.unsubscribe(sub)
            except Exception:
                pass
        self._subscriptions.clear()

    # -----------------------------------------------------------------
    # Event handlers
    # -----------------------------------------------------------------

    def _parse(self, envelope: Envelope) -> dict[str, Any]:
        try:
            if envelope.payload:
                return json.loads(envelope.payload)
        except Exception:
            pass
        return {}

    def _on_state_updated(self, envelope: Envelope) -> None:
        p = self._parse(envelope)
        to_state = p.get("to_state", "")
        if not to_state or to_state == "LISTENING":
            return  # skip end-state
        label, color = _FSM_LABELS.get(to_state, (to_state, GRAY))
        self._set_activity(colorize(label, color))

    def _on_tool_started(self, envelope: Envelope) -> None:
        p = self._parse(envelope)
        tool = p.get("tool_name", "?")
        self._set_activity(f"Tool: {colorize(tool, MAGENTA)}")

    def _on_tool_completed(self, envelope: Envelope) -> None:
        p = self._parse(envelope)
        tool = p.get("tool_name", "?")
        dur = p.get("duration_ms", 0)
        ok = p.get("success", True)
        status = colorize("ok", GREEN) if ok else colorize("FAIL", "\033[91m")
        # Commit tool line with result, then move to generating
        self._set_activity(
            colorize("Generating response", GREEN),
            commit_text=(
                f"Tool: {colorize(tool, MAGENTA)} " f"{colorize(ARROW_R, GRAY)} {status} ({dur}ms)"
            ),
        )

    def _on_task_dispatch(self, envelope: Envelope) -> None:
        p = self._parse(envelope)
        intents = p.get("intents", [])
        if intents:
            actions = [i.get("action", "?") for i in intents[:3]]
            text = ", ".join(colorize(a, BLUE) for a in actions)
            self._insert_line(f"Dispatched: {text}")

    def _on_task_complete(self, envelope: Envelope) -> None:
        p = self._parse(envelope)
        task_id = p.get("task_id", "?")
        self._insert_line(f"Task done: {colorize(task_id, GREEN)}")

    def _on_task_failed(self, envelope: Envelope) -> None:
        p = self._parse(envelope)
        task_id = p.get("task_id", "?")
        error = p.get("error_code", "?")
        self._insert_line(
            f"Task failed: {colorize(task_id + ' (' + error + ')', chr(27) + '[91m')}"
        )

    def _on_task_suspended(self, envelope: Envelope) -> None:
        p = self._parse(envelope)
        task_id = p.get("task_id", "?")
        self._set_activity(colorize(f"Waiting for user: {task_id}", YELLOW))

    def _on_response(self, envelope: Envelope) -> None:
        """Final response / weave -- silently update text.

        The output channel calls finish() before rendering the
        CONCIERGE response, so this handler is a no-op in the
        normal flow.  It exists as a safety net in case finish()
        was not called.
        """
        if not self._running:
            return
        # Just update the spinning text -- stop()/finish() will commit
        self._current_text = colorize("Response ready", GREEN, bold=True)
        self._event_start_ns = time.monotonic_ns()

    def _on_stream(self, envelope: Envelope) -> None:
        """Show streaming thinking/text chunks on the spinner line."""
        if not self._running:
            return
        p = self._parse(envelope)
        chunk_type = p.get("chunk_type", "text")
        text = p.get("text", "")
        if not text:
            return
        # Show a truncated preview of the thinking/text content
        preview = text.replace("\n", " ")[:60]
        if chunk_type == "thinking":
            label = colorize(f"Thinking: {preview}", GRAY)
        else:
            label = colorize(f"Streaming: {preview}", GREEN)
        # Update spinner text without committing the previous line
        # (stream chunks arrive rapidly; we just update in place)
        self._current_text = label
        self._event_start_ns = time.monotonic_ns()
