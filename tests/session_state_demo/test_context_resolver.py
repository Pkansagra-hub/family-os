"""
Test Context Resolver
======================

Tests temporal and entity reference resolution to prevent re-asking.
"""

from poc.session_state_demo.concierge.context_resolver import create_context_resolver


class TestTemporalResolution:
    """Test temporal reference resolution."""

    def test_next_saturday_resolved_once(self):
        """'next Saturday' should be resolved once and locked."""
        resolver = create_context_resolver()

        # First resolution
        result1 = resolver.resolve(
            user_input="I want to go next Saturday",
            turn_number=1,
        )

        # Should have resolved the date
        assert "next_saturday" in result1.resolved_refs
        ref = result1.resolved_refs["next_saturday"]
        assert ref.locked is True
        assert ref.ref_type == "temporal"
        first_date = ref.resolved

        # Second resolution - should NOT change the date
        result2 = resolver.resolve(
            user_input="What about next Saturday?",
            turn_number=5,
        )

        # Same date should be used
        assert "next_saturday" in result2.resolved_refs
        assert result2.resolved_refs["next_saturday"].resolved == first_date

    def test_weekend_resolved(self):
        """'this weekend' and 'next weekend' should resolve."""
        resolver = create_context_resolver()

        result = resolver.resolve(
            user_input="Planning for this weekend",
            turn_number=1,
        )

        assert "this_weekend" in result.resolved_refs
        ref = result.resolved_refs["this_weekend"]
        assert ref.ref_type == "temporal"
        assert ref.locked is True

    def test_should_ask_for_unresolved(self):
        """Should ask for fields that haven't been resolved."""
        resolver = create_context_resolver()

        # Nothing resolved yet
        assert resolver.should_ask_for("date") is True
        assert resolver.should_ask_for("location") is True

        # Resolve a date
        resolver.resolve("next Saturday", turn_number=1)

        # Now date-related should NOT be asked
        assert resolver.is_resolved("next_saturday") is True

    def test_beliefs_prevent_asking(self):
        """Should not ask for fields already in beliefs."""
        resolver = create_context_resolver()

        beliefs = {
            "trip": {
                "destination": "Sonoma",
                "date": "2026-02-07",
            }
        }

        # Should NOT ask for date or destination
        assert resolver.should_ask_for("date", beliefs) is False
        assert resolver.should_ask_for("destination", beliefs) is False

        # Should still ask for unrelated fields
        assert resolver.should_ask_for("restaurant") is True


class TestEntityResolution:
    """Test entity reference resolution."""

    def test_pronoun_resolved_from_referents(self):
        """'it' should resolve from active referents."""
        resolver = create_context_resolver()

        scoreboard = {
            "referents": ["Vineyard Inn", "Sonoma", "Mike"],
            "topic": "accommodation_booking",
        }

        result = resolver.resolve(
            user_input="Book it for two nights",
            turn_number=5,
            scoreboard=scoreboard,
        )

        # "it" should resolve to Vineyard Inn (hotel referent)
        assert "it" in result.inferred_entities
        assert (
            "Vineyard" in result.inferred_entities["it"] or "Inn" in result.inferred_entities["it"]
        )

    def test_the_hotel_resolved(self):
        """'the hotel' should resolve from referents."""
        resolver = create_context_resolver()

        scoreboard = {
            "referents": ["Vineyard Inn", "dinner reservation"],
            "topic": "booking",
        }

        result = resolver.resolve(
            user_input="What's included at the hotel?",
            turn_number=3,
            scoreboard=scoreboard,
        )

        # "the_hotel" should resolve
        assert "the_hotel" in result.inferred_entities or "the_inn" in result.inferred_entities


class TestContextResolutionIntegration:
    """Integration tests for context resolution."""

    def test_full_conversation_flow(self):
        """Test resolution across multiple turns."""
        resolver = create_context_resolver()

        # Turn 1: Establish date
        result1 = resolver.resolve(
            user_input="I want to plan a trip for next Saturday",
            turn_number=1,
        )
        assert "next_saturday" in result1.resolved_refs

        # Turn 3: Mention a hotel
        scoreboard = {"referents": ["Vineyard Inn"], "topic": "accommodation"}
        resolver.resolve(
            user_input="The Vineyard Inn looks great",
            turn_number=3,
            scoreboard=scoreboard,
        )

        # Turn 5: Reference both with pronouns
        resolver.resolve(
            user_input="Book it for the weekend",
            turn_number=5,
            scoreboard={"referents": ["Vineyard Inn", "next Saturday"]},
        )

        # Both should be resolvable, no need to ask
        assert resolver.is_resolved("next_saturday")

    def test_date_from_beliefs_is_resolved(self):
        """Dates stored in beliefs should count as resolved."""
        resolver = create_context_resolver()

        beliefs = {
            "trip": {"date": "2026-02-07"},
        }

        result = resolver.resolve(
            user_input="Book the hotel",
            turn_number=5,
            beliefs=beliefs,
        )

        # Should recognize date from beliefs
        assert "date" in result.resolved_refs or not resolver.should_ask_for("date", beliefs)


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
