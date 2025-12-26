"""Feedback envelope model.

Story: FEEDBACK-001
Related ADR: K020

Notes:
- The envelope is pipeline-agnostic; the `payload` is pipeline-specific.
- Field names are aligned to the wiring guide (k0/ports/FEEDBACK.md), while
  allowing legacy aliases from the plan doc (PLAN-feedback-pipeline-system.md).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from .signals import SignalClass, SignalSource

_PIPELINE_ID_PATTERN = r"^P\d{2,3}$"  # P02, P08, ... P120
_PIPELINE_ID_RE = re.compile(_PIPELINE_ID_PATTERN)


class FeedbackCorrelation(BaseModel):
    """Links feedback to originating K0/K1 operations and target entities."""

    model_config = ConfigDict(extra="forbid")

    # Conversation/session linkage
    session_id: str | None = None
    message_id: str | None = None

    # K0 operation linkage
    query_id: str | None = None
    receipt_id: str | None = None
    recall_id: str | None = None
    response_id: str | None = None

    # Entity linkage
    event_ids: list[str] = Field(default_factory=list)

    # WAL linkage (allow both singular and plural inputs during rollout)
    wal_positions: list[int] = Field(default_factory=list)
    wal_position: int | None = None

    # Optional explicit target selector (see FEEDBACK.md)
    target_entity_type: str | None = None
    target_entity_id: str | None = None

    @field_validator(
        "session_id",
        "message_id",
        "query_id",
        "receipt_id",
        "recall_id",
        "response_id",
        "target_entity_type",
        "target_entity_id",
    )
    @classmethod
    def _normalize_optional_str(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return normalized

    @field_validator("event_ids")
    @classmethod
    def _normalize_event_ids(cls, values: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            candidate = value.strip()
            if not candidate:
                raise ValueError("event_ids entries must not be empty")
            if candidate in seen:
                continue
            seen.add(candidate)
            deduped.append(candidate)
        return deduped

    @model_validator(mode="after")
    def _merge_wal_position(self) -> "FeedbackCorrelation":
        if self.wal_position is not None:
            if self.wal_position < 0:
                raise ValueError("wal_position must be >= 0")
            if self.wal_position not in self.wal_positions:
                self.wal_positions.append(self.wal_position)
            self.wal_position = None
        return self


class FeedbackEnvelope(BaseModel):
    """Pipeline-agnostic feedback envelope.

    The `payload` field is pipeline-specific and is validated separately against
    the schema registered for `pipeline_id`.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    # Identity / versioning
    feedback_id: UUID = Field(
        default_factory=uuid4,
        validation_alias=AliasChoices("feedback_id", "envelope_id"),
    )
    feedback_version: str = Field(default="1.0")

    # Routing
    pipeline_id: str = Field(
        validation_alias=AliasChoices("pipeline_id", "target_pipeline"),
    )
    signal_class: SignalClass
    signal_subtype: str | None = None

    # Multi-tenant routing (optional during early rollout)
    tenant_id: str | None = None
    space_id: str | None = None

    # Optional source attribution
    source: SignalSource | None = None
    source_component: str | None = None

    # Tracing (optional; many flows carry these inside correlation)
    session_id: str | None = None
    trace_id: str | None = None

    correlation: FeedbackCorrelation = Field(
        default_factory=FeedbackCorrelation,
        validation_alias=AliasChoices("correlation", "correlation_ids"),
    )

    # Provenance will be formalized in FEEDBACK-000. Keep flexible for now.
    provenance: dict[str, Any] | None = None

    # Timing
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_timestamp: datetime | None = None

    # Scheduling / importance
    priority: float = Field(default=0.5, ge=0.0, le=1.0)

    # Payload
    payload: dict[str, Any]

    # Optional additional metadata
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("pipeline_id")
    @classmethod
    def _normalize_pipeline_id(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("pipeline_id must not be empty")
        if _PIPELINE_ID_RE.fullmatch(normalized) is None:
            raise ValueError(f"pipeline_id must match {_PIPELINE_ID_PATTERN}")
        return normalized

    @field_validator(
        "signal_subtype", "tenant_id", "space_id", "source_component", "session_id", "trace_id"
    )
    @classmethod
    def _normalize_optional_str(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return normalized

    @model_validator(mode="after")
    def _validate_session_consistency(self) -> "FeedbackEnvelope":
        if (
            self.session_id
            and self.correlation.session_id
            and self.session_id != self.correlation.session_id
        ):
            raise ValueError("session_id must match correlation.session_id when both are provided")
        if self.session_id is None and self.correlation.session_id is not None:
            self.session_id = self.correlation.session_id
        return self
