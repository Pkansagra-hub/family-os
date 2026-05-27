"""M1.5-E4: Front prompt builder grounding projection rendering."""

from __future__ import annotations

from types import SimpleNamespace

from k1.concierge.prompt.affect import AffectBand
from k1.concierge.prompt.builder import SS_READ_CONFIGS, DynamicPromptBuilder
from k1.concierge.prompt.mode import PromptMode
from k1.grounding.factory import GroundingFactory
from k1.selfmodel.contracts.capsule import GroundingCapsule


class _SituationFrameSS:
    def __init__(self) -> None:
        self.affective_now = SimpleNamespace(
            current_emotion="frustrated",
            intensity=0.62,
            valence=-0.2,
            arousal=0.7,
        )

    def get_section(self, name: str):
        if name == "affective_now":
            return self.affective_now
        return None


async def test_builder_renders_now_and_place_from_grounding_projection() -> None:
    bundle = GroundingFactory.create_standalone()
    projection = await bundle.service.build_projection("s1", consumer="front", turn_id="t1")

    built = DynamicPromptBuilder().build(
        PromptMode.STANDARD,
        AffectBand("neutral"),
        history_messages=[],
        all_tool_schemas=[],
        grounding_projection=projection,
    )

    assert "== NOW ==" in built.system_prompt
    assert "== PLACE ==" in built.system_prompt


async def test_builder_situation_frame_survives_empty_tool_surface() -> None:
    """M4.I5 guard: grounding/read context must not depend on Front tools."""
    bundle = GroundingFactory.create_standalone()
    projection = await bundle.service.build_projection("s1", consumer="front", turn_id="t1")
    capsule = GroundingCapsule(
        self_block="[self]\nname=Anand\nrole=guardian",
        space_graph_block="[space]\n- Riley (child)",
        preferences_block="[preferences]\n- meal_style=vegetarian",
        conscience_block="[conscience]\nforbidden=delete_account\nmust_ask=send_message",
        freshness_footer="[freshness]\nworst_of_three=fresh",
    )

    built = DynamicPromptBuilder().build(
        PromptMode.STANDARD,
        AffectBand("neutral"),
        history_messages=[],
        all_tool_schemas=[],
        scenario_data={
            "compressed_context": "== CONVERSATION HISTORY (COMPRESSED) ==\n[EPISODE] survived",
            "identity_block": "== DYNAMIC IDENTITY CONTEXT ==\nRole: executor",
        },
        ss=_SituationFrameSS(),
        grounding_capsule=capsule,
        grounding_projection=projection,
    )

    prompt = built.system_prompt
    assert built.tools == []
    assert "== ACTIVE MEMBER (authoritative" in prompt
    assert "[self]\nname=Anand" in prompt
    assert "[space]\n- Riley" in prompt
    assert "== NOW ==" in prompt
    assert "== PLACE ==" in prompt
    assert "== AFFECT STATE ==" in prompt
    assert "Raw: emotion=frustrated valence=-0.2 arousal=0.7" in prompt
    assert "== CONSCIENCE (live, from constitution) ==" in prompt
    assert "forbidden=delete_account" in prompt
    assert "must_ask=send_message" in prompt
    assert "== SESSION STATE ==" in prompt
    assert "## affective_now" in prompt
    assert "Emotion: frustrated" in prompt
    assert "== CONVERSATION HISTORY (COMPRESSED) ==" in prompt
    assert "== DYNAMIC IDENTITY CONTEXT ==" in prompt
    assert "== REFERENCE PROFILE (live projection) ==" in prompt
    assert "[preferences]" in prompt

    assert prompt.index("== ACTIVE MEMBER") < prompt.index("== NOW ==")
    assert prompt.index("== NOW ==") < prompt.index("== AFFECT STATE ==")
    assert prompt.index("== AFFECT STATE ==") < prompt.index("== CONSCIENCE")
    assert prompt.index("== CONVERSATION HISTORY (COMPRESSED) ==") < prompt.index(
        "== DYNAMIC IDENTITY CONTEXT =="
    )


def test_builder_no_longer_reads_temporal_section_directly() -> None:
    for configs in SS_READ_CONFIGS.values():
        assert all(config.section != "temporal" for config in configs)
