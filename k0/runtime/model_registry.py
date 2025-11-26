"""
Model Registry - Centralized ML Model Management for K0 Kernel.

This registry provides unified model loading, memory management, and retrieval
for all ML models used across K0 modules.

Architecture:
- Lazy loading: Models loaded on first use, not at startup
- Memory-aware: GPU memory limits with automatic CPU fallback
- Thread-safe: Concurrent model access with locking
- Versioned: Model versioning for reproducibility
- Tier-aware: Works with FeatureFlags for gradual ML rollout

Related:
- MODULE_ENHANCEMENT_PLAN.md: Milestone 1 - Infrastructure
- k0/kernel/app.py: Integration point
- k0/config/feature_flags.py: ML tier selection
- k0/config/models.yaml: Model definitions

Issue: 1.1.1 - Unified Model Registry
Status: IMPLEMENTED
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Optional, TypeVar

import yaml

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ModelTier(str, Enum):
    """ML model complexity tiers."""

    RULE_BASED = "rule_based"
    SPACY_SMALL = "spacy_small"
    SPACY_LARGE = "spacy_large"
    TRANSFORMER_SMALL = "transformer_small"
    TRANSFORMER_LARGE = "transformer_large"


class DeviceType(str, Enum):
    """Compute device types."""

    CPU = "cpu"
    CUDA = "cuda"
    MPS = "mps"  # Apple Silicon


@dataclass
class ModelSpec:
    """Specification for a single ML model."""

    name: str
    model_id: str
    tier: ModelTier
    loader: str  # Module path to loader function
    memory_mb: int  # Expected memory usage in MB
    version: str = "1.0.0"
    device_preference: DeviceType = DeviceType.CPU
    fallback_to_cpu: bool = True
    load_timeout_sec: float = 30.0
    warmup_input: Optional[str] = None  # Sample input for warmup


@dataclass
class LoadedModel:
    """Container for a loaded model with metadata."""

    model: Any
    spec: ModelSpec
    device: DeviceType
    load_time_sec: float
    memory_mb: int
    loaded_at: float = field(default_factory=time.time)

    @property
    def age_sec(self) -> float:
        """Seconds since model was loaded."""
        return time.time() - self.loaded_at


class ModelLoadError(Exception):
    """Raised when model loading fails."""

    pass


class ModelNotFoundError(Exception):
    """Raised when requested model is not registered."""

    pass


class MemoryLimitExceededError(Exception):
    """Raised when GPU memory limit would be exceeded."""

    pass


class ModelRegistry:
    """
    Centralized registry for ML model management.

    Responsibilities:
    1. Load model specifications from YAML config
    2. Lazy-load models on first request
    3. Manage GPU memory allocation
    4. Provide thread-safe model access
    5. Handle CPU fallback on GPU OOM
    6. Track model versions and metadata

    Usage:
        >>> registry = ModelRegistry(gpu_memory_limit_mb=4096)
        >>> await registry.load_config("k0/config/models.yaml")
        >>> spacy_model = await registry.get("spacy_nlp")
        >>> result = spacy_model("Some text to process")
    """

    # Default model specifications (used if no config file)
    _DEFAULT_SPECS: Dict[str, Dict[str, Any]] = {
        "spacy_nlp": {
            "name": "spaCy English Small",
            "model_id": "en_core_web_sm",
            "tier": "spacy_small",
            "loader": "k0.runtime.model_loaders.load_spacy",
            "memory_mb": 100,
            "version": "3.7.0",
            "device_preference": "cpu",
            "fallback_to_cpu": True,
            "load_timeout_sec": 15.0,
            "warmup_input": "Hello world",
        },
        "spacy_nlp_lg": {
            "name": "spaCy English Large",
            "model_id": "en_core_web_lg",
            "tier": "spacy_large",
            "loader": "k0.runtime.model_loaders.load_spacy",
            "memory_mb": 800,
            "version": "3.7.0",
            "device_preference": "cpu",
            "fallback_to_cpu": True,
            "load_timeout_sec": 30.0,
            "warmup_input": "Hello world",
        },
        "vader_analyzer": {
            "name": "VADER Sentiment Analyzer",
            "model_id": "vaderSentiment",
            "tier": "rule_based",
            "loader": "k0.runtime.model_loaders.load_vader",
            "memory_mb": 50,
            "version": "3.3.2",
            "device_preference": "cpu",
            "fallback_to_cpu": True,
            "load_timeout_sec": 5.0,
            "warmup_input": "I love this!",
        },
        "sentence_transformer": {
            "name": "Sentence Transformer all-MiniLM-L6-v2",
            "model_id": "all-MiniLM-L6-v2",
            "tier": "transformer_small",
            "loader": "k0.runtime.model_loaders.load_sentence_transformer",
            "memory_mb": 500,
            "version": "2.2.0",
            "device_preference": "cuda",
            "fallback_to_cpu": True,
            "load_timeout_sec": 60.0,
            "warmup_input": "Hello world",
        },
    }

    def __init__(
        self,
        gpu_memory_limit_mb: int = 4096,
        cpu_memory_limit_mb: int = 8192,
    ) -> None:
        """
        Initialize model registry.

        Args:
            gpu_memory_limit_mb: Maximum GPU memory budget (default 4GB)
            cpu_memory_limit_mb: Maximum CPU memory budget (default 8GB)
        """
        self._specs: Dict[str, ModelSpec] = {}
        self._models: Dict[str, LoadedModel] = {}
        self._gpu_memory_limit_mb = gpu_memory_limit_mb
        self._cpu_memory_limit_mb = cpu_memory_limit_mb
        self._gpu_memory_used_mb = 0
        self._cpu_memory_used_mb = 0
        self._lock = threading.RLock()
        self._async_lock = asyncio.Lock()
        self._loaded = False

        # Initialize default specs
        self._init_default_specs()

    def _init_default_specs(self) -> None:
        """Initialize default model specifications."""
        for name, spec_dict in self._DEFAULT_SPECS.items():
            self._specs[name] = ModelSpec(
                name=spec_dict["name"],
                model_id=spec_dict["model_id"],
                tier=ModelTier(spec_dict["tier"]),
                loader=spec_dict["loader"],
                memory_mb=spec_dict["memory_mb"],
                version=spec_dict.get("version", "1.0.0"),
                device_preference=DeviceType(spec_dict.get("device_preference", "cpu")),
                fallback_to_cpu=spec_dict.get("fallback_to_cpu", True),
                load_timeout_sec=spec_dict.get("load_timeout_sec", 30.0),
                warmup_input=spec_dict.get("warmup_input"),
            )

    async def load_config(self, config_path: str | Path) -> None:
        """
        Load model specifications from YAML config.

        Args:
            config_path: Path to models.yaml

        Raises:
            FileNotFoundError: If config file doesn't exist
        """
        config_path = Path(config_path)
        if not config_path.exists():
            logger.warning(
                f"Model config not found: {config_path}, using defaults",
                extra={"config_path": str(config_path)},
            )
            self._loaded = True
            return

        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        models_config = config.get("models", {})

        for name, spec_dict in models_config.items():
            try:
                self._specs[name] = ModelSpec(
                    name=spec_dict.get("name", name),
                    model_id=spec_dict["model_id"],
                    tier=ModelTier(spec_dict.get("tier", "rule_based")),
                    loader=spec_dict["loader"],
                    memory_mb=spec_dict.get("memory_mb", 100),
                    version=spec_dict.get("version", "1.0.0"),
                    device_preference=DeviceType(spec_dict.get("device_preference", "cpu")),
                    fallback_to_cpu=spec_dict.get("fallback_to_cpu", True),
                    load_timeout_sec=spec_dict.get("load_timeout_sec", 30.0),
                    warmup_input=spec_dict.get("warmup_input"),
                )
                logger.debug(f"Loaded model spec: {name}")
            except Exception as e:
                logger.error(f"Failed to load model spec {name}: {e}")

        self._loaded = True
        logger.info(
            f"Loaded {len(self._specs)} model specifications",
            extra={"count": len(self._specs), "models": list(self._specs.keys())},
        )

    async def get(self, model_name: str) -> Any:
        """
        Get a loaded model by name (lazy-loads if needed).

        Args:
            model_name: Name of the model (e.g., "spacy_nlp", "vader_analyzer")

        Returns:
            Loaded model object

        Raises:
            ModelNotFoundError: If model not registered
            ModelLoadError: If model fails to load
        """
        # Fast path: return cached model
        with self._lock:
            if model_name in self._models:
                return self._models[model_name].model

        # Slow path: load model with async lock
        async with self._async_lock:
            # Double-check after acquiring lock
            if model_name in self._models:
                return self._models[model_name].model

            # Load the model
            loaded_model = await self._load_model(model_name)

            with self._lock:
                self._models[model_name] = loaded_model

            return loaded_model.model

    async def _load_model(self, model_name: str) -> LoadedModel:
        """
        Load a model by name.

        Args:
            model_name: Name of the model to load

        Returns:
            LoadedModel container

        Raises:
            ModelNotFoundError: If model not in specs
            ModelLoadError: If loading fails
        """
        if model_name not in self._specs:
            raise ModelNotFoundError(
                f"Model not found: {model_name} (available: {list(self._specs.keys())})"
            )

        spec = self._specs[model_name]
        start_time = time.time()

        logger.info(
            f"Loading model: {model_name}",
            extra={
                "model_name": model_name,
                "model_id": spec.model_id,
                "tier": spec.tier.value,
                "expected_memory_mb": spec.memory_mb,
            },
        )

        # Determine device
        device = await self._select_device(spec)

        # Check memory limits
        if device == DeviceType.CUDA:
            if self._gpu_memory_used_mb + spec.memory_mb > self._gpu_memory_limit_mb:
                if spec.fallback_to_cpu:
                    logger.warning(
                        f"GPU memory limit exceeded, falling back to CPU for {model_name}",
                        extra={
                            "model_name": model_name,
                            "gpu_used_mb": self._gpu_memory_used_mb,
                            "model_memory_mb": spec.memory_mb,
                            "limit_mb": self._gpu_memory_limit_mb,
                        },
                    )
                    device = DeviceType.CPU
                else:
                    raise MemoryLimitExceededError(f"GPU memory limit exceeded for {model_name}")

        # Load model using loader function
        try:
            loader_func = self._get_loader(spec.loader)
            model = await asyncio.wait_for(
                asyncio.to_thread(loader_func, spec.model_id, device.value),
                timeout=spec.load_timeout_sec,
            )
        except asyncio.TimeoutError:
            raise ModelLoadError(f"Model load timeout ({spec.load_timeout_sec}s) for {model_name}")
        except Exception as e:
            # Try CPU fallback
            if device != DeviceType.CPU and spec.fallback_to_cpu:
                logger.warning(
                    f"Model load failed on {device.value}, trying CPU fallback: {e}",
                    extra={"model_name": model_name, "original_device": device.value},
                )
                try:
                    model = await asyncio.wait_for(
                        asyncio.to_thread(loader_func, spec.model_id, DeviceType.CPU.value),
                        timeout=spec.load_timeout_sec,
                    )
                    device = DeviceType.CPU
                except Exception as fallback_e:
                    raise ModelLoadError(
                        f"Model load failed for {model_name} (including CPU fallback): {fallback_e}"
                    ) from fallback_e
            else:
                raise ModelLoadError(f"Model load failed for {model_name}: {e}") from e

        load_time = time.time() - start_time

        # Update memory tracking
        with self._lock:
            if device == DeviceType.CUDA:
                self._gpu_memory_used_mb += spec.memory_mb
            else:
                self._cpu_memory_used_mb += spec.memory_mb

        # Optional warmup
        if spec.warmup_input and hasattr(model, "__call__"):
            try:
                _ = model(spec.warmup_input)
                logger.debug(f"Model warmup complete: {model_name}")
            except Exception as e:
                logger.warning(f"Model warmup failed for {model_name}: {e}")

        loaded_model = LoadedModel(
            model=model,
            spec=spec,
            device=device,
            load_time_sec=load_time,
            memory_mb=spec.memory_mb,
        )

        logger.info(
            f"Model loaded: {model_name}",
            extra={
                "model_name": model_name,
                "device": device.value,
                "load_time_sec": round(load_time, 2),
                "memory_mb": spec.memory_mb,
            },
        )

        return loaded_model

    async def _select_device(self, spec: ModelSpec) -> DeviceType:
        """
        Select best available device for model.

        Args:
            spec: Model specification

        Returns:
            Selected device type
        """
        preferred = spec.device_preference

        if preferred == DeviceType.CPU:
            return DeviceType.CPU

        if preferred == DeviceType.CUDA:
            if self._is_cuda_available():
                return DeviceType.CUDA

        if preferred == DeviceType.MPS:
            if self._is_mps_available():
                return DeviceType.MPS

        return DeviceType.CPU

    def _is_cuda_available(self) -> bool:
        """Check if CUDA is available."""
        try:
            import torch

            return torch.cuda.is_available()
        except ImportError:
            return False

    def _is_mps_available(self) -> bool:
        """Check if Apple MPS is available."""
        try:
            import torch

            return torch.backends.mps.is_available()
        except (ImportError, AttributeError):
            return False

    def _get_loader(self, loader_path: str) -> Callable:
        """
        Get loader function from module path.

        Args:
            loader_path: Dotted path (e.g., "k0.runtime.model_loaders.load_spacy")

        Returns:
            Loader function

        Raises:
            ImportError: If loader module not found
            AttributeError: If loader function not found
        """
        module_path, func_name = loader_path.rsplit(".", 1)

        try:
            import importlib

            module = importlib.import_module(module_path)
            return getattr(module, func_name)
        except ImportError as e:
            raise ImportError(f"Loader module not found: {module_path}") from e
        except AttributeError as e:
            raise AttributeError(f"Loader function not found: {func_name} in {module_path}") from e

    async def preload(self, model_names: list[str]) -> Dict[str, bool]:
        """
        Preload multiple models.

        Args:
            model_names: List of model names to preload

        Returns:
            Dict mapping model name to success status
        """
        results = {}
        for name in model_names:
            try:
                await self.get(name)
                results[name] = True
            except Exception as e:
                logger.error(f"Failed to preload {name}: {e}")
                results[name] = False
        return results

    def get_sync(self, model_name: str) -> Optional[Any]:
        """
        Get cached model synchronously (returns None if not loaded).

        For hot paths where async is not feasible.

        Args:
            model_name: Name of the model

        Returns:
            Loaded model or None if not cached
        """
        with self._lock:
            if model_name in self._models:
                return self._models[model_name].model
        return None

    def is_loaded(self, model_name: str) -> bool:
        """Check if model is loaded."""
        with self._lock:
            return model_name in self._models

    def list_specs(self) -> list[str]:
        """Return list of available model names."""
        return list(self._specs.keys())

    def list_loaded(self) -> list[str]:
        """Return list of currently loaded models."""
        with self._lock:
            return list(self._models.keys())

    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        with self._lock:
            return {
                "specs_count": len(self._specs),
                "loaded_count": len(self._models),
                "gpu_memory_used_mb": self._gpu_memory_used_mb,
                "gpu_memory_limit_mb": self._gpu_memory_limit_mb,
                "cpu_memory_used_mb": self._cpu_memory_used_mb,
                "cpu_memory_limit_mb": self._cpu_memory_limit_mb,
                "loaded_models": {
                    name: {
                        "device": lm.device.value,
                        "memory_mb": lm.memory_mb,
                        "load_time_sec": round(lm.load_time_sec, 2),
                        "age_sec": round(lm.age_sec, 1),
                        "tier": lm.spec.tier.value,
                    }
                    for name, lm in self._models.items()
                },
            }

    async def unload(self, model_name: str) -> bool:
        """
        Unload a model to free memory.

        Args:
            model_name: Name of model to unload

        Returns:
            True if unloaded, False if not loaded
        """
        async with self._async_lock:
            with self._lock:
                if model_name not in self._models:
                    return False

                loaded_model = self._models.pop(model_name)

                # Update memory tracking
                if loaded_model.device == DeviceType.CUDA:
                    self._gpu_memory_used_mb -= loaded_model.memory_mb
                else:
                    self._cpu_memory_used_mb -= loaded_model.memory_mb

                # Help GC
                del loaded_model.model

                logger.info(
                    f"Model unloaded: {model_name}",
                    extra={"model_name": model_name},
                )
                return True

    async def shutdown(self) -> None:
        """Unload all models and clean up."""
        logger.info("Shutting down model registry")
        model_names = self.list_loaded()
        for name in model_names:
            await self.unload(name)
        logger.info("Model registry shutdown complete")


# Singleton instance for kernel-wide use
_registry: Optional[ModelRegistry] = None


def get_model_registry() -> ModelRegistry:
    """
    Get the global model registry singleton.

    Returns:
        ModelRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry


async def init_model_registry(
    config_path: Optional[str | Path] = None,
    gpu_memory_limit_mb: int = 4096,
    cpu_memory_limit_mb: int = 8192,
) -> ModelRegistry:
    """
    Initialize the global model registry.

    Args:
        config_path: Optional path to models.yaml
        gpu_memory_limit_mb: GPU memory limit
        cpu_memory_limit_mb: CPU memory limit

    Returns:
        Initialized ModelRegistry
    """
    global _registry
    _registry = ModelRegistry(
        gpu_memory_limit_mb=gpu_memory_limit_mb,
        cpu_memory_limit_mb=cpu_memory_limit_mb,
    )

    if config_path:
        await _registry.load_config(config_path)

    return _registry
