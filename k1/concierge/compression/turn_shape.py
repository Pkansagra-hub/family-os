"""k1.concierge.compression.turn_shape -- shared history->compressor turn shaping.

The Front prompt path (``front_handler``) and the ExperienceLayer tick path
both feed conversation history into the :class:`EpisodicCompressor`. The
compressor expects a strict dict shape:

    {
        "turn_number": int,
        "user_message": str,
        "response": str,
        "intent": str,
        "entities": list,
        "has_hitl": bool,
        "safety_band": str,
    }

But the actual SessionState ``history_active`` rows expose only::

    turn_number, entry_type, text, timestamp_ms, source, task_id, metadata

so the intent/safety/entities must be derived from ``metadata`` per the
M6 plan precedence chain (``metadata['arbiter']['decision']`` ->
``metadata['intent']`` -> ``entry_type``).

This module is the SINGLE OWNER of that conversion. Both call sites
import the same function so the prompt path and the experience tick
path never drift apart.
"""

from __future__ import annotations

from typing import Any


def history_entries_to_opp_turns(history_active: Any) -> list[dict[str, Any]]:
    """Convert SS ``history_active`` rows into EpisodicCompressor turn dicts.

    Accepts either ``TypedHistoryEntry`` dataclass objects or already-dict
    rows. Prompt-only -- never mutates ``history_active``.

    Intent precedence: ``metadata['arbiter']['decision']`` ->
    ``metadata['intent']`` -> ``entry_type`` fallback.

    HITL detection: ``entry_type in {hitl_request, hitl_response,
    hil_request, hil_response}``.

    Safety band default: ``"GREEN"``.
    """
    if not history_active:
        return []

    out: list[dict[str, Any]] = []
    for idx, entry in enumerate(history_active):
        if isinstance(entry, dict):
            # Pass-through path: rows already shaped like the compressor's
            # canonical turn dict (used by integration tests and any caller
            # that has pre-shaped its history). Detected by the presence of
            # ``user_message`` or ``response`` keys, which are not part of
            # the raw ``TypedHistoryEntry`` schema.
            if "user_message" in entry or "response" in entry:
                out.append(
                    {
                        "turn_number": int(entry.get("turn_number", idx) or idx),
                        "user_message": str(entry.get("user_message", "") or ""),
                        "response": str(entry.get("response", "") or ""),
                        "intent": str(entry.get("intent", "") or ""),
                        "entities": list(entry.get("entities", []) or []),
                        "has_hitl": bool(entry.get("has_hitl", False)),
                        "safety_band": str(entry.get("safety_band", "GREEN") or "GREEN"),
                    }
                )
                continue
            get = entry.get
            metadata = entry.get("metadata") or {}
        else:

            def _get(key: str, default: Any = None, _e: Any = entry) -> Any:
                return getattr(_e, key, default)

            get = _get  # type: ignore[assignment]
            metadata = getattr(entry, "metadata", None) or {}

        entry_type = str(get("entry_type", "") or "")
        text = str(get("text", "") or "")
        turn_number = int(get("turn_number", idx) or idx)
        source = str(get("source", "") or "")

        user_message = ""
        response = ""
        if source == "user" or entry_type == "user_input":
            user_message = text
        else:
            response = text

        arbiter = metadata.get("arbiter") if isinstance(metadata, dict) else None
        arbiter_decision = ""
        if isinstance(arbiter, dict):
            arbiter_decision = str(arbiter.get("decision", "") or "")
        intent = (
            arbiter_decision
            or str((metadata.get("intent") if isinstance(metadata, dict) else "") or "")
            or entry_type
        )

        entities_raw = metadata.get("entities") if isinstance(metadata, dict) else None
        entities = list(entities_raw) if isinstance(entities_raw, (list, tuple)) else []

        has_hitl = entry_type in {
            "hitl_request",
            "hitl_response",
            "hil_request",
            "hil_response",
        }

        safety_band = str(
            (metadata.get("safety_band") if isinstance(metadata, dict) else "") or "GREEN"
        )

        out.append(
            {
                "turn_number": turn_number,
                "user_message": user_message,
                "response": response,
                "intent": intent,
                "entities": entities,
                "has_hitl": has_hitl,
                "safety_band": safety_band,
            }
        )
    return out
