"""Tests for ``VisibilityPolicy`` (§E15.0.3)."""

from __future__ import annotations

import pytest

from k1.tools.family.base import BaseEntity, WriteContext
from k1.tools.family.definition import ActionSpec
from k1.tools.family.policy import VisibilityPolicy, default_policy


def _ctx(role: str = "parent", band: str = "GREEN") -> WriteContext:
    return WriteContext(user_id="u1", trace_id="t", role=role, band=band)  # type: ignore[arg-type]


def _action(min_band: str = "GREEN", allowed_roles=None) -> ActionSpec:
    return ActionSpec(
        name="x",
        kind="write",
        summary="x",
        min_band=min_band,  # type: ignore[arg-type]
        allowed_roles=allowed_roles or ["parent", "guardian", "system"],
    )


class TestBandGate:
    def test_green_action_allowed_under_green_band(self) -> None:
        p = default_policy()
        assert p.check_band(_action("GREEN"), _ctx(band="GREEN")) is True

    def test_amber_action_blocked_under_red_band(self) -> None:
        p = default_policy()
        assert p.check_band(_action("AMBER"), _ctx(band="RED")) is False

    def test_disable_band_gate(self) -> None:
        p = VisibilityPolicy(enforce_band_gates=False)
        assert p.check_band(_action("AMBER"), _ctx(band="CRISIS")) is True


class TestRoleGate:
    def test_role_in_allowed(self) -> None:
        p = default_policy()
        assert p.check_role(_action(allowed_roles=["parent"]), _ctx(role="parent")) is True

    def test_role_not_in_allowed(self) -> None:
        p = default_policy()
        assert p.check_role(_action(allowed_roles=["parent"]), _ctx(role="child")) is False


class TestReadVisibility:
    @pytest.mark.parametrize(
        "role,visible",
        [
            ("parent", {"family", "adults", "named", "private"}),
            ("guardian", {"family", "adults", "named", "private"}),
            ("elder", {"family", "adults", "named"}),
            ("child", {"family", "named"}),
            ("guest", {"family"}),
            ("system", {"family", "adults", "named", "private"}),
        ],
    )
    def test_default_table(self, role: str, visible: set[str]) -> None:
        p = default_policy()
        assert set(p.visible_bands_for(role)) == visible  # type: ignore[arg-type]


class TestApplyRules:
    def test_classroom_imports_default_to_family(self) -> None:
        p = default_policy()
        e = BaseEntity(id="e1", source="classroom", visibility="adults")
        assert p.apply(e, "child") == "family"

    def test_google_work_default_to_adults(self) -> None:
        p = default_policy()
        e = BaseEntity(id="e1", source="google", source_label="work", visibility="family")
        assert p.apply(e, "parent") == "adults"

    def test_outlook_default_to_adults_unless_family_tag(self) -> None:
        p = default_policy()
        e = BaseEntity(id="e1", source="outlook", visibility="family")
        assert p.apply(e, "parent") == "adults"
        e2 = BaseEntity(id="e2", source="outlook", visibility="adults", tags=["family"])
        assert p.apply(e2, "parent") == "family"

    def test_sensitive_keywords_force_adults(self) -> None:
        p = default_policy()
        e = BaseEntity(id="e1", source="native", visibility="family", tags=["doctor"])
        assert p.apply(e, "parent") == "adults"

    def test_native_default_preserves_stored_visibility(self) -> None:
        p = default_policy()
        e = BaseEntity(id="e1", source="native", visibility="private")
        assert p.apply(e, "parent") == "private"


class TestCrossUser:
    def test_default_roles(self) -> None:
        p = default_policy()
        assert p.can_read_cross_user("parent") is True
        assert p.can_read_cross_user("guest") is False
