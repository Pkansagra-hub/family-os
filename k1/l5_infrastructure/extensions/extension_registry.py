# Extension Registry
# Central registry for extension points with lifecycle management

"""
Extension Registry - Extensions Framework Core

Layer: L5 Infrastructure
Component: Extensions
Priority: 🔴 CRITICAL (Framework foundation)
Status: 🚧 STUB - NEEDS_IMPLEMENTATION

Architecture Decision Records:
    - ADR-0034: Extensions Framework Design

Extension Registry Philosophy:
    - Central registry for all extension points
    - Lifecycle management (register → load → activate → validate)
    - Interface compliance validation
    - Dependency resolution and ordering
    - State tracking and health monitoring

Extension Points:
    - config_provider: Configuration sources
    - metrics_exporter: Metrics export destinations
    - trace_exporter: Trace export destinations
    - log_handler: Logging destinations
    - thermal_policy: Thermal management policies
    - placement_strategy: Model placement algorithms
    - storage_tier: Storage backend implementations
    - circuit_breaker_strategy: Resilience strategies
    - security_policy: Access control policies
    - performance_optimizer: Performance optimization

Dependencies:
    Internal:
        - k1.l5_infrastructure.modules (for hot-reload)
    External:
        - typing (type hints)

Connects To:
    Upstream:
        - k1.l5_infrastructure.modules (plugin loading)
    Downstream:
        - All extension implementations (registration)

Observability:
    - Metrics: k1_extension_registry_extensions_total{state}
    - Metrics: k1_extension_registry_operations_total{operation, result}
    - Logs: INFO extension registered, WARN validation failed

References:
    - Planning: docs/planning/stub_generation_plan_layer5.md (Milestone 14)
    - Test: tests/k1/l5_infrastructure/extensions/test_extension_registry.py
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Type


class ExtensionState(Enum):
    """Extension lifecycle states."""
    REGISTERED = "registered"      # Discovered, not loaded
    INITIALIZING = "initializing"  # Loading and configuring
    ACTIVE = "active"             # Ready to use
    INACTIVE = "inactive"         # Disabled by configuration
    FAILED = "failed"             # Load/validation failed
    UNLOADING = "unloading"       # Cleanup in progress
    UNLOADED = "unloaded"         # Removed from registry


class Extension(ABC):
    """
    Base class for all extensions.

    All extensions must implement this interface plus their specific extension point interface.
    """

    @property
    @abstractmethod
    def extension_point(self) -> str:
        """
        Return extension point name.

        Returns:
            Extension point identifier (e.g., 'config_provider')
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Return extension name.

        Returns:
            Unique extension name (e.g., 'vault_config_provider')
        """
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """
        Return extension version.

        Returns:
            Semantic version string (e.g., '1.0.0')
        """
        pass

    @property
    @abstractmethod
    def api_version(self) -> str:
        """
        Return required K1 API version.

        Returns:
            K1 API version this extension requires
        """
        pass

    @property
    @abstractmethod
    def dependencies(self) -> List[str]:
        """
        Return list of required extensions.

        Returns:
            List of extension names this extension depends on
        """
        pass

    @abstractmethod
    async def initialize(self, config: Dict[str, Any]) -> None:
        """
        Initialize extension with configuration.

        Args:
            config: Extension-specific configuration

        TODO(@extensions-team): Implement extension initialization
        """
        pass

    @abstractmethod
    async def activate(self) -> None:
        """
        Activate extension (start background tasks if needed).

        TODO(@extensions-team): Implement extension activation
        """
        pass

    @abstractmethod
    async def deactivate(self) -> None:
        """
        Deactivate extension (stop background tasks).

        TODO(@extensions-team): Implement extension deactivation
        """
        pass

    @abstractmethod
    async def validate(self) -> bool:
        """
        Validate extension state (connectivity, permissions).

        Returns:
            True if extension is healthy and functional

        TODO(@extensions-team): Implement extension validation
        """
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """
        Cleanup when extension unloads.

        TODO(@extensions-team): Implement extension shutdown
        """
        pass


class ExtensionPointDefinition:
    """
    Definition of an extension point.

    TODO(@extensions-team): Implement extension point definition structure
    """
    pass


class ExtensionMetadata:
    """
    Metadata for a registered extension.

    TODO(@extensions-team): Implement extension metadata structure
    """
    pass


# Custom exceptions
class ExtensionRegistryError(Exception):
    """Base exception for extension registry errors."""
    pass


class ExtensionPointNotFoundError(ExtensionRegistryError):
    """Raised when extension point is not registered."""
    pass


class InterfaceComplianceError(ExtensionRegistryError):
    """Raised when extension doesn't implement required interface."""
    pass


class DuplicateExtensionError(ExtensionRegistryError):
    """Raised when trying to register duplicate extension."""
    pass


class ExtensionNotFoundError(ExtensionRegistryError):
    """Raised when extension is not found."""
    pass


class ActivationError(ExtensionRegistryError):
    """Raised when extension activation fails."""
    pass


class UnresolvedDependencyError(ExtensionRegistryError):
    """Raised when extension dependency cannot be resolved."""
    pass


class CircularDependencyError(ExtensionRegistryError):
    """Raised when circular dependency is detected."""
    pass


class ExtensionRegistry:
    """
    Central extension point registry.

    Manages extension points, extension registration, lifecycle, and dependency resolution.
    """

    def __init__(self):
        self.extension_points: Dict[str, ExtensionPointDefinition] = {}
        self.extensions: Dict[str, ExtensionMetadata] = {}

    async def register_extension_point(
        self,
        name: str,
        interface: Type,
        required: bool = False,
        multiple: bool = False,
        default_impl: Optional[Extension] = None
    ) -> None:
        """
        Register a new extension point with required interface.

        Args:
            name: Extension point name (e.g., "config_provider")
            interface: Abstract base class defining extension interface
            required: If True, K1 won't start without an implementation
            multiple: If True, multiple implementations can coexist
            default_impl: Built-in default implementation (fallback)

        TODO(@extensions-team): Implement extension point registration
        """
        pass

    async def register_extension(
        self,
        extension: Extension,
        extension_point: str
    ) -> None:
        """
        Register an extension instance for a point.

        Args:
            extension: Extension instance (must implement Extension + point interface)
            extension_point: Target extension point name

        Raises:
            ExtensionPointNotFoundError: If point not registered
            InterfaceComplianceError: If extension doesn't implement interface
            DuplicateExtensionError: If multiple=False and already registered

        TODO(@extensions-team): Implement extension registration with validation
        """
        pass

    async def get_extension(
        self,
        extension_point: str,
        name: Optional[str] = None
    ) -> Extension:
        """
        Get extension by point and name.

        Args:
            extension_point: Extension point name
            name: Extension name (if None, return first active)

        Returns:
            Extension instance

        Raises:
            ExtensionNotFoundError: If not found/active

        TODO(@extensions-team): Implement extension retrieval
        """
        pass

    async def list_extensions(
        self,
        extension_point: Optional[str] = None
    ) -> List[Extension]:
        """
        List all extensions (optionally filtered by point).

        Args:
            extension_point: Filter by point (None = all)

        Returns:
            List of Extension instances

        TODO(@extensions-team): Implement extension listing
        """
        pass

    async def activate_extension(self, name: str) -> None:
        """
        Activate an extension (move to ACTIVE state).

        Args:
            name: Extension name

        Raises:
            ExtensionNotFoundError: If not found
            ActivationError: If initialization fails

        TODO(@extensions-team): Implement extension activation
        """
        pass

    async def deactivate_extension(self, name: str) -> None:
        """
        Deactivate an extension (move to INACTIVE state).

        Args:
            name: Extension name

        TODO(@extensions-team): Implement extension deactivation
        """
        pass

    async def validate_extension(self, name: str) -> bool:
        """
        Validate extension state (connectivity, permissions, etc.).

        Args:
            name: Extension name

        Returns:
            True if valid, False otherwise

        TODO(@extensions-team): Implement extension validation
        """
        pass

    async def resolve_dependencies(self, name: str) -> List[Extension]:
        """
        Resolve extension dependencies in load order.

        Args:
            name: Extension name

        Returns:
            List of extensions in dependency order

        Raises:
            UnresolvedDependencyError: If dependency not found
            CircularDependencyError: If circular dependency detected

        TODO(@extensions-team): Implement dependency resolution
        """
        pass

    async def get_registry_snapshot(self) -> Dict[str, Any]:
        """
        Get current registry state (extension count, statuses, health).

        Returns:
            Snapshot with total_extensions, status_breakdown, health_status

        TODO(@extensions-team): Implement registry snapshot
        """
        pass

    async def unregister_extension(self, name: str) -> None:
        """
        Unregister an extension.

        Args:
            name: Extension name

        TODO(@extensions-team): Implement extension unregistration
        """
        pass

    async def get_extension_state(self, name: str) -> ExtensionState:
        """
        Get current state of an extension.

        Args:
            name: Extension name

        Returns:
            Current extension state

        TODO(@extensions-team): Implement state retrieval
        """
        pass

    async def list_extension_points(self) -> List[str]:
        """
        List all registered extension points.

        Returns:
            List of extension point names

        TODO(@extensions-team): Implement extension point listing
        """
        pass


# Global extension registry instance
_extension_registry: Optional[ExtensionRegistry] = None


def get_extension_registry() -> ExtensionRegistry:
    """
    Get global extension registry instance.

    TODO(@extensions-team): Implement singleton pattern
    """
    global _extension_registry
    if _extension_registry is None:
        _extension_registry = ExtensionRegistry()
    return _extension_registry


__all__ = [
    "ExtensionState",
    "Extension",
    "ExtensionPointDefinition",
    "ExtensionMetadata",
    "ExtensionRegistryError",
    "ExtensionPointNotFoundError",
    "InterfaceComplianceError",
    "DuplicateExtensionError",
    "ExtensionNotFoundError",
    "ActivationError",
    "UnresolvedDependencyError",
    "CircularDependencyError",
    "ExtensionRegistry",
    "get_extension_registry",
]
