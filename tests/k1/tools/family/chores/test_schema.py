"""Tests for ChoreTemplate and ChoreOccurrence Pydantic schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from k1.tools.family.chores.schema import ChoreOccurrence, ChoreTemplate

# ---------------------------------------------------------------------------
# ChoreTemplate
# ---------------------------------------------------------------------------


def test_template_minimal_construction() -> None:
    t = ChoreTemplate(id="t1", actor="u1", title="Vacuum")
    assert t.frequency == "weekly"
    assert t.base_points == 0
    assert t.is_active is True


def test_template_invalid_frequency() -> None:
    with pytest.raises(ValidationError):
        ChoreTemplate(id="t1", actor="u1", title="X", frequency="hourly")  # type: ignore[call-arg]


def test_template_base_points_negative_rejected() -> None:
    with pytest.raises(ValidationError):
        ChoreTemplate(id="t1", actor="u1", title="X", base_points=-1)


def test_template_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        ChoreTemplate(id="t1", actor="u1", title="X", oops="x")  # type: ignore[call-arg]


def test_template_is_frozen() -> None:
    t = ChoreTemplate(id="t1", actor="u1", title="Vacuum")
    with pytest.raises(ValidationError):
        t.title = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ChoreOccurrence
# ---------------------------------------------------------------------------


def test_occurrence_minimal_construction() -> None:
    o = ChoreOccurrence(id="o1", actor="u1", template_id="t1", title="Vacuum")
    assert o.status == "pending"
    assert o.completed_at is None
    assert o.skipped_at is None


def test_occurrence_done_requires_completed_at() -> None:
    with pytest.raises(ValidationError, match="completed_at"):
        ChoreOccurrence(
            id="o1",
            actor="u1",
            template_id="t1",
            title="X",
            status="done",
        )


def test_occurrence_skipped_requires_skipped_at() -> None:
    with pytest.raises(ValidationError, match="skipped_at"):
        ChoreOccurrence(
            id="o1",
            actor="u1",
            template_id="t1",
            title="X",
            status="skipped",
        )


def test_occurrence_completed_at_must_be_none_when_pending() -> None:
    with pytest.raises(ValidationError, match="completed_at must be None"):
        ChoreOccurrence(
            id="o1",
            actor="u1",
            template_id="t1",
            title="X",
            status="pending",
            completed_at="2026-05-12T10:00:00Z",
        )


def test_occurrence_skipped_at_must_be_none_when_not_skipped() -> None:
    with pytest.raises(ValidationError, match="skipped_at must be None"):
        ChoreOccurrence(
            id="o1",
            actor="u1",
            template_id="t1",
            title="X",
            status="pending",
            skipped_at="2026-05-12T10:00:00Z",
        )


def test_occurrence_points_negative_rejected() -> None:
    with pytest.raises(ValidationError):
        ChoreOccurrence(
            id="o1",
            actor="u1",
            template_id="t1",
            title="X",
            points_awarded=-5,
        )


def test_occurrence_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        ChoreOccurrence(
            id="o1",
            actor="u1",
            template_id="t1",
            title="X",
            oops="x",  # type: ignore[call-arg]
        )


def test_occurrence_is_frozen() -> None:
    o = ChoreOccurrence(id="o1", actor="u1", template_id="t1", title="X")
    with pytest.raises(ValidationError):
        o.title = "changed"  # type: ignore[misc]
