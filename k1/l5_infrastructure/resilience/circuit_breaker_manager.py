"""
Resilience - Circuit Breaker Manager (3-State FSM Registry)

Purpose: Manages multiple circuit breaker instances with per-service configuration
Location: k1/l5_infrastructure/resilience/circuit_breaker_manager.py
Performance: <10ms circuit breaker lookup, <100ms config reload

Primary ADRs:
- ADR-0009: Circuit Breaker Pattern (3-state FSM, Nygard 2007)
- ADR-0009a: Circuit Breaker FSM Implementation
- ADR-0009b: Per-Service Circuit Configuration
- ADR-0009c: Circuit Breaker Metrics & Observability

Features: Circuit registry, config management, hot reload, fallback strategies

Last Updated: January 2025
ADR Reference: docs/architecture/decisions/0009-circuit-breaker.md
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from k1.l5_infrastructure.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
)

try:  # pragma: no cover - structlog may be optional in slim environments
    import structlog  # type: ignore

    logger = structlog.get_logger(__name__)  # type: ignore
except ImportError:  # pragma: no cover - fallback shim
    import logging

    class _StructLogShim:
        """Minimal shim replicating structlog's API with stdlib logging."""

        def __init__(self, base: logging.Logger) -> None:
            self._base = base

        def _log(self, level: int, event: str, **kwargs: object) -> None:
            self._base.log(level, event, extra=kwargs)

        def debug(self, event: str, **kwargs: object) -> None:
            self._log(logging.DEBUG, event, **kwargs)

        def info(self, event: str, **kwargs: object) -> None:
            self._log(logging.INFO, event, **kwargs)

        def warning(self, event: str, **kwargs: object) -> None:
            self._log(logging.WARNING, event, **kwargs)

        def error(self, event: str, **kwargs: object) -> None:
            self._log(logging.ERROR, event, **kwargs)

        def exception(self, event: str, **kwargs: object) -> None:
            self._log(logging.ERROR, event, exc_info=True, **kwargs)

    logger = _StructLogShim(logging.getLogger(__name__))


@dataclass(slots=True)
class _CacheEntry:
    """In-memory cache entry with TTL for cached_result fallback strategy."""

    value: Any
    expires_at: float  # Monotonic timestamp


class _FallbackCache:
    """
    Simple in-memory cache with TTL for circuit breaker fallback results.

    NOT production-ready:
    - No LRU eviction (unbounded growth)
    - No persistence across restarts
    - No distributed cache support

    For production, integrate with Redis/Memcached via k1.storage layer.
    """

    def __init__(self) -> None:
        self._cache: Dict[str, _CacheEntry] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired."""
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None

            now = time.monotonic()
            if now >= entry.expires_at:
                del self._cache[key]
                return None

            return entry.value

    async def set(self, key: str, value: Any, ttl_ms: int) -> None:
        """Store value with TTL in milliseconds."""
        expires_at = time.monotonic() + (ttl_ms / 1000.0)
        async with self._lock:
            self._cache[key] = _CacheEntry(value=value, expires_at=expires_at)


@dataclass(slots=True)
class ServiceCircuitBreakerConfig:
    """Circuit breaker configuration per ADR-0009b."""

    failure_threshold: int
    timeout_duration_ms: int
    success_threshold: int
    slow_call_threshold_ms: int
    time_window_ms: int
    fallback_strategy: str
    enabled: bool
    # Optional fields
    alternate_service: Optional[str] = None
    cache_ttl_ms: Optional[int] = None
    default_value: Optional[Any] = None  # For default_value strategy
    alternate_callable: Optional[Callable[[], Any]] = (
        None  # For alternate_model strategy
    )


class ConfigManager:
    """Manages circuit breaker configurations with hot reload per ADR-0009b."""

    def __init__(self, config_path: str = "k1/config/circuit_breakers.yml"):
        self.config_path = Path(config_path)
        self.configs: Dict[str, ServiceCircuitBreakerConfig] = {}
        self.reload_lock = asyncio.Lock()
        self._load_configs()

    def _load_configs(self) -> None:
        """Load circuit breaker configs from YAML file with env var overrides."""
        try:
            with open(self.config_path, "r") as f:
                data: Dict[str, Any] = yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning(
                "circuit_breaker_config_not_found",
                path=str(self.config_path),
                using_defaults=True,
            )
            data = {"circuit_breakers": {}}

        # Clear existing configs before loading new ones
        self.configs.clear()

        # Parse circuit breaker configs
        circuit_breakers: Dict[str, Dict[str, Any]] = data.get("circuit_breakers", {})
        for service_name, config_dict in circuit_breakers.items():
            # Apply environment variable overrides
            config_dict = self._apply_env_overrides(service_name, config_dict)
            # Validate config
            self._validate_config(service_name, config_dict)
            self.configs[service_name] = ServiceCircuitBreakerConfig(**config_dict)

        logger.info(
            "circuit_breaker_configs_loaded",
            num_configs=len(self.configs),
            services=list(self.configs.keys()),
        )

    def _apply_env_overrides(
        self, service_name: str, config_dict: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply environment variable overrides."""
        env_prefix = f"K1_CIRCUIT_{service_name.upper()}_"
        overridden = config_dict.copy()

        for key, value in config_dict.items():
            env_var = f"{env_prefix}{key.upper()}"
            if env_var in os.environ:
                # Parse value based on type
                if isinstance(value, int):
                    overridden[key] = int(os.environ[env_var])
                elif isinstance(value, bool):
                    overridden[key] = os.environ[env_var].lower() == "true"
                else:
                    overridden[key] = os.environ[env_var]

                logger.info(
                    "circuit_config_override",
                    service=service_name,
                    key=key,
                    value=overridden[key],
                    source="env_var",
                )

        return overridden

    def _validate_config(self, service_name: str, config_dict: Dict[str, Any]) -> None:
        """Validate circuit breaker config."""
        errors: List[str] = []

        if config_dict.get("failure_threshold", 5) < 2:
            errors.append("failure_threshold must be >= 2")

        if config_dict.get("timeout_duration_ms", 30000) < 1000:
            errors.append("timeout_duration_ms must be >= 1000")

        if config_dict.get("success_threshold", 2) < 1:
            errors.append("success_threshold must be >= 1")

        if config_dict.get("slow_call_threshold_ms", 5000) < 100:
            errors.append("slow_call_threshold_ms must be >= 100")

        if config_dict.get("time_window_ms", 60000) < 10000:
            errors.append("time_window_ms must be >= 10000")

        valid_strategies = [
            "default_value",
            "cached_result",
            "alternate_model",
            "raise_error",
        ]
        if (
            config_dict.get("fallback_strategy", "default_value")
            not in valid_strategies
        ):
            errors.append(f"fallback_strategy must be one of {valid_strategies}")

        if errors:
            raise ValueError(
                f"Invalid circuit breaker config for {service_name}: {', '.join(errors)}"
            )

    def get_circuit_config(self, service_name: str) -> ServiceCircuitBreakerConfig:
        """Get circuit breaker config for service."""
        if service_name not in self.configs:
            logger.warning(
                "circuit_config_not_found",
                service_name=service_name,
                using_default=True,
            )
            return self._get_default_config()

        return self.configs[service_name]

    def _get_default_config(self) -> ServiceCircuitBreakerConfig:
        """Return default circuit breaker config."""
        return ServiceCircuitBreakerConfig(
            failure_threshold=5,
            timeout_duration_ms=30000,
            success_threshold=2,
            slow_call_threshold_ms=5000,
            time_window_ms=60000,
            fallback_strategy="default_value",
            enabled=True,
        )

    async def reload_configs(self) -> Dict[str, Any]:
        """Hot-reload circuit breaker configs from disk."""
        async with self.reload_lock:
            start_time = time.time()

            try:
                # Load new configs
                self._load_configs()

                latency_ms = (time.time() - start_time) * 1000
                logger.info("circuit_breaker_configs_reloaded", latency_ms=latency_ms)

                return {"status": "success", "latency_ms": latency_ms}

            except Exception as e:
                logger.error("circuit_breaker_config_reload_failed", error=str(e))
                raise


class CircuitBreakerManager:
    """Manages multiple circuit breaker instances with per-service configuration."""

    def __init__(self, config_path: str = "k1/config/circuit_breakers.yml"):
        self.config_manager = ConfigManager(config_path)
        self.circuits: Dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()
        self._fallback_cache = _FallbackCache()  # In-memory cache for fallback results

    def get_circuit(self, service_name: str) -> CircuitBreaker:
        """Get or create circuit breaker for service."""
        if service_name not in self.circuits:
            config = self.config_manager.get_circuit_config(service_name)
            if not config.enabled:
                raise CircuitBreakerError(
                    f"Circuit breaker disabled for service: {service_name}"
                )

            # Convert our config to circuit_breaker.CircuitBreakerConfig
            cb_config = self._convert_config(service_name, config)
            self.circuits[service_name] = CircuitBreaker(cb_config)

            logger.info(
                "circuit_breaker_created",
                service=service_name,
                failure_threshold=config.failure_threshold,
                timeout_duration_ms=config.timeout_duration_ms,
            )

        return self.circuits[service_name]

    def _convert_config(
        self, service_name: str, config: ServiceCircuitBreakerConfig
    ) -> CircuitBreakerConfig:
        """Convert our config to circuit_breaker.CircuitBreakerConfig."""
        return CircuitBreakerConfig(
            service=service_name,  # Always use requested service name for metrics
            failure_threshold=config.failure_threshold,
            timeout_duration_ms=config.timeout_duration_ms,
            success_threshold=config.success_threshold,
            slow_call_threshold_ms=config.slow_call_threshold_ms,
            time_window_ms=config.time_window_ms,
            failure_exceptions=(Exception,),  # Default to all exceptions
            fallback=self._create_fallback(config),
            alternate_service=config.alternate_service,  # Separate label for metrics clarity
        )

    def _create_fallback(
        self, config: ServiceCircuitBreakerConfig
    ) -> Optional[Callable[[], Any]]:
        """
        Create fallback function based on strategy.

        Strategies:
        - default_value: Return configured default value (from config.default_value)
        - cached_result: Return cached result if available (uses in-memory cache with TTL)
        - alternate_model: Delegate to alternate callable (from config.alternate_callable)
        - raise_error: No fallback, raise original error

        NOTE: cached_result uses simple in-memory cache. For production, integrate
        with Redis/Memcached via k1.storage layer.
        """
        if config.fallback_strategy == "default_value":
            # Return configured default value instead of None
            default_val = config.default_value
            return lambda: default_val

        elif config.fallback_strategy == "cached_result":
            # Return cached result from in-memory cache if available
            # NOTE: This is a placeholder implementation. Production should use
            # persistent cache (Redis/Memcached) for distributed systems.
            # TODO: Store successful results via cache_successful_result() method
            cache_key = f"fallback:{config.alternate_service or 'unknown'}"

            async def cached_fallback() -> Any:
                cached_value = await self._fallback_cache.get(cache_key)
                if cached_value is not None:
                    logger.info(
                        "circuit_breaker_fallback_cache_hit",
                        service=config.alternate_service or "unknown",
                        cache_key=cache_key,
                    )
                    return cached_value

                logger.warning(
                    "circuit_breaker_fallback_cache_miss",
                    service=config.alternate_service or "unknown",
                    cache_key=cache_key,
                )
                return None  # No cached value available

            return cached_fallback

        elif config.fallback_strategy == "alternate_model":
            # Delegate to injected alternate callable
            if config.alternate_callable is not None:
                return config.alternate_callable
            else:
                logger.warning(
                    "circuit_breaker_alternate_callable_missing",
                    service=config.alternate_service or "unknown",
                    fallback_strategy="alternate_model",
                )
                return lambda: None  # Fallback to None if no callable provided

        elif config.fallback_strategy == "raise_error":
            # No fallback, circuit breaker will raise the original error
            return None

        else:
            logger.warning(
                "circuit_breaker_unknown_fallback_strategy",
                strategy=config.fallback_strategy,
            )
            return lambda: None  # Safe default

    async def reload_configs(self) -> Dict[str, Any]:
        """Reload configurations and update existing circuits."""
        result = await self.config_manager.reload_configs()

        # Update existing circuits with new configs
        async with self._lock:
            for service_name in self.circuits.keys():
                new_config = self.config_manager.get_circuit_config(service_name)
                if new_config.enabled:
                    # Update the circuit breaker with new config
                    new_cb_config = self._convert_config(service_name, new_config)

                    # Preserve state by updating config instead of recreating breaker
                    await self.circuits[service_name].update_config(new_cb_config)

                    logger.info(
                        "circuit_breaker_config_updated",
                        service=service_name,
                        new_failure_threshold=new_config.failure_threshold,
                        new_timeout_duration_ms=new_config.timeout_duration_ms,
                    )

        return result

    def get_all_circuits(self) -> Dict[str, CircuitBreaker]:
        """Get all circuit breakers."""
        return self.circuits.copy()

    def get_circuit_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all circuits."""
        stats: Dict[str, Dict[str, Any]] = {}
        for service_name, circuit in self.circuits.items():
            stats[service_name] = {
                "state": circuit.state.name,
                "failure_count": circuit.failure_count,
                "success_count": circuit.success_count,
                "is_open": circuit.is_open,
            }
        return stats

    async def cache_successful_result(self, service_name: str, result: Any) -> None:
        """
        Cache successful result for fallback strategy.

        Call this after successful circuit breaker operations to populate
        the fallback cache for future circuit OPEN scenarios.

        Args:
            service_name: Service name to cache result for
            result: Successful operation result to cache

        Example:
            result = await manager.get_circuit("llm").call(operation)
            await manager.cache_successful_result("llm", result)
        """
        config = self.config_manager.get_circuit_config(service_name)
        if config.fallback_strategy == "cached_result":
            cache_key = f"fallback:{config.alternate_service or service_name}"
            ttl_ms = config.cache_ttl_ms or 60000  # Default 60s TTL
            await self._fallback_cache.set(cache_key, result, ttl_ms)
            logger.debug(
                "circuit_breaker_result_cached",
                service=service_name,
                cache_key=cache_key,
                ttl_ms=ttl_ms,
            )
