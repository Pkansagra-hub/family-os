"""Tests for TemporalLink and TemporalLinkType (Epic 2.1).

Validates the multi-link temporal model: TemporalLinkType enum (6 values),
TemporalLink frozen dataclass (5 fields), and MemoryAtom.temporal_links
tuple field for 0-5 temporal references per atom.
"""

import pytest

from k1.memory_writer.types import MemoryAtom, Temporal, TemporalLink, TemporalLinkType

# ===================================================================
# Issue 2.1.1 -- TemporalLinkType enum
# ===================================================================


class TestTemporalLinkTypeEnum:
    """Verify TemporalLinkType enum has exactly 6 str-based members."""

    def test_all_six_values_exist(self):
        expected = {
            "RETROSPECTIVE",
            "PROSPECTIVE",
            "CONCURRENT",
            "HABITUAL",
            "CONTEXTUAL",
            "CONDITIONAL",
        }
        actual = {m.value for m in TemporalLinkType}
        assert actual == expected

    def test_member_count(self):
        assert len(TemporalLinkType) == 6

    def test_str_enum_serialization(self):
        for member in TemporalLinkType:
            assert isinstance(member, str)
            assert member.value == member.name

    def test_retrospective_value(self):
        assert TemporalLinkType.RETROSPECTIVE.value == "RETROSPECTIVE"

    def test_prospective_value(self):
        assert TemporalLinkType.PROSPECTIVE.value == "PROSPECTIVE"

    def test_concurrent_value(self):
        assert TemporalLinkType.CONCURRENT.value == "CONCURRENT"

    def test_habitual_value(self):
        assert TemporalLinkType.HABITUAL.value == "HABITUAL"

    def test_contextual_value(self):
        assert TemporalLinkType.CONTEXTUAL.value == "CONTEXTUAL"

    def test_conditional_value(self):
        assert TemporalLinkType.CONDITIONAL.value == "CONDITIONAL"


# ===================================================================
# Issue 2.1.2 -- TemporalLink frozen dataclass
# ===================================================================


class TestTemporalLinkConstruction:
    """Verify TemporalLink construction, defaults, and immutability."""

    def test_minimal_construction(self):
        link = TemporalLink(mentioned_time="yesterday")
        assert link.mentioned_time == "yesterday"
        assert link.resolved_epoch_ms == 0
        assert link.uncertainty_window_ms == 0
        assert link.link_type == "CONCURRENT"
        assert link.confidence == 1.0

    def test_full_construction(self):
        link = TemporalLink(
            mentioned_time="next Friday evening",
            resolved_epoch_ms=1700000000000,
            uncertainty_window_ms=14_400_000,
            link_type=TemporalLinkType.PROSPECTIVE.value,
            confidence=0.85,
        )
        assert link.mentioned_time == "next Friday evening"
        assert link.resolved_epoch_ms == 1700000000000
        assert link.uncertainty_window_ms == 14_400_000
        assert link.link_type == "PROSPECTIVE"
        assert link.confidence == 0.85

    def test_link_type_accepts_enum_value(self):
        link = TemporalLink(
            mentioned_time="every Sunday",
            link_type=TemporalLinkType.HABITUAL.value,
        )
        assert link.link_type == "HABITUAL"

    def test_link_type_accepts_raw_string(self):
        link = TemporalLink(
            mentioned_time="in college",
            link_type="CONTEXTUAL",
        )
        assert link.link_type == "CONTEXTUAL"


class TestTemporalLinkFrozen:
    """Verify TemporalLink is immutable (frozen=True)."""

    def test_cannot_set_mentioned_time(self):
        link = TemporalLink(mentioned_time="yesterday")
        with pytest.raises(AttributeError):
            link.mentioned_time = "today"

    def test_cannot_set_resolved_epoch_ms(self):
        link = TemporalLink(mentioned_time="yesterday")
        with pytest.raises(AttributeError):
            link.resolved_epoch_ms = 999

    def test_cannot_set_link_type(self):
        link = TemporalLink(mentioned_time="yesterday")
        with pytest.raises(AttributeError):
            link.link_type = "RETROSPECTIVE"

    def test_cannot_set_confidence(self):
        link = TemporalLink(mentioned_time="yesterday")
        with pytest.raises(AttributeError):
            link.confidence = 0.5


# ===================================================================
# Issue 2.1.3 -- MemoryAtom.temporal_links
# ===================================================================


class TestMemoryAtomTemporalLinks:
    """Verify temporal_links field on MemoryAtom."""

    def test_default_empty_tuple(self):
        atom = MemoryAtom()
        assert atom.temporal_links == ()
        assert isinstance(atom.temporal_links, tuple)

    def test_single_link(self):
        link = TemporalLink(mentioned_time="yesterday evening")
        atom = MemoryAtom(temporal_links=(link,))
        assert len(atom.temporal_links) == 1
        assert atom.temporal_links[0].mentioned_time == "yesterday evening"

    def test_multiple_links(self):
        """3 temporal references: yesterday (RETRO), next Friday (PROSPECTIVE), Christmas (PROSPECTIVE)."""
        links = (
            TemporalLink(
                mentioned_time="yesterday",
                resolved_epoch_ms=1700000000000,
                link_type=TemporalLinkType.RETROSPECTIVE.value,
                confidence=0.95,
            ),
            TemporalLink(
                mentioned_time="next Friday",
                resolved_epoch_ms=1700500000000,
                link_type=TemporalLinkType.PROSPECTIVE.value,
                confidence=0.80,
            ),
            TemporalLink(
                mentioned_time="Christmas",
                resolved_epoch_ms=1703462400000,
                link_type=TemporalLinkType.PROSPECTIVE.value,
                confidence=0.90,
            ),
        )
        atom = MemoryAtom(temporal_links=links)
        assert len(atom.temporal_links) == 3
        assert atom.temporal_links[0].link_type == "RETROSPECTIVE"
        assert atom.temporal_links[1].link_type == "PROSPECTIVE"
        assert atom.temporal_links[2].mentioned_time == "Christmas"

    def test_max_five_links(self):
        links = tuple(TemporalLink(mentioned_time=f"time_{i}") for i in range(5))
        atom = MemoryAtom(temporal_links=links)
        assert len(atom.temporal_links) == 5

    def test_temporal_links_frozen(self):
        atom = MemoryAtom(temporal_links=(TemporalLink(mentioned_time="x"),))
        with pytest.raises(AttributeError):
            atom.temporal_links = ()

    def test_extraction_sequence_default_zero(self):
        atom = MemoryAtom()
        assert atom.extraction_sequence == 0

    def test_extraction_sequence_set(self):
        atom = MemoryAtom(extraction_sequence=3)
        assert atom.extraction_sequence == 3

    def test_extraction_sequence_frozen(self):
        atom = MemoryAtom(extraction_sequence=1)
        with pytest.raises(AttributeError):
            atom.extraction_sequence = 2


class TestMemoryAtomBackwardCompat:
    """Verify temporal (old) and temporal_links (new) coexist."""

    def test_both_fields_populated(self):
        old_temporal = Temporal(
            mentioned_time="yesterday",
            resolved_epoch_ms=1700000000000,
            is_backdated=True,
        )
        new_links = (
            TemporalLink(
                mentioned_time="yesterday",
                resolved_epoch_ms=1700000000000,
                link_type=TemporalLinkType.RETROSPECTIVE.value,
            ),
        )
        atom = MemoryAtom(temporal=old_temporal, temporal_links=new_links)
        assert atom.temporal is not None
        assert atom.temporal.mentioned_time == "yesterday"
        assert len(atom.temporal_links) == 1
        assert atom.temporal_links[0].link_type == "RETROSPECTIVE"

    def test_old_temporal_only(self):
        old_temporal = Temporal(
            mentioned_time="last week",
            resolved_epoch_ms=1699900000000,
            is_backdated=True,
        )
        atom = MemoryAtom(temporal=old_temporal)
        assert atom.temporal is not None
        assert atom.temporal_links == ()

    def test_new_links_only(self):
        links = (TemporalLink(mentioned_time="tomorrow"),)
        atom = MemoryAtom(temporal_links=links)
        assert atom.temporal is None
        assert len(atom.temporal_links) == 1

    def test_neither_populated(self):
        atom = MemoryAtom()
        assert atom.temporal is None
        assert atom.temporal_links == ()


class TestMemoryAtomFieldCount:
    """Verify MemoryAtom field count after temporal_links + place_id additions."""

    def test_field_count(self):
        from dataclasses import fields

        assert len(fields(MemoryAtom)) == 42


# ===================================================================
# Epic 4.2 (GAP-002) -- location_hierarchy on MemoryAtom
# ===================================================================


class TestMemoryAtomLocationHierarchy:
    """Verify location_hierarchy tuple field on MemoryAtom."""

    def test_default_empty_tuple(self):
        atom = MemoryAtom()
        assert atom.location_hierarchy == ()

    def test_set_hierarchy(self):
        atom = MemoryAtom(location_hierarchy=("kitchen", "home", "Seattle"))
        assert atom.location_hierarchy == ("kitchen", "home", "Seattle")

    def test_single_level(self):
        atom = MemoryAtom(location_hierarchy=("office",))
        assert atom.location_hierarchy == ("office",)
        assert len(atom.location_hierarchy) == 1

    def test_frozen(self):
        atom = MemoryAtom(location_hierarchy=("park",))
        with pytest.raises(AttributeError):
            atom.location_hierarchy = ("other",)


# ===================================================================
# Epic 4.3 (GAP-002) -- transition fields on MemoryAtom
# ===================================================================


class TestMemoryAtomSpatialTransition:
    """Verify transition_from_place and transition_mode on MemoryAtom."""

    def test_defaults_none(self):
        atom = MemoryAtom()
        assert atom.transition_from_place is None
        assert atom.transition_mode is None

    def test_set_transition(self):
        atom = MemoryAtom(
            transition_from_place="restaurant",
            transition_mode="drove",
        )
        assert atom.transition_from_place == "restaurant"
        assert atom.transition_mode == "drove"

    def test_transition_from_place_only(self):
        atom = MemoryAtom(transition_from_place="park")
        assert atom.transition_from_place == "park"
        assert atom.transition_mode is None

    def test_frozen_transition(self):
        atom = MemoryAtom(transition_from_place="home")
        with pytest.raises(AttributeError):
            atom.transition_from_place = "office"
