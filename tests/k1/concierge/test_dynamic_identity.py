"""
tests.k1.concierge.test_dynamic_identity
E-0.5.26 I-0.5.26.3: DynamicIdentityContext (OPP-7) tests.

Validates:
    1. Initial state + config defaults.
    2. compute() — IdentitySnapshot generation per turn.
    3. Role selection: SUPPORTER/EXPERT/EXECUTOR/PEER/GUIDE rules.
    4. Role adaptation disabled → always default_role.
    5. Domain expertise learning + capping at 1.0.
    6. Formality drift over turns (formal → casual).
    7. Emotional attunement mapping for all affect bands.
    8. Context tags: multitasking, extended_session, domain, returning_topic.
    9. IdentitySnapshot.to_prompt_block() formatting.
    10. ConversationalRole constants.
"""

from __future__ import annotations

import pytest

from k1.concierge.identity.dynamic_identity import (
    ConversationalRole,
    DynamicIdentityConfig,
    DynamicIdentityContext,
    IdentitySnapshot,
)

# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def dic() -> DynamicIdentityContext:
    return DynamicIdentityContext()


@pytest.fixture
def dic_no_adapt() -> DynamicIdentityContext:
    """All adaptations disabled."""
    return DynamicIdentityContext(
        DynamicIdentityConfig(
            enable_role_adaptation=False,
            enable_expertise_tracking=False,
            enable_formality_drift=False,
        )
    )


# =========================================================================
# 1. Initial state + config
# =========================================================================


class TestInitialState:
    def test_zero_turn_count(self, dic: DynamicIdentityContext) -> None:
        assert dic.turn_count == 0

    def test_empty_expertise(self, dic: DynamicIdentityContext) -> None:
        assert dic.domain_expertise == {}

    def test_default_config(self) -> None:
        cfg = DynamicIdentityConfig()
        assert cfg.enable_role_adaptation is True
        assert cfg.enable_expertise_tracking is True
        assert cfg.enable_formality_drift is True
        assert cfg.default_role == ConversationalRole.PEER
        assert cfg.expertise_learning_rate == 0.1

    def test_conversational_role_constants(self) -> None:
        assert ConversationalRole.EXPERT == "expert"
        assert ConversationalRole.PEER == "peer"
        assert ConversationalRole.GUIDE == "guide"
        assert ConversationalRole.SUPPORTER == "supporter"
        assert ConversationalRole.EXECUTOR == "executor"


# =========================================================================
# 2. compute() — basic snapshot
# =========================================================================


class TestCompute:
    def test_returns_identity_snapshot(self, dic: DynamicIdentityContext) -> None:
        snap = dic.compute(user_id="u1", user_name="Alice")
        assert isinstance(snap, IdentitySnapshot)

    def test_user_fields(self, dic: DynamicIdentityContext) -> None:
        snap = dic.compute(user_id="u1", user_name="Alice")
        assert snap.active_user_id == "u1"
        assert snap.active_user_name == "Alice"

    def test_turn_count_increments(self, dic: DynamicIdentityContext) -> None:
        dic.compute()
        dic.compute()
        dic.compute()
        assert dic.turn_count == 3

    def test_relationship_turns_match(self, dic: DynamicIdentityContext) -> None:
        dic.compute()
        snap = dic.compute()
        assert snap.relationship_turns == 2


# =========================================================================
# 3. Role selection rules
# =========================================================================


class TestRoleSelection:
    def test_crisis_returns_supporter(self, dic: DynamicIdentityContext) -> None:
        snap = dic.compute(affect_band="crisis")
        assert snap.conversational_role == ConversationalRole.SUPPORTER

    def test_low_affect_returns_supporter(self, dic: DynamicIdentityContext) -> None:
        snap = dic.compute(affect_band="low")
        assert snap.conversational_role == ConversationalRole.SUPPORTER

    def test_high_complexity_returns_expert(self, dic: DynamicIdentityContext) -> None:
        """P3.4a: complexity_tier removed; HIGH→EXPERT branch deleted.

        With no complexity signal, default GUIDE role is returned (early turns).
        """
        snap = dic.compute()
        assert snap.conversational_role == ConversationalRole.GUIDE

    def test_inflight_tasks_returns_executor(self, dic: DynamicIdentityContext) -> None:
        snap = dic.compute(has_inflight_tasks=True)
        assert snap.conversational_role == ConversationalRole.EXECUTOR

    def test_early_turns_returns_guide(self, dic: DynamicIdentityContext) -> None:
        snap = dic.compute()  # turn 1
        assert snap.conversational_role == ConversationalRole.GUIDE

    def test_after_10_turns_returns_peer(self, dic: DynamicIdentityContext) -> None:
        for _ in range(10):
            dic.compute()
        snap = dic.compute()  # turn 11
        assert snap.conversational_role == ConversationalRole.PEER

    def test_crisis_overrides_high_complexity(self, dic: DynamicIdentityContext) -> None:
        """Crisis affect takes precedence in role selection."""
        snap = dic.compute(affect_band="crisis")
        assert snap.conversational_role == ConversationalRole.SUPPORTER

    def test_high_complexity_overrides_inflight(self, dic: DynamicIdentityContext) -> None:
        """P3.4a: complexity_tier removed; inflight tasks now win."""
        snap = dic.compute(has_inflight_tasks=True)
        assert snap.conversational_role == ConversationalRole.EXECUTOR


# =========================================================================
# 4. Role adaptation disabled
# =========================================================================


class TestRoleAdaptationDisabled:
    def test_always_default_role(self, dic_no_adapt: DynamicIdentityContext) -> None:
        snap = dic_no_adapt.compute(affect_band="crisis")
        assert snap.conversational_role == ConversationalRole.PEER

    def test_custom_default_role(self) -> None:
        dic = DynamicIdentityContext(
            DynamicIdentityConfig(
                enable_role_adaptation=False,
                default_role=ConversationalRole.GUIDE,
            )
        )
        snap = dic.compute()
        assert snap.conversational_role == ConversationalRole.GUIDE


# =========================================================================
# 5. Domain expertise learning
# =========================================================================


class TestDomainExpertise:
    def test_expertise_accumulates(self, dic: DynamicIdentityContext) -> None:
        dic.compute(domain="travel")
        dic.compute(domain="travel")
        dic.compute(domain="travel")
        assert dic.domain_expertise["travel"] == pytest.approx(0.3)

    def test_expertise_capped_at_one(self, dic: DynamicIdentityContext) -> None:
        for _ in range(20):
            dic.compute(domain="cooking")
        assert dic.domain_expertise["cooking"] == 1.0

    def test_multiple_domains(self, dic: DynamicIdentityContext) -> None:
        dic.compute(domain="travel")
        dic.compute(domain="finance")
        dic.compute(domain="travel")
        assert "travel" in dic.domain_expertise
        assert "finance" in dic.domain_expertise
        assert dic.domain_expertise["travel"] == pytest.approx(0.2)
        assert dic.domain_expertise["finance"] == pytest.approx(0.1)

    def test_no_domain_no_expertise(self, dic: DynamicIdentityContext) -> None:
        dic.compute()
        assert dic.domain_expertise == {}

    def test_expertise_tracking_disabled(self, dic_no_adapt: DynamicIdentityContext) -> None:
        dic_no_adapt.compute(domain="travel")
        assert dic_no_adapt.domain_expertise == {}

    def test_expertise_in_snapshot(self, dic: DynamicIdentityContext) -> None:
        dic.compute(domain="travel")
        snap = dic.compute(domain="travel")
        assert snap.domain_expertise["travel"] == pytest.approx(0.2)

    def test_snapshot_expertise_is_copy(self, dic: DynamicIdentityContext) -> None:
        """Mutating snapshot dict shouldn't affect internal state."""
        dic.compute(domain="travel")
        snap = dic.compute(domain="travel")
        snap.domain_expertise["travel"] = 999.0
        assert dic.domain_expertise["travel"] == pytest.approx(0.2)


# =========================================================================
# 6. Formality drift
# =========================================================================


class TestFormalityDrift:
    def test_early_turns_formal(self, dic: DynamicIdentityContext) -> None:
        snap = dic.compute()  # turn 1
        assert snap.formality_level == pytest.approx(0.6)

    def test_mid_turns_decrease(self, dic: DynamicIdentityContext) -> None:
        for _ in range(3):
            dic.compute()
        snap = dic.compute()  # turn 4
        assert snap.formality_level < 0.6

    def test_late_turns_casual(self, dic: DynamicIdentityContext) -> None:
        for _ in range(20):
            dic.compute()
        snap = dic.compute()  # turn 21
        assert snap.formality_level == pytest.approx(0.3)

    def test_formality_has_floor(self, dic: DynamicIdentityContext) -> None:
        for _ in range(50):
            dic.compute()
        snap = dic.compute()
        assert snap.formality_level >= 0.2

    def test_formality_disabled(self, dic_no_adapt: DynamicIdentityContext) -> None:
        snap = dic_no_adapt.compute()
        assert snap.formality_level == 0.5


# =========================================================================
# 7. Emotional attunement
# =========================================================================


class TestEmotionalAttunement:
    def test_crisis(self, dic: DynamicIdentityContext) -> None:
        snap = dic.compute(affect_band="crisis")
        assert "calm" in snap.emotional_attunement.lower()

    def test_low(self, dic: DynamicIdentityContext) -> None:
        snap = dic.compute(affect_band="low")
        assert "gentle" in snap.emotional_attunement.lower()

    def test_neutral(self, dic: DynamicIdentityContext) -> None:
        snap = dic.compute(affect_band="neutral")
        assert (
            "natural" in snap.emotional_attunement.lower()
            or "efficient" in snap.emotional_attunement.lower()
        )

    def test_positive(self, dic: DynamicIdentityContext) -> None:
        snap = dic.compute(affect_band="positive")
        assert (
            "celebrate" in snap.emotional_attunement.lower()
            or "energy" in snap.emotional_attunement.lower()
        )

    def test_elevated(self, dic: DynamicIdentityContext) -> None:
        snap = dic.compute(affect_band="elevated")
        assert "acknowledge" in snap.emotional_attunement.lower()

    def test_unknown_band(self, dic: DynamicIdentityContext) -> None:
        snap = dic.compute(affect_band="unknown")
        assert snap.emotional_attunement == ""


# =========================================================================
# 8. Context tags
# =========================================================================


class TestContextTags:
    def test_multitasking_tag(self, dic: DynamicIdentityContext) -> None:
        snap = dic.compute(has_inflight_tasks=True)
        assert "multitasking" in snap.context_tags

    def test_extended_session_tag(self, dic: DynamicIdentityContext) -> None:
        for _ in range(15):
            dic.compute()
        snap = dic.compute()  # turn 16
        assert "extended_session" in snap.context_tags

    def test_domain_tag(self, dic: DynamicIdentityContext) -> None:
        snap = dic.compute(domain="travel")
        assert "domain:travel" in snap.context_tags

    def test_returning_topic_tag(self, dic: DynamicIdentityContext) -> None:
        """After 6+ visits to a domain (expertise > 0.5), 'returning_topic' tag appears."""
        for _ in range(6):
            dic.compute(domain="travel")
        snap = dic.compute(domain="travel")
        assert "returning_topic" in snap.context_tags

    def test_no_tags_baseline(self, dic: DynamicIdentityContext) -> None:
        snap = dic.compute()
        # Turn 1, no domain, no inflight → no tags
        assert "multitasking" not in snap.context_tags
        assert "extended_session" not in snap.context_tags


# =========================================================================
# 9. IdentitySnapshot.to_prompt_block()
# =========================================================================


class TestToPromptBlock:
    def test_contains_header_and_footer(self) -> None:
        snap = IdentitySnapshot()
        block = snap.to_prompt_block()
        assert "== DYNAMIC IDENTITY CONTEXT ==" in block
        assert "== END IDENTITY ==" in block

    def test_includes_user_name(self) -> None:
        snap = IdentitySnapshot(active_user_name="Alice")
        block = snap.to_prompt_block()
        assert "Speaking with: Alice" in block

    def test_excludes_user_name_if_empty(self) -> None:
        snap = IdentitySnapshot()
        block = snap.to_prompt_block()
        assert "Speaking with:" not in block

    def test_includes_role(self) -> None:
        snap = IdentitySnapshot(conversational_role="expert")
        block = snap.to_prompt_block()
        assert "Role: expert" in block

    def test_includes_expertise(self) -> None:
        snap = IdentitySnapshot(domain_expertise={"travel": 0.8, "finance": 0.3})
        block = snap.to_prompt_block()
        assert "Domain expertise:" in block
        assert "travel" in block

    def test_formality_label_formal(self) -> None:
        snap = IdentitySnapshot(formality_level=0.8)
        block = snap.to_prompt_block()
        assert "Register: formal" in block

    def test_formality_label_casual(self) -> None:
        snap = IdentitySnapshot(formality_level=0.2)
        block = snap.to_prompt_block()
        assert "Register: casual" in block

    def test_formality_label_balanced(self) -> None:
        snap = IdentitySnapshot(formality_level=0.5)
        block = snap.to_prompt_block()
        assert "Register: balanced" in block

    def test_includes_attunement(self) -> None:
        snap = IdentitySnapshot(emotional_attunement="Be calm and grounding.")
        block = snap.to_prompt_block()
        assert "Attunement: Be calm and grounding." in block

    def test_excludes_attunement_if_empty(self) -> None:
        snap = IdentitySnapshot()
        block = snap.to_prompt_block()
        assert "Attunement:" not in block

    def test_includes_context_tags(self) -> None:
        snap = IdentitySnapshot(context_tags=["multitasking", "domain:travel"])
        block = snap.to_prompt_block()
        assert "Context: multitasking, domain:travel" in block

    def test_excludes_tags_if_empty(self) -> None:
        snap = IdentitySnapshot()
        block = snap.to_prompt_block()
        assert "Context:" not in block
