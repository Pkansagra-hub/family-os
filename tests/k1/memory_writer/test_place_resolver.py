"""
Epic 3.1 (GAP-002) -- PlaceResolver unit tests.

Tests PlaceResolver class, ResolvedPlace dataclass, _to_place_id slug generation,
MemoryAtom.place_id field, and MW-13 invariant.
"""

from dataclasses import dataclass

import pytest

from k1.memory_writer.context_assembly import assemble_temporal_spatial, resolve_place_id
from k1.memory_writer.events import TurnCompletePayload
from k1.memory_writer.invariants import InvariantViolation, assert_mw13_place_id
from k1.memory_writer.place_resolver import PlaceResolver, ResolvedPlace, _to_place_id
from k1.memory_writer.types import MemoryAtom

# ---------------------------------------------------------------------------
# Helper: EntityRef-like object for PlaceResolver construction
# ---------------------------------------------------------------------------


@dataclass
class FakeEntity:
    id: str
    type: str
    display_name: str = ""
    confidence: float = 1.0


# ===========================================================================
# PlaceResolver -- slug generation
# ===========================================================================


class TestToPlaceId:
    """_to_place_id slug generation."""

    def test_simple_name(self):
        assert _to_place_id("Olive Garden") == "place_olive_garden"

    def test_possessive(self):
        assert _to_place_id("Mom's House") == "place_mom_s_house"

    def test_numbers(self):
        assert _to_place_id("7-Eleven") == "place_7_eleven"

    def test_multiple_spaces(self):
        assert _to_place_id("Central  Park  Zoo") == "place_central_park_zoo"

    def test_trailing_punctuation(self):
        assert _to_place_id("Starbucks!") == "place_starbucks"

    def test_mixed_case(self):
        assert _to_place_id("McDonald's") == "place_mcdonald_s"

    def test_unicode_stripped(self):
        # Non-ASCII chars become underscores, then trimmed
        result = _to_place_id("Cafe")
        assert result == "place_cafe"


# ===========================================================================
# PlaceResolver -- construction and resolution
# ===========================================================================


class TestPlaceResolver:
    """PlaceResolver construction and resolve()."""

    def test_resolve_exact_match(self):
        entities = [FakeEntity(id="e1", type="LOCATION", display_name="Olive Garden")]
        resolver = PlaceResolver(entities)
        assert resolver.resolve("Olive Garden") == "place_olive_garden"

    def test_resolve_case_insensitive(self):
        entities = [FakeEntity(id="e1", type="LOCATION", display_name="Olive Garden")]
        resolver = PlaceResolver(entities)
        assert resolver.resolve("olive garden") == "place_olive_garden"

    def test_resolve_prefix_match_query_shorter(self):
        """'Olive Garden' entity matches 'Olive Garden on Main St' query."""
        entities = [FakeEntity(id="e1", type="LOCATION", display_name="Olive Garden")]
        resolver = PlaceResolver(entities)
        assert resolver.resolve("Olive Garden on Main St") == "place_olive_garden"

    def test_resolve_prefix_match_entity_shorter(self):
        """'Olive Garden on Main St' query starts with entity 'Olive Garden'."""
        entities = [
            FakeEntity(id="e1", type="LOCATION", display_name="Olive Garden"),
        ]
        resolver = PlaceResolver(entities)
        assert resolver.resolve("Olive Garden on Main St") == "place_olive_garden"

    def test_resolve_no_match(self):
        entities = [FakeEntity(id="e1", type="LOCATION", display_name="Olive Garden")]
        resolver = PlaceResolver(entities)
        assert resolver.resolve("Central Park") is None

    def test_resolve_empty_entities(self):
        resolver = PlaceResolver([])
        assert resolver.resolve("Olive Garden") is None

    def test_resolve_none_name(self):
        entities = [FakeEntity(id="e1", type="LOCATION", display_name="Olive Garden")]
        resolver = PlaceResolver(entities)
        assert resolver.resolve(None) is None

    def test_resolve_empty_name(self):
        entities = [FakeEntity(id="e1", type="LOCATION", display_name="Olive Garden")]
        resolver = PlaceResolver(entities)
        assert resolver.resolve("") is None

    def test_resolve_whitespace_name(self):
        entities = [FakeEntity(id="e1", type="LOCATION", display_name="Olive Garden")]
        resolver = PlaceResolver(entities)
        assert resolver.resolve("   ") is None

    def test_filters_non_location_entities(self):
        entities = [
            FakeEntity(id="e1", type="PERSON", display_name="Mom"),
            FakeEntity(id="e2", type="LOCATION", display_name="Olive Garden"),
        ]
        resolver = PlaceResolver(entities)
        assert resolver.resolve("Mom") is None
        assert resolver.resolve("Olive Garden") == "place_olive_garden"

    def test_multiple_locations(self):
        entities = [
            FakeEntity(id="e1", type="LOCATION", display_name="Olive Garden"),
            FakeEntity(id="e2", type="LOCATION", display_name="Central Park"),
        ]
        resolver = PlaceResolver(entities)
        assert resolver.resolve("Olive Garden") == "place_olive_garden"
        assert resolver.resolve("Central Park") == "place_central_park"

    def test_entity_with_empty_display_name_skipped(self):
        entities = [
            FakeEntity(id="e1", type="LOCATION", display_name=""),
            FakeEntity(id="e2", type="LOCATION", display_name="Olive Garden"),
        ]
        resolver = PlaceResolver(entities)
        assert resolver.resolve("Olive Garden") == "place_olive_garden"

    def test_confidence_preserved(self):
        entities = [FakeEntity(id="e1", type="LOCATION", display_name="Home", confidence=0.95)]
        resolver = PlaceResolver(entities)
        # resolve returns just place_id, but internal ResolvedPlace has confidence
        assert resolver.resolve("Home") == "place_home"


# ===========================================================================
# ResolvedPlace dataclass
# ===========================================================================


class TestResolvedPlace:
    """ResolvedPlace is frozen with correct fields."""

    def test_construction(self):
        rp = ResolvedPlace(place_id="place_home", canonical_name="Home", confidence=0.95)
        assert rp.place_id == "place_home"
        assert rp.canonical_name == "Home"
        assert rp.confidence == 0.95

    def test_frozen(self):
        rp = ResolvedPlace(place_id="place_home", canonical_name="Home", confidence=0.95)
        with pytest.raises(AttributeError):
            rp.place_id = "changed"


# ===========================================================================
# MemoryAtom -- place_id field
# ===========================================================================


class TestMemoryAtomPlaceId:
    """MemoryAtom.place_id field added in Epic 3.1."""

    def test_default_none(self):
        atom = MemoryAtom()
        assert atom.place_id is None

    def test_set_place_id(self):
        atom = MemoryAtom(place_id="place_olive_garden")
        assert atom.place_id == "place_olive_garden"

    def test_field_exists(self):
        assert hasattr(MemoryAtom, "place_id")

    def test_frozen(self):
        atom = MemoryAtom(place_id="place_home")
        with pytest.raises(AttributeError):
            atom.place_id = "changed"


# ===========================================================================
# MW-13 invariant -- place_id validation
# ===========================================================================


class TestMW13PlaceIdInvariant:
    """MW-13: place_id must be None or match ^place_[a-z0-9_]+$."""

    def test_none_valid(self):
        assert_mw13_place_id(None)

    def test_valid_simple(self):
        assert_mw13_place_id("place_olive_garden")

    def test_valid_with_numbers(self):
        assert_mw13_place_id("place_7_eleven")

    def test_valid_single_word(self):
        assert_mw13_place_id("place_home")

    def test_empty_string_invalid(self):
        with pytest.raises(InvariantViolation, match="MW-13"):
            assert_mw13_place_id("")

    def test_no_prefix_invalid(self):
        with pytest.raises(InvariantViolation, match="MW-13"):
            assert_mw13_place_id("olive_garden")

    def test_uppercase_invalid(self):
        with pytest.raises(InvariantViolation, match="MW-13"):
            assert_mw13_place_id("place_Olive_Garden")

    def test_spaces_invalid(self):
        with pytest.raises(InvariantViolation, match="MW-13"):
            assert_mw13_place_id("place_olive garden")

    def test_special_chars_invalid(self):
        with pytest.raises(InvariantViolation, match="MW-13"):
            assert_mw13_place_id("place_olive-garden")

    def test_integer_invalid(self):
        with pytest.raises((InvariantViolation, TypeError, AttributeError)):
            assert_mw13_place_id(42)  # type: ignore[arg-type]


# ===========================================================================
# context_assembly: resolve_place_id integration
# ===========================================================================


def _payload(**overrides) -> TurnCompletePayload:
    defaults = {
        "turn_id": "turn-001",
        "session_id": "sess-001",
        "cognitive_trace_id": "ct-001",
        "user_message": "We went to Olive Garden",
        "assistant_response": "Nice!",
        "timestamp_ms": 1704067200000,
        "turn_number": 1,
    }
    defaults.update(overrides)
    return TurnCompletePayload(**defaults)


def _beliefs_with_entities() -> dict:
    return {
        "mentioned_entities": [
            {"type": "LOCATION", "display_name": "Olive Garden", "confidence": 0.9},
            {"type": "PERSON", "display_name": "Mom", "confidence": 0.95},
        ],
    }


class TestResolvePlaceId:
    """resolve_place_id from context_assembly."""

    def test_resolves_with_matching_entity(self):
        result = resolve_place_id("Olive Garden", _beliefs_with_entities())
        assert result == "place_olive_garden"

    def test_returns_none_no_entities(self):
        result = resolve_place_id("Olive Garden", {})
        assert result is None

    def test_returns_none_empty_location(self):
        result = resolve_place_id("", _beliefs_with_entities())
        assert result is None

    def test_returns_none_none_location(self):
        result = resolve_place_id(None, _beliefs_with_entities())  # type: ignore[arg-type]
        assert result is None

    def test_returns_none_no_snapshot(self):
        result = resolve_place_id("Olive Garden", None)
        assert result is None

    def test_case_insensitive(self):
        result = resolve_place_id("olive garden", _beliefs_with_entities())
        assert result == "place_olive_garden"

    def test_filters_non_location(self):
        result = resolve_place_id("Mom", _beliefs_with_entities())
        assert result is None

    def test_entity_as_object(self):
        """Entities can be objects (not just dicts)."""
        entities_as_objects = {
            "mentioned_entities": [
                FakeEntity(id="e1", type="LOCATION", display_name="Central Park"),
            ],
        }
        result = resolve_place_id("Central Park", entities_as_objects)
        assert result == "place_central_park"


class TestAssembleTemporalSpatialPlaceId:
    """assemble_temporal_spatial includes place_id (Epic 3.1)."""

    def test_place_id_present_in_result(self):
        p = _payload(mentioned_location_raw="Olive Garden")
        beliefs = {
            **_beliefs_with_entities(),
            "mentioned_location": {
                "raw_text": "Olive Garden",
                "location_type": "restaurant",
                "entity_id": "ent-og",
                "confidence": 0.9,
            },
        }
        result = assemble_temporal_spatial(p, beliefs_snapshot=beliefs)
        assert "place_id" in result
        assert result["place_id"] == "place_olive_garden"

    def test_place_id_none_when_no_location(self):
        p = _payload()
        result = assemble_temporal_spatial(p)
        assert result["place_id"] is None

    def test_place_id_none_when_no_matching_entity(self):
        p = _payload(mentioned_location_raw="Unknown Place")
        beliefs = _beliefs_with_entities()
        result = assemble_temporal_spatial(p, beliefs_snapshot=beliefs)
        assert result["place_id"] is None
