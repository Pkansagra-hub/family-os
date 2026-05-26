"""Build ``SectionUpdateInput`` objects from completed Concierge turns."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any, Mapping

from k1.concierge.section_update.types import SectionUpdateInput

MAX_TURN_TEXT_CHARS = 12_000
MAX_DISPATCH_SPECS = 12
MAX_HISTORY_ENTRIES = 8
MAX_SCOREBOARD_ITEMS = 16

_PROMPT_PRIVATE_KEYS = frozenset(
    {
        "system_prompt",
        "prompt",
        "raw_prompt",
        "messages",
        "memory_dump",
        "session_dump",
    }
)


def build_section_update_input(
    *,
    envelope: Any | None = None,
    ss: Any | None = None,
    turn_id: str | None = None,
    turn_number: int | None = None,
    session_id: str = "",
    cognitive_trace_id: str = "",
    user_text: str = "",
    assistant_text: str = "",
    prompt_mode: str | Enum = "",
    fsm_state: str | Enum = "",
    react_result: Any | None = None,
    scenario_data: Mapping[str, Any] | None = None,
    prompt_context: Mapping[str, Any] | None = None,
    admission_context: Mapping[str, Any] | None = None,
    arbiter_context: Mapping[str, Any] | None = None,
    history_context: Mapping[str, Any] | None = None,
    session_snapshot: Mapping[str, Any] | None = None,
    constraints: Mapping[str, Any] | None = None,
) -> SectionUpdateInput:
    """Create a deterministic classifier input from a finalized turn.

    The builder is deliberately side-effect free: it reads optional context,
    normalizes it into plain JSON-compatible values, and never calls writer
    ports or section mutation methods.
    """

    payload = _envelope_payload(envelope)
    snapshot = _collect_session_snapshot(ss, session_snapshot)
    resolved_session_id = _first_text(
        session_id,
        getattr(envelope, "session_id", "") if envelope is not None else "",
        str(snapshot.get("session_id", "") or ""),
        str(payload.get("session_id", "") or ""),
    )
    resolved_turn_id = _derive_turn_id(
        explicit_turn_id=turn_id,
        session_id=resolved_session_id,
        turn_number=turn_number,
        envelope=envelope,
        payload=payload,
    )
    resolved_trace_id = _first_text(
        cognitive_trace_id,
        getattr(envelope, "cognitive_trace_id", "") if envelope is not None else "",
        str(payload.get("cognitive_trace_id", "") or ""),
        str(payload.get("trace_id", "") or ""),
    )
    event_timestamp_ms = _event_timestamp_ms(envelope, payload)
    dispatch_specs = _dispatch_specs(react_result)
    user_turn = {
        "text": _bounded_text(user_text or str(payload.get("text", "") or "")),
        "turn_number": turn_number,
        "device_id": str(payload.get("device_id", "") or ""),
        "timestamp_ms": event_timestamp_ms,
        "source_topic": getattr(envelope, "topic", "") if envelope is not None else "",
        "envelope_id": getattr(envelope, "envelope_id", 0) if envelope is not None else 0,
    }
    assistant_turn = {
        "final_text": _bounded_text(assistant_text or str(getattr(react_result, "text", "") or "")),
        "react_status": str(getattr(react_result, "status", "") or ""),
        "dispatch_count": len(dispatch_specs),
        "dispatch_specs": dispatch_specs,
        "parallel_tool_calls": int(getattr(react_result, "parallel_tool_calls", 0) or 0),
        "sequential_tool_calls": int(getattr(react_result, "sequential_tool_calls", 0) or 0),
        "iteration_durations_ms": _normalize(
            list(getattr(react_result, "iteration_durations_ms", []) or [])
        ),
        "loop_events": _normalize(list(getattr(react_result, "loop_events", []) or [])),
    }
    prompt_payload = _sanitize_prompt_context(prompt_context)
    if "prompt_mode" not in prompt_payload:
        prompt_payload["prompt_mode"] = _enum_text(prompt_mode)
    scoreboard_context = _collect_scoreboard_context(ss)
    if scoreboard_context:
        snapshot["scoreboard_context"] = scoreboard_context

    return SectionUpdateInput(
        turn_id=resolved_turn_id,
        session_id=resolved_session_id,
        cognitive_trace_id=resolved_trace_id,
        prompt_mode=_enum_text(prompt_mode),
        fsm_state=_enum_text(fsm_state),
        bus_topic=getattr(envelope, "topic", "") if envelope is not None else "",
        admission_context=_normalize(admission_context or {}),
        user_turn=user_turn,
        assistant_turn=assistant_turn,
        arbiter_context=_normalize(arbiter_context or _arbiter_context_from_payload(payload)),
        prompt_context=prompt_payload,
        session_snapshot=snapshot,
        history_context=_normalize(history_context or _collect_history_context(ss)),
        scenario_context=_normalize(scenario_data or {}),
        constraints=_normalize(constraints or {}),
    )


def _derive_turn_id(
    *,
    explicit_turn_id: str | None,
    session_id: str,
    turn_number: int | None,
    envelope: Any | None,
    payload: Mapping[str, Any],
) -> str:
    supplied = _first_text(explicit_turn_id or "", str(payload.get("turn_id", "") or ""))
    if supplied:
        return supplied
    if session_id and turn_number is not None:
        return f"{session_id}:{turn_number}"
    envelope_id = getattr(envelope, "envelope_id", 0) if envelope is not None else 0
    if session_id and envelope_id:
        return f"{session_id}:env:{envelope_id}"
    if envelope_id:
        return f"env:{envelope_id}"
    return "turn:unknown"


def _collect_session_snapshot(
    ss: Any | None,
    provided: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if provided:
        normalized = _normalize(provided)
        if isinstance(normalized, dict):
            stable = dict(normalized)
            stable.setdefault("source", "provided")
            stable.setdefault("snapshot_version", _digest(stable))
            stable.setdefault("snapshot_source_epoch", str(stable.get("last_mutation_ms", "")))
            return stable
    if ss is None or not hasattr(ss, "get_snapshot"):
        return {
            "source": "none",
            "snapshot_version": "",
            "snapshot_source_epoch": "",
        }
    try:
        raw = _normalize(ss.get_snapshot())
    except Exception:  # noqa: BLE001 - read-only diagnostics boundary.
        return {
            "source": "session_state.get_snapshot",
            "snapshot_version": "unavailable",
            "snapshot_source_epoch": "unavailable",
        }
    if not isinstance(raw, dict):
        return {
            "source": "session_state.get_snapshot",
            "snapshot_version": "unavailable",
            "snapshot_source_epoch": "unavailable",
        }
    sections = raw.get("sections") if isinstance(raw.get("sections"), dict) else {}
    compact_sections: dict[str, Any] = {}
    for name in sorted(sections):
        info = sections[name]
        if isinstance(info, dict):
            compact_sections[str(name)] = {
                key: info.get(key)
                for key in (
                    "name",
                    "tier",
                    "size_bytes",
                    "budget_bytes",
                    "utilization_pct",
                    "pressure",
                )
                if key in info
            }
    stable = {
        "source": "session_state.get_snapshot",
        "session_id": str(raw.get("session_id", "") or ""),
        "total_size_bytes": raw.get("total_size_bytes", 0),
        "hot_size_bytes": raw.get("hot_size_bytes", 0),
        "warm_size_bytes": raw.get("warm_size_bytes", 0),
        "pressure": raw.get("pressure", ""),
        "last_mutation_ms": raw.get("last_mutation_ms", 0),
        "is_running": bool(raw.get("is_running", False)),
        "sections": compact_sections,
    }
    stable["snapshot_version"] = _digest(stable)
    stable["snapshot_source_epoch"] = str(raw.get("last_mutation_ms", "") or "")
    return stable


def _collect_history_context(ss: Any | None) -> dict[str, Any]:
    section = _safe_get_section(ss, "history_active")
    if section is None:
        return {"entries": [], "entry_count": 0, "window": MAX_HISTORY_ENTRIES}
    entries = _safe_call(section, "get_typed_entries")
    if entries is None:
        entries = getattr(section, "entries", None)
    if entries is None:
        entries = _safe_call(section, "get_all")
    if entries is None:
        entries = []
    normalized_entries = _normalize(list(entries)[-MAX_HISTORY_ENTRIES:])
    return {
        "entries": normalized_entries,
        "entry_count": len(entries) if hasattr(entries, "__len__") else len(normalized_entries),
        "window": MAX_HISTORY_ENTRIES,
    }


def _collect_scoreboard_context(ss: Any | None) -> dict[str, Any]:
    scoreboard = _safe_get_section(ss, "scoreboard")
    if scoreboard is None:
        return {}
    referents = _safe_call(scoreboard, "list_referents") or []
    questions = _safe_call(scoreboard, "list_open_questions") or []
    commitments = _safe_call(scoreboard, "get_open_commitments") or []
    return {
        "referents": _normalize(list(referents)[:MAX_SCOREBOARD_ITEMS]),
        "open_questions": _normalize(list(questions)[:MAX_SCOREBOARD_ITEMS]),
        "open_commitments": _normalize(list(commitments)[:MAX_SCOREBOARD_ITEMS]),
    }


def _dispatch_specs(react_result: Any | None) -> list[dict[str, Any]]:
    if react_result is None:
        return []
    specs = getattr(react_result, "dispatched_tasks", []) or []
    normalized = _normalize(list(specs)[:MAX_DISPATCH_SPECS])
    return normalized if isinstance(normalized, list) else []


def _sanitize_prompt_context(prompt_context: Mapping[str, Any] | None) -> dict[str, Any]:
    if not prompt_context:
        return {}
    result: dict[str, Any] = {}
    for key in sorted(prompt_context, key=str):
        text_key = str(key)
        value = prompt_context[key]
        if text_key in _PROMPT_PRIVATE_KEYS:
            result[f"{text_key}_summary"] = _summarize_private_value(value)
        else:
            result[text_key] = _normalize(value)
    return result


def _summarize_private_value(value: Any) -> dict[str, Any]:
    normalized = _normalize(value)
    encoded = _stable_json(normalized)
    summary = {
        "sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        "chars": len(encoded),
    }
    if isinstance(normalized, list):
        summary["items"] = len(normalized)
    if isinstance(normalized, dict):
        summary["keys"] = sorted(normalized.keys())
    return summary


def _arbiter_context_from_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    routing_metadata = payload.get("routing_metadata")
    return {
        "decision": payload.get("arbiter_decision", ""),
        "safety_band": payload.get("safety_band", ""),
        "routing_metadata": routing_metadata if isinstance(routing_metadata, dict) else {},
    }


def _envelope_payload(envelope: Any | None) -> dict[str, Any]:
    if envelope is None:
        return {}
    raw = getattr(envelope, "payload", b"")
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return dict(raw) if isinstance(raw, Mapping) else {}


def _event_timestamp_ms(envelope: Any | None, payload: Mapping[str, Any]) -> int:
    for key in ("timestamp_ms", "created_at_ms", "event_timestamp_ms"):
        value = payload.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    created_ns = getattr(envelope, "created_ns", 0) if envelope is not None else 0
    if isinstance(created_ns, (int, float)) and created_ns > 0:
        return int(created_ns // 1_000_000)
    return 0


def _safe_get_section(ss: Any | None, name: str) -> Any | None:
    if ss is None or not hasattr(ss, "get_section"):
        return None
    try:
        return ss.get_section(name)
    except Exception:  # noqa: BLE001 - optional context should degrade cleanly.
        return None


def _safe_call(obj: Any, method_name: str) -> Any | None:
    method = getattr(obj, method_name, None)
    if method is None:
        return None
    try:
        return method()
    except TypeError:
        return None
    except Exception:  # noqa: BLE001 - optional context should degrade cleanly.
        return None


def _first_text(*values: str | None) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _enum_text(value: str | Enum) -> str:
    if isinstance(value, Enum):
        enum_value = value.value
        return enum_value if isinstance(enum_value, str) else value.name
    return str(value or "")


def _bounded_text(value: Any, max_chars: int = MAX_TURN_TEXT_CHARS) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"{text[:max_chars]}\n[truncated original_chars={len(text)} sha256={digest}]"


def _digest(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _stable_json(value: Any) -> str:
    return json.dumps(
        _normalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _normalize(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, Enum):
        enum_value = value.value
        return enum_value if isinstance(enum_value, (str, int, float, bool)) else value.name
    if is_dataclass(value):
        return _normalize(asdict(value))
    if hasattr(value, "to_dict"):
        try:
            return _normalize(value.to_dict())
        except Exception:  # noqa: BLE001 - fallback to repr-safe shape.
            return str(value)
    if isinstance(value, Mapping):
        return {str(key): _normalize(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, set):
        return sorted((_normalize(item) for item in value), key=lambda item: _stable_json(item))
    if hasattr(value, "__dict__"):
        return _normalize(vars(value))
    return str(value)


__all__ = [
    "MAX_DISPATCH_SPECS",
    "MAX_HISTORY_ENTRIES",
    "MAX_SCOREBOARD_ITEMS",
    "MAX_TURN_TEXT_CHARS",
    "build_section_update_input",
]
