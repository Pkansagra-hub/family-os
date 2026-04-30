"""Front-side HIL envelope adapters (E1.M2.1).

Bridges the unified `HILEnvelope` / `HILResponseEnvelope` shape (defined
in `k1.hil.types`) with the existing Front actor scenario-data flow.

Design
------
Front's `_extract_scenario_data` for `PromptMode.HITL_RELAY` historically
read top-level keys (`hil_type`, `question`, `options`, `side_effects`)
from the bus payload. The unified HIL service publishes a
`HILEnvelope.to_dict()` shape instead, with the kind-specific fields
nested under `payload`.

This module provides a single entry point, `unwrap_hil_request_payload`,
that:

  * Detects the new envelope shape via presence of `hil_request_id`
    AND `kind` AND a nested `payload` dict.
  * Renders kind-specific question / options / side_effects / hil_type
    fields back to the flat shape the existing prompt template expects.
  * For legacy (no `hil_request_id`) payloads, returns the payload
    unchanged and logs a one-time deprecation warning per process.
  * Always preserves the original envelope under `_hil_envelope` so the
    HITL_RESOLVE branch can build a correctly-correlated response.

`build_hil_response_envelope_dict` constructs the outbound
`HILResponseEnvelope` payload from a Front-built resolution dict; only
called when the incoming carried a `_hil_envelope` (new-envelope path).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from k1.hil.types import HILKind, HILResponseEnvelope

logger = logging.getLogger(__name__)

_LEGACY_WARN_EMITTED: set[str] = set()


def is_new_hil_envelope(payload: dict[str, Any]) -> bool:
    """True iff `payload` looks like a `HILEnvelope.to_dict()` result."""
    if not isinstance(payload, dict):
        return False
    return (
        "hil_request_id" in payload
        and "kind" in payload
        and isinstance(payload.get("payload"), dict)
    )


def unwrap_hil_request_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a flat dict suitable for HITL_RELAY scenario rendering.

    For new-envelope payloads, kind-specific fields are extracted from
    the inner `payload` dict and rendered into the legacy keys
    (`hil_type`, `question`, `options`, `side_effects`). The original
    envelope is preserved under `_hil_envelope` for response correlation.

    For legacy payloads, the input is returned as-is (with a one-time
    deprecation warning per `hil_type` value).
    """
    if not is_new_hil_envelope(payload):
        hil_type = str(payload.get("hil_type", "<unknown>"))
        if hil_type not in _LEGACY_WARN_EMITTED:
            _LEGACY_WARN_EMITTED.add(hil_type)
            logger.warning(
                "front_hil_legacy_envelope hil_type=%s -- migrate publisher to HILEnvelope (E1.M2)",
                hil_type,
            )
        return dict(payload)

    try:
        kind = HILKind(payload["kind"])
    except ValueError:
        logger.warning(
            "front_hil_unknown_kind kind=%s hil_request_id=%s",
            payload.get("kind"),
            payload.get("hil_request_id"),
        )
        return dict(payload)

    inner = payload.get("payload") or {}
    question, options, side_effects, hil_type = _render_kind_specific(kind, inner)

    return {
        "hil_type": hil_type,
        "question": question,
        "options": list(options),
        "side_effects": list(side_effects),
        "_hil_envelope": dict(payload),
    }


def _render_kind_specific(kind: HILKind, inner: dict[str, Any]) -> tuple[str, list, list, str]:
    """Map kind-specific inner payload to (question, options, side_effects, hil_type)."""
    if kind is HILKind.CLARIFICATION:
        return (
            str(inner.get("question", "") or ""),
            list(inner.get("options", []) or []),
            [],
            "clarification",
        )
    if kind is HILKind.APPROVAL:
        bullets = inner.get("side_effects", []) or []
        summary = str(inner.get("summary", "") or "")
        bullet_text = "\n".join(f"- {se}" for se in bullets) if bullets else ""
        question = summary if not bullet_text else f"{summary}\n\nSide effects:\n{bullet_text}"
        return (
            question,
            list(inner.get("options", []) or []),
            list(bullets),
            "approval",
        )
    if kind is HILKind.NEEDS_HUMAN:
        return (
            str(inner.get("question", "") or ""),
            list(inner.get("options", []) or []),
            list(inner.get("side_effects", []) or []),
            str(inner.get("hil_type", "clarification") or "clarification"),
        )
    if kind is HILKind.OVERRIDE:
        unresolved = inner.get("unresolved_capabilities", []) or []
        alts = inner.get("proposed_alternatives", []) or []
        question_lines = ["Cannot resolve the following capabilities:"]
        question_lines.extend(f"- {c}" for c in unresolved)
        if alts:
            question_lines.append("\nProposed alternatives:")
            for a in alts:
                desc = a.get("description") or a.get("name") or str(a)
                question_lines.append(f"- {desc}")
        return (
            "\n".join(question_lines),
            list(alts),
            [],
            "override",
        )
    if kind is HILKind.CAPABILITY_GATE:
        cap_name = str(inner.get("capability_name", "") or "")
        params_summary = str(inner.get("params_summary", "") or "")
        contract = inner.get("contract") or {}
        side_effects = list(contract.get("side_effects", []) or [])
        question = f"About to {cap_name}: {params_summary}. Approve?"
        return (
            question,
            [{"label": "Approve", "value": "approve"}, {"label": "Reject", "value": "reject"}],
            side_effects,
            "capability_gate",
        )
    return ("", [], [], "")


def build_hil_response_envelope_dict(
    incoming_envelope: dict[str, Any],
    resolution: dict[str, Any],
    *,
    raw_user_text: str | None = None,
    timed_out: bool = False,
) -> dict[str, Any]:
    """Build a `HILResponseEnvelope.to_dict()` from a Front resolution.

    `incoming_envelope` MUST be the value previously returned in the
    `_hil_envelope` slot by `unwrap_hil_request_payload`. Returns a dict
    ready to publish on `TOPIC_HIL_RESPONSE`.
    """
    try:
        kind = HILKind(incoming_envelope["kind"])
    except (KeyError, ValueError) as exc:
        raise ValueError(
            f"incoming_envelope missing/invalid 'kind': {incoming_envelope!r}"
        ) from exc

    payload = _build_response_payload(kind, resolution, raw_user_text)
    env = HILResponseEnvelope(
        hil_request_id=str(incoming_envelope["hil_request_id"]),
        kind=kind,
        responded_at_ms=int(time.time() * 1000),
        payload=payload,
        timed_out=timed_out,
    )
    return env.to_dict()


def _build_response_payload(
    kind: HILKind, resolution: dict[str, Any], raw_user_text: str | None
) -> dict[str, Any]:
    """Map a Front resolution dict to the kind-specific response payload."""
    if kind is HILKind.CLARIFICATION:
        return {
            "answer": resolution.get("additional_info")
            or resolution.get("selected_option")
            or raw_user_text
            or "",
        }
    if kind is HILKind.APPROVAL:
        approved = resolution.get("approval")
        if approved is True:
            decision = "approve"
        elif approved is False:
            decision = "reject"
        else:
            decision = str(resolution.get("selected_option") or "reject")
        return {
            "decision": decision,
            "modifications": resolution.get("modifications"),
        }
    if kind is HILKind.NEEDS_HUMAN:
        return {
            "decision": str(resolution.get("selected_option") or "answered"),
            "resolution": dict(resolution),
            "raw_user_text": raw_user_text,
        }
    if kind is HILKind.OVERRIDE:
        return {
            "choice": str(resolution.get("selected_option") or "abort"),
            "selected_alternative": resolution.get("target"),
            "fallback_action": resolution.get("additional_info"),
        }
    if kind is HILKind.CAPABILITY_GATE:
        approved = resolution.get("approval")
        if approved is None:
            sel = str(resolution.get("selected_option", "")).lower()
            approved = sel in {"approve", "yes", "ok"}
        return {
            "approved": bool(approved),
            "reason": str(resolution.get("additional_info") or "user_decision"),
        }
    return {}
