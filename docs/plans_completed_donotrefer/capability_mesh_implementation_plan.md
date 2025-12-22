# Capability Mesh Implementation Plan

**ADR Reference**: [ADR-K004: Capability Mesh Architecture](../architecture/decisions-K0/k004-capability-mesh-architecture.md)

**Status**: PLANNING

**Branch**: `p03-implementation`

**Last Updated**: 2025-12-14

---

## Overview

This plan implements the 3-layer Capability Mesh Architecture:

1. **CapabilityFabric** - Request/reply by capability name
2. **PipelineScheduler** - Declarative trigger-based activation
3. **Extended ModuleRegistry** - Capability-based lookup

---

## Milestones

### Phase 1 (Initial Release)

| Milestone | Name | Duration | Dependencies |
|-----------|------|----------|--------------|
| **M1** | Foundation & Schemas | 3 days | None |
| **M2** | CapabilityFabric Core | 4 days | M1 |
| **M3** | PipelineScheduler (INTERVAL, THRESHOLD, MANUAL) | 3 days | M1 |
| **M4** | P03 Integration | 2 days | M2 |
| **M5** | P08 Migration | 2 days | M3 |

**Phase 1 Total Duration**: 14 days

### Phase 2 (P03 Prerequisite - CRON & IDLE Triggers)

> **⚠️ CRITICAL**: P03 Consolidation Pipeline requires CRON and IDLE triggers for production use.
> **Phase 2 COMPLETED**: Both CRON and IDLE triggers are now fully implemented.
>
> - ✅ **M6**: CronTriggerEngine with croniter integration (5 issues complete)
> - ✅ **M7**: IdleTriggerEngine with ActivityTracker infrastructure (9 issues complete)
>
> P03 can now use full trigger specification including CRON schedules and idle-based activation.

| Milestone | Name | Duration | Dependencies | Status |
|-----------|------|----------|--------------|--------|
| **M6** | CRON Trigger Engine | 3 days | M3 | ✅ COMPLETE |
| **M7** | IDLE Trigger Engine | 3 days | M3 | ✅ COMPLETE |

**Phase 2 Total Duration**: 6 days (completed)

---

## Milestone 1: Foundation & Schemas (M1)

**Objective**: Create foundational schemas and registry infrastructure.

### Epic 1.1: Capability Registry Schema

Define YAML schema for capability registration and provider configuration.

#### Issue 1.1.1: Create TriggerSpec Pydantic Model

**File**: `k0/runtime/schemas.py`

**Description**: Add Pydantic models for declarative triggers.

**Implementation**:

```python
# Add to k0/runtime/schemas.py

class TriggerType(str, Enum):
    """Types of pipeline triggers."""
    # Phase 1 trigger types
    INTERVAL = "interval"
    THRESHOLD = "threshold"
    MANUAL = "manual"
    # Phase 2 trigger types (not yet implemented)
    CRON = "cron"
    IDLE = "idle"


class TriggerSpec(BaseModel):
    """
    Specification for a pipeline trigger.

    Examples:
        # Interval trigger (every 5 minutes)
        - id: faiss_indexer_interval
          type: interval
          interval_seconds: 300

        # Threshold trigger (when 50+ records pending)
        - id: faiss_indexer_threshold
          type: threshold
          table: st_vec
          condition: "status = 'READY'"
          threshold_count: 50
    """

    id: str = Field(
        ...,
        description="Unique trigger identifier within pipeline",
        pattern=r"^[a-z0-9_]+$",
    )

    type: TriggerType = Field(
        ...,
        description="Trigger type (cron, interval, threshold, idle, manual)",
    )

    # Interval trigger fields
    interval_seconds: int | None = Field(
        default=None,
        ge=1,
        le=86400,
        description="Interval in seconds (for interval type)",
    )

    # Cron trigger fields
    cron_expression: str | None = Field(
        default=None,
        description="Cron expression (for cron type)",
    )

    # Threshold trigger fields
    table: str | None = Field(
        default=None,
        description="Table to monitor (for threshold type)",
    )

    condition: str | None = Field(
        default=None,
        description="SQL WHERE condition (for threshold type)",
    )

    threshold_count: int | None = Field(
        default=None,
        ge=1,
        description="Threshold count to trigger (for threshold type)",
    )

    check_interval_seconds: int | None = Field(
        default=60,
        ge=1,
        description="How often to check threshold (for threshold type)",
    )

    # Idle trigger fields
    idle_seconds: int | None = Field(
        default=None,
        ge=1,
        description="Idle time before trigger (for idle type)",
    )

    min_pending: int | None = Field(
        default=1,
        ge=1,
        description="Minimum pending items for idle trigger",
    )

    # Common fields
    batch_size: int | None = Field(
        default=None,
        ge=1,
        description="Batch size for triggered processing",
    )

    catch_up_enabled: bool = Field(
        default=True,
        description="Whether to catch up on missed triggers at startup",
    )

    @model_validator(mode="after")
    def validate_trigger_fields(self) -> "TriggerSpec":
        """Validate that required fields are present based on trigger type."""
        if self.type == TriggerType.INTERVAL:
            if not self.interval_seconds:
                raise ValueError("interval_seconds required for interval triggers")
        elif self.type == TriggerType.CRON:
            if not self.cron_expression:
                raise ValueError("cron_expression required for cron triggers")
        elif self.type == TriggerType.THRESHOLD:
            if not self.table:
                raise ValueError("table required for threshold triggers")
            if not self.threshold_count:
                raise ValueError("threshold_count required for threshold triggers")
        elif self.type == TriggerType.IDLE:
            if not self.idle_seconds:
                raise ValueError("idle_seconds required for idle triggers")
        # MANUAL type has no required fields
        return self
```

**Testing**:

- File: `tests/k0/runtime/test_schemas_trigger.py`
- Test cases:
  - `test_trigger_spec_interval_valid`
  - `test_trigger_spec_threshold_valid`
  - `test_trigger_spec_cron_valid`
  - `test_trigger_spec_idle_valid`
  - `test_trigger_spec_manual_valid`
  - `test_trigger_spec_invalid_type_raises`
  - `test_trigger_spec_interval_missing_seconds_raises`
  - `test_trigger_spec_cron_missing_expression_raises`
  - `test_trigger_spec_threshold_missing_table_raises`
  - `test_trigger_spec_threshold_missing_count_raises`
  - `test_trigger_spec_idle_missing_seconds_raises`

**Acceptance Criteria**:

- [ ] TriggerSpec Pydantic model validates all trigger types
- [ ] Invalid triggers raise ValidationError with helpful message
- [ ] All tests pass

---

#### Issue 1.1.2: Create CapabilityProvider Pydantic Model

**File**: `k0/runtime/schemas.py`

**Description**: Add Pydantic models for capability provider configuration.

**Implementation**:

```python
# Add to k0/runtime/schemas.py

class ProviderType(str, Enum):
    """Types of capability providers."""
    MODULE = "module"
    PIPELINE = "pipeline"


class FabricContextPolicy(str, Enum):
    """How fabric calls inherit caller context."""
    INHERIT = "inherit"      # Inherit caller's syscalls (capability intersection)
    ISOLATED = "isolated"    # Provider uses its own context only
    SYNTHETIC = "synthetic"  # Fabric creates synthetic context


class CapabilityProvider(BaseModel):
    """
    Configuration for a capability provider.

    Example:
        providers:
          - type: module
            module_id: salience.score:v1
            priority: 1
            condition: always
    """

    type: ProviderType = Field(
        ...,
        description="Provider type (module or pipeline)",
    )

    # Module provider fields
    module_id: str | None = Field(
        default=None,
        description="Module ID (for module providers)",
        pattern=r"^[a-z_]+\.[a-z_]+(:[a-z0-9]+)?$",
    )

    # Pipeline provider fields
    pipeline_id: str | None = Field(
        default=None,
        description="Pipeline ID (for pipeline providers)",
    )

    request_topic: str | None = Field(
        default=None,
        description="Request topic (for pipeline providers)",
    )

    response_topic: str | None = Field(
        default=None,
        description="Response topic (for pipeline providers)",
    )

    # Common fields
    priority: int = Field(
        default=1,
        ge=1,
        le=100,
        description="Provider priority (lower = higher priority)",
    )

    condition: str = Field(
        default="always",
        description="Condition for using this provider",
    )

    latency_budget_ms: int | None = Field(
        default=None,
        ge=1,
        le=10000,
        description="Latency budget for this provider",
    )

    timeout_ms: int | None = Field(
        default=None,
        ge=1,
        le=60000,
        description="Timeout for provider response",
    )

    @model_validator(mode="after")
    def validate_provider_fields(self) -> "CapabilityProvider":
        """Validate that required fields are present based on provider type."""
        if self.type == ProviderType.MODULE:
            if not self.module_id:
                raise ValueError("module_id required for module providers")
        elif self.type == ProviderType.PIPELINE:
            if not self.pipeline_id:
                raise ValueError("pipeline_id required for pipeline providers")
            if not self.request_topic or not self.response_topic:
                raise ValueError("request_topic and response_topic required for pipeline providers")
        return self


class CapabilityDefinition(BaseModel):
    """
    Definition of a capability with its providers.

    Example:
        score_salience:
          description: "Compute salience score"
          providers:
            - type: module
              module_id: salience.score:v1
    """

    description: str = Field(
        ...,
        description="Human-readable capability description",
    )

    providers: list[CapabilityProvider] = Field(
        ...,
        min_length=1,
        description="Ordered list of providers for this capability",
    )

    default_timeout_ms: int = Field(
        default=100,
        ge=1,
        le=60000,
        description="Default timeout for capability requests",
    )
```

**Testing**:

- File: `tests/k0/runtime/test_schemas_capability.py`
- Test cases:
  - `test_capability_provider_module_valid`
  - `test_capability_provider_pipeline_valid`
  - `test_capability_provider_module_missing_id_raises`
  - `test_capability_provider_pipeline_missing_topics_raises`
  - `test_capability_definition_valid`
  - `test_capability_definition_empty_providers_raises`

**Acceptance Criteria**:

- [ ] CapabilityProvider validates module and pipeline providers
- [ ] Cross-field validation catches missing required fields
- [ ] All tests pass

---

#### Issue 1.1.3: Extend ModuleContract for Fabric Integration

**File**: `k0/runtime/schemas.py`

**Description**: Add fabric-related fields to ModuleContract.

**Implementation**:

```python
# Modify ModuleContract in k0/runtime/schemas.py

class ModuleContract(BaseModel):
    # ... existing fields ...

    # NEW: Fabric integration fields
    fabric_callable: bool = Field(
        default=False,
        description="Whether module can be invoked via CapabilityFabric",
    )

    fabric_capabilities: list[str] = Field(
        default_factory=list,
        description="Capabilities this module provides",
    )

    fabric_context_policy: FabricContextPolicy = Field(
        default=FabricContextPolicy.INHERIT,
        description="How fabric calls inherit caller context",
    )
```

**Testing**:

- File: `tests/k0/runtime/test_schemas.py` (extend existing)
- Test cases:
  - `test_module_contract_fabric_callable_default_false`
  - `test_module_contract_fabric_capabilities_empty_default`
  - `test_module_contract_fabric_context_policy_default_inherit`
  - `test_module_contract_with_fabric_fields`

**Acceptance Criteria**:

- [ ] ModuleContract has fabric_callable, fabric_capabilities, fabric_context_policy
- [ ] Defaults are backward-compatible (fabric_callable=False)
- [ ] Existing module contracts still validate
- [ ] All tests pass

---

#### Issue 1.1.4: Extend PipelineSpec for Triggers

**File**: `k0/runtime/schemas.py`

**Description**: Add triggers field to PipelineSpec.

**Implementation**:

```python
# Modify PipelineSpec in k0/runtime/schemas.py

class PipelineSpec(BaseModel):
    # ... existing fields ...

    # NEW: Trigger configuration
    triggers: list[TriggerSpec] = Field(
        default_factory=list,
        description="Declarative triggers for scheduled activation",
    )

    # NEW: Fabric actions this pipeline provides
    fabric_actions: list[str] = Field(
        default_factory=list,
        description="Fabric capabilities this pipeline exposes",
    )
```

**Testing**:

- File: `tests/k0/runtime/test_schemas.py` (extend existing)
- Test cases:
  - `test_pipeline_spec_triggers_default_empty`
  - `test_pipeline_spec_with_interval_trigger`
  - `test_pipeline_spec_with_threshold_trigger`
  - `test_pipeline_spec_fabric_actions_default_empty`

**Acceptance Criteria**:

- [ ] PipelineSpec has triggers and fabric_actions fields
- [ ] Existing pipeline specs still validate
- [ ] All tests pass

---

### Epic 1.2: CapabilityRegistry Core

Create the in-memory registry for capability lookups.

#### Issue 1.2.1: Create CapabilityRegistry Class

**Directory**: `k0/fabric/`

**Files**:

- `k0/fabric/__init__.py`
- `k0/fabric/registry.py`

**Description**: Core registry for capability registration and lookup.

**Implementation** (`k0/fabric/registry.py`):

```python
"""
Capability Registry - Maps capability names to providers.

This module provides the core registry for capability-based lookups,
enabling modules and pipelines to discover providers by capability name
rather than concrete implementation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from k0.runtime.schemas import CapabilityProvider

logger = logging.getLogger(__name__)


class ResolutionStrategy(str, Enum):
    """How to resolve multiple providers."""
    FIRST = "first"          # First matching provider
    PRIORITY = "priority"    # Highest priority matching
    ROUND_ROBIN = "round_robin"  # Distribute across providers


@dataclass
class RegisteredProvider:
    """A provider registered for a capability."""

    capability: str
    provider: CapabilityProvider
    handler: Callable | None = None  # Resolved handler function

    # Runtime metrics
    call_count: int = 0
    total_latency_ms: float = 0.0
    error_count: int = 0


@dataclass
class CapabilityRegistry:
    """
    Registry for capability-based lookups.

    Thread-safe registry that maps capability names to ordered
    lists of providers. Supports hot-reload of providers without
    restart.

    Example:
        registry = CapabilityRegistry()
        registry.register("score_salience", provider, handler_fn)

        provider, handler = registry.resolve("score_salience")
        result = handler(**kwargs)
    """

    _providers: dict[str, list[RegisteredProvider]] = field(default_factory=dict)
    _round_robin_index: dict[str, int] = field(default_factory=dict)

    def register(
        self,
        capability: str,
        provider: CapabilityProvider,
        handler: Callable | None = None,
    ) -> None:
        """
        Register a provider for a capability.

        Args:
            capability: Capability name (e.g., "score_salience")
            provider: Provider configuration
            handler: Resolved handler function (optional, can bind later)
        """
        if capability not in self._providers:
            self._providers[capability] = []
            self._round_robin_index[capability] = 0

        registered = RegisteredProvider(
            capability=capability,
            provider=provider,
            handler=handler,
        )

        # Insert sorted by priority (lower = higher priority)
        providers = self._providers[capability]
        insert_idx = 0
        for i, p in enumerate(providers):
            if provider.priority < p.provider.priority:
                insert_idx = i
                break
            insert_idx = i + 1

        providers.insert(insert_idx, registered)
        logger.info(
            "Registered provider for %s: %s (priority=%d)",
            capability,
            provider.module_id or provider.pipeline_id,
            provider.priority,
        )

    def unregister(self, capability: str, provider_id: str) -> bool:
        """
        Unregister a provider from a capability.

        Args:
            capability: Capability name
            provider_id: Module ID or pipeline ID to unregister

        Returns:
            True if provider was found and removed
        """
        if capability not in self._providers:
            return False

        providers = self._providers[capability]
        for i, p in enumerate(providers):
            pid = p.provider.module_id or p.provider.pipeline_id
            if pid == provider_id:
                providers.pop(i)
                logger.info("Unregistered %s from %s", provider_id, capability)
                return True

        return False

    def resolve(
        self,
        capability: str,
        strategy: ResolutionStrategy = ResolutionStrategy.PRIORITY,
    ) -> RegisteredProvider | None:
        """
        Resolve a capability to a provider.

        Args:
            capability: Capability name to resolve
            strategy: Resolution strategy

        Returns:
            RegisteredProvider or None if not found
        """
        providers = self._providers.get(capability, [])
        if not providers:
            return None

        if strategy == ResolutionStrategy.FIRST:
            return providers[0]

        if strategy == ResolutionStrategy.PRIORITY:
            # Already sorted by priority, return first
            return providers[0]

        if strategy == ResolutionStrategy.ROUND_ROBIN:
            idx = self._round_robin_index.get(capability, 0)
            provider = providers[idx % len(providers)]
            self._round_robin_index[capability] = (idx + 1) % len(providers)
            return provider

        return providers[0]

    def list_capabilities(self) -> list[str]:
        """List all registered capability names."""
        return list(self._providers.keys())

    def list_providers(self, capability: str) -> list[RegisteredProvider]:
        """List all providers for a capability."""
        return list(self._providers.get(capability, []))

    def bind_handler(
        self,
        capability: str,
        provider_id: str,
        handler: Callable,
    ) -> bool:
        """
        Bind a handler function to a registered provider.

        Used for late-binding when handlers aren't available at registration.

        Args:
            capability: Capability name
            provider_id: Module ID or pipeline ID
            handler: Handler function to bind

        Returns:
            True if provider found and handler bound
        """
        providers = self._providers.get(capability, [])
        for p in providers:
            pid = p.provider.module_id or p.provider.pipeline_id
            if pid == provider_id:
                p.handler = handler
                return True
        return False

    def record_call(
        self,
        capability: str,
        provider_id: str,
        latency_ms: float,
        error: bool = False,
    ) -> None:
        """Record metrics for a capability call."""
        providers = self._providers.get(capability, [])
        for p in providers:
            pid = p.provider.module_id or p.provider.pipeline_id
            if pid == provider_id:
                p.call_count += 1
                p.total_latency_ms += latency_ms
                if error:
                    p.error_count += 1
                break


# Global registry instance
_capability_registry: CapabilityRegistry | None = None


def get_capability_registry() -> CapabilityRegistry:
    """Get the global capability registry."""
    global _capability_registry
    if _capability_registry is None:
        _capability_registry = CapabilityRegistry()
    return _capability_registry


def reset_capability_registry() -> None:
    """Reset the global registry (for testing)."""
    global _capability_registry
    _capability_registry = None
```

**Implementation** (`k0/fabric/__init__.py`):

```python
"""
Capability Fabric - Request/reply by capability name.

This package provides Layer 2 of the Capability Mesh architecture,
enabling modules and pipelines to invoke capabilities without
knowing the concrete provider implementation.
"""

from k0.fabric.registry import (
    CapabilityRegistry,
    RegisteredProvider,
    ResolutionStrategy,
    get_capability_registry,
    reset_capability_registry,
)

__all__ = [
    "CapabilityRegistry",
    "RegisteredProvider",
    "ResolutionStrategy",
    "get_capability_registry",
    "reset_capability_registry",
]
```

**Testing**:

- File: `tests/k0/fabric/test_registry.py`
- Test cases:
  - `test_register_single_provider`
  - `test_register_multiple_providers_sorted_by_priority`
  - `test_resolve_returns_highest_priority`
  - `test_resolve_round_robin_cycles`
  - `test_resolve_unknown_capability_returns_none`
  - `test_unregister_removes_provider`
  - `test_bind_handler_updates_provider`
  - `test_record_call_updates_metrics`
  - `test_global_registry_singleton`
  - `test_reset_clears_registry`

**Acceptance Criteria**:

- [ ] CapabilityRegistry registers, resolves, and unregisters providers
- [ ] Priority-based resolution works correctly
- [ ] Round-robin resolution cycles through providers
- [ ] Metrics recording works
- [ ] Global singleton pattern works
- [ ] All tests pass

---

### Epic 1.3: Create Capability YAML Schema

Define JSON Schema for capability YAML files.

#### Issue 1.3.1: Create Capability JSON Schema

**File**: `contracts/schemas/capability.schema.json`

**Description**: JSON Schema for capability definition YAML files.

**Implementation**:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://familyos.dev/schemas/capability.schema.json",
  "title": "Capability Definition Schema",
  "description": "Schema for capability YAML definition files",
  "type": "object",
  "required": ["version", "capabilities"],
  "properties": {
    "version": {
      "type": "string",
      "pattern": "^v[0-9]+$",
      "description": "Schema version (e.g., v1)"
    },
    "capabilities": {
      "type": "object",
      "additionalProperties": {
        "$ref": "#/definitions/capability"
      }
    }
  },
  "definitions": {
    "capability": {
      "type": "object",
      "required": ["description", "providers"],
      "properties": {
        "description": {
          "type": "string",
          "minLength": 1
        },
        "default_timeout_ms": {
          "type": "integer",
          "minimum": 1,
          "maximum": 60000,
          "default": 100
        },
        "providers": {
          "type": "array",
          "minItems": 1,
          "items": {
            "$ref": "#/definitions/provider"
          }
        }
      }
    },
    "provider": {
      "type": "object",
      "required": ["type"],
      "properties": {
        "type": {
          "type": "string",
          "enum": ["module", "pipeline"]
        },
        "module_id": {
          "type": "string",
          "pattern": "^[a-z_]+\\.[a-z_]+(:[a-z0-9]+)?$"
        },
        "pipeline_id": {
          "type": "string"
        },
        "request_topic": {
          "type": "string"
        },
        "response_topic": {
          "type": "string"
        },
        "priority": {
          "type": "integer",
          "minimum": 1,
          "maximum": 100,
          "default": 1
        },
        "condition": {
          "type": "string",
          "default": "always"
        },
        "latency_budget_ms": {
          "type": "integer",
          "minimum": 1,
          "maximum": 10000
        },
        "timeout_ms": {
          "type": "integer",
          "minimum": 1,
          "maximum": 60000
        }
      },
      "allOf": [
        {
          "if": {
            "properties": { "type": { "const": "module" } }
          },
          "then": {
            "required": ["module_id"]
          }
        },
        {
          "if": {
            "properties": { "type": { "const": "pipeline" } }
          },
          "then": {
            "required": ["pipeline_id", "request_topic", "response_topic"]
          }
        }
      ]
    }
  }
}
```

**Testing**:

- File: `tests/contracts/test_capability_schema.py`
- Test cases:
  - `test_valid_module_provider_validates`
  - `test_valid_pipeline_provider_validates`
  - `test_missing_module_id_fails`
  - `test_missing_pipeline_topics_fails`
  - `test_invalid_priority_fails`

**Acceptance Criteria**:

- [ ] JSON Schema validates module provider definitions
- [ ] JSON Schema validates pipeline provider definitions
- [ ] Invalid configurations fail validation with clear errors
- [ ] All tests pass

---

#### Issue 1.3.2: Create Default Capability Registry YAML

**File**: `k0/contracts/capabilities/core.v1.yaml`

**Description**: Initial capability definitions for core K0 capabilities.

**Implementation**:

```yaml
# Core K0 Capability Definitions
# Version: v1
# Defines foundational capabilities and their default providers

version: v1

capabilities:
  # Salience scoring capability
  score_salience:
    description: "Compute salience score for content"
    default_timeout_ms: 100
    providers:
      - type: module
        module_id: salience.score:v1
        priority: 1
        condition: always

  # Pattern separation capability (hippocampus)
  pattern_separate:
    description: "Pattern separation via hippocampus"
    default_timeout_ms: 200
    providers:
      - type: module
        module_id: hippocampus.pattern_separate:v1
        priority: 1
        condition: always

  # Deduplication capability
  deduplicate_content:
    description: "Detect and mark duplicate content"
    default_timeout_ms: 150
    providers:
      - type: module
        module_id: dedup.detect:v1
        priority: 1
        condition: always

  # Embedding generation capability
  generate_embedding:
    description: "Generate embedding vector for content"
    default_timeout_ms: 500
    providers:
      - type: module
        module_id: embedding.generate:v1
        priority: 1
        condition: always

  # Entity extraction capability
  extract_entities:
    description: "Extract named entities from content"
    default_timeout_ms: 300
    providers:
      - type: module
        module_id: entity.extract:v1
        priority: 1
        condition: always

  # Retrieval capability
  retrieve_similar:
    description: "Retrieve similar content from memory"
    default_timeout_ms: 200
    providers:
      - type: module
        module_id: retrieval.similar:v1
        priority: 1
        condition: always
```

**Testing**:

- File: `tests/contracts/test_capability_contracts.py`
- Test cases:
  - `test_core_capabilities_yaml_valid`
  - `test_core_capabilities_loads_without_error`
  - `test_all_providers_have_valid_module_ids`

**Acceptance Criteria**:

- [ ] YAML file validates against JSON Schema
- [ ] All referenced module IDs follow naming convention
- [ ] File loads and parses without errors
- [ ] All tests pass

---

## Milestone 2: CapabilityFabric Core (M2)

**Objective**: Implement the CapabilityFabric for request/reply by capability.

**Dependencies**: M1 complete

### Epic 2.1: CapabilityFabric Implementation

Core fabric that routes capability requests to providers.

#### Issue 2.1.1: Create CapabilityRequest/Response Dataclasses

**File**: `k0/fabric/messages.py`

**Description**: Define request/response types for fabric calls.

**Implementation**:

```python
"""
Capability Fabric Messages.

Dataclasses for request/response communication via CapabilityFabric.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RequestStatus(str, Enum):
    """Status of a capability request."""
    PENDING = "pending"
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class CapabilityRequest:
    """
    Request to invoke a capability.

    Attributes:
        capability: Capability name to invoke (e.g., "score_salience")
        payload: Arguments to pass to the capability handler
        request_id: Unique request identifier for tracing
        timeout_ms: Request timeout in milliseconds
        caller_id: Identifier of the calling module/pipeline
        trace_id: Distributed trace ID for observability
        created_at: Request creation timestamp
    """

    capability: str
    payload: dict[str, Any]
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timeout_ms: int = 100
    caller_id: str | None = None
    trace_id: str | None = None
    created_at: float = field(default_factory=time.time)

    def elapsed_ms(self) -> float:
        """Return elapsed time since request creation."""
        return (time.time() - self.created_at) * 1000


@dataclass
class CapabilityResponse:
    """
    Response from a capability invocation.

    Attributes:
        request_id: Matching request identifier
        status: Response status (success, error, timeout)
        result: Result data (on success)
        error: Error message (on error)
        provider_id: ID of provider that handled the request
        latency_ms: Handler latency in milliseconds
    """

    request_id: str
    status: RequestStatus
    result: Any = None
    error: str | None = None
    provider_id: str | None = None
    latency_ms: float = 0.0

    @classmethod
    def success(
        cls,
        request_id: str,
        result: Any,
        provider_id: str,
        latency_ms: float,
    ) -> CapabilityResponse:
        """Create a success response."""
        return cls(
            request_id=request_id,
            status=RequestStatus.SUCCESS,
            result=result,
            provider_id=provider_id,
            latency_ms=latency_ms,
        )

    @classmethod
    def error(
        cls,
        request_id: str,
        error: str,
        provider_id: str | None = None,
        latency_ms: float = 0.0,
    ) -> CapabilityResponse:
        """Create an error response."""
        return cls(
            request_id=request_id,
            status=RequestStatus.ERROR,
            error=error,
            provider_id=provider_id,
            latency_ms=latency_ms,
        )

    @classmethod
    def timeout(
        cls,
        request_id: str,
        timeout_ms: float,
    ) -> CapabilityResponse:
        """Create a timeout response."""
        return cls(
            request_id=request_id,
            status=RequestStatus.TIMEOUT,
            error=f"Request timed out after {timeout_ms}ms",
            latency_ms=timeout_ms,
        )
```

**Testing**:

- File: `tests/k0/fabric/test_messages.py`
- Test cases:
  - `test_request_generates_unique_id`
  - `test_request_elapsed_ms_increases`
  - `test_response_success_factory`
  - `test_response_error_factory`
  - `test_response_timeout_factory`

**Acceptance Criteria**:

- [ ] CapabilityRequest generates unique request IDs
- [ ] CapabilityRequest tracks elapsed time
- [ ] CapabilityResponse factory methods work correctly
- [ ] All tests pass

---

#### Issue 2.1.2: Create CapabilityFabric Core Class

**File**: `k0/fabric/fabric.py`

**Description**: Main fabric class for routing capability requests.

**Implementation**:

```python
"""
Capability Fabric - Request/reply by capability name.

The CapabilityFabric provides a capability-based request/reply layer
that sits above the event bus. It enables modules to invoke capabilities
without knowing the concrete provider implementation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Callable

from k0.fabric.messages import CapabilityRequest, CapabilityResponse, RequestStatus
from k0.fabric.registry import (
    CapabilityRegistry,
    RegisteredProvider,
    ResolutionStrategy,
    get_capability_registry,
)

if TYPE_CHECKING:
    from k0.pipelines.protocol import PipelineContext

logger = logging.getLogger(__name__)


class CapabilityNotFoundError(Exception):
    """Raised when a capability cannot be resolved."""
    pass


class CapabilityTimeoutError(Exception):
    """Raised when a capability request times out."""
    pass


class CapabilityFabric:
    """
    Capability Fabric for request/reply by capability name.

    Provides a synchronous request/reply pattern for invoking capabilities.
    Handles provider resolution, timeout enforcement, and metrics collection.

    Example:
        fabric = CapabilityFabric.get_instance()
        result = fabric.invoke(
            "score_salience",
            context=pipeline_context,
            content="Hello world",
        )
    """

    _instance: CapabilityFabric | None = None

    def __init__(self, registry: CapabilityRegistry | None = None):
        """
        Initialize the fabric.

        Args:
            registry: CapabilityRegistry to use. Defaults to global registry.
        """
        self._registry = registry or get_capability_registry()
        self._default_timeout_ms = 100
        self._pending_requests: dict[str, CapabilityRequest] = {}

    @classmethod
    def get_instance(cls) -> CapabilityFabric:
        """Get the singleton fabric instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton (for testing)."""
        cls._instance = None

    def invoke(
        self,
        capability: str,
        context: PipelineContext | None = None,
        timeout_ms: int | None = None,
        caller_id: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """
        Invoke a capability synchronously.

        Args:
            capability: Capability name to invoke
            context: PipelineContext for syscalls inheritance
            timeout_ms: Request timeout (overrides default)
            caller_id: Identifier of the caller
            **kwargs: Arguments to pass to the capability handler

        Returns:
            Result from the capability handler

        Raises:
            CapabilityNotFoundError: If capability cannot be resolved
            CapabilityTimeoutError: If request times out
            Exception: If handler raises an exception
        """
        request = CapabilityRequest(
            capability=capability,
            payload=kwargs,
            timeout_ms=timeout_ms or self._default_timeout_ms,
            caller_id=caller_id,
            trace_id=getattr(context, "trace_id", None) if context else None,
        )

        logger.debug(
            "Fabric invoke: capability=%s request_id=%s",
            capability,
            request.request_id,
        )

        # Resolve provider
        provider = self._registry.resolve(capability, ResolutionStrategy.PRIORITY)
        if provider is None:
            raise CapabilityNotFoundError(f"No provider for capability: {capability}")

        if provider.handler is None:
            raise CapabilityNotFoundError(
                f"Provider {provider.provider.module_id} has no handler bound"
            )

        # Track pending request
        self._pending_requests[request.request_id] = request

        try:
            start_time = time.perf_counter()

            # Check timeout before invoking
            if request.elapsed_ms() > request.timeout_ms:
                raise CapabilityTimeoutError(
                    f"Request timed out before invocation: {request.request_id}"
                )

            # Invoke handler
            result = provider.handler(context=context, **kwargs)

            latency_ms = (time.perf_counter() - start_time) * 1000

            # Record metrics
            provider_id = provider.provider.module_id or provider.provider.pipeline_id
            self._registry.record_call(capability, provider_id, latency_ms, error=False)

            logger.debug(
                "Fabric invoke success: capability=%s latency=%.2fms",
                capability,
                latency_ms,
            )

            return result

        except Exception as e:
            latency_ms = request.elapsed_ms()
            provider_id = provider.provider.module_id or provider.provider.pipeline_id
            self._registry.record_call(capability, provider_id, latency_ms, error=True)

            logger.warning(
                "Fabric invoke error: capability=%s error=%s",
                capability,
                str(e),
            )
            raise

        finally:
            self._pending_requests.pop(request.request_id, None)

    async def invoke_async(
        self,
        capability: str,
        context: PipelineContext | None = None,
        timeout_ms: int | None = None,
        caller_id: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """
        Invoke a capability asynchronously.

        Same as invoke() but uses asyncio.to_thread for blocking handlers.
        """
        return await asyncio.to_thread(
            self.invoke,
            capability,
            context=context,
            timeout_ms=timeout_ms,
            caller_id=caller_id,
            **kwargs,
        )

    def register_handler(
        self,
        capability: str,
        handler: Callable,
        module_id: str,
        priority: int = 1,
    ) -> None:
        """
        Register a handler for a capability.

        Convenience method for registering module handlers.

        Args:
            capability: Capability name
            handler: Handler function
            module_id: Module identifier
            priority: Provider priority
        """
        from k0.runtime.schemas import CapabilityProvider, ProviderType

        provider = CapabilityProvider(
            type=ProviderType.MODULE,
            module_id=module_id,
            priority=priority,
        )

        self._registry.register(capability, provider, handler)

    def pending_count(self) -> int:
        """Return number of pending requests."""
        return len(self._pending_requests)


def get_capability_fabric() -> CapabilityFabric:
    """Get the global CapabilityFabric instance."""
    return CapabilityFabric.get_instance()
```

**Testing**:

- File: `tests/k0/fabric/test_fabric.py`
- Test cases:
  - `test_invoke_resolves_and_calls_handler`
  - `test_invoke_not_found_raises`
  - `test_invoke_no_handler_raises`
  - `test_invoke_records_success_metrics`
  - `test_invoke_records_error_metrics`
  - `test_invoke_passes_context`
  - `test_register_handler_convenience`
  - `test_singleton_instance`
  - `test_pending_count_tracks_requests`

**Acceptance Criteria**:

- [ ] CapabilityFabric resolves capabilities to handlers
- [ ] Invoke passes context and kwargs to handler
- [ ] Metrics are recorded for success and error
- [ ] CapabilityNotFoundError raised for unknown capabilities
- [ ] All tests pass

---

#### Issue 2.1.3: Add Fabric to PipelineContext

**File**: `k0/pipelines/protocol.py`

**Description**: Add CapabilityFabric to PipelineContext for module access.

**Wiring Details**:

Current PipelineContext (from `k0/pipelines/protocol.py`):

```python
@dataclass
class PipelineContext:
    syscalls: KernelSyscalls
    config: dict[str, Any]
    logger: logging.Logger
    preloaded_models: dict[str, Any] | None = None
    bus_dispatcher: BusDispatcher | None = None
```

**Changes Required**:

1. Add import:

   ```python
   from k0.fabric.fabric import CapabilityFabric, get_capability_fabric
   ```

2. Add field to PipelineContext:

   ```python
   fabric: CapabilityFabric | None = None
   ```

3. Update PipelineContext initialization in `k0/runtime/pipeline_runner.py`:

   ```python
   context = PipelineContext(
       syscalls=syscalls,
       config=config,
       logger=logger,
       preloaded_models=preloaded_models,
       bus_dispatcher=bus_dispatcher,
       fabric=get_capability_fabric(),  # NEW
   )
   ```

**Testing**:

- File: `tests/k0/pipelines/test_protocol.py` (extend existing)
- Test cases:
  - `test_pipeline_context_has_fabric_field`
  - `test_pipeline_context_fabric_default_none`

- File: `tests/k0/runtime/test_pipeline_runner.py` (extend existing)
- Test cases:
  - `test_context_includes_fabric`

**Acceptance Criteria**:

- [ ] PipelineContext has fabric field
- [ ] PipelineRunner passes fabric to context
- [ ] Modules can access context.fabric
- [ ] All tests pass

---

#### Issue 2.1.4: Update **init**.py Exports

**File**: `k0/fabric/__init__.py`

**Description**: Export all fabric components.

**Implementation**:

```python
"""
Capability Fabric - Request/reply by capability name.

This package provides Layer 2 of the Capability Mesh architecture,
enabling modules and pipelines to invoke capabilities without
knowing the concrete provider implementation.
"""

from k0.fabric.fabric import (
    CapabilityFabric,
    CapabilityNotFoundError,
    CapabilityTimeoutError,
    get_capability_fabric,
)
from k0.fabric.messages import (
    CapabilityRequest,
    CapabilityResponse,
    RequestStatus,
)
from k0.fabric.registry import (
    CapabilityRegistry,
    RegisteredProvider,
    ResolutionStrategy,
    get_capability_registry,
    reset_capability_registry,
)

__all__ = [
    # Fabric
    "CapabilityFabric",
    "CapabilityNotFoundError",
    "CapabilityTimeoutError",
    "get_capability_fabric",
    # Messages
    "CapabilityRequest",
    "CapabilityResponse",
    "RequestStatus",
    # Registry
    "CapabilityRegistry",
    "RegisteredProvider",
    "ResolutionStrategy",
    "get_capability_registry",
    "reset_capability_registry",
]
```

**Testing**:

- File: `tests/k0/fabric/test_init.py`
- Test cases:
  - `test_all_exports_importable`

**Acceptance Criteria**:

- [ ] All public classes/functions exported
- [ ] Imports work from `k0.fabric`
- [ ] All tests pass

---

#### Issue 2.1.5: Add Fabric Context Policy Enforcement

**File**: `k0/fabric/fabric.py`

**Description**: Add enforcement boundary methods for `fabric_context_policy`.

**Wiring Details**:

Module contracts can declare `fabric_context_policy: inherit | isolated | synthetic`.
The fabric must enforce this policy before invoking the provider.

**Implementation**:

Add these methods to `CapabilityFabric`:

```python
def _enforce_context_policy(
    self,
    caller_context: PipelineContext | None,
    provider_policy: str,  # "inherit" | "isolated" | "synthetic"
    provider_caps: set[str],
) -> PipelineContext | None:
    """
    Enforce fabric_context_policy before invoking provider.

    Args:
        caller_context: Caller's PipelineContext
        provider_policy: Policy from module contract
        provider_caps: Provider's declared capabilities

    Returns:
        Effective PipelineContext for provider invocation

    Policy behaviors:
        - inherit: caller_caps ∩ provider_caps = effective_caps
        - isolated: provider uses only its declared syscalls
        - synthetic: fabric creates minimal context with trace_id only
    """
    if caller_context is None:
        return None

    if provider_policy == "inherit":
        # Capability intersection: provider can only use
        # capabilities that both caller and provider have
        effective_caps = self._intersect_capabilities(
            getattr(caller_context, "capabilities", set()),
            provider_caps,
        )
        return self._create_context_with_caps(caller_context, effective_caps)

    elif provider_policy == "isolated":
        # Provider uses only its own declared context
        return None

    elif provider_policy == "synthetic":
        # Minimal context with trace_id only
        return self._create_synthetic_context(caller_context)

    else:
        raise ValueError(f"Unknown fabric_context_policy: {provider_policy}")


def _intersect_capabilities(
    self,
    caller_caps: set[str],
    provider_caps: set[str],
) -> set[str]:
    """Return intersection of caller and provider capabilities."""
    return caller_caps & provider_caps


def _create_context_with_caps(
    self,
    source_context: PipelineContext,
    effective_caps: set[str],
) -> PipelineContext:
    """Create a new context with restricted capabilities."""
    from dataclasses import replace

    return replace(source_context, capabilities=effective_caps)


def _create_synthetic_context(
    self,
    source_context: PipelineContext,
) -> PipelineContext:
    """Create minimal synthetic context for isolated invocation."""
    from k0.pipelines.protocol import PipelineContext

    return PipelineContext(
        syscalls=None,  # No syscalls access
        config={},
        logger=source_context.logger,
        trace_id=getattr(source_context, "trace_id", None),
    )
```

**Update invoke() method** to call enforcement:

```python
def invoke(self, capability: str, context: PipelineContext | None = None, ...):
    # ... resolve provider ...

    # Enforce context policy
    provider_policy = getattr(provider.provider, "context_policy", "inherit")
    provider_caps = set(provider.provider.fabric_capabilities or [])
    effective_context = self._enforce_context_policy(
        context, provider_policy, provider_caps
    )

    # Invoke with effective context
    result = provider.handler(context=effective_context, **kwargs)
```

**Testing**:

- File: `tests/k0/fabric/test_fabric_policy.py`
- Test cases:
  - `test_enforce_inherit_policy_intersects_caps`
  - `test_enforce_isolated_policy_returns_none`
  - `test_enforce_synthetic_policy_minimal_context`
  - `test_intersect_capabilities_basic`
  - `test_intersect_capabilities_empty_caller`
  - `test_intersect_capabilities_empty_provider`
  - `test_invoke_uses_effective_context`

**Acceptance Criteria**:

- [ ] inherit policy performs capability intersection
- [ ] isolated policy uses provider-only context
- [ ] synthetic policy creates minimal trace-only context
- [ ] invoke() calls enforcement before handler
- [ ] All tests pass

---

#### Issue 2.1.6: Add Fabric Audit Logging

**File**: `k0/fabric/audit.py`

**Description**: Add structured audit logging for all fabric invocations.

**Wiring Details**:

Per ADR-K004, all fabric calls cross trust boundaries and must be auditable.

**Implementation**:

```python
"""
Fabric Audit Logging - Structured audit events for fabric calls.

All fabric invocations are logged with structured JSON for auditability.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

# Dedicated audit logger
audit_logger = logging.getLogger("k0.fabric.audit")


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Base audit event structure."""
    event: str
    timestamp: str
    trace_id: str | None
    correlation_id: str | None


@dataclass(frozen=True, slots=True)
class FabricInvokeStart(AuditEvent):
    """Logged before provider resolution."""
    capability: str
    caller_id: str | None


@dataclass(frozen=True, slots=True)
class FabricInvokeComplete(AuditEvent):
    """Logged after handler returns successfully."""
    capability: str
    provider_id: str
    caller_id: str | None
    latency_ms: float
    success: bool = True


@dataclass(frozen=True, slots=True)
class FabricInvokeError(AuditEvent):
    """Logged on handler exception."""
    capability: str
    provider_id: str | None
    caller_id: str | None
    error_type: str
    error_msg: str
    latency_ms: float
    success: bool = False


class FabricAuditor:
    """Audit logger for fabric invocations."""

    def __init__(self, logger: logging.Logger | None = None):
        self._logger = logger or audit_logger

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def log_invoke_start(
        self,
        capability: str,
        caller_id: str | None,
        trace_id: str | None,
        correlation_id: str | None,
    ) -> float:
        """Log invoke start, return start time for latency calculation."""
        event = FabricInvokeStart(
            event="fabric.invoke.start",
            timestamp=self._now_iso(),
            trace_id=trace_id,
            correlation_id=correlation_id,
            capability=capability,
            caller_id=caller_id,
        )
        self._logger.info(asdict(event))
        return time.perf_counter()

    def log_invoke_complete(
        self,
        capability: str,
        provider_id: str,
        caller_id: str | None,
        start_time: float,
        trace_id: str | None,
        correlation_id: str | None,
    ) -> None:
        """Log successful invoke completion."""
        latency_ms = (time.perf_counter() - start_time) * 1000
        event = FabricInvokeComplete(
            event="fabric.invoke.complete",
            timestamp=self._now_iso(),
            trace_id=trace_id,
            correlation_id=correlation_id,
            capability=capability,
            provider_id=provider_id,
            caller_id=caller_id,
            latency_ms=round(latency_ms, 3),
        )
        self._logger.info(asdict(event))

    def log_invoke_error(
        self,
        capability: str,
        provider_id: str | None,
        caller_id: str | None,
        error: Exception,
        start_time: float,
        trace_id: str | None,
        correlation_id: str | None,
    ) -> None:
        """Log invoke error."""
        latency_ms = (time.perf_counter() - start_time) * 1000
        event = FabricInvokeError(
            event="fabric.invoke.error",
            timestamp=self._now_iso(),
            trace_id=trace_id,
            correlation_id=correlation_id,
            capability=capability,
            provider_id=provider_id,
            caller_id=caller_id,
            error_type=type(error).__name__,
            error_msg=str(error),
            latency_ms=round(latency_ms, 3),
        )
        self._logger.warning(asdict(event))


# Global auditor instance
_auditor: FabricAuditor | None = None


def get_fabric_auditor() -> FabricAuditor:
    """Get the global fabric auditor."""
    global _auditor
    if _auditor is None:
        _auditor = FabricAuditor()
    return _auditor
```

**Update CapabilityFabric.invoke()** to use auditor:

```python
def invoke(self, capability: str, context: PipelineContext | None = None, ...):
    auditor = get_fabric_auditor()
    trace_id = getattr(context, "trace_id", None) if context else None
    correlation_id = request.request_id

    start_time = auditor.log_invoke_start(
        capability, caller_id, trace_id, correlation_id
    )

    try:
        # ... existing logic ...
        result = provider.handler(context=effective_context, **kwargs)

        auditor.log_invoke_complete(
            capability, provider_id, caller_id, start_time, trace_id, correlation_id
        )
        return result

    except Exception as e:
        auditor.log_invoke_error(
            capability, provider_id, caller_id, e, start_time, trace_id, correlation_id
        )
        raise
```

**Testing**:

- File: `tests/k0/fabric/test_audit.py`
- Test cases:
  - `test_audit_invoke_start_logs_event`
  - `test_audit_invoke_complete_logs_event`
  - `test_audit_invoke_error_logs_event`
  - `test_audit_event_has_all_fields`
  - `test_audit_latency_calculated_correctly`
  - `test_fabric_invoke_calls_auditor`

**Acceptance Criteria**:

- [ ] All fabric invocations produce audit events
- [ ] Audit events include trace_id, correlation_id, capability, provider_id
- [ ] Latency is measured accurately
- [ ] Errors include error_type and error_msg
- [ ] Audit logger is separate namespace (k0.fabric.audit)
- [ ] All tests pass

---

### Epic 2.2: Capability Auto-Registration

Automatically register module capabilities at boot.

#### Issue 2.2.1: Extend ModuleRegistry for Capability Index

**File**: `k0/runtime/module_registry.py`

**Description**: Add capability indexing to ModuleRegistry.

**Wiring Details**:

Current ModuleRegistry structure (from code read):

- `_registry: dict[str, ModuleEntry]` - module ID → entry
- `_load_implementation(module_name)` - lazy loads module
- `get(name)` - returns module run function

**Changes Required**:

1. Add capability index field:

   ```python
   _capability_index: dict[str, list[str]] = {}  # capability → [module_ids]
   ```

2. Add `register_capability` method:

   ```python
   def register_capability(self, capability: str, module_id: str) -> None:
       """Register a module as provider for a capability."""
       if capability not in self._capability_index:
           self._capability_index[capability] = []
       if module_id not in self._capability_index[capability]:
           self._capability_index[capability].append(module_id)
   ```

3. Add `resolve_capability` method:

   ```python
   def resolve_capability(self, capability: str) -> list[str]:
       """Return module IDs that provide a capability."""
       return self._capability_index.get(capability, [])
   ```

4. Modify `_load_implementation` to check for `fabric_capabilities`:

   ```python
   # After loading contract
   if contract and contract.fabric_capabilities:
       for cap in contract.fabric_capabilities:
           self.register_capability(cap, module_name)
   ```

**Testing**:

- File: `tests/k0/runtime/test_module_registry.py` (extend existing)
- Test cases:
  - `test_register_capability_adds_to_index`
  - `test_register_capability_no_duplicates`
  - `test_resolve_capability_returns_modules`
  - `test_resolve_unknown_capability_empty`
  - `test_load_implementation_registers_fabric_capabilities`

**Acceptance Criteria**:

- [ ] ModuleRegistry tracks capability → module mappings
- [ ] Loading modules auto-registers fabric_capabilities
- [ ] resolve_capability returns correct modules
- [ ] All tests pass

---

#### Issue 2.2.2: Auto-register Capabilities at Boot

**File**: `k0/fabric/loader.py`

**Description**: Load capability definitions and register providers at boot.

**Implementation**:

```python
"""
Capability Loader - Load and register capabilities at boot.

This module scans capability YAML files and registers providers
with the CapabilityRegistry at application startup.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from k0.fabric.registry import get_capability_registry
from k0.runtime.schemas import CapabilityDefinition, CapabilityProvider

if TYPE_CHECKING:
    from k0.runtime.module_registry import ModuleRegistry

logger = logging.getLogger(__name__)

CAPABILITY_CONTRACTS_DIR = Path(__file__).parent.parent / "contracts" / "capabilities"


def load_capability_definitions(
    contracts_dir: Path | None = None,
) -> dict[str, CapabilityDefinition]:
    """
    Load capability definitions from YAML files.

    Args:
        contracts_dir: Directory containing capability YAML files.
                       Defaults to k0/contracts/capabilities/

    Returns:
        Dict mapping capability names to definitions
    """
    contracts_dir = contracts_dir or CAPABILITY_CONTRACTS_DIR
    definitions: dict[str, CapabilityDefinition] = {}

    if not contracts_dir.exists():
        logger.warning("Capability contracts directory not found: %s", contracts_dir)
        return definitions

    for yaml_file in contracts_dir.glob("*.yaml"):
        try:
            with open(yaml_file) as f:
                data = yaml.safe_load(f)

            if not data or "capabilities" not in data:
                continue

            for name, defn in data["capabilities"].items():
                definitions[name] = CapabilityDefinition.model_validate(defn)
                logger.debug("Loaded capability definition: %s", name)

        except Exception as e:
            logger.error("Failed to load capability file %s: %s", yaml_file, e)

    return definitions


def register_capabilities_from_definitions(
    definitions: dict[str, CapabilityDefinition],
    module_registry: ModuleRegistry,
) -> int:
    """
    Register capability providers from definitions.

    Args:
        definitions: Capability definitions loaded from YAML
        module_registry: ModuleRegistry to resolve module handlers

    Returns:
        Number of providers registered
    """
    registry = get_capability_registry()
    registered_count = 0

    for capability, definition in definitions.items():
        for provider in definition.providers:
            handler = None

            # Resolve module handler
            if provider.module_id:
                try:
                    # Remove version suffix for registry lookup
                    module_name = provider.module_id.split(":")[0]
                    handler = module_registry.get(module_name)
                except Exception as e:
                    logger.warning(
                        "Failed to resolve handler for %s: %s",
                        provider.module_id,
                        e,
                    )

            registry.register(capability, provider, handler)
            registered_count += 1

    logger.info(
        "Registered %d capability providers for %d capabilities",
        registered_count,
        len(definitions),
    )

    return registered_count


def discover_and_register_capabilities(
    module_registry: ModuleRegistry,
    contracts_dir: Path | None = None,
) -> int:
    """
    Discover and register all capabilities.

    Convenience function that loads definitions and registers providers.

    Args:
        module_registry: ModuleRegistry for handler resolution
        contracts_dir: Optional custom contracts directory

    Returns:
        Number of providers registered
    """
    definitions = load_capability_definitions(contracts_dir)
    return register_capabilities_from_definitions(definitions, module_registry)
```

**Testing**:

- File: `tests/k0/fabric/test_loader.py`
- Test cases:
  - `test_load_capability_definitions_from_yaml`
  - `test_load_capability_definitions_missing_dir`
  - `test_load_capability_definitions_invalid_yaml_skipped`
  - `test_register_capabilities_from_definitions`
  - `test_register_capabilities_resolves_handlers`
  - `test_discover_and_register_full_flow`

**Acceptance Criteria**:

- [ ] YAML capability files are loaded and parsed
- [ ] Providers are registered with handlers
- [ ] Invalid files don't crash the loader
- [ ] All tests pass

---

#### Issue 2.2.3: Integrate Capability Loading into App Bootstrap

**File**: `k0/kernel/app.py`

**Description**: Call capability loader during kernel boot.

**Wiring Details**:

Current boot sequence in `k0/kernel/app.py`:

1. `create_app()` creates FastAPI app
2. `lifespan()` context manager runs startup
3. `discover_and_boot_pipelines()` loads pipelines
4. Hardcoded P08 scheduler starts

**Changes Required**:

1. Add import:

   ```python
   from k0.fabric.loader import discover_and_register_capabilities
   ```

2. In `lifespan()` after module registry is available:

   ```python
   # Register capabilities
   from k0.runtime.module_registry import get_module_registry
   module_registry = get_module_registry()
   discover_and_register_capabilities(module_registry)
   ```

**Testing**:

- File: `tests/k0/kernel/test_app_boot.py`
- Test cases:
  - `test_app_boot_registers_capabilities`
  - `test_app_boot_capabilities_available_after_lifespan`

**Acceptance Criteria**:

- [ ] Capabilities registered during app boot
- [ ] Modules can use fabric after boot
- [ ] All tests pass

---

## Milestone 3: PipelineScheduler (M3)

**Objective**: Implement declarative trigger-based pipeline activation.

**Phase 1 Scope**: Only INTERVAL, THRESHOLD, and MANUAL trigger types.
CRON and IDLE triggers are deferred to Phase 2 (see M6/M7).

**Dependencies**: M1 complete

### Epic 3.1: PipelineScheduler Core

Core scheduler that manages trigger-based pipeline activation.

#### Issue 3.1.0: Add query_count() Syscall Method

**File**: `k0/kernel/syscalls.py`

**Description**: Add generic table count query method for threshold triggers.

**Gap Identified**: ThresholdTriggerEngine requires `syscalls.query_count(table, where)` but this method doesn't exist. Existing code has embedded COUNT queries within specific methods (e.g., `vec_query`) but no generic count capability.

**Implementation**:

```python
# Add to k0/kernel/syscalls.py

async def query_count(
    self,
    table: str,
    where: str = "1=1",
    params: tuple = (),
) -> int:
    """
    Query row count from a table with optional WHERE clause.

    Used by PipelineScheduler for threshold triggers.

    Args:
        table: Table name (must be in allowed tables)
        where: WHERE clause (default: all rows)
        params: Query parameters for WHERE clause

    Returns:
        Row count matching condition

    Raises:
        PermissionError: If pipeline lacks read capability for table

    Example:
        >>> count = await syscalls.query_count(
        ...     table="st_vec",
        ...     where="status = ?",
        ...     params=("READY",)
        ... )
        >>> print(f"{count} vectors pending indexing")
    """
    # Validate table access
    required_cap = f"{table}.read"
    if required_cap not in self._granted_caps:
        raise PermissionError(
            f"Pipeline {self._pipeline_id} lacks capability: {required_cap}"
        )

    # Allowed tables for threshold queries
    allowed_tables = {
        "st_vec", "st_hipp_events", "st_wal", "st_epi",
        "st_sem", "st_outbox", "st_pipeline_processed"
    }
    if table not in allowed_tables:
        raise ValueError(f"Table not allowed for count queries: {table}")

    async with self._uow_factory() as uow:
        conn = uow._connection
        if conn is None:
            raise RuntimeError("UnitOfWork connection not initialized")

        try:
            loop = asyncio.get_running_loop()
            sql = f"SELECT COUNT(*) FROM {table} WHERE {where}"
            result = await loop.run_in_executor(
                None,
                lambda: conn.execute(sql, params).fetchone(),
            )
            return result[0] if result else 0

        except Exception as e:
            logger.error(f"query_count failed for {table}: {e}")
            raise
```

**Testing**:

- File: `tests/k0/kernel/test_syscalls_query_count.py`
- Test cases:
  - `test_query_count_basic`
  - `test_query_count_with_where_clause`
  - `test_query_count_permission_denied`
  - `test_query_count_invalid_table_raises`
  - `test_query_count_empty_table_returns_zero`

**Acceptance Criteria**:

- [ ] query_count() method exists on Syscalls class
- [ ] Validates table access via capabilities
- [ ] Only allows approved tables
- [ ] Returns correct count for WHERE conditions
- [ ] All tests pass

---

#### Issue 3.1.1: Create TriggerEngine Base

**File**: `k0/scheduler/triggers.py`

**Description**: Abstract trigger engine and concrete implementations.

**Implementation**:

```python
"""
Trigger Engines - Implementations for each trigger type.

Each trigger type has its own engine that evaluates whether
the trigger condition is met.
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from k0.runtime.schemas import TriggerSpec
    from k0.kernel.syscalls import KernelSyscalls

logger = logging.getLogger(__name__)


@dataclass
class TriggerEvent:
    """Event emitted when a trigger fires."""

    trigger_id: str
    pipeline_id: str
    fired_at: float
    context: dict[str, Any] | None = None


class TriggerEngine(ABC):
    """Base class for trigger engines."""

    def __init__(self, spec: TriggerSpec, pipeline_id: str):
        self.spec = spec
        self.pipeline_id = pipeline_id
        self._running = False
        self._last_fired: float | None = None

    @abstractmethod
    async def start(self, callback: Callable[[TriggerEvent], None]) -> None:
        """Start the trigger engine."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the trigger engine."""
        pass

    @property
    def is_running(self) -> bool:
        return self._running


class IntervalTriggerEngine(TriggerEngine):
    """Trigger that fires at fixed intervals."""

    def __init__(self, spec: TriggerSpec, pipeline_id: str):
        super().__init__(spec, pipeline_id)
        self._task: asyncio.Task | None = None

    async def start(self, callback: Callable[[TriggerEvent], None]) -> None:
        """Start interval trigger."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop(callback))
        logger.info(
            "Started interval trigger %s for %s (every %ds)",
            self.spec.id,
            self.pipeline_id,
            self.spec.interval_seconds,
        )

    async def _run_loop(self, callback: Callable[[TriggerEvent], None]) -> None:
        """Run the interval loop."""
        while self._running:
            try:
                await asyncio.sleep(self.spec.interval_seconds or 60)

                if not self._running:
                    break

                event = TriggerEvent(
                    trigger_id=self.spec.id,
                    pipeline_id=self.pipeline_id,
                    fired_at=time.time(),
                )
                self._last_fired = event.fired_at

                callback(event)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Interval trigger error: %s", e)

    async def stop(self) -> None:
        """Stop interval trigger."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass


class ThresholdTriggerEngine(TriggerEngine):
    """Trigger that fires when a table row count exceeds threshold."""

    def __init__(
        self,
        spec: TriggerSpec,
        pipeline_id: str,
        syscalls: KernelSyscalls,
    ):
        super().__init__(spec, pipeline_id)
        self._syscalls = syscalls
        self._task: asyncio.Task | None = None

    async def start(self, callback: Callable[[TriggerEvent], None]) -> None:
        """Start threshold trigger."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop(callback))
        logger.info(
            "Started threshold trigger %s for %s (table=%s, threshold=%d)",
            self.spec.id,
            self.pipeline_id,
            self.spec.table,
            self.spec.threshold_count,
        )

    async def _run_loop(self, callback: Callable[[TriggerEvent], None]) -> None:
        """Run the threshold check loop."""
        check_interval = self.spec.check_interval_seconds or 60

        while self._running:
            try:
                await asyncio.sleep(check_interval)

                if not self._running:
                    break

                # Check threshold
                count = await self._check_count()

                if count >= (self.spec.threshold_count or 1):
                    event = TriggerEvent(
                        trigger_id=self.spec.id,
                        pipeline_id=self.pipeline_id,
                        fired_at=time.time(),
                        context={"count": count},
                    )
                    self._last_fired = event.fired_at
                    callback(event)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Threshold trigger error: %s", e)

    async def _check_count(self) -> int:
        """Check current count from table."""
        # Use syscalls to query count
        table = self.spec.table
        condition = self.spec.condition or "1=1"

        try:
            result = await asyncio.to_thread(
                self._syscalls.query_count,
                table=table,
                where=condition,
            )
            return result or 0
        except Exception as e:
            logger.warning("Threshold check failed: %s", e)
            return 0

    async def stop(self) -> None:
        """Stop threshold trigger."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass


class ManualTriggerEngine(TriggerEngine):
    """Trigger that only fires on explicit request."""

    def __init__(self, spec: TriggerSpec, pipeline_id: str):
        super().__init__(spec, pipeline_id)
        self._callback: Callable[[TriggerEvent], None] | None = None

    async def start(self, callback: Callable[[TriggerEvent], None]) -> None:
        """Start manual trigger (just stores callback)."""
        self._running = True
        self._callback = callback
        logger.info("Registered manual trigger %s for %s", self.spec.id, self.pipeline_id)

    async def stop(self) -> None:
        """Stop manual trigger."""
        self._running = False
        self._callback = None

    def fire(self) -> None:
        """Manually fire the trigger."""
        if not self._running or not self._callback:
            return

        event = TriggerEvent(
            trigger_id=self.spec.id,
            pipeline_id=self.pipeline_id,
            fired_at=time.time(),
        )
        self._last_fired = event.fired_at
        self._callback(event)


def create_trigger_engine(
    spec: TriggerSpec,
    pipeline_id: str,
    syscalls: KernelSyscalls | None = None,
) -> TriggerEngine:
    """
    Factory function to create appropriate trigger engine.

    Args:
        spec: Trigger specification
        pipeline_id: Pipeline this trigger belongs to
        syscalls: KernelSyscalls for threshold queries

    Returns:
        Appropriate TriggerEngine subclass
    """
    from k0.runtime.schemas import TriggerType

    if spec.type == TriggerType.INTERVAL:
        return IntervalTriggerEngine(spec, pipeline_id)
    elif spec.type == TriggerType.THRESHOLD:
        if syscalls is None:
            raise ValueError("Threshold triggers require syscalls")
        return ThresholdTriggerEngine(spec, pipeline_id, syscalls)
    elif spec.type == TriggerType.MANUAL:
        return ManualTriggerEngine(spec, pipeline_id)
    elif spec.type in (TriggerType.CRON, TriggerType.IDLE):
        raise NotImplementedError(
            f"Trigger type {spec.type.value} is Phase 2 (not yet implemented)"
        )
    else:
        raise ValueError(f"Unsupported trigger type: {spec.type}")
```

**Testing**:

- File: `tests/k0/scheduler/test_triggers.py`
- Test cases:
  - `test_interval_trigger_fires_after_interval`
  - `test_interval_trigger_stop_cancels_task`
  - `test_threshold_trigger_fires_when_exceeded`
  - `test_threshold_trigger_does_not_fire_below`
  - `test_manual_trigger_fires_on_call`
  - `test_create_trigger_engine_factory`
  - `test_trigger_event_has_correct_fields`

**Acceptance Criteria**:

- [ ] IntervalTriggerEngine fires at correct intervals
- [ ] ThresholdTriggerEngine queries table and fires when exceeded
- [ ] ManualTriggerEngine fires on explicit call
- [ ] Factory creates correct engine type
- [ ] All tests pass

---

#### Issue 3.1.2: Create PipelineScheduler Class

**File**: `k0/scheduler/scheduler.py`

**Description**: Main scheduler that manages triggers and invokes pipelines.

**Implementation**:

```python
"""
Pipeline Scheduler - Declarative trigger-based pipeline activation.

The PipelineScheduler manages trigger engines for all pipelines and
invokes pipeline handlers when triggers fire.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from k0.scheduler.triggers import TriggerEngine, TriggerEvent, create_trigger_engine

if TYPE_CHECKING:
    from k0.kernel.syscalls import KernelSyscalls
    from k0.runtime.pipeline_runner import PipelineRunner
    from k0.runtime.schemas import PipelineSpec, TriggerSpec

logger = logging.getLogger(__name__)


@dataclass
class ScheduledPipeline:
    """A pipeline with its triggers."""

    pipeline_id: str
    spec: PipelineSpec
    triggers: list[TriggerEngine] = field(default_factory=list)

    # Runtime stats
    trigger_count: int = 0
    last_triggered: float | None = None
    last_error: str | None = None


class PipelineScheduler:
    """
    Pipeline Scheduler for trigger-based activation.

    Manages trigger engines for all registered pipelines and invokes
    the pipeline runner when triggers fire.

    Example:
        scheduler = PipelineScheduler(pipeline_runner, syscalls)
        scheduler.register_pipeline(pipeline_spec)
        await scheduler.start()
    """

    _instance: PipelineScheduler | None = None

    def __init__(
        self,
        pipeline_runner: PipelineRunner,
        syscalls: KernelSyscalls,
    ):
        """
        Initialize the scheduler.

        Args:
            pipeline_runner: Runner to invoke pipelines
            syscalls: Syscalls for threshold queries
        """
        self._runner = pipeline_runner
        self._syscalls = syscalls
        self._pipelines: dict[str, ScheduledPipeline] = {}
        self._running = False

    @classmethod
    def get_instance(cls) -> PipelineScheduler | None:
        """Get the singleton scheduler instance."""
        return cls._instance

    @classmethod
    def set_instance(cls, scheduler: PipelineScheduler) -> None:
        """Set the singleton scheduler instance."""
        cls._instance = scheduler

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton (for testing)."""
        cls._instance = None

    def register_pipeline(self, spec: PipelineSpec) -> int:
        """
        Register a pipeline with its triggers.

        Args:
            spec: Pipeline specification with triggers

        Returns:
            Number of triggers registered
        """
        if not spec.triggers:
            return 0

        triggers = []
        for trigger_spec in spec.triggers:
            engine = create_trigger_engine(
                trigger_spec,
                spec.id,
                self._syscalls,
            )
            triggers.append(engine)

        self._pipelines[spec.id] = ScheduledPipeline(
            pipeline_id=spec.id,
            spec=spec,
            triggers=triggers,
        )

        logger.info(
            "Registered pipeline %s with %d triggers",
            spec.id,
            len(triggers),
        )

        return len(triggers)

    def unregister_pipeline(self, pipeline_id: str) -> bool:
        """
        Unregister a pipeline and stop its triggers.

        Args:
            pipeline_id: Pipeline to unregister

        Returns:
            True if pipeline was found and removed
        """
        scheduled = self._pipelines.pop(pipeline_id, None)
        if scheduled is None:
            return False

        # Stop triggers synchronously if possible
        for trigger in scheduled.triggers:
            asyncio.create_task(trigger.stop())

        logger.info("Unregistered pipeline %s", pipeline_id)
        return True

    async def start(self) -> None:
        """Start all trigger engines."""
        if self._running:
            return

        self._running = True

        for scheduled in self._pipelines.values():
            for trigger in scheduled.triggers:
                await trigger.start(self._on_trigger_fired)

        logger.info(
            "Pipeline scheduler started with %d pipelines",
            len(self._pipelines),
        )

    async def stop(self) -> None:
        """Stop all trigger engines."""
        self._running = False

        for scheduled in self._pipelines.values():
            for trigger in scheduled.triggers:
                await trigger.stop()

        logger.info("Pipeline scheduler stopped")

    def _on_trigger_fired(self, event: TriggerEvent) -> None:
        """Handle trigger fired event."""
        scheduled = self._pipelines.get(event.pipeline_id)
        if not scheduled:
            logger.warning("Trigger fired for unknown pipeline: %s", event.pipeline_id)
            return

        scheduled.trigger_count += 1
        scheduled.last_triggered = event.fired_at

        logger.info(
            "Trigger %s fired for pipeline %s",
            event.trigger_id,
            event.pipeline_id,
        )

        # Schedule pipeline execution
        asyncio.create_task(self._execute_pipeline(scheduled, event))

    async def _execute_pipeline(
        self,
        scheduled: ScheduledPipeline,
        event: TriggerEvent,
    ) -> None:
        """Execute a triggered pipeline."""
        try:
            # Build trigger context for pipeline
            trigger_context = {
                "trigger_id": event.trigger_id,
                "trigger_context": event.context,
                "triggered_at": event.fired_at,
            }

            await self._runner.execute(
                scheduled.spec.id,
                payload=trigger_context,
            )

        except Exception as e:
            scheduled.last_error = str(e)
            logger.error(
                "Pipeline execution failed for %s: %s",
                scheduled.pipeline_id,
                e,
            )

    def list_scheduled_pipelines(self) -> list[str]:
        """List all scheduled pipeline IDs."""
        return list(self._pipelines.keys())

    def get_pipeline_stats(self, pipeline_id: str) -> dict[str, Any] | None:
        """Get trigger stats for a pipeline."""
        scheduled = self._pipelines.get(pipeline_id)
        if not scheduled:
            return None

        return {
            "pipeline_id": pipeline_id,
            "trigger_count": scheduled.trigger_count,
            "last_triggered": scheduled.last_triggered,
            "last_error": scheduled.last_error,
            "num_triggers": len(scheduled.triggers),
        }

    def fire_manual_trigger(self, pipeline_id: str, trigger_id: str) -> bool:
        """
        Manually fire a trigger.

        Args:
            pipeline_id: Pipeline containing the trigger
            trigger_id: Trigger to fire

        Returns:
            True if trigger was found and fired
        """
        from k0.scheduler.triggers import ManualTriggerEngine

        scheduled = self._pipelines.get(pipeline_id)
        if not scheduled:
            return False

        for trigger in scheduled.triggers:
            if trigger.spec.id == trigger_id:
                if isinstance(trigger, ManualTriggerEngine):
                    trigger.fire()
                    return True

        return False
```

**Testing**:

- File: `tests/k0/scheduler/test_scheduler.py`
- Test cases:
  - `test_register_pipeline_creates_triggers`
  - `test_register_pipeline_no_triggers_returns_zero`
  - `test_unregister_pipeline_stops_triggers`
  - `test_start_starts_all_triggers`
  - `test_stop_stops_all_triggers`
  - `test_trigger_fired_executes_pipeline`
  - `test_get_pipeline_stats`
  - `test_fire_manual_trigger`
  - `test_singleton_instance`

**Acceptance Criteria**:

- [ ] PipelineScheduler registers pipelines with triggers
- [ ] Start/stop controls all trigger engines
- [ ] Trigger events invoke pipeline runner
- [ ] Stats tracking works
- [ ] Manual trigger firing works
- [ ] All tests pass

---

#### Issue 3.1.3: Create Scheduler Package Init

**Files**:

- `k0/scheduler/__init__.py`

**Description**: Export scheduler components.

**Implementation**:

```python
"""
Pipeline Scheduler - Declarative trigger-based pipeline activation.

This package provides Layer 3 of the Capability Mesh architecture,
enabling pipelines to be activated via declarative triggers rather
than hardcoded scheduler loops.
"""

from k0.scheduler.scheduler import PipelineScheduler, ScheduledPipeline
from k0.scheduler.triggers import (
    IntervalTriggerEngine,
    ManualTriggerEngine,
    ThresholdTriggerEngine,
    TriggerEngine,
    TriggerEvent,
    create_trigger_engine,
)

__all__ = [
    # Scheduler
    "PipelineScheduler",
    "ScheduledPipeline",
    # Triggers
    "TriggerEngine",
    "TriggerEvent",
    "IntervalTriggerEngine",
    "ThresholdTriggerEngine",
    "ManualTriggerEngine",
    "create_trigger_engine",
]
```

**Testing**:

- File: `tests/k0/scheduler/test_init.py`
- Test cases:
  - `test_all_exports_importable`

**Acceptance Criteria**:

- [ ] All public classes/functions exported
- [ ] Imports work from `k0.scheduler`
- [ ] All tests pass

---

### Epic 3.2: Scheduler Integration

Integrate scheduler into kernel boot and pipeline loading.

#### Issue 3.2.1: Integrate Scheduler into App Bootstrap

**File**: `k0/kernel/app.py`

**Description**: Create and start PipelineScheduler during kernel boot.

**Wiring Details**:

Current boot in `lifespan()`:

1. Creates syscalls
2. Calls `discover_and_boot_pipelines()`
3. Starts hardcoded P08 loop

**Changes Required**:

1. Add imports:

   ```python
   from k0.scheduler.scheduler import PipelineScheduler
   ```

2. In `lifespan()` after pipeline discovery:

   ```python
   # Create scheduler
   from k0.runtime.pipeline_runner import get_pipeline_runner
   pipeline_runner = get_pipeline_runner()
   scheduler = PipelineScheduler(pipeline_runner, syscalls)
   PipelineScheduler.set_instance(scheduler)

   # Register pipelines with triggers
   for spec in loaded_pipelines:
       scheduler.register_pipeline(spec)

   # Start scheduler
   await scheduler.start()
   ```

3. In `lifespan()` shutdown:

   ```python
   # Stop scheduler
   scheduler = PipelineScheduler.get_instance()
   if scheduler:
       await scheduler.stop()
   ```

**Testing**:

- File: `tests/k0/kernel/test_app_scheduler.py`
- Test cases:
  - `test_app_creates_scheduler_on_boot`
  - `test_app_registers_pipelines_with_scheduler`
  - `test_app_starts_scheduler`
  - `test_app_stops_scheduler_on_shutdown`

**Acceptance Criteria**:

- [ ] Scheduler created during app boot
- [ ] Pipelines registered with scheduler
- [ ] Scheduler started and stopped with app lifecycle
- [ ] All tests pass

---

#### Issue 3.2.2: Update Pipeline Loader to Return Specs

**File**: `k0/pipelines/loader.py`

**Description**: Modify `discover_and_boot_pipelines` to return loaded specs.

**Wiring Details**:

Current signature:

```python
def discover_and_boot_pipelines(
    base_path: Path | None = None,
    ...
) -> int:
```

**Changes Required**:

Return loaded specs instead of just count:

```python
@dataclass
class PipelineLoadResult:
    """Result from pipeline loading."""

    loaded_count: int
    specs: list[PipelineSpec]
    errors: list[str]


def discover_and_boot_pipelines(
    base_path: Path | None = None,
    ...
) -> PipelineLoadResult:
    """
    Discover and load pipeline contracts.

    Returns:
        PipelineLoadResult with specs and error info
    """
```

**Testing**:

- File: `tests/k0/pipelines/test_loader.py` (extend existing)
- Test cases:
  - `test_discover_returns_load_result`
  - `test_discover_result_contains_specs`
  - `test_discover_result_contains_errors`

**Acceptance Criteria**:

- [ ] Returns PipelineLoadResult with specs
- [ ] Backward compatible (count still accessible)
- [ ] Errors captured in result
- [ ] All tests pass

---

### Epic 3.3: Concurrency Controls

Implement thread safety and trigger overlap policies per ADR-K004.

#### Issue 3.3.1: Add Single-Flight Pipeline Gate

**File**: `k0/scheduler/concurrency.py`

**Description**: Implement "one run at a time per pipeline" policy.

**Implementation**:

```python
"""
Scheduler Concurrency Controls.

Implements single-flight gating to prevent concurrent runs of the same pipeline.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable

logger = logging.getLogger(__name__)


class OverlapPolicy(str, Enum):
    """What to do when trigger fires while pipeline is running."""
    SKIP = "skip"      # Drop this trigger (interval behavior)
    QUEUE = "queue"    # Queue one pending run (threshold/manual behavior)


@dataclass
class PendingRun:
    """A queued trigger waiting to run."""
    trigger_id: str
    trigger_type: str
    queued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class RunStats:
    """Statistics for a pipeline's run history."""
    total_runs: int = 0
    total_skipped: int = 0
    total_queued: int = 0
    last_run_at: datetime | None = None
    last_skip_at: datetime | None = None


class SingleFlightGate:
    """
    Ensures only one run per pipeline at a time.

    Per ADR-K004 Concurrency Policy:
    - INTERVAL triggers: SKIP if already running
    - THRESHOLD/MANUAL triggers: QUEUE (max depth 1, coalesce)
    """

    def __init__(self):
        self._running: dict[str, asyncio.Task] = {}
        self._pending: dict[str, PendingRun | None] = {}
        self._stats: dict[str, RunStats] = {}
        self._lock = asyncio.Lock()

    async def try_acquire(
        self,
        pipeline_id: str,
        trigger_id: str,
        trigger_type: str,
    ) -> bool:
        """
        Try to acquire the run slot for a pipeline.

        Returns:
            True if acquired, False if skipped/queued
        """
        async with self._lock:
            stats = self._stats.setdefault(pipeline_id, RunStats())

            if pipeline_id in self._running:
                # Already running - apply overlap policy
                policy = self._get_overlap_policy(trigger_type)

                if policy == OverlapPolicy.SKIP:
                    stats.total_skipped += 1
                    stats.last_skip_at = datetime.now(timezone.utc)
                    logger.warning(
                        "Skipping trigger %s for %s: already running",
                        trigger_id,
                        pipeline_id,
                    )
                    return False

                else:  # QUEUE
                    # Coalesce: replace any existing pending
                    if self._pending.get(pipeline_id):
                        logger.info(
                            "Coalescing trigger %s for %s: replacing pending",
                            trigger_id,
                            pipeline_id,
                        )
                    self._pending[pipeline_id] = PendingRun(
                        trigger_id=trigger_id,
                        trigger_type=trigger_type,
                    )
                    stats.total_queued += 1
                    return False

            # Not running - acquire slot
            return True

    def mark_running(self, pipeline_id: str, task: asyncio.Task) -> None:
        """Mark a pipeline as running."""
        self._running[pipeline_id] = task
        stats = self._stats.setdefault(pipeline_id, RunStats())
        stats.total_runs += 1
        stats.last_run_at = datetime.now(timezone.utc)

    async def release(self, pipeline_id: str) -> PendingRun | None:
        """
        Release the run slot for a pipeline.

        Returns:
            Pending run if one was queued, None otherwise
        """
        async with self._lock:
            self._running.pop(pipeline_id, None)
            return self._pending.pop(pipeline_id, None)

    def is_running(self, pipeline_id: str) -> bool:
        """Check if pipeline is currently running."""
        return pipeline_id in self._running

    def get_stats(self, pipeline_id: str) -> RunStats | None:
        """Get run statistics for a pipeline."""
        return self._stats.get(pipeline_id)

    def _get_overlap_policy(self, trigger_type: str) -> OverlapPolicy:
        """Get overlap policy based on trigger type."""
        if trigger_type == "interval":
            return OverlapPolicy.SKIP
        else:
            return OverlapPolicy.QUEUE


# Global gate instance
_gate: SingleFlightGate | None = None


def get_single_flight_gate() -> SingleFlightGate:
    """Get the global single-flight gate."""
    global _gate
    if _gate is None:
        _gate = SingleFlightGate()
    return _gate


def reset_single_flight_gate() -> None:
    """Reset the global gate (for testing)."""
    global _gate
    _gate = None
```

**Testing**:

- File: `tests/k0/scheduler/test_concurrency.py`
- Test cases:
  - `test_try_acquire_succeeds_when_not_running`
  - `test_try_acquire_skip_interval_when_running`
  - `test_try_acquire_queue_threshold_when_running`
  - `test_try_acquire_queue_manual_when_running`
  - `test_coalesce_replaces_pending`
  - `test_release_returns_pending`
  - `test_release_clears_running`
  - `test_stats_tracks_runs_and_skips`

**Acceptance Criteria**:

- [ ] Single-flight gate prevents concurrent runs
- [ ] INTERVAL triggers are skipped when running
- [ ] THRESHOLD/MANUAL triggers are queued
- [ ] Pending runs are coalesced (max 1)
- [ ] Stats track runs, skips, and queued
- [ ] All tests pass

---

#### Issue 3.3.2: Add Hot Reload with Atomic Swap

**File**: `k0/scheduler/scheduler.py`

**Description**: Add hot reload support with atomic trigger swap.

**Implementation**:

Add to `PipelineScheduler`:

```python
class PipelineScheduler:
    def __init__(self, ...):
        # ... existing ...
        self._reload_lock = asyncio.Lock()
        self._drain_timeout_seconds = 30

    async def hot_reload(
        self,
        new_specs: dict[str, PipelineSpec],
        affected_pipelines: set[str] | None = None,
    ) -> HotReloadResult:
        """
        Atomically swap trigger configuration.

        Per ADR-K004:
        1. Build new config in memory
        2. Acquire reload lock
        3. Cancel triggers for affected pipelines
        4. Drain in-flight runs (with timeout)
        5. Install new triggers
        6. Release lock

        Args:
            new_specs: New pipeline specifications
            affected_pipelines: Pipelines to reload (None = all)

        Returns:
            HotReloadResult with success/error info
        """
        async with self._reload_lock:
            affected = affected_pipelines or set(self._active_triggers.keys())
            result = HotReloadResult(affected_pipelines=list(affected))

            try:
                # Step 1: Cancel affected triggers
                for pipeline_id in affected:
                    await self._cancel_triggers(pipeline_id)

                # Step 2: Drain in-flight runs
                await self._drain_in_flight(affected)

                # Step 3: Install new triggers
                for pipeline_id, spec in new_specs.items():
                    if pipeline_id in affected and spec.triggers:
                        for trigger in spec.triggers:
                            await self._register_trigger(pipeline_id, spec, trigger)

                result.success = True

            except Exception as e:
                result.success = False
                result.error = str(e)
                logger.error("Hot reload failed: %s", e)

            return result

    async def _drain_in_flight(self, pipeline_ids: set[str]) -> None:
        """Wait for in-flight runs to complete."""
        gate = get_single_flight_gate()
        in_flight = [pid for pid in pipeline_ids if gate.is_running(pid)]

        if not in_flight:
            return

        logger.info("Draining %d in-flight runs...", len(in_flight))

        # Wait with timeout
        deadline = asyncio.get_event_loop().time() + self._drain_timeout_seconds
        while in_flight and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.5)
            in_flight = [pid for pid in in_flight if gate.is_running(pid)]

        if in_flight:
            logger.warning(
                "Drain timeout: %d runs still in flight: %s",
                len(in_flight),
                in_flight,
            )

    async def _cancel_triggers(self, pipeline_id: str) -> None:
        """Cancel all triggers for a pipeline."""
        handles = self._active_triggers.pop(pipeline_id, [])
        for handle in handles:
            handle.cancel()
        await asyncio.sleep(0)  # Let cancellation propagate


@dataclass
class HotReloadResult:
    """Result of hot reload operation."""
    affected_pipelines: list[str]
    success: bool = False
    error: str | None = None
```

**Testing**:

- File: `tests/k0/scheduler/test_hot_reload.py`
- Test cases:
  - `test_hot_reload_cancels_old_triggers`
  - `test_hot_reload_waits_for_drain`
  - `test_hot_reload_installs_new_triggers`
  - `test_hot_reload_atomic_no_partial_state`
  - `test_hot_reload_timeout_logs_warning`
  - `test_hot_reload_error_returns_failure`

**Acceptance Criteria**:

- [ ] Hot reload is atomic (lock held)
- [ ] Old triggers cancelled before new installed
- [ ] In-flight runs drained with timeout
- [ ] Result indicates success/failure
- [ ] All tests pass

---

#### Issue 3.3.3: Add Registry Thread Safety

**File**: `k0/fabric/registry.py`

**Description**: Add asyncio locks for registry mutations.

**Implementation**:

Update `CapabilityRegistry`:

```python
class CapabilityRegistry:
    def __init__(self):
        # ... existing ...
        self._register_lock = asyncio.Lock()
        self._metrics_lock = asyncio.Lock()

    async def register_async(
        self,
        capability: str,
        provider: CapabilityProvider,
        handler: Callable | None = None,
    ) -> None:
        """Thread-safe registration."""
        async with self._register_lock:
            self._do_register(capability, provider, handler)

    def resolve(self, capability: str, strategy: ResolutionStrategy) -> RegisteredProvider | None:
        """Thread-safe resolution (copy-on-read)."""
        # Return copy to prevent mutation during iteration
        providers = list(self._providers.get(capability, []))
        if not providers:
            return None
        # ... existing resolution logic on copy ...

    async def record_call_async(
        self,
        capability: str,
        provider_id: str,
        latency_ms: float,
        error: bool,
    ) -> None:
        """Thread-safe metrics recording."""
        async with self._metrics_lock:
            self._do_record_call(capability, provider_id, latency_ms, error)
```

**Testing**:

- File: `tests/k0/fabric/test_registry_threadsafe.py`
- Test cases:
  - `test_concurrent_register_no_corruption`
  - `test_concurrent_resolve_returns_copy`
  - `test_concurrent_record_call_no_race`
  - `test_resolve_during_register_safe`

**Acceptance Criteria**:

- [ ] Concurrent registrations don't corrupt state
- [ ] Resolve returns copy (iteration safe)
- [ ] Metrics recording is thread-safe
- [ ] All tests pass

---

#### Issue 3.3.4: Add Trigger Audit Logging

**File**: `k0/scheduler/audit.py`

**Description**: Add structured audit logging for trigger events.

**Implementation**:

```python
"""
Scheduler Audit Logging - Structured audit events for triggers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

audit_logger = logging.getLogger("k0.scheduler.audit")


@dataclass(frozen=True, slots=True)
class TriggerFiredEvent:
    """Logged when trigger activates pipeline."""
    event: str = "trigger.fired"
    timestamp: str = ""
    pipeline_id: str = ""
    trigger_id: str = ""
    trigger_type: str = ""


@dataclass(frozen=True, slots=True)
class TriggerSkippedEvent:
    """Logged when trigger is skipped due to overlap policy."""
    event: str = "trigger.skipped"
    timestamp: str = ""
    pipeline_id: str = ""
    trigger_id: str = ""
    trigger_type: str = ""
    reason: str = ""  # "already_running", "coalesced"


class SchedulerAuditor:
    """Audit logger for scheduler events."""

    def __init__(self, logger: logging.Logger | None = None):
        self._logger = logger or audit_logger

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def log_trigger_fired(
        self,
        pipeline_id: str,
        trigger_id: str,
        trigger_type: str,
    ) -> None:
        """Log trigger activation."""
        event = TriggerFiredEvent(
            timestamp=self._now_iso(),
            pipeline_id=pipeline_id,
            trigger_id=trigger_id,
            trigger_type=trigger_type,
        )
        self._logger.info(asdict(event))

    def log_trigger_skipped(
        self,
        pipeline_id: str,
        trigger_id: str,
        trigger_type: str,
        reason: str,
    ) -> None:
        """Log trigger skip."""
        event = TriggerSkippedEvent(
            timestamp=self._now_iso(),
            pipeline_id=pipeline_id,
            trigger_id=trigger_id,
            trigger_type=trigger_type,
            reason=reason,
        )
        self._logger.warning(asdict(event))


_auditor: SchedulerAuditor | None = None


def get_scheduler_auditor() -> SchedulerAuditor:
    """Get the global scheduler auditor."""
    global _auditor
    if _auditor is None:
        _auditor = SchedulerAuditor()
    return _auditor
```

**Testing**:

- File: `tests/k0/scheduler/test_audit.py`
- Test cases:
  - `test_log_trigger_fired`
  - `test_log_trigger_skipped`
  - `test_audit_event_has_all_fields`

**Acceptance Criteria**:

- [ ] Trigger fired events logged with correct fields
- [ ] Trigger skipped events logged with reason
- [ ] Audit logger uses separate namespace (k0.scheduler.audit)
- [ ] All tests pass

---

## Milestone 4: P03 Integration (M4)

**Objective**: Integrate P03 with CapabilityFabric for salience scoring.

**Dependencies**: M2 complete

### Epic 4.0: P03 Pipeline Contract (Prerequisite)

Create the P03 pipeline contract (currently missing from codebase).

#### Issue 4.0.1: Create P03 Pipeline Contract

**File**: `k0/contracts/pipelines/p03_consolidation.v1.yaml`

**Description**: Create minimal P03 pipeline contract for fabric integration.

**Gap Identified**: P03 pipeline contract does not exist. Only `p02_write.v1.yaml` and `p08_embedding_management.v2.yaml` exist in `k0/contracts/pipelines/`. P03 implementation status is "NOT STARTED" per dossier.

**Implementation**:

```yaml
# P03 Consolidation Pipeline Contract
# Version: v1 (Minimal for Fabric Integration)
# Reference: docs/pipelines/P03_consolidation_dossier.md

pipeline_id: P03_CONSOLIDATION
version: v1
name: P03 Memory Consolidation

description: |
  Memory consolidation pipeline - transforms staged hippocampus events
  into permanent, organized, queryable memory structures.

  Runs in batch mode during system idle time (preferred: 2AM-5AM).
  Performs 5 consolidation processes:
  1. Hippocampal Replay
  2. Neocortical Integration
  3. Synaptic Homeostasis (dedup, novelty, pruning)
  4. Knowledge Graph Consolidation
  5. Dream-Like Exploration

# P03 is scheduled, not event-driven
entry_topic: scheduled.p03.trigger.v1
exit_topic: p03.consolidation.complete.v1

# Trigger configuration (Phase 1: INTERVAL and MANUAL only)
triggers:
  - id: consolidation_interval
    type: interval
    interval_seconds: 5400  # 90 minutes (sleep cycle)
    batch_size: 1000

  - id: consolidation_manual
    type: manual

concurrency: 1
max_queue_depth: 100

required_capabilities:
  # Input: hippocampus staging
  - st_hipp_events.read
  - st_hipp_events.write
  - st_vec.read
  - st_vec.write
  # Output: memory layers
  - st_epi.write
  - st_sem.write
  - st_kg_dom.write
  - st_kg_edges.write
  # FAISS for similarity
  - faiss.read

# Fabric dependencies (capabilities P03 will invoke)
fabric_dependencies:
  - score_salience
  - retrieve_similar

# Minimal DAG for Phase 1 (will expand per dossier)
dag:
  - id: stage_10_novelty
    module: consolidation.novelty_score:v1
    depends_on: []
    description: "Compute novelty scores for pending events"
    latency_budget_ms: 100

performance:
  batch_processing_target: 1000 events in 15 minutes
```

**Testing**:

- File: `tests/contracts/test_p03_contract.py`
- Test cases:
  - `test_p03_contract_loads_without_error`
  - `test_p03_contract_validates_schema`
  - `test_p03_has_triggers`
  - `test_p03_has_fabric_dependencies`

**Acceptance Criteria**:

- [ ] P03 contract exists at `k0/contracts/pipelines/p03_consolidation.v1.yaml`
- [ ] Contract validates against PipelineSpec schema
- [ ] Has triggers field (interval + manual)
- [ ] Documents fabric_dependencies
- [ ] All tests pass

---

### Epic 4.1: P03 Fabric Integration

Update P03 to use CapabilityFabric for module invocation.

#### Issue 4.1.1: Update salience.score Module Contract

**File**: `k0/contracts/modules/salience.score.v1.yaml`

**Description**: Add fabric_callable and fabric_capabilities to module contract.

**Changes Required**:

```yaml
# Add to salience.score.v1.yaml

fabric_callable: true
fabric_capabilities:
  - score_salience
fabric_context_policy: inherit
```

**Testing**:

- File: `tests/contracts/test_module_contracts.py` (extend existing)
- Test cases:
  - `test_salience_score_contract_has_fabric_fields`
  - `test_salience_score_fabric_capabilities_correct`

**Acceptance Criteria**:

- [ ] Module contract has fabric_callable: true
- [ ] fabric_capabilities includes score_salience
- [ ] Contract validates without errors
- [ ] All tests pass

---

#### Issue 4.1.2: Update P03 Contract for Fabric Usage

**File**: `k0/contracts/pipelines/p03_salience.v1.yaml`

**Description**: Document fabric usage in P03 pipeline contract.

**Changes Required**:

Add to pipeline contract metadata:

```yaml
# P03 contract additions

fabric_dependencies:
  - score_salience

stages:
  - id: score
    module: salience.score
    description: "Compute salience via fabric"
    fabric_invocation: true  # Indicates this stage uses fabric
```

**Testing**:

- File: `tests/contracts/test_pipeline_contracts.py` (extend existing)
- Test cases:
  - `test_p03_contract_has_fabric_dependencies`
  - `test_p03_stage_fabric_invocation_flag`

**Acceptance Criteria**:

- [ ] P03 contract documents fabric dependencies
- [ ] Stage has fabric_invocation flag
- [ ] Contract validates
- [ ] All tests pass

---

#### Issue 4.1.3: Update P03 Module to Use Fabric (Optional Pattern)

**File**: `k0/modules/salience/score.py`

**Description**: Demonstrate fabric pattern (P03 can call other capabilities via fabric).

**Implementation Notes**:

P03's salience.score module is the **provider** of score_salience capability,
so it doesn't need to call the fabric itself. However, if P03 needed to call
another capability (e.g., retrieve_similar), the pattern would be:

```python
# Example: If P03 needed to call another capability

def run(
    *,
    context: PipelineContext,
    envelope_id: str,
    content: str,
    **kwargs,
) -> dict:
    """Score content salience, optionally using fabric for retrieval."""

    # If we need similar content for context-aware scoring
    if context.fabric:
        similar = context.fabric.invoke(
            "retrieve_similar",
            context=context,
            query=content,
            limit=5,
        )

    # Compute score
    score = _compute_salience(content, similar)

    return {"salience_score": score}
```

For P03, the primary change is ensuring the module is **registered** as a
fabric provider, which happens automatically via Issue 2.2.2.

**Testing**:

- File: `tests/k0/modules/salience/test_score.py` (extend existing)
- Test cases:
  - `test_score_module_accessible_via_fabric`
  - `test_fabric_invoke_score_salience`

**Acceptance Criteria**:

- [ ] salience.score accessible via fabric
- [ ] Fabric invoke returns correct result
- [ ] All tests pass

---

### Epic 4.2: P03 End-to-End Validation

Validate P03 works correctly with fabric integration.

#### Issue 4.2.1: Create P03 Fabric Integration Test

**File**: `tests/integration/test_p03_fabric.py`

**Description**: End-to-end test for P03 with fabric.

**Implementation**:

```python
"""
P03 Fabric Integration Tests.

Validates that P03 (salience scoring) works correctly with
the CapabilityFabric for module discovery and invocation.
"""

import pytest

from k0.fabric import get_capability_fabric, reset_capability_registry
from k0.fabric.loader import discover_and_register_capabilities
from k0.runtime.module_registry import get_module_registry


@pytest.fixture
def setup_fabric():
    """Set up fabric with capabilities registered."""
    reset_capability_registry()

    module_registry = get_module_registry()
    discover_and_register_capabilities(module_registry)

    yield get_capability_fabric()

    reset_capability_registry()


class TestP03FabricIntegration:
    """P03 integration with CapabilityFabric."""

    def test_score_salience_capability_registered(self, setup_fabric):
        """Verify score_salience capability is registered."""
        from k0.fabric.registry import get_capability_registry

        registry = get_capability_registry()
        capabilities = registry.list_capabilities()

        assert "score_salience" in capabilities

    def test_fabric_invoke_score_salience(self, setup_fabric):
        """Invoke score_salience via fabric."""
        fabric = setup_fabric

        result = fabric.invoke(
            "score_salience",
            content="Important meeting tomorrow",
        )

        assert "salience_score" in result
        assert isinstance(result["salience_score"], float)

    def test_p03_pipeline_uses_fabric_handler(self, setup_fabric):
        """Verify P03 pipeline stage uses fabric-registered handler."""
        from k0.fabric.registry import get_capability_registry

        registry = get_capability_registry()
        provider = registry.resolve("score_salience")

        assert provider is not None
        assert provider.provider.module_id == "salience.score:v1"
        assert provider.handler is not None
```

**Acceptance Criteria**:

- [ ] Integration test validates fabric registration
- [ ] Integration test validates fabric invocation
- [ ] Integration test validates handler binding
- [ ] All tests pass

---

## Milestone 5: P08 Migration (M5)

**Objective**: Migrate P08 from hardcoded scheduler to declarative triggers.

**Dependencies**: M3 complete

### Epic 5.1: P08 Trigger Configuration

Add declarative triggers to P08 contract.

#### Issue 5.1.1: Update P08 Contract with Triggers

**File**: `k0/contracts/pipelines/p08_embedding_management.v2.yaml`

**Description**: Add declarative triggers to replace hardcoded scheduler.

**Current State** (from contract):

```yaml
trigger_mode: scheduled
# But scheduling is hardcoded in k0/kernel/app.py
```

**Changes Required**:

```yaml
# Replace trigger_mode with declarative triggers

triggers:
  # Interval trigger: every 5 minutes
  - id: faiss_indexer_interval
    type: interval
    interval_seconds: 300
    batch_size: 100

  # Threshold trigger: when 50+ embeddings pending
  - id: faiss_indexer_threshold
    type: threshold
    table: st_vec
    condition: "status = 'READY'"
    threshold_count: 50
    check_interval_seconds: 60
    batch_size: 50

  # Manual trigger: for admin-initiated indexing
  - id: faiss_indexer_manual
    type: manual
```

**Testing**:

- File: `tests/contracts/test_p08_triggers.py`
- Test cases:
  - `test_p08_contract_has_triggers`
  - `test_p08_interval_trigger_valid`
  - `test_p08_threshold_trigger_valid`
  - `test_p08_manual_trigger_valid`
  - `test_p08_triggers_validate_schema`

**Acceptance Criteria**:

- [ ] P08 contract has declarative triggers
- [ ] All trigger types properly configured
- [ ] Contract validates against schema
- [ ] All tests pass

---

### Epic 5.2: Remove Hardcoded P08 Scheduler

Remove the hardcoded scheduler loop from kernel.

#### Issue 5.2.1: Remove _p08_faiss_indexer_loop

**File**: `k0/kernel/app.py`

**Description**: Remove hardcoded P08 scheduler.

**Wiring Details**:

Current code (lines 500-620 approximately):

```python
async def _p08_faiss_indexer_loop():
    """Hardcoded P08 FAISS indexer loop."""
    while True:
        await asyncio.sleep(300)  # 5 minutes
        # ... indexing logic
```

And in lifespan():

```python
asyncio.create_task(_p08_faiss_indexer_loop())
```

**Changes Required**:

1. Delete `_p08_faiss_indexer_loop()` function entirely
2. Remove the `asyncio.create_task(_p08_faiss_indexer_loop())` call
3. P08 will now be activated via PipelineScheduler triggers

**Testing**:

- File: `tests/k0/kernel/test_app.py` (extend existing)
- Test cases:
  - `test_no_hardcoded_p08_loop`
  - `test_p08_scheduled_via_scheduler`

**Acceptance Criteria**:

- [ ] Hardcoded loop removed
- [ ] No direct P08 scheduling in app.py
- [ ] P08 activates via scheduler triggers
- [ ] All tests pass

---

#### Issue 5.2.2: Create P08 Migration Integration Test

**File**: `tests/integration/test_p08_scheduler_migration.py`

**Description**: Validate P08 works with declarative triggers.

**Implementation**:

```python
"""
P08 Scheduler Migration Integration Tests.

Validates that P08 (embedding management) works correctly
with declarative triggers instead of hardcoded scheduler.
"""

import asyncio
import pytest

from k0.scheduler import PipelineScheduler, ManualTriggerEngine


@pytest.fixture
async def scheduler_with_p08(mock_pipeline_runner, mock_syscalls):
    """Set up scheduler with P08 registered."""
    from k0.runtime.schemas import PipelineSpec, TriggerSpec, TriggerType

    scheduler = PipelineScheduler(mock_pipeline_runner, mock_syscalls)

    # Create P08 spec with triggers
    p08_spec = PipelineSpec(
        id="p08_embedding_management",
        version="v2",
        triggers=[
            TriggerSpec(
                id="faiss_indexer_interval",
                type=TriggerType.INTERVAL,
                interval_seconds=1,  # Fast for testing
            ),
            TriggerSpec(
                id="faiss_indexer_manual",
                type=TriggerType.MANUAL,
            ),
        ],
    )

    scheduler.register_pipeline(p08_spec)
    await scheduler.start()

    yield scheduler

    await scheduler.stop()


class TestP08SchedulerMigration:
    """P08 migration to declarative triggers."""

    async def test_p08_registered_with_scheduler(self, scheduler_with_p08):
        """Verify P08 is registered with scheduler."""
        scheduler = scheduler_with_p08
        pipelines = scheduler.list_scheduled_pipelines()

        assert "p08_embedding_management" in pipelines

    async def test_p08_interval_trigger_fires(
        self,
        scheduler_with_p08,
        mock_pipeline_runner,
    ):
        """Verify interval trigger fires and executes P08."""
        # Wait for interval trigger (1 second in test)
        await asyncio.sleep(1.5)

        # Check pipeline was executed
        assert mock_pipeline_runner.execute.called
        call_args = mock_pipeline_runner.execute.call_args
        assert call_args[0][0] == "p08_embedding_management"

    async def test_p08_manual_trigger_fires(
        self,
        scheduler_with_p08,
        mock_pipeline_runner,
    ):
        """Verify manual trigger can be fired."""
        scheduler = scheduler_with_p08

        result = scheduler.fire_manual_trigger(
            "p08_embedding_management",
            "faiss_indexer_manual",
        )

        assert result is True

        # Allow async execution
        await asyncio.sleep(0.1)

        # Check pipeline was executed
        assert mock_pipeline_runner.execute.called

    async def test_p08_stats_tracked(self, scheduler_with_p08):
        """Verify trigger stats are tracked."""
        scheduler = scheduler_with_p08

        # Fire manual trigger
        scheduler.fire_manual_trigger(
            "p08_embedding_management",
            "faiss_indexer_manual",
        )

        await asyncio.sleep(0.1)

        stats = scheduler.get_pipeline_stats("p08_embedding_management")

        assert stats is not None
        assert stats["trigger_count"] >= 1
```

**Acceptance Criteria**:

- [ ] P08 registered with scheduler
- [ ] Interval trigger fires and executes P08
- [ ] Manual trigger works
- [ ] Stats are tracked
- [ ] All tests pass

---

## Phase 2 Milestones (Future Enhancement)

The following milestones are planned for Phase 2 and are **not** part of the initial release.
They require additional infrastructure and dependencies.

---

## Milestone 6: CRON Trigger Engine (M6)

**Objective**: Add cron-based scheduling for pipelines (required for P03 scheduled consolidation).

**Dependencies**: M3 (PipelineScheduler core)

**Duration**: 3 days

**Blocks**: P03 scheduled consolidation (2AM-5AM window)

**Prerequisites**:

- Cron expression parser library (`croniter>=2.0.0`)
- Timezone handling infrastructure

### Epic 6.1: CronTriggerEngine Implementation

#### Issue 6.1.1: Add Cron Parser Dependency

**Type**: Infrastructure
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `infrastructure`, `scheduler`, `phase2`

**File**: `pyproject.toml`

**Description**: Add `croniter` library for cron expression parsing.

**Changes**:

```toml
[project.dependencies]
# ... existing dependencies ...

[project.optional-dependencies]
scheduler = [
    "croniter>=2.0.0",
]
```

**Acceptance Criteria**:

- [ ] `croniter` added to optional dependencies
- [ ] Can import `from croniter import croniter`
- [ ] Version constraint allows security updates

**Testing**:

- Manual verification: `pip install -e ".[scheduler]"`

---

#### Issue 6.1.2: Implement CronTriggerEngine Class

**Type**: Implementation
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `implementation`, `scheduler`, `phase2`

**File**: `k0/scheduler/triggers.py`

**Description**: Implement cron-based trigger engine that fires at scheduled times.

**Implementation**:

```python
class CronTriggerEngine(TriggerEngine):
    """
    Trigger based on cron expression.

    Supports standard 5-field cron expressions:
    - minute (0-59)
    - hour (0-23)
    - day of month (1-31)
    - month (1-12)
    - day of week (0-6, Sunday=0)

    Example spec:
        - id: consolidation_nightly
          type: cron
          cron_expression: "0 2 * * *"  # 2 AM daily

    P03 Use Case:
        - Consolidation window: "0 2-5 * * *" (2AM-5AM hourly)
    """

    def __init__(
        self,
        spec: "TriggerSpec",
        pipeline_id: str,
        timezone: str = "UTC",
    ):
        super().__init__(spec, pipeline_id)
        self._timezone = timezone
        self._cron: "croniter" | None = None
        self._task: asyncio.Task | None = None
        self._callback: TriggerCallback | None = None

    async def start(self, callback: TriggerCallback) -> None:
        """Start cron trigger engine."""
        if self._running:
            logger.warning(
                "CronTriggerEngine %s already running",
                self.spec.id,
            )
            return

        try:
            from croniter import croniter
        except ImportError as e:
            raise RuntimeError(
                "croniter not installed. Install with: pip install croniter"
            ) from e

        if not self.spec.cron_expression:
            raise ValueError(f"Cron trigger {self.spec.id} missing cron_expression")

        self._callback = callback
        self._cron = croniter(self.spec.cron_expression)
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

        logger.info(
            "CronTriggerEngine %s started with expression: %s",
            self.spec.id,
            self.spec.cron_expression,
            extra={
                "trigger_id": self.spec.id,
                "pipeline_id": self.pipeline_id,
                "cron_expression": self.spec.cron_expression,
            },
        )

    async def stop(self) -> None:
        """Stop cron trigger engine."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info(
            "CronTriggerEngine %s stopped (fired %d times)",
            self.spec.id,
            self._fire_count,
            extra={"trigger_id": self.spec.id, "fire_count": self._fire_count},
        )

    async def _run_loop(self) -> None:
        """Main loop - sleep until next cron time, then fire."""
        while self._running:
            try:
                # Get next scheduled time
                next_fire = self._cron.get_next(float)
                now = time.time()
                delay = next_fire - now

                if delay > 0:
                    logger.debug(
                        "CronTrigger %s sleeping for %.1f seconds until next fire",
                        self.spec.id,
                        delay,
                    )
                    await asyncio.sleep(delay)

                if self._running and self._callback:
                    event = self._create_event({
                        "scheduled_time": next_fire,
                        "trigger_type": "cron",
                        "cron_expression": self.spec.cron_expression,
                    })
                    self._record_fire(event)
                    self._callback(event)

                    logger.info(
                        "CronTrigger %s fired (count=%d)",
                        self.spec.id,
                        self._fire_count,
                        extra={
                            "trigger_id": self.spec.id,
                            "pipeline_id": self.pipeline_id,
                            "fire_count": self._fire_count,
                            "scheduled_time": next_fire,
                        },
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "CronTrigger %s error: %s",
                    self.spec.id,
                    str(e),
                    exc_info=True,
                )
                # Sleep before retry to prevent tight error loop
                await asyncio.sleep(60)

    def get_next_fire_time(self) -> float | None:
        """Return next scheduled fire time (for debugging/observability)."""
        if self._cron:
            return self._cron.get_next(float, start_time=time.time())
        return None
```

**Acceptance Criteria**:

- [ ] CronTriggerEngine parses cron expressions
- [ ] Engine fires at scheduled times
- [ ] Handles timezone correctly (default UTC)
- [ ] Logs next fire time for observability
- [ ] Graceful error handling (doesn't crash on invalid expression)

**Files to Create/Modify**:

- Modify: `k0/scheduler/triggers.py`

---

#### Issue 6.1.3: Update create_trigger_engine Factory

**Type**: Implementation
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `implementation`, `scheduler`, `phase2`

**File**: `k0/scheduler/triggers.py`

**Description**: Update factory function to handle CRON trigger type.

**Changes**:

```python
def create_trigger_engine(
    spec: "TriggerSpec",
    pipeline_id: str,
    syscalls: "Syscalls | None" = None,
    activity_tracker: "ActivityTracker | None" = None,  # NEW: for IDLE triggers
) -> TriggerEngine:
    """
    Factory function to create appropriate trigger engine.

    Phase 1 triggers: INTERVAL, THRESHOLD, MANUAL
    Phase 2 triggers: CRON, IDLE
    """
    from k0.runtime.schemas import TriggerType

    if spec.type == TriggerType.INTERVAL:
        return IntervalTriggerEngine(spec, pipeline_id)

    elif spec.type == TriggerType.THRESHOLD:
        if syscalls is None:
            raise ValueError(f"Threshold trigger {spec.id} requires syscalls")
        return ThresholdTriggerEngine(spec, pipeline_id, syscalls)

    elif spec.type == TriggerType.MANUAL:
        return ManualTriggerEngine(spec, pipeline_id)

    elif spec.type == TriggerType.CRON:
        # Phase 2: CRON trigger
        return CronTriggerEngine(spec, pipeline_id)

    elif spec.type == TriggerType.IDLE:
        # Phase 2: IDLE trigger
        if activity_tracker is None:
            raise ValueError(f"Idle trigger {spec.id} requires activity_tracker")
        return IdleTriggerEngine(spec, pipeline_id, activity_tracker)

    else:
        raise ValueError(f"Unsupported trigger type: {spec.type}")
```

**Acceptance Criteria**:

- [ ] Factory creates CronTriggerEngine for CRON type
- [ ] Remove NotImplementedError for CRON
- [ ] Backward compatible with existing Phase 1 triggers

**Files to Modify**:

- `k0/scheduler/triggers.py`

---

#### Issue 6.1.4: Add CronTriggerEngine Tests

**Type**: Testing
**Priority**: Critical
**Assignee**: QA Engineer
**Labels**: `testing`, `scheduler`, `phase2`

**File**: `tests/k0/scheduler/test_triggers_cron.py`

**Description**: Comprehensive tests for CronTriggerEngine.

**Test Cases**:

```python
class TestCronTriggerEngine:
    """Tests for CronTriggerEngine."""

    def test_cron_trigger_parses_valid_expression(self):
        """Valid cron expression is parsed without error."""

    def test_cron_trigger_rejects_invalid_expression(self):
        """Invalid cron expression raises ValueError."""

    async def test_cron_trigger_fires_at_scheduled_time(self):
        """Trigger fires at the scheduled cron time."""
        # Use freezegun or similar to control time

    async def test_cron_trigger_fires_multiple_times(self):
        """Trigger fires repeatedly according to schedule."""

    async def test_cron_trigger_stop_cancels_task(self):
        """Stopping trigger cancels the background task."""

    def test_cron_trigger_get_next_fire_time(self):
        """get_next_fire_time returns correct timestamp."""

    async def test_cron_trigger_handles_error_gracefully(self):
        """Engine continues after transient errors."""

    def test_cron_trigger_context_includes_expression(self):
        """TriggerEvent context includes cron_expression."""

    async def test_cron_trigger_records_fire_count(self):
        """Fire count is incremented on each trigger."""

    def test_cron_trigger_requires_croniter(self):
        """ImportError raised if croniter not installed."""
```

**Acceptance Criteria**:

- [ ] All test cases pass
- [ ] >90% code coverage for CronTriggerEngine
- [ ] Time-sensitive tests use mocking (freezegun or time.monotonic patch)

**Files to Create**:

- `tests/k0/scheduler/test_triggers_cron.py`

---

#### Issue 6.1.5: Document CRON Trigger Usage

**Type**: Documentation
**Priority**: High
**Assignee**: Tech Lead
**Labels**: `documentation`, `scheduler`, `phase2`

**Files**:

- `k0/fabric/pipeline-fabric-integration-guide.md`
- `k0/scheduler/README.md`

**Description**: Update documentation to include CRON trigger usage.

**Documentation Updates**:

1. **pipeline-fabric-integration-guide.md Section 3.3**: Update TriggerType enum status
   - Change CRON from "Not yet implemented" to "Phase 2 (Implemented)"

2. **pipeline-fabric-integration-guide.md Section 7.4**: Add CronTriggerEngine row

3. **Create scheduler README**: Document all trigger types with examples

**Example YAML for P03**:

```yaml
# P03 consolidation triggers
triggers:
  # Nightly consolidation at 2 AM
  - id: consolidation_nightly
    type: cron
    cron_expression: "0 2 * * *"

  # Hourly during sleep window (2-5 AM)
  - id: consolidation_sleep_window
    type: cron
    cron_expression: "0 2-5 * * *"
```

**Acceptance Criteria**:

- [ ] CRON trigger documented in integration guide
- [ ] Example YAML for P03 use case
- [ ] Scheduler README created

---

## Milestone 7: IDLE Trigger Engine (M7)

**Objective**: Add idle-detection triggers for background processing (required for P03 idle consolidation).

**Dependencies**: M3 (PipelineScheduler core)

**Duration**: 4 days

**Blocks**: P03 idle-based consolidation (5min idle + 100 pending items)

**Prerequisites**:

- Activity tracking infrastructure (ActivityTracker class)
- BusDispatcher integration for activity recording
- Pending item count via syscalls.query_count()

### Epic 7.1: ActivityTracker Infrastructure

#### Issue 7.1.1: Implement ActivityTracker Class

**Type**: Implementation
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `infrastructure`, `scheduler`, `phase2`

**File**: `k0/scheduler/activity.py`

**Description**: Track system activity for idle detection. This is kernel infrastructure that records when the system is "active" (processing requests, dispatching events, etc.).

**Implementation**:

```python
"""
Activity tracking for idle detection triggers.

The ActivityTracker is a kernel-level component that records system activity.
It integrates with BusDispatcher to automatically record activity on each
event dispatch.

P03 Use Case:
    - Fire consolidation when system idle for 5 minutes
    - AND at least 100 pending items in embedding queue
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass
class IdleListener:
    """Registered idle listener with callback and threshold."""

    callback: Callable[[], None]
    threshold_seconds: float
    id: str
    fired: bool = False  # Reset when activity occurs


class ActivityTracker:
    """
    Tracks system activity for idle detection.

    Thread-safe. Called from BusDispatcher on every event dispatch
    and from API handlers on user requests.

    Metrics:
        - activity_tracker_records_total: Count of activity records
        - activity_tracker_idle_seconds: Current idle duration gauge
        - activity_tracker_listeners_total: Number of registered listeners
    """

    def __init__(self, check_interval: float = 1.0):
        """
        Initialize activity tracker.

        Args:
            check_interval: How often to check idle conditions (seconds)
        """
        self._last_activity = time.monotonic()
        self._listeners: dict[str, IdleListener] = {}
        self._lock = asyncio.Lock()
        self._check_interval = check_interval
        self._running = False
        self._task: asyncio.Task | None = None

    def record_activity(self) -> None:
        """
        Record activity (called on bus dispatch, API request, etc.).

        This resets the idle timer and marks all listeners as unfired
        so they can fire again after the next idle period.

        Thread-safe via atomic timestamp update.
        """
        self._last_activity = time.monotonic()

        # Reset fired flags so listeners can fire again
        for listener in self._listeners.values():
            listener.fired = False

        logger.debug(
            "Activity recorded, idle timer reset",
            extra={"listener_count": len(self._listeners)},
        )

    def idle_seconds(self) -> float:
        """Return seconds since last activity."""
        return time.monotonic() - self._last_activity

    async def register_idle_listener(
        self,
        listener_id: str,
        callback: Callable[[], None],
        threshold_seconds: float,
    ) -> None:
        """
        Register callback to fire when idle exceeds threshold.

        Args:
            listener_id: Unique identifier for this listener
            callback: Sync callback to invoke when idle threshold met
            threshold_seconds: Minimum idle duration before firing

        Note:
            Callback is invoked from async context but should be sync.
            If callback needs async, wrap in asyncio.create_task().
        """
        async with self._lock:
            self._listeners[listener_id] = IdleListener(
                callback=callback,
                threshold_seconds=threshold_seconds,
                id=listener_id,
            )
            logger.info(
                "Registered idle listener %s (threshold=%.1fs)",
                listener_id,
                threshold_seconds,
                extra={
                    "listener_id": listener_id,
                    "threshold_seconds": threshold_seconds,
                },
            )

    async def unregister_idle_listener(self, listener_id: str) -> bool:
        """
        Unregister an idle listener.

        Returns:
            True if listener was found and removed, False otherwise.
        """
        async with self._lock:
            if listener_id in self._listeners:
                del self._listeners[listener_id]
                logger.info("Unregistered idle listener %s", listener_id)
                return True
            return False

    async def start(self) -> None:
        """Start the idle check loop."""
        if self._running:
            logger.warning("ActivityTracker already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._check_loop())
        logger.info("ActivityTracker started (check_interval=%.1fs)", self._check_interval)

    async def stop(self) -> None:
        """Stop the idle check loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("ActivityTracker stopped")

    async def _check_loop(self) -> None:
        """Main loop - periodically check idle conditions."""
        while self._running:
            try:
                await asyncio.sleep(self._check_interval)

                idle = self.idle_seconds()

                async with self._lock:
                    for listener in self._listeners.values():
                        if not listener.fired and idle >= listener.threshold_seconds:
                            logger.info(
                                "Idle threshold met for %s (idle=%.1fs, threshold=%.1fs)",
                                listener.id,
                                idle,
                                listener.threshold_seconds,
                            )
                            try:
                                listener.callback()
                                listener.fired = True
                            except Exception as e:
                                logger.error(
                                    "Idle listener %s callback error: %s",
                                    listener.id,
                                    str(e),
                                    exc_info=True,
                                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("ActivityTracker check loop error: %s", str(e), exc_info=True)


# Singleton for kernel-wide activity tracking
_activity_tracker: ActivityTracker | None = None


def get_activity_tracker() -> ActivityTracker:
    """Get the global ActivityTracker instance."""
    global _activity_tracker
    if _activity_tracker is None:
        _activity_tracker = ActivityTracker()
    return _activity_tracker


def set_activity_tracker(tracker: ActivityTracker) -> None:
    """Set the global ActivityTracker instance (for testing)."""
    global _activity_tracker
    _activity_tracker = tracker
```

**Acceptance Criteria**:

- [ ] ActivityTracker records activity timestamps
- [ ] `idle_seconds()` returns correct duration
- [ ] Idle listeners fire when threshold exceeded
- [ ] Listeners reset on new activity
- [ ] Thread-safe for concurrent access

**Files to Create**:

- `k0/scheduler/activity.py`

---

#### Issue 7.1.2: Wire ActivityTracker to BusDispatcher

**Type**: Integration
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `integration`, `scheduler`, `phase2`

**File**: `k0/bus/dispatcher.py`

**Description**: Integrate ActivityTracker with BusDispatcher so that every event dispatch records activity. This ensures the idle timer resets on any kernel activity.

**Changes**:

```python
# In BusDispatcher.__init__():
from k0.scheduler.activity import get_activity_tracker

class BusDispatcher:
    def __init__(self, ...):
        ...
        self._activity_tracker = get_activity_tracker()

    async def dispatch(self, event: BusEvent) -> None:
        # Record activity on every dispatch
        self._activity_tracker.record_activity()

        # ... existing dispatch logic ...
```

**Acceptance Criteria**:

- [ ] Every `dispatch()` call records activity
- [ ] Idle timer resets on kernel events
- [ ] No performance regression (record_activity is O(1))

**Files to Modify**:

- `k0/bus/dispatcher.py`

---

#### Issue 7.1.3: Add ActivityTracker to Kernel Boot

**Type**: Integration
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `integration`, `scheduler`, `phase2`

**File**: `k0/kernel/app.py`

**Description**: Start ActivityTracker during kernel boot, stop during shutdown.

**Changes**:

```python
# In K0App or boot sequence:
from k0.scheduler.activity import get_activity_tracker

async def boot() -> None:
    ...
    # Start activity tracker for idle detection
    activity_tracker = get_activity_tracker()
    await activity_tracker.start()
    ...

async def shutdown() -> None:
    ...
    activity_tracker = get_activity_tracker()
    await activity_tracker.stop()
    ...
```

**Acceptance Criteria**:

- [ ] ActivityTracker starts on boot
- [ ] ActivityTracker stops on shutdown
- [ ] Graceful handling if already started/stopped

**Files to Modify**:

- `k0/kernel/app.py`

---

### Epic 7.2: IdleTriggerEngine Implementation

#### Issue 7.2.1: Implement IdleTriggerEngine Class

**Type**: Implementation
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `implementation`, `scheduler`, `phase2`

**File**: `k0/scheduler/triggers.py`

**Description**: Implement idle-based trigger engine that fires when system is idle and optional pending work conditions are met.

**Implementation**:

```python
class IdleTriggerEngine(TriggerEngine):
    """
    Trigger when system is idle for specified duration.

    Optionally waits for minimum pending work count before firing.
    Uses ActivityTracker for idle detection.

    Example spec:
        - id: consolidation_idle
          type: idle
          idle_seconds: 300  # 5 minutes
          min_pending: 100   # Optional: require 100+ pending items

    P03 Use Case:
        - Fire when idle 5 minutes AND 100+ pending embeddings
    """

    def __init__(
        self,
        spec: "TriggerSpec",
        pipeline_id: str,
        activity_tracker: "ActivityTracker",
        syscalls: "Syscalls | None" = None,
    ):
        super().__init__(spec, pipeline_id)
        self._tracker = activity_tracker
        self._syscalls = syscalls
        self._callback: TriggerCallback | None = None
        self._listener_id: str | None = None

    async def start(self, callback: TriggerCallback) -> None:
        """Start idle trigger engine."""
        if self._running:
            logger.warning("IdleTriggerEngine %s already running", self.spec.id)
            return

        if not self.spec.idle_seconds:
            raise ValueError(f"Idle trigger {self.spec.id} missing idle_seconds")

        self._callback = callback
        self._running = True
        self._listener_id = f"trigger_{self.spec.id}"

        # Register with activity tracker
        await self._tracker.register_idle_listener(
            listener_id=self._listener_id,
            callback=self._on_idle,
            threshold_seconds=self.spec.idle_seconds,
        )

        logger.info(
            "IdleTriggerEngine %s started (idle_seconds=%.1f, min_pending=%s)",
            self.spec.id,
            self.spec.idle_seconds,
            self.spec.min_pending or "none",
            extra={
                "trigger_id": self.spec.id,
                "pipeline_id": self.pipeline_id,
                "idle_seconds": self.spec.idle_seconds,
                "min_pending": self.spec.min_pending,
            },
        )

    async def stop(self) -> None:
        """Stop idle trigger engine."""
        self._running = False

        if self._listener_id:
            await self._tracker.unregister_idle_listener(self._listener_id)
            self._listener_id = None

        logger.info(
            "IdleTriggerEngine %s stopped (fired %d times)",
            self.spec.id,
            self._fire_count,
            extra={"trigger_id": self.spec.id, "fire_count": self._fire_count},
        )

    def _on_idle(self) -> None:
        """Callback when idle threshold met."""
        if not self._running or not self._callback:
            return

        # Check min_pending condition if specified
        if self.spec.min_pending:
            pending = self._get_pending_count()
            if pending < self.spec.min_pending:
                logger.debug(
                    "IdleTrigger %s skipped: pending=%d < min_pending=%d",
                    self.spec.id,
                    pending,
                    self.spec.min_pending,
                )
                return

        # Fire the trigger
        event = self._create_event({
            "idle_seconds": self._tracker.idle_seconds(),
            "trigger_type": "idle",
            "pending_count": self._get_pending_count() if self.spec.min_pending else None,
        })
        self._record_fire(event)
        self._callback(event)

        logger.info(
            "IdleTrigger %s fired (count=%d, idle=%.1fs)",
            self.spec.id,
            self._fire_count,
            self._tracker.idle_seconds(),
            extra={
                "trigger_id": self.spec.id,
                "pipeline_id": self.pipeline_id,
                "fire_count": self._fire_count,
                "idle_seconds": self._tracker.idle_seconds(),
            },
        )

    def _get_pending_count(self) -> int:
        """Get pending item count via syscalls."""
        if not self._syscalls:
            return 0

        try:
            # Use query_count syscall to get pending items
            result = self._syscalls.query_count(
                table=self.spec.count_table or "st_embedding_queue",
                filter_fn=self.spec.count_filter or "status='pending'",
            )
            return result
        except Exception as e:
            logger.error(
                "IdleTrigger %s failed to get pending count: %s",
                self.spec.id,
                str(e),
            )
            return 0
```

**Acceptance Criteria**:

- [ ] IdleTriggerEngine registers with ActivityTracker
- [ ] Fires when idle threshold exceeded
- [ ] Respects min_pending condition if specified
- [ ] Uses syscalls.query_count for pending count
- [ ] Proper cleanup on stop

**Files to Modify**:

- `k0/scheduler/triggers.py`

---

#### Issue 7.2.2: Update create_trigger_engine Factory for IDLE

**Type**: Implementation
**Priority**: Critical
**Assignee**: Backend Engineer
**Labels**: `implementation`, `scheduler`, `phase2`

**File**: `k0/scheduler/triggers.py`

**Description**: Update factory to handle IDLE trigger type with ActivityTracker injection.

**Changes**:

```python
def create_trigger_engine(
    spec: "TriggerSpec",
    pipeline_id: str,
    syscalls: "Syscalls | None" = None,
    activity_tracker: "ActivityTracker | None" = None,
) -> TriggerEngine:
    ...
    elif spec.type == TriggerType.IDLE:
        if activity_tracker is None:
            raise ValueError(f"Idle trigger {spec.id} requires activity_tracker")
        return IdleTriggerEngine(
            spec,
            pipeline_id,
            activity_tracker,
            syscalls=syscalls,  # For min_pending check
        )
    ...
```

**Note**: This is the same change as Issue 6.1.3 - implement both CRON and IDLE factory updates together.

**Files to Modify**:

- `k0/scheduler/triggers.py`

---

### Epic 7.3: IdleTriggerEngine Testing

#### Issue 7.3.1: Add ActivityTracker Tests

**Type**: Testing
**Priority**: Critical
**Assignee**: QA Engineer
**Labels**: `testing`, `scheduler`, `phase2`

**File**: `tests/k0/scheduler/test_activity.py`

**Description**: Comprehensive tests for ActivityTracker.

**Test Cases**:

```python
class TestActivityTracker:
    """Tests for ActivityTracker."""

    def test_activity_tracker_initial_idle_zero(self):
        """Initial idle_seconds is near zero."""

    def test_activity_tracker_records_activity(self):
        """record_activity resets idle timer."""

    async def test_activity_tracker_fires_listener(self):
        """Listener fires when idle threshold exceeded."""

    async def test_activity_tracker_listener_reset_on_activity(self):
        """Listener can fire again after activity resets."""

    async def test_activity_tracker_multiple_listeners(self):
        """Multiple listeners with different thresholds."""

    async def test_activity_tracker_unregister_listener(self):
        """Unregistered listener does not fire."""

    async def test_activity_tracker_start_stop(self):
        """Start and stop work correctly."""

    async def test_activity_tracker_listener_error_handling(self):
        """Listener errors don't crash the tracker."""

    def test_activity_tracker_thread_safety(self):
        """Concurrent record_activity calls are safe."""

    def test_get_activity_tracker_singleton(self):
        """get_activity_tracker returns singleton."""
```

**Acceptance Criteria**:

- [ ] All test cases pass
- [ ] >90% code coverage for ActivityTracker
- [ ] Thread-safety tests use concurrent execution

**Files to Create**:

- `tests/k0/scheduler/test_activity.py`

---

#### Issue 7.3.2: Add IdleTriggerEngine Tests

**Type**: Testing
**Priority**: Critical
**Assignee**: QA Engineer
**Labels**: `testing`, `scheduler`, `phase2`

**File**: `tests/k0/scheduler/test_triggers_idle.py`

**Description**: Comprehensive tests for IdleTriggerEngine.

**Test Cases**:

```python
class TestIdleTriggerEngine:
    """Tests for IdleTriggerEngine."""

    async def test_idle_trigger_fires_after_idle_period(self):
        """Trigger fires when idle threshold exceeded."""

    async def test_idle_trigger_respects_min_pending(self):
        """Trigger skipped if pending count below min_pending."""

    async def test_idle_trigger_fires_with_min_pending(self):
        """Trigger fires when pending count >= min_pending."""

    async def test_idle_trigger_resets_on_activity(self):
        """Trigger can fire again after activity."""

    async def test_idle_trigger_requires_activity_tracker(self):
        """Factory raises if activity_tracker missing."""

    async def test_idle_trigger_requires_idle_seconds(self):
        """Start raises if idle_seconds not specified."""

    async def test_idle_trigger_stop_unregisters_listener(self):
        """Stop unregisters from ActivityTracker."""

    async def test_idle_trigger_context_includes_idle_seconds(self):
        """TriggerEvent context includes idle_seconds."""

    async def test_idle_trigger_uses_syscalls_for_pending(self):
        """Pending count retrieved via syscalls.query_count."""

    async def test_idle_trigger_handles_syscall_error(self):
        """Graceful handling if syscalls.query_count fails."""
```

**Acceptance Criteria**:

- [ ] All test cases pass
- [ ] >90% code coverage for IdleTriggerEngine
- [ ] Integration with ActivityTracker validated

**Files to Create**:

- `tests/k0/scheduler/test_triggers_idle.py`

---

#### Issue 7.3.3: Add BusDispatcher Integration Test

**Type**: Testing
**Priority**: High
**Assignee**: QA Engineer
**Labels**: `testing`, `integration`, `phase2`

**File**: `tests/k0/bus/test_dispatcher_activity.py`

**Description**: Test that BusDispatcher correctly records activity.

**Test Cases**:

```python
class TestBusDispatcherActivity:
    """Tests for BusDispatcher activity recording."""

    async def test_dispatch_records_activity(self):
        """Event dispatch resets idle timer."""

    async def test_multiple_dispatches_record_activity(self):
        """Each dispatch records activity."""

    async def test_idle_trigger_fires_after_no_dispatch(self):
        """Idle trigger fires when no events dispatched."""

    async def test_idle_trigger_reset_by_dispatch(self):
        """Idle trigger resets when event dispatched."""
```

**Acceptance Criteria**:

- [ ] All test cases pass
- [ ] BusDispatcher + ActivityTracker integration validated

**Files to Create**:

- `tests/k0/bus/test_dispatcher_activity.py`

---

#### Issue 7.3.4: Document IDLE Trigger Usage

**Type**: Documentation
**Priority**: High
**Assignee**: Tech Lead
**Labels**: `documentation`, `scheduler`, `phase2`

**Files**:

- `k0/fabric/pipeline-fabric-integration-guide.md`
- `k0/scheduler/README.md`

**Description**: Update documentation to include IDLE trigger usage.

**Documentation Updates**:

1. **pipeline-fabric-integration-guide.md Section 3.3**: Update TriggerType enum status
   - Change IDLE from "Not yet implemented" to "Phase 2 (Implemented)"

2. **pipeline-fabric-integration-guide.md Section 7.4**: Add IdleTriggerEngine row

3. **Update scheduler README**: Document IDLE trigger with ActivityTracker

**Example YAML for P03**:

```yaml
# P03 idle-based consolidation trigger
triggers:
  # Fire when idle 5 minutes AND 100+ pending embeddings
  - id: consolidation_idle
    type: idle
    idle_seconds: 300  # 5 minutes
    min_pending: 100
    count_table: st_vec.embedding_status
    count_filter: "status = 'pending'"
```

**Acceptance Criteria**:

- [ ] IDLE trigger documented in integration guide
- [ ] Example YAML for P03 use case
- [ ] ActivityTracker integration documented

---

## Summary

### Phase 1 Total Issues: 33

| Milestone | Epics | Issues |
|-----------|-------|--------|
| M1: Foundation & Schemas | 3 | 7 |
| M2: CapabilityFabric Core | 2 | 8 |
| M3: PipelineScheduler + Concurrency | 3 | 10 |
| M4: P03 Integration | 3 | 5 |
| M5: P08 Migration | 2 | 3 |

### Issues Added from Gap Analysis

| Issue | Description | Gap |
|-------|-------------|-----|
| 3.1.0 | Add query_count() syscall | ThresholdTriggerEngine requires generic count |
| 4.0.1 | Create P03 pipeline contract | P03 contract doesn't exist in codebase |

### Phase 2 Issues (P03 Prerequisites)

| Milestone | Epics | Issues | Duration | Blocks |
|-----------|-------|--------|----------|--------|
| M6: CRON Trigger Engine | 1 | 5 | 3 days | P03 scheduled consolidation |
| M7: IDLE Trigger Engine | 3 | 9 | 4 days | P03 idle consolidation |

**Total Phase 2**: 2 milestones, 4 epics, 14 issues, ~7 days

**Critical Path**: M3 → M6 + M7 (parallel) → P03 production

### Phase 3 Issues (Future Enhancement)

Per ADR-K004 Future Considerations, these are deferred until prerequisites are met:

| Feature | Description | Prerequisite | Priority |
|---------|-------------|--------------|----------|
| Circuit Breakers | Fail-fast for unhealthy providers | Metrics infrastructure | High |
| Provider Health Checks | Periodic liveness probes | Background health task | Medium |
| Version Negotiation | Semantic version matching | Version in registry | Medium |
| Load Shedding | Provider selection by load | Real-time metrics | Low |
| Distributed Registry | Multi-instance discovery | K1 orchestration | Low |
| Capability ACLs | Fine-grained access control | Identity/auth | Low |
| Event Replay/Debugging | Replay fabric call sequences | Event sourcing | Low |
| Schema Evolution | Backward-compatible payloads | Schema registry | Low |

### Key Files Created

| File | Purpose |
|------|---------|
| `k0/fabric/__init__.py` | Fabric package exports |
| `k0/fabric/registry.py` | CapabilityRegistry |
| `k0/fabric/messages.py` | Request/Response types |
| `k0/fabric/fabric.py` | CapabilityFabric core |
| `k0/fabric/audit.py` | Fabric audit logging |
| `k0/fabric/loader.py` | Capability auto-registration |
| `k0/scheduler/__init__.py` | Scheduler package exports |
| `k0/scheduler/triggers.py` | Trigger engines |
| `k0/scheduler/scheduler.py` | PipelineScheduler |
| `k0/scheduler/concurrency.py` | SingleFlightGate, overlap policies |
| `k0/scheduler/audit.py` | Scheduler audit logging |
| `contracts/schemas/capability.schema.json` | Capability JSON Schema |
| `k0/contracts/capabilities/core.v1.yaml` | Core capability definitions |

### Key Files Modified

| File | Changes |
|------|---------|
| `k0/runtime/schemas.py` | TriggerSpec, CapabilityProvider, ModuleContract extensions |
| `k0/runtime/module_registry.py` | Capability index and resolution |
| `k0/pipelines/protocol.py` | Add fabric to PipelineContext |
| `k0/pipelines/loader.py` | Return PipelineLoadResult |
| `k0/kernel/app.py` | Integrate fabric and scheduler, remove hardcoded P08 |
| `k0/contracts/modules/salience.score.v1.yaml` | Fabric fields |
| `k0/contracts/pipelines/p03_salience.v1.yaml` | Fabric dependencies |
| `k0/contracts/pipelines/p08_embedding_management.v2.yaml` | Declarative triggers |

### Test Files

| File | Coverage |
|------|----------|
| `tests/k0/runtime/test_schemas_trigger.py` | TriggerSpec validation |
| `tests/k0/runtime/test_schemas_capability.py` | CapabilityProvider validation |
| `tests/k0/fabric/test_registry.py` | CapabilityRegistry |
| `tests/k0/fabric/test_registry_threadsafe.py` | Registry thread safety |
| `tests/k0/fabric/test_messages.py` | Request/Response |
| `tests/k0/fabric/test_fabric.py` | CapabilityFabric |
| `tests/k0/fabric/test_fabric_policy.py` | Context policy enforcement |
| `tests/k0/fabric/test_audit.py` | Fabric audit logging |
| `tests/k0/fabric/test_loader.py` | Capability loading |
| `tests/k0/scheduler/test_triggers.py` | Trigger engines (Phase 1) |
| `tests/k0/scheduler/test_triggers_cron.py` | CronTriggerEngine (Phase 2) |
| `tests/k0/scheduler/test_triggers_idle.py` | IdleTriggerEngine (Phase 2) |
| `tests/k0/scheduler/test_activity.py` | ActivityTracker (Phase 2) |
| `tests/k0/scheduler/test_scheduler.py` | PipelineScheduler |
| `tests/k0/scheduler/test_concurrency.py` | SingleFlightGate |
| `tests/k0/scheduler/test_hot_reload.py` | Hot reload |
| `tests/k0/scheduler/test_audit.py` | Scheduler audit logging |
| `tests/k0/kernel/test_app_boot.py` | Boot integration |
| `tests/k0/kernel/test_app_scheduler.py` | Scheduler integration |
| `tests/k0/bus/test_dispatcher_activity.py` | BusDispatcher activity integration (Phase 2) |
| `tests/integration/test_p03_fabric.py` | P03 fabric integration |
| `tests/integration/test_p08_scheduler_migration.py` | P08 migration |
| `tests/contracts/test_capability_schema.py` | Schema validation |
| `tests/contracts/test_capability_contracts.py` | YAML contracts |
| `tests/contracts/test_p08_triggers.py` | P08 trigger config |

### Key Files Created (Phase 2)

| File | Purpose |
|------|---------|
| `k0/scheduler/activity.py` | ActivityTracker for idle detection |

### Key Files Modified (Phase 2)

| File | Changes |
|------|---------|
| `k0/scheduler/triggers.py` | Add CronTriggerEngine, IdleTriggerEngine |
| `k0/bus/dispatcher.py` | Wire ActivityTracker for activity recording |
| `k0/kernel/app.py` | Start/stop ActivityTracker on boot/shutdown |
| `pyproject.toml` | Add croniter optional dependency |

---

## Revision History

| Date | Version | Author | Changes |
|------|---------|--------|---------|
| 2025-12-14 | 1.0 | AI | Initial plan creation |
| 2025-12-14 | 1.1 | AI | Added Phase 1/2 split for triggers (CRON/IDLE deferred) |
| 2025-12-14 | 1.2 | AI | Added concurrency controls (Epic 3.3), audit logging (Issue 2.1.6), Phase 3 roadmap |
| 2025-01-26 | 1.3 | AI | Expanded Phase 2 (M6/M7) from sketches to full implementation issues. Phase 2 now P03 prerequisite with detailed issues: M6 (5 issues - CRON trigger), M7 (9 issues - IDLE trigger + ActivityTracker). Added BusDispatcher integration, kernel boot integration, and comprehensive testing requirements. |
