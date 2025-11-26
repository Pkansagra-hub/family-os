"""
Feature Flags - ML Tier Selection and Gradual Rollout System.

This module provides feature flags for controlling which ML tier each module uses.
Enables gradual rollout of ML upgrades with automatic fallback on failures.

Architecture:
- Module-level tier selection (RULE_BASED, SPACY_LARGE, TRANSFORMER, etc.)
- Percentage-based rollout for A/B testing
- Automatic fallback on model failures
- Metrics collection for comparison

Related:
- MODULE_ENHANCEMENT_PLAN.md: Milestone 1 - Infrastructure
- k0/runtime/model_registry.py: Uses tier to select models
- k0/config/feature_flags.yaml: Flag definitions

Issue: 1.1.2 - Feature Flag System
Status: IMPLEMENTED
"""

from __future__ import annotations

import hashlib
import logging
import random
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


class MLTier(str, Enum):
    """ML complexity tiers for modules."""

    DISABLED = "disabled"
    RULE_BASED = "rule_based"
    SPACY_SMALL = "spacy_small"
    SPACY_LARGE = "spacy_large"
    TRANSFORMER_SMALL = "transformer_small"
    TRANSFORMER_LARGE = "transformer_large"
    CUSTOM = "custom"


@dataclass
class ModuleFlag:
    """Feature flag for a single module."""

    module_id: str
    enabled_tier: MLTier
    fallback_tier: MLTier = MLTier.RULE_BASED
    rollout_percentage: float = 100.0
    description: str = ""
    metrics_enabled: bool = True
    failure_count: int = 0
    max_failures_before_fallback: int = 3
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def should_use_advanced_tier(self, request_id: Optional[str] = None) -> bool:
        """
        Check if advanced tier should be used for this request.

        Uses consistent hashing for percentage rollout so same request_id
        always gets same result.

        Args:
            request_id: Optional request identifier for consistent hashing

        Returns:
            True if advanced tier should be used
        """
        # Check failure threshold
        with self._lock:
            if self.failure_count >= self.max_failures_before_fallback:
                logger.warning(
                    f"Module {self.module_id} exceeded failure threshold, using fallback",
                    extra={
                        "module_id": self.module_id,
                        "failure_count": self.failure_count,
                        "threshold": self.max_failures_before_fallback,
                    },
                )
                return False

        # 100% rollout - always use advanced
        if self.rollout_percentage >= 100.0:
            return True

        # 0% rollout - never use advanced
        if self.rollout_percentage <= 0.0:
            return False

        # Percentage rollout with consistent hashing
        if request_id:
            hash_input = f"{self.module_id}:{request_id}"
            hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
            percentage = (hash_value % 10000) / 100.0
        else:
            percentage = random.uniform(0, 100)

        return percentage < self.rollout_percentage

    def record_failure(self) -> None:
        """Record a failure for this module."""
        with self._lock:
            self.failure_count += 1
            logger.warning(
                f"Module {self.module_id} failure recorded",
                extra={
                    "module_id": self.module_id,
                    "failure_count": self.failure_count,
                },
            )

    def record_success(self) -> None:
        """Record a success, potentially resetting failure count."""
        with self._lock:
            if self.failure_count > 0:
                self.failure_count = max(0, self.failure_count - 1)

    def reset_failures(self) -> None:
        """Reset failure count."""
        with self._lock:
            self.failure_count = 0


@dataclass
class FeatureFlagsConfig:
    """Configuration for feature flags system."""

    global_enabled: bool = True
    default_tier: MLTier = MLTier.RULE_BASED
    default_rollout_percentage: float = 100.0
    metrics_enabled: bool = True
    auto_fallback_enabled: bool = True


class FeatureFlags:
    """
    Feature flag system for ML tier selection.

    Responsibilities:
    1. Load flag configurations from YAML
    2. Determine which ML tier to use per module
    3. Handle percentage-based rollouts
    4. Track failures and auto-fallback
    5. Provide metrics for A/B comparison

    Usage:
        >>> flags = FeatureFlags()
        >>> await flags.load_config("k0/config/feature_flags.yaml")
        >>> tier = flags.get_tier("affect.analyze", request_id="req-123")
        >>> if tier == MLTier.TRANSFORMER_SMALL:
        ...     result = await run_transformer_sentiment(text)
        ... else:
        ...     result = await run_vader_sentiment(text)
    """

    # Default module flags (used if no config file)
    _DEFAULT_FLAGS: Dict[str, Dict[str, Any]] = {
        # M02 - Semantic Project (Entity/KG extraction)
        "hippocampus.semantic_project": {
            "enabled_tier": "rule_based",
            "fallback_tier": "rule_based",
            "rollout_percentage": 100.0,
            "description": "Entity extraction and KG triple generation",
        },
        # M04 - Affect Analyze (Sentiment)
        "affect.analyze": {
            "enabled_tier": "rule_based",  # VADER
            "fallback_tier": "rule_based",
            "rollout_percentage": 100.0,
            "description": "Sentiment and emotion analysis",
        },
        # M06 - Salience Score
        "salience.score": {
            "enabled_tier": "rule_based",
            "fallback_tier": "rule_based",
            "rollout_percentage": 100.0,
            "description": "Salience scoring for memories",
        },
        # M07 - Family Graph Resolve
        "social.family_graph_resolve": {
            "enabled_tier": "rule_based",
            "fallback_tier": "rule_based",
            "rollout_percentage": 100.0,
            "description": "Social context and family relationship resolution",
        },
        # M10 - Ingress Classify
        "context.ingress_classify": {
            "enabled_tier": "rule_based",
            "fallback_tier": "rule_based",
            "rollout_percentage": 100.0,
            "description": "Activity type classification",
        },
    }

    def __init__(self) -> None:
        """Initialize feature flags system."""
        self._flags: Dict[str, ModuleFlag] = {}
        self._config = FeatureFlagsConfig()
        self._lock = threading.RLock()
        self._metrics: Dict[str, Dict[str, int]] = {}
        self._loaded = False

        # Initialize default flags
        self._init_default_flags()

    def _init_default_flags(self) -> None:
        """Initialize default module flags."""
        for module_id, flag_dict in self._DEFAULT_FLAGS.items():
            self._flags[module_id] = ModuleFlag(
                module_id=module_id,
                enabled_tier=MLTier(flag_dict.get("enabled_tier", "rule_based")),
                fallback_tier=MLTier(flag_dict.get("fallback_tier", "rule_based")),
                rollout_percentage=flag_dict.get("rollout_percentage", 100.0),
                description=flag_dict.get("description", ""),
                metrics_enabled=flag_dict.get("metrics_enabled", True),
            )
            self._metrics[module_id] = {"advanced_calls": 0, "fallback_calls": 0, "failures": 0}

    async def load_config(self, config_path: str | Path) -> None:
        """
        Load feature flag configuration from YAML.

        Args:
            config_path: Path to feature_flags.yaml
        """
        config_path = Path(config_path)
        if not config_path.exists():
            logger.warning(
                f"Feature flags config not found: {config_path}, using defaults",
                extra={"config_path": str(config_path)},
            )
            self._loaded = True
            return

        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        # Load global config
        global_config = config.get("global", {})
        self._config = FeatureFlagsConfig(
            global_enabled=global_config.get("enabled", True),
            default_tier=MLTier(global_config.get("default_tier", "rule_based")),
            default_rollout_percentage=global_config.get("default_rollout_percentage", 100.0),
            metrics_enabled=global_config.get("metrics_enabled", True),
            auto_fallback_enabled=global_config.get("auto_fallback_enabled", True),
        )

        # Load module flags
        module_flags = config.get("modules", {})
        for module_id, flag_dict in module_flags.items():
            self._flags[module_id] = ModuleFlag(
                module_id=module_id,
                enabled_tier=MLTier(flag_dict.get("enabled_tier", self._config.default_tier.value)),
                fallback_tier=MLTier(flag_dict.get("fallback_tier", "rule_based")),
                rollout_percentage=flag_dict.get(
                    "rollout_percentage", self._config.default_rollout_percentage
                ),
                description=flag_dict.get("description", ""),
                metrics_enabled=flag_dict.get("metrics_enabled", self._config.metrics_enabled),
                max_failures_before_fallback=flag_dict.get("max_failures_before_fallback", 3),
            )
            if module_id not in self._metrics:
                self._metrics[module_id] = {"advanced_calls": 0, "fallback_calls": 0, "failures": 0}

        self._loaded = True
        logger.info(
            f"Loaded {len(self._flags)} feature flags",
            extra={"count": len(self._flags), "modules": list(self._flags.keys())},
        )

    def get_tier(
        self,
        module_id: str,
        request_id: Optional[str] = None,
    ) -> MLTier:
        """
        Get the ML tier to use for a module.

        Args:
            module_id: Module identifier (e.g., "affect.analyze")
            request_id: Optional request ID for consistent hashing

        Returns:
            MLTier to use
        """
        if not self._config.global_enabled:
            return self._config.default_tier

        with self._lock:
            if module_id not in self._flags:
                logger.debug(f"No flag for {module_id}, using default tier")
                return self._config.default_tier

            flag = self._flags[module_id]

            # Check if should use advanced tier
            if flag.should_use_advanced_tier(request_id):
                tier = flag.enabled_tier
                if flag.metrics_enabled:
                    self._metrics[module_id]["advanced_calls"] += 1
            else:
                tier = flag.fallback_tier
                if flag.metrics_enabled:
                    self._metrics[module_id]["fallback_calls"] += 1

            return tier

    def get_flag(self, module_id: str) -> Optional[ModuleFlag]:
        """Get flag for a module."""
        with self._lock:
            return self._flags.get(module_id)

    def set_tier(
        self,
        module_id: str,
        tier: MLTier,
        rollout_percentage: float = 100.0,
    ) -> None:
        """
        Set tier for a module (runtime override).

        Args:
            module_id: Module identifier
            tier: ML tier to use
            rollout_percentage: Percentage of requests to use this tier
        """
        with self._lock:
            if module_id in self._flags:
                self._flags[module_id].enabled_tier = tier
                self._flags[module_id].rollout_percentage = rollout_percentage
            else:
                self._flags[module_id] = ModuleFlag(
                    module_id=module_id,
                    enabled_tier=tier,
                    rollout_percentage=rollout_percentage,
                )
                self._metrics[module_id] = {"advanced_calls": 0, "fallback_calls": 0, "failures": 0}

            logger.info(
                f"Set tier for {module_id}: {tier.value} at {rollout_percentage}%",
                extra={"module_id": module_id, "tier": tier.value, "rollout": rollout_percentage},
            )

    def record_failure(self, module_id: str) -> None:
        """
        Record a failure for module's advanced tier.

        Args:
            module_id: Module identifier
        """
        with self._lock:
            if module_id in self._flags:
                self._flags[module_id].record_failure()
                self._metrics[module_id]["failures"] += 1

    def record_success(self, module_id: str) -> None:
        """
        Record a success for module's advanced tier.

        Args:
            module_id: Module identifier
        """
        with self._lock:
            if module_id in self._flags:
                self._flags[module_id].record_success()

    def reset_failures(self, module_id: str) -> None:
        """Reset failure count for a module."""
        with self._lock:
            if module_id in self._flags:
                self._flags[module_id].reset_failures()
                logger.info(f"Reset failures for {module_id}")

    def get_metrics(self, module_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get metrics for modules.

        Args:
            module_id: Optional specific module, or None for all

        Returns:
            Metrics dictionary
        """
        with self._lock:
            if module_id:
                if module_id in self._metrics:
                    return {module_id: self._metrics[module_id].copy()}
                return {}
            return {k: v.copy() for k, v in self._metrics.items()}

    def get_all_flags(self) -> Dict[str, Dict[str, Any]]:
        """Get all flags as dictionary."""
        with self._lock:
            return {
                module_id: {
                    "enabled_tier": flag.enabled_tier.value,
                    "fallback_tier": flag.fallback_tier.value,
                    "rollout_percentage": flag.rollout_percentage,
                    "failure_count": flag.failure_count,
                    "description": flag.description,
                }
                for module_id, flag in self._flags.items()
            }

    def list_modules(self) -> List[str]:
        """List all modules with flags."""
        with self._lock:
            return list(self._flags.keys())

    def is_loaded(self) -> bool:
        """Check if config has been loaded."""
        return self._loaded


# Singleton instance
_feature_flags: Optional[FeatureFlags] = None


def get_feature_flags() -> FeatureFlags:
    """
    Get the global feature flags singleton.

    Returns:
        FeatureFlags instance
    """
    global _feature_flags
    if _feature_flags is None:
        _feature_flags = FeatureFlags()
    return _feature_flags


async def init_feature_flags(config_path: Optional[str | Path] = None) -> FeatureFlags:
    """
    Initialize the global feature flags.

    Args:
        config_path: Optional path to feature_flags.yaml

    Returns:
        Initialized FeatureFlags
    """
    global _feature_flags
    _feature_flags = FeatureFlags()

    if config_path:
        await _feature_flags.load_config(config_path)

    return _feature_flags


# Convenience decorator for module tier selection
def with_ml_tier(module_id: str):
    """
    Decorator that selects ML tier for a module function.

    Usage:
        @with_ml_tier("affect.analyze")
        async def analyze_sentiment(text: str, tier: MLTier) -> dict:
            if tier == MLTier.TRANSFORMER_SMALL:
                return await transformer_sentiment(text)
            else:
                return vader_sentiment(text)
    """

    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            flags = get_feature_flags()
            request_id = kwargs.get("request_id") or kwargs.get("trace_id")
            tier = flags.get_tier(module_id, request_id)
            kwargs["tier"] = tier
            try:
                result = await func(*args, **kwargs)
                flags.record_success(module_id)
                return result
            except Exception:
                flags.record_failure(module_id)
                raise

        return wrapper

    return decorator
