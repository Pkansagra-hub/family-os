"""M3-E7 beliefs_active mentioned_location semantics."""

from __future__ import annotations

from k1.sessionstate.sections.beliefs_active import BeliefsActiveSection


def test_mentioned_location_remains_conversation_evidence_only() -> None:
    section = BeliefsActiveSection(session_id="s1")
    section.set_mentioned_location("Central Park", location_type="park", entity_id="loc1")

    mentioned = section.get_mentioned_location()

    assert mentioned is not None
    assert mentioned.raw_text == "Central Park"
    assert not hasattr(mentioned, "current_place")
