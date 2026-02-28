"""
Tests for M8 E8.2 -- Adaptive Weave Decision Engine.

Covers:
  - 8.2.1: WeaveDecision enum values, WeaveDecisionResult construction
  - 8.2.2: WeavePolicy.decide() 9-rule decision table (all rules + edge cases)
  - 8.2.3: WeavePolicyConfig defaults and custom values (config already in loader.py)
  - 8.2.4: TOPIC_WEAVE_DECIDED wiring (bus topic, builder, guard table, event)

Test count: ~70 tests across 7 test classes.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from poc.k1_poc.bus.builders import BUILDERS, build_weave_decided, get_builder_registry
from poc.k1_poc.bus.topics import ALL_TOPICS, RELAXED_TOPICS, STRICT_TOPICS, TOPIC_WEAVE_DECIDED
from poc.k1_poc.config.loader import WeavePolicyConfig
from poc.k1_poc.events.weave import WeaveDecisionMade
from poc.k1_poc.fsm.states import ConciergeState
from poc.k1_poc.fsm.transition_table import (
    FULL_GUARD_TABLE,
    SUBSCRIBED_TOPICS,
    GuardAction,
    get_guard_action,
)
from poc.k1_poc.protocols.weave_policy import (
    EMOTIONAL_GATE_OPEN,
    EMOTIONAL_GATE_SUPPRESS_ALL_NON_SAFETY,
    EMOTIONAL_GATE_SUPPRESS_TRIVIAL,
    IDLE_BATCH_MS,
    IDLE_EAGER_MS,
    WeaveDecision,
    WeaveDecisionResult,
    WeavePolicy,
    WeaveSignal,
)

# =====================================================================
# Helpers
# =====================================================================


def _signal(**overrides: object) -> WeaveSignal:
    """Build a WeaveSignal with sensible defaults, overriding as needed."""
    defaults: dict[str, object] = {
        "fsm_state": "COMPANIONING",
        "pending_count": 1,
        "pending_urgency_profile": {"critical": 0, "normal": 1, "low": 0},
        "has_critical": False,
        "user_typing": False,
        "user_idle_ms": 2000,
        "affect_band": "",
        "affect_valence": 0.0,
        "emotional_gate": EMOTIONAL_GATE_OPEN,
        "backpool_utilization": 0.3,
        "hitl_pending": False,
        "recent_weave_count": 0,
    }
    defaults.update(overrides)
    return WeaveSignal(**defaults)  # type: ignore[arg-type]


# =====================================================================
# 8.2.1 -- WeaveDecision enum
# =====================================================================


class TestWeaveDecisionEnum:
    """WeaveDecision IntEnum -- 5 values ordered by delivery urgency."""

    def test_enum_values(self) -> None:
        """All 5 values exist with correct ordinal."""
        assert WeaveDecision.IMMEDIATE == 0
        assert WeaveDecision.BATCH == 1
        assert WeaveDecision.DEFER == 2
        assert WeaveDecision.DIGEST == 3
        assert WeaveDecision.SUPPRESS == 4

    def test_enum_count(self) -> None:
        """Exactly 5 members."""
        assert len(WeaveDecision) == 5

    def test_ordering(self) -> None:
        """IMMEDIATE < BATCH < DEFER < DIGEST < SUPPRESS."""
        assert WeaveDecision.IMMEDIATE < WeaveDecision.BATCH
        assert WeaveDecision.BATCH < WeaveDecision.DEFER
        assert WeaveDecision.DEFER < WeaveDecision.DIGEST
        assert WeaveDecision.DIGEST < WeaveDecision.SUPPRESS

    def test_names(self) -> None:
        """All expected names are present."""
        names = {m.name for m in WeaveDecision}
        assert names == {"IMMEDIATE", "BATCH", "DEFER", "DIGEST", "SUPPRESS"}

    def test_is_int(self) -> None:
        """WeaveDecision members are integers (IntEnum)."""
        for member in WeaveDecision:
            assert isinstance(member, int)


# =====================================================================
# 8.2.1 -- WeaveDecisionResult dataclass
# =====================================================================


class TestWeaveDecisionResult:
    """WeaveDecisionResult frozen dataclass -- decision + metadata."""

    def test_default_construction(self) -> None:
        """Default result is BATCH with 500ms window."""
        result = WeaveDecisionResult()
        assert result.decision == WeaveDecision.BATCH
        assert result.window_ms == 500
        assert result.reasoning == ""
        assert result.urgency_override is False
        assert result.emotional_gate_applied is False

    def test_custom_construction(self) -> None:
        """All fields can be specified."""
        result = WeaveDecisionResult(
            decision=WeaveDecision.IMMEDIATE,
            window_ms=0,
            reasoning="R2: has_critical + gate=open -> IMMEDIATE",
            urgency_override=True,
            emotional_gate_applied=False,
        )
        assert result.decision == WeaveDecision.IMMEDIATE
        assert result.window_ms == 0
        assert "R2" in result.reasoning
        assert result.urgency_override is True
        assert result.emotional_gate_applied is False

    def test_frozen(self) -> None:
        """Result is immutable."""
        result = WeaveDecisionResult()
        with pytest.raises(FrozenInstanceError):
            result.window_ms = 999  # type: ignore[misc]

    def test_immediate_zero_window(self) -> None:
        """IMMEDIATE decisions should have 0ms window."""
        result = WeaveDecisionResult(decision=WeaveDecision.IMMEDIATE, window_ms=0)
        assert result.window_ms == 0

    def test_suppress_zero_window(self) -> None:
        """SUPPRESS decisions should have 0ms window."""
        result = WeaveDecisionResult(decision=WeaveDecision.SUPPRESS, window_ms=0)
        assert result.window_ms == 0


# =====================================================================
# 8.2.3 -- WeavePolicyConfig (already in config/loader.py)
# =====================================================================


class TestWeavePolicyConfig:
    """WeavePolicyConfig dataclass -- 11 configurable fields + enabled."""

    def test_default_values(self) -> None:
        """Config defaults match E8.2.3 spec."""
        cfg = WeavePolicyConfig()
        assert cfg.enabled is True
        assert cfg.idle_eager_ms == 10_000
        assert cfg.idle_batch_ms == 3_000
        assert cfg.typing_suppress_ms == 500
        assert cfg.digest_threshold_count == 3
        assert cfg.digest_window_ms == 15_000
        assert cfg.pool_pressure_threshold == 0.8
        assert cfg.pool_pressure_batch_ms == 2_000
        assert cfg.default_batch_ms == 500
        assert cfg.max_batch_ms == 5_000
        assert cfg.emotional_suppress_valence == -0.5
        assert cfg.max_consecutive_defers == 5

    def test_custom_values(self) -> None:
        """Config accepts custom thresholds."""
        cfg = WeavePolicyConfig(
            idle_eager_ms=5000,
            digest_threshold_count=5,
            pool_pressure_threshold=0.6,
            max_consecutive_defers=10,
        )
        assert cfg.idle_eager_ms == 5000
        assert cfg.digest_threshold_count == 5
        assert cfg.pool_pressure_threshold == 0.6
        assert cfg.max_consecutive_defers == 10

    def test_disabled(self) -> None:
        """Config can be disabled for fallback mode."""
        cfg = WeavePolicyConfig(enabled=False)
        assert cfg.enabled is False


# =====================================================================
# 8.2.2 -- WeavePolicy.decide() -- 9-rule decision table
# =====================================================================


class TestWeavePolicyDecide:
    """WeavePolicy.decide() -- priority-ordered decision table."""

    def setup_method(self) -> None:
        """Create a policy with default config for each test."""
        self.policy = WeavePolicy()
        self.policy_with_config = WeavePolicy(WeavePolicyConfig())

    # ----- Rule 1: LISTENING + long idle -> IMMEDIATE -----

    def test_rule1_listening_idle_eager(self) -> None:
        """R1: LISTENING + idle > IDLE_EAGER_MS -> IMMEDIATE."""
        sig = _signal(
            fsm_state="LISTENING",
            user_idle_ms=IDLE_EAGER_MS + 1,
        )
        result = self.policy.decide(sig)
        assert result.decision == WeaveDecision.IMMEDIATE
        assert result.window_ms == 0
        assert "R1" in result.reasoning
        assert result.urgency_override is False

    def test_rule1_listening_not_idle_enough(self) -> None:
        """R1 does NOT trigger when idle < IDLE_EAGER_MS."""
        sig = _signal(
            fsm_state="LISTENING",
            user_idle_ms=IDLE_EAGER_MS - 1,
        )
        result = self.policy.decide(sig)
        assert result.decision != WeaveDecision.IMMEDIATE or "R1" not in result.reasoning

    def test_rule1_non_listening_state(self) -> None:
        """R1 does NOT trigger in COMPANIONING state even with long idle."""
        sig = _signal(
            fsm_state="COMPANIONING",
            user_idle_ms=IDLE_EAGER_MS + 5000,
        )
        result = self.policy.decide(sig)
        assert "R1" not in result.reasoning

    def test_rule1_exact_boundary(self) -> None:
        """R1 does NOT trigger when idle == IDLE_EAGER_MS (must be strictly >)."""
        sig = _signal(
            fsm_state="LISTENING",
            user_idle_ms=IDLE_EAGER_MS,
        )
        result = self.policy.decide(sig)
        # At exact boundary, R1 should NOT fire (> not >=)
        assert "R1" not in result.reasoning

    # ----- Rule 2: critical + gate open -> IMMEDIATE -----

    def test_rule2_critical_gate_open(self) -> None:
        """R2: has_critical + gate=open -> IMMEDIATE."""
        sig = _signal(
            has_critical=True,
            emotional_gate=EMOTIONAL_GATE_OPEN,
        )
        result = self.policy.decide(sig)
        assert result.decision == WeaveDecision.IMMEDIATE
        assert result.window_ms == 0
        assert "R2" in result.reasoning
        assert result.urgency_override is True

    def test_rule2_critical_gate_not_open(self) -> None:
        """R2 does NOT trigger when gate is suppress_trivial."""
        sig = _signal(
            has_critical=True,
            emotional_gate=EMOTIONAL_GATE_SUPPRESS_TRIVIAL,
        )
        result = self.policy.decide(sig)
        # R2 requires gate=open
        assert "R2" not in result.reasoning

    def test_rule2_no_critical(self) -> None:
        """R2 does NOT trigger when has_critical=False."""
        sig = _signal(
            has_critical=False,
            emotional_gate=EMOTIONAL_GATE_OPEN,
        )
        result = self.policy.decide(sig)
        assert "R2" not in result.reasoning

    # ----- Rule 3: user typing -> DEFER -----

    def test_rule3_user_typing(self) -> None:
        """R3: user_typing=True -> DEFER."""
        sig = _signal(user_typing=True)
        result = self.policy.decide(sig)
        assert result.decision == WeaveDecision.DEFER
        assert result.window_ms == 0
        assert "R3" in result.reasoning

    def test_rule3_not_typing(self) -> None:
        """R3 does NOT trigger when user_typing=False."""
        sig = _signal(user_typing=False)
        result = self.policy.decide(sig)
        assert "R3" not in result.reasoning

    def test_rule3_typing_overrides_critical_when_gate_not_open(self) -> None:
        """R3 fires before R4/R5 because typing is checked at priority 3."""
        sig = _signal(
            user_typing=True,
            has_critical=True,
            emotional_gate=EMOTIONAL_GATE_SUPPRESS_TRIVIAL,
        )
        result = self.policy.decide(sig)
        # R2 requires gate=open so it won't fire, R3 fires next
        assert result.decision == WeaveDecision.DEFER
        assert "R3" in result.reasoning

    # ----- Rule 4: suppress_all_non_safety -> SUPPRESS -----

    def test_rule4_suppress_all(self) -> None:
        """R4: gate=suppress_all_non_safety -> SUPPRESS."""
        sig = _signal(
            emotional_gate=EMOTIONAL_GATE_SUPPRESS_ALL_NON_SAFETY,
            user_typing=False,
        )
        result = self.policy.decide(sig)
        assert result.decision == WeaveDecision.SUPPRESS
        assert result.window_ms == 0
        assert "R4" in result.reasoning
        assert result.emotional_gate_applied is True

    def test_rule4_not_suppress_all(self) -> None:
        """R4 does NOT trigger with gate=open."""
        sig = _signal(emotional_gate=EMOTIONAL_GATE_OPEN, user_typing=False)
        result = self.policy.decide(sig)
        assert "R4" not in result.reasoning

    # ----- Rule 5: suppress_trivial + no critical -> DEFER -----

    def test_rule5_suppress_trivial_no_critical(self) -> None:
        """R5: gate=suppress_trivial + no critical -> DEFER."""
        sig = _signal(
            emotional_gate=EMOTIONAL_GATE_SUPPRESS_TRIVIAL,
            has_critical=False,
            user_typing=False,
        )
        result = self.policy.decide(sig)
        assert result.decision == WeaveDecision.DEFER
        assert "R5" in result.reasoning
        assert result.emotional_gate_applied is True

    def test_rule5_suppress_trivial_with_critical(self) -> None:
        """R5 does NOT trigger when has_critical=True (critical overrides)."""
        sig = _signal(
            emotional_gate=EMOTIONAL_GATE_SUPPRESS_TRIVIAL,
            has_critical=True,
            user_typing=False,
        )
        result = self.policy.decide(sig)
        # R2 won't fire (gate != open), R5 won't fire (has_critical=True)
        assert "R5" not in result.reasoning

    # ----- Rule 6: 3+ pending + all low -> DIGEST -----

    def test_rule6_digest_all_low(self) -> None:
        """R6: pending>=3 + all low urgency -> DIGEST."""
        sig = _signal(
            pending_count=3,
            pending_urgency_profile={"critical": 0, "normal": 0, "low": 3},
            user_typing=False,
            emotional_gate=EMOTIONAL_GATE_OPEN,
        )
        result = self.policy.decide(sig)
        assert result.decision == WeaveDecision.DIGEST
        assert result.window_ms == 15_000
        assert "R6" in result.reasoning

    def test_rule6_pending_4_all_low(self) -> None:
        """R6 also fires with 4 low-urgency pending results."""
        sig = _signal(
            pending_count=4,
            pending_urgency_profile={"critical": 0, "normal": 0, "low": 4},
            user_typing=False,
            emotional_gate=EMOTIONAL_GATE_OPEN,
        )
        result = self.policy.decide(sig)
        assert result.decision == WeaveDecision.DIGEST
        assert "R6" in result.reasoning

    def test_rule6_not_all_low(self) -> None:
        """R6 does NOT trigger when some results are normal urgency."""
        sig = _signal(
            pending_count=3,
            pending_urgency_profile={"critical": 0, "normal": 1, "low": 2},
            user_typing=False,
            emotional_gate=EMOTIONAL_GATE_OPEN,
        )
        result = self.policy.decide(sig)
        assert "R6" not in result.reasoning

    def test_rule6_pending_below_threshold(self) -> None:
        """R6 does NOT trigger when pending < 3."""
        sig = _signal(
            pending_count=2,
            pending_urgency_profile={"critical": 0, "normal": 0, "low": 2},
            user_typing=False,
            emotional_gate=EMOTIONAL_GATE_OPEN,
        )
        result = self.policy.decide(sig)
        assert "R6" not in result.reasoning

    # ----- Rule 7: pending >= 1 + idle > IDLE_BATCH_MS -> BATCH -----

    def test_rule7_batch_idle(self) -> None:
        """R7: pending>=1 + idle > IDLE_BATCH_MS -> BATCH (dynamic window)."""
        sig = _signal(
            pending_count=1,
            user_idle_ms=IDLE_BATCH_MS + 1,
            user_typing=False,
            emotional_gate=EMOTIONAL_GATE_OPEN,
        )
        result = self.policy.decide(sig)
        assert result.decision == WeaveDecision.BATCH
        assert result.window_ms >= 200
        assert "R7" in result.reasoning

    def test_rule7_dynamic_window_shorter_when_more_idle(self) -> None:
        """R7 dynamic window shrinks with longer idle (500 - idle/20)."""
        sig_short_idle = _signal(
            pending_count=1,
            user_idle_ms=4000,
            user_typing=False,
            emotional_gate=EMOTIONAL_GATE_OPEN,
        )
        sig_long_idle = _signal(
            pending_count=1,
            user_idle_ms=8000,
            user_typing=False,
            emotional_gate=EMOTIONAL_GATE_OPEN,
        )
        result_short = self.policy.decide(sig_short_idle)
        result_long = self.policy.decide(sig_long_idle)
        # Longer idle -> shorter window (faster delivery)
        assert result_long.window_ms <= result_short.window_ms

    def test_rule7_window_minimum_200(self) -> None:
        """R7 dynamic window is clamped to minimum 200ms."""
        sig = _signal(
            pending_count=1,
            user_idle_ms=50_000,  # very idle
            user_typing=False,
            emotional_gate=EMOTIONAL_GATE_OPEN,
        )
        result = self.policy.decide(sig)
        assert result.window_ms >= 200

    def test_rule7_not_idle_enough(self) -> None:
        """R7 does NOT trigger when idle <= IDLE_BATCH_MS."""
        sig = _signal(
            pending_count=1,
            user_idle_ms=IDLE_BATCH_MS,
            user_typing=False,
            emotional_gate=EMOTIONAL_GATE_OPEN,
            backpool_utilization=0.3,
        )
        result = self.policy.decide(sig)
        assert "R7" not in result.reasoning

    def test_rule7_no_pending(self) -> None:
        """R7 does NOT trigger when pending_count=0."""
        sig = _signal(
            pending_count=0,
            user_idle_ms=IDLE_BATCH_MS + 1000,
            user_typing=False,
            emotional_gate=EMOTIONAL_GATE_OPEN,
            backpool_utilization=0.3,
        )
        result = self.policy.decide(sig)
        assert "R7" not in result.reasoning

    # ----- Rule 8: pool pressure -> BATCH (wide window) -----

    def test_rule8_pool_pressure(self) -> None:
        """R8: backpool_utilization > 0.8 -> BATCH(2000ms)."""
        sig = _signal(
            pending_count=0,
            user_idle_ms=1000,
            backpool_utilization=0.85,
            user_typing=False,
            emotional_gate=EMOTIONAL_GATE_OPEN,
        )
        result = self.policy.decide(sig)
        assert result.decision == WeaveDecision.BATCH
        assert result.window_ms == 2000
        assert "R8" in result.reasoning

    def test_rule8_at_threshold(self) -> None:
        """R8 does NOT trigger at exactly 0.8 (must be strictly >)."""
        sig = _signal(
            pending_count=0,
            user_idle_ms=1000,
            backpool_utilization=0.8,
            user_typing=False,
            emotional_gate=EMOTIONAL_GATE_OPEN,
        )
        result = self.policy.decide(sig)
        assert "R8" not in result.reasoning

    def test_rule8_below_threshold(self) -> None:
        """R8 does NOT trigger below 0.8."""
        sig = _signal(
            pending_count=0,
            user_idle_ms=1000,
            backpool_utilization=0.5,
            user_typing=False,
            emotional_gate=EMOTIONAL_GATE_OPEN,
        )
        result = self.policy.decide(sig)
        assert "R8" not in result.reasoning

    # ----- Rule 9: default -> BATCH(500ms) -----

    def test_rule9_default(self) -> None:
        """R9: default fallback -> BATCH(500ms)."""
        sig = _signal(
            fsm_state="COMPANIONING",
            pending_count=0,
            user_idle_ms=1000,
            backpool_utilization=0.3,
            user_typing=False,
            emotional_gate=EMOTIONAL_GATE_OPEN,
        )
        result = self.policy.decide(sig)
        assert result.decision == WeaveDecision.BATCH
        assert result.window_ms == 500
        assert "R9" in result.reasoning

    # ----- Priority ordering: first-match wins -----

    def test_rule1_beats_rule2(self) -> None:
        """R1 (LISTENING+idle) fires before R2 (critical) when both apply."""
        sig = _signal(
            fsm_state="LISTENING",
            user_idle_ms=IDLE_EAGER_MS + 1,
            has_critical=True,
            emotional_gate=EMOTIONAL_GATE_OPEN,
        )
        result = self.policy.decide(sig)
        assert "R1" in result.reasoning

    def test_rule2_beats_rule3(self) -> None:
        """R2 (critical+open) fires before R3 (typing)."""
        sig = _signal(
            has_critical=True,
            emotional_gate=EMOTIONAL_GATE_OPEN,
            user_typing=True,
        )
        result = self.policy.decide(sig)
        assert "R2" in result.reasoning

    def test_rule3_beats_rule4(self) -> None:
        """R3 (typing) fires before R4 (suppress_all)."""
        sig = _signal(
            user_typing=True,
            emotional_gate=EMOTIONAL_GATE_SUPPRESS_ALL_NON_SAFETY,
        )
        result = self.policy.decide(sig)
        assert "R3" in result.reasoning
        assert result.decision == WeaveDecision.DEFER

    def test_rule4_beats_rule5(self) -> None:
        """R4 (suppress_all) fires before R5 (suppress_trivial)."""
        # This tests that suppress_all -> SUPPRESS not DEFER
        sig = _signal(
            user_typing=False,
            emotional_gate=EMOTIONAL_GATE_SUPPRESS_ALL_NON_SAFETY,
            has_critical=False,
        )
        result = self.policy.decide(sig)
        assert result.decision == WeaveDecision.SUPPRESS
        assert "R4" in result.reasoning


# =====================================================================
# 8.2.2 -- WeavePolicy with custom config
# =====================================================================


class TestWeavePolicyWithConfig:
    """WeavePolicy respects WeavePolicyConfig thresholds."""

    def test_custom_idle_eager(self) -> None:
        """Custom idle_eager_ms threshold is respected."""
        cfg = WeavePolicyConfig(idle_eager_ms=5000)
        policy = WeavePolicy(cfg)
        sig = _signal(
            fsm_state="LISTENING",
            user_idle_ms=6000,
        )
        result = policy.decide(sig)
        assert result.decision == WeaveDecision.IMMEDIATE
        assert "R1" in result.reasoning

    def test_custom_digest_threshold(self) -> None:
        """Custom digest_threshold_count is respected."""
        cfg = WeavePolicyConfig(digest_threshold_count=5)
        policy = WeavePolicy(cfg)
        # 3 low pending: below custom threshold of 5
        sig = _signal(
            pending_count=3,
            pending_urgency_profile={"critical": 0, "normal": 0, "low": 3},
            user_typing=False,
            emotional_gate=EMOTIONAL_GATE_OPEN,
        )
        result = policy.decide(sig)
        assert "R6" not in result.reasoning

    def test_custom_digest_threshold_met(self) -> None:
        """Custom digest fires when count meets threshold."""
        cfg = WeavePolicyConfig(digest_threshold_count=5)
        policy = WeavePolicy(cfg)
        sig = _signal(
            pending_count=5,
            pending_urgency_profile={"critical": 0, "normal": 0, "low": 5},
            user_typing=False,
            emotional_gate=EMOTIONAL_GATE_OPEN,
        )
        result = policy.decide(sig)
        assert result.decision == WeaveDecision.DIGEST
        assert "R6" in result.reasoning

    def test_custom_pool_pressure_threshold(self) -> None:
        """Custom pool_pressure_threshold is respected."""
        cfg = WeavePolicyConfig(pool_pressure_threshold=0.5)
        policy = WeavePolicy(cfg)
        sig = _signal(
            pending_count=0,
            user_idle_ms=1000,
            backpool_utilization=0.6,
            user_typing=False,
            emotional_gate=EMOTIONAL_GATE_OPEN,
        )
        result = policy.decide(sig)
        assert result.decision == WeaveDecision.BATCH
        assert "R8" in result.reasoning

    def test_custom_pool_pressure_batch_ms(self) -> None:
        """Custom pool_pressure_batch_ms window is used."""
        cfg = WeavePolicyConfig(pool_pressure_batch_ms=3000)
        policy = WeavePolicy(cfg)
        sig = _signal(
            pending_count=0,
            user_idle_ms=1000,
            backpool_utilization=0.9,
            user_typing=False,
            emotional_gate=EMOTIONAL_GATE_OPEN,
        )
        result = policy.decide(sig)
        assert result.window_ms == 3000

    def test_custom_default_batch_ms(self) -> None:
        """Custom default_batch_ms is used for R9."""
        cfg = WeavePolicyConfig(default_batch_ms=250)
        policy = WeavePolicy(cfg)
        sig = _signal(
            pending_count=0,
            user_idle_ms=1000,
            backpool_utilization=0.3,
            user_typing=False,
            emotional_gate=EMOTIONAL_GATE_OPEN,
        )
        result = policy.decide(sig)
        assert result.window_ms == 250
        assert "R9" in result.reasoning

    def test_custom_digest_window_ms(self) -> None:
        """Custom digest_window_ms is used for R6."""
        cfg = WeavePolicyConfig(digest_window_ms=30_000)
        policy = WeavePolicy(cfg)
        sig = _signal(
            pending_count=3,
            pending_urgency_profile={"critical": 0, "normal": 0, "low": 3},
            user_typing=False,
            emotional_gate=EMOTIONAL_GATE_OPEN,
        )
        result = policy.decide(sig)
        assert result.window_ms == 30_000

    def test_none_config_uses_defaults(self) -> None:
        """WeavePolicy(None) uses module-level constants."""
        policy = WeavePolicy(None)
        sig = _signal(
            fsm_state="LISTENING",
            user_idle_ms=IDLE_EAGER_MS + 1,
        )
        result = policy.decide(sig)
        assert result.decision == WeaveDecision.IMMEDIATE


# =====================================================================
# 8.2.4 -- TOPIC_WEAVE_DECIDED wiring
# =====================================================================


class TestWeaveDecidedTopicWiring:
    """TOPIC_WEAVE_DECIDED is properly wired into bus infrastructure."""

    def test_topic_string(self) -> None:
        """Topic constant matches the spec string."""
        assert TOPIC_WEAVE_DECIDED == "k1.conversation.weave.decided.v1"

    def test_in_all_topics(self) -> None:
        """TOPIC_WEAVE_DECIDED is in ALL_TOPICS."""
        assert TOPIC_WEAVE_DECIDED in ALL_TOPICS

    def test_in_relaxed_topics(self) -> None:
        """TOPIC_WEAVE_DECIDED is RELAXED delivery."""
        assert TOPIC_WEAVE_DECIDED in RELAXED_TOPICS

    def test_not_in_strict_topics(self) -> None:
        """TOPIC_WEAVE_DECIDED is NOT strict."""
        assert TOPIC_WEAVE_DECIDED not in STRICT_TOPICS

    def test_all_topics_count(self) -> None:
        """ALL_TOPICS has 46 topics after E8.5.1 + E11.x."""
        assert len(ALL_TOPICS) == 46

    def test_relaxed_topics_count(self) -> None:
        """RELAXED_TOPICS has 10 topics after E8.5.1 + E11.x."""
        assert len(RELAXED_TOPICS) == 10

    def test_builder_exists(self) -> None:
        """build_weave_decided is in BUILDERS registry."""
        assert TOPIC_WEAVE_DECIDED in BUILDERS

    def test_builder_produces_envelope(self) -> None:
        """build_weave_decided produces a valid Envelope."""
        env = build_weave_decided(
            payload={"decision": "BATCH", "reason": "R9: default"},
            parent_id=42,
        )
        assert env.topic == TOPIC_WEAVE_DECIDED
        assert env.parent_id == 42

    def test_builder_registry_entry(self) -> None:
        """get_builder_registry includes TOPIC_WEAVE_DECIDED."""
        registry = get_builder_registry()
        assert TOPIC_WEAVE_DECIDED in registry
        entry = registry[TOPIC_WEAVE_DECIDED]
        assert entry.builder_fn is build_weave_decided

    def test_in_subscribed_topics(self) -> None:
        """TOPIC_WEAVE_DECIDED is in SUBSCRIBED_TOPICS."""
        assert TOPIC_WEAVE_DECIDED in SUBSCRIBED_TOPICS

    def test_subscribed_topics_count(self) -> None:
        """SUBSCRIBED_TOPICS has 30 topics after E8.5.1."""
        assert len(SUBSCRIBED_TOPICS) == 30

    def test_guard_table_all_states(self) -> None:
        """TOPIC_WEAVE_DECIDED has OBSERVE action in all 11 FSM states."""
        for state in ConciergeState:
            action, target = get_guard_action(state, TOPIC_WEAVE_DECIDED)
            assert (
                action == GuardAction.OBSERVE
            ), f"State {state.name}: expected OBSERVE, got {action}"
            assert target is None

    def test_guard_table_explicit_entries(self) -> None:
        """Each state dict in FULL_GUARD_TABLE has the topic entry."""
        for state in ConciergeState:
            state_guards = FULL_GUARD_TABLE[state]
            assert (
                TOPIC_WEAVE_DECIDED in state_guards
            ), f"State {state.name} missing TOPIC_WEAVE_DECIDED"


# =====================================================================
# 8.2.4 -- WeaveDecisionMade event extension
# =====================================================================


class TestWeaveDecisionMadeEvent:
    """WeaveDecisionMade event extended with M8 E8.2.4 fields."""

    def test_new_fields_default(self) -> None:
        """New fields have safe defaults."""
        evt = WeaveDecisionMade()
        assert evt.signal_snapshot == {}
        assert evt.urgency_override is False
        assert evt.emotional_gate_applied is False

    def test_new_fields_set(self) -> None:
        """New fields can be set via constructor."""
        snapshot = {"fsm_state": "LISTENING", "pending_count": 2}
        evt = WeaveDecisionMade(
            decision="IMMEDIATE",
            reason="R1: LISTENING + idle",
            signal_snapshot=snapshot,
            urgency_override=True,
            emotional_gate_applied=False,
        )
        assert evt.decision == "IMMEDIATE"
        assert evt.signal_snapshot == snapshot
        assert evt.urgency_override is True

    def test_to_payload_includes_new_fields(self) -> None:
        """to_payload() includes signal_snapshot, urgency_override, emotional_gate_applied."""
        snapshot = {"fsm_state": "LISTENING"}
        evt = WeaveDecisionMade(
            decision="BATCH",
            signal_snapshot=snapshot,
            urgency_override=False,
            emotional_gate_applied=True,
        )
        payload = evt.to_payload()
        assert payload["signal_snapshot"] == snapshot
        assert payload["urgency_override"] is False
        assert payload["emotional_gate_applied"] is True

    def test_from_payload_roundtrip(self) -> None:
        """from_payload reconstructs new fields correctly."""
        snapshot = {"fsm_state": "COMPANIONING", "pending_count": 3}
        original = WeaveDecisionMade(
            event_id="evt-1",
            session_id="s-1",
            decision="DIGEST",
            reason="R6: pending=3 all low",
            batch_window_ms=15000,
            signal_snapshot=snapshot,
            urgency_override=False,
            emotional_gate_applied=False,
        )
        payload = original.to_payload()
        restored = WeaveDecisionMade.from_payload(payload)
        assert restored.decision == "DIGEST"
        assert restored.signal_snapshot == snapshot
        assert restored.urgency_override is False
        assert restored.emotional_gate_applied is False
        assert restored.batch_window_ms == 15000

    def test_from_payload_missing_new_fields(self) -> None:
        """from_payload handles legacy payloads missing new fields."""
        legacy_payload = {
            "event_id": "evt-old",
            "decision": "IMMEDIATE",
            "reason": "old reason",
            "fsm_state": "LISTENING",
            "batch_window_ms": 0,
        }
        evt = WeaveDecisionMade.from_payload(legacy_payload)
        assert evt.signal_snapshot == {}
        assert evt.urgency_override is False
        assert evt.emotional_gate_applied is False

    def test_event_type(self) -> None:
        """event_type is conversation.weave.decided."""
        evt = WeaveDecisionMade()
        assert evt.event_type == "conversation.weave.decided"
