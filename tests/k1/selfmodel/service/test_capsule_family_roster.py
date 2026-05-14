"""Tests for capsule [family] roster + aliases rendering (A + B).

The ``[family]`` block must surface the actor's trusted L3 roster
(family_members, with aliases) in addition to the privacy-projected
``relations.projected_others`` view. Without this, casual references
like "little demon of house" are unresolvable for the LLM.

Run: python -m pytest tests/k1/selfmodel/service/test_capsule_family_roster.py -q --no-cov
"""

from __future__ import annotations

from k1.selfmodel.contracts.situation import (
    ApplicableRules,
    Capabilities,
    RelationsSubset,
    SituationFrame,
    Visibility,
)
from k1.selfmodel.service.capsule_builder import GroundingCapsuleBuilder

T0 = 1_700_000_000_000


def _frame_with_roster(roster, self_aliases=None) -> SituationFrame:
    proj: dict = {"display_name": "Alex", "role": "guardian"}
    proj["family_members"] = roster
    if self_aliases is not None:
        proj["aliases"] = self_aliases
    return SituationFrame(
        actor_id="a1",
        situation_kind="caregiver_context_briefing",
        composed_at_ms=T0,
        device_id="dev-1",
        projected_self=proj,
        relations=RelationsSubset(),
        rules=ApplicableRules(rule_ids=(), constitution_version="v0"),
        capabilities=Capabilities(),
        visibility=Visibility(),
        freshness={"self": "fresh", "family": "fresh", "constitution": "fresh"},
    )


def _builder() -> GroundingCapsuleBuilder:
    return GroundingCapsuleBuilder(size_limit_bytes=4096, clock_ms=lambda: T0)


def test_family_block_renders_roster_with_aliases() -> None:
    cap = _builder().build(
        _frame_with_roster(
            [
                {
                    "member_id": "riley",
                    "display_name": "Riley",
                    "role": "child",
                    "aliases": ["little demon of house", "the kiddo"],
                },
                {
                    "member_id": "jordan",
                    "display_name": "Jordan",
                    "role": "parent",
                },
            ]
        )
    )
    block = cap.family_block
    assert block.startswith("[family]")
    assert "Riley" in block
    assert "id=riley" in block
    assert "little demon of house" in block
    assert "the kiddo" in block
    # Member with no aliases must not get an "aliases:" suffix.
    jordan_line = next(ln for ln in block.splitlines() if "Jordan" in ln)
    assert "aliases:" not in jordan_line


def test_family_block_renders_self_aliases() -> None:
    cap = _builder().build(
        _frame_with_roster(
            roster=[],
            self_aliases=["boss", "captain"],
        )
    )
    assert "self aliases: boss, captain" in cap.family_block


def test_family_block_empty_roster_falls_back_to_placeholder() -> None:
    cap = _builder().build(_frame_with_roster(roster=[]))
    assert cap.family_block.startswith("[family]")
    assert "(no related members in this frame)" in cap.family_block


def test_family_block_handles_missing_family_members_key() -> None:
    frame = SituationFrame(
        actor_id="a1",
        situation_kind="caregiver_context_briefing",
        composed_at_ms=T0,
        device_id="dev-1",
        projected_self={"display_name": "Alex"},
        relations=RelationsSubset(),
        rules=ApplicableRules(rule_ids=(), constitution_version="v0"),
        capabilities=Capabilities(),
        visibility=Visibility(),
        freshness={"self": "fresh", "family": "fresh", "constitution": "fresh"},
    )
    cap = _builder().build(frame)
    assert "(no related members in this frame)" in cap.family_block
