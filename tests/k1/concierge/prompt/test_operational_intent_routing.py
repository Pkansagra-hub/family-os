"""Tests for domain-agnostic Front/Back operational intent routing."""

from __future__ import annotations

from k1.concierge.prompt.back_prompt import BACK_SYSTEM_PROMPT
from k1.concierge.prompt.mode import PromptMode
from k1.concierge.prompt.sections import MODE_SECTIONS, PROMPT_SECTIONS


def test_operational_intent_routing_section_exists() -> None:
    section = PROMPT_SECTIONS["OPERATIONAL_INTENT_ROUTING"]
    assert "OPERATIONAL INTENT ROUTING" in section
    assert "domain-agnostic" not in section.lower()  # Say it via behavior, not branding.
    assert "dispatch_task" in section
    assert "recall_memory" in section
    assert "soft hints" in section
    assert "Do NOT name capability IDs" in section
    assert '"action":' in section
    assert '{"intent":' not in section


def test_operational_routing_section_has_no_vertical_specific_triggers() -> None:
    section = PROMPT_SECTIONS["OPERATIONAL_INTENT_ROUTING"].lower()
    forbidden_terms = ["household", "shopping", "family", "errands", "school run"]
    assert not any(term in section for term in forbidden_terms)


def test_standard_mode_includes_operational_routing_after_proactive() -> None:
    sections = MODE_SECTIONS[PromptMode.STANDARD]
    assert "OPERATIONAL_INTENT_ROUTING" in sections
    assert sections.index("OPERATIONAL_INTENT_ROUTING") == (
        sections.index("PROACTIVE_INTELLIGENCE") + 1
    )


def test_interrupt_mode_includes_operational_routing() -> None:
    assert "OPERATIONAL_INTENT_ROUTING" in MODE_SECTIONS[PromptMode.INTERRUPT]


def test_react_rhythm_first_iteration_table_routes_explicit_action() -> None:
    rhythm = PROMPT_SECTIONS["REACT_RHYTHM"]
    assert "Explicit action/check/read/write" in rhythm
    assert "dispatch_task()" in rhythm
    assert "LIFE-CONTEXT" not in rhythm


def test_proactive_intelligence_points_to_operational_routing() -> None:
    proactive = PROMPT_SECTIONS["PROACTIVE_INTELLIGENCE"]
    assert "OPERATIONAL INTENT ROUTING" in proactive
    assert "life-context" not in proactive.lower()


def test_back_domain_hints_are_soft_and_not_vertical_hardcoded() -> None:
    hints = BACK_SYSTEM_PROMPT.split("DOMAIN HINTS for discover_capabilities", 1)[1]
    hints = hints.split("WEB SEARCH WORKFLOW", 1)[0].lower()
    assert "soft" in hints or "hints" in hints
    assert "authoritative match" in hints
    assert "hard-code vertical-specific" in hints
    forbidden_terms = ["household", "shopping", "family", "chores"]
    assert not any(term in hints for term in forbidden_terms)
