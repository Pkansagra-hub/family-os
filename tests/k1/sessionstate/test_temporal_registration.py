"""Tests for TemporalSection SessionState registration."""

from __future__ import annotations

from k1.sessionstate.sections.temporal import TemporalSection
from k1.sessionstate.sizetracker import (
    HOT_SECTIONS,
    NEVER_EVICT_SECTIONS,
    SECTION_BUDGETS,
)
from k1.sessionstate.tiers.hot import HOT_SECTION_NAMES, HotTier


def test_temporal_is_registered_hot_never_evict() -> None:
    assert "temporal" in HOT_SECTIONS
    assert "temporal" in NEVER_EVICT_SECTIONS
    assert SECTION_BUDGETS["temporal"].max_bytes == 4 * 1024
    assert "temporal" in HOT_SECTION_NAMES


def test_hot_tier_instantiates_temporal_section() -> None:
    tier = HotTier(session_id="s1")
    section = tier.get_section("temporal")
    assert isinstance(section, TemporalSection)
