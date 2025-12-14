"""
Unit tests for k0/config/feature_flags.py

Tests cover:
- FeatureFlags initialization
- ML tier selection
- Percentage-based rollout (consistent hashing)
- Failure tracking and auto-fallback
- Metrics collection
- Thread-safety

Related:
- k0/config/feature_flags.py: Implementation
- k0/modules/MODULE_ENHANCEMENT_PLAN.md: Issue 1.1.2

Issue: 1.1.2 - Feature Flag System
"""

import pytest

from k0.config.feature_flags import (
    FeatureFlags,
    FeatureFlagsConfig,
    MLTier,
    ModuleFlag,
    get_feature_flags,
    init_feature_flags,
    with_ml_tier,
)


class TestMLTier:
    """Tests for MLTier enum."""

    def test_tier_values(self):
        """Test tier string values."""
        assert MLTier.DISABLED.value == "disabled"
        assert MLTier.RULE_BASED.value == "rule_based"
        assert MLTier.SPACY_SMALL.value == "spacy_small"
        assert MLTier.SPACY_LARGE.value == "spacy_large"
        assert MLTier.TRANSFORMER_SMALL.value == "transformer_small"
        assert MLTier.TRANSFORMER_LARGE.value == "transformer_large"

    def test_tier_from_string(self):
        """Test creating tier from string."""
        assert MLTier("rule_based") == MLTier.RULE_BASED
        assert MLTier("transformer_small") == MLTier.TRANSFORMER_SMALL


class TestModuleFlag:
    """Tests for ModuleFlag dataclass."""

    def test_defaults(self):
        """Test default values."""
        flag = ModuleFlag(
            module_id="test.module",
            enabled_tier=MLTier.SPACY_LARGE,
        )
        assert flag.fallback_tier == MLTier.RULE_BASED
        assert flag.rollout_percentage == 100.0
        assert flag.metrics_enabled is True
        assert flag.failure_count == 0
        assert flag.max_failures_before_fallback == 3

    def test_should_use_advanced_tier_100_percent(self):
        """Test 100% rollout always returns True."""
        flag = ModuleFlag(
            module_id="test.module",
            enabled_tier=MLTier.TRANSFORMER_SMALL,
            rollout_percentage=100.0,
        )
        # Should always return True for 100% rollout
        for _ in range(10):
            assert flag.should_use_advanced_tier() is True

    def test_should_use_advanced_tier_0_percent(self):
        """Test 0% rollout always returns False."""
        flag = ModuleFlag(
            module_id="test.module",
            enabled_tier=MLTier.TRANSFORMER_SMALL,
            rollout_percentage=0.0,
        )
        # Should always return False for 0% rollout
        for _ in range(10):
            assert flag.should_use_advanced_tier() is False

    def test_consistent_hashing(self):
        """Test that same request_id gives same result."""
        flag = ModuleFlag(
            module_id="test.module",
            enabled_tier=MLTier.TRANSFORMER_SMALL,
            rollout_percentage=50.0,
        )
        # Same request_id should give consistent results
        result1 = flag.should_use_advanced_tier("request-123")
        result2 = flag.should_use_advanced_tier("request-123")
        assert result1 == result2

    def test_failure_threshold(self):
        """Test failure threshold triggers fallback."""
        flag = ModuleFlag(
            module_id="test.module",
            enabled_tier=MLTier.TRANSFORMER_SMALL,
            rollout_percentage=100.0,
            max_failures_before_fallback=3,
        )

        # Before failures, should use advanced
        assert flag.should_use_advanced_tier() is True

        # Record failures up to threshold
        flag.record_failure()
        flag.record_failure()
        assert flag.should_use_advanced_tier() is True  # Still 2 failures

        flag.record_failure()  # 3 failures = threshold
        assert flag.should_use_advanced_tier() is False  # Now fallback

    def test_record_success_decrements_failures(self):
        """Test that success decrements failure count."""
        flag = ModuleFlag(
            module_id="test.module",
            enabled_tier=MLTier.TRANSFORMER_SMALL,
        )
        flag.failure_count = 2
        flag.record_success()
        assert flag.failure_count == 1

    def test_reset_failures(self):
        """Test reset_failures clears count."""
        flag = ModuleFlag(
            module_id="test.module",
            enabled_tier=MLTier.TRANSFORMER_SMALL,
        )
        flag.failure_count = 5
        flag.reset_failures()
        assert flag.failure_count == 0


class TestFeatureFlagsConfig:
    """Tests for FeatureFlagsConfig dataclass."""

    def test_defaults(self):
        """Test default configuration values."""
        config = FeatureFlagsConfig()
        assert config.global_enabled is True
        assert config.default_tier == MLTier.RULE_BASED
        assert config.default_rollout_percentage == 100.0
        assert config.metrics_enabled is True
        assert config.auto_fallback_enabled is True


class TestFeatureFlags:
    """Tests for FeatureFlags class."""

    def test_init_loads_defaults(self):
        """Test that default flags are loaded."""
        flags = FeatureFlags()
        assert "affect.analyze" in flags._flags
        assert "hippocampus.semantic_project" in flags._flags
        assert "context.ingress_classify" in flags._flags

    def test_list_modules(self):
        """Test list_modules returns all registered modules."""
        flags = FeatureFlags()
        modules = flags.list_modules()
        assert isinstance(modules, list)
        assert "affect.analyze" in modules

    def test_get_tier_default(self):
        """Test get_tier returns tier for known module."""
        flags = FeatureFlags()
        tier = flags.get_tier("affect.analyze")
        assert tier == MLTier.RULE_BASED  # Default in our config

    def test_get_tier_unknown_module(self):
        """Test get_tier returns default for unknown module."""
        flags = FeatureFlags()
        tier = flags.get_tier("unknown.module")
        assert tier == flags._config.default_tier

    def test_get_flag(self):
        """Test get_flag returns ModuleFlag."""
        flags = FeatureFlags()
        flag = flags.get_flag("affect.analyze")
        assert flag is not None
        assert flag.module_id == "affect.analyze"

    def test_get_flag_unknown(self):
        """Test get_flag returns None for unknown module."""
        flags = FeatureFlags()
        flag = flags.get_flag("unknown.module")
        assert flag is None

    def test_set_tier(self):
        """Test set_tier updates module tier."""
        flags = FeatureFlags()
        flags.set_tier("affect.analyze", MLTier.TRANSFORMER_SMALL, 75.0)

        flag = flags.get_flag("affect.analyze")
        assert flag.enabled_tier == MLTier.TRANSFORMER_SMALL
        assert flag.rollout_percentage == 75.0

    def test_set_tier_new_module(self):
        """Test set_tier creates flag for new module."""
        flags = FeatureFlags()
        flags.set_tier("new.module", MLTier.SPACY_LARGE)

        flag = flags.get_flag("new.module")
        assert flag is not None
        assert flag.enabled_tier == MLTier.SPACY_LARGE

    def test_record_failure(self):
        """Test record_failure updates flag and metrics."""
        flags = FeatureFlags()
        initial_failures = flags._metrics["affect.analyze"]["failures"]

        flags.record_failure("affect.analyze")

        assert flags._metrics["affect.analyze"]["failures"] == initial_failures + 1

    def test_record_success(self):
        """Test record_success updates flag."""
        flags = FeatureFlags()
        flags._flags["affect.analyze"].failure_count = 2

        flags.record_success("affect.analyze")

        assert flags._flags["affect.analyze"].failure_count == 1

    def test_reset_failures(self):
        """Test reset_failures clears count."""
        flags = FeatureFlags()
        flags._flags["affect.analyze"].failure_count = 5

        flags.reset_failures("affect.analyze")

        assert flags._flags["affect.analyze"].failure_count == 0

    def test_get_metrics_all(self):
        """Test get_metrics returns all metrics."""
        flags = FeatureFlags()
        metrics = flags.get_metrics()
        assert "affect.analyze" in metrics
        assert "advanced_calls" in metrics["affect.analyze"]

    def test_get_metrics_specific(self):
        """Test get_metrics for specific module."""
        flags = FeatureFlags()
        metrics = flags.get_metrics("affect.analyze")
        assert "affect.analyze" in metrics
        assert len(metrics) == 1

    def test_get_all_flags(self):
        """Test get_all_flags returns dict."""
        flags = FeatureFlags()
        all_flags = flags.get_all_flags()
        assert isinstance(all_flags, dict)
        assert "affect.analyze" in all_flags
        assert "enabled_tier" in all_flags["affect.analyze"]

    def test_global_disabled(self):
        """Test global disable returns default tier."""
        flags = FeatureFlags()
        flags._config.global_enabled = False
        flags._config.default_tier = MLTier.DISABLED

        tier = flags.get_tier("affect.analyze")
        assert tier == MLTier.DISABLED

    @pytest.mark.asyncio
    async def test_load_config_missing_file(self):
        """Test load_config handles missing file gracefully."""
        flags = FeatureFlags()
        await flags.load_config("/nonexistent/path/feature_flags.yaml")
        assert flags._loaded is True


class TestFeatureFlagsMetrics:
    """Tests for metrics collection."""

    def test_metrics_advanced_calls(self):
        """Test metrics track advanced tier calls."""
        flags = FeatureFlags()
        initial = flags._metrics["affect.analyze"]["advanced_calls"]

        # Force 100% rollout
        flags._flags["affect.analyze"].rollout_percentage = 100.0
        flags.get_tier("affect.analyze")

        assert flags._metrics["affect.analyze"]["advanced_calls"] == initial + 1

    def test_metrics_fallback_calls(self):
        """Test metrics track fallback tier calls."""
        flags = FeatureFlags()
        initial = flags._metrics["affect.analyze"]["fallback_calls"]

        # Force 0% rollout
        flags._flags["affect.analyze"].rollout_percentage = 0.0
        flags.get_tier("affect.analyze")

        assert flags._metrics["affect.analyze"]["fallback_calls"] == initial + 1


class TestFeatureFlagsThreadSafety:
    """Tests for thread-safety."""

    def test_concurrent_get_tier(self):
        """Test concurrent get_tier calls are safe."""
        flags = FeatureFlags()

        results = []

        def get_tier_thread():
            for _ in range(100):
                tier = flags.get_tier("affect.analyze")
                results.append(tier)

        import threading

        threads = [threading.Thread(target=get_tier_thread) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All results should be valid tiers
        assert len(results) == 500
        assert all(isinstance(r, MLTier) for r in results)


class TestGlobalFeatureFlags:
    """Tests for global feature flags functions."""

    def test_get_feature_flags_singleton(self):
        """Test get_feature_flags returns singleton."""
        import k0.config.feature_flags as module

        module._feature_flags = None

        flags1 = get_feature_flags()
        flags2 = get_feature_flags()

        assert flags1 is flags2

    @pytest.mark.asyncio
    async def test_init_feature_flags(self):
        """Test init_feature_flags creates new instance."""
        import k0.config.feature_flags as module

        module._feature_flags = None

        flags = await init_feature_flags()
        assert flags is not None
        assert isinstance(flags, FeatureFlags)


class TestWithMLTierDecorator:
    """Tests for with_ml_tier decorator."""

    @pytest.mark.asyncio
    async def test_decorator_injects_tier(self):
        """Test decorator injects tier into function."""
        import k0.config.feature_flags as module

        module._feature_flags = None
        flags = await init_feature_flags()
        flags.set_tier("test.module", MLTier.TRANSFORMER_SMALL, 100.0)

        received_tier = None

        @with_ml_tier("test.module")
        async def test_func(text: str, tier: MLTier = None):
            nonlocal received_tier
            received_tier = tier
            return {"result": text}

        await test_func("hello")
        assert received_tier == MLTier.TRANSFORMER_SMALL

    @pytest.mark.asyncio
    async def test_decorator_records_success(self):
        """Test decorator records success on completion."""
        import k0.config.feature_flags as module

        module._feature_flags = None
        flags = await init_feature_flags()

        # Create the flag first, then set failure count
        flags.set_tier("test.success", MLTier.SPACY_LARGE, 100.0)
        flags._flags["test.success"].failure_count = 2

        @with_ml_tier("test.success")
        async def test_func(tier: MLTier = None):
            return "ok"

        await test_func()

        # Failure count should have decremented
        assert flags._flags["test.success"].failure_count < 2

    @pytest.mark.asyncio
    async def test_decorator_records_failure(self):
        """Test decorator records failure on exception."""
        import k0.config.feature_flags as module

        module._feature_flags = None
        flags = await init_feature_flags()
        flags.set_tier("test.failure", MLTier.SPACY_LARGE, 100.0)

        initial_failures = flags._flags["test.failure"].failure_count

        @with_ml_tier("test.failure")
        async def test_func(tier: MLTier = None):
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            await test_func()

        # Failure count should have incremented
        assert flags._flags["test.failure"].failure_count == initial_failures + 1
