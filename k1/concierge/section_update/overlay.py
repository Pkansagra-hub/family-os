"""Dispatch-critical turn-state overlay helpers."""

from __future__ import annotations

from typing import Any, Mapping

from k1.concierge.section_update.types import (
    CommitClass,
    SectionMutation,
    SectionUpdatePlan,
    TurnStateOverlay,
)
from k1.concierge.section_update.vocabulary import validate_target

OVERLAY_TASK_PAYLOAD_KEY = "turn_state_overlay"
MAX_OVERLAY_MUTATIONS = 12
FORBIDDEN_OVERLAY_AUTHORITY_KEYS = frozenset(
    {
        "task_id",
        "tier",
        "budget_hint",
        "depends_on",
        "route",
        "routing",
        "orchestrator",
        "planner",
        "safety_band",
    }
)


def build_dispatch_overlay_from_plan(
    plan: SectionUpdatePlan | Mapping[str, Any],
    *,
    durable: bool,
    status: str,
    degraded_reason: str = "",
) -> dict[str, Any] | None:
    """Project dispatch-critical plan mutations into a bounded task overlay."""

    plan = plan if isinstance(plan, SectionUpdatePlan) else SectionUpdatePlan.from_dict(plan)
    sections: dict[str, dict[str, Any]] = {}
    fields_applied: list[str] = []
    rejected: list[dict[str, Any]] = []
    for mutation in plan.mutations:
        mutation = (
            mutation
            if isinstance(mutation, SectionMutation)
            else SectionMutation.from_dict(mutation)
        )
        if mutation.commit_class != CommitClass.DISPATCH_CRITICAL:
            continue
        validation = validate_target(mutation.section, mutation.operation)
        if not validation.ok:
            rejected.append(
                {
                    "section": mutation.section,
                    "operation": mutation.operation,
                    "reason": validation.reason,
                }
            )
            continue
        if (
            sum(len(item.get("mutations", [])) for item in sections.values())
            >= MAX_OVERLAY_MUTATIONS
        ):
            rejected.append(
                {
                    "section": mutation.section,
                    "operation": mutation.operation,
                    "reason": "overlay mutation limit reached",
                }
            )
            continue
        section_payload = sections.setdefault(mutation.section, {"mutations": []})
        section_payload["mutations"].append(
            {
                "operation": mutation.operation,
                "data": _strip_authority_keys(mutation.data),
                "confidence": mutation.confidence,
                "reason": mutation.reason,
                "source": mutation.source,
                "commit_class": mutation.commit_class.value,
            }
        )
        fields_applied.append(f"{mutation.section}.{mutation.operation}")

    if plan.overlay is not None:
        overlay = normalize_turn_state_overlay_payload(
            plan.overlay,
            provenance="classifier:section_update",
            snapshot_version=plan.snapshot_version,
            snapshot_source_epoch=plan.snapshot_source_epoch,
            durable=durable,
            status=status,
            degraded_reason=degraded_reason,
        )
        if sections:
            overlay["sections"].update(sections)
            overlay["fields_applied"] = sorted(
                set(list(overlay.get("fields_applied", [])) + fields_applied)
            )
        if rejected:
            overlay.setdefault("diagnostics", {})["rejected"] = rejected
        return overlay

    if not sections and not degraded_reason and not rejected:
        return None
    return normalize_turn_state_overlay_payload(
        TurnStateOverlay(turn_id=plan.turn_id, sections=sections),
        provenance="classifier:section_update",
        snapshot_version=plan.snapshot_version,
        snapshot_source_epoch=plan.snapshot_source_epoch,
        durable=durable,
        status=status,
        degraded_reason=degraded_reason,
        fields_applied=fields_applied,
        diagnostics={"rejected": rejected} if rejected else None,
    )


def degraded_turn_state_overlay(
    *,
    turn_id: str,
    snapshot_version: str = "",
    snapshot_source_epoch: str = "",
    degraded_reason: str,
) -> dict[str, Any]:
    """Build an explicit empty overlay for degraded dispatch-critical gating."""

    return normalize_turn_state_overlay_payload(
        TurnStateOverlay(turn_id=turn_id, sections={}),
        provenance="classifier:section_update",
        snapshot_version=snapshot_version,
        snapshot_source_epoch=snapshot_source_epoch,
        durable=False,
        status="degraded",
        degraded_reason=degraded_reason,
    )


def normalize_turn_state_overlay_payload(
    overlay: TurnStateOverlay | Mapping[str, Any],
    *,
    provenance: str = "classifier:section_update",
    snapshot_version: str = "",
    snapshot_source_epoch: str = "",
    durable: bool = False,
    status: str = "",
    degraded_reason: str = "",
    fields_applied: list[str] | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize an overlay for task payload transport, without SS merge."""

    typed = (
        overlay if isinstance(overlay, TurnStateOverlay) else TurnStateOverlay.from_dict(overlay)
    )
    sections = _normalize_overlay_sections(typed.sections)
    field_names = list(fields_applied or [])
    if not field_names:
        for section, section_payload in sections.items():
            mutations = (
                section_payload.get("mutations") if isinstance(section_payload, dict) else None
            )
            if isinstance(mutations, list):
                for mutation in mutations:
                    operation = mutation.get("operation") if isinstance(mutation, dict) else ""
                    if operation:
                        field_names.append(f"{section}.{operation}")
            else:
                field_names.append(section)
    return {
        "turn_id": typed.turn_id,
        "provenance": str(provenance or "classifier:section_update"),
        "snapshot_version": str(snapshot_version or ""),
        "snapshot_source_epoch": str(snapshot_source_epoch or ""),
        "durable": bool(durable),
        "status": str(status or ""),
        "degraded_reason": str(degraded_reason or ""),
        "sections": sections,
        "fields_applied": sorted(set(field_names)),
        "diagnostics": dict(diagnostics or typed.diagnostics or {}),
    }


def attach_overlay_to_task_payload(
    payload: Mapping[str, Any],
    overlay_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return a task payload with at most one explicit turn-state overlay."""

    result = dict(payload)
    if overlay_payload:
        result[OVERLAY_TASK_PAYLOAD_KEY] = dict(overlay_payload)
    else:
        result.pop(OVERLAY_TASK_PAYLOAD_KEY, None)
    return result


def summarize_task_overlay(task_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return log-safe overlay diagnostics from a Back task payload."""

    overlay = task_payload.get(OVERLAY_TASK_PAYLOAD_KEY)
    if not isinstance(overlay, Mapping):
        return {"present": False}
    sections = overlay.get("sections") if isinstance(overlay.get("sections"), Mapping) else {}
    return {
        "present": True,
        "turn_id": str(overlay.get("turn_id", "") or ""),
        "durable": bool(overlay.get("durable", False)),
        "status": str(overlay.get("status", "") or ""),
        "degraded_reason": str(overlay.get("degraded_reason", "") or ""),
        "section_count": len(sections),
        "fields_applied": list(overlay.get("fields_applied", []) or []),
    }


def _normalize_overlay_sections(sections: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for section, payload in sections.items():
        section_name = str(section or "")
        validation = validate_target(section_name, _first_operation(payload))
        if not validation.ok and section_name not in {"", "all"}:
            raise ValueError(f"invalid overlay target {section_name}: {validation.reason}")
        normalized[section_name] = _strip_authority_keys(payload)
    return normalized


def _first_operation(payload: Any) -> str:
    if isinstance(payload, Mapping):
        mutations = payload.get("mutations")
        if isinstance(mutations, list) and mutations:
            first = mutations[0]
            if isinstance(first, Mapping):
                return str(first.get("operation", "") or "")
        return str(payload.get("operation", "") or "")
    return "update"


def _strip_authority_keys(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _strip_authority_keys(item)
            for key, item in value.items()
            if str(key) not in FORBIDDEN_OVERLAY_AUTHORITY_KEYS
        }
    if isinstance(value, list):
        return [_strip_authority_keys(item) for item in value]
    return value


__all__ = [
    "FORBIDDEN_OVERLAY_AUTHORITY_KEYS",
    "MAX_OVERLAY_MUTATIONS",
    "OVERLAY_TASK_PAYLOAD_KEY",
    "attach_overlay_to_task_payload",
    "build_dispatch_overlay_from_plan",
    "degraded_turn_state_overlay",
    "normalize_turn_state_overlay_payload",
    "summarize_task_overlay",
]
