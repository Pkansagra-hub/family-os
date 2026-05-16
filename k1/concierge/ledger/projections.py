"""
k1.concierge.ledger.projections -- Pure projection functions.

M1 E1.2.2: Materialize session state from ledger event streams.

Each projection is a pure function: events in -> state out. No side effects.
Projections serve three purposes:
    1. Crash recovery (replay all events from ledger).
    2. Debugging (materialize state at any point in time).
    3. Testing (verify state by replaying known event sequences).

Reference: v3_milestones.md E1.2.2 (projection reader).
Reference: v3_whiteboard.md 3.A (session state = derived projection).
"""

from __future__ import annotations

import logging
from collections import deque
from typing import TYPE_CHECKING, Any

from k1.concierge.protocols.hitl_persistence import (
    HILStateRecord,
    TaskStateEntry,
    TaskStatus,
)

if TYPE_CHECKING:
    from k1.concierge.ledger.store import LedgerEntry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Event type -> history entry mapping
# ---------------------------------------------------------------------------

# Maps canonical event_type to (entry_type, role) for history projection.
# Events not in this map produce no history entry.
_HISTORY_EVENT_MAP: dict[str, tuple[str, str]] = {
    "conversation.user_input.received": ("user", "user"),
    "task.created": ("task_dispatch", "system"),
    "task.completed": ("task_complete", "assistant"),
    "task.failed": ("error", "system"),
    "task.cancelled": ("cancel_confirmed", "system"),
    "task.suspended": ("task_suspended", "system"),
    "task.resumed": ("task_resumed", "system"),
    "hil.requested": ("hil_request", "system"),
    "hil.resolved": ("hil_response", "user"),
    "conversation.weave.emitted": ("assistant_response", "assistant"),
    "conversation.intent.arbitrated": ("intent", "system"),
    "conversation.dead_lettered": ("dead_letter", "system"),
}

# Events that increment the turn number
_TURN_INCREMENT_EVENTS: frozenset[str] = frozenset(
    {
        "conversation.user_input.received",
    }
)


def _extract_text(event_type: str, payload: dict[str, Any]) -> str:
    """Extract display text from a canonical event payload.

    Each event type stores its human-readable text in a different field.
    """
    if event_type == "conversation.user_input.received":
        return payload.get("text", "")
    if event_type == "task.completed":
        rd = payload.get("result_data", {})
        if isinstance(rd, dict):
            return rd.get("summary", rd.get("text", str(rd)))
        return str(rd)
    if event_type == "task.failed":
        return payload.get("reason", "")
    if event_type == "task.cancelled":
        return payload.get("reason", "")
    if event_type == "hil.requested":
        return payload.get("question", "")
    if event_type == "hil.resolved":
        return payload.get("raw_user_text", "")
    if event_type == "conversation.weave.emitted":
        return payload.get("response_text_preview", "")
    if event_type == "conversation.intent.arbitrated":
        return payload.get("intent_class", "")
    if event_type == "task.suspended":
        return payload.get("suspension_type", "")
    if event_type == "task.resumed":
        return payload.get("resume_instruction", "")
    return ""


def _extract_source(event_type: str, payload: dict[str, Any]) -> str:
    """Extract source actor from canonical event payload."""
    actor = payload.get("actor", "")
    if actor:
        return actor
    # Infer from event type
    if event_type.startswith("conversation.user_input"):
        return "user"
    if event_type.startswith("task."):
        return "back"
    if event_type.startswith("hil."):
        return "fsm"
    if event_type.startswith("conversation.weave"):
        return "fsm"
    return "system"


# ---------------------------------------------------------------------------
# project_history
# ---------------------------------------------------------------------------


def project_history(entries: list[LedgerEntry]) -> list[dict[str, Any]]:
    """Replay ledger events into history entry dicts.

    Produces dicts matching TypedHistoryEntry.to_dict() format:
        {turn, type, role, text, timestamp_ms, source, [task_id], [metadata]}

    Only events in _HISTORY_EVENT_MAP produce history entries.
    Turn number increments on user input events.

    Args:
        entries: Ordered ledger entries for a session.

    Returns:
        List of history entry dicts in ledger order.
    """
    result: list[dict[str, Any]] = []
    turn_number = 0

    for entry in entries:
        event_type = entry.event_type
        payload = entry.payload

        # Turn number management
        if event_type in _TURN_INCREMENT_EVENTS:
            turn_number += 1

        mapping = _HISTORY_EVENT_MAP.get(event_type)
        if mapping is None:
            continue  # No history entry for this event type

        entry_type, role = mapping
        text = _extract_text(event_type, payload)
        source = _extract_source(event_type, payload)
        task_id = payload.get("task_id", "")
        ts_utc = payload.get("ts_utc", "")

        # Convert ISO 8601 ts_utc to timestamp_ms for TypedHistoryEntry compat
        timestamp_ms = _iso_to_ms(ts_utc) if ts_utc else 0

        hist: dict[str, Any] = {
            "turn": turn_number,
            "type": entry_type,
            "role": role,
            "text": text,
            "timestamp_ms": timestamp_ms,
            "source": source,
        }
        if task_id:
            hist["task_id"] = task_id
        result.append(hist)

    return result


# ---------------------------------------------------------------------------
# M9 E9.1.2: Cancel state projection
# ---------------------------------------------------------------------------


def project_cancel_state(
    entries: list[LedgerEntry],
) -> tuple[set[str], set[str]]:
    """Replay ledger events into cancel protocol state.

    M9 E9.1.2: Pure projection for CancellationHandler recovery.

    Returns:
        Tuple of (active_task_ids, cancelled_task_ids).
        - active_task_ids: Tasks that are created but not yet terminal.
        - cancelled_task_ids: Tasks that received a task.cancelled event.
    """
    active: set[str] = set()
    cancelled: set[str] = set()

    for entry in entries:
        event_type = entry.event_type
        task_id = entry.payload.get("task_id", "")
        if not task_id:
            continue

        if event_type == "task.created":
            active.add(task_id)
        elif event_type == "task.cancelled":
            cancelled.add(task_id)
            active.discard(task_id)
        elif event_type in ("task.completed", "task.failed"):
            active.discard(task_id)

    return active, cancelled


# ---------------------------------------------------------------------------
# M9 E9.2.3: Suspension state projection
# ---------------------------------------------------------------------------


def project_suspension_state(
    entries: list[LedgerEntry],
) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    """Replay ledger events into suspension protocol state.

    M9 E9.2.3: Pure projection for SuspensionManager recovery.

    Returns:
        Tuple of (active_suspensions, suspension_counts).
        - active_suspensions: task_id -> payload dict of the active suspension
          (includes suspension_type, question, options, react_history, etc.)
        - suspension_counts: task_id -> total number of suspensions.
    """
    active: dict[str, dict[str, Any]] = {}
    counts: dict[str, int] = {}

    for entry in entries:
        event_type = entry.event_type
        task_id = entry.payload.get("task_id", "")
        if not task_id:
            continue

        if event_type == "task.suspended":
            active[task_id] = dict(entry.payload)
            counts[task_id] = entry.payload.get("suspension_count", counts.get(task_id, 0) + 1)
        elif event_type == "task.resumed":
            active.pop(task_id, None)
        elif event_type in ("task.completed", "task.failed", "task.cancelled"):
            active.pop(task_id, None)

    return active, counts


# ---------------------------------------------------------------------------
# M9 E9.3.2: HITL state projection
# ---------------------------------------------------------------------------


def project_hitl_state(
    entries: list[LedgerEntry],
) -> tuple[dict[str, HILStateRecord], dict[str, int], dict[str, list[dict[str, Any]]]]:
    """Replay ledger events into HITL coordinator state.

    M9 E9.3.2: Pure projection for HILCoordinator recovery.

    Returns:
        Tuple of (pending_requests, hil_counts, hil_histories).
                - pending_requests: task_id -> HILStateRecord for tasks
          with hil.requested but no hil.resolved yet.
        - hil_counts: task_id -> total number of HIL rounds.
        - hil_histories: task_id -> list of resolved HIL interaction dicts.
    """
    pending: dict[str, HILStateRecord] = {}
    counts: dict[str, int] = {}
    histories: dict[str, list[dict[str, Any]]] = {}
    request_to_task: dict[str, str] = {}

    def _hil_identity(payload: dict[str, Any]) -> str:
        return str(
            payload.get("hil_request_id")
            or payload.get("pending_hil_id")
            or payload.get("event_id")
            or ""
        )

    for entry in entries:
        event_type = entry.event_type
        payload = entry.payload
        hil_identity = _hil_identity(payload)
        task_id = str(payload.get("task_id") or (f"hil:{hil_identity}" if hil_identity else ""))

        if event_type == "hil.requested":
            if not task_id:
                continue
            record = HILStateRecord.from_projection_payload(task_id, payload)
            pending[task_id] = record
            for key in {record.hil_request_id, record.pending_hil_id, entry.event_id}:
                if key:
                    request_to_task[key] = task_id
            counts[task_id] = counts.get(task_id, 0) + 1
        elif event_type == "hil.resolved":
            task_id = request_to_task.get(hil_identity, task_id)
            if not task_id:
                continue
            prior = pending.pop(task_id, None)
            if task_id not in histories:
                histories[task_id] = []
            histories[task_id].append(
                {
                    "hil_request_id": hil_identity,
                    "kind": payload.get("kind", getattr(prior, "kind", "resolved")),
                    "hil_type": payload.get("hil_type", getattr(prior, "hil_type", "resolved")),
                    "resolution": payload.get("resolution", {}),
                    "resolution_type": payload.get("resolution_type", ""),
                    "raw_user_text": payload.get("raw_user_text", ""),
                }
            )
        elif event_type in ("hil.timed_out", "hil.blocked"):
            task_id = request_to_task.get(hil_identity, task_id)
            if task_id:
                pending.pop(task_id, None)
        elif event_type in ("task.completed", "task.failed", "task.cancelled"):
            if task_id:
                pending.pop(task_id, None)

    return pending, counts, histories


# ---------------------------------------------------------------------------
# project_task_states
# ---------------------------------------------------------------------------


def project_task_states(entries: list[LedgerEntry]) -> dict[str, TaskStateEntry]:
    """Replay ledger events into per-task state entries.

    Produces a dict of task_id -> TaskStateEntry matching the controller's
    runtime _task_states dict.

    Handles the full task lifecycle:
        TaskCreated    -> new DISPATCHED entry
        TaskProgressed -> update progress_pct, findings_so_far
        TaskCompleted  -> status=COMPLETED
        TaskFailed     -> status=FAILED
        TaskCancelled  -> status=CANCELLED
        TaskSuspended  -> status=SUSPENDED, pending_hil set
        TaskResumed    -> status=IN_PROGRESS, pending_hil cleared

    Args:
        entries: Ordered ledger entries for a session.

    Returns:
        Dict of task_id -> TaskStateEntry.
    """
    states: dict[str, TaskStateEntry] = {}

    for entry in entries:
        event_type = entry.event_type
        payload = entry.payload
        task_id = payload.get("task_id", "")

        if not task_id:
            continue  # Non-task events don't affect task state

        if event_type == "task.created":
            states[task_id] = TaskStateEntry(
                task_id=task_id,
                action=payload.get("action", ""),
                status=TaskStatus.DISPATCHED,
                dispatched_at_ms=_iso_to_ms(payload.get("ts_utc", "")),
            )

        elif event_type == "task.progressed":
            state = states.get(task_id)
            if state is not None:
                state.status = TaskStatus.IN_PROGRESS
                state.progress_pct = payload.get("progress_pct", 0)
                fsf = payload.get("findings_so_far")
                if fsf and isinstance(fsf, dict):
                    state.findings_so_far.append(fsf)

        elif event_type == "task.completed":
            state = states.get(task_id)
            if state is not None:
                state.status = TaskStatus.COMPLETED
                state.pending_hil = None
                state.completed_at_ms = _iso_to_ms(payload.get("ts_utc", ""))

        elif event_type == "task.failed":
            state = states.get(task_id)
            if state is not None:
                state.status = TaskStatus.FAILED
                state.pending_hil = None
                state.cancel_reason = payload.get("reason", "error")
                state.completed_at_ms = _iso_to_ms(payload.get("ts_utc", ""))

        elif event_type == "task.cancelled":
            state = states.get(task_id)
            if state is not None:
                state.status = TaskStatus.CANCELLED
                state.pending_hil = None
                state.cancel_reason = payload.get("reason", "user_cancel")
                state.completed_at_ms = _iso_to_ms(payload.get("ts_utc", ""))

        elif event_type == "task.suspended":
            state = states.get(task_id)
            if state is not None:
                state.status = TaskStatus.SUSPENDED
                state.hil_suspensions_count = payload.get("suspension_count", 1)
                # Store the HIL request reference for crash recovery
                state.pending_hil = {
                    "hil_request_event_id": payload.get("hil_request_event_id", ""),
                    "suspension_type": payload.get("suspension_type", ""),
                }

        elif event_type == "task.resumed":
            state = states.get(task_id)
            if state is not None:
                state.pending_hil = None
                state.status = TaskStatus.IN_PROGRESS

        elif event_type == "hil.requested":
            # Record HIL interaction metadata on the task
            state = states.get(task_id)
            if state is not None and state.status == TaskStatus.SUSPENDED:
                # Enrich pending_hil with full request data
                state.pending_hil = {
                    "hil_request_id": payload.get("hil_request_id", ""),
                    "pending_hil_id": payload.get("pending_hil_id", ""),
                    "kind": payload.get("kind", payload.get("hil_type", "")),
                    "hil_type": payload.get("hil_type", ""),
                    "question": payload.get("question", ""),
                    "options": payload.get("options", []),
                    "context": payload.get("context", {}),
                    "side_effects": payload.get("side_effects", []),
                    "safety_band": payload.get("safety_band", "GREEN"),
                }

        elif event_type == "hil.resolved":
            # Record HITL interaction in history
            state = states.get(task_id)
            if state is not None:
                state.hil_history.append(
                    {
                        "hil_type": "resolved",
                        "resolution": payload.get("resolution", {}),
                        "resolution_type": payload.get("resolution_type", ""),
                    }
                )

    return states


# ---------------------------------------------------------------------------
# project_pending_results
# ---------------------------------------------------------------------------


def project_pending_results(entries: list[LedgerEntry]) -> deque[dict[str, Any]]:
    """Replay weave events into pending results queue.

    WeaveCandidateArrived adds to the queue.
    WeaveEmitted removes candidates that were delivered.

    Produces a deque matching FSMTurnState.pending_results shape:
        {task_id, result, envelope_id, parent_id, queued_at_ns}

    Args:
        entries: Ordered ledger entries for a session.

    Returns:
        Deque of pending result dicts.
    """
    pending: deque[dict[str, Any]] = deque()
    # Track delivered candidate event_ids for removal
    delivered_event_ids: set[str] = set()

    # First pass: collect all delivered candidate IDs
    for entry in entries:
        if entry.event_type == "conversation.weave.emitted":
            for cid in entry.payload.get("candidate_event_ids", []):
                delivered_event_ids.add(cid)

    # Second pass: collect candidates not yet delivered
    for entry in entries:
        if entry.event_type == "conversation.weave.candidate":
            event_id = entry.payload.get("event_id", "")
            if event_id in delivered_event_ids:
                continue  # Already delivered
            pending.append(
                {
                    "task_id": entry.payload.get("task_id", ""),
                    "result": entry.payload.get("result_data", {}),
                    "envelope_id": 0,  # Not available from canonical event
                    "parent_id": 0,  # Not available from canonical event
                    "queued_at_ns": entry.payload.get("completed_at_ns", 0),
                }
            )

    return pending


# ---------------------------------------------------------------------------
# M2 E2.5.2: Dead-letter projection
# ---------------------------------------------------------------------------


def project_dead_letters(entries: list[LedgerEntry]) -> list[dict[str, Any]]:
    """Materialize dead-letter events from the ledger stream.

    Extracts all conversation.dead_lettered events and returns them as
    dicts for observability dashboards and reconciliation.

    Args:
        entries: Ordered list of LedgerEntry from the store.

    Returns:
        List of dead-letter payload dicts with seq and written_at_utc added.
    """
    dead_letters: list[dict[str, Any]] = []

    for entry in entries:
        if entry.event_type != "conversation.dead_lettered":
            continue
        payload = dict(entry.payload) if entry.payload else {}
        payload["_seq"] = entry.seq
        payload["_written_at_utc"] = entry.written_at_utc
        dead_letters.append(payload)

    return dead_letters


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _iso_to_ms(iso_str: str) -> int:
    """Convert ISO 8601 UTC string to milliseconds since epoch.

    Returns 0 if the string cannot be parsed.
    """
    if not iso_str:
        return 0
    try:
        from datetime import datetime

        # Handle both 'Z' and '+00:00' suffixes
        cleaned = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        return int(dt.timestamp() * 1000)
    except (ValueError, OSError):
        return 0
