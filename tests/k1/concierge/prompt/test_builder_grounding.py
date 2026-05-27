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
    assert "== FRONT ROLE CONTRACT ==" in prompt
    assert "== FRONT SITUATION FRAME ==" in prompt
    assert "-- INJECT: ACTIVE ACTOR --" in prompt
    assert "-- INJECT: VISIBLE SPACE --" in prompt
    assert "[self]\nname=Anand" in prompt
    assert "[space]\n- Riley" in prompt
    assert "== NOW ==" in prompt
    assert "== PLACE ==" in prompt
    assert "== AFFECTIVE POSTURE ==" in prompt
    assert "Raw: emotion=frustrated valence=-0.2 arousal=0.7" in prompt
    assert "-- INJECT: CONSCIENCE / POLICY --" in prompt
    assert "forbidden=delete_account" in prompt
    assert "must_ask=send_message" in prompt
    assert "-- INJECT: CONVERSATION STATE --" in prompt
    assert "== CONVERSATION HISTORY (COMPRESSED) ==" in prompt
    assert "== DYNAMIC IDENTITY CONTEXT ==" in prompt
    assert "-- INJECT: REFERENCE PROFILE --" in prompt
    assert "[preferences]" in prompt

    expected_order = [
        "== FRONT ROLE CONTRACT ==",
        "== FRONT SITUATION FRAME ==",
        "-- INJECT: ACTIVE ACTOR --",
        "-- INJECT: VISIBLE SPACE --",
        "-- INJECT: CONSCIENCE / POLICY --",
        "-- INJECT: NOW --",
        "-- INJECT: PLACE --",
        "-- INJECT: DYNAMIC IDENTITY CONTEXT --",
        "-- INJECT: REFERENCE PROFILE --",
        "-- INJECT: AFFECTIVE POSTURE --",
        "-- INJECT: INTERACTION PROFILE --",
        "-- INJECT: CONVERSATION STATE --",
        "-- INJECT: ACTIVE WORK --",
        "-- INJECT: MEMORY AND AUTHORITY BOUNDARY --",
        "== CURRENT EVENT ==",
        "== TOOL CONTRACT ==",
        "== RESPONSE BEHAVIOR ==",
    ]
    positions = [prompt.index(marker) for marker in expected_order]
    assert positions == sorted(positions)
    assert prompt.index("== DYNAMIC IDENTITY CONTEXT ==") < prompt.index(
        "== CONVERSATION HISTORY (COMPRESSED) =="
    )


def test_builder_no_longer_reads_temporal_section_directly() -> None:
    for configs in SS_READ_CONFIGS.values():
        assert all(config.section != "temporal" for config in configs)


# ---------------------------------------------------------------------------
# M4.I11 — Front Iteration 2 typed grounding seating
# ---------------------------------------------------------------------------


async def test_builder_v2_seats_typed_grounding_time_and_place_and_device(
    tmp_path,
) -> None:
    """When ``prompt.front_prompt_iteration: v2`` is set, the Front prompt
    must seat the typed ``== GROUNDING ==``, ``== TIME ==``, and
    ``== PLACE AND DEVICE ==`` blocks in place of the v1
    ``== NOW ==`` / ``== PLACE ==`` blocks, with matching seat labels.
    """
    from k1.concierge.config import load_config, reset_config

    override = tmp_path / "config.yaml"
    override.write_text(
        "prompt:\n  front_prompt_iteration: v2\n",
        encoding="utf-8",
    )
    load_config(override)
    try:
        bundle = GroundingFactory.create_standalone()
        projection = await bundle.service.build_projection(
            "s1", consumer="front", turn_id="t1"
        )

        built = DynamicPromptBuilder().build(
            PromptMode.STANDARD,
            AffectBand("neutral"),
            history_messages=[],
            all_tool_schemas=[],
            grounding_projection=projection,
        )
        prompt = built.system_prompt

        # v2 typed block headers are seated.
        assert "== GROUNDING ==" in prompt
        assert "== TIME ==" in prompt
        assert "== PLACE AND DEVICE ==" in prompt
        # v1 headers must not appear when v2 is active and projection is present.
        assert "== NOW ==" not in prompt
        assert "\n== PLACE ==" not in prompt

        # Seat labels must match the typed block names.
        assert "-- INJECT: GROUNDING META --" in prompt
        assert "-- INJECT: TIME --" in prompt
        assert "-- INJECT: PLACE AND DEVICE --" in prompt
        assert "-- INJECT: NOW --" not in prompt

        # Seating order is preserved.
        expected_order = [
            "-- INJECT: ACTIVE ACTOR --",
            "-- INJECT: VISIBLE SPACE --",
            "-- INJECT: CONSCIENCE / POLICY --",
            "-- INJECT: GROUNDING META --",
            "-- INJECT: TIME --",
            "-- INJECT: PLACE AND DEVICE --",
            "-- INJECT: DYNAMIC IDENTITY CONTEXT --",
            "-- INJECT: REFERENCE PROFILE --",
            "-- INJECT: AFFECTIVE POSTURE --",
        ]
        positions = [prompt.index(marker) for marker in expected_order]
        assert positions == sorted(positions)
    finally:
        reset_config()


async def test_builder_v1_default_keeps_now_and_place_blocks() -> None:
    """Default config must retain the v1 ``== NOW ==``/``== PLACE ==`` seating."""
    from k1.concierge.config import reset_config

    reset_config()
    try:
        bundle = GroundingFactory.create_standalone()
        projection = await bundle.service.build_projection(
            "s1", consumer="front", turn_id="t1"
        )

        built = DynamicPromptBuilder().build(
            PromptMode.STANDARD,
            AffectBand("neutral"),
            history_messages=[],
            all_tool_schemas=[],
            grounding_projection=projection,
        )
        prompt = built.system_prompt

        assert "== NOW ==" in prompt
        assert "== PLACE ==" in prompt
        assert "== GROUNDING ==" not in prompt
        assert "== TIME ==" not in prompt
        assert "== PLACE AND DEVICE ==" not in prompt
        assert "-- INJECT: NOW --" in prompt
        assert "-- INJECT: PLACE --" in prompt
        assert "-- INJECT: GROUNDING META --" not in prompt
    finally:
        reset_config()

