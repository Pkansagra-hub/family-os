"""Tests for ``BaseEntity`` and ``WriteContext`` (foundation §E15.0.1)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from k1.tools.family.base import BaseEntity, WriteContext, role_satisfies


class TestBaseEntity:
    def test_defaults(self) -> None:
        e = BaseEntity(id="e1")
        assert e.id == "e1"
        assert e.space_id == ""
        assert e.source == "native"
        assert e.visibility == "family"
        assert e.version == 1
        assert e.deleted_at is None
        assert e.is_deleted is False
        assert isinstance(e.created_at, datetime)
        assert e.created_at.tzinfo is timezone.utc

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            BaseEntity(id="e1", unknown="x")  # type: ignore[call-arg]

    def test_frozen(self) -> None:
        e = BaseEntity(id="e1")
        with pytest.raises(ValidationError):
            e.id = "e2"  # type: ignore[misc]

    def test_to_storage_row(self) -> None:
        e = BaseEntity(id="e1", space_id="h1", actor="u1", tags=["a", "b"])
        row = e.to_storage_row()
        assert row["id"] == "e1"
        assert row["space_id"] == "h1"
        assert row["actor"] == "u1"
        assert row["tags"] == ["a", "b"]
        assert row["visibility"] == "family"

    def test_bump_increments_version_and_records_actor(self) -> None:
        e = BaseEntity(id="e1", actor="creator")
        e2 = e.bump("editor")
        assert e2.version == 2
        assert e2.actor == "creator"  # unchanged
        assert e2.metadata["_last_actor"] == "editor"
        assert e2.updated_at >= e.updated_at

    def test_soft_delete_flag(self) -> None:
        e = BaseEntity(id="e1", deleted_at=datetime.now(timezone.utc))
        assert e.is_deleted is True


class TestWriteContext:
    def test_required_fields(self) -> None:
        ctx = WriteContext(user_id="u1", trace_id="t1")
        assert ctx.user_id == "u1"
        assert ctx.trace_id == "t1"
        assert ctx.role == "parent"
        assert ctx.band == "GREEN"
        assert ctx.face == "system"
        assert ctx.idempotency_key is None
        assert ctx.actor_member_id == "u1"
        assert ctx.idem_key is None

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            WriteContext(user_id="u1", trace_id="t", extra=1)  # type: ignore[call-arg]

    def test_invalid_role(self) -> None:
        with pytest.raises(ValidationError):
            WriteContext(user_id="u1", trace_id="t", role="admin")  # type: ignore[arg-type]

    def test_invalid_face(self) -> None:
        with pytest.raises(ValidationError):
            WriteContext(user_id="u1", trace_id="t", face="other")  # type: ignore[arg-type]


class TestRoleOrdering:
    @pytest.mark.parametrize(
        "actor,required,expected",
        [
            ("system", "parent", True),
            ("parent", "parent", True),
            ("guardian", "parent", False),
            ("child", "guardian", False),
            ("guest", "guest", True),
            ("child", "guest", True),
            ("guest", "child", False),
        ],
    )
    def test_role_satisfies(self, actor: str, required: str, expected: bool) -> None:
        assert role_satisfies(actor, required) is expected
