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
from typing import Any, Callable, Dict

import yaml

from .schemas import ModuleContract, ModuleID

logger = logging.getLogger(__name__)


class ModuleNotFoundError(Exception):
    """Raised when requested module is not registered."""

    pass


class ModuleLoadError(Exception):
    """Raised when module implementation fails to load."""

    pass


ModuleCallable = Callable[
    [dict, Any, Any, dict], Any
]  # (envelope, syscalls, logger, config) -> envelope


class ModuleRegistry:
    """
    Registry for module contracts and implementations.

    Responsibilities:
    1. Load module contracts from YAML files
    2. Validate contract schemas
    3. Provide lookup by module_id:version
    4. Lazy load module implementations
    5. Track module metadata for observability

    Usage:
        >>> registry = ModuleRegistry()
        >>> await registry.load_contracts("k0/contracts/modules")
        >>> module = registry.get("hippocampus.pattern_separate:v1")
        >>> result = await module(envelope, syscalls, logger, config)
    """

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._contracts: Dict[ModuleID, ModuleContract] = {}
        self._implementations: Dict[ModuleID, ModuleCallable] = {}
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

        # Check contract exists
        if module_id not in self._contracts:
            raise ModuleNotFoundError(
                f"Module not found: {module_id} (available: {list(self._contracts.keys())})"
            )

        # Return cached implementation if available
        if module_id in self._implementations:
            return self._implementations[module_id]

        # Lazy load implementation
        try:
            impl = self._load_implementation(module_id)
            self._implementations[module_id] = impl
            return impl
        except Exception as e:
            raise ModuleLoadError(f"Failed to load implementation for {module_id}: {e}") from e

    def _load_implementation(self, module_id: ModuleID) -> ModuleCallable:
        """
        Lazy load module implementation.

        Convention:
            module_id "hippocampus.pattern_separate:v1"
            -> import k0.modules.hippocampus.pattern_separate
            -> call pattern_separate.run()

        Args:
            module_id: Full module ID with version

        Returns:
            Module run function

        Raises:
            ImportError: If module cannot be imported
            AttributeError: If module doesn't have 'run' function
        """
        # Parse module_id
        base_id, version = module_id.split(":")
        domain, action = base_id.split(".", 1)

        # Construct import path: k0.modules.<domain>.<action>
        module_path = f"k0.modules.{domain}.{action}"

        logger.debug(
            f"Loading module implementation: {module_id}",
            extra={"module_id": module_id, "import_path": module_path},
        )

        # Import module
        try:
            module = importlib.import_module(module_path)
        except ImportError as e:
            raise ImportError(f"Cannot import module {module_path} for {module_id}: {e}") from e

        # Get 'run' function
        if not hasattr(module, "run"):
            raise AttributeError(f"Module {module_path} does not have 'run' function")

        run_func = getattr(module, "run")

        logger.info(
            f"Loaded module implementation: {module_id}",
            extra={"module_id": module_id, "import_path": module_path},
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

    def __len__(self) -> int:
        """Return number of registered modules."""
        return len(self._contracts)

    def __contains__(self, module_id: ModuleID) -> bool:
        """Check if module is registered."""
        if ":" not in module_id:
            module_id = f"{module_id}:v1"
        return module_id in self._contracts
