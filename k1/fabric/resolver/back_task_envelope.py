"""BackTaskEnvelope — Contract CC-0.

The incoming task format from Back.  Back wraps the user's utterance plus
resolved context into this envelope before calling ``resolve_situation``.

Spec: Epic 3.1, whiteboard Contract CC-0.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

# ── Constants ──────────────────────────────────────────────────────────
VALID_TIERS: set[str] = {"LOW", "MEDIUM", "HIGH"}
VALID_SAFETY_BANDS: set[str] = {"GREEN", "AMBER", "RED"}

# ── Errors ─────────────────────────────────────────────────────────────


class BackTaskEnvelopeError(ValueError):
    """Validation error for back-task envelope payloads."""

    def __init__(self, field_name: str, message: str | None = None) -> None:
        self.field_name = field_name
        super().__init__(message or field_name)


# ── Dataclasses ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BackTaskEnvelope:
    """The envelope Back wraps around the user utterance + resolved context.

    This is the single entry point into ``ResolveSituationService.resolve()``.

    Budget (max_iterations, max_fabric_calls, max_prompt_tokens) is NOT
    part of this contract — it belongs to Back/Concierge runtime,
    not Fabric resolution.
    """

    envelope_id: str
    task_id: str
    trace_id: str
    session_id: str
    actor_id: str
    space_id: str
    tier: str
    safety_band: str
    task_dispatch: dict[str, Any]
    session_state_ref: str | None = None
    grounding_envelope_id: str | None = None
    temporal_anchor_id: str | None = None
    spatial_context_id: str | None = None
    submitted_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Parsing ────────────────────────────────────────────────────────────


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_back_task_envelope(payload: dict[str, Any]) -> BackTaskEnvelope:
    """Validate and parse a raw dict into a ``BackTaskEnvelope``.

    Raises ``BackTaskEnvelopeError`` for missing/invalid fields.
    """
    if not isinstance(payload, dict):
        raise BackTaskEnvelopeError("payload", "payload must be a dict")

    task_id = _required_str(payload, "task_id")
    trace_id = str(payload.get("trace_id") or "").strip()
    if not trace_id:
        raise BackTaskEnvelopeError("trace_id", "trace_id must be a non-empty string")
    session_id = _required_str(payload, "session_id")
    actor_id = _required_str(payload, "actor_id")
    space_id = _required_str(payload, "space_id")

    tier = str(payload.get("tier") or "").strip()
    if tier not in VALID_TIERS:
        raise BackTaskEnvelopeError("tier", f"tier must be one of {sorted(VALID_TIERS)}")
    safety_band = str(payload.get("safety_band") or "").strip()
    if safety_band not in VALID_SAFETY_BANDS:
        raise BackTaskEnvelopeError(
            "safety_band", f"safety_band must be one of {sorted(VALID_SAFETY_BANDS)}"
        )

    task_dispatch = payload.get("task_dispatch")
    if not isinstance(task_dispatch, dict) or not task_dispatch:
        raise BackTaskEnvelopeError("task_dispatch", "task_dispatch must be a non-empty dict")

    return BackTaskEnvelope(
        envelope_id=str(payload.get("envelope_id") or "env-" + uuid.uuid4().hex),
        task_id=task_id,
        trace_id=trace_id,
        session_id=session_id,
        actor_id=actor_id,
        space_id=space_id,
        tier=tier,
        safety_band=safety_band,
        task_dispatch=task_dispatch,
        session_state_ref=_optional_str(payload.get("session_state_ref")),
        grounding_envelope_id=_optional_str(payload.get("grounding_envelope_id")),
        temporal_anchor_id=_optional_str(payload.get("temporal_anchor_id")),
        spatial_context_id=_optional_str(payload.get("spatial_context_id")),
        submitted_at=str(payload.get("submitted_at") or _utc_now_iso()),
    )


def _required_str(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if value is None or str(value).strip() == "":
        raise BackTaskEnvelopeError(field_name)
    return str(value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
