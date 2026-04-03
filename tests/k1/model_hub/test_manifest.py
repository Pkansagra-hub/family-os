"""M1 Foundation -- Test Manifest Schema [F03].

Tests all manifest dataclasses, validation, and YAML loading.

NO MOCKS.  Pure data structure tests + file-based load_manifest.
"""

from __future__ import annotations

import dataclasses
import tempfile
from pathlib import Path

import pytest
import yaml

from k1.model_hub.manifest import (
    AuthConfig,
    CircuitBreakerConfig,
    ModelSpec,
    PlacementConfig,
    ProviderManifest,
    RateLimitConfig,
    load_manifest,
)
from k1.model_hub.types import CapabilityType, ModelTier, PlacementType

# =========================================================================
# AuthConfig
# =========================================================================


class TestAuthConfig:
    def test_defaults(self) -> None:
        a = AuthConfig()
        assert a.type == "bearer"
        assert a.credential_key == ""
        assert a.header_name is None

    def test_frozen(self) -> None:
        a = AuthConfig()
        with pytest.raises(dataclasses.FrozenInstanceError):
            a.type = "x"  # type: ignore[misc]

    def test_invalid_type_rejected(self) -> None:
        with pytest.raises(ValueError, match="AuthConfig.type must be"):
            AuthConfig(type="oauth")

    def test_valid_types(self) -> None:
        for t in ("bearer", "api_key_header", "none"):
            a = AuthConfig(type=t)
            assert a.type == t


# =========================================================================
# CircuitBreakerConfig
# =========================================================================


class TestCircuitBreakerConfig:
    def test_defaults(self) -> None:
        c = CircuitBreakerConfig()
        assert c.failure_threshold == 3
        assert c.failure_window_s == 60
        assert c.cooldown_s == 30

    def test_zero_threshold_rejected(self) -> None:
        with pytest.raises(ValueError, match="failure_threshold must be > 0"):
            CircuitBreakerConfig(failure_threshold=0)

    def test_zero_window_rejected(self) -> None:
        with pytest.raises(ValueError, match="failure_window_s must be > 0"):
            CircuitBreakerConfig(failure_window_s=0)

    def test_zero_cooldown_rejected(self) -> None:
        with pytest.raises(ValueError, match="cooldown_s must be > 0"):
            CircuitBreakerConfig(cooldown_s=0)


# =========================================================================
# RateLimitConfig
# =========================================================================


class TestRateLimitConfig:
    def test_defaults(self) -> None:
        r = RateLimitConfig()
        assert r.rpm == 60
        assert r.tpm == 100000
        assert r.headroom_pct == 0.80

    def test_zero_rpm_rejected(self) -> None:
        with pytest.raises(ValueError, match="rpm must be > 0"):
            RateLimitConfig(rpm=0)

    def test_zero_tpm_rejected(self) -> None:
        with pytest.raises(ValueError, match="tpm must be > 0"):
            RateLimitConfig(tpm=0)

    def test_headroom_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="headroom_pct must be in"):
            RateLimitConfig(headroom_pct=0.0)


# =========================================================================
# ModelSpec
# =========================================================================


class TestModelSpec:
    def test_construction(self) -> None:
        m = ModelSpec(id="gpt-4o")
        assert m.id == "gpt-4o"
        assert m.tier == ModelTier.STANDARD
        assert m.max_context == 128000

    def test_empty_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="id must be non-empty"):
            ModelSpec(id="")

    def test_negative_input_cost_rejected(self) -> None:
        with pytest.raises(ValueError, match="cost_per_1m_input must be >= 0"):
            ModelSpec(id="m", cost_per_1m_input=-1)

    def test_negative_output_cost_rejected(self) -> None:
        with pytest.raises(ValueError, match="cost_per_1m_output must be >= 0"):
            ModelSpec(id="m", cost_per_1m_output=-1)

    def test_zero_context_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_context must be > 0"):
            ModelSpec(id="m", max_context=0)

    def test_frozen(self) -> None:
        m = ModelSpec(id="m")
        with pytest.raises(dataclasses.FrozenInstanceError):
            m.id = "x"  # type: ignore[misc]


# =========================================================================
# PlacementConfig
# =========================================================================


class TestPlacementConfig:
    def test_defaults(self) -> None:
        p = PlacementConfig()
        assert p.type == PlacementType.REMOTE
        assert p.device_requirements is None


# =========================================================================
# ProviderManifest
# =========================================================================


class TestProviderManifest:
    def test_construction(self) -> None:
        m = ProviderManifest(provider_id="openai")
        assert m.provider_id == "openai"
        assert m.models == []
        assert m.capabilities == []

    def test_empty_provider_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="provider_id must be non-empty"):
            ProviderManifest(provider_id="")

    def test_frozen(self) -> None:
        m = ProviderManifest(provider_id="openai")
        with pytest.raises(dataclasses.FrozenInstanceError):
            m.provider_id = "x"  # type: ignore[misc]


# =========================================================================
# load_manifest (YAML roundtrip)
# =========================================================================


class TestLoadManifest:
    def _write_yaml(self, data: dict) -> Path:
        """Write dict to a temp YAML file, return path."""
        tmp = tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w", encoding="utf-8")
        yaml.safe_dump(data, tmp)
        tmp.close()
        return Path(tmp.name)

    def test_minimal_manifest(self) -> None:
        path = self._write_yaml({"provider_id": "test"})
        m = load_manifest(path)
        assert m.provider_id == "test"
        assert m.models == []
        path.unlink()

    def test_full_manifest(self) -> None:
        data = {
            "provider_id": "openai",
            "display_name": "OpenAI",
            "plugin_class": "k1.model_hub.plugins.openai.OpenAIPlugin",
            "api_base": "https://api.openai.com/v1",
            "auth": {"type": "bearer", "credential_key": "OPENAI_API_KEY"},
            "capabilities": ["CHAT", "TOOL_CALL", "EMBED"],
            "models": [
                {
                    "id": "gpt-4o",
                    "capabilities": ["CHAT", "TOOL_CALL"],
                    "cost_per_1m_input": 2.5,
                    "cost_per_1m_output": 10.0,
                    "max_context": 128000,
                    "max_output": 16384,
                    "tier": "PREMIUM",
                }
            ],
            "circuit_breaker": {
                "failure_threshold": 5,
                "failure_window_s": 120,
                "cooldown_s": 60,
            },
            "rate_limits": {"rpm": 500, "tpm": 200000, "headroom_pct": 0.90},
            "placement": {"type": "remote"},
        }
        path = self._write_yaml(data)
        m = load_manifest(path)
        assert m.provider_id == "openai"
        assert m.display_name == "OpenAI"
        assert len(m.models) == 1
        assert m.models[0].id == "gpt-4o"
        assert m.models[0].tier == ModelTier.PREMIUM
        assert CapabilityType.CHAT in m.capabilities
        assert m.circuit_breaker.failure_threshold == 5
        assert m.rate_limits.rpm == 500
        path.unlink()

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_manifest("/nonexistent/path.yaml")

    def test_missing_provider_id(self) -> None:
        path = self._write_yaml({"display_name": "test"})
        with pytest.raises(ValueError, match="missing 'provider_id'"):
            load_manifest(path)
        path.unlink()
