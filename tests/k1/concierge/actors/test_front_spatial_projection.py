"""M3-E5 Front prompt context uses grounding, not persona time/place."""

from __future__ import annotations

from k1.concierge.actors.front import _extract_family_context
from k1.sessionstate.sections.persona import PersonaSection


class _SS:
    def __init__(self, persona: PersonaSection) -> None:
        self._persona = persona

    def get_section(self, name: str):  # type: ignore[no-untyped-def]
        return self._persona if name == "persona" else None


def test_family_context_omits_legacy_location_and_timezone_lines() -> None:
    persona = PersonaSection()
    persona.set_preference(
        "family",
        {
            "family_name": "Test Family",
            "location": "Texas",
            "timezone": "America/Chicago",
            "members": [],
        },
    )

    context = _extract_family_context(_SS(persona))["family_context"]

    assert "Family: Test Family" in context
    assert "Location:" not in context
    assert "Timezone:" not in context
