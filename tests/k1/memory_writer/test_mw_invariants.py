"""Tests for MW-12 temporal_links invariant (assert_mw12_temporal_links).

Epic 2.3 Issue 2.3.2 -- Validates that temporal_links on MemoryAtom
conform to the TemporalLink contract: type, count, field constraints.
"""

from __future__ import annotations

import pytest

from k1.memory_writer.config import MWConfig
from k1.memory_writer.invariants import InvariantViolation, assert_mw12_temporal_links
from k1.memory_writer.types import TemporalLink, TemporalLinkType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _link(**overrides) -> TemporalLink:
    """Build a valid TemporalLink with sensible defaults, apply overrides."""
    defaults = dict(
        mentioned_time="yesterday",
        resolved_epoch_ms=1700000000000,
        uncertainty_window_ms=86400000,
        link_type="RETROSPECTIVE",
        confidence=0.95,
    )
    defaults.update(overrides)
    return TemporalLink(**defaults)


# ---------------------------------------------------------------------------
# TestMW12ValidCases -- should NOT raise
# ---------------------------------------------------------------------------


class TestMW12ValidCases:
    """Cases that must pass validation without error."""

    def test_empty_list(self):
        assert_mw12_temporal_links([])

    def test_empty_tuple(self):
        assert_mw12_temporal_links(())

    def test_single_link(self):
        assert_mw12_temporal_links([_link()])

    def test_three_links(self):
        links = [
            _link(mentioned_time="yesterday", link_type="RETROSPECTIVE"),
            _link(mentioned_time="next Friday", link_type="PROSPECTIVE"),
            _link(mentioned_time="Christmas", link_type="PROSPECTIVE"),
        ]
        assert_mw12_temporal_links(links)

    def test_five_links_max(self):
        links = [_link(mentioned_time=f"time_{i}") for i in range(5)]
        assert_mw12_temporal_links(links)

    def test_tuple_input(self):
        assert_mw12_temporal_links((_link(), _link()))

    def test_confidence_zero(self):
        assert_mw12_temporal_links([_link(confidence=0.0)])

    def test_confidence_one(self):
        assert_mw12_temporal_links([_link(confidence=1.0)])

    def test_uncertainty_zero(self):
        assert_mw12_temporal_links([_link(uncertainty_window_ms=0)])

    def test_all_six_link_types(self):
        for lt in TemporalLinkType:
            assert_mw12_temporal_links([_link(link_type=lt.value)])

    def test_with_config(self):
        cfg = MWConfig()
        assert cfg.max_temporal_links_per_atom == 5
        assert_mw12_temporal_links([_link()], config=cfg)


# ---------------------------------------------------------------------------
# TestMW12CountViolations -- too many links
# ---------------------------------------------------------------------------


class TestMW12CountViolations:

    def test_six_links_rejected(self):
        links = [_link(mentioned_time=f"t_{i}") for i in range(6)]
        with pytest.raises(InvariantViolation, match="MW-12") as exc_info:
            assert_mw12_temporal_links(links)
        assert "6 items" in str(exc_info.value)
        assert "exceeding limit of 5" in str(exc_info.value)

    def test_custom_config_limit(self):
        cfg = MWConfig(max_temporal_links_per_atom=3)
        links = [_link(mentioned_time=f"t_{i}") for i in range(4)]
        with pytest.raises(InvariantViolation, match="MW-12"):
            assert_mw12_temporal_links(links, config=cfg)

    def test_custom_config_allows_within_limit(self):
        cfg = MWConfig(max_temporal_links_per_atom=3)
        links = [_link(mentioned_time=f"t_{i}") for i in range(3)]
        assert_mw12_temporal_links(links, config=cfg)


# ---------------------------------------------------------------------------
# TestMW12TypeViolations -- wrong container type
# ---------------------------------------------------------------------------


class TestMW12TypeViolations:

    def test_string_rejected(self):
        with pytest.raises(InvariantViolation, match="MW-12"):
            assert_mw12_temporal_links("not a list")

    def test_dict_rejected(self):
        with pytest.raises(InvariantViolation, match="MW-12"):
            assert_mw12_temporal_links({"a": 1})

    def test_none_rejected(self):
        with pytest.raises(InvariantViolation, match="MW-12"):
            assert_mw12_temporal_links(None)

    def test_int_rejected(self):
        with pytest.raises(InvariantViolation, match="MW-12"):
            assert_mw12_temporal_links(42)


# ---------------------------------------------------------------------------
# TestMW12MentionedTimeViolations
# ---------------------------------------------------------------------------


class TestMW12MentionedTimeViolations:

    def test_empty_mentioned_time(self):
        link = _link(mentioned_time="")
        with pytest.raises(InvariantViolation, match="mentioned_time is missing or empty"):
            assert_mw12_temporal_links([link])

    def test_whitespace_mentioned_time(self):
        link = _link(mentioned_time="   ")
        with pytest.raises(InvariantViolation, match="mentioned_time is missing or empty"):
            assert_mw12_temporal_links([link])

    def test_second_link_bad_mentioned_time(self):
        links = [_link(), _link(mentioned_time="")]
        with pytest.raises(InvariantViolation, match=r"temporal_links\[1\]"):
            assert_mw12_temporal_links(links)


# ---------------------------------------------------------------------------
# TestMW12LinkTypeViolations
# ---------------------------------------------------------------------------


class TestMW12LinkTypeViolations:

    def test_invalid_link_type(self):
        link = _link(link_type="PAST")
        with pytest.raises(InvariantViolation, match="not a valid TemporalLinkType"):
            assert_mw12_temporal_links([link])

    def test_lowercase_link_type_rejected(self):
        link = _link(link_type="retrospective")
        with pytest.raises(InvariantViolation, match="not a valid TemporalLinkType"):
            assert_mw12_temporal_links([link])

    def test_empty_link_type(self):
        link = _link(link_type="")
        with pytest.raises(InvariantViolation, match="not a valid TemporalLinkType"):
            assert_mw12_temporal_links([link])


# ---------------------------------------------------------------------------
# TestMW12ConfidenceViolations
# ---------------------------------------------------------------------------


class TestMW12ConfidenceViolations:

    def test_negative_confidence(self):
        link = _link(confidence=-0.1)
        with pytest.raises(InvariantViolation, match="confidence"):
            assert_mw12_temporal_links([link])

    def test_over_one_confidence(self):
        link = _link(confidence=1.01)
        with pytest.raises(InvariantViolation, match="confidence"):
            assert_mw12_temporal_links([link])


# ---------------------------------------------------------------------------
# TestMW12UncertaintyViolations
# ---------------------------------------------------------------------------


class TestMW12UncertaintyViolations:

    def test_negative_uncertainty(self):
        link = _link(uncertainty_window_ms=-1)
        with pytest.raises(InvariantViolation, match="uncertainty_window_ms"):
            assert_mw12_temporal_links([link])
