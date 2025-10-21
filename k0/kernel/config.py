"""Runtime configuration models and loader for the K0 kernel."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, ClassVar, Literal, Mapping, MutableMapping, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..config import KERNEL_CONFIG_PATH

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SSE_ACL_PATH = PACKAGE_ROOT / "sse" / "acl.yaml"

ENV_PREFIX = "K0_KERNEL_"
CONFIG_ENV_VAR = f"{ENV_PREFIX}CONFIG_FILE"


class TelemetrySettings(BaseModel):
    """Destination and feature flags for telemetry exporters."""

    model_config = ConfigDict(extra="forbid")

    otlp_endpoint: str | None = Field(
        default=None,
        description="Endpoint for OTLP trace export. When omitted, spans emit to console only.",
    )
    otlp_headers: dict[str, str] = Field(
        default_factory=dict,
        description="Optional HTTP headers attached to OTLP export requests.",
    )
    trace_sample_ratio: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Ratio (0-1] controlling probabilistic span sampling.",
    )
    prometheus_enabled: bool = Field(
        default=True,
        description="Expose Prometheus metrics endpoint when true.",
    )
    metrics_namespace: str = Field(
        default="k0_kernel",
        min_length=1,
        description="Namespace prefix applied to emitted Prometheus metrics.",
    )
    log_sensitive_keys: list[str] = Field(
        default_factory=list,
        description=(
            "Additional field names treated as sensitive for structured logging "
            "redaction."
        ),
    )
    log_mask: str = Field(
        default="[REDACTED]",
        min_length=1,
        description="Mask token applied to redacted structured log fields.",
    )

    @field_validator("otlp_endpoint")
    @classmethod
    def _normalize_otlp_endpoint(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("metrics_namespace")
    @classmethod
    def _normalize_namespace(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            msg = "metrics_namespace must not be empty"
            raise ValueError(msg)
        return normalized

    @field_validator("log_sensitive_keys")
    @classmethod
    def _normalize_log_sensitive_keys(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for key in value:
            candidate = str(key).strip().lower()
            if candidate:
                normalized.append(candidate)
        return normalized

    @field_validator("log_mask")
    @classmethod
    def _normalize_log_mask(cls, value: str) -> str:
        masked = str(value).strip()
        if not masked:
            msg = "log_mask must not be empty"
            raise ValueError(msg)
        return masked


class QoSSettings(BaseModel):
    """Scheduler defaults that dictate fairness and budget tighteners."""

    model_config = ConfigDict(extra="forbid")

    fanout_max: int = Field(
        default=3,
        ge=1,
        le=16,
        description="Hard cap on the number of stores fanned out per query.",
    )
    top_k_max: int = Field(
        default=8,
        ge=1,
        le=128,
        description="Maximum top-k aggregation window allowed per recall.",
    )
    scheduler_profile: str = Field(
        default="balanced",
        description="Logical scheduler profile drawn from qos/defaults.yaml.",
        min_length=1,
    )

    @field_validator("scheduler_profile")
    @classmethod
    def _strip_profile(cls, value: str) -> str:
        value = value.strip()
        if not value:
            msg = "scheduler_profile must not be empty"
            raise ValueError(msg)
        return value


class RetentionPolicy(BaseModel):
    """Retention thresholds applied to WAL and snapshot policies."""

    model_config = ConfigDict(extra="forbid")

    wal_days: int = Field(
        default=7,
        ge=1,
        le=365,
        description="Number of days to retain WAL segments before pruning.",
    )
    wal_max_events: int = Field(
        default=10_000_000,
        ge=1,
        description="Maximum number of events retained for the scope.",
    )


class RetentionSettings(BaseModel):
    """Grouped retention configuration for default/topic/space scopes."""

    model_config = ConfigDict(extra="forbid")

    default: RetentionPolicy = Field(default_factory=RetentionPolicy)
    topics: dict[str, RetentionPolicy] = Field(default_factory=dict)
    spaces: dict[str, RetentionPolicy] = Field(default_factory=dict)


class DatabaseSettings(BaseModel):
    """Settings governing the kernel's ACID cohort datastore."""

    model_config = ConfigDict(extra="forbid")

    path: Path = Field(
        default=Path("k0_runtime.sqlite3"),
        description="Filesystem path to the kernel SQLite database.",
    )
    fsync_mode: Literal["strict", "wal_only", "disabled"] = Field(
        default="wal_only",
        description=(
            "Durability policy used when flushing the SQLite WAL. `strict` fsyncs "
            "database, WAL, and SHM files; `wal_only` skips the main database file; "
            "`disabled` bypasses fsync entirely (unsafe for production)."
        ),
    )

    @field_validator("fsync_mode")
    @classmethod
    def _normalize_fsync_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        allowed = {"strict", "wal_only", "disabled"}
        if normalized not in allowed:
            options = ", ".join(sorted(allowed))
            msg = f"fsync_mode must be one of: {options}"
            raise ValueError(msg)
        return normalized


class ServerSettings(BaseModel):
    """Network-facing server configuration for the kernel runtime."""

    model_config = ConfigDict(extra="forbid")

    ALLOWED_LOG_LEVELS: ClassVar[set[str]] = {
        "critical",
        "error",
        "warning",
        "info",
        "debug",
        "trace",
    }

    host: str = Field(
        default="0.0.0.0",
        min_length=1,
        description="Network interface bind address for the HTTP server.",
    )
    port: int = Field(
        default=8080,
        ge=1,
        le=65_535,
        description="TCP port exposed by the HTTP server.",
    )
    log_level: str = Field(
        default="info",
        description="Log level propagated to Uvicorn.",
    )
    timeout_graceful_shutdown: float = Field(
        default=30.0,
        ge=0.0,
        le=300.0,
        description=(
            "Seconds to wait for in-flight requests to complete before the server "
            "forces shutdown."
        ),
    )

    @field_validator("host")
    @classmethod
    def _normalize_host(cls, value: str) -> str:
        value = value.strip()
        if not value:
            msg = "host must not be empty"
            raise ValueError(msg)
        return value

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip().lower()
        if normalized not in cls.ALLOWED_LOG_LEVELS:
            allowed = ", ".join(sorted(cls.ALLOWED_LOG_LEVELS))
            msg = f"log_level must be one of: {allowed}"
            raise ValueError(msg)
        return normalized


class SecuritySettings(BaseModel):
    """Security policies for device key rotation and verification."""

    model_config = ConfigDict(extra="forbid")

    key_rotation_grace_window_hours: int = Field(
        default=24,
        ge=1,
        le=168,  # Max 7 days
        description=(
            "Default grace period (in hours) during which a ROTATING key remains "
            "valid for signature verification after a new key is activated."
        ),
    )
    key_rotation_max_grace_hours: int = Field(
        default=168,
        ge=1,
        le=720,  # Max 30 days
        description=(
            "Maximum grace period (in hours) that operators can set when "
            "overriding the default rotation window."
        ),
    )


class ChaosSettings(BaseModel):
    """Chaos engineering toggles for controlled fault injection.

    CRITICAL: All chaos injection uses real errors/behaviors, never simulation code.
    - WAL fsync failures raise OSError(errno.EIO)
    - Scheduler starvation actually reduces port limits
    - Network latency uses real time.sleep() delays (acceptable for chaos)
    - Telemetry outage conditionally skips metric emission
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        default=False,
        description="Master toggle enabling chaos engineering features.",
    )
    wal_fsync_fail_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Probability (0.0-1.0) of WAL fsync failure injection (OSError).",
    )
    scheduler_starvation_multiplier: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description=(
            "Multiplier applied to scheduler port limits "
            "(e.g., 0.3 = 30% capacity, 70% starvation)."
        ),
    )
    network_latency_ms: int = Field(
        default=0,
        ge=0,
        description="Network latency injection in milliseconds (0=disabled).",
    )
    telemetry_outage_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Probability (0.0-1.0) of dropping telemetry emissions.",
    )
    random_seed: int | None = Field(
        default=None,
        description="Random seed for deterministic chaos behavior in testing.",
    )


class BusMiddlewareSettings(BaseModel):
    """Feature flags controlling bus middleware chain composition."""

    model_config = ConfigDict(extra="forbid")

    timestamps_enabled: bool = Field(
        default=True,
        description="Enable middleware that records wall-clock and monotonic timestamps.",
    )
    tracing_enabled: bool = Field(
        default=True,
        description="Enable middleware that propagates cognitive trace identifiers and spans.",
    )
    metrics_enabled: bool = Field(
        default=True,
        description="Enable middleware that emits dispatch latency metrics.",
    )


class BusSettings(BaseModel):
    """Aggregate configuration for post-commit bus dispatch."""

    model_config = ConfigDict(extra="forbid")

    middleware: BusMiddlewareSettings = Field(default_factory=BusMiddlewareSettings)


class KernelSettings(BaseModel):
    """Aggregate settings consumed by the FastAPI app factory."""

    model_config = ConfigDict(extra="forbid")

    version: str = Field(default="0.0.0-dev", description="Kernel semantic version.")
    environment: str = Field(
        default="development",
        description="Deployment environment identifier (dev/staging/prod).",
        min_length=1,
    )
    config_file: Path | None = Field(
        default=None,
        description="Resolved path to the YAML configuration file, if any.",
    )
    telemetry: TelemetrySettings = Field(default_factory=TelemetrySettings)
    qos: QoSSettings = Field(default_factory=QoSSettings)
    retention: RetentionSettings = Field(default_factory=RetentionSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    security: SecuritySettings = Field(
        default_factory=SecuritySettings,
        description="Security policies for key rotation and verification.",
    )
    chaos: ChaosSettings = Field(
        default_factory=ChaosSettings,
        description="Chaos engineering toggles for fault injection (disabled by default).",
    )
    bus: BusSettings = Field(
        default_factory=BusSettings,
        description="Configuration controlling bus dispatch middleware and behavior.",
    )
    allowed_origins: list[str] | None = Field(
        default=None,
        description="Optional list of CORS origins exposed via the runtime.",
    )
    sse_acl_path: Path = Field(
        default=DEFAULT_SSE_ACL_PATH,
        description="Filesystem path to the SSE role ACL configuration.",
    )

    @field_validator("environment")
    @classmethod
    def _normalize_environment(cls, value: str) -> str:
        value = value.strip()
        if not value:
            msg = "environment must not be empty"
            raise ValueError(msg)
        return value

    @classmethod
    def from_yaml(cls, path: Path | str) -> "KernelSettings":
        """Load settings from a YAML file."""

        return cls.load(config_path=Path(path))

    @classmethod
    def load(
        cls,
        *,
        config_path: Path | str | None = None,
        env: Mapping[str, str] | None = None,
        overrides: Mapping[str, Any] | None = None,
    ) -> "KernelSettings":
        """Resolve settings from YAML, environment variables, and overrides.

        The resolution order is: YAML file (defaulting to ``config/kernel.yaml``),
        environment variables prefixed with ``K0_KERNEL_``, and finally explicit
        overrides supplied programmatically (e.g. CLI flags).
        """

        env_map = env or os.environ
        resolved_path = _resolve_config_path(config_path, env_map)

        aggregate: dict[str, Any] = {}
        if resolved_path is not None:
            aggregate = _deep_merge(aggregate, _read_yaml(resolved_path))

        env_overrides = _extract_env_overrides(env_map)
        if env_overrides:
            aggregate = _deep_merge(aggregate, env_overrides)

        if overrides:
            aggregate = _deep_merge(aggregate, overrides)

        if resolved_path is not None:
            aggregate.setdefault("config_file", Path(resolved_path))

        _normalize_legacy_keys(aggregate)

        return cls(**aggregate)

    @classmethod
    def default(cls) -> "KernelSettings":
        """Return the canonical default settings instance."""

        return cls.load()


def _resolve_config_path(
    config_path: Path | str | None,
    env: Mapping[str, str],
) -> Path | None:
    """Determine which configuration file should be used."""

    if config_path is not None:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")
        return path

    if CONFIG_ENV_VAR in env:
        env_path = Path(env[CONFIG_ENV_VAR])
        if not env_path.exists():
            raise FileNotFoundError(
                f"Configuration file from {CONFIG_ENV_VAR} not found: {env_path}"
            )
        return env_path

    if KERNEL_CONFIG_PATH.exists():
        return KERNEL_CONFIG_PATH

    return None


def _deep_merge(base: Mapping[str, Any], update: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively merge two mappings, returning a new dictionary."""

    merged: dict[str, Any] = dict(base)
    for key, value in update.items():
        if (
            key in merged
            and isinstance(merged[key], Mapping)
            and isinstance(value, Mapping)
        ):
            merged[key] = _deep_merge(
                cast(Mapping[str, Any], merged[key]),
                cast(Mapping[str, Any], value),
            )
        else:
            merged[key] = value
    return merged


def _normalize_legacy_keys(payload: MutableMapping[str, Any]) -> None:
    """Coerce legacy flat keys into their modern structured equivalents."""

    qos_profile = payload.pop("qos_profile", None)
    if qos_profile is not None:
        existing_qos = payload.get("qos")
        if isinstance(existing_qos, Mapping):
            qos_settings: dict[str, Any] = dict(cast(Mapping[str, Any], existing_qos))
        else:
            qos_settings = {}
        qos_settings.setdefault("scheduler_profile", qos_profile)
        payload["qos"] = qos_settings


def _extract_env_overrides(env: Mapping[str, str]) -> dict[str, Any]:
    """Translate ``K0_KERNEL_*`` environment variables into overrides."""

    overrides: dict[str, Any] = {}
    for key, raw_value in env.items():
        if not key.startswith(ENV_PREFIX) or key == CONFIG_ENV_VAR:
            continue

        suffix = key[len(ENV_PREFIX) :]
        parts = [part.strip().lower() for part in suffix.split("__") if part.strip()]
        if not parts:
            continue

        _assign_nested(overrides, parts, _coerce_env_value(raw_value))
    return overrides


def _assign_nested(
    target: MutableMapping[str, Any], path: list[str], value: Any
) -> None:
    """Assign a value to a nested mapping given a sequence of keys."""

    current: MutableMapping[str, Any] = target
    for part in path[:-1]:
        existing = current.get(part)
        if existing is None or not isinstance(existing, MutableMapping):
            next_level: dict[str, Any] = {}
            current[part] = next_level
            current = next_level
        else:
            current = cast(MutableMapping[str, Any], existing)
    current[path[-1]] = value


def _coerce_env_value(raw: str) -> Any:
    """Best-effort coercion of environment variable overrides."""

    stripped = raw.strip()
    if not stripped:
        return ""

    # Comma-delimited lists without explicit JSON/YAML brackets.
    if "," in stripped and not stripped.startswith(("[", "{", "'", '"')):
        return [item.strip() for item in stripped.split(",") if item.strip()]

    try:
        value = yaml.safe_load(stripped)
    except (yaml.YAMLError, ValueError):
        return stripped

    return stripped if value is None else value


def _read_yaml(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        raw_content: Any = yaml.safe_load(handle) or {}
    if not isinstance(raw_content, Mapping):
        raise ValueError(
            f"Expected mapping at root of {path}, got {type(raw_content)!r}"
        )
    mapping_content = cast(Mapping[Any, Any], raw_content)
    raw_dict: dict[str, Any] = {}
    bad_keys: set[str] = set()
    for key, value in mapping_content.items():
        if isinstance(key, str):
            raw_dict[key] = value
        else:
            bad_keys.add(type(key).__name__)
    if bad_keys:
        raise ValueError(
            (
                "Configuration keys must be strings; found incompatible types: "
                + ", ".join(sorted(bad_keys))
                + f" in {path}"
            )
        )
    typed_mapping = cast(Mapping[str, Any], raw_dict)
    return dict(typed_mapping)
