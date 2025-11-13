"""
Base provider interface and registry.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Type

from ..exceptions import ProviderError
from ..model_types import GenerateRequest, GenerateResponse, ProviderConfig, StreamChunk


class BaseProvider(ABC):
    """Abstract base class for all LLM providers."""

    def __init__(self, config: ProviderConfig):
        self.config = config

    @abstractmethod
    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        """Generate text using the provider."""
        pass

    @abstractmethod
    async def stream_generate(
        self, request: GenerateRequest
    ) -> AsyncIterator[StreamChunk]:
        """Stream text generation using the provider."""
        pass

    @abstractmethod
    def get_default_model(self) -> str:
        """Get the default model name for this provider."""
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Get the provider name."""
        pass

    async def validate_config(self) -> None:
        """Validate provider configuration."""
        if not self.config.api_key and self.provider_name in [
            "openai",
            "anthropic",
            "google",
        ]:
            raise ProviderError(self.provider_name, "API key is required")


class ProviderRegistry:
    """Registry for managing provider implementations."""

    def __init__(self):
        self._providers: Dict[str, Type[BaseProvider]] = {}

    def register(self, name: str, provider_class: Type[BaseProvider]):
        """Register a provider implementation."""
        self._providers[name] = provider_class

    def get_provider_class(self, name: str) -> Type[BaseProvider]:
        """Get a provider class by name."""
        if name not in self._providers:
            raise ProviderError(name, f"Provider '{name}' not registered")
        return self._providers[name]

    def list_providers(self) -> list[str]:
        """List all registered providers."""
        return list(self._providers.keys())

    def create_provider(self, name: str, config: ProviderConfig) -> BaseProvider:
        """Create a provider instance."""
        provider_class = self.get_provider_class(name)
        return provider_class(config)


# Global registry instance
registry = ProviderRegistry()
