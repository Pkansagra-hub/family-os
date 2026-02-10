"""
POC Domain Types
=================

Minimal frozen dataclasses for the Concierge -> Planner -> Orchestrator flow.

Types:
  - TaskEnvelope: Concierge -> Orchestrator (what needs doing)
  - PlanRequest: Orchestrator -> Planner (plan this intent)
  - PlanStep: A single step in a committed plan
  - CommittedPlan: Planner -> Orchestrator (execute this DAG)
  - OrchestratorResult: Aggregated results from DAG execution
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ComplexityTier(str, Enum):
    """Complexity routing tier."""

    LOW = "LOW"  # <2s, direct Fabric call
    MEDIUM = "MEDIUM"  # 2-10s, Orchestrator no planning
    HIGH = "HIGH"  # 10-60s, full Planner + Orchestrator + Fabric


@dataclass(frozen=True)
class TaskEnvelope:
    """
    Concierge -> Orchestrator message.

    Contains the user's intent, extracted context, and the
    complexity tier that determines the execution path.
    """

    envelope_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_input: str = ""
    intent: str = ""
    domains: List[str] = field(default_factory=list)
    tier: ComplexityTier = ComplexityTier.HIGH
    context: Dict[str, Any] = field(default_factory=dict)
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass(frozen=True)
class PlanRequest:
    """
    Orchestrator -> Planner message.

    Asks the Planner to build a DAG plan for the given intent.
    The Planner discovers capabilities on its own via agentic
    function calling -- available_capabilities is optional and
    only used for backwards compatibility.
    """

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    intent: str = ""
    user_input: str = ""
    domains: List[str] = field(default_factory=list)
    available_capabilities: List[Dict[str, Any]] = field(default_factory=list)  # legacy/optional
    context: Dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""


@dataclass(frozen=True)
class PlanStep:
    """
    A single step in a CommittedPlan.

    Maps directly to a CapabilityRequest that the Orchestrator
    will send to Fabric.
    """

    step_id: str = ""
    capability_name: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    description: str = ""


@dataclass(frozen=True)
class CommittedPlan:
    """
    Planner -> Orchestrator message.

    A validated DAG of PlanSteps ready for execution.
    The Orchestrator blindly executes this.
    """

    plan_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    intent: str = ""
    steps: List[PlanStep] = field(default_factory=list)
    reasoning: str = ""
    trace_id: str = ""


@dataclass
class StepResult:
    """Result of a single DAG step execution."""

    step_id: str = ""
    capability_name: str = ""
    success: bool = False
    data: Any = None
    error: Optional[str] = None
    duration_ms: int = 0


@dataclass
class OrchestratorResult:
    """
    Aggregated results from the Orchestrator's DAG execution.

    Contains all step results plus the original plan for context.
    """

    plan_id: str = ""
    success: bool = False
    step_results: List[StepResult] = field(default_factory=list)
    total_duration_ms: int = 0
    trace_id: str = ""

    @property
    def failed_steps(self) -> List[StepResult]:
        return [r for r in self.step_results if not r.success]

    @property
    def successful_steps(self) -> List[StepResult]:
        return [r for r in self.step_results if r.success]
