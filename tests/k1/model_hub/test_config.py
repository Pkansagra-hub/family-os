"""M1 Foundation -- Test ModelHubConfig [F02].

Tests construction, defaults, validation, from_dict, and frozen immutability.

NO MOCKS.  Pure data structure tests.
"""

from __future__ import annotations

import dataclasses

import pytest

from k1.model_hub.config import ModelHubConfig


class TestModelHubConfigDefaults:
    def test_defaults(self) -> None:
        c = ModelHubConfig()
        assert c.daily_budget_usd == 5.0
        assert c.monthly_budget_usd == 100.0
        assert c.max_concurrent_requests == 50
        assert c.cache_max_entries == 1000
        assert c.cache_ttl_s == 300
        assert c.realtime_timeout_ms == 10000
        assert c.interactive_timeout_ms == 30000
        assert c.background_timeout_ms == 60000
        assert c.rate_limit_headroom_pct == 0.80
        assert c.health_check_interval_s == 30
        assert c.manifest_dir == "k1/config/providers"
        assert c.shutdown_grace_period_ms == 10000

    def test_frozen(self) -> None:
        c = ModelHubConfig()
        with pytest.raises(dataclasses.FrozenInstanceError):
            c.daily_budget_usd = 99.0  # type: ignore[misc]


class TestModelHubConfigValidation:
    def test_daily_budget_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="daily_budget_usd must be > 0"):
            ModelHubConfig(daily_budget_usd=0)

    def test_daily_budget_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="daily_budget_usd must be > 0"):
            ModelHubConfig(daily_budget_usd=-1)

    def test_monthly_budget_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="monthly_budget_usd must be > 0"):
            ModelHubConfig(monthly_budget_usd=0)

    def test_max_concurrent_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_concurrent_requests must be > 0"):
            ModelHubConfig(max_concurrent_requests=0)

    def test_cache_max_entries_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="cache_max_entries must be > 0"):
            ModelHubConfig(cache_max_entries=0)

    def test_cache_ttl_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="cache_ttl_s must be > 0"):
            ModelHubConfig(cache_ttl_s=0)

    def test_realtime_timeout_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="realtime_timeout_ms must be > 0"):
            ModelHubConfig(realtime_timeout_ms=0)

    def test_interactive_timeout_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="interactive_timeout_ms must be > 0"):
            ModelHubConfig(interactive_timeout_ms=0)

    def test_background_timeout_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="background_timeout_ms must be > 0"):
            ModelHubConfig(background_timeout_ms=0)

    def test_headroom_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="rate_limit_headroom_pct must be in"):
            ModelHubConfig(rate_limit_headroom_pct=0.0)

    def test_headroom_over_one_rejected(self) -> None:
        with pytest.raises(ValueError, match="rate_limit_headroom_pct must be in"):
            ModelHubConfig(rate_limit_headroom_pct=1.1)

    def test_headroom_one_accepted(self) -> None:
        c = ModelHubConfig(rate_limit_headroom_pct=1.0)
        assert c.rate_limit_headroom_pct == 1.0

    def test_health_check_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="health_check_interval_s must be > 0"):
            ModelHubConfig(health_check_interval_s=0)

    def test_shutdown_grace_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="shutdown_grace_period_ms must be > 0"):
            ModelHubConfig(shutdown_grace_period_ms=0)


class TestModelHubConfigFromDict:
    def test_roundtrip(self) -> None:
        c = ModelHubConfig()
        d = dataclasses.asdict(c)
        c2 = ModelHubConfig.from_dict(d)
        assert c == c2

    def test_custom_values(self) -> None:
        c = ModelHubConfig.from_dict({"daily_budget_usd": 10.0, "cache_ttl_s": 600})
        assert c.daily_budget_usd == 10.0
        assert c.cache_ttl_s == 600

    def test_unknown_key_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unknown config keys"):
            ModelHubConfig.from_dict({"unknown_key": 42})

    def test_empty_dict(self) -> None:
        c = ModelHubConfig.from_dict({})
        assert c == ModelHubConfig()
