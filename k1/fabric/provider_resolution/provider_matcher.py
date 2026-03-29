"""
k1.fabric.provider_resolution.provider_matcher -- Provider Matcher (3.1.2).

Given a CapabilityContract, finds all registered providers that can
fulfill it. The primary mechanism is 1:1 matching via contract.provider_id,
but multi-provider scenarios are supported through the ProviderRegistry.

Design:
  - Usually 1 provider per capability (contract.provider_id -> ProviderConfig)
  - For multi-provider capabilities: contract.provider_id is the primary,
    additional providers can be registered separately with matching type
  - Only HEALTHY or DEGRADED providers are returned (UNHEALTHY filtered)
  - Constructor injection: requires ProviderRegistry

References:
  - fabric_discussion.md Section 9 (Resolution Pipeline, step 2)
  - Epic 3.1.2 in fabric-implementation-plan.md

Exports:
  ProviderMatcher -- Finds providers for a contract
  ProviderMatcherError -- Base exception
  NoProviderError -- No provider can fulfill the contract
"""

from __future__ import annotations

import logging
from typing import List, Union

from k1.fabric.provider_resolution.provider_registry import ProviderRegistry
from k1.fabric.types import (
    AgentContract,
    CapabilityContract,
    PromptContract,
    ProviderConfig,
    ProviderStatus,
    WorkflowContract,
)

logger = logging.getLogger(__name__)

# Type alias (same as registry.py)
ContractUnion = Union[CapabilityContract, AgentContract, PromptContract, WorkflowContract]

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ProviderMatcherError(Exception):
    """Base exception for provider matching operations."""


class NoProviderError(ProviderMatcherError):
    """Raised when no provider can fulfill a contract."""

    def __init__(self, capability_name: str, provider_id: str):
        self.capability_name = capability_name
        self.provider_id = provider_id
        super().__init__(
            f"No provider found for capability '{capability_name}' "
            f"(provider_id='{provider_id}')"
        )


# ---------------------------------------------------------------------------
# 3.1.2 -- ProviderMatcher
# ---------------------------------------------------------------------------


class ProviderMatcher:
    """
    Given a CapabilityContract, find all registered providers that can fulfill it.

    Primary matching: contract.provider_id -> ProviderRegistry.lookup_provider().
    The matcher also checks health status to skip UNHEALTHY providers.

    Constructor Args:
        provider_registry: The ProviderRegistry to query.

    Thread Safety:
        Reads only -- no mutation. Safe for concurrent calls.

    References:
        - fabric_discussion.md Section 9 (Resolution Pipeline step 2)
        - Epic 3.1.2
    """

    __slots__ = ("_provider_registry",)

    def __init__(self, *, provider_registry: ProviderRegistry) -> None:
        self._provider_registry = provider_registry

    def match(
        self,
        contract: ContractUnion,
        *,
        include_unhealthy: bool = False,
    ) -> List[ProviderConfig]:
        """
        Find all providers that can fulfill the given contract.

        Steps:
          1. Extract provider_id from contract
          2. Look up primary provider in ProviderRegistry
          3. Check health (skip UNHEALTHY unless include_unhealthy=True)
          4. Return list of matching ProviderConfigs

        For prompt contracts (no provider_id), returns an empty list since
        prompts are templates, not executable providers.

        Args:
            contract: The capability contract to match.
            include_unhealthy: If True, include unhealthy providers.

        Returns:
            List of matching ProviderConfigs (may be empty).
        """
        provider_id = getattr(contract, "provider_id", "")
        if not provider_id:
            return []

        config = self._provider_registry.lookup_provider(provider_id)
        if config is None:
            return []

        # Health filter
        if not include_unhealthy:
            try:
                health = self._provider_registry.health_check(provider_id)
                if health.status == ProviderStatus.UNHEALTHY.value:
                    logger.debug(
                        "Provider %s is UNHEALTHY, skipping for %s",
                        provider_id,
                        getattr(contract, "name", "?"),
                    )
                    return []
            except Exception:
                pass  # If health check fails, include provider anyway

        return [config]

    def match_or_raise(
        self,
        contract: ContractUnion,
        *,
        include_unhealthy: bool = False,
    ) -> List[ProviderConfig]:
        """
        Like match(), but raises NoProviderError if no providers found.

        Args:
            contract: The capability contract to match.
            include_unhealthy: If True, include unhealthy providers.

        Returns:
            Non-empty list of matching ProviderConfigs.

        Raises:
            NoProviderError: No provider found for this contract.
        """
        results = self.match(contract, include_unhealthy=include_unhealthy)
        if not results:
            name = getattr(contract, "name", "")
            pid = getattr(contract, "provider_id", "")
            raise NoProviderError(name, pid)
        return results
