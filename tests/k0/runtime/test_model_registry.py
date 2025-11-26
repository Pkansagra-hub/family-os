"""
Unit tests for k0/runtime/model_registry.py

Tests cover:
- ModelRegistry initialization
- Model specification loading
- Lazy loading behavior
- GPU memory management
- CPU fallback
- Thread-safety
- Error handling

Related:
- k0/runtime/model_registry.py: Implementation
- k0/modules/MODULE_ENHANCEMENT_PLAN.md: Issue 1.1.1

Issue: 1.1.1 - Unified Model Registry
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from k0.runtime.model_registry import (
    DeviceType,
    LoadedModel,
    ModelNotFoundError,
    ModelRegistry,
    ModelSpec,
    ModelTier,
    get_model_registry,
    init_model_registry,
)


class TestModelSpec:
    """Tests for ModelSpec dataclass."""

    def test_model_spec_defaults(self):
        """Test default values for ModelSpec."""
        spec = ModelSpec(
            name="Test Model",
            model_id="test-model",
            tier=ModelTier.RULE_BASED,
            loader="test.loader",
            memory_mb=100,
        )
        assert spec.version == "1.0.0"
        assert spec.device_preference == DeviceType.CPU
        assert spec.fallback_to_cpu is True
        assert spec.load_timeout_sec == 30.0
        assert spec.warmup_input is None

    def test_model_spec_custom_values(self):
        """Test custom values for ModelSpec."""
        spec = ModelSpec(
            name="Custom Model",
            model_id="custom-model",
            tier=ModelTier.TRANSFORMER_LARGE,
            loader="custom.loader",
            memory_mb=2000,
            version="2.0.0",
            device_preference=DeviceType.CUDA,
            fallback_to_cpu=False,
            load_timeout_sec=120.0,
            warmup_input="test input",
        )
        assert spec.name == "Custom Model"
        assert spec.tier == ModelTier.TRANSFORMER_LARGE
        assert spec.device_preference == DeviceType.CUDA
        assert spec.fallback_to_cpu is False


class TestLoadedModel:
    """Tests for LoadedModel dataclass."""

    def test_loaded_model_age(self):
        """Test age calculation for LoadedModel."""
        spec = ModelSpec(
            name="Test",
            model_id="test",
            tier=ModelTier.RULE_BASED,
            loader="test",
            memory_mb=100,
        )
        model = LoadedModel(
            model=MagicMock(),
            spec=spec,
            device=DeviceType.CPU,
            load_time_sec=1.5,
            memory_mb=100,
        )
        # Age should be non-negative
        assert model.age_sec >= 0


class TestModelRegistry:
    """Tests for ModelRegistry class."""

    def test_init_defaults(self):
        """Test default initialization."""
        registry = ModelRegistry()
        assert registry._gpu_memory_limit_mb == 4096
        assert registry._cpu_memory_limit_mb == 8192
        assert len(registry._specs) > 0  # Default specs loaded

    def test_init_custom_limits(self):
        """Test custom memory limits."""
        registry = ModelRegistry(gpu_memory_limit_mb=2048, cpu_memory_limit_mb=4096)
        assert registry._gpu_memory_limit_mb == 2048
        assert registry._cpu_memory_limit_mb == 4096

    def test_default_specs_loaded(self):
        """Test that default specs are loaded."""
        registry = ModelRegistry()
        assert "spacy_nlp" in registry._specs
        assert "vader_analyzer" in registry._specs

    def test_list_specs(self):
        """Test listing available model names."""
        registry = ModelRegistry()
        specs = registry.list_specs()
        assert isinstance(specs, list)
        assert "spacy_nlp" in specs
        assert "vader_analyzer" in specs

    def test_is_loaded_false(self):
        """Test is_loaded returns False for unloaded model."""
        registry = ModelRegistry()
        assert registry.is_loaded("spacy_nlp") is False

    def test_list_loaded_empty(self):
        """Test list_loaded returns empty for fresh registry."""
        registry = ModelRegistry()
        assert registry.list_loaded() == []

    def test_get_sync_returns_none_unloaded(self):
        """Test get_sync returns None for unloaded model."""
        registry = ModelRegistry()
        assert registry.get_sync("spacy_nlp") is None

    def test_get_stats(self):
        """Test get_stats returns correct structure."""
        registry = ModelRegistry()
        stats = registry.get_stats()
        assert "specs_count" in stats
        assert "loaded_count" in stats
        assert "gpu_memory_used_mb" in stats
        assert "gpu_memory_limit_mb" in stats
        assert stats["loaded_count"] == 0

    @pytest.mark.asyncio
    async def test_get_model_not_found(self):
        """Test get raises ModelNotFoundError for unknown model."""
        registry = ModelRegistry()
        with pytest.raises(ModelNotFoundError):
            await registry.get("nonexistent_model")

    @pytest.mark.asyncio
    async def test_load_config_missing_file(self):
        """Test load_config handles missing file gracefully."""
        registry = ModelRegistry()
        await registry.load_config("/nonexistent/path/models.yaml")
        assert registry._loaded is True  # Should succeed with defaults

    @pytest.mark.asyncio
    async def test_unload_not_loaded(self):
        """Test unload returns False for not-loaded model."""
        registry = ModelRegistry()
        result = await registry.unload("spacy_nlp")
        assert result is False

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test shutdown clears all models."""
        registry = ModelRegistry()
        await registry.shutdown()
        assert registry.list_loaded() == []


class TestModelRegistryLoading:
    """Tests for model loading behavior."""

    @pytest.mark.asyncio
    async def test_lazy_loading_with_mock(self):
        """Test that models are loaded lazily with mocked loader."""
        registry = ModelRegistry()

        # Mock the loader
        mock_model = MagicMock()
        mock_loader = MagicMock(return_value=mock_model)

        with patch.object(registry, "_get_loader", return_value=mock_loader):
            # Model should not be loaded yet
            assert registry.is_loaded("spacy_nlp") is False

            # Get the model (triggers load)
            model = await registry.get("spacy_nlp")

            # Now it should be loaded
            assert registry.is_loaded("spacy_nlp") is True
            assert model == mock_model

    @pytest.mark.asyncio
    async def test_cached_model_returned(self):
        """Test that cached model is returned on subsequent calls."""
        registry = ModelRegistry()
        mock_model = MagicMock()
        mock_loader = MagicMock(return_value=mock_model)

        with patch.object(registry, "_get_loader", return_value=mock_loader):
            model1 = await registry.get("spacy_nlp")
            model2 = await registry.get("spacy_nlp")

            # Same model instance should be returned
            assert model1 is model2
            # Loader should only be called once
            assert mock_loader.call_count == 1

    @pytest.mark.asyncio
    async def test_memory_tracking(self):
        """Test that memory usage is tracked."""
        registry = ModelRegistry()
        mock_model = MagicMock()
        mock_loader = MagicMock(return_value=mock_model)

        with patch.object(registry, "_get_loader", return_value=mock_loader):
            initial_memory = registry._cpu_memory_used_mb
            await registry.get("spacy_nlp")

            # Memory should have increased
            assert registry._cpu_memory_used_mb > initial_memory

    @pytest.mark.asyncio
    async def test_unload_frees_memory(self):
        """Test that unload frees memory."""
        registry = ModelRegistry()
        mock_model = MagicMock()
        mock_loader = MagicMock(return_value=mock_model)

        with patch.object(registry, "_get_loader", return_value=mock_loader):
            await registry.get("spacy_nlp")
            memory_after_load = registry._cpu_memory_used_mb

            await registry.unload("spacy_nlp")

            # Memory should have decreased
            assert registry._cpu_memory_used_mb < memory_after_load
            assert registry.is_loaded("spacy_nlp") is False


class TestModelRegistryCPUFallback:
    """Tests for CPU fallback behavior."""

    @pytest.mark.asyncio
    async def test_cpu_fallback_on_cuda_failure(self):
        """Test CPU fallback when CUDA loading fails."""
        registry = ModelRegistry()

        # Get a CUDA-preferred spec
        if "sentence_transformer" in registry._specs:
            spec = registry._specs["sentence_transformer"]

            # Create loader that fails on CUDA, succeeds on CPU
            call_count = [0]

            def mock_loader(model_id, device):
                call_count[0] += 1
                if device == "cuda":
                    raise RuntimeError("CUDA not available")
                return MagicMock()

            with patch.object(registry, "_get_loader", return_value=mock_loader):
                with patch.object(registry, "_is_cuda_available", return_value=True):
                    model = await registry.get("sentence_transformer")

                    # Should have tried CUDA first, then CPU
                    assert call_count[0] == 2
                    assert model is not None


class TestModelRegistryThreadSafety:
    """Tests for thread-safety."""

    @pytest.mark.asyncio
    async def test_concurrent_access(self):
        """Test concurrent access to registry."""
        registry = ModelRegistry()
        mock_model = MagicMock()
        mock_loader = MagicMock(return_value=mock_model)

        with patch.object(registry, "_get_loader", return_value=mock_loader):
            # Run multiple concurrent gets
            tasks = [registry.get("spacy_nlp") for _ in range(10)]
            results = await asyncio.gather(*tasks)

            # All should get the same model
            assert all(r == mock_model for r in results)
            # Loader should only be called once
            assert mock_loader.call_count == 1


class TestGlobalRegistry:
    """Tests for global registry functions."""

    def test_get_model_registry_singleton(self):
        """Test that get_model_registry returns singleton."""
        # Reset global
        import k0.runtime.model_registry as module

        module._registry = None

        registry1 = get_model_registry()
        registry2 = get_model_registry()

        assert registry1 is registry2

    @pytest.mark.asyncio
    async def test_init_model_registry(self):
        """Test init_model_registry creates new registry."""
        import k0.runtime.model_registry as module

        module._registry = None

        registry = await init_model_registry(
            gpu_memory_limit_mb=2048,
            cpu_memory_limit_mb=4096,
        )

        assert registry is not None
        assert registry._gpu_memory_limit_mb == 2048
        assert registry._cpu_memory_limit_mb == 4096
