"""RequestFrameBuilder — simple mapper from BackTaskEnvelope to RequestFrame.

Back is responsible for providing ``operation_hint`` and ``resource_kind_hint``
in each intent.  This builder copies them — it does NOT derive them from keywords.

Spec: Epic 3.3.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any

from k1.fabric.resolver.back_task_envelope import BackTaskEnvelope
from k1.fabric.resolver.request_frame import (
    PersonRef,
    RequestFrame,
    RequestFrameIntent,
    ResourceRef,
    TimeWindowHint,
)

# ── Parameter extraction keys ──────────────────────────────────────────
_PERSON_KEYS = ("person_hint", "participant", "attendee", "for_person", "assignee")
_RESOURCE_KEYS = (
    "resource_hint",
    "calendar_hint",
    "list_hint",
    "notebook_hint",
    "task_list_hint",
    "reminder_list_hint",
    "connector_hint",
    "contact_book_hint",
)
_TIME_KEYS = ("date", "time", "date_hint", "time_hint", "duration_minutes", "time_phrase")


# ── Builder ────────────────────────────────────────────────────────────


class RequestFrameBuilder:
    """Simple mapper: BackTaskEnvelope → RequestFrame.

    Back provides ``operation_hint`` and ``resource_kind_hint`` in every
    intent.  This builder copies them.  There is NO keyword-heuristic
    derivation, NO ``OPERATION_KEYWORDS`` table, NO ``_derive_operation_hint``.
    """

    def __init__(
        self, *, now: datetime | None = None, actor_timezone: timezone = timezone.utc
    ) -> None:
        self.now = now or datetime.now(timezone.utc)
        self.actor_timezone = actor_timezone

    # ── Public API ─────────────────────────────────────────────────

    def build(self, envelope: BackTaskEnvelope) -> RequestFrame:
        """Build a ``RequestFrame`` from a ``BackTaskEnvelope``.

        Back is responsible for providing ``operation_hint`` and
        ``resource_kind_hint`` in each intent.  This builder does NOT
        derive them.
        """
        raw_intents = envelope.task_dispatch.get("intents")
        if not isinstance(raw_intents, list):
            raw_intents = []

        intents: list[RequestFrameIntent] = []
        person_refs: list[PersonRef] = []
        resource_refs: list[ResourceRef] = []
        time_parts: list[str] = []

        for raw in raw_intents:
            if not isinstance(raw, dict):
                continue
            params = dict(raw.get("params") or {})
            action = str(raw.get("action") or envelope.task_dispatch.get("user_phrase", "compute"))

            intents.append(
                RequestFrameIntent(
                    intent_id=str(raw.get("intent_id") or "intent-" + uuid.uuid4().hex[:12]),
                    action=action,
                    domain=raw.get("domain"),
                    operation_hint=raw.get("operation_hint", ""),
                    resource_kind_hint=raw.get("resource_kind_hint"),
                    subject_hint=raw.get("subject_hint"),
                    params=params,
                )
            )

            # Extract person refs from params
            for key in _PERSON_KEYS:
                val = params.get(key)
                values = val if isinstance(val, list) else ([val] if val is not None else [])
                for item in values:
                    text = _optional_text(item)
                    if text:
                        person_refs.append(PersonRef(raw=text, confidence="medium"))

            # Extract resource refs from params
            for key in _RESOURCE_KEYS:
                text = _optional_text(params.get(key))
                if text:
                    resource_refs.append(
                        ResourceRef(
                            raw=text,
                            resource_kind_hint=_resource_ref_kind(
                                key, raw.get("resource_kind_hint")
                            ),
                            confidence="medium",
                        )
                    )

            # Collect time parts
            for key in _TIME_KEYS:
                val = params.get(key)
                if val is not None:
                    time_parts.append(str(val))

        if not intents:
            return RequestFrame(
                request_id="req-" + uuid.uuid4().hex[:12],
                task_id=envelope.task_id,
                trace_id=envelope.trace_id,
                actor_id=envelope.actor_id,
                space_id=envelope.space_id,
                intents=[],
                safety_context={
                    "actor_role": envelope.task_dispatch.get("actor_role", "parent"),
                    "safety_band": envelope.safety_band,
                    "session_id": envelope.session_id,
                },
                target_tier="tier2",
                resolution_mode="execution",
                created_at=_utc_now_iso(),
            )

        time_window = self._resolve_time_window(time_parts)

        return RequestFrame(
            request_id="req-" + uuid.uuid4().hex[:12],
            task_id=envelope.task_id,
            trace_id=envelope.trace_id,
            actor_id=envelope.actor_id,
            space_id=envelope.space_id,
            intents=intents,
            time_window_hint=time_window,
            person_refs=_dedupe_person_refs(person_refs),
            resource_refs=_dedupe_resource_refs(resource_refs),
            safety_context={
                "actor_role": envelope.task_dispatch.get("actor_role", "parent"),
                "safety_band": envelope.safety_band,
                "session_id": envelope.session_id,
            },
            target_tier="tier2",
            resolution_mode="execution",
            created_at=_utc_now_iso(),
        )

    # ── Time resolution (deterministic datetime math, not LLM) ─────

    def _resolve_time_window(self, time_parts: list[str]) -> TimeWindowHint | None:
        raw_phrase = " ".join(part for part in time_parts if part).strip()
        if not raw_phrase:
            return None

        lowered = raw_phrase.lower()
        if any(marker in lowered for marker in ("sometime", "next week", "later")):
            return TimeWindowHint(
                raw_phrase=raw_phrase,
                resolved_start=None,
                resolved_end=None,
                confidence="unresolvable",
            )

        start = _resolve_date(self.now, lowered)
        if start is None:
            return TimeWindowHint(
                raw_phrase=raw_phrase, resolved_start=None, resolved_end=None, confidence="low"
            )

        start = _apply_time(start, lowered, self.actor_timezone)
        end = start + timedelta(minutes=60)
        confidence = "high" if _has_explicit_time(lowered) else "medium"
        return TimeWindowHint(
            raw_phrase=raw_phrase,
            resolved_start=start.isoformat(),
            resolved_end=end.isoformat(),
            confidence=confidence,
        )


# ── Test helper ────────────────────────────────────────────────────────


def build_frame_from_dict(data: dict[str, Any], actor_id: str, space_id: str) -> RequestFrame:
    """Build a ``RequestFrame`` directly from a dict (bypasses envelope).

    Useful for benchmarks and tests that don't need the full envelope parse.
    """
    intents_data = data.get("intents") or []
    if isinstance(intents_data, list):
        intents = [
            RequestFrameIntent(
                intent_id=ri.get("intent_id", "intent-" + uuid.uuid4().hex[:8]),
                action=ri.get("action", ""),
                domain=ri.get("domain"),
                operation_hint=ri.get("operation_hint", ""),
                resource_kind_hint=ri.get("resource_kind_hint"),
                subject_hint=ri.get("subject_hint"),
                params=dict(ri.get("params") or {}),
            )
            for ri in intents_data
            if isinstance(ri, dict)
        ]
    else:
        intents = []

    person_refs = [
        PersonRef(
            raw=pr.get("raw", ""),
            confidence=pr.get("confidence", "medium"),
            needs_resolution=pr.get("needs_resolution", True),
        )
        for pr in (data.get("person_refs") or [])
        if isinstance(pr, dict)
    ]

    resource_refs = [
        ResourceRef(
            raw=rr.get("raw", ""),
            resource_kind_hint=rr.get("resource_kind_hint"),
            confidence=rr.get("confidence", "medium"),
            needs_resolution=rr.get("needs_resolution", True),
        )
        for rr in (data.get("resource_refs") or [])
        if isinstance(rr, dict)
    ]

    return RequestFrame(
        request_id=data.get("request_id", "req-" + uuid.uuid4().hex[:12]),
        task_id=data.get("task_id", "task-" + uuid.uuid4().hex[:8]),
        trace_id=data.get("trace_id", "trace-" + uuid.uuid4().hex[:8]),
        actor_id=actor_id,
        space_id=space_id,
        intents=intents,
        person_refs=person_refs,
        resource_refs=resource_refs,
        safety_context=data.get("safety_context", {}),
        target_tier=data.get("target_tier", "tier2"),
        resolution_mode=data.get("resolution_mode", "execution"),
        created_at=data.get("created_at", _utc_now_iso()),
    )


# ── Helpers ────────────────────────────────────────────────────────────


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _resource_ref_kind(key: str, resource_kind_hint: str | None) -> str | None:
    """Return Back's resource_kind_hint — no key-name heuristics."""
    return resource_kind_hint


# ── Deduplication ──────────────────────────────────────────────────────


def _dedupe_person_refs(refs: list[PersonRef]) -> list[PersonRef]:
    seen: set[str] = set()
    deduped: list[PersonRef] = []
    for ref in refs:
        key = ref.raw.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(ref)
    return deduped


def _dedupe_resource_refs(refs: list[ResourceRef]) -> list[ResourceRef]:
    seen: set[tuple[str, str | None]] = set()
    deduped: list[ResourceRef] = []
    for ref in refs:
        key = (ref.raw.lower(), ref.resource_kind_hint)
        if key not in seen:
            seen.add(key)
            deduped.append(ref)
    return deduped


# ── Deterministic time resolution ──────────────────────────────────────


def _resolve_date(now: datetime, lowered: str) -> datetime | None:
    """Deterministic date parsing. No LLM. No guessing."""
    if "tomorrow" in lowered:
        return (now + timedelta(days=1)).astimezone(timezone.utc).replace(second=0, microsecond=0)
    if "today" in lowered:
        return now.astimezone(timezone.utc).replace(second=0, microsecond=0)
    if "in two hours" in lowered or "in 2 hours" in lowered:
        return (now + timedelta(hours=2)).astimezone(timezone.utc).replace(second=0, microsecond=0)
    if "this weekend" in lowered:
        days_until_saturday = (5 - now.weekday()) % 7
        if days_until_saturday == 0:
            days_until_saturday = 7
        return (
            (now + timedelta(days=days_until_saturday))
            .astimezone(timezone.utc)
            .replace(second=0, microsecond=0)
        )
    weekday_match = re.search(
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", lowered
    )
    if weekday_match:
        target = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ].index(weekday_match.group(1))
        days = (target - now.weekday()) % 7
        if days == 0:
            days = 7
        return (
            (now + timedelta(days=days)).astimezone(timezone.utc).replace(second=0, microsecond=0)
        )
    if re.search(r"\d{4}-\d{2}-\d{2}", lowered):
        date_text = re.search(r"\d{4}-\d{2}-\d{2}", lowered)
        if date_text is not None:
            return datetime.fromisoformat(date_text.group(0)).replace(tzinfo=timezone.utc)
    return None


def _apply_time(date_value: datetime, lowered: str, actor_timezone: timezone) -> datetime:
    time_match = re.search(r"\b(1[0-2]|0?[1-9])(?::([0-5][0-9]))?\s*(am|pm)\b", lowered)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or "0")
        meridian = time_match.group(3)
        if meridian == "pm" and hour != 12:
            hour += 12
        if meridian == "am" and hour == 12:
            hour = 0
        return (
            date_value.astimezone(actor_timezone)
            .replace(hour=hour, minute=minute)
            .astimezone(timezone.utc)
        )
    return date_value.astimezone(actor_timezone).replace(hour=9, minute=0).astimezone(timezone.utc)


def _has_explicit_time(lowered: str) -> bool:
    return (
        bool(re.search(r"\b(1[0-2]|0?[1-9])(?::([0-5][0-9]))?\s*(am|pm)\b", lowered))
        or "in two hours" in lowered
    )
