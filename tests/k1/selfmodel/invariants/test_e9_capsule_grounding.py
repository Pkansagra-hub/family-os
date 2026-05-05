"""E9 invariant -- capsule has [self], no fabric verbs (M9.E3.I2).

The grounding capsule is the LLM's window into the actor's identity
and the household's social conscience. After the M6/M7 inversion it
MUST:

1. Contain a ``[self]`` block whenever the actor is non-anonymous.
2. NOT leak fabric/tool verbs into the prompt-facing text. Tools are
   carried separately under ``tools=[...]``; mixing them into the
   capsule re-creates the IAM-style confusion the inversion is meant
   to undo.

The check is deliberately lexical -- if a known fabric capability
name appears verbatim in the rendered capsule (other than inside the
``[conscience]`` block where social-act ids live), the test fails.
"""

from __future__ import annotations

import re

import pytest

from k1.selfmodel.contracts.conscience import ConscienceDigest
from k1.selfmodel.contracts.pattern import Goal
from k1.selfmodel.contracts.situation import (
    ApplicableRules,
    Capabilities,
    SelfView,
    SituationFrame,
    Visibility,
)
from k1.selfmodel.service.capsule_builder import GroundingCapsuleBuilder

# Concrete fabric verbs that must NEVER appear in [self]/[preferences]/...
# blocks. They MAY appear inside the [conscience] block when an act_id
# happens to share a name (transitional mapping for V0).
_FABRIC_VERBS_FORBIDDEN_OUTSIDE_CONSCIENCE = (
    "invoke_capability",
    "batch_invoke_capabilities",
    "spawn_via_fabric",
    "execute_workflow",
    "submit_result",
    "needs_human",
)


def _strip_conscience_block(text: str) -> str:
    """Remove ``[conscience] ... <next-block-or-eof>`` from ``text``."""
    # Greedy strip from "[conscience]" until the next block header or EOF.
    return re.sub(
        r"\[conscience\].*?(?=\n\[[a-z_]+\]|\Z)",
        "",
        text,
        flags=re.DOTALL,
    )


@pytest.fixture
def non_anonymous_frame() -> SituationFrame:
    return SituationFrame(
        actor_id="anand",
        situation_kind="caregiver_context_briefing",
        rules=ApplicableRules(),
        capabilities=Capabilities(),
        self_view=SelfView(
            actor_id="anand",
            display_name="Anand",
            role="guardian",
            preferences={"theme": "dark"},
            hobbies=("hiking",),
            goals=(Goal(goal_id="g1", summary="run 5k"),),
        ),
        conscience=ConscienceDigest(
            forbidden_acts=("set_medication",),
            must_ask_acts=("send_message",),
        ),
        visibility=Visibility(),
    )


def test_e9_capsule_has_self_block_for_named_actor(
    non_anonymous_frame: SituationFrame,
) -> None:
    capsule = GroundingCapsuleBuilder().build(non_anonymous_frame)
    text = capsule.as_prompt_text()
    assert "[self]" in text, "non-anonymous actor must surface [self] block"
    assert "name=Anand" in text


def test_e9_capsule_has_no_fabric_verbs_outside_conscience(
    non_anonymous_frame: SituationFrame,
) -> None:
    capsule = GroundingCapsuleBuilder().build(non_anonymous_frame)
    text = capsule.as_prompt_text()
    stripped = _strip_conscience_block(text)
    leaked = [verb for verb in _FABRIC_VERBS_FORBIDDEN_OUTSIDE_CONSCIENCE if verb in stripped]
    assert leaked == [], (
        f"fabric verbs leaked into capsule outside [conscience]: {leaked}\n"
        "tools belong in tools=[...], not in the conscience-grounded blocks."
    )
