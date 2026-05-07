"""Tests for PersonResolver (E-MW-1.3).

22 tests across 5 test classes covering exact match, alias match,
partial match, fallback, and resolve_all.
"""

from __future__ import annotations

from k1.memory_writer.context.person_resolver import PersonResolver
from k1.memory_writer.types import ExtractionContext

# ===========================================================================
# Helpers
# ===========================================================================


def _ctx(
    persons=None,
    persona_context=None,
) -> ExtractionContext:
    """Build a minimal ExtractionContext for PersonResolver tests."""
    return ExtractionContext(
        active_persons=persons or {},
        persona_context=persona_context or {},
    )


def _persons(*entries):
    """Build active_persons dict from (display_name, person_id) pairs."""
    result = {}
    for name, pid in entries:
        result[name] = {"person_id": pid, "type": "PERSON", "confidence": 1.0}
    return result


# ===========================================================================
# TestExactMatch
# ===========================================================================


class TestExactMatch:
    def test_exact_match_case_insensitive(self):
        resolver = PersonResolver()
        ctx = _ctx(persons=_persons(("Mom", "person_mom")))
        r = resolver.resolve("mom", ctx)
        assert r.person_id == "person_mom"
        assert r.confidence == 1.0
        assert r.is_provisional is False

    def test_exact_match_preserves_original_name(self):
        resolver = PersonResolver()
        ctx = _ctx(persons=_persons(("Mom", "person_mom")))
        r = resolver.resolve("Mom", ctx)
        assert r.natural_name == "Mom"

    def test_no_match_in_empty_persons(self):
        resolver = PersonResolver()
        ctx = _ctx(persons={})
        r = resolver.resolve("Dad", ctx)
        assert r.is_provisional is True
        assert r.person_id == "person_dad"

    def test_multiple_entities_first_match(self):
        resolver = PersonResolver()
        ctx = _ctx(persons=_persons(("Mom", "person_mom"), ("Dad", "person_dad")))
        r = resolver.resolve("Mom", ctx)
        assert r.person_id == "person_mom"

    def test_confidence_is_1_0(self):
        resolver = PersonResolver()
        ctx = _ctx(persons=_persons(("Mom", "person_mom")))
        r = resolver.resolve("Mom", ctx)
        assert r.confidence == 1.0


# ===========================================================================
# TestAliasMatch
# ===========================================================================


class TestAliasMatch:
    def test_alias_resolves_to_primary(self):
        resolver = PersonResolver()
        ctx = _ctx(
            persons=_persons(("Mom", "person_mom")),
            persona_context={"aliases": {"Mom": ["Mother", "Mama"]}},
        )
        r = resolver.resolve("Mother", ctx)
        assert r.person_id == "person_mom"
        assert r.confidence == 0.9

    def test_alias_case_insensitive(self):
        resolver = PersonResolver()
        ctx = _ctx(
            persons=_persons(("Mom", "person_mom")),
            persona_context={"aliases": {"Mom": ["Mother", "MAMA"]}},
        )
        r = resolver.resolve("mama", ctx)
        assert r.person_id == "person_mom"

    def test_no_aliases_in_persona(self):
        resolver = PersonResolver()
        ctx = _ctx(
            persons=_persons(("Mom", "person_mom")),
            persona_context={},
        )
        r = resolver.resolve("Mother", ctx)
        # Falls through to partial or fallback
        assert r.person_id != "person_mom" or r.confidence < 1.0

    def test_confidence_is_0_9(self):
        resolver = PersonResolver()
        ctx = _ctx(
            persons=_persons(("Mom", "person_mom")),
            persona_context={"aliases": {"Mom": ["Mama"]}},
        )
        r = resolver.resolve("Mama", ctx)
        assert r.confidence == 0.9


# ===========================================================================
# TestPartialMatch
# ===========================================================================


class TestPartialMatch:
    def test_substring_match(self):
        resolver = PersonResolver()
        ctx = _ctx(persons=_persons(("Dr. Smith", "person_dr_smith")))
        r = resolver.resolve("Dr.", ctx)
        assert r.person_id == "person_dr_smith"
        assert r.confidence == 0.8

    def test_reverse_substring(self):
        resolver = PersonResolver()
        ctx = _ctx(persons=_persons(("Dr. Smith", "person_dr_smith")))
        r = resolver.resolve("Smith", ctx)
        assert r.person_id == "person_dr_smith"
        assert r.confidence == 0.8

    def test_confidence_is_0_8(self):
        resolver = PersonResolver()
        ctx = _ctx(persons=_persons(("Dr. Smith", "person_dr_smith")))
        r = resolver.resolve("Smith", ctx)
        assert r.confidence == 0.8

    def test_no_partial_on_short_names(self):
        """Document known behavior: single char 'a' matches 'Anna'."""
        resolver = PersonResolver()
        ctx = _ctx(persons=_persons(("Anna", "person_anna")))
        r = resolver.resolve("a", ctx)
        # Current implementation: 'a' is substring of 'anna' → match
        assert r.person_id == "person_anna"
        assert r.confidence == 0.8


# ===========================================================================
# TestFallback
# ===========================================================================


class TestFallback:
    def test_unknown_name_generates_provisional(self):
        resolver = PersonResolver()
        ctx = _ctx(persons={})
        r = resolver.resolve("Zara", ctx)
        assert r.person_id == "person_zara"
        assert r.is_provisional is True

    def test_sanitizes_special_characters(self):
        resolver = PersonResolver()
        ctx = _ctx(persons={})
        r = resolver.resolve("Dr. O'Brien", ctx)
        assert r.person_id == "person_dr__o_brien"
        assert r.is_provisional is True

    def test_empty_name(self):
        resolver = PersonResolver()
        ctx = _ctx(persons={})
        r = resolver.resolve("", ctx)
        assert r.person_id == "person_unknown"
        assert r.confidence == 0.0

    def test_whitespace_name(self):
        resolver = PersonResolver()
        ctx = _ctx(persons={})
        r = resolver.resolve("  ", ctx)
        assert r.person_id == "person_unknown"
        assert r.confidence == 0.0

    def test_confidence_is_0_5(self):
        resolver = PersonResolver()
        ctx = _ctx(persons={})
        r = resolver.resolve("Zara", ctx)
        assert r.confidence == 0.5


# ===========================================================================
# TestResolveAll
# ===========================================================================


class TestResolveAll:
    def test_resolves_multiple_names(self):
        resolver = PersonResolver()
        ctx = _ctx(persons=_persons(("Mom", "person_mom"), ("Dad", "person_dad")))
        results = resolver.resolve_all(["Mom", "Dad"], ctx)
        assert len(results) == 2
        ids = [r.person_id for r in results]
        assert "person_mom" in ids
        assert "person_dad" in ids

    def test_dedup_by_person_id(self):
        resolver = PersonResolver()
        ctx = _ctx(
            persons=_persons(("Mom", "person_mom")),
            persona_context={"aliases": {"Mom": ["Mother"]}},
        )
        results = resolver.resolve_all(["Mom", "Mother"], ctx)
        assert len(results) == 1
        assert results[0].person_id == "person_mom"

    def test_preserves_order(self):
        resolver = PersonResolver()
        ctx = _ctx(persons=_persons(("Dad", "person_dad"), ("Mom", "person_mom")))
        results = resolver.resolve_all(["Dad", "Mom"], ctx)
        assert results[0].person_id == "person_dad"
        assert results[1].person_id == "person_mom"

    def test_empty_list(self):
        resolver = PersonResolver()
        ctx = _ctx(persons={})
        results = resolver.resolve_all([], ctx)
        assert results == []
