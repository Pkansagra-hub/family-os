# Configuration Provider
# Extensible configuration provider interface

"""
Configuration Provider - Extensible Configuration Management

Layer: L5 Infrastructure
Component: Extensions
Priority: 🟡 MEDIUM (Configuration extensibility)
Status: 🚧 STUB - NEEDS_IMPLEMENTATION

Architecture Decision Records:
    - ADR-0034: Extensions Framework Design

Configuration Provider Philosophy:
    - Extensible configuration sources (YAML, JSON, environment, K0, etc.)
    - Hierarchical configuration merging
    - Hot-reload capability via Module System
    - Type-safe configuration access
    - Validation and schema support

Extension Points:
    - Configuration sources (file, env, database, K0)
    - Configuration formats (YAML, JSON, TOML, HCL)
    - Configuration validation (JSON Schema, custom validators)
    - Configuration transformation (environment variable expansion, templating)

Dependencies:
    Internal:
        - k1.l5_infrastructure.modules (for hot-reload)
    External:
        - pyyaml (YAML support)
        - jsonschema (validation)

Connects To:
    Upstream:
        - All K1 components (configuration access)
    Downstream:
        - k1.l5_infrastructure.extensions (extension registry)

Observability:
    - Metrics: k1_config_provider_loads_total{source, result}
    - Metrics: k1_config_provider_load_duration_seconds{source}
    - Logs: INFO config loaded, ERROR config load failed

References:
    - Planning: docs/planning/stub_generation_plan_layer5.md (Milestone 14)
    - Test: tests/k1/l5_infrastructure/extensions/test_config_provider.py
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class ConfigurationProvider(ABC):
    """
    Abstract configuration provider interface.

    Extensions implement this to provide configuration from different sources.
    """

    @abstractmethod
    async def load_config(self, source: str) -> Dict[str, Any]:
        """
        Load configuration from source.

        Args:
            source: Configuration source identifier

        Returns:
            Configuration dictionary

        TODO(@extensions-team): Implement configuration loading
        """
        pass

    @abstractmethod
    async def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """
        Validate configuration.

        Args:
            config: Configuration to validate

        Returns:
            List of validation errors (empty if valid)

        TODO(@extensions-team): Implement configuration validation
        """
        pass


class FileConfigurationProvider(ConfigurationProvider):
    """
    File-based configuration provider (YAML, JSON).

    Supports:
        - YAML files
        - JSON files
        - File watching for hot-reload
        - Include/import directives

    TODO(@extensions-team): Implement file configuration provider
    """
    pass


class EnvironmentConfigurationProvider(ConfigurationProvider):
    """
    Environment variable configuration provider.

    Supports:
        - Environment variable mapping
        - Prefix filtering
        - Type conversion

    TODO(@extensions-team): Implement environment configuration provider
    """
    pass


class K0ConfigurationProvider(ConfigurationProvider):
    """
    K0-backed configuration provider.

    Supports:
        - Configuration stored in K0
        - Hierarchical keys
        - Versioned configurations

    TODO(@extensions-team): Implement K0 configuration provider
    """
    pass


# Global configuration manager
_config_manager: Optional['ConfigurationManager'] = None


class ConfigurationManager:
    """
    Configuration manager with extension support.

    Manages multiple configuration providers and merges configurations.

    TODO(@extensions-team): Implement configuration manager
    """

    def __init__(self):
        self.providers: List[ConfigurationProvider] = []
        self.config_cache: Dict[str, Any] = {}

    async def add_provider(self, provider: ConfigurationProvider) -> None:
        """
        Add configuration provider.

        TODO(@extensions-team): Implement provider registration
        """
        pass

    async def load_config(self, sources: List[str]) -> Dict[str, Any]:
        """
        Load and merge configuration from all sources.

        TODO(@extensions-team): Implement configuration loading and merging
        """
        pass

    async def get_config(self, key: str) -> Any:
        """
        Get configuration value by key.

        TODO(@extensions-team): Implement configuration access
        """
        pass


def get_config_manager() -> ConfigurationManager:
    """
    Get global configuration manager instance.

    TODO(@extensions-team): Implement singleton pattern
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigurationManager()
    return _config_manager


__all__ = [
    "ConfigurationProvider",
    "FileConfigurationProvider",
    "EnvironmentConfigurationProvider",
    "K0ConfigurationProvider",
    "ConfigurationManager",
    "get_config_manager",
]
