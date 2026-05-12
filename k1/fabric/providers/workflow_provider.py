"""
k1.fabric.providers.workflow_provider -- WorkflowProvider (3.3.5).

Rehydrates a frozen WorkflowSpec and executes it as a DAG via the
Orchestrator.

Execution flow (from fabric_discussion.md Section 11 -- Provider Type 5):
  1. Receive CapabilityRequest (e.g. "workflow.run.weekly_health_check")
  2. Load WorkflowSpec from IWorkflowRegistry
  3. Validate all referenced capabilities still exist
     (version-aware lookup via Epic 2.4)
  4. Detect schema drift:
     - small drift: auto-fill defaults, continue
     - large drift: store gap in K0 via BridgeProvider, abort
  5. Create RunManifest (pinned version + hash for audit)
  6. Send rehydrated plan to IOrchestrator for DAG execution
  7. Guard: max workflow depth = 3 (sub-workflow nesting limit)
  8. Return aggregated CapabilityResult

Design:
  - All external dependencies injected via port protocols:
    - IWorkflowRegistry: load/store WorkflowSpec
    - IOrchestrator: DAG execution engine
    - ICapabilityLookup: version-aware capability validation
  - WorkflowProvider does NOT import Orchestrator or Registry at import time
  - Thread-safe: no mutable state after construction

References:
  - fabric_discussion.md Section 11 (Provider Type 5: Workflow Provider)
  - fabric_discussion.md Section 15 Q6 (cross-workflow triggers)
  - k1_cognitive_architecture_skeleton.mmd (Workflow subgraph)
  - whiteboard Section 7 (Fabric: Workflow execution)
  - Epic 3.3.5 in fabric-implementation-plan.md

Wiring (from plan):
  - Uses Registry (2.2.1) for version-aware capability lookup (2.4.3)
  - Sends to Orchestrator for DAG execution
  - max_depth=3 guard
  - Wrapped by CircuitBreaker (60s timeout, 1 failure/min)

Exports:
  WorkflowProvider          -- Workflow DAG execution provider
  IWorkflowRegistry         -- Workflow storage port protocol
  IOrchestrator             -- DAG execution port protocol
  ICapabilityLookup         -- Version-aware capability lookup port
  WorkflowSpec              -- Frozen workflow specification
  WorkflowStep              -- Single step in a workflow DAG
  RunManifest               -- Pinned execution manifest
  SchemaDrift               -- Schema drift details
  DriftSeverity             -- Drift severity enum
  WorkflowProviderError     -- Base workflow exception
  WorkflowNotFoundError     -- Workflow not in registry
  WorkflowValidationError   -- Capability validation failed
  WorkflowDepthExceededError -- max_depth guard triggered
  WorkflowSchemaDriftError  -- Large schema drift detected
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol

from k1.fabric.providers.base_provider import BaseProvider, ProviderExecutionError
from k1.fabric.types import (
    CapabilityRequest,
    CapabilityResult,
    ExecutionContext,
    ProviderConfig,
    ProviderHealth,
    ProviderStatus,
)

logger = logging.getLogger(__name__)

# Max nesting depth for sub-workflow execution
MAX_WORKFLOW_DEPTH: int = 3


# ---------------------------------------------------------------------------
# Workflow data types
# ---------------------------------------------------------------------------


class DriftSeverity(str, Enum):
    """Severity of schema drift detected during workflow rehydration."""

    NONE = "NONE"
    MINOR = "MINOR"  # Auto-fill defaults, continue
    MAJOR = "MAJOR"  # Store gap in K0, abort


@dataclass(frozen=True)
class WorkflowStep:
    """
    Single step in a workflow DAG.

    Attributes:
        step_id: Unique step identifier within the workflow.
        capability: Capability name to invoke (e.g. "tool.execute.weather").
        params: Parameters for this step.
        deps: Step IDs this step depends on (DAG edges).
        version: Pinned capability version (semver or None for latest).
        timeout_ms: Per-step timeout (0 = use provider default).
    """

    step_id: str = ""
    capability: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    deps: List[str] = field(default_factory=list)
    version: Optional[str] = None
    timeout_ms: int = 0


@dataclass(frozen=True)
class WorkflowSpec:
    """
    Frozen workflow specification.

    Stored in IWorkflowRegistry, loaded by WorkflowProvider for execution.
    Created by Planner Stage 4 COMMIT and frozen as immutable spec.

    Attributes:
        workflow_id: Unique workflow identifier.
        name: Canonical workflow name (e.g. "workflow.run.weekly_health_check").
        version: Workflow version (semver string).
        steps: Ordered list of workflow steps (DAG nodes).
        description: Human-readable description.
        created_at: ISO timestamp of creation.
        metadata: Additional workflow metadata.
    """

    workflow_id: str = ""
    name: str = ""
    version: str = "1.0.0"
    steps: List[WorkflowStep] = field(default_factory=list)
    description: str = ""
    created_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SchemaDrift:
    """
    Schema drift detected during workflow rehydration.

    Attributes:
        step_id: The step where drift was detected.
        capability: The capability name.
        expected_version: Version pinned in the workflow.
        actual_version: Version currently registered.
        severity: How severe the drift is.
        details: Description of what changed.
        auto_filled: Fields that were auto-filled with defaults.
    """

    step_id: str = ""
    capability: str = ""
    expected_version: str = ""
    actual_version: str = ""
    severity: str = DriftSeverity.NONE.value
    details: str = ""
    auto_filled: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class RunManifest:
    """
    Pinned execution manifest for a workflow run.

    Created from a validated WorkflowSpec with all versions resolved
    and schema drift handled. Used by Orchestrator for DAG execution.
    Provides an audit trail.

    Attributes:
        manifest_id: Unique manifest identifier.
        workflow_id: Source workflow ID.
        workflow_version: Source workflow version.
        steps: Validated steps with resolved versions.
        content_hash: SHA-256 hash of the manifest for integrity.
        depth: Current nesting depth (0 = top-level).
        trace_id: Cognitive trace ID.
        drifts: Any schema drifts detected and handled.
    """

    manifest_id: str = ""
    workflow_id: str = ""
    workflow_version: str = ""
    steps: List[WorkflowStep] = field(default_factory=list)
    content_hash: str = ""
    depth: int = 0
    trace_id: str = ""
    drifts: List[SchemaDrift] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Port protocols
# ---------------------------------------------------------------------------


class IWorkflowRegistry(Protocol):
    """
    Port protocol for workflow storage.

    Concrete implementation loads WorkflowSpec from disk, database,
    or in-memory cache. Injected by FabricFactory.
    """

    async def load(self, workflow_name: str) -> Optional[WorkflowSpec]:
        """
        Load a WorkflowSpec by canonical name.

        Args:
            workflow_name: e.g. "workflow.run.weekly_health_check"

        Returns:
            WorkflowSpec or None if not found.
        """
        ...

    async def store(self, spec: WorkflowSpec) -> None:
        """Store or update a WorkflowSpec."""
        ...


class ICapabilityLookup(Protocol):
    """
    Port protocol for version-aware capability validation.

    Maps to CapabilityRegistry.lookup(name, version) from Epic 2.4.3.
    Injected by FabricFactory.
    """

    def exists(self, capability_name: str, version: Optional[str] = None) -> bool:
        """
        Check if a capability exists (optionally at a specific version).

        Args:
            capability_name: Canonical capability name.
            version: Exact semver version, or None for latest.

        Returns:
            True if the capability exists.
        """
        ...

    def get_version(self, capability_name: str) -> Optional[str]:
        """
        Get the current version of a registered capability.

        Returns:
            Version string or None if not registered.
        """
        ...


class IOrchestrator(Protocol):
    """
    Port protocol for DAG execution via the Orchestrator.

    Concrete implementation is the K1 Orchestrator. Injected by FabricFactory.
    The Orchestrator walks the DAG, executing each step via Fabric
    (recursive: Fabric -> Orchestrator -> Fabric).
    """

    async def execute_workflow(
        self,
        manifest: RunManifest,
        context: ExecutionContext,
    ) -> CapabilityResult:
        """
        Execute a workflow from a RunManifest.

        Args:
            manifest: Validated RunManifest with all steps.
            context: Execution context.

        Returns:
            Aggregated CapabilityResult from DAG execution.
        """
        ...


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class WorkflowProviderError(ProviderExecutionError):
    """Base exception for workflow provider operations."""

    def __init__(
        self,
        provider_id: str,
        message: str,
        *,
        retriable: bool = False,
    ) -> None:
        super().__init__(
            provider_id,
            message,
            retriable=retriable,
            error_code="workflow_error",
        )


class WorkflowNotFoundError(WorkflowProviderError):
    """Workflow not found in the registry."""

    def __init__(self, provider_id: str, workflow_name: str) -> None:
        self.workflow_name = workflow_name
        super().__init__(
            provider_id,
            f"Workflow '{workflow_name}' not found in registry",
            retriable=False,
        )


class WorkflowValidationError(WorkflowProviderError):
    """Capability validation failed during workflow rehydration."""

    def __init__(
        self,
        provider_id: str,
        missing_capabilities: List[str],
    ) -> None:
        self.missing_capabilities = list(missing_capabilities)
        msg = (
            f"Workflow references {len(missing_capabilities)} missing "
            f"capabilities: {', '.join(missing_capabilities[:5])}"
        )
        super().__init__(provider_id, msg, retriable=False)


class WorkflowDepthExceededError(WorkflowProviderError):
    """Sub-workflow nesting depth exceeded max_depth guard."""

    def __init__(self, provider_id: str, depth: int, max_depth: int) -> None:
        self.depth = depth
        self.max_depth = max_depth
        super().__init__(
            provider_id,
            f"Workflow depth {depth} exceeds max {max_depth}",
            retriable=False,
        )


class WorkflowSchemaDriftError(WorkflowProviderError):
    """Large schema drift detected; workflow cannot be safely executed."""

    def __init__(
        self,
        provider_id: str,
        drifts: List[SchemaDrift],
    ) -> None:
        self.drifts = list(drifts)
        capabilities = [d.capability for d in drifts]
        msg = f"Major schema drift in {len(drifts)} capabilities: " f"{', '.join(capabilities[:5])}"
        super().__init__(provider_id, msg, retriable=False)


# ---------------------------------------------------------------------------
# WorkflowProvider
# ---------------------------------------------------------------------------


class WorkflowProvider(BaseProvider):
    """
    Workflow DAG execution provider (3.3.5).

    Rehydrates a frozen WorkflowSpec, validates capability availability,
    detects schema drift, builds a RunManifest, and delegates DAG
    execution to the Orchestrator.

    Constructor Args:
        config: ProviderConfig with endpoint and limits.
        workflow_registry: IWorkflowRegistry for loading WorkflowSpecs.
        capability_lookup: ICapabilityLookup for version-aware validation.
        orchestrator: IOrchestrator for DAG execution.
        capability_names: List of workflow capability names this provider handles.
        max_depth: Maximum sub-workflow nesting depth (default 3).
        current_depth: Current nesting depth (for recursive invocations).

    Usage::

        provider = WorkflowProvider(
            config=ProviderConfig(
                provider_id="workflow-runner",
                provider_type="WORKFLOW",
            ),
            workflow_registry=my_registry,
            capability_lookup=my_lookup,
            orchestrator=my_orchestrator,
            capability_names=["workflow.run.weekly_health_check"],
        )
        result = await provider.execute(request, context, trace_id)

    Wrapped by CircuitBreaker (3.4.1): 60s timeout, 1 failure/min.
    """

    __slots__ = (
        "_workflow_registry",
        "_capability_lookup",
        "_orchestrator",
        "_capability_names",
        "_max_depth",
    )

    def __init__(
        self,
        config: ProviderConfig,
        *,
        workflow_registry: IWorkflowRegistry,
        capability_lookup: ICapabilityLookup,
        orchestrator: IOrchestrator,
        capability_names: Optional[List[str]] = None,
        max_depth: int = MAX_WORKFLOW_DEPTH,
        **_kwargs: Any,
    ) -> None:
        super().__init__(config)
        self._workflow_registry = workflow_registry
        self._capability_lookup = capability_lookup
        self._orchestrator = orchestrator
        self._capability_names: List[str] = list(capability_names or [])
        self._max_depth = max_depth

    # ======================================================================
    # CapabilityProvider interface
    # ======================================================================

    def capabilities(self) -> List[str]:
        """Return the list of workflow capability names this provider handles."""
        return list(self._capability_names)

    async def health_check(self) -> ProviderHealth:
        """
        Workflow Provider health: check registry is reachable.

        Returns HEALTHY if workflow_registry responds, UNKNOWN otherwise.
        """
        try:
            # Light probe: try loading a non-existent workflow.
            # If the registry is up, it returns None (not found).
            await self._workflow_registry.load("__health_probe__")
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderStatus.HEALTHY.value,
            )
        except Exception as exc:
            logger.warning("[%s] health_check failed: %s", self.provider_id, exc)
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderStatus.UNHEALTHY.value,
                error=str(exc),
            )

    # ======================================================================
    # Internal execution (BaseProvider._execute)
    # ======================================================================

    async def _execute(
        self,
        request: CapabilityRequest,
        context: ExecutionContext,
        trace_id: str,
    ) -> CapabilityResult:
        """
        Workflow-specific execution logic.

        Flow:
          1. Guard max depth
          2. Load WorkflowSpec
          3. Validate capabilities exist
          4. Detect schema drift
          5. Build RunManifest
          6. Execute via Orchestrator
          7. Return result
        """
        # --- Step 1: Guard max depth ---
        # Issue 8 fix: read depth from the call-time ExecutionContext so that
        # (a) concurrent calls on the same instance are independent, and
        # (b) sub-workflows spawned by the orchestrator correctly inherit depth
        # by reading "__workflow_depth__" from their own ExecutionContext.
        # The factory no longer stores current_depth as instance state.
        current_depth: int = int((context.params or {}).get("__workflow_depth__", 0))
        if current_depth >= self._max_depth:
            raise WorkflowDepthExceededError(self.provider_id, current_depth, self._max_depth)

        # --- Step 2: Load WorkflowSpec ---
        workflow_name = request.capability_name
        spec = await self._workflow_registry.load(workflow_name)
        if spec is None:
            raise WorkflowNotFoundError(self.provider_id, workflow_name)

        logger.debug(
            "[%s] loaded workflow: %s (v%s, %d steps, depth=%d)",
            self.provider_id,
            spec.name,
            spec.version,
            len(spec.steps),
            current_depth,
        )

        # --- Step 3: Validate capabilities exist ---
        missing = self._validate_capabilities(spec)
        if missing:
            raise WorkflowValidationError(self.provider_id, missing)

        # --- Step 4: Detect schema drift ---
        drifts = self._detect_schema_drift(spec)
        major_drifts = [d for d in drifts if d.severity == DriftSeverity.MAJOR.value]
        if major_drifts:
            raise WorkflowSchemaDriftError(self.provider_id, major_drifts)

        # Log minor drifts but continue
        for drift in drifts:
            if drift.severity == DriftSeverity.MINOR.value:
                logger.info(
                    "[%s] minor schema drift in step %s capability %s: %s",
                    self.provider_id,
                    drift.step_id,
                    drift.capability,
                    drift.details,
                )

        # --- Step 5: Build RunManifest ---
        manifest = self._build_manifest(spec, drifts, trace_id, current_depth)

        logger.debug(
            "[%s] manifest built: %s (hash=%s)",
            self.provider_id,
            manifest.manifest_id,
            manifest.content_hash[:16],
        )

        # --- Step 6: Execute via Orchestrator ---
        result = await self._orchestrator.execute_workflow(manifest, context)

        return result

    # ======================================================================
    # Private helpers
    # ======================================================================

    def _validate_capabilities(self, spec: WorkflowSpec) -> List[str]:
        """
        Validate all referenced capabilities exist in the registry.

        Uses version-aware lookup from Epic 2.4.

        Returns:
            List of missing capability names (empty if all valid).
        """
        missing: List[str] = []
        for step in spec.steps:
            if not self._capability_lookup.exists(step.capability, step.version):
                missing.append(step.capability)
        return missing

    def _detect_schema_drift(self, spec: WorkflowSpec) -> List[SchemaDrift]:
        """
        Detect schema drift between pinned and current capability versions.

        - If step has no pinned version: no drift possible.
        - If current version matches pinned: no drift.
        - If current major differs: MAJOR drift.
        - If current minor/patch differs: MINOR drift (auto-fill defaults).
        """
        drifts: List[SchemaDrift] = []
        for step in spec.steps:
            if step.version is None:
                continue  # No pinned version, no drift check

            current_version = self._capability_lookup.get_version(step.capability)
            if current_version is None:
                continue  # Missing capability handled by _validate_capabilities

            if current_version == step.version:
                continue  # Exact match, no drift

            # Parse major versions for severity classification
            pinned_major = step.version.split(".")[0] if "." in step.version else step.version
            current_major = (
                current_version.split(".")[0] if "." in current_version else current_version
            )

            if pinned_major != current_major:
                severity = DriftSeverity.MAJOR.value
                details = f"Breaking version change: {step.version} -> {current_version}"
            else:
                severity = DriftSeverity.MINOR.value
                details = f"Compatible version change: {step.version} -> {current_version}"

            drifts.append(
                SchemaDrift(
                    step_id=step.step_id,
                    capability=step.capability,
                    expected_version=step.version,
                    actual_version=current_version,
                    severity=severity,
                    details=details,
                )
            )
        return drifts

    def _build_manifest(
        self,
        spec: WorkflowSpec,
        drifts: List[SchemaDrift],
        trace_id: str,
        current_depth: int = 0,
    ) -> RunManifest:
        """
        Build an auditable RunManifest from a validated WorkflowSpec.

        The manifest pins exact versions and includes a content hash.
        """
        # Build steps with resolved versions
        resolved_steps: List[WorkflowStep] = []
        for step in spec.steps:
            current_version = self._capability_lookup.get_version(step.capability)
            resolved_steps.append(
                WorkflowStep(
                    step_id=step.step_id,
                    capability=step.capability,
                    params=dict(step.params),
                    deps=list(step.deps),
                    version=current_version or step.version,
                    timeout_ms=step.timeout_ms,
                )
            )

        # Content hash for integrity/audit
        content = json.dumps(
            {
                "workflow_id": spec.workflow_id,
                "version": spec.version,
                "steps": [
                    {"id": s.step_id, "cap": s.capability, "ver": s.version} for s in resolved_steps
                ],
            },
            sort_keys=True,
        )
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        manifest_id = f"run-{spec.workflow_id}-{trace_id[:8]}"

        return RunManifest(
            manifest_id=manifest_id,
            workflow_id=spec.workflow_id,
            workflow_version=spec.version,
            steps=resolved_steps,
            content_hash=content_hash,
            depth=current_depth,
            trace_id=trace_id,
            drifts=drifts,
        )

    def __repr__(self) -> str:
        return (
            f"WorkflowProvider("
            f"provider_id={self.provider_id!r}, "
            f"capabilities={len(self._capability_names)}, "
            f"max_depth={self._max_depth})"
        )
