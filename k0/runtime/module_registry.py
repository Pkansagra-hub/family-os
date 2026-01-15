"""
Module Registry - Switchboard for Module Discovery and Lookup

This registry loads module contracts from k0/contracts/modules/*.yaml and provides
a centralized lookup mechanism for module implementations.

Architecture:
- Single source of truth for module metadata
- Lazy loading of module implementations
- Contract validation at startup
- Version-aware lookup

Related:
- MIGRATION_PLAN.md: Phase 2 - Module Registry
- k0/runtime/schemas.py: ModuleContract definition
- k0/modules/: Module implementations
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict

import yaml

from .schemas import ModuleContract, ModuleID

logger = logging.getLogger(__name__)


class ModuleNotFoundError(Exception):
    """Raised when requested module is not registered."""

    pass


class ModuleLoadError(Exception):
    """Raised when module implementation fails to load."""

    pass


ModuleCallable = Callable[..., Awaitable[Any]]
"""
Module function signature.

Expected signature:
    async def run(
        message: BusMessage,
        context: PipelineContext,
        **config: Any,
    ) -> dict[str, Any]:
        ...

Args:
    message: Incoming BusMessage event
    context: PipelineContext with syscalls, logger, config
    **config: Stage-specific configuration overrides

Returns:
    Enriched envelope (dict) with module outputs
"""


class ModuleRegistry:
    """
    Registry for module contracts and implementations.

    Responsibilities:
    1. Load module contracts from YAML files
    2. Validate contract schemas
    3. Provide lookup by module_id:version
    4. Lazy load module implementations
    5. Track module metadata for observability
    6. Index fabric_capabilities for capability-based lookup

    Usage:
        >>> registry = ModuleRegistry()
        >>> await registry.load_contracts("k0/contracts/modules")
        >>> module = registry.get("hippocampus.pattern_separate:v1")
        >>> result = await module(envelope, syscalls, logger, config)

        # Capability-based lookup (Issue 2.2.1)
        >>> modules = registry.resolve_capability("pattern_separate")
        >>> for module_id in modules:
        ...     handler = registry.get(module_id)
    """

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._contracts: Dict[ModuleID, ModuleContract] = {}
        self._implementations: Dict[ModuleID, ModuleCallable] = {}
        self._capability_index: Dict[str, list[str]] = {}  # capability → [module_ids]
        self._loaded = False

    async def load_contracts(self, contracts_dir: str | Path) -> None:
        """
        Load all module contracts from directory.

        Scans for *.yaml files matching pattern: <module_id>.v<version>.yaml

        Args:
            contracts_dir: Path to k0/contracts/modules/

        Raises:
            FileNotFoundError: If contracts directory doesn't exist
            ValueError: If contract fails validation
        """
        contracts_path = Path(contracts_dir)
        if not contracts_path.exists():
            logger.warning(
                f"Module contracts directory not found: {contracts_path}",
                extra={"contracts_dir": str(contracts_path)},
            )
            return

        contract_files = list(contracts_path.glob("*.yaml")) + list(contracts_path.glob("*.yml"))

        logger.info(
            f"Loading module contracts from {contracts_path}",
            extra={"contracts_dir": str(contracts_path), "file_count": len(contract_files)},
        )

        for contract_file in contract_files:
            try:
                await self._load_single_contract(contract_file)
            except Exception as e:
                logger.error(
                    f"Failed to load contract {contract_file.name}: {e}",
                    extra={"file": str(contract_file), "error": str(e)},
                    exc_info=True,
                )
                # Continue loading other contracts
                continue

        self._loaded = True
        logger.info(
            f"Loaded {len(self._contracts)} module contracts",
            extra={"count": len(self._contracts), "modules": list(self._contracts.keys())},
        )

    async def _load_single_contract(self, contract_file: Path) -> None:
        """Load and validate a single module contract."""
        with open(contract_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # Validate with Pydantic
        contract = ModuleContract(**data)

        # Store by full_id (module_id:version)
        full_id = contract.full_id
        if full_id in self._contracts:
            logger.warning(
                f"Duplicate module contract: {full_id} (overwriting)",
                extra={"module_id": full_id, "file": str(contract_file)},
            )

        self._contracts[full_id] = contract

        # Issue 2.2.1: Auto-register fabric_capabilities
        if contract.fabric_capabilities:
            for capability in contract.fabric_capabilities:
                self.register_capability(capability, full_id)
            logger.debug(
                f"Registered {len(contract.fabric_capabilities)} capabilities for {full_id}",
                extra={
                    "module_id": full_id,
                    "capabilities": contract.fabric_capabilities,
                },
            )

        logger.debug(
            f"Loaded contract: {full_id}",
            extra={
                "module_id": full_id,
                "latency_budget_ms": contract.latency_budget_ms,
                "idempotent": contract.idempotent,
            },
        )

    def get(self, module_id: ModuleID) -> ModuleCallable:
        """
        Get module implementation by ID.

        Args:
            module_id: Full module ID (e.g., "hippocampus.pattern_separate:v1")

        Returns:
            Async callable module function

        Raises:
            ModuleNotFoundError: If module not registered
            ModuleLoadError: If implementation fails to load
        """
        # Add default version if not specified
        if ":" not in module_id:
            module_id = f"{module_id}:v1"

        # Return cached implementation if available
        if module_id in self._implementations:
            return self._implementations[module_id]

        # Lazy load implementation (contract validation is optional)
        # We allow loading modules even if contracts failed validation
        try:
            impl = self._load_implementation(module_id)
            self._implementations[module_id] = impl

            # Warn if contract not loaded (non-blocking)
            if module_id not in self._contracts:
                logger.warning(
                    f"Module loaded without contract validation: {module_id}",
                    extra={
                        "module_id": module_id,
                        "reason": "contract validation failed or missing",
                    },
                )

            return impl
        except Exception as e:
            raise ModuleLoadError(f"Failed to load implementation for {module_id}: {e}") from e

    # Subdirectory search paths for place-agnostic module resolution
    # Order matters: more specific paths first, then common locations
    _SUBDIRECTORY_SEARCH_PATHS: list[str] = [
        "",  # Direct path: k0.modules.<domain>.<action>
        "algorithms",  # k0.modules.<domain>.algorithms.<action>
        "staging",  # k0.modules.<domain>.staging.<action>
        "truth_writer",  # k0.modules.<domain>.truth_writer.<action>
        "emission",  # k0.modules.<domain>.emission.<action>
    ]

    def _load_implementation(self, module_id: ModuleID) -> ModuleCallable:
        """
        Lazy load module implementation with place-agnostic resolution.

        Tries multiple paths to find the module, making it location-independent.
        This allows modules to be organized in subdirectories (algorithms/, staging/, etc.)
        without requiring exact path specification in contracts.

        Search order:
            1. k0.modules.<domain>.<action> (direct)
            2. k0.modules.<domain>.algorithms.<action>
            3. k0.modules.<domain>.staging.<action>
            4. k0.modules.<domain>.truth_writer.<action>
            5. k0.modules.<domain>.emission.<action>

        Convention:
            module_id "consolidation.hebbian_learner:v1"
            -> tries k0.modules.consolidation.hebbian_learner
            -> tries k0.modules.consolidation.algorithms.hebbian_learner (found!)
            -> call hebbian_learner.run()

        Args:
            module_id: Full module ID with version

        Returns:
            Module run function

        Raises:
            ImportError: If module cannot be imported from any search path
            AttributeError: If module doesn't have 'run' function
        """
        # Parse module_id
        base_id, version = module_id.split(":")
        domain, action = base_id.split(".", 1)

        # Try each search path until we find the module
        module = None
        tried_paths: list[str] = []
        successful_path: str = ""

        for subdir in self._SUBDIRECTORY_SEARCH_PATHS:
            if subdir:
                module_path = f"k0.modules.{domain}.{subdir}.{action}"
            else:
                module_path = f"k0.modules.{domain}.{action}"

            tried_paths.append(module_path)

            try:
                module = importlib.import_module(module_path)
                successful_path = module_path
                logger.debug(
                    f"Found module at: {module_path}",
                    extra={"module_id": module_id, "import_path": module_path},
                )
                break
            except ImportError:
                # Try next path
                continue

        if module is None:
            raise ImportError(
                f"Cannot import module for {module_id}. " f"Tried paths: {tried_paths}"
            )

        # Get 'run' function
        if not hasattr(module, "run"):
            raise AttributeError(
                f"Module {successful_path} does not have 'run' function. "
                f"Available attributes: {[a for a in dir(module) if not a.startswith('_')]}"
            )

        run_func = getattr(module, "run")

        logger.debug(
            f"Loaded module implementation: {module_id}",
            extra={
                "module_id": module_id,
                "resolved_path": successful_path,
                "tried_paths": tried_paths,
            },
        )

        return run_func

    def get_contract(self, module_id: ModuleID) -> ModuleContract:
        """
        Get module contract by ID.

        Args:
            module_id: Full module ID (e.g., "hippocampus.pattern_separate:v1")

        Returns:
            ModuleContract with metadata

        Raises:
            ModuleNotFoundError: If module not registered
        """
        # Add default version if not specified
        if ":" not in module_id:
            module_id = f"{module_id}:v1"

        if module_id not in self._contracts:
            raise ModuleNotFoundError(
                f"Module not found: {module_id} (available: {list(self._contracts.keys())})"
            )

        return self._contracts[module_id]

    def list_modules(self) -> list[ModuleID]:
        """Return list of all registered module IDs."""
        return list(self._contracts.keys())

    def is_loaded(self) -> bool:
        """Check if contracts have been loaded."""
        return self._loaded

    # =========================================================================
    # Issue 2.2.1: Capability Index Methods
    # =========================================================================

    def register_capability(self, capability: str, module_id: str) -> None:
        """
        Register a module as provider for a capability.

        Args:
            capability: Capability name (e.g., "pattern_separate")
            module_id: Full module ID (e.g., "hippocampus.pattern_separate:v1")
        """
        if capability not in self._capability_index:
            self._capability_index[capability] = []
        if module_id not in self._capability_index[capability]:
            self._capability_index[capability].append(module_id)
            logger.debug(
                f"Registered capability: {capability} -> {module_id}",
                extra={"capability": capability, "module_id": module_id},
            )

    def unregister_capability(self, capability: str, module_id: str) -> bool:
        """
        Unregister a module from a capability.

        Args:
            capability: Capability name
            module_id: Module ID to remove

        Returns:
            True if module was found and removed
        """
        if capability not in self._capability_index:
            return False
        if module_id in self._capability_index[capability]:
            self._capability_index[capability].remove(module_id)
            logger.debug(
                f"Unregistered capability: {capability} -> {module_id}",
                extra={"capability": capability, "module_id": module_id},
            )
            return True
        return False

    def resolve_capability(self, capability: str) -> list[str]:
        """
        Return module IDs that provide a capability.

        Args:
            capability: Capability name to resolve

        Returns:
            List of module IDs (may be empty if no providers)
        """
        return list(self._capability_index.get(capability, []))

    def list_capabilities(self) -> list[str]:
        """Return list of all registered capabilities."""
        return list(self._capability_index.keys())

    def get_capability_stats(self) -> dict[str, int]:
        """Return capability index statistics."""
        return {
            "total_capabilities": len(self._capability_index),
            "total_mappings": sum(len(v) for v in self._capability_index.values()),
        }

    def __len__(self) -> int:
        """Return number of registered modules."""
        return len(self._contracts)

    def __contains__(self, module_id: ModuleID) -> bool:
        """Check if module is registered."""
        if ":" not in module_id:
            module_id = f"{module_id}:v1"
        return module_id in self._contracts


# =============================================================================
# Global Module Registry Singleton (Issue 2.2.1)
# =============================================================================

_module_registry: ModuleRegistry | None = None


def get_module_registry() -> ModuleRegistry:
    """
    Get the global module registry singleton.

    The registry is lazily created on first access. Use set_module_registry()
    to inject a pre-configured registry (e.g., during app boot).

    Returns:
        Global ModuleRegistry instance
    """
    global _module_registry
    if _module_registry is None:
        _module_registry = ModuleRegistry()
    return _module_registry


def set_module_registry(registry: ModuleRegistry) -> None:
    """
    Set the global module registry.

    Use during app bootstrap to inject a fully initialized registry.

    Args:
        registry: ModuleRegistry instance to use globally
    """
    global _module_registry
    _module_registry = registry


def reset_module_registry() -> None:
    """Reset the global registry (for testing)."""
    global _module_registry
    _module_registry = None
