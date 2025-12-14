"""
Provider implementations for the Model Hub.
"""

from .anthropic import AnthropicProvider
from .base import BaseProvider, ProviderRegistry, registry
from .google import GoogleProvider
from .groq import GroqProvider
from .local import LocalProvider
from .openai import OpenAIProvider

# Register built-in providers
registry.register("openai", OpenAIProvider)
registry.register("anthropic", AnthropicProvider)
registry.register("google", GoogleProvider)
registry.register("groq", GroqProvider)
registry.register("local", LocalProvider)

__all__ = [
    "BaseProvider",
    "ProviderRegistry",
    "registry",
    "OpenAIProvider",
    "AnthropicProvider",
    "GoogleProvider",
    "GroqProvider",
    "LocalProvider",
]
