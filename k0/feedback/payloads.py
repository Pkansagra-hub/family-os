"""Builtin payload schemas for implemented pipelines.

Issue Tracker Reality Check:
- Only P02 (Write) and P08 (Embeddings) exist today.

Stories:
- FEEDBACK-004: Define feedback schemas for P02 and P08 only
Related ADR: K020
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class P02UserCorrection(BaseModel):
    """User correction details for P02 write ingestion."""

    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1)
    expected: str | None = None
    actual: str | None = None


class P02FeedbackPayload(BaseModel):
    """Feedback payload schema for P02 (Write).

    Draft from issue tracker (FEEDBACK-issues-tracker.md).
    """

    model_config = ConfigDict(extra="forbid")

    ingested_envelope_id: str | None = None
    extraction_quality: Literal["good", "partial", "poor"] | None = None
    user_correction: P02UserCorrection | None = None


class P08FeedbackPayload(BaseModel):
    """Feedback payload schema for P08 (Embeddings).

    Draft from issue tracker (FEEDBACK-issues-tracker.md).
    """

    model_config = ConfigDict(extra="forbid")

    embedding_id: str | None = None
    retrieval_hit: bool | None = None
    retrieval_rank: int | None = Field(default=None, ge=1)
    user_relevance: Literal["relevant", "irrelevant", "partial"] | None = None
