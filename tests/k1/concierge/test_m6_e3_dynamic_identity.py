"""tests/k1/concierge/test_m6_e3_dynamic_identity.py

M6.E3 -- Dynamic Identity wiring tests.

Covers:
  * I1: Role transitions across an 11-turn shift sequence
        (GUIDE -> SUPPORTER -> EXECUTOR -> PEER).
  * I2: ``identity_block`` placement -- prompt builder appends it AFTER
        Stage 9.5 promoted blocks, never as scenario_data fallback text.
  * I3: Back leak guard -- the identity_block must NOT bleed into Back
        execution prompts (Back receives raw turns, not Front prompts).
  * I3: ``front_handler`` accepts ``opp_pipeline`` while ``back_handler``
        does not -- compile-time enforcement of single-instance routing.
"""

from __future__ import annotations

import inspect

from k1.concierge.identity.dynamic_identity import (
    ConversationalRole,
    DynamicIdentityContext,
)
from k1.concierge.prompt.affect import AffectBand
from k1.concierge.prompt.builder import DynamicPromptBuilder
from k1.concierge.prompt.mode import PromptMode

# ---------------------------------------------------------------------------
# I1 -- 11-turn role shift sequence
# ---------------------------------------------------------------------------


class TestRoleShiftSequence:
    def test_eleven_turn_role_shift_sequence(self):
        """Verifies role adapts per turn across a realistic shift:

        T1-3   neutral / no inflight  -> GUIDE
        T4-5   crisis affect          -> SUPPORTER
        T6-9   neutral + inflight     -> EXECUTOR
        T10    GUIDE (boundary: turn_count==10 still <= 10)
        T11    PEER  (turn_count > 10)
        """
        dic = DynamicIdentityContext()
        roles: list[str] = []

        for _ in range(3):
            roles.append(dic.compute(affect_band="neutral").conversational_role)
        for _ in range(2):
            roles.append(dic.compute(affect_band="crisis").conversational_role)
        for _ in range(4):
            roles.append(
                dic.compute(affect_band="neutral", has_inflight_tasks=True).conversational_role
            )
        for _ in range(2):
            roles.append(dic.compute(affect_band="neutral").conversational_role)

        assert len(roles) == 11
        assert roles[:3] == [ConversationalRole.GUIDE] * 3
        assert roles[3:5] == [ConversationalRole.SUPPORTER] * 2
        assert roles[5:9] == [ConversationalRole.EXECUTOR] * 4
        # turn 10: count == 10 -> still GUIDE; turn 11: count > 10 -> PEER
        assert roles[9] == ConversationalRole.GUIDE
        assert roles[10] == ConversationalRole.PEER

    def test_role_adaptation_disabled_pins_to_default(self):
        from k1.concierge.identity.dynamic_identity import DynamicIdentityConfig

        dic = DynamicIdentityContext(
            DynamicIdentityConfig(
                enable_role_adaptation=False,
                default_role=ConversationalRole.PEER,
            )
        )
        for affect in ("crisis", "neutral", "elevated"):
            snap = dic.compute(affect_band=affect, has_inflight_tasks=True)
            assert snap.conversational_role == ConversationalRole.PEER


# ---------------------------------------------------------------------------
# I2 -- identity_block placement in assembled prompt
# ---------------------------------------------------------------------------


class _StubSS:
    def get_section(self, name: str):
        return None


class TestIdentityBlockPlacement:
    def _build(self, scenario_data):
        return DynamicPromptBuilder().build(
            mode=PromptMode.STANDARD,
            affect_band=AffectBand(band="neutral"),
            scenario_data=scenario_data,
            ss=_StubSS(),
        )

    def test_identity_block_rendered_with_header(self):
        ctx = self._build({"identity_block": "== DYNAMIC IDENTITY CONTEXT ==\nrole=EXECUTOR"})
        assert "DYNAMIC IDENTITY CONTEXT" in ctx.system_prompt
        assert "role=EXECUTOR" in ctx.system_prompt

    def test_identity_block_not_leaked_as_scenario_kv(self):
        ctx = self._build({"identity_block": "== DYNAMIC IDENTITY CONTEXT ==\nrole=EXECUTOR"})
        # The smuggled key name must never appear as raw text in the prompt.
        assert "identity_block:" not in ctx.system_prompt

    def test_compressed_context_before_identity_block(self):
        ctx = self._build(
            {
                "compressed_context": "== CONVERSATION HISTORY (COMPRESSED) ==\nx",
                "identity_block": "== DYNAMIC IDENTITY CONTEXT ==\ny",
            }
        )
        c = ctx.system_prompt.index("CONVERSATION HISTORY (COMPRESSED)")
        i = ctx.system_prompt.index("DYNAMIC IDENTITY CONTEXT")
        assert c < i, "compressed_context (Stage 8) must precede identity_block (post-9.5)"


# ---------------------------------------------------------------------------
# I3 -- Front/Back routing guard for opp_pipeline
# ---------------------------------------------------------------------------


class TestOppPipelineRouting:
    def test_front_handler_accepts_opp_pipeline(self):
        from k1.concierge.actors.front import front_handler

        assert "opp_pipeline" in inspect.signature(front_handler).parameters

    def test_back_handler_does_not_accept_opp_pipeline(self):
        from k1.concierge.actors.back import back_handler, back_resume_handler

        assert "opp_pipeline" not in inspect.signature(back_handler).parameters
        assert "opp_pipeline" not in inspect.signature(back_resume_handler).parameters

    def test_identity_block_not_in_back_executor_prompts(self):
        """Back executes raw tool calls -- it must never receive Front's
        identity_block. We assert by inspecting the back-actor module
        for any reference to ``identity_block`` (lexical leak guard)."""
        import pathlib

        from k1.concierge.actors import back as back_module

        src_path = pathlib.Path(back_module.__file__)
        src = src_path.read_text(encoding="utf-8")
        assert "identity_block" not in src, (
            "back actor must not reference identity_block " "(OPP-7 output is Front-only)"
        )
        assert "compressed_context" not in src, (
            "back actor must not reference compressed_context " "(OPP-6 output is Front-only)"
        )
