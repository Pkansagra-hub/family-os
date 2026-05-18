"""tests/k1/concierge/test_m6_e1_episodic_compression.py

M6.E1 -- Episodic Compression wiring tests.

Covers:
  * I2: Front handler receives ``opp_pipeline``; Back does NOT.
  * I3: ``_history_entries_to_opp_turns`` produces the canonical
        EpisodicCompressor turn shape from both dict rows and
        ``TypedHistoryEntry`` objects, with intent/safety_band/has_hitl
        derived from ``metadata``.
  * I4: ``DynamicPromptBuilder.build`` replaces ``history_active`` with
        ``compressed_context`` at Stage 8 and never leaks the smuggled
        keys through ``_format_scenario_data`` fallback.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from k1.concierge.compression.turn_shape import history_entries_to_opp_turns
from k1.concierge.prompt.affect import AffectBand
from k1.concierge.prompt.builder import DynamicPromptBuilder
from k1.concierge.prompt.mode import PromptMode

# ---------------------------------------------------------------------------
# I3 -- canonical turn shaping
# ---------------------------------------------------------------------------


class TestHistoryEntriesToOppTurns:
    def test_empty_returns_empty(self):
        assert history_entries_to_opp_turns(None) == []
        assert history_entries_to_opp_turns([]) == []

    def test_dict_row_user_input_maps_to_user_message(self):
        rows = [
            {
                "turn_number": 3,
                "entry_type": "user_input",
                "text": "hello",
                "source": "user",
                "metadata": {},
            }
        ]
        out = history_entries_to_opp_turns(rows)
        assert len(out) == 1
        t = out[0]
        assert t["turn_number"] == 3
        assert t["user_message"] == "hello"
        assert t["response"] == ""
        # entry_type fallback when no arbiter / no metadata intent
        assert t["intent"] == "user_input"
        assert t["has_hitl"] is False
        assert t["safety_band"] == "GREEN"

    def test_assistant_collapses_to_response(self):
        rows = [
            {
                "turn_number": 4,
                "entry_type": "front_response",
                "text": "ok",
                "source": "front",
                "metadata": {"safety_band": "AMBER"},
            }
        ]
        out = history_entries_to_opp_turns(rows)
        assert out[0]["user_message"] == ""
        assert out[0]["response"] == "ok"
        assert out[0]["safety_band"] == "AMBER"

    def test_intent_precedence_arbiter_decision_first(self):
        rows = [
            {
                "turn_number": 1,
                "entry_type": "user_input",
                "text": "x",
                "source": "user",
                "metadata": {
                    "arbiter": {"decision": "STANDARD"},
                    "intent": "WEAVE",
                },
            }
        ]
        out = history_entries_to_opp_turns(rows)
        assert out[0]["intent"] == "STANDARD"

    def test_intent_falls_back_to_metadata_intent(self):
        rows = [
            {
                "turn_number": 1,
                "entry_type": "user_input",
                "text": "x",
                "source": "user",
                "metadata": {"intent": "WEAVE"},
            }
        ]
        out = history_entries_to_opp_turns(rows)
        assert out[0]["intent"] == "WEAVE"

    def test_hitl_entries_flagged(self):
        for et in ("hitl_request", "hitl_response", "hil_request", "hil_response"):
            row = {
                "turn_number": 1,
                "entry_type": et,
                "text": "?",
                "source": "back",
                "metadata": {},
            }
            assert history_entries_to_opp_turns([row])[0]["has_hitl"] is True

    def test_typed_history_entry_object_input(self):
        # Use the real dataclass so we exercise the getattr branch.
        from k1.sessionstate.sections.history_active import TypedHistoryEntry

        entry = TypedHistoryEntry(
            turn_number=7,
            entry_type="user_input",
            text="hi",
            timestamp_ms=1000,
            source="user",
            metadata={
                "arbiter": {"decision": "STANDARD"},
                "entities": ["alice", "paris"],
                "safety_band": "RED",
            },
        )
        out = history_entries_to_opp_turns([entry])
        t = out[0]
        assert t["turn_number"] == 7
        assert t["user_message"] == "hi"
        assert t["intent"] == "STANDARD"
        assert t["entities"] == ["alice", "paris"]
        assert t["safety_band"] == "RED"


# ---------------------------------------------------------------------------
# I2 -- OPP routes to Front only
# ---------------------------------------------------------------------------


class TestOppPipelineFrontOnly:
    def test_back_handler_signature_has_no_opp_pipeline(self):
        """Back handlers must never accept an ``opp_pipeline`` parameter
        so the wiring layer cannot accidentally pass one in. This is a
        compile-time leak guard."""
        import inspect

        from k1.concierge.actors.back import back_handler, back_resume_handler

        assert "opp_pipeline" not in inspect.signature(back_handler).parameters
        assert "opp_pipeline" not in inspect.signature(back_resume_handler).parameters

    def test_front_handler_signature_has_opp_pipeline(self):
        """The Front handler accepts ``opp_pipeline`` so the session loop
        can forward the per-session OPP instance."""
        import inspect

        from k1.concierge.actors.front import front_handler

        assert "opp_pipeline" in inspect.signature(front_handler).parameters


# ---------------------------------------------------------------------------
# I4 -- builder replaces history_active with compressed_context
# ---------------------------------------------------------------------------


class _StubSection:
    """Minimal SS section that exposes a marker string via every renderer.

    We only need the SS surface to verify the *absence* of the history
    block when compressed_context is present.
    """

    SECTION_NAME = "history_active"


class _StubSS:
    def __init__(self, sections: dict[str, object] | None = None) -> None:
        self._sections = sections or {}

    def get_section(self, name: str):
        return self._sections.get(name)


class TestBuilderCompressedContextReplacesHistory:
    def _build(self, scenario_data, mode=PromptMode.STANDARD):
        builder = DynamicPromptBuilder()
        return builder.build(
            mode=mode,
            affect_band=AffectBand(band="neutral"),
            scenario_data=scenario_data,
            ss=_StubSS(),  # no history_active section -> nothing to render
        )

    def test_compressed_context_appears_at_stage_8(self):
        ctx = self._build(
            {
                "compressed_context": "== CONVERSATION HISTORY (COMPRESSED) ==\nfoo",
            }
        )
        assert "CONVERSATION HISTORY (COMPRESSED)" in ctx.system_prompt
        # And the smuggled key must NOT leak as raw "compressed_context: ..." text.
        assert "compressed_context:" not in ctx.system_prompt

    def test_identity_block_not_leaked_through_scenario_fallback(self):
        ctx = self._build(
            {
                "identity_block": "== DYNAMIC IDENTITY CONTEXT ==\nrole=EXECUTOR",
            }
        )
        assert "DYNAMIC IDENTITY CONTEXT" in ctx.system_prompt
        assert "identity_block:" not in ctx.system_prompt

    def test_both_blocks_present_when_both_supplied(self):
        ctx = self._build(
            {
                "compressed_context": "== CONVERSATION HISTORY (COMPRESSED) ==\nx",
                "identity_block": "== DYNAMIC IDENTITY CONTEXT ==\ny",
            }
        )
        assert "CONVERSATION HISTORY (COMPRESSED)" in ctx.system_prompt
        assert "DYNAMIC IDENTITY CONTEXT" in ctx.system_prompt
        # Order: compressed_context lives at Stage 8 (mid-prompt); identity
        # block lives after Stage 9.5 promoted blocks -- i.e. later.
        c_idx = ctx.system_prompt.index("CONVERSATION HISTORY (COMPRESSED)")
        i_idx = ctx.system_prompt.index("DYNAMIC IDENTITY CONTEXT")
        assert c_idx < i_idx


# ---------------------------------------------------------------------------
# I5 -- ExperienceLayer compression boundary (telemetry-only)
# ---------------------------------------------------------------------------


class _FakeCompressor:
    """Captures call surface; emits a deterministic episode."""

    def __init__(self):
        self.calls = 0
        self.config = SimpleNamespace(min_turns_to_compress=3)

    def compress_all(self, turns):
        self.calls += 1
        ep = SimpleNamespace()
        return [ep], turns[-1:]

    def build_compressed_context(self, episodes, recent):
        return "compressed-block"


@pytest.mark.asyncio
async def test_experience_layer_runs_compression_when_threshold_met():
    """M6.E1.I5: ExperienceLayer.tick must invoke the attached compressor
    once history reaches ``min_turns_to_compress`` and store metrics on
    ``self.last_*`` without mutating Session State."""
    from k1.concierge.experience.layer import ExperienceLayer

    fc = _FakeCompressor()
    layer = ExperienceLayer(episodic_compressor=fc)
    history = [
        {
            "turn_number": i,
            "entry_type": "user_input",
            "text": f"t{i}",
            "source": "user",
            "metadata": {},
        }
        for i in range(5)
    ]
    await layer.tick(
        "STANDARD",
        {"conversation_history": history, "user_cadence": {}},
    )
    assert fc.calls == 1
    assert layer.compression_count == 1
    assert layer.last_compressed_context == "compressed-block"
    assert layer.last_episodes_used == 1
    assert layer.last_recent_turns_kept == 1


@pytest.mark.asyncio
async def test_experience_layer_skips_compression_below_threshold():
    from k1.concierge.experience.layer import ExperienceLayer

    fc = _FakeCompressor()  # min_turns_to_compress=3
    layer = ExperienceLayer(episodic_compressor=fc)
    history = [
        {
            "turn_number": i,
            "entry_type": "user_input",
            "text": f"t{i}",
            "source": "user",
            "metadata": {},
        }
        for i in range(2)
    ]
    await layer.tick(
        "STANDARD",
        {"conversation_history": history, "user_cadence": {}},
    )
    assert fc.calls == 0
    assert layer.compression_count == 0
