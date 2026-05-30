"""M0 import tests for k1.temporal."""

from __future__ import annotations

import dataclasses
import importlib

from k1.temporal import (
    TemporalAnchor,
    TemporalConfig,
    TemporalProjection,
    TemporalWindow,
)


def test_temporal_package_imports() -> None:
    module = importlib.import_module("k1.temporal")
    assert "TemporalConfig" in module.__all__
    for name in module.__all__:
        assert getattr(module, name) is not None


def test_temporal_types_are_frozen_dataclasses() -> None:
    for cls in (TemporalAnchor, TemporalWindow, TemporalProjection):
        assert dataclasses.is_dataclass(cls)
        assert cls.__dataclass_params__.frozen is True


def test_temporal_config_defaults_are_migration_safe() -> None:
    config = TemporalConfig()
    assert config.default_timezone == "UTC"
    assert config.fallback_timezone_sources == ("device", "spatial", "persona", "utc")
