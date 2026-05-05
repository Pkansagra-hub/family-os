"""M4.E1.I2 — DynamicPromptBuilder injection regression + capsule-on tests.

The contract for this milestone:

* ``grounding_capsule=None`` (default) leaves the system_prompt
  byte-identical to the pre-M4 baseline. (regression)
* ``grounding_capsule=<GroundingCapsule>`` appends its
  ``as_prompt_text()`` to the system_prompt, regardless of mode.
* A capsule whose ``as_prompt_text()`` raises is silently dropped
  (fail-soft) so the LLM call never crashes.
"""

from __future__ import annotations

# AffectBand is a small dataclass elsewhere in the prompt package.
from k1.concierge.prompt.affect import AffectBand
from k1.concierge.prompt.builder import DynamicPromptBuilder
from k1.concierge.prompt.mode import PromptMode
from k1.selfmodel.contracts.capsule import GroundingCapsule


def _affect_neutral() -> AffectBand:
    return AffectBand(band="neutral")


def _build(mode: PromptMode = PromptMode.STANDARD, **kwargs):
    return DynamicPromptBuilder().build(
        mode=mode,
        affect_band=_affect_neutral(),
        history_messages=[],
        all_tool_schemas=[],
        scenario_data={},
        **kwargs,
    )


# ---------------------------------------------------------------------
# Baseline regression
# ---------------------------------------------------------------------
def test_baseline_unchanged_when_capsule_omitted() -> None:
    a = _build()
    b = _build(grounding_capsule=None)
    assert a.system_prompt == b.system_prompt


# ---------------------------------------------------------------------
# Capsule-on injection
# ---------------------------------------------------------------------
def test_capsule_text_appended_when_provided() -> None:
    cap = GroundingCapsule(
        actor_block="[actor]\nid=a1",
        family_block="[family]\n(no related members in this frame)",
        rules_block="[rules]\nconstitution_version=v0",
        capabilities_block="[capabilities]\ncan_do=recall_memory",
        freshness_footer="[freshness]\nworst_of_three=fresh",
        rendered_at_ms=0,
    )
    baseline = _build(grounding_capsule=None)
    augmented = _build(grounding_capsule=cap)
    assert "[actor]" in augmented.system_prompt
    assert "[freshness]" in augmented.system_prompt
    # The capsule text must appear AFTER the baseline content.
    assert augmented.system_prompt.endswith("worst_of_three=fresh")
    # Augmented prompt strictly contains baseline as a prefix.
    assert augmented.system_prompt.startswith(baseline.system_prompt)


def test_capsule_appended_for_every_mode() -> None:
    cap = GroundingCapsule(actor_block="[actor]\nid=a1", rendered_at_ms=0)
    for mode in PromptMode:
        out = _build(mode=mode, grounding_capsule=cap)
        assert "[actor]" in out.system_prompt, f"missing in mode={mode}"


# ---------------------------------------------------------------------
# Fail-soft
# ---------------------------------------------------------------------
def test_capsule_with_raising_render_does_not_crash() -> None:
    class _BadCap:
        def as_prompt_text(self) -> str:
            raise RuntimeError("kaboom")

    out = _build(grounding_capsule=_BadCap())
    # Still returns a system_prompt (no exception escapes).
    assert isinstance(out.system_prompt, str)


def test_empty_capsule_text_is_skipped() -> None:
    cap = GroundingCapsule()  # all blocks empty
    baseline = _build(grounding_capsule=None)
    out = _build(grounding_capsule=cap)
    assert out.system_prompt == baseline.system_prompt
