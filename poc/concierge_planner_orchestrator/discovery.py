"""
Capability Discovery
=====================

Bridge between the Planner and the Fabric registry.

Loads real tool contracts from k1/contracts/tools/ and formats
them for the Planner LLM to reason about.

Two usage modes:
  1. Bulk: load_capability_catalog() + filter_capabilities_by_domain()
  2. Handler: create_discovery_handler() returns a callable for the
     Planner's agentic loop (discover_capabilities tool)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List

import yaml

logger = logging.getLogger(__name__)

# Default contracts directory
DEFAULT_CONTRACTS_DIR = Path("k1/contracts/tools")


def load_capability_catalog(
    contracts_dir: Path = DEFAULT_CONTRACTS_DIR,
) -> List[Dict[str, Any]]:
    """
    Load tool contracts from YAML files and format for Planner.

    Reads every .yaml file in the contracts directory and extracts
    the capability metadata the Planner needs to build plans.

    Args:
        contracts_dir: Path to the contracts/tools/ directory.

    Returns:
        List of capability dicts with name, description, inputs, etc.
    """
    capabilities: List[Dict[str, Any]] = []

    if not contracts_dir.exists():
        logger.warning("Contracts directory not found: %s", contracts_dir)
        return capabilities

    for yaml_file in sorted(contracts_dir.glob("*.yaml")):
        try:
            with open(yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data:
                continue

            contract = data.get("tool_contract", {})
            if not contract:
                continue

            name = contract.get("name", "")
            if not name:
                continue

            # Skip Planner/Fabric internal tools (not user-facing)
            # NOTE: build_agent is discoverable -- it's an Orchestrator DAG
            # step that the Planner can include in plans (PLAN-06).
            if name in (
                "tool.read.discover_capabilities",
                "tool.read.find_prompts",
            ):
                continue

            cap = {
                "name": name,
                "description": contract.get("description", "").strip(),
                "domain": contract.get("domain", []),
                "capabilities": contract.get("capabilities", []),
                "required_inputs": contract.get("required_inputs", []),
                "optional_inputs": contract.get("optional_inputs", []),
                "provider_type": contract.get("provider_type", ""),
                "safety_band_min": contract.get("safety_band_min", "GREEN"),
            }
            capabilities.append(cap)

            logger.debug("Loaded capability: %s", name)

        except Exception as exc:
            logger.warning("Failed to load contract %s: %s", yaml_file, exc)

    logger.info("Loaded %d capabilities from %s", len(capabilities), contracts_dir)
    return capabilities


def filter_capabilities_by_domain(
    capabilities: List[Dict[str, Any]],
    domains: List[str],
) -> List[Dict[str, Any]]:
    """
    Filter capabilities to those relevant for the given domains.

    Args:
        capabilities: Full capability catalog.
        domains: Domain tags to filter by (e.g., ["WEATHER", "RECIPES"]).

    Returns:
        Capabilities with at least one domain overlap.
        If domains is empty or contains "GENERAL", returns all.
    """
    if not domains or "GENERAL" in domains:
        return capabilities

    domain_set = {d.upper() for d in domains}
    return [
        cap
        for cap in capabilities
        if domain_set.intersection({d.upper() for d in cap.get("domain", [])})
    ]


def create_discovery_handler(
    contracts_dir: Path = DEFAULT_CONTRACTS_DIR,
) -> Callable[..., List[Dict[str, Any]]]:
    """
    Create a discovery handler for the Planner's agentic loop.

    The handler is called when the LLM invokes discover_capabilities(domain, intent).
    It loads the full catalog (cached on first call) and filters by domain.

    Args:
        contracts_dir: Path to the contracts/tools/ directory.

    Returns:
        Callable that accepts (domain=..., intent=...) and returns
        a list of capability dicts.
    """
    # Cache the full catalog on first call
    _catalog_cache: List[Dict[str, Any]] = []

    def handler(domain: str = "", intent: str = "", **kwargs: Any) -> List[Dict[str, Any]]:
        """
        Discover capabilities by domain and/or intent.

        This is what runs when the Planner LLM calls discover_capabilities.
        """
        nonlocal _catalog_cache

        if not _catalog_cache:
            _catalog_cache.extend(load_capability_catalog(contracts_dir))
            logger.info(
                "[Discovery] Loaded %d capabilities from %s",
                len(_catalog_cache),
                contracts_dir,
            )

        if domain:
            filtered = filter_capabilities_by_domain(_catalog_cache, [domain])
            logger.info(
                "[Discovery] domain='%s' intent='%s' -> %d capabilities",
                domain,
                intent,
                len(filtered),
            )
            return filtered
        else:
            logger.info(
                "[Discovery] domain=ALL intent='%s' -> %d capabilities",
                intent,
                len(_catalog_cache),
            )
            return _catalog_cache

    return handler
