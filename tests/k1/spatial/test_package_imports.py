"""M0 import tests for k1.spatial."""

from __future__ import annotations

import dataclasses
import importlib

from k1.spatial import (
    LocationFix,
    PlaceRef,
    SpatialConfig,
    SpatialContext,
    SpatialProjection,
)


def test_spatial_package_imports() -> None:
    module = importlib.import_module("k1.spatial")
    assert "SpatialConfig" in module.__all__
    for name in module.__all__:
        assert getattr(module, name) is not None


def test_spatial_types_are_frozen_dataclasses() -> None:
    for cls in (LocationFix, PlaceRef, SpatialContext, SpatialProjection):
        assert dataclasses.is_dataclass(cls)
        assert cls.__dataclass_params__.frozen is True


def test_spatial_config_defaults_are_private_by_default() -> None:
    config = SpatialConfig()
    assert config.raw_location_allowed_by_default is False
    assert config.default_precision == "semantic"
