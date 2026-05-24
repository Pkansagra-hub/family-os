"""Temporal expression candidate helpers."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from k1.temporal.types import CandidateSpan

_TEMPORAL_FIELD_HINTS = frozenset(
    {
        "after",
        "before",
        "date",
        "date_range",
        "day",
        "deadline",
        "delivery_by",
        "due",
        "due_at",
        "due_date",
        "during",
        "end",
        "end_date",
        "end_time",
        "from",
        "remind_at",
        "reminder_time",
        "schedule_for",
        "since",
        "start",
        "start_date",
        "start_time",
        "time",
        "until",
        "when",
        "window",
    }
)

_SKIP_KEYS = frozenset(
    {
        "created_at",
        "event_id",
        "grounding",
        "grounding_envelope_id",
        "payload_schema_version",
        "resolved_spatial_refs",
        "resolved_temporal_refs",
        "spatial_context_id",
        "task_id",
        "temporal_anchor_id",
        "trace_id",
        "ts_utc",
    }
)


def normalize_candidate_text(text: str) -> str:
    """Normalize a candidate without regex or prompt scraping."""

    cleaned = text.replace("_", " ").replace("-", " ").strip().lower()
    return " ".join(cleaned.split())


def ensure_candidate(value: str | CandidateSpan, *, locale: str = "en-US") -> CandidateSpan:
    if isinstance(value, CandidateSpan):
        return value
    return CandidateSpan(text=value, locale=locale)


def extract_from_dispatch(
    dispatch: Mapping[str, Any], *, locale: str = "en-US"
) -> tuple[CandidateSpan, ...]:
    """Extract typed temporal candidates from a structured dispatch payload.

    The extractor only walks Front-owned structured dispatch fields: intent
    actions, intent params, and reference_context. It emits CandidateSpan
    objects for deterministic catalog phrases, and for temporal-keyed fields
    whose value still needs the resolver to mark ambiguity explicitly.
    """

    if not isinstance(dispatch, Mapping):
        return ()

    candidates: list[CandidateSpan] = []
    seen: set[tuple[str, str]] = set()
    for path, value, temporal_hint in _dispatch_text_values(dispatch):
        extracted = _extract_from_text(value, path=path, locale=locale)
        if not extracted and temporal_hint:
            stripped = value.strip()
            if stripped:
                extracted = (
                    CandidateSpan(
                        text=stripped,
                        locale=locale,
                        metadata={"field_path": path, "source": "dispatch", "temporal_hint": True},
                    ),
                )
        for candidate in extracted:
            key = (
                normalize_candidate_text(candidate.text),
                str(candidate.metadata.get("field_path") or ""),
            )
            if not key[0] or key in seen:
                continue
            seen.add(key)
            candidates.append(candidate)
    return tuple(candidates)


def _dispatch_text_values(dispatch: Mapping[str, Any]) -> Iterator[tuple[str, str, bool]]:
    intents = dispatch.get("intents")
    if isinstance(intents, list):
        for index, intent in enumerate(intents):
            if not isinstance(intent, Mapping):
                continue
            action = intent.get("action")
            if isinstance(action, str):
                yield (f"intents[{index}].action", action, False)
            params = intent.get("params")
            if isinstance(params, Mapping):
                yield from _walk_value(params, f"intents[{index}].params")
            intent_context = intent.get("reference_context")
            if isinstance(intent_context, Mapping):
                yield from _walk_value(intent_context, f"intents[{index}].reference_context")

    action = dispatch.get("action")
    if isinstance(action, str):
        yield ("action", action, False)

    params = dispatch.get("params")
    if isinstance(params, Mapping):
        yield from _walk_value(params, "params")

    reference_context = dispatch.get("reference_context")
    if isinstance(reference_context, Mapping):
        yield from _walk_value(reference_context, "reference_context")


def _walk_value(value: Any, path: str) -> Iterator[tuple[str, str, bool]]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            key_normalized = normalize_candidate_text(key_text)
            if key_normalized in _SKIP_KEYS or key_normalized.endswith("_id"):
                continue
            child_path = f"{path}.{key_text}"
            if isinstance(child, str):
                yield (child_path, child, key_normalized in _TEMPORAL_FIELD_HINTS)
            elif isinstance(child, (Mapping, list, tuple)):
                yield from _walk_value(child, child_path)
        return

    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            if isinstance(child, str):
                yield (child_path, child, _path_has_temporal_hint(path))
            elif isinstance(child, (Mapping, list, tuple)):
                yield from _walk_value(child, child_path)


def _path_has_temporal_hint(path: str) -> bool:
    tail = path.rsplit(".", 1)[-1]
    return normalize_candidate_text(tail) in _TEMPORAL_FIELD_HINTS


def _extract_from_text(text: str, *, path: str, locale: str) -> tuple[CandidateSpan, ...]:
    tokens = _tokens_with_spans(text)
    if not tokens:
        return ()

    candidates: list[CandidateSpan] = []
    occupied: set[int] = set()
    for start_index in range(len(tokens)):
        if start_index in occupied:
            continue
        match: CandidateSpan | None = None
        match_end_index = start_index
        for width in range(4, 0, -1):
            end_index = start_index + width
            if end_index > len(tokens):
                continue
            phrase = " ".join(token for token, _start, _end in tokens[start_index:end_index])
            if _lookup_phrase(phrase) is None:
                continue
            span_start = tokens[start_index][1]
            span_end = tokens[end_index - 1][2]
            match = CandidateSpan(
                text=text[span_start:span_end],
                locale=locale,
                span_start=span_start,
                span_end=span_end,
                metadata={"field_path": path, "source": "dispatch"},
            )
            match_end_index = end_index
            break
        if match is not None:
            candidates.append(match)
            occupied.update(range(start_index, match_end_index))
    return tuple(candidates)


def _tokens_with_spans(text: str) -> tuple[tuple[str, int, int], ...]:
    tokens: list[tuple[str, int, int]] = []
    start: int | None = None
    for index, char in enumerate(text):
        if char.isalnum():
            if start is None:
                start = index
            continue
        if start is not None:
            tokens.append((text[start:index].lower(), start, index))
            start = None
    if start is not None:
        tokens.append((text[start:].lower(), start, len(text)))
    return tuple(tokens)


def _lookup_phrase(text: str) -> Any | None:
    from k1.temporal.service.phrase_catalog import lookup_phrase

    return lookup_phrase(text)


__all__ = ["ensure_candidate", "extract_from_dispatch", "normalize_candidate_text"]
