"""
Component Registry - Process-Global Component Registration for Dashboard

Provides centralized registration and status tracking for all system components.
Used by IntegrationDashboard to display accurate health status.

Design:
- Process-global singleton (not per-instance)
- Components register on init with register_component()
- Components update status with set_status()
- Dashboard reads from this single source of truth

Usage:
    from monitoring.component_registry import get_component_registry

    registry = get_component_registry()

    # On component init
    registry.register_component("Concierge Agent", concierge_instance)
    registry.set_status("Concierge Agent", "RUNNING")

    # Optional heartbeat
    registry.heartbeat("Concierge Agent")

    # Dashboard reads
    status = registry.get_status("Concierge Agent")
"""

import time
from dataclasses import dataclass, field
from typing import Dict, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ComponentState:
    """Component state information"""

    name: str
    status: str = "STARTING"  # STARTING/RUNNING/DEGRADED/SHUTTING_DOWN/UNKNOWN/DOWN
    p95_ms: Optional[float] = None
    details: Optional[str] = None
    last_heartbeat: float = field(default_factory=lambda: time.time())


class ComponentRegistry:
    """
    Process-global component registry for health monitoring.

    Thread-safe singleton that tracks all system components.
    """

    _inst: Optional["ComponentRegistry"] = None
    _lock = None  # Will be initialized in __init__

    def __init__(self):
        """Initialize registry state"""
        if not hasattr(self, "_m"):
            import threading

            # Initialize lock only once
            if ComponentRegistry._lock is None:
                ComponentRegistry._lock = threading.Lock()

            self._m: Dict[str, ComponentState] = {}
            logger.info("[ComponentRegistry] Initialized")

    @classmethod
    def inst(cls) -> "ComponentRegistry":
        """Get singleton instance (thread-safe)"""
        import threading

        if cls._lock is None:
            cls._lock = threading.Lock()

        with cls._lock:
            if cls._inst is None:
                cls._inst = cls.__new__(cls)
                cls._inst.__init__()
            return cls._inst

    def register(self, name: str) -> None:
        """
        Register a component for monitoring.

        Args:
            name: Component name (e.g., "Concierge Agent", "DeltaBus")
        """
        if name in self._m:
            logger.debug("component_already_registered", name=name)
        else:
            self._m[name] = ComponentState(name=name)
            logger.debug("component_registered", name=name)

    def set(
        self, name: str, status: str, p95_ms: Optional[float] = None, details: Optional[str] = None
    ) -> None:
        """
        Update component status.

        Args:
            name: Component name
            status: Status string (RUNNING, DEGRADED, SHUTTING_DOWN, etc.)
            p95_ms: Optional P95 latency in milliseconds
            details: Optional details string
        """
        import time

        c = self._m.setdefault(name, ComponentState(name=name))
        c.status = status
        c.last_heartbeat = time.time()

        if p95_ms is not None:
            c.p95_ms = p95_ms

        if details is not None:
            c.details = details

        logger.debug(
            "component_status_updated", name=name, status=status, p95_ms=p95_ms, details=details
        )

    def all(self) -> list:
        """Get all component states as list."""
        return list(self._m.values())

    def heartbeat(self, name: str) -> None:
        """
        Record heartbeat for component.

        Args:
            name: Component name
        """
        if name not in self._m:
            logger.warning("heartbeat_for_unregistered_component", name=name, action="ignoring")
            return

        self._m[name].last_heartbeat = time.time()
        logger.debug("component_heartbeat", name=name)

    def get_status(self, name: str) -> Optional[ComponentState]:
        """
        Get component status.

        Args:
            name: Component name

        Returns:
            ComponentState or None if not registered
        """
        return self._m.get(name)

    def get_all_components(self) -> Dict[str, ComponentState]:
        """
        Get all registered components.

        Returns:
            Dict of name → ComponentState
        """
        return self._m.copy()

    def unregister_component(self, name: str) -> bool:
        """
        Unregister a component.

        Args:
            name: Component name

        Returns:
            True if unregistered, False if not found
        """
        if name in self._m:
            del self._m[name]
            logger.debug("component_unregistered", name=name)
            return True
        return False

    def clear(self) -> None:
        """Clear all registered components (for testing)"""
        self._m.clear()
        logger.info("[ComponentRegistry] Cleared")

    # ===== Backwards compatibility with old API =====
    def register_component(self, name: str, handle=None) -> None:
        """Legacy API: register component with optional handle (ignored)"""
        self.register(name)

    def set_status(
        self, name: str, status: str, p95_ms: Optional[float] = None, details: Optional[str] = None
    ) -> None:
        """Legacy API: update component status"""
        self.set(name, status, p95_ms=p95_ms, details=details)


# Global singleton accessor
def get_component_registry() -> ComponentRegistry:
    """
    Get process-global ComponentRegistry instance.

    Returns:
        ComponentRegistry singleton
    """
    return ComponentRegistry.inst()
