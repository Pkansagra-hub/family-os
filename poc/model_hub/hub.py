"""
Main Model Hub implementation.
"""

from typing import AsyncIterator, List, Optional

from .config import config
from .exceptions import ConfigurationError, ProviderError
from .model_types import GenerateRequest, GenerateResponse, StreamChunk
from .providers import registry


class ModelHub:
    """Main interface for interacting with multiple LLM providers."""

    def __init__(self):
        self._providers = {}
        self._load_configured_providers()

    def _load_configured_providers(self):
        """Load providers based on configuration."""
        for provider_name in config.list_configured_providers():
            try:
                provider_config = config.get_provider_config(provider_name)
                provider = registry.create_provider(provider_name, provider_config)
                self._providers[provider_name] = provider
            except Exception as e:
                # Log warning but continue - provider might not be available
                print(f"Warning: Failed to load provider '{provider_name}': {e}")

    async def generate(
        self,
        provider: str,
        model: Optional[str] = None,
        prompt: Optional[str] = None,
        **kwargs,
    ) -> GenerateResponse:
        """
        Generate text using the specified provider.

        Args:
            provider: Name of the provider (e.g., 'openai', 'anthropic')
            model: Model name (uses default if not specified)
            prompt: Text prompt for generation
            **kwargs: Additional generation parameters

        Returns:
            GenerateResponse with generated text and metadata
        """
        if provider not in self._providers:
            raise ProviderError(
                provider, f"Provider '{provider}' not configured or available"
            )

        provider_instance = self._providers[provider]

        # Use default model if not specified
        if model is None:
            model = provider_instance.get_default_model()

        # Ensure model is a string
        model = str(model)

        # Build request
        request = GenerateRequest(prompt=prompt or "", model=model, **kwargs)

        return await provider_instance.generate(request)

    async def stream_generate(
        self,
        provider: str,
        model: Optional[str] = None,
        prompt: Optional[str] = None,
        **kwargs,
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream text generation using the specified provider.

        Args:
            provider: Name of the provider
            model: Model name (uses default if not specified)
            prompt: Text prompt for generation
            **kwargs: Additional generation parameters

        Yields:
            StreamChunk objects with text chunks
        """
        if provider not in self._providers:
            raise ProviderError(
                provider, f"Provider '{provider}' not configured or available"
            )

        provider_instance = self._providers[provider]

        # Use default model if not specified
        if model is None:
            model = provider_instance.get_default_model()

        # Ensure model is a string
        model = str(model)

        # Build request
        request = GenerateRequest(prompt=prompt or "", model=model, **kwargs)

        async for chunk in provider_instance.stream_generate(request):
            yield chunk

    def list_providers(self) -> List[str]:
        """List all configured and available providers."""
        return list(self._providers.keys())

    def get_default_model(self, provider: str) -> str:
        """Get the default model for a provider."""
        if provider not in self._providers:
            raise ProviderError(
                provider, f"Provider '{provider}' not configured or available"
            )

        return self._providers[provider].get_default_model()

    def validate_config(self):
        """Validate all provider configurations."""
        config.validate_config()

        # Validate that providers can be instantiated
        for provider_name in config.list_configured_providers():
            try:
                provider_config = config.get_provider_config(provider_name)
                registry.create_provider(provider_name, provider_config)
            except Exception as e:
                raise ConfigurationError(
                    f"Failed to validate provider '{provider_name}': {e}"
                )

    async def close(self):
        """Close all provider connections."""
        for provider in self._providers.values():
            if hasattr(provider, "close"):
                await provider.close()

        self._providers.clear()

    # Context manager support
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
