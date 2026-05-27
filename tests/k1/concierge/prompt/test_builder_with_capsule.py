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

from k1.concierge.config import load_config, reset_config

# AffectBand is a small dataclass elsewhere in the prompt package.
from k1.concierge.prompt.affect import AffectBand
from k1.concierge.prompt.builder import DynamicPromptBuilder
from k1.concierge.prompt.mode import PromptMode
from k1.selfmodel.contracts.capsule import GroundingCapsule
from k1.sessionstate.sections.trust_level import TrustLevelSection


def _affect_neutral() -> AffectBand:
    return AffectBand(band="neutral")


def _build(
    mode: PromptMode = PromptMode.STANDARD,
    scenario_data: dict[str, object] | None = None,
    **kwargs,
):
    return DynamicPromptBuilder().build(
        mode=mode,
        affect_band=_affect_neutral(),
        history_messages=[],
        all_tool_schemas=[],
        scenario_data=scenario_data or {},
        **kwargs,
    )


class _SessionState:
    def __init__(self, sections: dict[str, object]) -> None:
        self._sections = sections

    def get_section(self, name: str) -> object | None:
        return self._sections.get(name)


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
    assert "-- INJECT: REFERENCE PROFILE --" in augmented.system_prompt
    assert augmented.system_prompt != baseline.system_prompt
    assert augmented.system_prompt.index(
        "-- INJECT: REFERENCE PROFILE --"
    ) < augmented.system_prompt.index("== CURRENT EVENT ==")


def test_trust_level_renders_as_situation_frame_seat() -> None:
    trust = TrustLevelSection(session_id="s1")
    trust.update(
        trust_score=0.38,
        confidence=0.9,
        signal="correction_after_misread",
        stance="repairing",
        reason="User corrected K1 and asked it not to assume.",
    )

    out = _build(ss=_SessionState({"trust_level": trust}))

    assert "-- INJECT: TRUST CALIBRATION --" in out.system_prompt
    assert "## trust_level" in out.system_prompt
    assert "Trust score: 0.38" in out.system_prompt
    assert "Latest signal: correction_after_misread" in out.system_prompt


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


def test_standard_prompt_examples_do_not_override_greeting_rules() -> None:
    out = _build(grounding_capsule=None)
    assert "Reply like a family member would" in out.system_prompt
    assert "One short line, two at most. No tools." in out.system_prompt
    assert "Mixed banter + request turn:" in out.system_prompt
    assert (
        "1. recall_memory() + update_scoreboard() + update_beliefs()  [all at once]"
        not in out.system_prompt
    )


def test_standard_prompt_forces_text_only_salutations() -> None:
    out = _build(grounding_capsule=None)
    assert "good morning" in out.system_prompt
    assert "good evening" in out.system_prompt
    assert "Reply like a family member would" in out.system_prompt
    assert "One short line, two at most. No tools." in out.system_prompt
    assert "Do not spend a tool iteration maintaining hidden state." in out.system_prompt
    assert "1. update_beliefs() or text response directly" not in out.system_prompt


def test_standard_prompt_drops_duplicate_active_member_when_capsule_present() -> None:
    cap = GroundingCapsule(
        self_block="[self]\nname=Alex\nrole=parent",
        space_graph_block="[space]\n- Alex\n- Jordan",
        rendered_at_ms=0,
    )
    out = _build(
        grounding_capsule=cap,
        scenario_data={"active_member": "unknown", "async_results_context": ""},
    )
    assert out.system_prompt.count("-- INJECT: ACTIVE ACTOR --") == 1
    assert out.system_prompt.count("-- INJECT: VISIBLE SPACE --") == 1
    assert "You are talking to: unknown" not in out.system_prompt
    assert "name=Alex" in out.system_prompt


def test_builder_reads_iteration_budget_from_config(tmp_path) -> None:
    override = tmp_path / "config.yaml"
    override.write_text(
        "prompt:\n"
        "  max_iterations:\n"
        "    STANDARD: 2\n"
        "  crisis_iterations:\n"
        "    STANDARD: 1\n",
        encoding="utf-8",
    )
    load_config(override)
    try:
        standard = _build(mode=PromptMode.STANDARD)
        crisis = DynamicPromptBuilder().build(
            mode=PromptMode.STANDARD,
            affect_band=AffectBand(band="crisis"),
            history_messages=[],
            all_tool_schemas=[],
            scenario_data={},
        )
        assert standard.max_iterations == 2
        assert crisis.max_iterations == 1
    finally:
        reset_config()
