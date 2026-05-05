"""M0.E1.I2 — grounding capsule dataclass is frozen and renders as text."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from k1.selfmodel.contracts.capsule import GroundingCapsule


def test_grounding_capsule_min_construct() -> None:
    c = GroundingCapsule()
    assert c.actor_block == ""
    assert c.family_block == ""
    assert c.rules_block == ""
    assert c.capabilities_block == ""
    assert c.freshness_footer == ""


def test_grounding_capsule_is_frozen() -> None:
    c = GroundingCapsule()
    with pytest.raises(FrozenInstanceError):
        c.actor_block = "tampered"  # type: ignore[misc]


def test_as_prompt_text_skips_empty_blocks() -> None:
    c = GroundingCapsule(actor_block="ACTOR", capabilities_block="CAPS")
    text = c.as_prompt_text()
    assert text == "ACTOR\nCAPS"


def test_as_prompt_text_preserves_order() -> None:
    c = GroundingCapsule(
        actor_block="A",
        family_block="F",
        rules_block="R",
        capabilities_block="C",
        freshness_footer="X",
    )
    assert c.as_prompt_text() == "A\nF\nR\nC\nX"


def test_as_prompt_text_empty_when_all_blocks_empty() -> None:
    assert GroundingCapsule().as_prompt_text() == ""
