"""Model Hub provider manifest schema [F03].

Parsed manifest YAML dataclasses for provider discovery and configuration.

Import graph (Layer 0 -- no internal deps)
------------------------------------------
k1.model_hub.manifest
  -> k1.model_hub.types  (CapabilityType, ModelTier, PlacementType)
  -> stdlib only

NEVER import from any service, port, adapter, or plugin module.

References
----------
- model_hub.mmd: PROVIDER_MANIFEST_SCHEMA section
- ADR-0001b: Model Hub Architecture
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from k1.model_hub.types import CapabilityType, ModelTier, PlacementType

# ===========================================================================
# Manifest Sub-Structures
# ===========================================================================


@dataclass(frozen=True)
class AuthConfig:
    """Provider authentication configuration.

    MH-02: credential_key references CredentialStore, NOT raw API key.
    """

    type: str = "bearer"
    credential_key: str = ""
    header_name: Optional[str] = None

    def __post_init__(self) -> None:
        if self.type not in ("bearer", "api_key_header", "none"):
            raise ValueError(f"AuthConfig.type must be bearer|api_key_header|none, got {self.type}")


@dataclass(frozen=True)
class CircuitBreakerConfig:
    """Per-provider circuit breaker configuration (MH-05)."""

    failure_threshold: int = 3
    failure_window_s: int = 60
    cooldown_s: int = 30

    def __post_init__(self) -> None:
        if self.failure_threshold <= 0:
            raise ValueError(
                f"CircuitBreakerConfig.failure_threshold must be > 0, "
                f"got {self.failure_threshold}"
            )
        if self.failure_window_s <= 0:
            raise ValueError(
                f"CircuitBreakerConfig.failure_window_s must be > 0, "
                f"got {self.failure_window_s}"
            )
        if self.cooldown_s <= 0:
            raise ValueError(f"CircuitBreakerConfig.cooldown_s must be > 0, got {self.cooldown_s}")


@dataclass(frozen=True)
class HealthCheckConfig:
    """Provider health check configuration (MH-14)."""

    endpoint: str = ""
    interval_s: int = 30
    timeout_s: int = 5


@dataclass(frozen=True)
class ConcurrencyConfig:
    """Provider concurrency limits."""

    max_concurrent: int = 10


@dataclass(frozen=True)
class RateLimitConfig:
    """Provider rate limit configuration (MH-12)."""

    rpm: int = 60
    tpm: int = 100000
    headroom_pct: float = 0.80

    def __post_init__(self) -> None:
        if self.rpm <= 0:
            raise ValueError(f"RateLimitConfig.rpm must be > 0, got {self.rpm}")
        if self.tpm <= 0:
            raise ValueError(f"RateLimitConfig.tpm must be > 0, got {self.tpm}")
        if not 0.0 < self.headroom_pct <= 1.0:
            raise ValueError(
                f"RateLimitConfig.headroom_pct must be in (0.0, 1.0], " f"got {self.headroom_pct}"
            )


@dataclass(frozen=True)
class PlacementConfig:
    """Provider placement configuration (MH-13, ADR-0027)."""

    type: PlacementType = PlacementType.REMOTE
    device_requirements: Optional[str] = None


# ===========================================================================
# Model Spec (per-model entry in manifest)
# ===========================================================================


@dataclass(frozen=True)
class ModelSpec:
    """Per-model specification from provider manifest."""

    id: str
    capabilities: List[CapabilityType] = field(default_factory=list)
    cost_per_1m_input: float = 0.0
    cost_per_1m_output: float = 0.0
    max_context: int = 128000
    max_output: Optional[int] = None
    supports_streaming: bool = True
    supports_parallel_tools: Optional[bool] = None
    embedding_dimensions: Optional[int] = None
    rate_limit_rpm: Optional[int] = None
    rate_limit_tpm: Optional[int] = None
    tier: ModelTier = ModelTier.STANDARD

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("ModelSpec.id must be non-empty")
        if self.cost_per_1m_input < 0:
            raise ValueError("ModelSpec.cost_per_1m_input must be >= 0")
        if self.cost_per_1m_output < 0:
            raise ValueError("ModelSpec.cost_per_1m_output must be >= 0")
        if self.max_context <= 0:
            raise ValueError("ModelSpec.max_context must be > 0")


# ===========================================================================
# Provider Manifest (top-level parsed YAML)
# ===========================================================================


@dataclass(frozen=True)
class ProviderManifest:
    """Parsed provider manifest (one per provider YAML file).

    MH-18: Manifest is SOLE source of truth for provider capabilities.
    """

    provider_id: str
    display_name: str = ""
    plugin_class: str = ""
    api_base: str = ""
    auth: AuthConfig = field(default_factory=AuthConfig)
    capabilities: List[CapabilityType] = field(default_factory=list)
    models: List[ModelSpec] = field(default_factory=list)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    health_check: HealthCheckConfig = field(default_factory=HealthCheckConfig)
    concurrency: ConcurrencyConfig = field(default_factory=ConcurrencyConfig)
    rate_limits: RateLimitConfig = field(default_factory=RateLimitConfig)
    placement: PlacementConfig = field(default_factory=PlacementConfig)

    def __post_init__(self) -> None:
        if not self.provider_id:
            raise ValueError("ProviderManifest.provider_id must be non-empty")


# ===========================================================================
# Manifest Loader
# ===========================================================================


def _parse_model_spec(data: Dict[str, Any]) -> ModelSpec:
    """Parse a single model entry from manifest YAML."""
    caps = [CapabilityType(c) for c in data.get("capabilities", [])]
    tier = ModelTier(data["tier"]) if "tier" in data else ModelTier.STANDARD
    return ModelSpec(
        id=data["id"],
        capabilities=caps,
        cost_per_1m_input=float(data.get("cost_per_1m_input", 0.0)),
        cost_per_1m_output=float(data.get("cost_per_1m_output", 0.0)),
        max_context=int(data.get("max_context", 128000)),
        max_output=int(data["max_output"]) if "max_output" in data else None,
        supports_streaming=bool(data.get("supports_streaming", True)),
        supports_parallel_tools=data.get("supports_parallel_tools"),
        embedding_dimensions=(
            int(data["embedding_dimensions"]) if "embedding_dimensions" in data else None
        ),
        rate_limit_rpm=(int(data["rate_limit_rpm"]) if "rate_limit_rpm" in data else None),
        rate_limit_tpm=(int(data["rate_limit_tpm"]) if "rate_limit_tpm" in data else None),
        tier=tier,
    )


def _parse_auth(data: Dict[str, Any]) -> AuthConfig:
    """Parse auth section from manifest YAML."""
    return AuthConfig(
        type=data.get("type", "bearer"),
        credential_key=data.get("credential_key", ""),
        header_name=data.get("header_name"),
    )


def _parse_circuit_breaker(data: Dict[str, Any]) -> CircuitBreakerConfig:
    """Parse circuit_breaker section."""
    return CircuitBreakerConfig(
        failure_threshold=int(data.get("failure_threshold", 3)),
        failure_window_s=int(data.get("failure_window_s", 60)),
        cooldown_s=int(data.get("cooldown_s", 30)),
    )


def _parse_placement(data: Dict[str, Any]) -> PlacementConfig:
    """Parse placement section."""
    return PlacementConfig(
        type=PlacementType(data.get("type", "remote")),
        device_requirements=data.get("device_requirements"),
    )


def load_manifest(path: str | Path) -> ProviderManifest:
    """Load and parse a provider manifest YAML file.

    Raises:
        FileNotFoundError: if path does not exist.
        ValueError: if YAML is invalid or required fields missing.
        yaml.YAMLError: if YAML parsing fails.
    """
    manifest_path = Path(path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    with open(manifest_path, encoding="utf-8") as f:
        data: Dict[str, Any] = yaml.safe_load(f) or {}

    if "provider_id" not in data:
        raise ValueError(f"Manifest missing 'provider_id': {manifest_path}")

    capabilities = [CapabilityType(c) for c in data.get("capabilities", [])]
    models = [_parse_model_spec(m) for m in data.get("models", [])]
    auth = _parse_auth(data.get("auth", {}))
    cb = _parse_circuit_breaker(data.get("circuit_breaker", {}))
    health = HealthCheckConfig(
        endpoint=data.get("health_check", {}).get("endpoint", ""),
        interval_s=int(data.get("health_check", {}).get("interval_s", 30)),
        timeout_s=int(data.get("health_check", {}).get("timeout_s", 5)),
    )
    concurrency = ConcurrencyConfig(
        max_concurrent=int(data.get("concurrency", {}).get("max_concurrent", 10)),
    )
    rate_limits_data = data.get("rate_limits", {})
    rate_limits = RateLimitConfig(
        rpm=int(rate_limits_data.get("rpm", 60)),
        tpm=int(rate_limits_data.get("tpm", 100000)),
        headroom_pct=float(rate_limits_data.get("headroom_pct", 0.80)),
    )
    placement = _parse_placement(data.get("placement", {}))

    return ProviderManifest(
        provider_id=data["provider_id"],
        display_name=data.get("display_name", ""),
        plugin_class=data.get("plugin_class", ""),
        api_base=data.get("api_base", ""),
        auth=auth,
        capabilities=capabilities,
        models=models,
        circuit_breaker=cb,
        health_check=health,
        concurrency=concurrency,
        rate_limits=rate_limits,
        placement=placement,
    )


__all__ = [
    "AuthConfig",
    "CircuitBreakerConfig",
    "ConcurrencyConfig",
    "HealthCheckConfig",
    "ModelSpec",
    "PlacementConfig",
    "ProviderManifest",
    "RateLimitConfig",
    "load_manifest",
]
