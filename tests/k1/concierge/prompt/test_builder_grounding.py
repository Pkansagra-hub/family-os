"""M1.5-E4: Front prompt builder grounding projection rendering."""

from __future__ import annotations

from k1.concierge.prompt.affect import AffectBand
from k1.concierge.prompt.builder import SS_READ_CONFIGS, DynamicPromptBuilder
from k1.concierge.prompt.mode import PromptMode
from k1.grounding.factory import GroundingFactory


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


def test_builder_no_longer_reads_temporal_section_directly() -> None:
    for configs in SS_READ_CONFIGS.values():
        assert all(config.section != "temporal" for config in configs)
