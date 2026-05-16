"""Typed actor handoff frames for Concierge Front/Back boundaries."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _compact(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except TypeError:
        return str(value)


def _as_non_empty_strings(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return [str(item).strip() for item in values if str(item or "").strip()]


def _semantic_payloads_from_item(item: Any) -> list[dict[str, Any]]:
    if not isinstance(item, dict):
        return []
    payloads: list[dict[str, Any]] = []
    for key in ("semantic", "semantic_context", "_semantic"):
        payload = item.get(key)
        if isinstance(payload, dict):
            payloads.append(payload)
    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        for key in ("semantic", "_semantic"):
            payload = metadata.get(key)
            if isinstance(payload, dict):
                payloads.append(payload)
    return payloads


def _unique_non_empty(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        clean = " ".join(str(line or "").split())
        if clean and clean not in seen:
            seen.add(clean)
            out.append(clean)
    return out


def _get_section(ss: Any, name: str) -> Any:
    if ss is None:
        return None
    if hasattr(ss, "get_section"):
        try:
            return ss.get_section(name)
        except Exception:
            return None
    return getattr(ss, name, None)


def affect_dict_from_session(ss: Any) -> dict[str, Any]:
    section = _get_section(ss, "affective_now")
    if section is None:
        return {}
    if hasattr(section, "to_dict"):
        try:
            return dict(section.to_dict())
        except Exception:
            return {}
    return section if isinstance(section, dict) else {}


def build_emotional_context(affect_dict: dict[str, Any]) -> str:
    """Return Front guidance for weaving async results into the conversation."""
    if not affect_dict:
        return (
            "User affect is neutral. Standard weave -- respond to their "
            "topic first, then naturally transition to the result."
        )

    valence = affect_dict.get("valence", 0.0)
    band = affect_dict.get("band", affect_dict.get("affect_band", ""))

    if band == "crisis" or valence < -0.5:
        return (
            "The user is in emotional distress. Be extremely gentle. "
            "Acknowledge their state before presenting any result. "
            "If the result is not safety-critical, consider deferring it entirely. "
            "Example: 'I know this is a really hard time...'"
        )
    if valence < -0.3:
        return (
            "The user's mood is negative (sad, frustrated, or stressed). "
            "Be sensitive. Acknowledge what they're going through before "
            "transitioning to the result. Frame results positively: "
            "'One less thing to worry about -- your hotel is confirmed.'"
        )
    if band == "positive" or valence > 0.3:
        return (
            "The user is in a positive mood. Match their energy. "
            "Present results enthusiastically: 'Great news -- everything went through!'"
        )
    return (
        "User affect is neutral. Standard weave -- respond to their "
        "topic first, then naturally transition to the result."
    )


@dataclass(frozen=True, slots=True)
class BackResultFrame:
    """Typed result frame produced by Back and interpreted by Front."""

    task_id: str = ""
    status: str = "complete"
    result_type: str = "complete"
    facts: list[Any] = field(default_factory=list)
    artifacts: list[Any] = field(default_factory=list)
    confidence: float | None = None
    blockers: list[Any] = field(default_factory=list)
    suggested_next_action: str = ""
    semantic_context: dict[str, Any] = field(default_factory=dict)
    presentation_guidance: str = ""
    tool_call_summaries: list[dict[str, Any]] = field(default_factory=list)
    raw_final_answer: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "_frame_type": "back_result",
            "task_id": self.task_id,
            "status": self.status,
            "result_type": self.result_type,
            "facts": list(self.facts),
            "artifacts": list(self.artifacts),
            "confidence": self.confidence,
            "blockers": list(self.blockers),
            "suggested_next_action": self.suggested_next_action,
            "semantic_context": dict(self.semantic_context),
            "presentation_guidance": self.presentation_guidance,
            "tool_call_summaries": list(self.tool_call_summaries),
            "raw_final_answer": self.raw_final_answer,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> BackResultFrame:
        source = _as_dict(data)
        if isinstance(source.get("frame"), dict):
            source = _as_dict(source["frame"])

        facts = source.get("facts")
        if facts is None:
            facts = source.get("results", [])
        artifacts = source.get("artifacts")
        if artifacts is None:
            artifacts = source.get("artifacts_created", [])

        tool_summaries = [
            dict(item)
            for item in _as_list(source.get("tool_call_summaries", []))
            if isinstance(item, dict)
        ]
        return cls(
            task_id=str(source.get("task_id", "") or ""),
            status=str(source.get("status", "complete") or "complete"),
            result_type=str(source.get("result_type", "complete") or "complete"),
            facts=_as_list(facts),
            artifacts=_as_list(artifacts),
            confidence=source.get("confidence"),
            blockers=_as_list(source.get("blockers", [])),
            suggested_next_action=str(source.get("suggested_next_action", "") or ""),
            semantic_context=_as_dict(
                source.get("semantic_context") or source.get("semantic") or {}
            ),
            presentation_guidance=str(source.get("presentation_guidance", "") or ""),
            tool_call_summaries=tool_summaries,
            raw_final_answer=str(
                source.get("raw_final_answer") or source.get("final_answer") or ""
            ),
        )

    def semantic_payloads(self) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        if self.semantic_context:
            payloads.append(dict(self.semantic_context))
        for item in [*self.facts, *self.artifacts]:
            payloads.extend(_semantic_payloads_from_item(item))
        return payloads

    def semantic_guidance_text(self) -> str:
        lines: list[str] = []
        if self.presentation_guidance:
            lines.append(f"Presentation guidance: {self.presentation_guidance}")

        for payload in self.semantic_payloads():
            presentation = payload.get("presentation")
            if isinstance(presentation, dict):
                lines.extend(
                    f"Presentation {key}: {value}"
                    for key, value in presentation.items()
                    if value not in (None, "", [])
                )
            elif isinstance(payload.get("presentation_guidance"), str):
                lines.append(f"Presentation guidance: {payload['presentation_guidance']}")

            authority = payload.get("authority")
            if not isinstance(authority, dict):
                authority = {
                    key: payload.get(key)
                    for key in (
                        "guidance_scope",
                        "authority_source",
                        "requires_external_authority",
                        "boundary_note",
                    )
                    if key in payload
                }
            if authority:
                parts = []
                scope = authority.get("guidance_scope") or authority.get("scope")
                source = authority.get("authority_source") or authority.get("source")
                requires = authority.get("requires_external_authority")
                note = authority.get("boundary_note") or authority.get("note")
                if scope:
                    parts.append(f"scope={scope}")
                if source:
                    parts.append(f"source={source}")
                if requires is not None:
                    parts.append(f"external_authority_required={bool(requires)}")
                if note:
                    parts.append(str(note))
                if parts:
                    lines.append("Authority boundary: " + "; ".join(parts))

            future_weave = payload.get("future_weave")
            if isinstance(future_weave, dict):
                weave_parts: list[str] = []
                for key in ("triggers", "follow_up", "follow_up_after", "prep_notes", "priority"):
                    if key in future_weave:
                        vals = _as_non_empty_strings(future_weave.get(key))
                        if vals:
                            weave_parts.append(f"{key}={', '.join(vals)}")
                if weave_parts:
                    lines.append("Future weave: " + "; ".join(weave_parts))

            prep_notes = _as_non_empty_strings(payload.get("prep_notes"))
            if prep_notes:
                lines.append("Prep/context notes: " + "; ".join(prep_notes))

        return "\n".join(_unique_non_empty(lines))

    def fact_lines(self) -> list[str]:
        lines: list[str] = []
        for item in self.facts:
            if isinstance(item, dict):
                title = item.get("title") or item.get("name") or item.get("summary")
                url = item.get("url") or item.get("href")
                snippet = item.get("snippet") or item.get("body")
                if title:
                    line = f"* {title}"
                    if url:
                        line += f" -- {url}"
                    if snippet:
                        line += f"\n  {str(snippet)[:120]}"
                    lines.append(line)
                else:
                    lines.append(f"* {_compact(item)}")
            elif item not in (None, ""):
                lines.append(f"* {_compact(item)}")
        return lines

    def artifact_lines(self) -> list[str]:
        lines: list[str] = []
        for item in self.artifacts:
            if isinstance(item, dict):
                label = item.get("summary") or item.get("name") or item.get("type")
                lines.append(f"* {label or _compact(item)}")
            elif item not in (None, ""):
                lines.append(f"* {_compact(item)}")
        return lines

    def summary_text(self) -> str:
        parts = self.fact_lines()
        artifact_lines = self.artifact_lines()
        if artifact_lines:
            parts.append("Artifacts:")
            parts.extend(artifact_lines)
        if self.blockers:
            parts.append("Blockers:")
            parts.extend(f"* {_compact(item)}" for item in self.blockers)
        if self.suggested_next_action:
            parts.append(f"Suggested next action: {self.suggested_next_action}")
        if not parts and self.raw_final_answer:
            parts.append(self.raw_final_answer)
        return "\n".join(parts)


@dataclass(frozen=True, slots=True)
class HILResolutionFrame:
    """Typed human decision captured by Front for HIL response/resume paths."""

    task_id: str = ""
    hil_request_id: str = ""
    kind: str = "clarification"
    raw_user_text: str = ""
    selected_option: Any = None
    target: Any = None
    approval: bool | None = None
    additional_info: str = ""
    modifications: dict[str, Any] | None = None
    legacy_bridge: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = self.to_resolution_dict()
        data["raw_user_text"] = self.raw_user_text
        return data

    def to_resolution_dict(self) -> dict[str, Any]:
        return {
            "_frame_type": "hil_resolution",
            "task_id": self.task_id,
            "hil_request_id": self.hil_request_id,
            "kind": self.kind,
            "selected_option": self.selected_option,
            "target": self.target,
            "approval": self.approval,
            "additional_info": self.additional_info,
            "modifications": self.modifications,
            "legacy_bridge": self.legacy_bridge,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> HILResolutionFrame:
        source = _as_dict(data)
        approval = source.get("approval")
        return cls(
            task_id=str(source.get("task_id", "") or ""),
            hil_request_id=str(source.get("hil_request_id", "") or ""),
            kind=str(source.get("kind") or source.get("hil_type") or "clarification"),
            raw_user_text=str(source.get("raw_user_text", "") or ""),
            selected_option=source.get("selected_option"),
            target=source.get("target"),
            approval=approval if isinstance(approval, bool) else None,
            additional_info=str(source.get("additional_info", "") or ""),
            modifications=(
                source.get("modifications")
                if isinstance(source.get("modifications"), dict)
                else None
            ),
            legacy_bridge=bool(source.get("legacy_bridge", False)),
        )

    @classmethod
    def from_resolution_dict(
        cls,
        data: dict[str, Any] | None,
        *,
        task_id: str = "",
        hil_request_id: str = "",
        raw_user_text: str = "",
    ) -> HILResolutionFrame:
        source = _as_dict(data)
        merged = {
            **source,
            "task_id": source.get("task_id") or task_id,
            "hil_request_id": source.get("hil_request_id") or hil_request_id,
            "raw_user_text": source.get("raw_user_text") or raw_user_text,
        }
        return cls.from_dict(merged)

    def command_summary(self) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "kind": self.kind,
            "selected_option": self.selected_option,
            "target": self.target,
            "approval": self.approval,
            "modifications": self.modifications,
        }
        if self.kind in {"clarification", "needs_human"}:
            summary["additional_info"] = self.additional_info
        return {k: v for k, v in summary.items() if v not in (None, "", [])}


@dataclass(frozen=True, slots=True)
class WeavePresentationFrame:
    """Typed frame for asynchronous result presentation."""

    result_count: int = 0
    results_summary: str = ""
    current_thread: str = ""
    urgency_label: str = ""
    emotional_context: str = ""
    semantic_guidance: str = ""
    presentation_mode: str = "weave"
    source_task_ids: list[str] = field(default_factory=list)

    def to_scenario_dict(self) -> dict[str, Any]:
        return {
            "result_count": self.result_count,
            "results_summary": self.results_summary,
            "current_thread": self.current_thread,
            "urgency_label": self.urgency_label,
            "emotional_context": self.emotional_context,
            "semantic_guidance": self.semantic_guidance,
            "presentation_mode": self.presentation_mode,
            "source_task_ids": list(self.source_task_ids),
        }

    @classmethod
    def from_payload_and_pending(
        cls,
        payload: dict[str, Any],
        pending: list[Any] | None,
        ss: Any,
    ) -> WeavePresentationFrame:
        pending_items = list(pending or [])
        payload_results = payload.get("results")
        if pending is None and isinstance(payload_results, list):
            pending_items = list(payload_results)
        elif pending is None:
            control = _get_section(ss, "control")
            pending_items = list(getattr(control, "pending_results", None) or [])

        thread_name = str(payload.get("current_thread", "") or "")
        narrative = _get_section(ss, "narrative_active")
        if not thread_name and narrative and hasattr(narrative, "get_active_thread_name"):
            thread_name = narrative.get_active_thread_name() or ""

        emotional_context = build_emotional_context(affect_dict_from_session(ss))

        if isinstance(payload_results, list) and len(payload_results) == 1:
            first = payload_results[0]
            if isinstance(first, dict) and first.get("is_digest"):
                return cls(
                    result_count=int(first.get("digest_count", 0) or 0),
                    results_summary=str(first.get("digest_summary", "") or ""),
                    current_thread=thread_name,
                    urgency_label="Summary -- present as a brief update",
                    emotional_context=emotional_context,
                    semantic_guidance=str(first.get("semantic_guidance", "") or ""),
                    presentation_mode="digest",
                    source_task_ids=[],
                )

        payload_count = payload.get("count")
        result_count = payload_count if isinstance(payload_count, int) else len(pending_items)
        payload_summary = payload.get("results_summary")
        results_summary = str(payload_summary) if isinstance(payload_summary, str) else ""
        source_task_ids: list[str] = []
        semantic_lines: list[str] = []

        if not results_summary:
            summary_lines: list[str] = []
            for item in pending_items:
                inner = item.get("result", item) if isinstance(item, dict) else item
                if not isinstance(inner, dict):
                    continue
                task_id = str(inner.get("task_id", "") or "")
                if task_id:
                    source_task_ids.append(task_id)
                action = str(inner.get("action", "") or "")
                frame = BackResultFrame.from_dict(inner.get("frame", inner))
                frame_summary = frame.summary_text()
                frame_semantics = frame.semantic_guidance_text()
                if frame_semantics:
                    semantic_lines.extend(frame_semantics.splitlines())
                if action and frame_summary:
                    summary_lines.append(f"- {action}:\n{frame_summary}")
                elif frame_summary:
                    summary_lines.append(f"- {frame_summary}")
            results_summary = "\n".join(summary_lines)

        if isinstance(payload.get("semantic_guidance"), str):
            semantic_lines.append(payload["semantic_guidance"])

        has_critical = any(
            (item.get("result", item) if isinstance(item, dict) else {}).get("urgency")
            in ("critical", "urgent")
            for item in pending_items
            if isinstance(item, dict)
        )
        if has_critical:
            urgency_label = (
                "URGENT -- present the time-critical result(s) prominently. "
                "The user needs to know about this immediately."
            )
        elif result_count >= 3:
            urgency_label = (
                "Summary -- these are routine updates. Present as a brief, natural aside."
            )
        else:
            urgency_label = "Informational -- weave this result lightly into the conversation."

        return cls(
            result_count=result_count,
            results_summary=results_summary,
            current_thread=thread_name,
            urgency_label=urgency_label,
            emotional_context=emotional_context,
            semantic_guidance="\n".join(_unique_non_empty(semantic_lines)),
            presentation_mode=str(payload.get("presentation_mode") or "weave"),
            source_task_ids=source_task_ids,
        )
