"""
Tests for k1.bus.timing.timing_config -- TimingConfig prefix resolution.

Coverage targets:
    - Empty config returns default for all topics
    - Exact prefix match
    - Longest prefix match wins
    - Shorter prefix as fallback
    - Unknown topic falls back to default
    - set_default changes fallback behavior
    - reload atomically swaps rules
    - Reload preserves default
    - Empty prefix rejected (ValueError)
    - Non-DeliveryMode value rejected (TypeError)
    - Thread safety under concurrent resolve + reload
    - Edge cases: single segment, deeply nested, empty topic
    - rules property returns snapshot (not reference)
    - rule_count property
    - repr
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from k1.bus.envelope import DeliveryMode
from k1.bus.timing.timing_config import TimingConfig

STRICT = DeliveryMode.STRICT
RELAXED = DeliveryMode.RELAXED
BEST_EFFORT = DeliveryMode.BEST_EFFORT


# ===================================================================
# Construction
# ===================================================================


class TestTimingConfigConstruction:
    def test_empty_config_defaults_to_relaxed(self) -> None:
        config = TimingConfig()
        assert config.default == RELAXED
        assert config.rule_count == 0

    def test_custom_default(self) -> None:
        config = TimingConfig(default=STRICT)
        assert config.default == STRICT

    def test_rules_at_construction(self) -> None:
        config = TimingConfig(rules={"k1.cap": STRICT, "k1.sse": BEST_EFFORT})
        assert config.rule_count == 2

    def test_none_rules_is_empty(self) -> None:
        config = TimingConfig(rules=None)
        assert config.rule_count == 0


# ===================================================================
# Prefix Resolution
# ===================================================================


class TestTimingConfigResolve:
    def test_exact_prefix_match(self) -> None:
        config = TimingConfig(rules={"k1.capability": STRICT})
        assert config.resolve("k1.capability") == STRICT

    def test_longer_topic_matches_prefix(self) -> None:
        config = TimingConfig(rules={"k1.capability": STRICT})
        assert config.resolve("k1.capability.completed.v1") == STRICT

    def test_longest_prefix_wins(self) -> None:
        config = TimingConfig(
            rules={
                "k1": BEST_EFFORT,
                "k1.agent": RELAXED,
                "k1.agent.alpha.delta": STRICT,
            }
        )
        # Most specific match
        assert config.resolve("k1.agent.alpha.delta.v1") == STRICT
        # Fallback to k1.agent
        assert config.resolve("k1.agent.beta.lifecycle") == RELAXED
        # Fallback to k1
        assert config.resolve("k1.unknown.topic") == BEST_EFFORT

    def test_no_match_returns_default(self) -> None:
        config = TimingConfig(rules={"k1.capability": STRICT}, default=RELAXED)
        assert config.resolve("k2.something.else") == RELAXED

    def test_empty_topic_returns_default(self) -> None:
        config = TimingConfig(rules={"k1.capability": STRICT})
        assert config.resolve("") == RELAXED

    def test_single_segment_prefix(self) -> None:
        config = TimingConfig(rules={"k1": STRICT})
        assert config.resolve("k1") == STRICT
        assert config.resolve("k1.anything") == STRICT
        assert config.resolve("k2") == RELAXED

    def test_deeply_nested_topic(self) -> None:
        config = TimingConfig(rules={"k1.a.b.c.d.e": STRICT})
        assert config.resolve("k1.a.b.c.d.e.f.g") == STRICT
        assert config.resolve("k1.a.b.c.d") == RELAXED

    def test_multiple_rules_different_modes(self) -> None:
        config = TimingConfig(
            rules={
                "k1.capability": STRICT,
                "k1.orchestration": STRICT,
                "k1.affect": RELAXED,
                "k1.k0.sse": BEST_EFFORT,
            }
        )
        assert config.resolve("k1.capability.done.v1") == STRICT
        assert config.resolve("k1.orchestration.phase.v1") == STRICT
        assert config.resolve("k1.affect.update.v1") == RELAXED
        assert config.resolve("k1.k0.sse.event.v1") == BEST_EFFORT

    def test_prefix_does_not_match_partial_segment(self) -> None:
        """k1.cap should NOT match k1.capability (different segment)."""
        config = TimingConfig(rules={"k1.cap": STRICT})
        # k1.capability starts with "k1.cap" as a STRING but "cap" != "capability"
        # The resolve walks segments: k1.capability -> check "k1.capability" (no),
        # check "k1" (no) -> default.  "k1.cap" never matches.
        assert config.resolve("k1.capability.done") == RELAXED

    def test_overlapping_prefixes_most_specific_wins(self) -> None:
        config = TimingConfig(
            rules={
                "k1.agent": RELAXED,
                "k1.agent.alpha": STRICT,
            }
        )
        assert config.resolve("k1.agent.alpha.delta.v1") == STRICT
        assert config.resolve("k1.agent.beta.delta.v1") == RELAXED


# ===================================================================
# Mutation (set_default, reload)
# ===================================================================


class TestTimingConfigMutation:
    def test_set_default(self) -> None:
        config = TimingConfig()
        assert config.default == RELAXED
        config.set_default(STRICT)
        assert config.default == STRICT
        assert config.resolve("any.topic") == STRICT

    def test_reload_replaces_rules(self) -> None:
        config = TimingConfig(rules={"k1.old": STRICT})
        assert config.resolve("k1.old.topic") == STRICT

        config.reload({"k1.new": BEST_EFFORT})
        assert config.resolve("k1.old.topic") == RELAXED  # no longer matched
        assert config.resolve("k1.new.topic") == BEST_EFFORT

    def test_reload_preserves_default(self) -> None:
        config = TimingConfig(rules={"k1.x": STRICT}, default=BEST_EFFORT)
        config.reload({"k1.y": RELAXED})
        assert config.default == BEST_EFFORT
        assert config.resolve("unmatched") == BEST_EFFORT

    def test_reload_empty_clears_all_rules(self) -> None:
        config = TimingConfig(rules={"k1.x": STRICT})
        config.reload({})
        assert config.rule_count == 0
        assert config.resolve("k1.x.topic") == RELAXED


# ===================================================================
# Validation
# ===================================================================


class TestTimingConfigValidation:
    def test_empty_prefix_rejected(self) -> None:
        try:
            TimingConfig(rules={"": STRICT})
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "Empty prefix" in str(e)

    def test_non_delivery_mode_rejected(self) -> None:
        try:
            TimingConfig(rules={"k1.x": "STRICT"})  # type: ignore[dict-item]
            assert False, "Expected TypeError"
        except TypeError as e:
            assert "DeliveryMode" in str(e)

    def test_reload_validates_too(self) -> None:
        config = TimingConfig()
        try:
            config.reload({"": STRICT})
            assert False, "Expected ValueError"
        except ValueError:
            pass

    def test_reload_rejects_bad_type(self) -> None:
        config = TimingConfig()
        try:
            config.reload({"k1.x": 42})  # type: ignore[dict-item]
            assert False, "Expected TypeError"
        except TypeError:
            pass


# ===================================================================
# Properties & repr
# ===================================================================


class TestTimingConfigProperties:
    def test_rules_returns_snapshot(self) -> None:
        config = TimingConfig(rules={"k1.x": STRICT})
        snapshot = config.rules
        snapshot["k1.y"] = RELAXED  # mutate the snapshot
        assert config.rule_count == 1  # original unchanged

    def test_rule_count(self) -> None:
        config = TimingConfig(rules={"a": STRICT, "b": RELAXED, "c": BEST_EFFORT})
        assert config.rule_count == 3

    def test_repr(self) -> None:
        config = TimingConfig(rules={"k1.x": STRICT}, default=RELAXED)
        r = repr(config)
        assert "TimingConfig" in r
        assert "1" in r
        assert "RELAXED" in r


# ===================================================================
# Thread Safety
# ===================================================================


class TestTimingConfigThreadSafety:
    def test_concurrent_resolve_and_reload(self) -> None:
        """Concurrent resolves and reloads must not crash or return garbage."""
        config = TimingConfig(rules={"k1.capability": STRICT, "k1.affect": RELAXED})
        errors: list[str] = []
        stop = threading.Event()

        def resolver() -> None:
            while not stop.is_set():
                mode = config.resolve("k1.capability.done.v1")
                if mode not in (STRICT, RELAXED, BEST_EFFORT):
                    errors.append(f"Invalid mode: {mode}")
                mode2 = config.resolve("k1.unknown.topic")
                if mode2 not in (STRICT, RELAXED, BEST_EFFORT):
                    errors.append(f"Invalid default mode: {mode2}")

        def reloader() -> None:
            rules_a = {"k1.capability": STRICT, "k1.affect": RELAXED}
            rules_b = {"k1.capability": BEST_EFFORT, "k1.other": STRICT}
            toggle = False
            while not stop.is_set():
                config.reload(rules_a if toggle else rules_b)
                toggle = not toggle

        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = []
            for _ in range(4):
                futures.append(pool.submit(resolver))
            futures.append(pool.submit(reloader))

            # Run for 200ms
            stop.wait(timeout=0.2)
            stop.set()

            for f in futures:
                f.result()

        assert errors == [], f"Thread safety errors: {errors}"
