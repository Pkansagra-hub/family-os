"""Tests for ``filter_rows`` ACL evaluator."""

from __future__ import annotations

from k1.tools.family.acl import filter_rows
from k1.tools.family.base import WriteContext


def _ctx(user_id: str = "u1", role: str = "parent", space_id: str = "") -> WriteContext:
    return WriteContext(user_id=user_id, trace_id="t", role=role, space_id=space_id)  # type: ignore[arg-type]


def _row(
    *,
    id: str = "r1",
    actor: str = "u1",
    visibility: str = "family",
    deleted_at=None,
    named_visible=None,
    space_id: str = "",
) -> dict:
    return {
        "id": id,
        "actor": actor,
        "visibility": visibility,
        "deleted_at": deleted_at,
        "named_visible": named_visible or [],
        "space_id": space_id,
    }


class TestSoftDelete:
    def test_default_drops_soft_deleted(self) -> None:
        rows = [_row(id="r1"), _row(id="r2", deleted_at="2025-01-01T00:00:00Z")]
        out = filter_rows(rows, _ctx())
        assert [r["id"] for r in out] == ["r1"]

    def test_include_deleted_keeps_them(self) -> None:
        rows = [_row(id="r2", deleted_at="2025-01-01T00:00:00Z")]
        out = filter_rows(rows, _ctx(), include_deleted=True)
        assert len(out) == 1


class TestVisibilityBand:
    def test_child_cannot_see_adults(self) -> None:
        out = filter_rows([_row(visibility="adults")], _ctx(role="child"))
        assert out == []

    def test_guest_only_sees_family(self) -> None:
        rows = [_row(visibility="family"), _row(visibility="private"), _row(visibility="adults")]
        out = filter_rows(rows, _ctx(role="guest"))
        assert [r["visibility"] for r in out] == ["family"]


class TestPrivate:
    def test_private_visible_to_creator(self) -> None:
        out = filter_rows([_row(visibility="private", actor="u1")], _ctx(user_id="u1"))
        assert len(out) == 1

    def test_private_invisible_cross_user_without_privilege(self) -> None:
        # 'guest' has no cross_user privilege; row visibility='private' also outside guest's visible bands.
        out = filter_rows(
            [_row(visibility="private", actor="u2")], _ctx(user_id="u1", role="guest")
        )
        assert out == []

    def test_private_visible_cross_user_to_guardian(self) -> None:
        out = filter_rows(
            [_row(visibility="private", actor="u2")], _ctx(user_id="u1", role="guardian")
        )
        assert len(out) == 1


class TestNamed:
    def test_named_visible_to_allow_listed_member(self) -> None:
        out = filter_rows(
            [_row(visibility="named", actor="u2", named_visible=["u1"])],
            _ctx(user_id="u1", role="child"),
        )
        assert len(out) == 1

    def test_named_invisible_when_not_in_list(self) -> None:
        out = filter_rows(
            [_row(visibility="named", actor="u2", named_visible=["uX"])],
            _ctx(user_id="u1", role="child"),
        )
        assert out == []


class TestSpace:
    def test_space_mismatch_dropped(self) -> None:
        out = filter_rows([_row(space_id="hA")], _ctx(space_id="hB"))
        assert out == []

    def test_same_space_kept(self) -> None:
        out = filter_rows([_row(space_id="hA")], _ctx(space_id="hA"))
        assert len(out) == 1

    def test_empty_caller_space_disables_gate(self) -> None:
        out = filter_rows([_row(space_id="hA")], _ctx(space_id=""))
        assert len(out) == 1
