"""Tests for ``TaskItem`` and ``TaskList`` Pydantic schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from k1.tools.family.tasks.schema import TaskItem, TaskList


def test_task_item_minimal_construction() -> None:
    item = TaskItem(id="t1", actor="u1", title="Pick up Riley")
    assert item.title == "Pick up Riley"
    assert item.status == "open"
    assert item.priority == "medium"
    assert item.completed_at is None
    assert item.assigned_to is None
    assert item.is_deleted is False


def test_task_item_completed_at_only_allowed_when_done() -> None:
    with pytest.raises(ValidationError):
        TaskItem(
            id="t1",
            actor="u1",
            title="X",
            status="open",
            completed_at="2026-05-11T10:00:00+00:00",
        )


def test_task_item_done_with_completed_at_is_valid() -> None:
    item = TaskItem(
        id="t1",
        actor="u1",
        title="X",
        status="done",
        completed_at="2026-05-11T10:00:00+00:00",
    )
    assert item.completed_at == "2026-05-11T10:00:00+00:00"


def test_task_item_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        TaskItem(
            id="t1",
            actor="u1",
            title="X",
            oops="extra",  # type: ignore[call-arg]
        )


def test_task_item_is_frozen() -> None:
    item = TaskItem(id="t1", actor="u1", title="X")
    with pytest.raises(ValidationError):
        item.title = "changed"  # type: ignore[misc]


def test_task_list_minimal() -> None:
    lst = TaskList(id="l1", actor="u1", name="Household")
    assert lst.name == "Household"
    assert lst.color is None
    assert lst.version == 1
