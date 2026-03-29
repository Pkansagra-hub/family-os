"""
poc.k1_poc.demo.output_channel -- Bus-subscribed response renderer.

Subscribes to response topics on the K1 bus and renders them to the
console (or any pluggable renderer).  Also collects a timeline log of
every bus event for UI teams to visualize internal system activity.

Tracks per-turn data (FSM transitions, tool calls, session state ops)
and prints the anniversary-demo-style System Activity box after each
final response.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Protocol

from k1.bus.envelope import Envelope
from k1.bus.ports.bus import IBus
from poc.k1_poc.bus.topics import (
    TOPIC_AFFECT_UPDATE,
    TOPIC_ARTIFACT_CREATED,
    TOPIC_CLARIFICATION_OUT,
    TOPIC_FINAL_RESPONSE,
    TOPIC_PROACTIVE_FILL,
    TOPIC_RESPONSE_STREAM,
    TOPIC_STATE_UPDATED,
    TOPIC_TASK_COMPLETE,
    TOPIC_TASK_DISPATCH,
    TOPIC_TASK_FAILED,
    TOPIC_TASK_SUSPENDED,
    TOPIC_TOOL_COMPLETED,
    TOPIC_TOOL_STARTED,
    TOPIC_TURN_COMPLETED,
    TOPIC_TURN_STARTED,
    TOPIC_USER_INPUT,
    TOPIC_WEAVE_BATCH,
)
from poc.k1_poc.demo.display import (
    print_concierge_message,
    print_system_activity,
    print_system_message,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pluggable renderer protocol
# ---------------------------------------------------------------------------


class IRenderer(Protocol):
    """Pluggable output renderer -- swap console for web, TUI, etc."""

    def render_response(self, text: str, member: str, affect: str) -> None: ...
    def render_proactive(self, text: str) -> None: ...
    def render_weave(self, texts: list[str]) -> None: ...
    def render_system(self, text: str) -> None: ...
    def render_stream_chunk(self, text: str, chunk_type: str) -> None: ...


# ---------------------------------------------------------------------------
# Timeline log entry -- every bus event becomes a timeline entry for UI
# ---------------------------------------------------------------------------


@dataclass
class TimelineEntry:
    """Single entry in the timeline log -- consumed by UI visualizer."""

    timestamp_iso: str
    elapsed_ms: float
    phase: str  # "input" | "ack" | "dispatch" | "tool" | "result" | "response" | "state"
    component: str  # "front" | "back" | "fsm" | "bus" | "iot" | "output"
    event: str  # topic or short label
    summary: str  # human-readable one-liner
    envelope_id: int = 0
    parent_id: int = 0
    payload_excerpt: Dict[str, Any] = field(default_factory=dict)
    turn_number: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ts": self.timestamp_iso,
            "elapsed_ms": self.elapsed_ms,
            "phase": self.phase,
            "component": self.component,
            "event": self.event,
            "summary": self.summary,
            "envelope_id": self.envelope_id,
            "parent_id": self.parent_id,
            "payload": self.payload_excerpt,
            "turn": self.turn_number,
        }


# ---------------------------------------------------------------------------
# Console renderer (default)
# ---------------------------------------------------------------------------

AFFECT_INDICATORS = {
    "calm": "",
    "warm": "",
    "anxious": " [sensing stress]",
    "urgent": " [!]",
    "playful": " :)",
    "empathetic": " <3",
}


class ConsoleRenderer:
    """Render responses to stdout in anniversary demo style."""

    supports_immediate_proactive: bool = False

    def __init__(self, *, animated: bool = False) -> None:
        self.animated = animated

    def render_response(self, text: str, member: str, affect: str) -> None:
        if self.animated:
            from poc.k1_poc.demo.display import print_concierge_message_animated

            print_concierge_message_animated(text)
        else:
            print_concierge_message(text)

    def render_proactive(self, text: str) -> None:
        print_concierge_message(f"[proactive] {text}")

    def render_weave(self, texts: list[str]) -> None:
        print_concierge_message("[woven update]\n" + "\n".join(texts))

    def render_system(self, text: str) -> None:
        print_system_message(text)

    def render_stream_chunk(self, text: str, chunk_type: str) -> None:
        """Render a streaming chunk -- skip in console (spinner handles it)."""
        # Console renderer intentionally no-ops here: the LiveStatusSpinner
        # already shows a live preview, and direct stdout writes would
        # corrupt the spinner display.  WebSocket renderer overrides this.
        pass


# ---------------------------------------------------------------------------
# OutputChannel -- wired to the bus
# ---------------------------------------------------------------------------


class OutputChannel:
    """
    Subscribes to K1 bus response/state topics, renders to a pluggable
    renderer, and maintains a full timeline log for UI visualization.

    The timeline captures every interesting bus event with timestamps,
    component attribution, and payload excerpts so that a UI team can
    render an internal-components timeline view.
    """

    def __init__(
        self,
        bus: IBus,
        renderer: IRenderer | None = None,
        *,
        current_member: str = "Alex",
        enable_spinner: bool = True,
    ) -> None:
        self._bus = bus
        self._renderer: IRenderer = renderer or ConsoleRenderer()
        self._current_member = current_member
        self._boot_time_ns = time.monotonic_ns()
        self._timeline: List[TimelineEntry] = []
        self._turn_number = 0
        self._response_event: asyncio.Event = asyncio.Event()
        self._last_response_text: str = ""
        self._subscriptions: list[Any] = []
        self._enable_spinner = enable_spinner
        self._spinner: Any = None  # LiveStatusSpinner, lazy-created

        # Per-turn tracking for system activity box
        self._turn_start_ns: int = 0
        self._turn_session_ops: List[str] = []
        self._turn_tool_calls: List[str] = []
        self._turn_state_changes: Dict[str, Any] = {}
        self._turn_fsm_states: List[str] = []
        self._turn_bytes_in: int = 0
        self._turn_bytes_out: int = 0

        # Turn-active flag: True from user.input until FSM returns to
        # LISTENING.  Used to determine whether a FINAL_RESPONSE is part
        # of the active turn (render immediately) or truly proactive
        # (task completed while user was idle).  Replaces the old
        # _response_event.is_set() heuristic which misdetected in-turn
        # PRESENT/HITL responses as proactive.
        self._turn_active: bool = False

        # Weave buffer: when a task completes and the user is at the
        # input prompt (_turn_active == False), the PRESENT/WEAVE
        # response is buffered here instead of being printed to stdout
        # immediately (which would corrupt the user's typing).  The
        # interactive loop flushes this buffer at the START of the next
        # turn, before the front LLM runs, so the information is folded
        # into the conversation naturally.
        self._pending_weave_texts: list[str] = []

    # -- public API --------------------------------------------------------

    @property
    def timeline(self) -> List[TimelineEntry]:
        """Full timeline log -- read by UI teams."""
        return list(self._timeline)

    @property
    def timeline_dicts(self) -> List[Dict[str, Any]]:
        """Timeline as list of plain dicts (JSON-serializable)."""
        return [e.to_dict() for e in self._timeline]

    def set_member(self, member: str) -> None:
        self._current_member = member

    def set_turn(self, turn: int) -> None:
        self._turn_number = turn

    def set_animated(self, enabled: bool) -> None:
        """Enable or disable animated rendering for video recording."""
        if hasattr(self._renderer, "animated"):
            self._renderer.animated = enabled

    def has_pending_weaves(self) -> bool:
        """True if buffered weave results are waiting for display."""
        return len(self._pending_weave_texts) > 0

    def flush_pending_weaves(self) -> list[str]:
        """Return and clear all buffered weave texts.

        Called by the interactive loop at the START of a new turn so
        the user sees the weave results BEFORE the next Concierge
        response (and their typing is never interrupted).
        """
        texts = list(self._pending_weave_texts)
        self._pending_weave_texts.clear()
        return texts

    def start_turn(self, turn: int) -> None:
        """Reset per-turn tracking for a new turn."""
        self._turn_number = turn
        self._turn_start_ns = time.monotonic_ns()
        self._turn_session_ops.clear()
        self._turn_tool_calls.clear()
        self._turn_state_changes.clear()
        self._turn_fsm_states.clear()
        self._turn_bytes_in = 0
        self._turn_bytes_out = 0

        # Start spinner early so it catches FSM state transitions
        # that happen synchronously during bus.publish(user_input).
        if self._enable_spinner:
            self._start_spinner()

    def _flush_system_activity(self) -> None:
        """Print the system activity box with data collected this turn.

        Skipped when the spinner is disabled (web mode) -- the web UI
        receives activity data via send_activity() over WebSocket.
        """
        if not self._enable_spinner:
            return

        latency_ms = (
            int((time.monotonic_ns() - self._turn_start_ns) / 1_000_000)
            if self._turn_start_ns
            else 0
        )
        bytes_delta = self._turn_bytes_in + self._turn_bytes_out

        print_system_activity(
            turn_num=self._turn_number,
            session_ops=list(self._turn_session_ops),
            tool_calls=list(self._turn_tool_calls),
            state_changes=dict(self._turn_state_changes),
            bytes_delta=bytes_delta,
            latency_ms=latency_ms,
        )

    async def wait_for_response(self, timeout: float = 60.0) -> str:
        """Block until a FINAL_RESPONSE or WEAVE_BATCH arrives.

        While waiting, a LiveStatusSpinner shows real-time internal
        activity (FSM state, tool calls, task lifecycle) so the user
        sees progress even without debug logs.
        """
        self._response_event.clear()

        logger.info("OUTPUT: wait_for_response called (timeout=%.1fs)", timeout)

        try:
            await asyncio.wait_for(self._response_event.wait(), timeout=timeout)
            logger.info(
                "OUTPUT: response received -- text_len=%d",
                len(self._last_response_text),
            )
        except asyncio.TimeoutError:
            logger.warning("OUTPUT: response TIMEOUT after %.1fs", timeout)
            self._renderer.render_system("(response timeout)")
        finally:
            # Always stop spinner before rendering response
            if self._enable_spinner:
                self._stop_spinner()

        return self._last_response_text

    def drain_pending_back_results(self) -> List[Dict[str, Any]]:
        """Legacy API -- returns empty list.

        Back-task results are now rendered directly via PRESENT/WEAVE
        mode as they arrive (V2 Section 8.10).  No queuing.
        """
        return []

    def has_pending_back_results(self) -> bool:
        """Legacy API -- always False.  Results render directly now."""
        return False

    def _start_spinner(self) -> None:
        """Create and start the live status spinner."""
        try:
            from poc.k1_poc.demo.spinner import LiveStatusSpinner

            self._spinner = LiveStatusSpinner(self._bus)
            self._spinner.start(turn=self._turn_number)
        except Exception:
            logger.debug("Failed to start spinner", exc_info=True)
            self._spinner = None

    def _stop_spinner(self) -> None:
        """Stop and discard the live status spinner."""
        if self._spinner is not None:
            try:
                self._spinner.stop()
            except Exception:
                pass
            self._spinner = None

    def _finish_spinner(self, *, response_chars: int = 0) -> None:
        """Stop the spinner with a 'Response ready' footer."""
        if self._spinner is not None:
            try:
                self._spinner.finish(response_chars=response_chars)
            except Exception:
                pass
            self._spinner = None

    def restart_for_back_wait(self) -> None:
        """Restart spinner and tracking for awaiting back task results.

        Called by _process_turn() after the front response is rendered
        but before the back result arrives. This keeps the spinner
        active so the user sees progress during the back wait.
        """
        self._turn_start_ns = time.monotonic_ns()
        self._turn_session_ops.clear()
        self._turn_tool_calls.clear()
        self._turn_state_changes.clear()
        self._turn_bytes_in = 0
        self._turn_bytes_out = 0
        if self._enable_spinner:
            self._start_spinner()

    def subscribe_all(self) -> None:
        """Subscribe to all topics that should appear in the timeline."""
        topic_handler_map = {
            TOPIC_USER_INPUT: self._on_user_input,
            TOPIC_FINAL_RESPONSE: self._on_final_response,
            TOPIC_PROACTIVE_FILL: self._on_proactive,
            TOPIC_WEAVE_BATCH: self._on_weave,
            TOPIC_CLARIFICATION_OUT: self._on_clarification,
            TOPIC_STATE_UPDATED: self._on_state_updated,
            TOPIC_TURN_STARTED: self._on_turn_started,
            TOPIC_TURN_COMPLETED: self._on_turn_completed,
            TOPIC_TASK_DISPATCH: self._on_task_dispatch,
            TOPIC_TASK_COMPLETE: self._on_task_complete,
            TOPIC_TASK_FAILED: self._on_task_failed,
            TOPIC_TASK_SUSPENDED: self._on_task_suspended,
            TOPIC_TOOL_STARTED: self._on_tool_started,
            TOPIC_TOOL_COMPLETED: self._on_tool_completed,
            TOPIC_AFFECT_UPDATE: self._on_affect_update,
            TOPIC_ARTIFACT_CREATED: self._on_artifact_created,
            TOPIC_RESPONSE_STREAM: self._on_stream_chunk,
        }
        for topic, handler in topic_handler_map.items():
            sub = self._bus.subscribe(topic, handler)
            self._subscriptions.append(sub)

    def teardown(self) -> None:
        """Unsubscribe from all topics."""
        for sub in self._subscriptions:
            try:
                self._bus.unsubscribe(sub)
            except Exception:
                pass
        self._subscriptions.clear()

    def dump_timeline_json(self) -> str:
        """Serialize full timeline to JSON string."""
        return json.dumps(self.timeline_dicts, indent=2)

    # -- internal: timeline recording --------------------------------------

    def _elapsed_ms(self) -> float:
        return (time.monotonic_ns() - self._boot_time_ns) / 1_000_000

    def _record(
        self,
        phase: str,
        component: str,
        event: str,
        summary: str,
        envelope: Envelope | None = None,
        payload_excerpt: Dict[str, Any] | None = None,
    ) -> TimelineEntry:
        entry = TimelineEntry(
            timestamp_iso=datetime.now(timezone.utc).isoformat(),
            elapsed_ms=round(self._elapsed_ms(), 2),
            phase=phase,
            component=component,
            event=event,
            summary=summary,
            envelope_id=envelope.envelope_id if envelope else 0,
            parent_id=envelope.parent_id if envelope else 0,
            payload_excerpt=payload_excerpt or {},
            turn_number=self._turn_number,
        )
        self._timeline.append(entry)
        logger.info(
            "OUTPUT [%8.1fms] %-10s %-10s env_id=%-6d parent=%-6d %s",
            entry.elapsed_ms,
            phase,
            component,
            entry.envelope_id,
            entry.parent_id,
            summary,
        )
        return entry

    def _parse(self, envelope: Envelope) -> Dict[str, Any]:
        """Extract payload dict from envelope."""
        try:
            if envelope.payload:
                return json.loads(envelope.payload)
        except Exception:
            pass
        return {}

    # -- bus handlers ------------------------------------------------------

    def _on_user_input(self, envelope: Envelope) -> None:
        p = self._parse(envelope)
        raw_text = p.get("text", "")
        # Skip empty TimingChain echo envelopes (parent_id > 0, no text)
        if not raw_text:
            return
        # Mark turn as active -- all FINAL_RESPONSE events until FSM
        # returns to LISTENING are part of this turn (not proactive).
        self._turn_active = True
        text = raw_text[:80]
        self._record(
            "input", "bus", TOPIC_USER_INPUT, f"User input: {text}", envelope, {"text": text}
        )
        self._turn_session_ops.append(f"history.append(user_msg, len={len(raw_text)})")
        self._turn_bytes_in += len(raw_text)

    def _on_final_response(self, envelope: Envelope) -> None:
        p = self._parse(envelope)
        text = p.get("text", "")
        if not text:
            # Skip empty responses (caused by duplicate envelope replay
            # or observability event guard in front_handler).
            return

        # Stop spinner BEFORE rendering so the feed ends cleanly
        # above the concierge response.
        self._finish_spinner(response_chars=len(text))

        affect = p.get("affect", "calm")

        # Proactive detection: a response is proactive only if it
        # arrives outside an active user turn (FSM was in LISTENING when
        # the triggering task.complete arrived).  During an active turn,
        # PRESENT/HITL/WEAVE responses are expected continuations.
        # V2 Design: Section 4 (PROACTIVE_WAKE) + Section 8.10 (Weave).
        is_proactive = not self._turn_active

        self._record(
            "response",
            "front",
            TOPIC_FINAL_RESPONSE,
            f"Final response ({len(text)} chars, affect={affect}, proactive={is_proactive})",
            envelope,
            {"affect": affect, "text": text[:200], "proactive": is_proactive},
        )

        # If the user is NOT in an active turn (they're sitting at the
        # input prompt), buffer this response instead of printing it.
        # This prevents stdout writes from corrupting their typing.
        # The interactive loop will flush it at the next turn start.
        #
        # EXCEPTION: WebSocket renderers deliver immediately because the
        # browser separates the input field from the message area --
        # no corruption risk.
        if is_proactive:
            if getattr(self._renderer, "supports_immediate_proactive", False):
                self._renderer.render_response(text, self._current_member, affect)
                logger.info(
                    "OUTPUT: immediate proactive delivery (%d chars)",
                    len(text),
                )
                return
            self._pending_weave_texts.append(text)
            logger.info(
                "OUTPUT: buffered proactive response (%d chars, buffer=%d)",
                len(text),
                len(self._pending_weave_texts),
            )
            # Do NOT set _response_event -- nobody is waiting for it.
            # Do NOT render -- user is typing.
            return

        self._turn_session_ops.append(f"history.append(assistant_msg, len={len(text)})")
        self._turn_bytes_out += len(text)
        self._renderer.render_response(text, self._current_member, affect)
        # Print the system activity box after concierge response
        self._flush_system_activity()
        self._last_response_text = text
        self._response_event.set()

    def _on_proactive(self, envelope: Envelope) -> None:
        p = self._parse(envelope)
        text = p.get("text", "")
        self._record("response", "iot", TOPIC_PROACTIVE_FILL, f"Proactive: {text[:60]}", envelope)
        self._renderer.render_proactive(text)
        self._last_response_text = text
        self._response_event.set()

    def _on_weave(self, envelope: Envelope) -> None:
        p = self._parse(envelope)
        results = p.get("results", [])
        texts = [r.get("text", "") for r in results if r.get("text")]
        self._record(
            "response", "front", TOPIC_WEAVE_BATCH, f"Weave batch ({len(texts)} items)", envelope
        )
        if texts:
            # If user is NOT in an active turn, buffer instead of
            # printing (avoids corrupting their typing at the prompt).
            # EXCEPTION: WebSocket renderers deliver immediately.
            if not self._turn_active:
                if getattr(self._renderer, "supports_immediate_proactive", False):
                    self._renderer.render_weave(texts)
                    logger.info(
                        "OUTPUT: immediate weave delivery (%d items)",
                        len(texts),
                    )
                else:
                    self._pending_weave_texts.extend(texts)
                    logger.info(
                        "OUTPUT: buffered weave batch (%d items, buffer=%d)",
                        len(texts),
                        len(self._pending_weave_texts),
                    )
                return

            total_chars = sum(len(t) for t in texts)
            self._finish_spinner(response_chars=total_chars)
            # Start fresh tracking for weave delivery
            self._turn_start_ns = time.monotonic_ns()
            self._turn_session_ops.clear()
            self._turn_session_ops.append(f"weave_batch({len(texts)} results)")
            self._turn_bytes_out = sum(len(t) for t in texts)
            self._renderer.render_weave(texts)
            self._flush_system_activity()
            self._last_response_text = "\n".join(texts)
            self._response_event.set()

    def _on_clarification(self, envelope: Envelope) -> None:
        p = self._parse(envelope)
        question = p.get("question", "")
        self._record(
            "response",
            "front",
            TOPIC_CLARIFICATION_OUT,
            f"Clarification: {question[:60]}",
            envelope,
        )
        self._renderer.render_response(question, self._current_member, "warm")
        self._last_response_text = question
        self._response_event.set()

    def _on_state_updated(self, envelope: Envelope) -> None:
        p = self._parse(envelope)
        from_st = p.get("from_state", "?")
        to_st = p.get("to_state", "?")
        trigger = p.get("trigger", "?")
        self._record(
            "state",
            "fsm",
            TOPIC_STATE_UPDATED,
            f"FSM: {from_st} -> {to_st} (trigger={trigger})",
            envelope,
            {"from": from_st, "to": to_st, "trigger": trigger},
        )
        # Track FSM transitions for this turn
        if from_st not in self._turn_fsm_states:
            self._turn_fsm_states.append(from_st)
        if to_st not in self._turn_fsm_states:
            self._turn_fsm_states.append(to_st)
        self._turn_state_changes[f"fsm_{from_st}_{trigger}"] = to_st

        # Clear turn-active flag when FSM returns to LISTENING.
        # After this, any FINAL_RESPONSE that arrives is truly proactive
        # (e.g. a delayed task completing while the user is idle).
        if to_st == "LISTENING":
            self._turn_active = False

    def _on_turn_started(self, envelope: Envelope) -> None:
        self._parse(envelope)
        # Don't overwrite _turn_number -- start_turn() already set it
        self._record(
            "state", "fsm", TOPIC_TURN_STARTED, f"Turn {self._turn_number} started", envelope
        )

    def _on_turn_completed(self, envelope: Envelope) -> None:
        p = self._parse(envelope)
        turn = p.get("turn_number", "?")
        self._record("state", "fsm", TOPIC_TURN_COMPLETED, f"Turn {turn} completed", envelope)

    def _on_task_dispatch(self, envelope: Envelope) -> None:
        p = self._parse(envelope)
        intents = p.get("intents", [])
        summary_parts = [i.get("action", "?") for i in intents[:3]]
        self._record(
            "dispatch",
            "front",
            TOPIC_TASK_DISPATCH,
            f"Dispatched: {', '.join(summary_parts)}",
            envelope,
            {"intents": intents[:3]},
        )
        for part in summary_parts:
            self._turn_session_ops.append(f"session.dispatch({part})")

    def _on_task_complete(self, envelope: Envelope) -> None:
        p = self._parse(envelope)
        task_id = p.get("task_id", "?")
        self._record(
            "result",
            "back",
            TOPIC_TASK_COMPLETE,
            f"Task complete: {task_id}",
            envelope,
            {"task_id": task_id},
        )
        self._turn_session_ops.append(f"task.complete({task_id})")

    def _on_task_failed(self, envelope: Envelope) -> None:
        p = self._parse(envelope)
        task_id = p.get("task_id", "?")
        error = p.get("error_code", "?")
        self._record(
            "result",
            "back",
            TOPIC_TASK_FAILED,
            f"Task failed: {task_id} ({error})",
            envelope,
            {"task_id": task_id, "error": error},
        )
        self._turn_session_ops.append(f"task.failed({task_id}, {error})")

    def _on_task_suspended(self, envelope: Envelope) -> None:
        p = self._parse(envelope)
        task_id = p.get("task_id", "?")
        reason = p.get("hil_type", "?")
        self._record(
            "result",
            "back",
            TOPIC_TASK_SUSPENDED,
            f"Task suspended (HITL): {task_id} ({reason})",
            envelope,
            {"task_id": task_id, "hil_type": reason},
        )
        self._turn_session_ops.append(f"task.suspended({task_id}, hitl={reason})")

    def _on_tool_started(self, envelope: Envelope) -> None:
        p = self._parse(envelope)
        tool = p.get("tool_name", "?")
        actor = p.get("actor", "front")
        self._record(
            "tool", actor, TOPIC_TOOL_STARTED, f"Tool started: {tool}", envelope, {"tool": tool}
        )
        self._turn_tool_calls.append(tool)
        # Map tool names to meaningful session state operation descriptions
        _TOOL_OP_MAP = {
            "acknowledge": "session.acknowledge()",
            "update_beliefs": "beliefs.update()",
            "update_scoreboard": "scoreboard.update()",
            "update_clarifications": "clarifications.update()",
            "update_narrative": "narrative.update()",
            "refine_affect": "affective.refine()",
            "recall_memory": "memory.recall()",
            "summarize_context": "context.summarize()",
            "dispatch_task": "task.dispatch()",
            "promote_belief": "beliefs.promote()",
            "invoke_capability": "capability.invoke()",
            "discover_capabilities": "capability.discover()",
            "submit_result": "task.submit_result()",
        }
        op = _TOOL_OP_MAP.get(tool, f"tool.{tool}()")
        self._turn_session_ops.append(op)

    def _on_tool_completed(self, envelope: Envelope) -> None:
        p = self._parse(envelope)
        tool = p.get("tool_name", "?")
        actor = p.get("actor", "front")
        dur = p.get("duration_ms", 0)
        ok = p.get("success", True)
        result_data = p.get("result_data", {})
        args_summary = p.get("args_summary", "")
        self._record(
            "tool",
            actor,
            TOPIC_TOOL_COMPLETED,
            f"Tool done: {tool} ({'ok' if ok else 'FAIL'}, {dur}ms)",
            envelope,
            {"tool": tool, "duration_ms": dur, "success": ok, "result_data": result_data},
        )

        # Enrich session_ops with actual SS write details
        if result_data and ok:
            detail_parts = []
            for k, v in result_data.items():
                if isinstance(v, (int, float)):
                    detail_parts.append(f"{k}={v}")
                elif isinstance(v, str) and len(v) < 80:
                    detail_parts.append(f"{k}={v}")
                elif isinstance(v, list):
                    detail_parts.append(f"{k}=[{len(v)} items]")
                elif isinstance(v, dict):
                    detail_parts.append(f"{k}={{{len(v)} keys}}")
            if detail_parts:
                self._turn_session_ops.append(f"  -> {tool}: {', '.join(detail_parts)}")

        # Capture args summary for tools that write to SS
        _SS_WRITE_TOOLS = {
            "update_beliefs",
            "update_scoreboard",
            "update_clarifications",
            "update_narrative",
            "promote_belief",
            "acknowledge",
        }
        if tool in _SS_WRITE_TOOLS and args_summary:
            # Extract a concise description of what was written
            try:
                import ast

                args_dict = ast.literal_eval(args_summary)
                if isinstance(args_dict, dict):
                    if tool == "update_beliefs":
                        beliefs = args_dict.get("beliefs", [])
                        for b in beliefs[:3]:
                            subj = b.get("subject", "?")
                            pred = b.get("predicate", "?")
                            obj = b.get("object", "?")
                            self._turn_session_ops.append(f"  -> SS.beliefs: {subj}.{pred}={obj}")
                    elif tool == "update_scoreboard":
                        if args_dict.get("qud_push"):
                            self._turn_session_ops.append(
                                f"  -> SS.qud: push({args_dict['qud_push'][:60]})"
                            )
                        if args_dict.get("topic_shift"):
                            self._turn_session_ops.append(
                                f"  -> SS.topic: shift({args_dict['topic_shift'][:40]})"
                            )
                    elif tool == "update_narrative":
                        thread = args_dict.get("thread_name", "")
                        action = args_dict.get("action", "")
                        if thread:
                            self._turn_session_ops.append(
                                f"  -> SS.narrative: {action}({thread[:40]})"
                            )
            except Exception:
                pass  # Best-effort; never break output rendering

    def _on_stream_chunk(self, envelope: Envelope) -> None:
        """Handle streaming response chunks (thinking/text deltas).

        Records to timeline and forwards to the renderer.  The console
        renderer's render_stream_chunk is intentionally a no-op when a
        spinner is active (stdout writes would corrupt the display).
        WebSocket renderers deliver chunks to the browser for live
        streaming.
        """
        p = self._parse(envelope)
        text = p.get("text", "")
        chunk_type = p.get("chunk_type", "text")
        if not text:
            return
        self._record(
            "stream",
            "front",
            TOPIC_RESPONSE_STREAM,
            f"Stream {chunk_type}: {len(text)} chars",
            envelope,
            {"chunk_type": chunk_type, "text": text[:80]},
        )
        # Forward to renderer -- enables live streaming for web UI
        self._renderer.render_stream_chunk(text, chunk_type)

    def _on_affect_update(self, envelope: Envelope) -> None:
        p = self._parse(envelope)
        emotion = p.get("emotion", "?")
        valence = p.get("valence", 0)
        self._record(
            "state",
            "front",
            TOPIC_AFFECT_UPDATE,
            f"Affect: {emotion} (valence={valence})",
            envelope,
            {"emotion": emotion, "valence": valence},
        )
        self._turn_session_ops.append(f"affective.update({emotion})")

    def _on_artifact_created(self, envelope: Envelope) -> None:
        p = self._parse(envelope)
        art_type = p.get("artifact_type", "?")
        self._record(
            "result",
            "back",
            TOPIC_ARTIFACT_CREATED,
            f"Artifact: {art_type}",
            envelope,
            {"type": art_type},
        )
        self._turn_session_ops.append(f"artifact.created({art_type})")
