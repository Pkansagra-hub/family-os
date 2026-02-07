"""
k1.fabric.provider_resolution -- Provider Resolution Engine (Subsystem 4).

Maps CapabilityRequest.name to a concrete provider. Exact-match lookup,
not semantic search. Serves Role 2 (Execution).

Exports:
  ProviderRegistry -- Maps provider_id to ProviderConfig
  ProviderRegistryError -- Base exception for registry operations
  DuplicateProviderError -- Duplicate provider_id
  ProviderNotFoundError -- provider_id not found
  ProviderMatcher -- Finds providers for a contract
  ProviderMatcherError -- Base exception for matching
  NoProviderError -- No provider can fulfill contract
  ProviderSelector -- Deterministic provider selection
  ProviderSelectorError -- Base exception for selection
  AllProvidersRejectedError -- All candidates rejected by policy
  NoCandidatesError -- No candidates provided
  ScoredCandidate -- Intermediate scored-candidate type
  ProviderFactory -- Instantiates provider handlers from ProviderConfig
  ProviderFactoryError -- Base exception for factory operations
  UnsupportedProviderTypeError -- No handler for provider type
  ProviderInstantiationError -- Handler constructor failed
  CapabilityProvider -- Protocol interface for all providers
  Resolver -- Full resolution pipeline (5 steps)
  ResolverError -- Base exception for resolution
  ResolutionFailedError -- Resolution pipeline failed
  PolicyEnginePort -- Optional policy engine protocol
"""

from k1.fabric.provider_resolution.provider_factory import (
    CapabilityProvider,
    ProviderFactory,
    ProviderFactoryError,
    ProviderInstantiationError,
    UnsupportedProviderTypeError,
)
from k1.fabric.provider_resolution.provider_matcher import (
    NoProviderError,
    ProviderMatcher,
    ProviderMatcherError,
)
from k1.fabric.provider_resolution.provider_registry import (
    DuplicateProviderError,
    ProviderNotFoundError,
    ProviderRegistry,
    ProviderRegistryError,
)
from k1.fabric.provider_resolution.provider_selector import (
    AllProvidersRejectedError,
    NoCandidatesError,
    ProviderSelector,
    ProviderSelectorError,
    ScoredCandidate,
)
from k1.fabric.provider_resolution.resolver import (
    PolicyEnginePort,
    ResolutionFailedError,
    Resolver,
    ResolverError,
)

__all__ = [
    "ProviderRegistry",
    "ProviderRegistryError",
    "DuplicateProviderError",
    "ProviderNotFoundError",
    "ProviderMatcher",
    "ProviderMatcherError",
    "NoProviderError",
    "ProviderSelector",
    "ProviderSelectorError",
    "AllProvidersRejectedError",
    "NoCandidatesError",
    "ScoredCandidate",
    "ProviderFactory",
    "ProviderFactoryError",
    "UnsupportedProviderTypeError",
    "ProviderInstantiationError",
    "CapabilityProvider",
    "Resolver",
    "ResolverError",
    "ResolutionFailedError",
    "PolicyEnginePort",
]
