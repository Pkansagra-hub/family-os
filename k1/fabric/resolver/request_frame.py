"""RequestFrame types — Contract A.

Pure dataclasses for the structured input to ``ResolveSituationService.resolve()``.
No builder logic, no keyword matching.  Back populates every field explicitly.

Spec: Epic 3.2, whiteboard Contract A.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PersonRef:
    """A person reference from Back's intent extraction.

    If ``needs_resolution`` is True the resolver looks up the person in
    ``LocalProjectionStore.alias_index`` and ``household_members``.
    """

    raw: str  # e.g. "Riley", "Morgan"
    confidence: str  # "high" | "medium" | "low"
    needs_resolution: bool = True  # False = already resolved to person_id


@dataclass(frozen=True)
class ResourceRef:
    """A resource reference from Back's intent extraction."""

    raw: str  # e.g. "Riley's calendar", "family chores list"
    resource_kind_hint: str | None = None
    confidence: str = "medium"
    needs_resolution: bool = True


@dataclass(frozen=True)
class TimeWindowHint:
    """A time window extracted from the user utterance."""

    raw_phrase: str  # e.g. "next Monday at 3pm"
    resolved_start: str | None = None  # ISO 8601
    resolved_end: str | None = None
    confidence: str = "medium"


@dataclass(frozen=True)
class RequestFrameIntent:
    """One intent within a request frame."""

    intent_id: str
    action: str  # raw user action text: "Add dentist appointment"
    domain: str | None = None  # e.g. "family"
    operation_hint: str = ""  # e.g. "create", "list" — Back provides this
    resource_kind_hint: str | None = None  # e.g. "calendar_event"
    subject_hint: str | None = None  # e.g. "dentist appointment"
    params: dict[str, Any] = field(
        default_factory=dict
    )  # {person_hint: "Riley", time_hint: "next Monday at 3pm"}


@dataclass(frozen=True)
class RequestFrame:
    """The full structured request from Back to the resolver.

    This is THE input to ``ResolveSituationService.resolve()``.
    """

    request_id: str
    task_id: str
    trace_id: str
    actor_id: str
    space_id: str
    intents: list[RequestFrameIntent]
    time_window_hint: TimeWindowHint | None = None
    person_refs: list[PersonRef] = field(default_factory=list)
    resource_refs: list[ResourceRef] = field(default_factory=list)
    safety_context: dict[str, Any] = field(default_factory=dict)
    target_tier: str = "tier2"
    resolution_mode: str = "execution"
    created_at: str = ""
