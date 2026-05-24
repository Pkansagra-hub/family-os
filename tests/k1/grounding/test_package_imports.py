"""M0 import tests for k1.grounding."""

from __future__ import annotations

import dataclasses
import importlib

from k1.grounding import DeviceContextSnapshot, GroundingConfig, GroundingEnvelope


def test_grounding_package_imports() -> None:
    module = importlib.import_module("k1.grounding")
    assert "DeviceContextSnapshot" in module.__all__
    for name in module.__all__:
        assert getattr(module, name) is not None


def test_grounding_types_are_frozen_dataclasses() -> None:
    for cls in (DeviceContextSnapshot, GroundingEnvelope):
        assert dataclasses.is_dataclass(cls)
        assert cls.__dataclass_params__.frozen is True


def test_grounding_config_defaults_are_private_by_default() -> None:
    config = GroundingConfig()
    assert config.raw_spatial_allowed_by_default is False
    assert config.agent_lease_ttl_seconds == 900
