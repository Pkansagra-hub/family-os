"""
Model Hub POC - Multi-Provider LLM Integration

A proof of concept implementation for integrating multiple Large Language Model providers
with a unified interface for easy switching and management.

Version: 0.1.0
"""

__version__ = "0.1.0"
__author__ = "FamilyOS Team"

from .exceptions import ConfigurationError, ModelHubError, ProviderError
from .hub import ModelHub
from .providers import ProviderRegistry

__all__ = [
    "ModelHub",
    "ProviderRegistry",
    "ModelHubError",
    "ProviderError",
    "ConfigurationError",
]
