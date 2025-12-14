"""
Data models for 4-Stage Planning Pipeline

ADR: 0007 - 4-Stage Planning Pipeline
Contracts: k1/contracts/planning/pipeline/*.yml
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class StepOp(str, Enum):
    """Step operation types (from ADR-0007)"""

    TOOL = "Tool"  # Call MCP tool
    MODEL = "Model"  # Call LLM for reasoning
    ASK = "Ask"  # Ask user for input


class PlanComplexity(str, Enum):
    """Plan complexity levels (from ADR-0007)"""

    SIMPLE = "simple"  # 1-2 steps, <500ms
    MEDIUM = "medium"  # 3-5 steps, <2s
    COMPLEX = "complex"  # 6+ steps, <5s


class ValidationStatus(str, Enum):
    """Validation status (from ADR-0007c)"""

    PENDING = "PENDING"
    PASSED = "PASSED"
    PASSED_WITH_WARNINGS = "PASSED_WITH_WARNINGS"
    FAILED = "FAILED"
    REQUIRES_ARBITER = "REQUIRES_ARBITER"


class PrivacyBand(str, Enum):
    """Privacy bands (from ADR-0037)"""

    GREEN = "GREEN"  # Public data, no restrictions
    AMBER = "AMBER"  # Sensitive, logging required
    RED = "RED"  # Highly sensitive, arbiter required


@dataclass
class PlanStep:
    """
    Single step in plan (all stages)

    Based on ADR-0007 Sketch/Expand/Validate schemas
    """

    step_id: str  # Unique step identifier
    op: StepOp  # Tool/Model/Ask
    description: str  # What this step does
    needs: List[str] = field(default_factory=list)  # Step dependencies (step_ids)

    # Stage 1 (Sketch): Basic fields above

    # Stage 2 (Expand): Add tool/agent details
    tool_name: Optional[str] = None  # Tool to call (if op=TOOL)
    agent_id: Optional[str] = None  # Agent assigned to execute
    parameters: Dict[str, Any] = field(default_factory=dict)  # Tool parameters
    estimated_latency_ms: int = 0  # Estimated duration
    estimated_cost: float = 0.0  # Estimated cost

    # Stage 3 (Validate): Add validation results
    is_valid: bool = True  # Validation passed
    validation_errors: List[str] = field(default_factory=list)  # Errors found
    privacy_band: PrivacyBand = PrivacyBand.GREEN  # Privacy classification


@dataclass
class SketchPlan:
    """
    Stage 1 output: High-level plan from LLM

    Based on ADR-0007a Sketch Stage schema
    Contract: k1/contracts/planning/pipeline/sketch_stage.yml
    """

    intent: str  # User intent (e.g., "plan_dinner")
    steps: List[PlanStep]  # High-level steps
    complexity: PlanComplexity  # Simple/Medium/Complex
    raw_output: str  # LLM raw JSON output
    latency_ms: float  # Stage 1 latency
    trace_id: str = ""  # Tracing correlation


@dataclass
class ExpandedPlan:
    """
    Stage 2 output: Plan with tool/agent details filled

    Based on ADR-0007b Expand Stage schema
    Contract: k1/contracts/planning/pipeline/expand_stage.yml
    """

    intent: str
    steps: List[PlanStep]  # Steps with tool/agent details
    complexity: PlanComplexity
    latency_ms: float  # Stage 2 latency (should be <1ms)
    trace_id: str = ""


@dataclass
class ValidationResult:
    """
    Validation check result (from ADR-0007c)
    """

    check_name: str  # e.g., "budget_check"
    passed: bool  # Check passed
    severity: str  # ERROR/WARNING/INFO
    message: str  # Human-readable description
    details: Dict[str, Any] = field(default_factory=dict)  # Additional context


@dataclass
class ValidatedPlan:
    """
    Stage 3 output: Plan validated for safety/budget/capabilities

    Based on ADR-0007c Validation Stage schema
    Contract: k1/contracts/planning/pipeline/validation_stage.yml
    """

    intent: str
    steps: List[PlanStep]
    complexity: PlanComplexity
    status: ValidationStatus  # PASSED/FAILED/REQUIRES_ARBITER
    validation_results: List[ValidationResult]  # All checks performed
    latency_ms: float  # Stage 3 latency
    requires_arbiter: bool = False  # Escalate to human arbiter
    trace_id: str = ""


@dataclass
class CommittedPlan:
    """
    Stage 4 output: Plan serialized and persisted to K0 WAL

    Based on ADR-0007d Commit Stage schema
    Contract: k1/contracts/planning/pipeline/commit_stage.yml
    """

    plan_id: str  # Unique plan ID (e.g., "plan_abc123")
    intent: str
    steps: List[PlanStep]
    complexity: PlanComplexity
    serialized_json: str  # JSON serialization
    plan_hash: str  # SHA256 hash for integrity
    committed_at: str  # ISO8601 timestamp
    latency_ms: float  # Stage 4 latency
    trace_id: str = ""

    # Execution tracking (populated by Orchestrator Phase 3)
    execution_status: str = "PENDING"  # PENDING/RUNNING/COMPLETED/FAILED
    estimated_duration_ms: int = 0  # Total plan duration estimate
    estimated_cost: float = 0.0  # Total plan cost estimate
