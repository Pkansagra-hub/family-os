"""
k1.fabric.core.registry -- Capability Registry (Subsystem 2) + Lifecycle (4.5.6).

The in-memory indexed catalog of all loaded contracts. Both Retrieval
(Role 1) and Resolution (Role 2) query the Registry. It is the single
source of truth for what capabilities exist, how to invoke them, and
their current state.

Data Structures (2.2.1):
  by_name:        dict[str, ContractUnion]   O(1) name lookup
  by_domain:      dict[str, list[ContractUnion]]  inverted domain index
  by_type:        dict[str, list[ContractUnion]]  grouped by type prefix
  by_provider:    dict[str, list[ContractUnion]]  grouped by provider_id
  metadata_cache: dict[str, ContractMetadata]     hot cache

Lifecycle Tracking (4.5.6):
  _created_agents: dict[str, ContractUnion]  -- agents created at runtime
  register_created_agent()  -- track a runtime-created agent
  list_created_agents()     -- defensive copy of created agents
  remove_expired_agents()   -- bulk-remove session-scoped ephemeral agents
  is_created_agent()        -- check if a name is a created agent

Thread Safety:
  All mutations guarded by RLock. Reads are concurrent-safe because
  Python dict reads are atomic at the bytecode level and we only ever
  do atomic reference swaps on list entries.

Design Decisions:
  - FAB-12: All contracts validated against schema before registration
  - FAB-11: Capability names follow type conventions
  - Constructor injection for validator and event_port (5.3.1)
  - Frozen contracts: update_availability / update_metrics replace
    the contract object (copy-on-write via dataclasses.replace)
  - Event port is Optional: when None, events are silently skipped
    (enables standalone testing without bus wiring)

References:
  - fabric_discussion.md Section 7 (complete data structures and API)
  - Epic 2.2 in fabric-implementation-plan.md

Exports:
  CapabilityRegistry -- Central hub of the Fabric
  ContractMetadata -- Hot-cache metadata per contract
  RegistryHealth -- Health snapshot returned by health()
  CreatedAgentRecord -- Lifecycle metadata for created agents (4.5.6)
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple, Union

from k1.fabric.core.contract_validator import ContractValidator
from k1.fabric.metrics import get_default_metrics
from k1.fabric.types import (
    AgentContract,
    Availability,
    CapabilityContract,
    CapabilityType,
    CapabilityVersion,
    CapabilityVersionError,
    PromptContract,
    WorkflowContract,
)

logger = logging.getLogger(__name__)

# Type alias for all contract types stored in the registry.
# CapabilityContract is the base; AgentContract extends it.
# PromptContract and WorkflowContract are separate hierarchies.
ContractUnion = Union[CapabilityContract, AgentContract, PromptContract, WorkflowContract]


# ---------------------------------------------------------------------------
# Event Port Protocol (duck-typed to avoid hard dependency on SessionState)
# ---------------------------------------------------------------------------


class EventPort(Protocol):
    """
    Minimal protocol for event emission.

    Matches IEventPort.emit() signature from k1/sessionstate/ports/events.py.
    Using Protocol allows the Registry to accept any event bus implementation
    without importing SessionState.
    """

    def emit(self, event_type: str, payload: Any) -> None:
        """Emit an event to the bus."""
        ...


# ---------------------------------------------------------------------------
# 2.2.1 -- ContractMetadata (hot-cache entry)
# ---------------------------------------------------------------------------


@dataclass
class ContractMetadata:
    """
    Hot-cache metadata for a registered contract.

    Stores derived / frequently-accessed data that callers need
    without deserializing the full contract. Mutable (not frozen)
    because update_availability and update_metrics mutate it.

    Attributes:
        name: Canonical capability name (primary key).
        contract_type: Type prefix (e.g. 'tool.execute', 'agent.spawn').
        domain_tags: Copy of domain[] from contract.
        provider_id: Provider identifier.
        provider_type: Provider type string (MCP, WASM, BRIDGE, AGENT, ...).
        availability: Current availability (ONLINE/DEGRADED/OFFLINE).
        safety_band_min: Minimum safety band to invoke.
        avg_latency_ms: Rolling average latency.
        success_rate_30d: Rolling 30-day success rate.
        total_invocations_30d: Rolling 30-day invocation count.
        registered_at_ns: Monotonic timestamp of registration (for age queries).
    """

    name: str = ""
    contract_type: Optional[str] = None
    domain_tags: List[str] = field(default_factory=list)
    provider_id: str = ""
    provider_type: str = ""
    availability: str = Availability.ONLINE.value
    safety_band_min: str = "GREEN"
    avg_latency_ms: int = 0
    success_rate_30d: float = 0.0
    total_invocations_30d: int = 0
    registered_at_ns: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for health / debug endpoints."""
        return {
            "name": self.name,
            "contract_type": self.contract_type,
            "domain_tags": list(self.domain_tags),
            "provider_id": self.provider_id,
            "provider_type": self.provider_type,
            "availability": self.availability,
            "safety_band_min": self.safety_band_min,
            "avg_latency_ms": self.avg_latency_ms,
            "success_rate_30d": self.success_rate_30d,
            "total_invocations_30d": self.total_invocations_30d,
            "registered_at_ns": self.registered_at_ns,
        }


# ---------------------------------------------------------------------------
# 2.2.8 -- RegistryHealth (returned by health())
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegistryHealth:
    """
    Snapshot of registry health, returned by CapabilityRegistry.health().

    Attributes:
        total_capabilities: Total number of registered contracts.
        by_type_counts: Count of capabilities per type prefix.
        by_availability_counts: Count per availability status.
        index_size_bytes: Approximate memory footprint of all indexes.
        last_reload_at: ISO 8601 timestamp of last full reload, or empty.
    """

    total_capabilities: int = 0
    by_type_counts: Dict[str, int] = field(default_factory=dict)
    by_availability_counts: Dict[str, int] = field(default_factory=dict)
    index_size_bytes: int = 0
    last_reload_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "total_capabilities": self.total_capabilities,
            "by_type_counts": dict(self.by_type_counts),
            "by_availability_counts": dict(self.by_availability_counts),
            "index_size_bytes": self.index_size_bytes,
            "last_reload_at": self.last_reload_at,
        }


# ---------------------------------------------------------------------------
# Event topic constants
# ---------------------------------------------------------------------------

EVENT_CAPABILITY_REGISTERED = "k1.fabric.capability.registered.v1"
EVENT_CAPABILITY_UNREGISTERED = "k1.fabric.capability.unregistered.v1"
EVENT_AVAILABILITY_CHANGED = "k1.fabric.capability.availability.changed.v1"
EVENT_METRICS_UPDATED = "k1.fabric.capability.metrics.updated.v1"
EVENT_REGISTRY_RELOADED = "k1.fabric.registry.reloaded.v1"
EVENT_VERSION_CONFLICT = "k1.fabric.capability.version.conflict.v1"
EVENT_VERSION_UPGRADED = "k1.fabric.capability.version.upgraded.v1"


# ---------------------------------------------------------------------------
# 4.5.6 -- CreatedAgentRecord (lifecycle metadata)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CreatedAgentRecord:
    """
    Lifecycle metadata for a runtime-created agent (4.5.6).

    Stored in CapabilityRegistry._created_agents alongside the contract
    in the main index.  Tracks how and when the agent was created, and
    whether it should be cleaned up on session end.

    Attributes:
        name: Agent capability name (matches the contract key).
        ephemeral: If True, the agent is removed on session end.
        created_by: Creator identifier (e.g. "orchestrator").
        created_at_iso: ISO 8601 creation timestamp.
        session_scoped: If True, tied to the originating session.
    """

    name: str
    ephemeral: bool = True
    created_by: str = ""
    created_at_iso: str = ""
    session_scoped: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "name": self.name,
            "ephemeral": self.ephemeral,
            "created_by": self.created_by,
            "created_at_iso": self.created_at_iso,
            "session_scoped": self.session_scoped,
        }


# ---------------------------------------------------------------------------
# 2.2.1-2.2.4 -- CapabilityRegistry
# ---------------------------------------------------------------------------


class CapabilityRegistryError(Exception):
    """Base exception for registry operations."""


class DuplicateCapabilityError(CapabilityRegistryError):
    """Raised when registering a capability name that already exists."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Capability already registered: {name}")


class CapabilityNotFoundError(CapabilityRegistryError):
    """Raised when a capability name is not in the registry."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Capability not found: {name}")


class VersionConflictError(CapabilityRegistryError):
    """Raised on unresolvable version conflict (same name + same version)."""

    def __init__(self, name: str, version: str):
        self.name = name
        self.version = version
        super().__init__(f"Version conflict: '{name}' version {version} already registered")


class VersionRegressionError(CapabilityRegistryError):
    """Raised when registering an older compatible version (regression)."""

    def __init__(self, name: str, old_version: str, new_version: str):
        self.name = name
        self.old_version = old_version
        self.new_version = new_version
        super().__init__(
            f"Version regression: '{name}' {new_version} is older than " f"existing {old_version}"
        )


class CapabilityRegistry:
    """
    In-memory indexed catalog of all loaded capability contracts.

    This is the central hub of the Fabric. Nearly every subsystem depends
    on it. Both Retrieval (Role 1) and Resolution (Role 2) query the
    Registry to discover and resolve capabilities.

    Constructor Args:
        validator: ContractValidator for pre-registration validation.
            If None, a default instance is created.
        event_port: Optional event bus for emitting lifecycle events.
            If None, events are silently skipped. Conforms to the
            EventPort protocol (emit(event_type, payload)).

    Thread Safety:
        All mutations (register, unregister, update_*) acquire self._lock
        (RLock). Reads (lookup, list_by_*) are safe without locking because
        they perform single dict lookups on stable references.

    References:
        - fabric_discussion.md Section 7
        - Epic 2.2 issues 2.2.1-2.2.8
    """

    __slots__ = (
        "_lock",
        "_validator",
        "_event_port",
        "_by_name",
        "_by_domain",
        "_by_type",
        "_by_provider",
        "_by_version",
        "_metadata_cache",
        "_last_reload_at",
        "_created_agents",
    )

    def __init__(
        self,
        *,
        validator: Optional[ContractValidator] = None,
        event_port: Optional[EventPort] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._validator = validator or ContractValidator()
        self._event_port = event_port

        # ---- 2.2.1: Core indexes ----
        # O(1) exact-match by canonical name
        self._by_name: Dict[str, ContractUnion] = {}

        # Inverted domain index: domain_tag -> [contracts]
        self._by_domain: Dict[str, List[ContractUnion]] = {}

        # Grouped by capability type prefix: "tool.execute" -> [contracts]
        self._by_type: Dict[str, List[ContractUnion]] = {}

        # Grouped by provider_id: provider_id -> [contracts]
        self._by_provider: Dict[str, List[ContractUnion]] = {}

        # 2.4.2: Version index -- name -> { version_str -> contract }
        self._by_version: Dict[str, Dict[str, ContractUnion]] = {}

        # Hot cache of frequently-accessed metadata
        self._metadata_cache: Dict[str, ContractMetadata] = {}

        # Audit: last full reload timestamp
        self._last_reload_at: str = ""

        # 4.5.6: Lifecycle tracking for runtime-created agents
        self._created_agents: Dict[str, CreatedAgentRecord] = {}

    # ======================================================================
    # 2.2.2 -- register() / unregister()
    # ======================================================================

    def register(
        self,
        contract: ContractUnion,
        *,
        skip_validation: bool = False,
    ) -> None:
        """
        Add a contract to the registry.

        Steps:
          1. Validate contract via ContractValidator (unless skip_validation)
          2. Version conflict resolution (2.4.2):
             a) same name + same version -> REJECT (VersionConflictError)
             b) same name + newer compatible (same major) -> UPGRADE
             c) same name + different major -> REGISTER BOTH (multi-version)
             d) same name + older compatible version -> REJECT (VersionRegressionError)
             e) new name -> normal registration
          3. Insert into all indexes
          4. Create metadata cache entry
          5. Emit lifecycle event

        Args:
            contract: A validated contract (CapabilityContract, AgentContract,
                PromptContract, or WorkflowContract).
            skip_validation: If True, skip ContractValidator validation.
                Only for internal use (e.g. reload after prior validation).

        Raises:
            ContractValidationError: Contract fails schema or semantic rules.
            DuplicateCapabilityError: Name already registered and no version.
            VersionConflictError: Same name + exact same version.
            VersionRegressionError: Same name + older compatible version.
        """
        name = _get_contract_name(contract)

        # Phase 1: Validate
        if not skip_validation:
            self._validate_contract(contract)

        version_str = _get_contract_field(contract, "version", "")

        with self._lock:
            if name in self._by_name:
                # ---- 2.4.2: Version conflict resolution ----
                existing = self._by_name[name]
                existing_ver_str = _get_contract_field(existing, "version", "")

                # If either contract has no version, fall back to legacy dup check
                if not version_str or not existing_ver_str:
                    raise DuplicateCapabilityError(name)

                try:
                    new_ver = CapabilityVersion.parse(version_str)
                    old_ver = CapabilityVersion.parse(existing_ver_str)
                except CapabilityVersionError:
                    # Unparseable version: revert to duplicate rejection
                    raise DuplicateCapabilityError(name)

                if new_ver == old_ver:
                    # Rule (a): same version -> REJECT
                    raise VersionConflictError(name, version_str)

                if new_ver.is_compatible_with(old_ver):
                    if new_ver > old_ver:
                        # Rule (b): newer compatible -> UPGRADE in-place
                        self._do_upgrade(name, existing, contract)
                        # Emit upgrade event outside lock below
                        self._emit(
                            EVENT_VERSION_UPGRADED,
                            {
                                "name": name,
                                "old_version": str(old_ver),
                                "new_version": str(new_ver),
                            },
                        )
                        logger.info(
                            "Upgraded capability: %s  %s -> %s",
                            name,
                            old_ver,
                            new_ver,
                        )
                        return
                    else:
                        # Rule (d): older compatible -> REJECT (regression)
                        raise VersionRegressionError(name, existing_ver_str, version_str)
                else:
                    # Rule (c): different major -> REGISTER BOTH
                    # Store the new contract under a versioned key
                    versioned_key = f"{name}@{new_ver.major}"
                    if versioned_key in self._by_name:
                        # That major slot is taken, run conflict again
                        raise VersionConflictError(name, version_str)
                    self._by_name[versioned_key] = contract
                    self._insert_domain_index(contract)
                    self._insert_type_index(contract)
                    self._insert_provider_index(contract)
                    self._insert_version_index(name, version_str, contract)
                    self._metadata_cache[versioned_key] = _build_metadata(contract)

                    self._emit(
                        EVENT_CAPABILITY_REGISTERED,
                        {
                            "name": versioned_key,
                            "version": version_str,
                            "domain": _get_contract_field(contract, "domain", []),
                            "provider_type": _get_contract_provider_type(contract),
                            "multi_version": True,
                        },
                    )
                    logger.info(
                        "Registered multi-version capability: %s (major=%d)",
                        name,
                        new_ver.major,
                    )
                    return

            # ---- Normal registration (no conflict) ----
            self._by_name[name] = contract
            self._insert_domain_index(contract)
            self._insert_type_index(contract)
            self._insert_provider_index(contract)
            if version_str:
                self._insert_version_index(name, version_str, contract)

            # Metadata cache
            self._metadata_cache[name] = _build_metadata(contract)

        # Emit event (outside lock to avoid deadlocks)
        self._emit(
            EVENT_CAPABILITY_REGISTERED,
            {
                "name": name,
                "version": version_str,
                "domain": _get_contract_field(contract, "domain", []),
                "provider_type": _get_contract_provider_type(contract),
            },
        )

        self._record_registration_metrics()
        logger.debug("Registered capability: %s (v%s)", name, version_str or "unversioned")

    def unregister(self, name: str) -> bool:
        """
        Remove a contract from the registry by canonical name.

        Also removes any versioned keys (name@major) and cleans _by_version.

        Args:
            name: Canonical capability name (e.g. "tool.execute.weather").

        Returns:
            True if the contract was found and removed, False if not found.
        """
        with self._lock:
            contract = self._by_name.pop(name, None)
            if contract is None:
                return False

            self._remove_domain_index(contract)
            self._remove_type_index(contract)
            self._remove_provider_index(contract)
            self._remove_version_index(name, contract)
            self._metadata_cache.pop(name, None)

            # Remove any versioned keys (e.g. name@2, name@3)
            versioned_keys = [k for k in self._by_name if k.startswith(f"{name}@")]
            for vk in versioned_keys:
                vc = self._by_name.pop(vk, None)
                if vc is not None:
                    self._remove_domain_index(vc)
                    self._remove_type_index(vc)
                    self._remove_provider_index(vc)
                    self._remove_version_index(name, vc)
                    self._metadata_cache.pop(vk, None)

        # Emit event (outside lock)
        self._emit(EVENT_CAPABILITY_UNREGISTERED, {"name": name})
        self._refresh_registry_size_gauges()
        logger.debug("Unregistered capability: %s", name)
        return True

    # ======================================================================
    # 2.2.3 -- lookup()
    # ======================================================================

    def lookup(
        self,
        name: str,
        *,
        version: Optional[str] = None,
    ) -> Optional[ContractUnion]:
        """
        O(1) exact-match lookup by canonical capability name.

        If *version* is provided, looks up the exact version in the
        _by_version index instead of _by_name.

        Args:
            name: Canonical capability name.
            version: Optional exact version string (e.g. "2.1.0").

        Returns:
            The contract if found, None otherwise.
        """
        start = time.perf_counter()
        try:
            if version is not None:
                versions = self._by_version.get(name)
                if versions is None:
                    return None
                return versions.get(version)
            return self._by_name.get(name)
        finally:
            try:
                get_default_metrics().observe_registry_lookup(time.perf_counter() - start)
            except Exception:
                logger.warning("Failed to record registry lookup metric", exc_info=True)

    def contains(self, name: str) -> bool:
        """Check if a capability name is registered."""
        return name in self._by_name

    # ======================================================================
    # 2.4.3 -- Version-aware lookup methods
    # ======================================================================

    def lookup_latest(self, name: str) -> Optional[ContractUnion]:
        """
        Return the highest-version contract for *name*, across all majors.

        Args:
            name: Base capability name (without @major suffix).

        Returns:
            Contract with the highest semver, or None.
        """
        versions = self._by_version.get(name)
        if not versions:
            return None
        best_key = max(
            versions,
            key=lambda v: CapabilityVersion.parse(v),
        )
        return versions[best_key]

    def lookup_latest_compatible(
        self,
        name: str,
        major: int,
    ) -> Optional[ContractUnion]:
        """
        Return the highest minor.patch for *name* within the given major.

        Useful when callers need "latest v2.x.x" but not v3.

        Args:
            name: Base capability name.
            major: Major version to filter on.

        Returns:
            Contract with the highest version matching the major, or None.
        """
        versions = self._by_version.get(name)
        if not versions:
            return None
        candidates = {
            v_str: c
            for v_str, c in versions.items()
            if CapabilityVersion.parse(v_str).major == major
        }
        if not candidates:
            return None
        best_key = max(
            candidates,
            key=lambda v: CapabilityVersion.parse(v),
        )
        return candidates[best_key]

    def list_versions(self, name: str) -> List[str]:
        """
        Return sorted list of all version strings for *name*.

        Args:
            name: Base capability name.

        Returns:
            List of version strings, sorted ascending by semver.
        """
        versions = self._by_version.get(name)
        if not versions:
            return []
        return sorted(
            versions.keys(),
            key=lambda v: CapabilityVersion.parse(v),
        )

    # ======================================================================
    # 2.2.4 -- list_by_domain() / list_by_type()
    # ======================================================================

    def list_by_domain(self, domain: str) -> List[ContractUnion]:
        """
        Return all capabilities tagged with the given domain.

        O(1) lookup via the by_domain inverted index, returns a copy
        of the internal list to prevent external mutation.

        Args:
            domain: Domain tag (e.g. "FOOD", "HEALTH", "SOCIAL").

        Returns:
            List of contracts with the given domain tag (may be empty).
        """
        return list(self._by_domain.get(domain, []))

    def list_by_type(self, type_prefix: str) -> List[ContractUnion]:
        """
        Return all capabilities matching the type prefix.

        O(1) lookup via the by_type index, returns a copy.

        Args:
            type_prefix: Type prefix (e.g. "tool.execute", "agent.spawn",
                "workflow.run"). Must NOT include trailing dot.

        Returns:
            List of contracts with the given type prefix (may be empty).
        """
        return list(self._by_type.get(type_prefix, []))

    def list_by_provider(self, provider_id: str) -> List[ContractUnion]:
        """
        Return all capabilities from the given provider.

        O(1) lookup via the by_provider index, returns a copy.

        Args:
            provider_id: Provider identifier string.

        Returns:
            List of contracts from the provider (may be empty).
        """
        return list(self._by_provider.get(provider_id, []))

    # ======================================================================
    # Bulk accessors
    # ======================================================================

    def list_all(self) -> List[ContractUnion]:
        """Return a copy of all registered contracts."""
        return list(self._by_name.values())

    def list_names(self) -> List[str]:
        """Return a sorted list of all registered capability names."""
        return sorted(self._by_name.keys())

    @property
    def size(self) -> int:
        """Number of registered capabilities."""
        return len(self._by_name)

    def get_metadata(self, name: str) -> Optional[ContractMetadata]:
        """
        Return hot-cache metadata for a capability, or None.

        This is cheaper than lookup() when callers only need
        availability, latency, or domain tags.
        """
        return self._metadata_cache.get(name)

    # ======================================================================
    # 2.2.5 -- update_availability()
    # ======================================================================

    def update_availability(
        self,
        name: str,
        availability: str,
    ) -> None:
        """
        Update a capability's availability status.

        Called by AvailabilityTracker (3.6.2), CircuitBreaker (3.4.1),
        and HealthChecker (3.6.1) when a provider transitions state.

        Because contracts are frozen (immutable), this method creates a
        new contract via dataclasses.replace() and swaps the reference
        in all indexes atomically under the RLock.  Metadata cache is
        updated in-place (it is mutable).

        Does NOT recompute the embedding -- that only happens on
        register/unregister (full contract change).

        Args:
            name: Canonical capability name.
            availability: New status -- must be a valid Availability value
                (ONLINE, DEGRADED, OFFLINE).

        Raises:
            CapabilityNotFoundError: name not in the registry.
            ValueError: Invalid availability value.
        """
        # Validate the new availability value
        valid = {a.value for a in Availability}
        if availability not in valid:
            raise ValueError(
                f"Invalid availability '{availability}'. Must be one of: {sorted(valid)}"
            )

        with self._lock:
            old_contract = self._by_name.get(name)
            if old_contract is None:
                raise CapabilityNotFoundError(name)

            old_availability = _get_contract_field(
                old_contract, "availability", Availability.ONLINE.value
            )
            if old_availability == availability:
                return  # No-op: already at target state

            # Create new frozen contract with updated availability
            new_contract = replace(old_contract, availability=availability)

            # Swap in all indexes
            self._by_name[name] = new_contract
            self._swap_in_list_index(self._by_domain, old_contract, new_contract)
            self._swap_in_list_index(self._by_type, old_contract, new_contract)
            self._swap_in_list_index(self._by_provider, old_contract, new_contract)

            # Update mutable metadata cache
            meta = self._metadata_cache.get(name)
            if meta is not None:
                meta.availability = availability

        # Emit event outside lock
        self._emit(
            EVENT_AVAILABILITY_CHANGED,
            {
                "name": name,
                "old_availability": old_availability,
                "new_availability": availability,
            },
        )
        logger.info(
            "Availability changed: %s  %s -> %s",
            name,
            old_availability,
            availability,
        )

    # ======================================================================
    # 2.2.6 -- update_metrics()
    # ======================================================================

    def update_metrics(
        self,
        name: str,
        *,
        success: bool,
        latency_ms: int,
    ) -> None:
        """
        Update rolling 30-day metrics after a CapabilityResult.

        Called by FabricFacade.execute() (5.3.2) after every invocation.
        Uses Exponential Moving Average (EMA) for latency and a
        running average for success rate.

        Because contracts are frozen, this creates a new contract via
        dataclasses.replace() and swaps the reference atomically.
        Metadata cache is updated in-place.

        Args:
            name: Canonical capability name.
            success: Whether the invocation succeeded.
            latency_ms: Observed latency in milliseconds (>= 0).

        Raises:
            CapabilityNotFoundError: name not in the registry.
            ValueError: latency_ms is negative.
        """
        if latency_ms < 0:
            raise ValueError(f"latency_ms must be >= 0, got {latency_ms}")

        with self._lock:
            old_contract = self._by_name.get(name)
            if old_contract is None:
                raise CapabilityNotFoundError(name)

            # Read current values
            old_total = _get_contract_field(old_contract, "total_invocations_30d", 0)
            old_rate = _get_contract_field(old_contract, "success_rate_30d", 0.0)
            old_latency = _get_contract_field(old_contract, "avg_latency_ms", 0)

            # Compute new values
            new_total = old_total + 1
            # Running average for success rate:
            # rate = (rate * old_total + (1 if success else 0)) / new_total
            new_rate = (old_rate * old_total + (1.0 if success else 0.0)) / new_total
            new_rate = round(new_rate, 6)

            # EMA for latency (alpha = 0.3 -- heavier weight on recent)
            alpha = 0.3
            if old_total == 0:
                new_latency = latency_ms
            else:
                new_latency = int(alpha * latency_ms + (1.0 - alpha) * old_latency)

            # Create new frozen contract with updated metrics
            new_contract = replace(
                old_contract,
                success_rate_30d=new_rate,
                avg_latency_ms=new_latency,
                total_invocations_30d=new_total,
            )

            # Swap in all indexes
            self._by_name[name] = new_contract
            self._swap_in_list_index(self._by_domain, old_contract, new_contract)
            self._swap_in_list_index(self._by_type, old_contract, new_contract)
            self._swap_in_list_index(self._by_provider, old_contract, new_contract)

            # Update mutable metadata cache
            meta = self._metadata_cache.get(name)
            if meta is not None:
                meta.success_rate_30d = new_rate
                meta.avg_latency_ms = new_latency
                meta.total_invocations_30d = new_total

        # Emit event outside lock
        self._emit(
            EVENT_METRICS_UPDATED,
            {
                "name": name,
                "success_rate_30d": new_rate,
                "avg_latency_ms": new_latency,
                "total_invocations_30d": new_total,
            },
        )

    # ======================================================================
    # 2.2.7 -- reload()
    # ======================================================================

    def reload(
        self,
        contracts_dir: Union[str, Path],
        *,
        skip_validation: bool = False,
    ) -> Dict[str, Any]:
        """
        Full reload from a contracts directory.

        Scans all YAML files in tools/, agents/, prompts/, workflows/
        subdirectories. Validates each. Rebuilds all indexes.
        Used at startup by ModuleLoader (2.3.1).

        Steps:
          1. Discover all .yaml/.yml files in known subdirectories
          2. Parse and validate each via parse_contract()
          3. Clear all existing indexes
          4. Re-register each valid contract (skip_validation=True since
             already validated in step 2)
          5. Set last_reload_at timestamp
          6. Emit k1.fabric.registry.reloaded.v1

        Args:
            contracts_dir: Root directory containing tools/, agents/,
                prompts/, workflows/ subdirectories.
            skip_validation: If True, skip ContractValidator during parse.

        Returns:
            Summary dict with keys:
                loaded (int): Number of contracts successfully loaded.
                failed (int): Number of contracts that failed parsing.
                errors (list[dict]): Details of each failure:
                    {file: str, error: str}
        """
        from k1.fabric.contracts import parse_contract

        contracts_path = Path(contracts_dir)
        subdirs = ["tools", "agents", "prompts", "workflows"]

        # Step 1: Discover YAML files
        yaml_files: List[Path] = []
        for subdir in subdirs:
            sub_path = contracts_path / subdir
            if sub_path.is_dir():
                yaml_files.extend(sub_path.glob("**/*.yaml"))
                yaml_files.extend(sub_path.glob("**/*.yml"))

        # Step 2: Parse all contracts, collecting successes and failures
        parsed: List[ContractUnion] = []
        errors: List[Dict[str, str]] = []

        shared_validator = self._validator
        for yaml_file in yaml_files:
            try:
                contract = parse_contract(
                    yaml_file,
                    validator=shared_validator,
                    skip_validation=skip_validation,
                )
                parsed.append(contract)
            except Exception as exc:
                errors.append({"file": str(yaml_file), "error": str(exc)})
                logger.warning("Failed to parse %s: %s", yaml_file, exc)

        # Steps 3-4: Clear and re-register under lock
        with self._lock:
            self._by_name.clear()
            self._by_domain.clear()
            self._by_type.clear()
            self._by_provider.clear()
            self._by_version.clear()
            self._metadata_cache.clear()

            for contract in parsed:
                name = _get_contract_name(contract)
                # Skip duplicates (keep first occurrence)
                if name in self._by_name:
                    errors.append(
                        {
                            "file": "in-memory",
                            "error": f"Duplicate name skipped: {name}",
                        }
                    )
                    continue
                self._by_name[name] = contract
                self._insert_domain_index(contract)
                self._insert_type_index(contract)
                self._insert_provider_index(contract)
                ver = _get_contract_field(contract, "version", "")
                if ver:
                    self._insert_version_index(name, ver, contract)
                self._metadata_cache[name] = _build_metadata(contract)

            # Step 5: Record timestamp
            self._last_reload_at = datetime.now(timezone.utc).isoformat()

        loaded = len(self._by_name)

        # Step 6: Emit event outside lock
        self._emit(
            EVENT_REGISTRY_RELOADED,
            {
                "loaded": loaded,
                "failed": len(errors),
                "contracts_dir": str(contracts_path),
            },
        )
        logger.info(
            "Registry reloaded: %d loaded, %d failed from %s",
            loaded,
            len(errors),
            contracts_path,
        )

        return {
            "loaded": loaded,
            "failed": len(errors),
            "errors": errors,
        }

    # ======================================================================
    # 2.2.8 -- health()
    # ======================================================================

    def health(self) -> RegistryHealth:
        """
        Return a frozen snapshot of registry health.

        Provides counts by type prefix, counts by availability status,
        approximate memory footprint, and last reload timestamp.

        Thread-safe: reads indexes under a short lock to get a consistent
        snapshot (counts could drift if read without lock while a mutation
        is in-flight).

        Returns:
            RegistryHealth frozen dataclass.
        """
        with self._lock:
            total = len(self._by_name)

            by_type_counts: Dict[str, int] = {k: len(v) for k, v in self._by_type.items()}

            # Count per availability from metadata cache
            avail_counts: Dict[str, int] = {}
            for meta in self._metadata_cache.values():
                avail = meta.availability
                avail_counts[avail] = avail_counts.get(avail, 0) + 1

            # Approximate memory: sys.getsizeof for each index dict
            index_bytes = (
                sys.getsizeof(self._by_name)
                + sys.getsizeof(self._by_domain)
                + sys.getsizeof(self._by_type)
                + sys.getsizeof(self._by_provider)
                + sys.getsizeof(self._by_version)
                + sys.getsizeof(self._metadata_cache)
            )

            reload_at = self._last_reload_at

        return RegistryHealth(
            total_capabilities=total,
            by_type_counts=by_type_counts,
            by_availability_counts=avail_counts,
            index_size_bytes=index_bytes,
            last_reload_at=reload_at,
        )

    # ======================================================================
    # 4.5.6 -- Lifecycle: Created Agent Tracking
    # ======================================================================

    def register_created_agent(
        self,
        contract: ContractUnion,
        ephemeral: bool,
        created_by: str,
        session_scoped: bool,
    ) -> None:
        """
        Track a runtime-created agent in the lifecycle index (4.5.6).

        Called by BuildAgentHandler (4.5.2) step 6 AFTER the contract
        has already been registered in the main index via register().

        Creates a ``CreatedAgentRecord`` and stores it in the
        ``_created_agents`` dict keyed by capability name.  Also stamps
        the contract with lifecycle metadata via dataclasses.replace()
        so that subsequent lookups reflect the lifecycle state.

        Thread-safe: protected by the existing Registry._lock (RLock).

        Args:
            contract: The already-registered contract.
            ephemeral: If True, agent is removed on session end.
            created_by: Creator identifier (e.g. "orchestrator").
            session_scoped: If True, tied to the originating session.

        Raises:
            CapabilityNotFoundError: Contract name not in the main index.
        """
        name = _get_contract_name(contract)
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._lock:
            if name not in self._by_name:
                raise CapabilityNotFoundError(name)

            # Stamp lifecycle fields onto the frozen contract
            stamped = replace(
                contract,
                ephemeral=ephemeral,
                created_by=created_by,
                created_at_iso=now_iso,
                session_scoped=session_scoped,
            )

            # Swap stamped contract into all indexes
            old_contract = self._by_name[name]
            self._by_name[name] = stamped
            self._swap_in_list_index(self._by_domain, old_contract, stamped)
            self._swap_in_list_index(self._by_type, old_contract, stamped)
            self._swap_in_list_index(self._by_provider, old_contract, stamped)

            # Update version index
            ver_str = _get_contract_field(stamped, "version", "")
            if ver_str:
                versions = self._by_version.get(name)
                if versions is not None and ver_str in versions:
                    versions[ver_str] = stamped

            # Update metadata cache
            self._metadata_cache[name] = _build_metadata(stamped)

            # Store lifecycle record
            self._created_agents[name] = CreatedAgentRecord(
                name=name,
                ephemeral=ephemeral,
                created_by=created_by,
                created_at_iso=now_iso,
                session_scoped=session_scoped,
            )

        logger.info(
            "Registered created agent: %s (ephemeral=%s, created_by=%s, session_scoped=%s)",
            name,
            ephemeral,
            created_by,
            session_scoped,
        )

    def list_created_agents(self) -> List[CreatedAgentRecord]:
        """
        Return a defensive copy of all created agent records (4.5.6).

        Thread-safe: snapshot taken under self._lock.

        Returns:
            List of ``CreatedAgentRecord`` instances (may be empty).
        """
        with self._lock:
            return list(self._created_agents.values())

    def is_created_agent(self, name: str) -> bool:
        """
        Check whether a capability was created at runtime (4.5.6).

        Args:
            name: Canonical capability name.

        Returns:
            True if the name is in the _created_agents index.
        """
        return name in self._created_agents

    @property
    def created_agent_count(self) -> int:
        """Number of runtime-created agents currently tracked."""
        return len(self._created_agents)

    def remove_expired_agents(self, session_id: str) -> Tuple[int, List[str]]:
        """
        Bulk-remove session-scoped ephemeral agents (4.5.6).

        Removes all created agents where ``ephemeral=True`` AND
        ``session_scoped=True``.  Each removed agent is unregistered
        from the main index via ``unregister()``.

        The ``session_id`` parameter is logged and included in emitted
        events for audit traceability but is NOT part of the filter
        criteria (all session-scoped ephemeral agents are removed
        regardless of which session created them).

        Thread-safe: operates under self._lock for the scan + removal,
        then calls unregister() per agent (which re-acquires the RLock).

        Args:
            session_id: Session identifier for audit logging.

        Returns:
            Tuple of (count_removed, list_of_removed_names).
        """
        # Phase 1: Identify agents to remove (under lock)
        with self._lock:
            to_remove = [
                record
                for record in self._created_agents.values()
                if record.ephemeral and record.session_scoped
            ]

        # Phase 2: Unregister each (unregister() acquires _lock internally)
        removed_names: List[str] = []
        for record in to_remove:
            success = self.unregister(record.name)
            if success:
                removed_names.append(record.name)

        # Phase 3: Clean up _created_agents index (under lock)
        with self._lock:
            for name in removed_names:
                self._created_agents.pop(name, None)

        if removed_names:
            logger.info(
                "Removed %d expired agents for session %s: %s",
                len(removed_names),
                session_id,
                removed_names,
            )

        return len(removed_names), removed_names

    # ======================================================================
    # Index Management (private)
    # ======================================================================

    def _insert_domain_index(self, contract: ContractUnion) -> None:
        """Add contract to the by_domain inverted index."""
        for tag in _get_contract_field(contract, "domain", []):
            if tag not in self._by_domain:
                self._by_domain[tag] = []
            self._by_domain[tag].append(contract)

    def _remove_domain_index(self, contract: ContractUnion) -> None:
        """Remove contract from the by_domain inverted index."""
        name = _get_contract_name(contract)
        for tag in _get_contract_field(contract, "domain", []):
            entries = self._by_domain.get(tag)
            if entries is not None:
                self._by_domain[tag] = [c for c in entries if _get_contract_name(c) != name]
                if not self._by_domain[tag]:
                    del self._by_domain[tag]

    def _insert_type_index(self, contract: ContractUnion) -> None:
        """Add contract to the by_type index."""
        name = _get_contract_name(contract)
        type_key = CapabilityType.get_type(name)
        if type_key is not None:
            if type_key not in self._by_type:
                self._by_type[type_key] = []
            self._by_type[type_key].append(contract)
        else:
            # Prompts and other non-typed contracts: use generic key
            generic = _get_generic_type_key(contract)
            if generic:
                if generic not in self._by_type:
                    self._by_type[generic] = []
                self._by_type[generic].append(contract)

    def _remove_type_index(self, contract: ContractUnion) -> None:
        """Remove contract from the by_type index."""
        name = _get_contract_name(contract)
        type_key = CapabilityType.get_type(name) or _get_generic_type_key(contract)
        if type_key:
            entries = self._by_type.get(type_key)
            if entries is not None:
                self._by_type[type_key] = [c for c in entries if _get_contract_name(c) != name]
                if not self._by_type[type_key]:
                    del self._by_type[type_key]

    def _insert_provider_index(self, contract: ContractUnion) -> None:
        """Add contract to the by_provider index."""
        pid = _get_contract_provider_id(contract)
        if pid:
            if pid not in self._by_provider:
                self._by_provider[pid] = []
            self._by_provider[pid].append(contract)

    def _remove_provider_index(self, contract: ContractUnion) -> None:
        """Remove contract from the by_provider index."""
        name = _get_contract_name(contract)
        pid = _get_contract_provider_id(contract)
        if pid:
            entries = self._by_provider.get(pid)
            if entries is not None:
                self._by_provider[pid] = [c for c in entries if _get_contract_name(c) != name]
                if not self._by_provider[pid]:
                    del self._by_provider[pid]

    def _do_upgrade(
        self,
        name: str,
        old_contract: ContractUnion,
        new_contract: ContractUnion,
    ) -> None:
        """
        In-place upgrade: replace old_contract with new_contract in all indexes.

        Called under self._lock by register() when a newer compatible version
        is detected (rule b). Also updates _by_version.
        """
        old_ver = _get_contract_field(old_contract, "version", "")
        new_ver = _get_contract_field(new_contract, "version", "")

        # Swap in primary index
        self._by_name[name] = new_contract

        # Swap in list indexes
        self._swap_in_list_index(self._by_domain, old_contract, new_contract)
        self._swap_in_list_index(self._by_type, old_contract, new_contract)
        self._swap_in_list_index(self._by_provider, old_contract, new_contract)

        # Update version index
        if old_ver:
            self._remove_version_index(name, old_contract)
        if new_ver:
            self._insert_version_index(name, new_ver, new_contract)

        # Update metadata cache
        self._metadata_cache[name] = _build_metadata(new_contract)

    def _insert_version_index(self, name: str, version_str: str, contract: ContractUnion) -> None:
        """Add contract to the _by_version index."""
        if name not in self._by_version:
            self._by_version[name] = {}
        self._by_version[name][version_str] = contract

    def _remove_version_index(self, name: str, contract: ContractUnion) -> None:
        """Remove contract from the _by_version index."""
        versions = self._by_version.get(name)
        if versions is None:
            return
        ver = _get_contract_field(contract, "version", "")
        if ver and ver in versions:
            del versions[ver]
        if not versions:
            del self._by_version[name]

    def _swap_in_list_index(
        self,
        index: Dict[str, List[ContractUnion]],
        old_contract: ContractUnion,
        new_contract: ContractUnion,
    ) -> None:
        """
        Replace old_contract with new_contract in all lists of a dict index.

        Used by update_availability() and update_metrics() to swap frozen
        contract references without rebuilding all indexes from scratch.
        Must be called under self._lock.
        """
        old_id = id(old_contract)
        for key, entries in index.items():
            for i, entry in enumerate(entries):
                if id(entry) is old_id or entry is old_contract:
                    entries[i] = new_contract
                    break  # Each contract appears at most once per key

    # ======================================================================
    # Validation
    # ======================================================================

    def _validate_contract(self, contract: ContractUnion) -> None:
        """
        Validate a contract via ContractValidator before registration.

        Wraps the contract back into its YAML-like dict structure
        and runs full two-phase validation (schema + 12 semantic rules).
        """
        data, contract_type = _contract_to_validation_dict(contract)
        self._validator.validate_or_raise(data, contract_type=contract_type)

    # ======================================================================
    # Event emission
    # ======================================================================

    def _emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Emit an event via the event port, if available."""
        if self._event_port is not None:
            try:
                self._event_port.emit(event_type, payload)
            except Exception:
                logger.warning(
                    "Failed to emit event %s for %s",
                    event_type,
                    payload.get("name", "unknown"),
                    exc_info=True,
                )

    def _record_registration_metrics(self) -> None:
        """Increment registration counter and refresh registry size gauges."""
        metrics = get_default_metrics()
        try:
            metrics.inc_registrations()
        except Exception:
            logger.warning("Failed to increment registrations counter", exc_info=True)
        self._refresh_registry_size_gauges()

    def _refresh_registry_size_gauges(self) -> None:
        """Refresh fabric_registry_size gauges for all known capability types."""
        metrics = get_default_metrics()
        try:
            with self._lock:
                type_counts = {k: len(v) for k, v in self._by_type.items()}
        except Exception:
            logger.warning("Failed to compute registry size counts", exc_info=True)
            return

        known_types = [p.rstrip(".") for p in CapabilityType.ALL_PREFIXES]
        known_types.extend(["prompt", "workflow"])
        for type_key in known_types:
            count = type_counts.get(type_key, 0)
            try:
                metrics.set_registry_size(type_key, count)
            except Exception:
                logger.warning(
                    "Failed to set registry size for %s",
                    type_key,
                    exc_info=True,
                )


# ===========================================================================
# Module-level helpers: contract field extraction
# ===========================================================================
# These helpers exist because the Registry stores a Union of 4 contract types:
# CapabilityContract + AgentContract share a hierarchy, but PromptContract
# and WorkflowContract are separate dataclass trees. The helpers provide
# polymorphic field access without isinstance cascades in every method.


def _get_contract_name(contract: ContractUnion) -> str:
    """Extract the canonical name from any contract type."""
    return contract.name


def _get_contract_field(contract: ContractUnion, field_name: str, default: Any = None) -> Any:
    """Extract an arbitrary field from any contract type."""
    return getattr(contract, field_name, default)


def _get_contract_provider_id(contract: ContractUnion) -> str:
    """Extract provider_id, returning empty string for types without it."""
    return getattr(contract, "provider_id", "")


def _get_contract_provider_type(contract: ContractUnion) -> str:
    """Extract provider_type, returning empty string for types without it."""
    return getattr(contract, "provider_type", "")


def _get_generic_type_key(contract: ContractUnion) -> Optional[str]:
    """
    Derive a generic type key for contracts whose names don't match
    CapabilityType prefixes (e.g., PromptContract names like 'greeting_v1').

    Returns:
        'prompt' for PromptContract, 'workflow' for WorkflowContract, None otherwise.
    """
    if isinstance(contract, PromptContract):
        return "prompt"
    if isinstance(contract, WorkflowContract):
        return "workflow"
    return None


def _build_metadata(contract: ContractUnion) -> ContractMetadata:
    """Build a ContractMetadata cache entry from a contract."""
    name = _get_contract_name(contract)
    return ContractMetadata(
        name=name,
        contract_type=CapabilityType.get_type(name) or _get_generic_type_key(contract),
        domain_tags=list(_get_contract_field(contract, "domain", [])),
        provider_id=_get_contract_provider_id(contract),
        provider_type=_get_contract_provider_type(contract),
        availability=_get_contract_field(contract, "availability", Availability.ONLINE.value),
        safety_band_min=_get_contract_field(contract, "safety_band_min", "GREEN"),
        avg_latency_ms=_get_contract_field(contract, "avg_latency_ms", 0),
        success_rate_30d=_get_contract_field(contract, "success_rate_30d", 0.0),
        total_invocations_30d=_get_contract_field(contract, "total_invocations_30d", 0),
        registered_at_ns=time.monotonic_ns(),
    )


# Lifecycle metadata fields added in 4.5.6 -- runtime-only, not part of
# YAML contract schemas.  Stripped before schema validation.
_LIFECYCLE_FIELDS = frozenset({"ephemeral", "created_by", "created_at_iso", "session_scoped"})


def _contract_to_validation_dict(
    contract: ContractUnion,
) -> tuple[Dict[str, Any], str]:
    """
    Convert a contract back to a root-keyed dict for ContractValidator.

    Strips lifecycle metadata fields (4.5.6) that are not part of the
    YAML contract schema to prevent ``additionalProperties`` violations.

    Returns:
        (wrapped_dict, contract_type) -- e.g. ({"tool_contract": {...}}, "tool_contract")
    """
    if isinstance(contract, AgentContract):
        raw = {k: v for k, v in contract.to_dict().items() if k not in _LIFECYCLE_FIELDS}
        return {"agent_contract": raw}, "agent_contract"
    if isinstance(contract, CapabilityContract):
        raw = {k: v for k, v in contract.to_dict().items() if k not in _LIFECYCLE_FIELDS}
        return {"tool_contract": raw}, "tool_contract"
    if isinstance(contract, PromptContract):
        return {"prompt_contract": contract.to_dict()}, "prompt_contract"
    if isinstance(contract, WorkflowContract):
        return {"workflow_contract": contract.to_dict()}, "workflow_contract"
    # Unreachable for valid ContractUnion
    raise CapabilityRegistryError(f"Unknown contract type: {type(contract).__name__}")
