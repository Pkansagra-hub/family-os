"""
Plugin Loader - Dynamic Module Loading with Lifecycle Management

Layer: L5 Infrastructure
Component: Module System (Plugin Architecture)
Priority: M2 (Extensibility)
Status: 🚧 STUB - NEEDS_IMPLEMENTATION

Architecture Decision Records:
    - ADR-0074: Pluggable Module System (Registry, Loader, Extensions)
    - ADR-0010: Capability-Based Security (capability injection)
    - ADR-0004b: Module Dependency Management
    - ADR-0028: Actor Isolation Model (module isolation)

Dependencies:
    Internal:
        - k1.l5_infrastructure.modules.plugin_discovery (metadata, registry)
        - k1.l5_infrastructure.metrics (observability)
    External:
        - importlib (dynamic import)
        - asyncio (async lifecycle management)
        - typing (type hints)
        - logging (structured logging)

Connects To:
    Upstream:
        - k1.l5_infrastructure.modules.plugin_discovery (PluginDiscovery)
    Downstream:
        - Extension points (ConfigProvider, MetricsExporter, etc.)
        - Application code using plugins

Performance Budgets:
    - Cold load (first time): <500ms
    - Warm load (cached): <10ms
    - Hot reload: <50ms P95
    - Unload: <20ms
    - Dependency graph build: <100ms

Observability:
    - Metrics:
        - k1_plugin_load_duration_ms{module_id} (histogram)
        - k1_plugin_load_count{status} (counter)
        - k1_plugin_hot_reload_count{module_id} (counter)
        - k1_plugin_active_count (gauge)
        - k1_plugin_dependency_errors_total (counter)
    - Traces:
        - Span: plugin_loader.load
        - Attributes: module_id, version, load_time_ms, dependencies
    - Logs:
        - INFO: plugin loaded (module_id, version, load_time_ms)
        - WARNING: hot reload failed (module_id, reason)
        - ERROR: dependency load failed (module_id, dependency, reason)

References:
    - Diagram: architecture_diagrams/k1/k1_plugin_architecture.mmd
    - Whiteboard: docs/whiteboard.md (Section 13: Module System)
    - Test: tests/k1/l5_infrastructure/modules/test_plugin_loader.py
"""

import asyncio
import importlib
import logging
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
# =============================================================================
# SECTION 1: IMPORTS
# =============================================================================
# Standard library imports
from typing import TYPE_CHECKING, Any, Dict, List, Optional

# Internal imports
if TYPE_CHECKING:
    from k1.l5_infrastructure.modules.plugin_discovery import PluginDiscovery

# Configure module logger
logger = logging.getLogger(__name__)

# =============================================================================
# SECTION 2: CONSTANTS & CONFIGURATION
# =============================================================================

# TODO(@platform-team): Load from k1/config/modules.yml (ADR-0074)
# Assigned to: Issue #L5-13.2.1
DEFAULT_CONFIG = {
    # Module loading configuration
    'module_namespace': 'k1.plugins',  # Isolated namespace for plugins
    'enable_hot_reload': True,  # Support hot-reload during development
    'lazy_load': False,  # Load all dependencies upfront vs lazy

    # Performance tuning
    'load_timeout_seconds': 10,
    'dependency_max_depth': 5,  # Max dependency chain depth

    # Security
    'sandbox_modules': True,  # Run modules in restricted environment
    'verify_signatures': False,  # Digital signature verification (future)

    # Error handling
    'continue_on_dependency_failure': False,  # Stop or continue on dep failure
    'max_reload_attempts': 3,
}

# =============================================================================
# SECTION 3: TYPE DEFINITIONS & ENUMS
# =============================================================================

class LoadStatus(Enum):
    """Module load status (ADR-0074)"""
    AVAILABLE = 'AVAILABLE'  # Discovered but not loaded
    LOADING = 'LOADING'  # Currently loading
    LOADED = 'LOADED'  # Loaded successfully
    ACTIVE = 'ACTIVE'  # Initialized and ready
    INACTIVE = 'INACTIVE'  # Loaded but not active
    UNLOADING = 'UNLOADING'  # Currently unloading
    UNLOADED = 'UNLOADED'  # Explicitly unloaded
    FAILED = 'FAILED'  # Load failed


@dataclass
class LoadedModule:
    """
    Loaded plugin module instance.

    Fields:
        module_id: Module identifier
        version: Module version
        python_module: Imported Python module object
        entry_point_instance: Instantiated entry point class
        status: Current load status
        loaded_at: Load timestamp (Unix ms)
        dependencies: List of loaded dependency module_ids
        capabilities: Capabilities provided
        config: Module configuration
    """
    module_id: str
    version: str
    python_module: Any  # importlib.module
    entry_point_instance: Any  # Plugin class instance
    status: LoadStatus
    loaded_at: int
    dependencies: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LoadResult:
    """
    Result of plugin load operation.

    Fields:
        module_id: Module identifier
        version: Module version
        status: Load status (LOADED, FAILED)
        instance: Loaded module instance (if successful)
        error: Error message (if failed)
        load_time_ms: Load duration in milliseconds
        dependencies_loaded: Count of dependencies loaded
    """
    module_id: str
    version: str
    status: LoadStatus
    instance: Optional[LoadedModule] = None
    error: Optional[str] = None
    load_time_ms: float = 0.0
    dependencies_loaded: int = 0


# =============================================================================
# SECTION 4: CORE CLASSES
# =============================================================================

class PluginLoader:
    """
    Dynamic plugin loader with lifecycle management.

    Purpose:
        Load plugins at runtime with isolation, dependency injection, capability
        binding, and lifecycle management (load, activate, deactivate, unload,
        hot-reload).

    Responsibilities:
        1. Load Python modules dynamically using importlib
        2. Instantiate plugin entry point classes
        3. Inject capabilities during initialization
        4. Manage plugin lifecycle (LOADING → LOADED → ACTIVE)
        5. Handle dependencies (load in topological order)
        6. Support hot-reload for development
        7. Maintain registry of loaded modules
        8. Isolate modules in separate namespaces

    Load Process:
        1. Resolve dependencies (get from PluginDiscovery)
        2. Load dependencies recursively (topological order)
        3. Import Python module (importlib)
        4. Instantiate entry point class
        5. Inject capabilities (capability-based security)
        6. Call initialize() on plugin
        7. Register in loaded_modules dict
        8. Update status to LOADED
        9. Call activate() to transition to ACTIVE

    Unload Process:
        1. Check for dependent modules (prevent if has dependents)
        2. Call deactivate() on plugin
        3. Call shutdown() on plugin
        4. Remove from sys.modules
        5. Update status to UNLOADED

    Hot Reload Process:
        1. Call deactivate() on current instance
        2. Reimport module (importlib.reload)
        3. Reinstantiate entry point
        4. Call initialize() with previous config
        5. Call activate()

    Thread Safety: Yes (async-safe with locks)
    Async Safe: Yes (fully async)

    Performance Budget (P95):
        - Cold load: <500ms
        - Warm load: <10ms
        - Hot reload: <50ms
        - Unload: <20ms

    Examples:
        >>> discovery = PluginDiscovery()
        >>> loader = PluginLoader(discovery, config=DEFAULT_CONFIG)
        >>> result = await loader.load('datadog_exporter', '>=1.0.0')
        >>> if result.status == LoadStatus.LOADED:
        >>>     print(f"Loaded: {result.module_id} v{result.version}")

    References:
        - ADR-0074: Pluggable Module System
        - ADR-0010: Capability-Based Security
        - ADR-0028: Actor Isolation Model
    """

    def __init__(
        self,
        discovery: 'PluginDiscovery',
        config: Dict[str, Any] = DEFAULT_CONFIG,
    ) -> None:
        """
        Initialize Plugin Loader.

        Args:
            discovery: PluginDiscovery instance for metadata lookup
            config: Configuration dict with namespace, hot-reload settings

        Raises:
            ValueError: If configuration is invalid
            TypeError: If discovery is not PluginDiscovery instance

        Side Effects:
            - Initializes loaded modules registry
            - Creates metrics collectors
            - Sets up module namespace isolation

        ADR: ADR-0074 (Pluggable Module System)
        Assigned to: Issue #L5-13.2.1
        """
        # TODO(@platform-team): Implement initialization (ADR-0074)
        # 1. Validate config
        # 2. Initialize loaded modules registry
        # 3. Setup metrics collectors
        # 4. Configure namespace isolation
        self.discovery = discovery
        self.config = config
        self._logger = logger

        # Loaded modules registry
        self.loaded_modules: Dict[str, LoadedModule] = {}  # module_id -> LoadedModule

        # Load metrics
        self.total_loads = 0
        self.total_failures = 0
        self.total_hot_reloads = 0

        # Module namespace for isolation
        self.namespace = config['module_namespace']

        # Async lock for thread safety
        self._lock = asyncio.Lock()

        self._logger.info(f"PluginLoader initialized with namespace={self.namespace}")

    async def load(
        self,
        module_id: str,
        version_constraint: str = "*",
        config: Optional[Dict[str, Any]] = None,
    ) -> LoadResult:
        """
        Load module with dependencies and initialize.

        This is the primary load method that handles dependency resolution,
        module import, instantiation, capability injection, and activation.

        Args:
            module_id: Module identifier
            version_constraint: Version constraint (default: latest)
            config: Module configuration (optional)

        Returns:
            LoadResult with status, instance, and load metrics

        Raises:
            ImportError: If module cannot be imported
            TimeoutError: If load exceeds timeout
            ValueError: If dependencies cannot be resolved

        Load Steps:
            1. Get metadata from discovery registry
            2. Resolve and load dependencies recursively
            3. Import Python module (importlib.import_module)
            4. Parse entry_point (format: "module:ClassName")
            5. Instantiate entry point class
            6. Inject capabilities via constructor or setter
            7. Call initialize(config) on instance
            8. Register in loaded_modules
            9. Update status to LOADED
            10. Call activate() to transition to ACTIVE

        Observability:
            - Metrics: k1_plugin_load_duration_ms{module_id}
            - Metrics: k1_plugin_load_count{status}
            - Traces: Span name: plugin_loader.load
            - Logs: INFO: plugin loaded (module_id, version, load_time_ms)

        ADR: ADR-0074 (Pluggable Module System)
        Assigned to: Issue #L5-13.2.1
        """
        # TODO(@platform-team): Implement module loading (ADR-0074)
        # This is the core loading algorithm from ADR-0074

        start_time_ms = time.time() * 1000
        self._logger.info(f"Loading plugin: {module_id} {version_constraint}")

        async with self._lock:
            # 1. Get metadata
            metadata = await self.discovery.get_module(module_id, version_constraint)
            if not metadata:
                error_msg = f"Module not found: {module_id} {version_constraint}"
                self._logger.error(error_msg)
                return LoadResult(
                    module_id=module_id,
                    version="unknown",
                    status=LoadStatus.FAILED,
                    error=error_msg,
                    load_time_ms=time.time() * 1000 - start_time_ms,
                )

            # Check if already loaded
            if module_id in self.loaded_modules:
                existing = self.loaded_modules[module_id]
                if existing.status in [LoadStatus.LOADED, LoadStatus.ACTIVE]:
                    self._logger.info(f"Module already loaded: {module_id} v{existing.version}")
                    return LoadResult(
                        module_id=module_id,
                        version=existing.version,
                        status=existing.status,
                        instance=existing,
                        load_time_ms=time.time() * 1000 - start_time_ms,
                    )

            # 2. Load dependencies first
            dependencies_loaded = 0
            for dep in metadata.dependencies:
                if not dep.optional:
                    dep_result = await self.load(dep.module_id, dep.version_constraint)
                    if dep_result.status == LoadStatus.FAILED:
                        error_msg = f"Dependency load failed: {dep.module_id}"
                        self._logger.error(error_msg)
                        if not self.config['continue_on_dependency_failure']:
                            return LoadResult(
                                module_id=module_id,
                                version=metadata.version,
                                status=LoadStatus.FAILED,
                                error=error_msg,
                                load_time_ms=time.time() * 1000 - start_time_ms,
                            )
                    else:
                        dependencies_loaded += 1

            # 3. Import Python module
            try:
                # Parse entry_point: "module_path:ClassName"
                module_path, class_name = metadata.entry_point.split(':')

                # Import module dynamically
                python_module = importlib.import_module(module_path)

                # Get entry point class
                entry_point_class = getattr(python_module, class_name)

                # 4. Instantiate with config
                if config is None:
                    config = {}

                instance = entry_point_class(config)

                # 5. Call initialize() if available
                if hasattr(instance, 'initialize'):
                    await instance.initialize()

                # 6. Register loaded module
                loaded_module = LoadedModule(
                    module_id=module_id,
                    version=metadata.version,
                    python_module=python_module,
                    entry_point_instance=instance,
                    status=LoadStatus.LOADED,
                    loaded_at=int(time.time() * 1000),
                    dependencies=[dep.module_id for dep in metadata.dependencies],
                    capabilities=metadata.capabilities,
                    config=config,
                )

                self.loaded_modules[module_id] = loaded_module

                # 7. Activate if available
                if hasattr(instance, 'activate'):
                    await instance.activate()
                    loaded_module.status = LoadStatus.ACTIVE

                end_time_ms = time.time() * 1000
                load_time_ms = end_time_ms - start_time_ms

                self.total_loads += 1

                self._logger.info(
                    f"Plugin loaded successfully: {module_id} v{metadata.version} "
                    f"in {load_time_ms:.2f}ms"
                )

                return LoadResult(
                    module_id=module_id,
                    version=metadata.version,
                    status=LoadStatus.LOADED,
                    instance=loaded_module,
                    load_time_ms=load_time_ms,
                    dependencies_loaded=dependencies_loaded,
                )

            except Exception as e:
                error_msg = f"Failed to load module {module_id}: {e}"
                self._logger.error(error_msg)
                self.total_failures += 1

                return LoadResult(
                    module_id=module_id,
                    version=metadata.version,
                    status=LoadStatus.FAILED,
                    error=error_msg,
                    load_time_ms=time.time() * 1000 - start_time_ms,
                )

    async def unload(self, module_id: str) -> bool:
        """
        Unload module and cleanup resources.

        Args:
            module_id: Module identifier

        Returns:
            True if unloaded successfully, False otherwise

        Raises:
            ValueError: If module has active dependents

        Unload Steps:
            1. Check for dependent modules (fail if has dependents)
            2. Call deactivate() on plugin
            3. Call shutdown() on plugin
            4. Remove from sys.modules
            5. Remove from loaded_modules registry
            6. Update status to UNLOADED

        Performance:
            - <20ms P95

        ADR: ADR-0074 (Pluggable Module System)
        Assigned to: Issue #L5-13.2.1
        """
        # TODO(@platform-team): Implement module unloading (ADR-0074)

        async with self._lock:
            if module_id not in self.loaded_modules:
                self._logger.warning(f"Module not loaded: {module_id}")
                return False

            loaded = self.loaded_modules[module_id]

            # Check for dependents
            dependents = self._get_dependents(module_id)
            if dependents:
                raise ValueError(
                    f"Cannot unload module {module_id}: has active dependents {dependents}"
                )

            try:
                # Call deactivate if available
                if hasattr(loaded.entry_point_instance, 'deactivate'):
                    await loaded.entry_point_instance.deactivate()

                # Call shutdown if available
                if hasattr(loaded.entry_point_instance, 'shutdown'):
                    await loaded.entry_point_instance.shutdown()

                # Remove from sys.modules
                module_name = loaded.python_module.__name__
                if module_name in sys.modules:
                    del sys.modules[module_name]

                # Remove from registry
                loaded.status = LoadStatus.UNLOADED
                del self.loaded_modules[module_id]

                self._logger.info(f"Plugin unloaded: {module_id}")
                return True

            except Exception as e:
                self._logger.error(f"Failed to unload module {module_id}: {e}")
                return False

    async def hot_reload_plugin(self, module_id: str) -> LoadResult:
        """
        Hot-reload plugin (unload + reload without stopping dependents).

        Args:
            module_id: Module identifier

        Returns:
            LoadResult with reload status

        Hot Reload Process:
            1. Check if module is loaded
            2. Call deactivate() but keep in memory
            3. Reimport module (importlib.reload)
            4. Reinstantiate entry point with previous config
            5. Call initialize() with previous config
            6. Call activate()
            7. Update loaded_modules registry

        Performance:
            - <50ms P95 (faster than full unload + load)

        Use Cases:
            - Development: Update plugin code without restart
            - Production: Fix bugs without downtime (if safe)

        ADR: ADR-0074 (Pluggable Module System)
        Assigned to: Issue #L5-13.2.1
        """
        # TODO(@platform-team): Implement hot-reload (ADR-0074)

        start_time_ms = time.time() * 1000
        self._logger.info(f"Hot-reloading plugin: {module_id}")

        async with self._lock:
            if module_id not in self.loaded_modules:
                error_msg = f"Module not loaded: {module_id}"
                self._logger.error(error_msg)
                return LoadResult(
                    module_id=module_id,
                    version="unknown",
                    status=LoadStatus.FAILED,
                    error=error_msg,
                    load_time_ms=time.time() * 1000 - start_time_ms,
                )

            loaded = self.loaded_modules[module_id]
            previous_config = loaded.config

            try:
                # 1. Deactivate current instance
                if hasattr(loaded.entry_point_instance, 'deactivate'):
                    await loaded.entry_point_instance.deactivate()

                # 2. Reload Python module
                reloaded_module = importlib.reload(loaded.python_module)

                # 3. Reinstantiate entry point
                entry_point_parts = loaded.entry_point_instance.__class__.__name__
                entry_point_class = getattr(reloaded_module, entry_point_parts)
                new_instance = entry_point_class(previous_config)

                # 4. Initialize and activate
                if hasattr(new_instance, 'initialize'):
                    await new_instance.initialize()

                if hasattr(new_instance, 'activate'):
                    await new_instance.activate()

                # 5. Update registry
                loaded.python_module = reloaded_module
                loaded.entry_point_instance = new_instance
                loaded.status = LoadStatus.ACTIVE
                loaded.loaded_at = int(time.time() * 1000)

                end_time_ms = time.time() * 1000
                reload_time_ms = end_time_ms - start_time_ms

                self.total_hot_reloads += 1

                self._logger.info(
                    f"Plugin hot-reloaded successfully: {module_id} "
                    f"in {reload_time_ms:.2f}ms"
                )

                return LoadResult(
                    module_id=module_id,
                    version=loaded.version,
                    status=LoadStatus.LOADED,
                    instance=loaded,
                    load_time_ms=reload_time_ms,
                )

            except Exception as e:
                error_msg = f"Hot-reload failed for {module_id}: {e}"
                self._logger.error(error_msg)

                return LoadResult(
                    module_id=module_id,
                    version=loaded.version,
                    status=LoadStatus.FAILED,
                    error=error_msg,
                    load_time_ms=time.time() * 1000 - start_time_ms,
                )

    async def get_loaded_modules(self) -> List[LoadedModule]:
        """
        Get list of currently loaded modules.

        Returns:
            List of LoadedModule instances

        ADR: ADR-0074 (Pluggable Module System)
        Assigned to: Issue #L5-13.2.1
        """
        # TODO(@platform-team): Implement loaded modules list (ADR-0074)
        return list(self.loaded_modules.values())

    async def get_module_status(self, module_id: str) -> Optional[LoadStatus]:
        """
        Get current status of a module.

        Args:
            module_id: Module identifier

        Returns:
            LoadStatus or None if not loaded

        ADR: ADR-0074 (Pluggable Module System)
        Assigned to: Issue #L5-13.2.1
        """
        # TODO(@platform-team): Implement status lookup (ADR-0074)
        if module_id in self.loaded_modules:
            return self.loaded_modules[module_id].status
        return None

    # =========================================================================
    # PRIVATE METHODS (Implementation Details)
    # =========================================================================

    def _get_dependents(self, module_id: str) -> List[str]:
        """
        Get list of modules that depend on this module.

        Args:
            module_id: Module identifier

        Returns:
            List of dependent module_ids

        ADR: ADR-0074
        """
        # TODO(@platform-team): Implement dependent tracking (ADR-0074)
        dependents = []
        for loaded_id, loaded_module in self.loaded_modules.items():
            if module_id in loaded_module.dependencies:
                dependents.append(loaded_id)
        return dependents

    async def _unload_no_deps(self, module_id: str) -> bool:
        """
        Unload module without checking dependents (internal use).

        Args:
            module_id: Module identifier

        Returns:
            True if unloaded successfully

        ADR: ADR-0074
        """
        # TODO(@platform-team): Implement unload without dep check (ADR-0074)
        # Used internally by hot_reload
        return await self.unload(module_id)


# =============================================================================
# SECTION 5: HELPER FUNCTIONS
# =============================================================================

def parse_entry_point(entry_point: str) -> tuple[str, str]:
    """
    Parse entry point string into module path and class name.

    Args:
        entry_point: Entry point string (format: "module.path:ClassName")

    Returns:
        Tuple of (module_path, class_name)

    Examples:
        >>> parse_entry_point("datadog_plugin:DatadogExporter")
        ('datadog_plugin', 'DatadogExporter')

    ADR: ADR-0074
    Assigned to: Issue #L5-13.2.1
    """
    # TODO(@platform-team): Implement entry point parsing (ADR-0074)
    if ':' not in entry_point:
        raise ValueError(f"Invalid entry point format: {entry_point}")

    module_path, class_name = entry_point.split(':', 1)
    return module_path, class_name


# =============================================================================
# SECTION 6: MODULE EXPORTS & INITIALIZATION
# =============================================================================

__all__ = [
    'PluginLoader',
    'LoadedModule',
    'LoadResult',
    'LoadStatus',
]


# =============================================================================
# OBSERVABILITY INTEGRATION
# =============================================================================
# Metrics to export:
#   - k1_plugin_load_duration_ms{module_id} - Load duration histogram
#   - k1_plugin_load_count{status} - Load attempts counter
#   - k1_plugin_hot_reload_count{module_id} - Hot reload counter
#   - k1_plugin_active_count - Currently active plugins gauge
#   - k1_plugin_dependency_errors_total - Dependency resolution failures
#
# Traces to generate:
#   - Span name: plugin_loader.load
#   - Attributes: module_id, version, load_time_ms, dependencies_loaded
#
# Logs to emit:
#   - Level: INFO (plugin loaded), WARNING (hot reload failed), ERROR (dependency load failed)
#   - Fields: module_id, version, load_time_ms, dependencies, error
#
# =============================================================================

# =============================================================================
# TESTING REQUIREMENTS (pytest Framework)
# =============================================================================
# Integration tests required:
#   - tests/k1/l5_infrastructure/modules/test_plugin_loader.py
#   - Load tests (single module, with dependencies)
#   - Unload tests (check dependents, cleanup)
#   - Hot-reload tests (verify state preservation)
#   - Performance budget tests (ensure <500ms cold, <10ms warm, <50ms reload)
#   - Isolation tests (verify namespace separation)
#
# No simulation code allowed:
#   - No asyncio.sleep() for testing timeouts
#   - Use real plugin modules or pytest fixtures
#   - Integration tests > unit tests
#
# =============================================================================
