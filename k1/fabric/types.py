"""
Fabric Core Types -- Domain-agnostic envelope types and data structures.

All types used across Fabric subsystems are defined here.
These are pure dataclasses with no port dependencies or I/O.

Design decisions:
  - FAB-001: Frozen Pydantic dataclasses (immutable after construction)
  - FAB-007: Pydantic internal, FlatBuffers at serialization boundaries
  - FAB-009: WFQPriority embedded in CapabilityRequest

References:
  - fabric_discussion.md Section 6  (Contract schemas)
  - fabric_discussion.md Section 14 (Message envelopes)
  - k1/docs/adrs/FAB-001-core-envelope-schemas.md
  - k1/docs/adrs/FAB-007-flatbuffers-serialization-in-fabric.md
  - k1/docs/adrs/FAB-009-performance-scheduling-in-fabric.md
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Enums (1.3.10 completes the full set; earlier issues defined the subset)
# ---------------------------------------------------------------------------


class WFQPriority(str, Enum):
    """Weighted Fair Queue priority classes (FAB-009)."""

    URGENT = "URGENT"  # <=50ms budget
    REALTIME = "REALTIME"  # <=150ms budget
    INTERACTIVE = "INTERACTIVE"  # <=300ms budget
    BACKGROUND = "BACKGROUND"  # <=5s budget


class RequestStatus(str, Enum):
    """Lifecycle status of a capability request."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


class Tier(str, Enum):
    """Complexity tier for request routing."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SafetyBand(str, Enum):
    """Safety band classification (ordered: GREEN < AMBER < RED < CRISIS)."""

    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"
    CRISIS = "CRISIS"

    def __ge__(self, other: "SafetyBand") -> bool:
        order = {SafetyBand.GREEN: 0, SafetyBand.AMBER: 1, SafetyBand.RED: 2, SafetyBand.CRISIS: 3}
        return order[self] >= order[other]

    def __gt__(self, other: "SafetyBand") -> bool:
        order = {SafetyBand.GREEN: 0, SafetyBand.AMBER: 1, SafetyBand.RED: 2, SafetyBand.CRISIS: 3}
        return order[self] > order[other]

    def __le__(self, other: "SafetyBand") -> bool:
        order = {SafetyBand.GREEN: 0, SafetyBand.AMBER: 1, SafetyBand.RED: 2, SafetyBand.CRISIS: 3}
        return order[self] <= order[other]

    def __lt__(self, other: "SafetyBand") -> bool:
        order = {SafetyBand.GREEN: 0, SafetyBand.AMBER: 1, SafetyBand.RED: 2, SafetyBand.CRISIS: 3}
        return order[self] < order[other]


class Availability(str, Enum):
    """Provider availability status."""

    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"


class ProviderType(str, Enum):
    """Capability provider type."""

    MCP = "MCP"
    WASM = "WASM"
    BRIDGE = "BRIDGE"
    AGENT = "AGENT"
    WORKFLOW = "WORKFLOW"
    CONCIERGE = "CONCIERGE"


# ---------------------------------------------------------------------------
# 1.3.1 -- CapabilityRequest
# ---------------------------------------------------------------------------


class CapabilityRequestValidationError(Exception):
    """Raised when a CapabilityRequest fails validation."""

    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__(f"CapabilityRequest validation failed: {'; '.join(errors)}")


@dataclass(frozen=True)
class CapabilityRequest:
    """
    Domain-agnostic request to invoke a capability.

    This is the PRIMARY input envelope for the Fabric pipeline.
    Constructed by Orchestrator (per DAG step), Concierge (LOW tier direct),
    or Sub-Agents (via scoped invoke_capability).

    Invariants:
      - Immutable after construction (frozen=True, FAB-001)
      - WFQ priority embedded for scheduling (FAB-009)
      - trace_id required for cognitive tracing (FAB-09 invariant)

    References:
      - fabric_discussion.md Section 14 (CapabilityRequest schema)
      - FAB-001 (core envelope decision)
      - orchestrator.mmd line 40 (CapabilityRequest: Orchestrator -> Fabric)
      - concierge.mmd line 158 (invoke_capability direct execution)
    """

    # ---- Identity ----
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    capability_name: str = ""

    # ---- Parameters ----
    params: Dict[str, Any] = field(default_factory=dict)
    prompt_template: Optional[str] = None
    context_override: Optional[Dict[str, Any]] = None

    # ---- Routing & Scheduling ----
    tier: str = Tier.MEDIUM.value
    wfq_priority: str = WFQPriority.INTERACTIVE.value
    safety_band: str = SafetyBand.GREEN.value
    timeout_ms: int = 30000
    retry_count: int = 0

    # ---- Caller Identity ----
    caller: str = ""
    caller_id: str = ""

    # ---- Tracing & Correlation ----
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    plan_id: Optional[str] = None
    step_id: Optional[str] = None

    def validate(self) -> List[str]:
        """
        Validate request fields. Returns list of error strings (empty = valid).

        Checks:
          1. capability_name is non-empty
          2. capability_name follows type convention (tool.*/agent.*/workflow.*/concierge.*)
          3. tier is a valid Tier value
          4. wfq_priority is a valid WFQPriority value
          5. timeout_ms is positive
          6. retry_count is non-negative
          7. trace_id is non-empty
          8. caller is non-empty
        """
        errors: List[str] = []

        if not self.capability_name:
            errors.append("capability_name is required")
        elif not any(
            self.capability_name.startswith(prefix)
            for prefix in ("tool.", "agent.", "workflow.", "concierge.")
        ):
            errors.append(
                f"capability_name '{self.capability_name}' must start with "
                "tool.*, agent.*, workflow.*, or concierge.*"
            )

        valid_tiers = {t.value for t in Tier}
        if self.tier not in valid_tiers:
            errors.append(f"tier '{self.tier}' is not valid; expected one of {valid_tiers}")

        valid_priorities = {p.value for p in WFQPriority}
        if self.wfq_priority not in valid_priorities:
            errors.append(
                f"wfq_priority '{self.wfq_priority}' is not valid; "
                f"expected one of {valid_priorities}"
            )

        if self.timeout_ms <= 0:
            errors.append(f"timeout_ms must be positive, got {self.timeout_ms}")

        if self.retry_count < 0:
            errors.append(f"retry_count must be non-negative, got {self.retry_count}")

        if not self.trace_id:
            errors.append("trace_id is required")

        if not self.caller:
            errors.append("caller is required")

        return errors

    def validate_or_raise(self) -> None:
        """Validate and raise CapabilityRequestValidationError if invalid."""
        errors = self.validate()
        if errors:
            raise CapabilityRequestValidationError(errors)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: Dict[str, Any] = {
            "request_id": self.request_id,
            "capability_name": self.capability_name,
            "params": dict(self.params),
            "prompt_template": self.prompt_template,
            "context_override": dict(self.context_override) if self.context_override else None,
            "tier": self.tier,
            "wfq_priority": self.wfq_priority,
            "safety_band": self.safety_band,
            "timeout_ms": self.timeout_ms,
            "retry_count": self.retry_count,
            "caller": self.caller,
            "caller_id": self.caller_id,
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "plan_id": self.plan_id,
            "step_id": self.step_id,
        }
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CapabilityRequest":
        """Create CapabilityRequest from dictionary."""
        return cls(
            request_id=data.get("request_id", str(uuid.uuid4())),
            capability_name=data.get("capability_name", ""),
            params=data.get("params", {}),
            prompt_template=data.get("prompt_template"),
            context_override=data.get("context_override"),
            tier=data.get("tier", Tier.MEDIUM.value),
            wfq_priority=data.get("wfq_priority", WFQPriority.INTERACTIVE.value),
            safety_band=data.get("safety_band", SafetyBand.GREEN.value),
            timeout_ms=data.get("timeout_ms", 30000),
            retry_count=data.get("retry_count", 0),
            caller=data.get("caller", ""),
            caller_id=data.get("caller_id", ""),
            trace_id=data.get("trace_id", str(uuid.uuid4())),
            session_id=data.get("session_id", ""),
            plan_id=data.get("plan_id"),
            step_id=data.get("step_id"),
        )


# ---------------------------------------------------------------------------
# 1.3.2 -- CapabilityResult + ErrorInfo
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ErrorInfo:
    """
    Structured error detail for failed capability results.

    Attributes:
        code: Machine-readable error code (e.g. capability_not_found, timeout, provider_error)
        message: Human-readable error description
        retriable: Whether the caller may retry this request
    """

    code: str = ""
    message: str = ""
    retriable: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "code": self.code,
            "message": self.message,
            "retriable": self.retriable,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ErrorInfo":
        """Create ErrorInfo from dictionary."""
        return cls(
            code=data.get("code", ""),
            message=data.get("message", ""),
            retriable=data.get("retriable", False),
        )


@dataclass(frozen=True)
class CapabilityResult:
    """
    Domain-agnostic result from capability execution.

    Returned by Fabric to the caller after the full pipeline completes.
    Validated by OutputValidationPipeline (3.5.5), emitted in events (5.4.1).

    Invariants:
      - Immutable after construction (frozen=True, FAB-001)
      - Factory methods enforce valid state (no COMPLETED with error, no FAILED with data)
      - trace_id matches the originating CapabilityRequest.trace_id

    References:
      - fabric_discussion.md Section 14 (CapabilityResult schema)
      - FAB-001 (core envelope decision, factory methods)
      - orchestrator.mmd line 41 (CapabilityResult: Fabric -> Orchestrator)
    """

    # ---- Correlation ----
    request_id: str = ""
    trace_id: str = ""

    # ---- Outcome ----
    success: bool = False
    data: Optional[Dict[str, Any]] = None
    error: Optional[ErrorInfo] = None

    # ---- Provider ----
    provider_id: str = ""

    # ---- Timing (milliseconds) ----
    duration_ms: int = 0
    retrieval_time_ms: int = 0
    resolution_time_ms: int = 0
    execution_time_ms: int = 0

    # ---- Factory Methods (FAB-001: enforce valid state) ----

    @classmethod
    def success_result(
        cls,
        request_id: str,
        data: Dict[str, Any],
        provider_id: str,
        trace_id: str = "",
        duration_ms: int = 0,
        retrieval_time_ms: int = 0,
        resolution_time_ms: int = 0,
        execution_time_ms: int = 0,
    ) -> "CapabilityResult":
        """
        Create a successful result.

        Guarantees: success=True, data is set, error is None.
        """
        return cls(
            request_id=request_id,
            trace_id=trace_id,
            success=True,
            data=data,
            error=None,
            provider_id=provider_id,
            duration_ms=duration_ms,
            retrieval_time_ms=retrieval_time_ms,
            resolution_time_ms=resolution_time_ms,
            execution_time_ms=execution_time_ms,
        )

    @classmethod
    def failure_result(
        cls,
        request_id: str,
        error_code: str,
        error_message: str,
        retriable: bool = False,
        provider_id: str = "",
        trace_id: str = "",
        duration_ms: int = 0,
        retrieval_time_ms: int = 0,
        resolution_time_ms: int = 0,
        execution_time_ms: int = 0,
    ) -> "CapabilityResult":
        """
        Create a failed result.

        Guarantees: success=False, error is set, data is None.
        """
        return cls(
            request_id=request_id,
            trace_id=trace_id,
            success=False,
            data=None,
            error=ErrorInfo(code=error_code, message=error_message, retriable=retriable),
            provider_id=provider_id,
            duration_ms=duration_ms,
            retrieval_time_ms=retrieval_time_ms,
            resolution_time_ms=resolution_time_ms,
            execution_time_ms=execution_time_ms,
        )

    @classmethod
    def timeout_result(
        cls,
        request_id: str,
        timeout_ms: int,
        provider_id: str = "",
        trace_id: str = "",
        duration_ms: int = 0,
    ) -> "CapabilityResult":
        """
        Create a timeout result.

        Guarantees: success=False, error.code='timeout', retriable=True.
        """
        return cls(
            request_id=request_id,
            trace_id=trace_id,
            success=False,
            data=None,
            error=ErrorInfo(
                code="timeout",
                message=f"Capability execution exceeded {timeout_ms}ms deadline",
                retriable=True,
            ),
            provider_id=provider_id,
            duration_ms=duration_ms,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: Dict[str, Any] = {
            "request_id": self.request_id,
            "trace_id": self.trace_id,
            "success": self.success,
            "data": dict(self.data) if self.data else None,
            "error": self.error.to_dict() if self.error else None,
            "provider_id": self.provider_id,
            "duration_ms": self.duration_ms,
            "retrieval_time_ms": self.retrieval_time_ms,
            "resolution_time_ms": self.resolution_time_ms,
            "execution_time_ms": self.execution_time_ms,
        }
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CapabilityResult":
        """Create CapabilityResult from dictionary."""
        error_data = data.get("error")
        error = ErrorInfo.from_dict(error_data) if error_data else None
        return cls(
            request_id=data.get("request_id", ""),
            trace_id=data.get("trace_id", ""),
            success=data.get("success", False),
            data=data.get("data"),
            error=error,
            provider_id=data.get("provider_id", ""),
            duration_ms=data.get("duration_ms", 0),
            retrieval_time_ms=data.get("retrieval_time_ms", 0),
            resolution_time_ms=data.get("resolution_time_ms", 0),
            execution_time_ms=data.get("execution_time_ms", 0),
        )


# ---------------------------------------------------------------------------
# 1.3.3 -- CapabilityContract + InputSpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InputSpec:
    """
    Describes a single input parameter for a capability contract.

    Matches the input_spec definition in tool_contract.schema.json.
    """

    name: str = ""
    type: str = ""
    description: str = ""
    enum: Optional[List[str]] = None
    default: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result: Dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "description": self.description,
        }
        if self.enum is not None:
            result["enum"] = list(self.enum)
        if self.default is not None:
            result["default"] = self.default
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InputSpec":
        """Create InputSpec from dictionary."""
        return cls(
            name=data.get("name", ""),
            type=data.get("type", ""),
            description=data.get("description", ""),
            enum=data.get("enum"),
            default=data.get("default"),
        )


# ---------------------------------------------------------------------------
# 2.4.1 -- CapabilityVersion
# ---------------------------------------------------------------------------

import re as _re

_SEMVER_RE = _re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class CapabilityVersionError(Exception):
    """Raised when a version string cannot be parsed."""

    def __init__(self, raw: str):
        self.raw = raw
        super().__init__(f"Invalid semver string: '{raw}'. Expected MAJOR.MINOR.PATCH.")


@dataclass(frozen=True, order=False)
class CapabilityVersion:
    """
    Parsed semantic version for capability contracts (2.4.1).

    Encapsulates a MAJOR.MINOR.PATCH triple with comparison,
    compatibility, and parsing logic.

    Compatibility rule (semver):
      Two versions are **compatible** if they share the same major version.
      major=0 is treated as unstable: only exact match is compatible.

    References:
      - Epic 2.4.1 in fabric-implementation-plan.md
      - https://semver.org/spec/v2.0.0.html
    """

    major: int = 0
    minor: int = 0
    patch: int = 0

    # ---- Parsing ----

    @classmethod
    def parse(cls, version_str: str) -> "CapabilityVersion":
        """
        Parse a semver string into a CapabilityVersion.

        Args:
            version_str: String in "MAJOR.MINOR.PATCH" format.

        Returns:
            Parsed CapabilityVersion.

        Raises:
            CapabilityVersionError: If string does not match semver format.
        """
        m = _SEMVER_RE.match(version_str.strip())
        if not m:
            raise CapabilityVersionError(version_str)
        return cls(
            major=int(m.group(1)),
            minor=int(m.group(2)),
            patch=int(m.group(3)),
        )

    # ---- Comparison ----

    def _as_tuple(self) -> tuple:
        return (self.major, self.minor, self.patch)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CapabilityVersion):
            return NotImplemented
        return self._as_tuple() == other._as_tuple()

    def __lt__(self, other: "CapabilityVersion") -> bool:
        if not isinstance(other, CapabilityVersion):
            return NotImplemented
        return self._as_tuple() < other._as_tuple()

    def __le__(self, other: "CapabilityVersion") -> bool:
        if not isinstance(other, CapabilityVersion):
            return NotImplemented
        return self._as_tuple() <= other._as_tuple()

    def __gt__(self, other: "CapabilityVersion") -> bool:
        if not isinstance(other, CapabilityVersion):
            return NotImplemented
        return self._as_tuple() > other._as_tuple()

    def __ge__(self, other: "CapabilityVersion") -> bool:
        if not isinstance(other, CapabilityVersion):
            return NotImplemented
        return self._as_tuple() >= other._as_tuple()

    def __hash__(self) -> int:
        return hash(self._as_tuple())

    # ---- Compatibility ----

    def is_compatible_with(self, other: "CapabilityVersion") -> bool:
        """
        Check if this version is compatible with another.

        Compatible means: same major version AND major > 0.
        major=0 (unstable) is only compatible with exact match.

        Args:
            other: The version to check compatibility against.

        Returns:
            True if the versions are compatible.
        """
        if self.major == 0 or other.major == 0:
            return self == other
        return self.major == other.major

    # ---- Convenience ----

    @staticmethod
    def compare(v1: "CapabilityVersion", v2: "CapabilityVersion") -> int:
        """
        Compare two versions.

        Returns:
            -1 if v1 < v2, 0 if v1 == v2, 1 if v1 > v2.
        """
        if v1 < v2:
            return -1
        if v1 > v2:
            return 1
        return 0

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def __repr__(self) -> str:
        return f"CapabilityVersion({self.major}, {self.minor}, {self.patch})"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "major": self.major,
            "minor": self.minor,
            "patch": self.patch,
            "string": str(self),
        }


@dataclass(frozen=True)
class CapabilityContract:
    """
    Registry record for a capability (tool, agent, prompt, or workflow).

    This is the in-memory representation of a validated YAML contract.
    Stored in CapabilityRegistry (2.2.1), queried by RetrievalEngine (4.1.5),
    Resolver (3.1.5), and ContextBuilder (4.2.1).

    Invariants:
      - Immutable after construction (frozen=True)
      - name follows type convention (FAB-11): tool.*, agent.*, workflow.*, concierge.*
      - version is semver
      - domain has at least 1 tag (JSON Schema enforced)
      - All contracts validated against schema before registration (FAB-12)

    References:
      - fabric_discussion.md Section 6 (Tool Contract Schema)
      - tool_contract.schema.json (JSON Schema validation)
    """

    # ---- Identity ----
    name: str = ""
    version: str = ""
    domain: List[str] = field(default_factory=list)
    description: str = ""

    # ---- Capabilities & Limitations ----
    capabilities: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)

    # ---- Input Requirements ----
    required_inputs: List[InputSpec] = field(default_factory=list)
    optional_inputs: List[InputSpec] = field(default_factory=list)

    # ---- Context Requirements (SessionState sections) ----
    required_context: List[str] = field(default_factory=list)
    optional_context: List[str] = field(default_factory=list)

    # ---- Output Schema (JSON Schema fragment) ----
    output: Dict[str, Any] = field(default_factory=dict)

    # ---- Provider Metadata ----
    provider_type: str = ""
    provider_id: str = ""
    provider_endpoint: str = ""

    # ---- Policy Metadata ----
    safety_band_min: str = SafetyBand.GREEN.value
    cost_per_call: float = 0.0
    avg_latency_ms: int = 0
    max_latency_ms: int = 0
    availability: str = Availability.ONLINE.value

    # ---- Audit Fields ----
    registered_at: str = ""
    last_updated: str = ""
    success_rate_30d: float = 0.0
    total_invocations_30d: int = 0

    # ---- Lifecycle Metadata (4.5.6) ----
    # Defaults are backward-compatible: existing YAML-loaded contracts
    # behave identically (ephemeral=True, created_by="", session_scoped=True).
    ephemeral: bool = True
    created_by: str = ""
    created_at_iso: str = ""
    session_scoped: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "version": self.version,
            "domain": list(self.domain),
            "description": self.description,
            "capabilities": list(self.capabilities),
            "limitations": list(self.limitations),
            "required_inputs": [inp.to_dict() for inp in self.required_inputs],
            "optional_inputs": [inp.to_dict() for inp in self.optional_inputs],
            "required_context": list(self.required_context),
            "optional_context": list(self.optional_context),
            "output": dict(self.output),
            "provider_type": self.provider_type,
            "provider_id": self.provider_id,
            "provider_endpoint": self.provider_endpoint,
            "safety_band_min": self.safety_band_min,
            "cost_per_call": self.cost_per_call,
            "avg_latency_ms": self.avg_latency_ms,
            "max_latency_ms": self.max_latency_ms,
            "availability": self.availability,
            "registered_at": self.registered_at,
            "last_updated": self.last_updated,
            "success_rate_30d": self.success_rate_30d,
            "total_invocations_30d": self.total_invocations_30d,
            "ephemeral": self.ephemeral,
            "created_by": self.created_by,
            "created_at_iso": self.created_at_iso,
            "session_scoped": self.session_scoped,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CapabilityContract":
        """Create CapabilityContract from dictionary."""
        return cls(
            name=data.get("name", ""),
            version=data.get("version", ""),
            domain=data.get("domain", []),
            description=data.get("description", ""),
            capabilities=data.get("capabilities", []),
            limitations=data.get("limitations", []),
            required_inputs=[InputSpec.from_dict(inp) for inp in data.get("required_inputs", [])],
            optional_inputs=[InputSpec.from_dict(inp) for inp in data.get("optional_inputs", [])],
            required_context=data.get("required_context", []),
            optional_context=data.get("optional_context", []),
            output=data.get("output", {}),
            provider_type=data.get("provider_type", ""),
            provider_id=data.get("provider_id", ""),
            provider_endpoint=data.get("provider_endpoint", ""),
            safety_band_min=data.get("safety_band_min", SafetyBand.GREEN.value),
            cost_per_call=data.get("cost_per_call", 0.0),
            avg_latency_ms=data.get("avg_latency_ms", 0),
            max_latency_ms=data.get("max_latency_ms", 0),
            availability=data.get("availability", Availability.ONLINE.value),
            registered_at=data.get("registered_at", ""),
            last_updated=data.get("last_updated", ""),
            success_rate_30d=data.get("success_rate_30d", 0.0),
            total_invocations_30d=data.get("total_invocations_30d", 0),
            ephemeral=data.get("ephemeral", True),
            created_by=data.get("created_by", ""),
            created_at_iso=data.get("created_at_iso", ""),
            session_scoped=data.get("session_scoped", True),
        )


# ---------------------------------------------------------------------------
# 1.3.4 -- AgentContract (extends CapabilityContract)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentContract(CapabilityContract):
    """
    Registry record for an agent capability.

    Extends CapabilityContract with agent-specific fields for the Agent Factory.
    Agents are tools with their own LLM, spawned on-demand from YAML templates.

    Invariants:
      - provider_type is always AGENT
      - tools_granted is scoped per plan step (FAB-07: only plan-specified tools)
      - llm_budget_tokens > 0
      - max_execution_time_ms > 0

    References:
      - fabric_discussion.md Section 6 (Agent Contract Schema)
      - agent_contract.schema.json (JSON Schema validation)
      - FAB-006 (Agent Lifecycle specialization)
      - concierge.mmd line 159 (spawn_via_fabric)
      - orchestrator.mmd (PORT_FABRIC: spawn(AgentContract) -> AgentHandle)

    Consumed by:
      - AgentFactory (4.3.1) for agent instantiation
      - ToolScope (3.2.6) for scoped tool access enforcement
    """

    # ---- Agent-Specific Fields ----
    prompt_template: str = ""
    tools_granted: List[str] = field(default_factory=list)
    llm_budget_tokens: int = 0
    max_tool_calls: int = 0
    max_execution_time_ms: int = 30000
    template_file: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = super().to_dict()
        result.update(
            {
                "prompt_template": self.prompt_template,
                "tools_granted": list(self.tools_granted),
                "llm_budget_tokens": self.llm_budget_tokens,
                "max_tool_calls": self.max_tool_calls,
                "max_execution_time_ms": self.max_execution_time_ms,
                "template_file": self.template_file,
            }
        )
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentContract":
        """Create AgentContract from dictionary."""
        return cls(
            # ---- Base CapabilityContract fields ----
            name=data.get("name", ""),
            version=data.get("version", ""),
            domain=data.get("domain", []),
            description=data.get("description", ""),
            capabilities=data.get("capabilities", []),
            limitations=data.get("limitations", []),
            required_inputs=[InputSpec.from_dict(inp) for inp in data.get("required_inputs", [])],
            optional_inputs=[InputSpec.from_dict(inp) for inp in data.get("optional_inputs", [])],
            required_context=data.get("required_context", []),
            optional_context=data.get("optional_context", []),
            output=data.get("output", {}),
            provider_type=data.get("provider_type", ProviderType.AGENT.value),
            provider_id=data.get("provider_id", ""),
            provider_endpoint=data.get("provider_endpoint", ""),
            safety_band_min=data.get("safety_band_min", SafetyBand.GREEN.value),
            cost_per_call=data.get("cost_per_call", 0.0),
            avg_latency_ms=data.get("avg_latency_ms", 0),
            max_latency_ms=data.get("max_latency_ms", 0),
            availability=data.get("availability", Availability.ONLINE.value),
            registered_at=data.get("registered_at", ""),
            last_updated=data.get("last_updated", ""),
            success_rate_30d=data.get("success_rate_30d", 0.0),
            total_invocations_30d=data.get("total_invocations_30d", 0),
            # ---- Lifecycle metadata (4.5.6) ----
            ephemeral=data.get("ephemeral", True),
            created_by=data.get("created_by", ""),
            created_at_iso=data.get("created_at_iso", ""),
            session_scoped=data.get("session_scoped", True),
            # ---- Agent-specific fields ----
            prompt_template=data.get("prompt_template", ""),
            tools_granted=data.get("tools_granted", []),
            llm_budget_tokens=data.get("llm_budget_tokens", 0),
            max_tool_calls=data.get("max_tool_calls", 0),
            max_execution_time_ms=data.get("max_execution_time_ms", 30000),
            template_file=data.get("template_file", ""),
        )


# ---------------------------------------------------------------------------
# 1.3.5 -- PromptContract + VariableSpec + OutputFormat
# ---------------------------------------------------------------------------


class OutputFormat(str, Enum):
    """Expected output format from a prompt template."""

    TEXT = "TEXT"
    JSON = "JSON"
    STRUCTURED = "STRUCTURED"


@dataclass(frozen=True)
class VariableSpec:
    """
    Describes a single variable in a prompt template.

    Matches the variable_spec definition in prompt_contract.schema.json.

    Attributes:
        name: Variable name as used in the template (e.g. {{guest_names}})
        type: Data type (STRING, NUMBER, BOOLEAN, DATE, OBJECT, ARRAY)
        required: Whether this variable must be provided
        default: Default value if not provided (only valid when required=False)
        description: Human-readable description
    """

    name: str = ""
    type: str = "STRING"
    required: bool = True
    default: Optional[str] = None
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result: Dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "required": self.required,
            "description": self.description,
        }
        if self.default is not None:
            result["default"] = self.default
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VariableSpec":
        """Create VariableSpec from dictionary."""
        return cls(
            name=data.get("name", ""),
            type=data.get("type", "STRING"),
            required=data.get("required", True),
            default=data.get("default"),
            description=data.get("description", ""),
        )


@dataclass(frozen=True)
class PromptContract:
    """
    Registry record for a prompt template.

    Prompts are templates used by agents and the Planner. They declare
    variables, output format, and compatibility with agents/tools.
    Stored in CapabilityRegistry, queried by find_relevant_prompts() (4.1.5).

    Invariants:
      - Immutable after construction (frozen=True)
      - name follows prompt convention: lowercase alphanumeric + underscores
      - version is semver
      - domain has at least 1 tag
      - variables list declares all template placeholders
      - template_file points to an existing .txt file

    References:
      - fabric_discussion.md Section 6 (Prompt Contract Schema)
      - prompt_contract.schema.json (JSON Schema validation)
      - planner.mmd (Planner discovery tools call find_relevant_prompts)
      - orchestrator.mmd (Orchestrator resolves prompt for agent steps)

    Consumed by:
      - RetrievalEngine.find_relevant_prompts() (4.1.5)
      - ContextBuilder (4.2.1) for prompt compilation
      - PromptContractParser (2.1.4) for YAML -> dataclass
    """

    # ---- Identity ----
    name: str = ""
    version: str = ""
    domain: List[str] = field(default_factory=list)
    description: str = ""

    # ---- Retrieval Matching ----
    intent_match: List[str] = field(default_factory=list)

    # ---- Template Variables ----
    variables: List[VariableSpec] = field(default_factory=list)

    # ---- Template Configuration ----
    template_file: str = ""
    max_tokens: int = 0
    output_format: str = OutputFormat.TEXT.value

    # ---- Compatibility ----
    compatible_agents: List[str] = field(default_factory=list)
    compatible_tools: List[str] = field(default_factory=list)

    # ---- Audit Fields ----
    registered_at: str = ""
    last_updated: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "version": self.version,
            "domain": list(self.domain),
            "description": self.description,
            "intent_match": list(self.intent_match),
            "variables": [v.to_dict() for v in self.variables],
            "template_file": self.template_file,
            "max_tokens": self.max_tokens,
            "output_format": self.output_format,
            "compatible_agents": list(self.compatible_agents),
            "compatible_tools": list(self.compatible_tools),
            "registered_at": self.registered_at,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PromptContract":
        """Create PromptContract from dictionary."""
        return cls(
            name=data.get("name", ""),
            version=data.get("version", ""),
            domain=data.get("domain", []),
            description=data.get("description", ""),
            intent_match=data.get("intent_match", []),
            variables=[VariableSpec.from_dict(v) for v in data.get("variables", [])],
            template_file=data.get("template_file", ""),
            max_tokens=data.get("max_tokens", 0),
            output_format=data.get("output_format", OutputFormat.TEXT.value),
            compatible_agents=data.get("compatible_agents", []),
            compatible_tools=data.get("compatible_tools", []),
            registered_at=data.get("registered_at", ""),
            last_updated=data.get("last_updated", ""),
        )


# ---------------------------------------------------------------------------
# 1.3.6 -- WorkflowContract + TriggerSpec + PlanStep
# ---------------------------------------------------------------------------


class TriggerType(str, Enum):
    """Workflow trigger type."""

    CRON = "cron"
    EVENT = "event"
    MANUAL = "manual"


@dataclass(frozen=True)
class TriggerSpec:
    """
    How and when a workflow is triggered.

    Matches the trigger_spec definition in workflow_contract.schema.json.

    Attributes:
        type: Trigger type (cron, event, manual)
        schedule: Cron expression (required when type=cron)
        timezone: IANA timezone for cron schedule
        event_topic: Event topic (required when type=event)
    """

    type: str = TriggerType.MANUAL.value
    schedule: Optional[str] = None
    timezone: Optional[str] = None
    event_topic: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result: Dict[str, Any] = {"type": self.type}
        if self.schedule is not None:
            result["schedule"] = self.schedule
        if self.timezone is not None:
            result["timezone"] = self.timezone
        if self.event_topic is not None:
            result["event_topic"] = self.event_topic
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TriggerSpec":
        """Create TriggerSpec from dictionary."""
        return cls(
            type=data.get("type", TriggerType.MANUAL.value),
            schedule=data.get("schedule"),
            timezone=data.get("timezone"),
            event_topic=data.get("event_topic"),
        )


@dataclass(frozen=True)
class FabricPlanStep:
    """
    A single step in a CommittedPlan or WorkflowContract.

    Each step specifies a capability to invoke, with optional prompt,
    parameters, scoped tools, and DAG dependencies.

    Matches the plan_step definition in workflow_contract.schema.json
    and PlanStep from FAB-001.

    Invariants:
      - Immutable after planning phase (frozen=True)
      - id is unique within the plan/workflow
      - capability follows naming convention (tool.*/agent.*/workflow.*)
      - tools_granted scoped per step (FAB-07)
      - deps must reference step IDs that exist in the same plan

    References:
      - workflow_contract.schema.json (plan_step definition)
      - FAB-001 (PlanStep type)
      - orchestrator.mmd (DAG engine resolves step dependencies)
    """

    id: str = ""
    capability: str = ""
    prompt_template: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    tools_granted: List[str] = field(default_factory=list)
    deps: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result: Dict[str, Any] = {
            "id": self.id,
            "capability": self.capability,
        }
        if self.prompt_template is not None:
            result["prompt_template"] = self.prompt_template
        if self.params:
            result["params"] = dict(self.params)
        if self.tools_granted:
            result["tools_granted"] = list(self.tools_granted)
        if self.deps:
            result["deps"] = list(self.deps)
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FabricPlanStep":
        """Create FabricPlanStep from dictionary."""
        return cls(
            id=data.get("id", ""),
            capability=data.get("capability", ""),
            prompt_template=data.get("prompt_template"),
            params=data.get("params", {}),
            tools_granted=data.get("tools_granted", []),
            deps=data.get("deps", []),
        )


# Backward-compatible alias (P2.4: disambiguate from Orchestrator's PlanStep)
PlanStep = FabricPlanStep


@dataclass(frozen=True)
class WorkflowContract:
    """
    Registry record for a workflow capability.

    Workflows are frozen CommittedPlans saved for repeated execution
    (cron, event trigger, or manual). They define a DAG of steps
    with dependencies and trigger configuration.

    Invariants:
      - Immutable after construction (frozen=True)
      - name follows convention: workflow.run.<name>
      - version is semver
      - steps is non-empty (minItems: 1 in schema)
      - dependencies must form acyclic DAG
      - max_depth bounds recursion (1-10, default 3)
      - safety_band_min enforced before execution

    References:
      - fabric_discussion.md Section 6 (Workflow Contract Schema)
      - workflow_contract.schema.json (JSON Schema validation)
      - FAB-001 (CommittedPlan type, PlanStep type)
      - orchestrator.mmd (DAG engine executes workflow steps)

    Consumed by:
      - WorkflowContractParser (2.1.5) for YAML -> dataclass
      - WorkflowProvider (3.3.5) for execution
      - CapabilityRegistry (2.2.1) for storage and lookup
    """

    # ---- Identity ----
    name: str = ""
    version: str = ""
    domain: List[str] = field(default_factory=list)
    description: str = ""

    # ---- Plan Origin ----
    source_plan_id: str = ""

    # ---- Trigger Configuration ----
    trigger: Optional[TriggerSpec] = None

    # ---- Execution Steps (DAG) ----
    steps: List[FabricPlanStep] = field(default_factory=list)
    dependencies: Dict[str, List[str]] = field(default_factory=dict)

    # ---- Recursion & Sub-Workflow Control ----
    max_depth: int = 3
    allows_sub_workflows: bool = True

    # ---- Policy Metadata ----
    safety_band_min: str = SafetyBand.GREEN.value
    avg_latency_ms: int = 0
    active: bool = True

    # ---- Audit Fields ----
    created_at: str = ""
    last_run: str = ""
    run_count: int = 0
    success_rate: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "version": self.version,
            "domain": list(self.domain),
            "description": self.description,
            "source_plan_id": self.source_plan_id,
            "trigger": self.trigger.to_dict() if self.trigger else None,
            "steps": [s.to_dict() for s in self.steps],
            "dependencies": {k: list(v) for k, v in self.dependencies.items()},
            "max_depth": self.max_depth,
            "allows_sub_workflows": self.allows_sub_workflows,
            "safety_band_min": self.safety_band_min,
            "avg_latency_ms": self.avg_latency_ms,
            "active": self.active,
            "created_at": self.created_at,
            "last_run": self.last_run,
            "run_count": self.run_count,
            "success_rate": self.success_rate,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowContract":
        """Create WorkflowContract from dictionary."""
        trigger_data = data.get("trigger")
        trigger = TriggerSpec.from_dict(trigger_data) if trigger_data else None
        return cls(
            name=data.get("name", ""),
            version=data.get("version", ""),
            domain=data.get("domain", []),
            description=data.get("description", ""),
            source_plan_id=data.get("source_plan_id", ""),
            trigger=trigger,
            steps=[FabricPlanStep.from_dict(s) for s in data.get("steps", [])],
            dependencies=data.get("dependencies", {}),
            max_depth=data.get("max_depth", 3),
            allows_sub_workflows=data.get("allows_sub_workflows", True),
            safety_band_min=data.get("safety_band_min", SafetyBand.GREEN.value),
            avg_latency_ms=data.get("avg_latency_ms", 0),
            active=data.get("active", True),
            created_at=data.get("created_at", ""),
            last_run=data.get("last_run", ""),
            run_count=data.get("run_count", 0),
            success_rate=data.get("success_rate", 0.0),
        )


# ---------------------------------------------------------------------------
# 1.3.7 -- RetrievalResult + ScoredCapability
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoredCapability:
    """
    A single capability candidate from semantic retrieval, paired with its score.

    Invariants:
      - Immutable (frozen=True, FAB-001)
      - score is in [0.0, 1.0] (cosine similarity)
      - contract is a full CapabilityContract snapshot

    References:
      - FAB-001 (RetrievalCandidate type)
      - fabric_discussion.md Section 8 (Retrieval pipeline, ScoredCapability)
      - FAB-002 (UltraBERT embedding, cosine similarity)
    """

    contract: Optional[CapabilityContract] = None
    score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "contract": self.contract.to_dict() if self.contract else None,
            "score": self.score,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScoredCapability":
        """Create ScoredCapability from dictionary."""
        contract_data = data.get("contract")
        contract = CapabilityContract.from_dict(contract_data) if contract_data else None
        return cls(
            contract=contract,
            score=data.get("score", 0.0),
        )


@dataclass(frozen=True)
class RetrievalResult:
    """
    Results from Semantic Retrieval Engine search.

    Contains top-K candidates with similarity scores. Returned by
    discover_capabilities() and find_relevant_prompts() to the Planner.

    Invariants:
      - Immutable (frozen=True, FAB-001)
      - capabilities sorted by descending score
      - total_matched >= len(capabilities)
      - query_latency_ms reflects end-to-end retrieval time

    References:
      - fabric_discussion.md Section 14 (RetrievalResult schema)
      - FAB-001 (RetrievalResult type: query_intent, candidates, search_time_ms, index_size)
      - fabric_discussion.md Section 8 (Retrieval pipeline output)
      - planner.mmd (Planner discovery tools consume RetrievalResult)

    Consumed by:
      - Planner discovery tools (discover_capabilities, find_relevant_prompts)
      - TaskEnvelope.retrieval_result (pipeline metadata)
    """

    # ---- Results ----
    capabilities: List[ScoredCapability] = field(default_factory=list)
    total_matched: int = 0
    query_latency_ms: int = 0

    # ---- Query Metadata (from FAB-001) ----
    query_intent: str = ""
    index_size: int = 0
    embedding_model: str = "ultrabert-v4.0.0"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "capabilities": [c.to_dict() for c in self.capabilities],
            "total_matched": self.total_matched,
            "query_latency_ms": self.query_latency_ms,
            "query_intent": self.query_intent,
            "index_size": self.index_size,
            "embedding_model": self.embedding_model,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RetrievalResult":
        """Create RetrievalResult from dictionary."""
        return cls(
            capabilities=[ScoredCapability.from_dict(c) for c in data.get("capabilities", [])],
            total_matched=data.get("total_matched", 0),
            query_latency_ms=data.get("query_latency_ms", 0),
            query_intent=data.get("query_intent", ""),
            index_size=data.get("index_size", 0),
            embedding_model=data.get("embedding_model", "ultrabert-v4.0.0"),
        )


# ---------------------------------------------------------------------------
# 1.3.8 -- ExecutionContext
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecutionContext:
    """
    Compiled context for capability execution.

    Built by ContextBuilder (4.2.1) from SessionState sections, request
    parameters, and compiled prompt template. Consumed by all Providers
    via execute(request, context, trace_id).

    Invariants:
      - Immutable after construction (frozen=True)
      - token_count <= 128_000 (K1 context window budget, FAB-08)
      - trace_id matches the originating CapabilityRequest.trace_id
      - session_sections contains only declared required/optional context

    References:
      - fabric_discussion.md Section 12 (Context Builder flow, step [6])
      - FAB-008 (Single Writer: Fabric reads SessionState, never writes)
      - orchestrator.mmd (ContextBuilder reads SessionState per step)

    Consumed by:
      - All Providers via execute(request, context, trace_id)
      - AgentFactory (4.3.1) for agent context injection
      - OutputValidation (3.5.5) for semantic validation context
    """

    # ---- SessionState Snapshot (read-only, per FAB-008) ----
    session_sections: Dict[str, Any] = field(default_factory=dict)

    # ---- Request Parameters ----
    params: Dict[str, Any] = field(default_factory=dict)

    # ---- Compiled Prompt (if applicable) ----
    prompt: Optional[str] = None

    # ---- Token Budget ----
    token_count: int = 0

    # ---- Tracing ----
    trace_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "session_sections": dict(self.session_sections),
            "params": dict(self.params),
            "prompt": self.prompt,
            "token_count": self.token_count,
            "trace_id": self.trace_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionContext":
        """Create ExecutionContext from dictionary."""
        return cls(
            session_sections=data.get("session_sections", {}),
            params=data.get("params", {}),
            prompt=data.get("prompt"),
            token_count=data.get("token_count", 0),
            trace_id=data.get("trace_id", ""),
        )


# ---------------------------------------------------------------------------
# 1.3.9 -- ProviderConfig + TransportType
# ---------------------------------------------------------------------------


class TransportType(str, Enum):
    """Transport protocol for MCP providers."""

    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable-http"


@dataclass(frozen=True)
class ProviderConfig:
    """
    Configuration record for a capability provider instance.

    Stored in ProviderRegistry (3.1.1), consumed by ProviderFactory (3.1.4)
    to instantiate the correct provider runtime. Each provider_id maps to
    exactly one ProviderConfig.

    Invariants:
      - Immutable after construction (frozen=True)
      - provider_type is a valid ProviderType value
      - endpoint required for MCP and BRIDGE providers
      - module_path required for WASM providers
      - max_concurrent > 0
      - max_execution_ms > 0

    References:
      - fabric_discussion.md Section 9 (Provider Resolution Engine, ProviderConfig examples)
      - FAB-005 (Fabric architecture, 6 provider types)
      - policies.contract.yaml (per-provider timeouts)

    Consumed by:
      - ProviderRegistry (3.1.1) for storage and lookup
      - ProviderFactory (3.1.4) for provider instantiation
      - CircuitBreaker (3.4.2) for timeout configuration
      - HealthChecker (3.6.1) for health_check_interval_s
    """

    # ---- Identity ----
    provider_id: str = ""
    provider_type: str = ProviderType.MCP.value

    # ---- Connection ----
    endpoint: Optional[str] = None
    transport: Optional[str] = None
    module_path: Optional[str] = None

    # ---- Resource Limits ----
    sandbox_memory_mb: Optional[int] = None
    max_concurrent: int = 10
    health_check_interval_s: int = 60
    max_execution_ms: int = 30000

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "provider_id": self.provider_id,
            "provider_type": self.provider_type,
            "endpoint": self.endpoint,
            "transport": self.transport,
            "module_path": self.module_path,
            "sandbox_memory_mb": self.sandbox_memory_mb,
            "max_concurrent": self.max_concurrent,
            "health_check_interval_s": self.health_check_interval_s,
            "max_execution_ms": self.max_execution_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProviderConfig":
        """Create ProviderConfig from dictionary."""
        return cls(
            provider_id=data.get("provider_id", ""),
            provider_type=data.get("provider_type", ProviderType.MCP.value),
            endpoint=data.get("endpoint"),
            transport=data.get("transport"),
            module_path=data.get("module_path"),
            sandbox_memory_mb=data.get("sandbox_memory_mb"),
            max_concurrent=data.get("max_concurrent", 10),
            health_check_interval_s=data.get("health_check_interval_s", 60),
            max_execution_ms=data.get("max_execution_ms", 30000),
        )


# ---------------------------------------------------------------------------
# 1.3.10 -- AgentLifecycleState + CapabilityType (completes enum set)
#
# NOTE: ProviderType, SafetyBand, Availability, Tier, RequestStatus,
#       WFQPriority, OutputFormat, TriggerType were defined earlier
#       alongside the types that use them. This section adds the
#       remaining enums required by 1.3.10.
# ---------------------------------------------------------------------------


class AgentLifecycleState(str, Enum):
    """
    6-state FSM for agent lifecycle (ADR-0005, specialized by FAB-006).

    State transitions:
      PENDING -> WARMING -> ACTIVE -> IDLE -> DRAINING -> TERMINATED
                                    -> DRAINING (on error/timeout)

    References:
      - ADR-0005 (Agent Lifecycle, 6-state FSM)
      - FAB-006 (Agent Lifecycle in Fabric)
    """

    PENDING = "PENDING"  # Roster registration
    WARMING = "WARMING"  # Model load, config, KV cache
    ACTIVE = "ACTIVE"  # Processing a request
    IDLE = "IDLE"  # Pooled for reuse
    DRAINING = "DRAINING"  # Graceful shutdown
    TERMINATED = "TERMINATED"  # Cleanup complete


class CapabilityType:
    """
    Canonical capability name prefixes (FAB-11).

    These are NOT an enum because they are used as string prefixes
    for pattern matching, not as discrete values. Each prefix defines
    a category of capability in the registry.

    Usage:
      name.startswith(CapabilityType.TOOL_EXECUTE)

    References:
      - fabric_discussion.md Section 14 (capability naming convention)
      - FAB-11 invariant (capability names follow type conventions)
    """

    # ---- Agent Capabilities ----
    AGENT_SPAWN = "agent.spawn."
    AGENT_EXECUTE = "agent.execute."

    # ---- Tool Capabilities ----
    TOOL_EXECUTE = "tool.execute."
    TOOL_READ = "tool.read."
    TOOL_WRITE = "tool.write."
    TOOL_DELETE = "tool.delete."

    # ---- Workflow Capabilities ----
    WORKFLOW_RUN = "workflow.run."

    # ---- Concierge Capabilities ----
    CONCIERGE_STATE = "concierge.state."

    ALL_PREFIXES = (
        "agent.spawn.",
        "agent.execute.",
        "tool.execute.",
        "tool.read.",
        "tool.write.",
        "tool.delete.",
        "workflow.run.",
        "concierge.state.",
    )

    @classmethod
    def matches(cls, name: str) -> bool:
        """Check if a capability name matches any known prefix."""
        return any(name.startswith(p) for p in cls.ALL_PREFIXES)

    @classmethod
    def get_type(cls, name: str) -> Optional[str]:
        """Extract the type prefix from a capability name, or None."""
        for p in cls.ALL_PREFIXES:
            if name.startswith(p):
                return p.rstrip(".")
        return None


# ---------------------------------------------------------------------------
# 3.1.1 -- ProviderHealth
# ---------------------------------------------------------------------------


class ProviderStatus(str, Enum):
    """Health status for a provider instance."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ProviderHealth:
    """
    Health snapshot for a single provider.

    Returned by ProviderRegistry.health_check() and CapabilityProvider.health_check().

    References:
      - fabric_discussion.md Section 9 (ProviderHealth in ProviderRegistry)
      - Epic 3.1.1 in fabric-implementation-plan.md
    """

    provider_id: str = ""
    status: str = ProviderStatus.UNKNOWN.value
    last_check_at: str = ""
    latency_ms: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "provider_id": self.provider_id,
            "status": self.status,
            "last_check_at": self.last_check_at,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# 3.1.3 -- PolicyResult + ResolvedProvider
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PolicyResult:
    """
    Composite result from PolicyEngine evaluation.

    Security is a hard gate (allowed=False -> immediate reject).
    The other three dimensions contribute additive soft scores.

    References:
      - fabric_discussion.md Section 10 (Four Policy Dimensions)
      - Epic 3.2.5 in fabric-implementation-plan.md
    """

    allowed: bool = True
    score: float = 0.0
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "allowed": self.allowed,
            "score": self.score,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class ResolvedProvider:
    """
    Output of the Provider Resolution pipeline (3.1.5).

    Bundles the instantiated provider reference, the matching contract,
    provider configuration, and policy evaluation results.

    References:
      - fabric_discussion.md Section 9 (Resolution Pipeline output)
      - Epic 3.1.3 / 3.1.5 in fabric-implementation-plan.md
    """

    provider_config: ProviderConfig = field(default_factory=ProviderConfig)
    contract: Optional[Any] = None  # ContractUnion (avoids circular import)
    policy_result: PolicyResult = field(default_factory=PolicyResult)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "provider_config": self.provider_config.to_dict(),
            "contract": (
                self.contract.to_dict()
                if self.contract and hasattr(self.contract, "to_dict")
                else None
            ),
            "policy_result": self.policy_result.to_dict(),
        }


# ---------------------------------------------------------------------------
# 4.5.8 -- AgentResponsePayload
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentResponsePayload:
    """
    Structured response payload from an agent execution.

    Every agent returns its output wrapped in this frozen dataclass.
    AgentFactory.execute() (4.3.2) constructs the payload then embeds
    ``payload.to_dict()`` inside ``CapabilityResult.data["payload"]``.

    Concierge (DELIVERING state) reads::

        result.data["payload"]["answer"]
        result.data["payload"]["domain_data"]
        result.data["payload"]["sources"]

    Multi-agent merging: Concierge aggregates multiple
    AgentResponsePayload instances via existing result aggregation logic.

    Validation rules (via :meth:`validate`):
      - confidence in [0.0, 1.0]
      - domain non-empty
      - answer non-empty

    References:
      - Epic 4.5.8 in fabric-implementation-plan.md
      - fabric_discussion.md Section 13 (Agent Factory execute)
    """

    answer: str = ""
    confidence: float = 0.0
    domain: tuple[str, ...] = ()
    sources: tuple[dict, ...] = ()
    domain_data: Dict[str, Any] = field(default_factory=dict)
    follow_up_needed: bool = False
    follow_up_suggestion: str = ""
    reasoning_trace: tuple[str, ...] = ()
    tools_used: tuple[str, ...] = ()
    k0_queries_made: int = 0

    # ---- Serialization ----

    def to_dict(self) -> Dict[str, Any]:
        """
        JSON-safe serialization.

        Tuples are emitted as lists.  ``domain_data`` and ``sources``
        are deep-copied to prevent caller mutation.
        """
        return {
            "answer": self.answer,
            "confidence": self.confidence,
            "domain": list(self.domain),
            "sources": [dict(s) for s in self.sources],
            "domain_data": dict(self.domain_data),
            "follow_up_needed": self.follow_up_needed,
            "follow_up_suggestion": self.follow_up_suggestion,
            "reasoning_trace": list(self.reasoning_trace),
            "tools_used": list(self.tools_used),
            "k0_queries_made": self.k0_queries_made,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentResponsePayload":
        """
        Classmethod factory with type coercion.

        Accepts a plain ``dict`` (e.g. from JSON deserialization) and
        returns a frozen ``AgentResponsePayload``.  Lists are coerced
        to tuples where the field type requires it.
        """
        raw_sources = data.get("sources", ())
        raw_domain = data.get("domain", ())
        raw_trace = data.get("reasoning_trace", ())
        raw_tools = data.get("tools_used", ())

        return cls(
            answer=str(data.get("answer", "")),
            confidence=float(data.get("confidence", 0.0)),
            domain=tuple(str(d) for d in raw_domain),
            sources=tuple(dict(s) if isinstance(s, dict) else {} for s in raw_sources),
            domain_data=dict(data.get("domain_data", {})),
            follow_up_needed=bool(data.get("follow_up_needed", False)),
            follow_up_suggestion=str(data.get("follow_up_suggestion", "")),
            reasoning_trace=tuple(str(r) for r in raw_trace),
            tools_used=tuple(str(t) for t in raw_tools),
            k0_queries_made=int(data.get("k0_queries_made", 0)),
        )

    # ---- Validation ----

    def validate(self) -> bool:
        """
        Return ``True`` when all business rules are satisfied.

        Rules:
          1. ``confidence`` in [0.0, 1.0]
          2. ``domain`` is non-empty
          3. ``answer`` is non-empty (after stripping whitespace)
        """
        if not (0.0 <= self.confidence <= 1.0):
            return False
        if not self.domain:
            return False
        if not self.answer.strip():
            return False
        return True
