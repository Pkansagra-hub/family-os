"""TrustLevelSection HOT cognitive state tests."""

from __future__ import annotations

import pytest

from k1.sessionstate.sections.trust_level import TrustLevelSection
from k1.sessionstate.sizetracker import ALL_SECTIONS, HOT_SECTIONS
from k1.sessionstate.tiers.hot import HotTier


def test_trust_level_defaults_and_bounded_update() -> None:
    section = TrustLevelSection(session_id="s1")

    assert section.name == "trust_level"
    assert section.tier == "hot"
    assert section.can_evict is False
    assert section.trust_score == 0.5
    assert section.band == "steady"

    section.update(delta=-0.12, confidence=0.9, signal="correction", stance="repairing")

    data = section.to_dict()
    assert data["trust_score"] == pytest.approx(0.38)
    assert data["band"] == "guarded"
    assert data["confidence"] == 0.9
    assert data["stance"] == "repairing"
    assert data["recent_signals"][-1]["signal"] == "correction"


def test_trust_level_registered_in_hot_sessionstate() -> None:
    tier = HotTier(session_id="s1")

    assert "trust_level" in ALL_SECTIONS
    assert "trust_level" in HOT_SECTIONS
    assert isinstance(tier.get_section("trust_level"), TrustLevelSection)


def test_trust_level_json_roundtrip_and_apply() -> None:
    section = TrustLevelSection(session_id="s1")
    section.apply(
        "update",
        {
            "trust_score": 0.82,
            "confidence": 0.8,
            "signal": "explicit_confidence",
            "reason": "User said K1 handled it correctly.",
            "source": "classifier:section_update",
        },
    )

    restored = TrustLevelSection()
    restored.from_flatbuffer(section.to_flatbuffer())

    assert restored.trust_score == pytest.approx(0.82)
    assert restored.band == "high"
    assert restored.to_dict()["recent_signals"][-1]["source"] == "classifier:section_update"

    restored.apply("clear", {})
    assert restored.trust_score == 0.5
    assert restored.to_dict()["recent_signals"] == []
