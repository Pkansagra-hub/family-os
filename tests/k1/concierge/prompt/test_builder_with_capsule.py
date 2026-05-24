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


def test_standard_prompt_examples_do_not_override_greeting_rules() -> None:
    out = _build(grounding_capsule=None)
    assert (
        "Pure greeting (hi/hey/morning)         -> text only, one line, no tools."
        in out.system_prompt
    )
    assert "Explicit single action" in out.system_prompt
    assert (
        "1. recall_memory() + update_scoreboard() + update_beliefs()  [all at once]"
        not in out.system_prompt
    )


def test_standard_prompt_forces_text_only_salutations() -> None:
    out = _build(grounding_capsule=None)
    # Greeting rule is now a single-row in the first-iteration decision table
    assert "Pure greeting (hi/hey/morning)" in out.system_prompt
    # Cognitive-tool discipline preserved (no update_* for filler)
    assert "Do NOT call cognitive tools (update_*) for greetings or filler." in out.system_prompt
    assert "1. update_beliefs() or text response directly" not in out.system_prompt


def test_standard_prompt_routes_work_outside_conversation_through_authority() -> None:
    out = _build(grounding_capsule=None)
    # First-iteration table routes live-state work to dispatch_task (tightened wording)
    assert "Explicit live-state work (book/send/" in out.system_prompt
    assert "Brainstorm / advice / recipe / idea    -> text only. Do NOT dispatch." in out.system_prompt
    # DISPATCH_RULES still owns the conversation-vs-work contract
    assert "Front owns conversation. Work outside conversation leaves Front" in out.system_prompt
    assert "Calendar, tasks, reminders, chores, shopping" in out.system_prompt
    assert "examples of work; memory and cognitive tools are not authoritative" in out.system_prompt
    # The "don't narrate action without dispatching" contract
    assert (
        "Announcing\nintent-to-act without a dispatch_task call is a contract violation"
        in out.system_prompt
    )
    assert (
        "Front does not call discover_capabilities or invoke_capability directly."
        in out.system_prompt
    )


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
    assert out.system_prompt.count("== ACTIVE MEMBER") == 1
    assert "You are talking to: unknown" not in out.system_prompt
    assert "name=Alex" in out.system_prompt
