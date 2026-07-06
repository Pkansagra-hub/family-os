"""Model Hub plugins package.

Re-exports the IProviderPlugin interface and supporting data types
for single-import convenience.
"""

from k1.model_hub.plugins.base import (
    IProviderPlugin,
    NormalizedRequest,
    ProviderChunk,
    ProviderHealth,
    ProviderResponse,
)
from k1.model_hub.plugins.deepseek_plugin import DeepSeekPlugin
from k1.model_hub.plugins.test_plugin import TestProviderPlugin

__all__ = [
    "DeepSeekPlugin",
    "IProviderPlugin",
    "NormalizedRequest",
    "ProviderChunk",
    "ProviderHealth",
    "ProviderResponse",
    "TestProviderPlugin",
]
