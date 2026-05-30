"""M3-E7 place candidate source tests."""

from __future__ import annotations

from k1.sessionstate.sections.beliefs_active import BeliefsActiveSection
from k1.spatial.service.place_candidate_source import (
    candidates_from_beliefs_active,
    candidates_from_session_state,
)


class _SS:
    def __init__(self, section: BeliefsActiveSection) -> None:
        self._section = section

    def get_section(self, name: str):  # type: ignore[no-untyped-def]
        return self._section if name == "beliefs_active" else None


def test_candidates_from_beliefs_active_marks_mentioned_location_as_evidence_only() -> None:
    section = BeliefsActiveSection(session_id="s1")
    section.set_mentioned_location("Mom's House", location_type="home", confidence=0.9)

    candidate = candidates_from_beliefs_active(section)[0]

    assert candidate.source == "conversation_mention"
    assert candidate.normalized_text == "mom's house"
    assert candidate.confidence == 0.45
    assert candidate.metadata["authoritative_current_place"] is False


def test_candidates_from_session_state_reads_beliefs_active_section() -> None:
    section = BeliefsActiveSection(session_id="s1")
    section.set_mentioned_location("kitchen", location_type="room", confidence=0.3)

    assert candidates_from_session_state(_SS(section))[0].normalized_text == "kitchen"
