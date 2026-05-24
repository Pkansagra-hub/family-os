"""M0 tests for temporal/spatial/grounding KernelConfig flags."""

from __future__ import annotations

import logging

from k1.concierge.config.kernel import KernelConfig
from k1.kernel.service import KernelService
from ui.web.coordinator import _env_flag


def test_kernel_config_grounding_flags_default_on_after_m3_exit() -> None:
    config = KernelConfig()
    assert config.enable_temporal is True
    assert config.enable_grounding is True
    assert config.enable_spatial is True


def test_kernel_config_grounding_flags_can_be_disabled_for_isolated_runs() -> None:
    config = KernelConfig(enable_temporal=False, enable_grounding=False, enable_spatial=False)
    assert config.enable_temporal is False
    assert config.enable_grounding is False
    assert config.enable_spatial is False


def test_env_flag_binding(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("K1_ENABLE_TEMPORAL", "1")
    monkeypatch.setenv("K1_ENABLE_GROUNDING", "true")
    monkeypatch.setenv("K1_ENABLE_SPATIAL", "on")
    assert _env_flag("K1_ENABLE_TEMPORAL") is True
    assert _env_flag("K1_ENABLE_GROUNDING") is True
    assert _env_flag("K1_ENABLE_SPATIAL") is True


def test_env_flag_default_and_false_values(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("K1_ENABLE_TEMPORAL", raising=False)
    monkeypatch.setenv("K1_ENABLE_GROUNDING", "0")
    assert _env_flag("K1_ENABLE_TEMPORAL") is False
    assert _env_flag("K1_ENABLE_TEMPORAL", default=True) is True
    assert _env_flag("K1_ENABLE_GROUNDING") is False


def test_kernel_service_logs_grounding_flags(caplog) -> None:  # type: ignore[no-untyped-def]
    service = KernelService(
        KernelConfig(enable_temporal=True, enable_grounding=False, enable_spatial=True)
    )
    with caplog.at_level(logging.INFO, logger="k1.kernel.service"):
        service._log_grounding_feature_flags()
    assert "temporal=True spatial=True grounding=False" in caplog.text
