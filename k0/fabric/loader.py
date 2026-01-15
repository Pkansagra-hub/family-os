"""
Capability Loader - Load and register capabilities at boot.

This module scans capability YAML files and registers providers
with the CapabilityRegistry at application startup.

Architecture (ADR-K004):
    1. Load capability definitions from YAML files
    2. Validate against CapabilityDefinition schema
    3. Register providers with CapabilityRegistry
    4. Optionally resolve module handlers from ModuleRegistry

Related:
- k0/contracts/capabilities/core.v1.yaml: Default capability definitions
- k0/fabric/registry.py: CapabilityRegistry
- k0/runtime/module_registry.py: ModuleRegistry
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from k0.fabric.registry import get_capability_registry
from k0.runtime.schemas import CapabilityDefinition

if TYPE_CHECKING:
    from k0.fabric.registry import CapabilityRegistry
    from k0.runtime.module_registry import ModuleRegistry

logger = logging.getLogger(__name__)

# Default location for capability YAML files
CAPABILITY_CONTRACTS_DIR = Path(__file__).parent.parent / "contracts" / "capabilities"


def load_capability_definitions(
    contracts_dir: Path | None = None,
) -> dict[str, CapabilityDefinition]:
    """
    Load capability definitions from YAML files.

    Scans the contracts directory for *.yaml files and parses capability
    definitions. Files must have a 'capabilities' top-level key.

    Args:
        contracts_dir: Directory containing capability YAML files.
                       Defaults to k0/contracts/capabilities/

    Returns:
        Dict mapping capability names to CapabilityDefinition objects
    """
    contracts_dir = contracts_dir or CAPABILITY_CONTRACTS_DIR
    definitions: dict[str, CapabilityDefinition] = {}

    if not contracts_dir.exists():
        logger.warning(
            "Capability contracts directory not found: %s",
            contracts_dir,
            extra={"contracts_dir": str(contracts_dir)},
        )
        return definitions

    yaml_files = list(contracts_dir.glob("*.yaml")) + list(contracts_dir.glob("*.yml"))
    logger.info(
        "Loading capability definitions from %s (%d files)",
        contracts_dir,
        len(yaml_files),
        extra={"contracts_dir": str(contracts_dir), "file_count": len(yaml_files)},
    )

    for yaml_file in yaml_files:
        try:
            with open(yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data or "capabilities" not in data:
                logger.debug(
                    "Skipping %s: no 'capabilities' key",
                    yaml_file.name,
                    extra={"file": str(yaml_file)},
                )
                continue

            for name, defn in data["capabilities"].items():
                try:
                    definitions[name] = CapabilityDefinition.model_validate(defn)
                    logger.debug(
                        "Loaded capability definition: %s",
                        name,
                        extra={"capability": name, "file": str(yaml_file)},
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to parse capability %s in %s: %s",
                        name,
                        yaml_file.name,
                        e,
                        extra={"capability": name, "file": str(yaml_file), "error": str(e)},
                    )

        except Exception as e:
            logger.error(
                "Failed to load capability file %s: %s",
                yaml_file,
                e,
                extra={"file": str(yaml_file), "error": str(e)},
            )

    logger.info(
        "Loaded %d capability definitions",
        len(definitions),
        extra={"capability_count": len(definitions), "capabilities": list(definitions.keys())},
    )

    return definitions


def register_capabilities_from_definitions(
    definitions: dict[str, CapabilityDefinition],
    module_registry: ModuleRegistry | None = None,
    capability_registry: CapabilityRegistry | None = None,
) -> int:
    """
    Register capability providers from definitions.

    For each capability definition, registers all providers with the
    CapabilityRegistry. If a ModuleRegistry is provided, attempts to
    resolve module handlers.

    Args:
        definitions: Capability definitions loaded from YAML
        module_registry: Optional ModuleRegistry for handler resolution
        capability_registry: Optional CapabilityRegistry (defaults to global)

    Returns:
        Number of providers registered
    """
    registry = capability_registry or get_capability_registry()
    registered_count = 0
    handler_bound_count = 0

    for capability, definition in definitions.items():
        for provider in definition.providers:
            handler = None

            # Attempt to resolve module handler
            if provider.module_id and module_registry is not None:
                try:
                    # Remove version suffix for registry lookup if present
                    module_name = provider.module_id
                    if ":" not in module_name:
                        module_name = f"{module_name}:v1"

                    handler = module_registry.get(module_name)
                    handler_bound_count += 1
                    logger.debug(
                        "Resolved handler for %s: %s",
                        capability,
                        provider.module_id,
                        extra={
                            "capability": capability,
                            "module_id": provider.module_id,
                        },
                    )
                except Exception as e:
                    # Log at DEBUG level for library-only modules (algorithms without run())
                    # These are used directly by phases, not through fabric invocation
                    # Late binding: handler will be None, can be resolved later if needed
                    logger.debug(
                        "Handler not bound for %s (%s) - will use late binding: %s",
                        capability,
                        provider.module_id,
                        e,
                        extra={
                            "capability": capability,
                            "module_id": provider.module_id,
                            "resolution": "late_binding",
                        },
                    )

            # Register provider (handler may be None for late binding)
            registry.register(capability, provider, handler)
            registered_count += 1

    logger.info(
        "Registered %d capability providers for %d capabilities (%d handlers bound)",
        registered_count,
        len(definitions),
        handler_bound_count,
        extra={
            "provider_count": registered_count,
            "capability_count": len(definitions),
            "handler_bound_count": handler_bound_count,
        },
    )

    return registered_count


def discover_and_register_capabilities(
    module_registry: ModuleRegistry | None = None,
    contracts_dir: Path | None = None,
    capability_registry: CapabilityRegistry | None = None,
) -> int:
    """
    Discover and register all capabilities.

    Convenience function that loads definitions and registers providers.
    Call during app bootstrap after ModuleRegistry is initialized.

    Args:
        module_registry: Optional ModuleRegistry for handler resolution
        contracts_dir: Optional custom contracts directory
        capability_registry: Optional CapabilityRegistry (defaults to global)

    Returns:
        Number of providers registered
    """
    definitions = load_capability_definitions(contracts_dir)
    return register_capabilities_from_definitions(
        definitions,
        module_registry,
        capability_registry,
    )


def get_capability_loader_stats() -> dict[str, int]:
    """
    Get statistics about loaded capabilities.

    Returns:
        Dict with capability and provider counts
    """
    registry = get_capability_registry()
    capabilities = registry.list_capabilities()
    total_providers = sum(len(registry.list_providers(cap)) for cap in capabilities)

    return {
        "total_capabilities": len(capabilities),
        "total_providers": total_providers,
    }
