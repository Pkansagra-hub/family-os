"""
Complexity Router
=================

Routes requests based on complexity tier.

Reference: k1_cognitive_architecture_skeleton.mmd
- COMPLEXITY-BASED ROUTING:
  - LOW: DISPATCHING -> CAPABILITY_FABRIC -> COMPANIONING (<2s)
  - MEDIUM: DISPATCHING -> ORCHESTRATOR -> CAPABILITY_FABRIC (2-10s)
  - HIGH: DISPATCHING -> ORCHESTRATOR -> PLANNER -> CAPABILITY_FABRIC (10-60s)

For POC, we implement LOW and MEDIUM only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from poc.session_state_demo.concierge.states import ClassificationResult, ComplexityTier, IntentType

if TYPE_CHECKING:
    pass


@dataclass
class RoutingDecision:
    """Decision about how to route the request."""

    tier: ComplexityTier
    route: str  # "direct", "llm_reasoning", "planner" (not implemented)
    requires_llm: bool
    requires_tools: bool
    skip_tool_execution: bool = False  # For greetings
    custom_response: Optional[str] = None  # For simple responses


class ComplexityRouter:
    """
    Routes requests based on complexity classification.

    LOW tier: Direct tool execution, then simple LLM response
    MEDIUM tier: LLM reasoning first, then tool execution
    HIGH tier: Not implemented (would go to Planner/Orchestrator)
    """

    def __init__(self):
        """Initialize router."""
        # Simple response templates for LOW tier greetings
        self._greeting_responses = [
            "Hello! How can I help you today?",
            "Hi there! What can I do for you?",
            "Hey! I'm ready to help. What's on your mind?",
        ]
        self._response_index = 0

    def route(
        self,
        classification: ClassificationResult,
        session_context: Optional[Dict[str, Any]] = None,
    ) -> RoutingDecision:
        """
        Determine routing based on classification.

        Args:
            classification: The classification result
            session_context: Optional session context

        Returns:
            RoutingDecision describing how to process the request
        """
        intent = classification.primary_intent
        tier = classification.complexity

        # Handle greetings specially - no LLM needed
        if intent == IntentType.GREETING:
            return self._route_greeting()

        # Handle clarification responses - simple processing
        if intent == IntentType.CLARIFICATION_RESPONSE:
            return RoutingDecision(
                tier=ComplexityTier.LOW,
                route="direct",
                requires_llm=False,
                requires_tools=False,
                skip_tool_execution=True,
            )

        # Route by tier
        if tier == ComplexityTier.LOW:
            return self._route_low_tier(intent)
        elif tier == ComplexityTier.MEDIUM:
            return self._route_medium_tier(intent)
        else:
            # HIGH tier falls back to MEDIUM in POC
            return self._route_medium_tier(intent)

    def _route_greeting(self) -> RoutingDecision:
        """Route a simple greeting."""
        # Rotate through greeting responses
        response = self._greeting_responses[self._response_index % len(self._greeting_responses)]
        self._response_index += 1

        return RoutingDecision(
            tier=ComplexityTier.LOW,
            route="direct",
            requires_llm=False,
            requires_tools=False,
            skip_tool_execution=True,
            custom_response=response,
        )

    def _route_low_tier(self, intent: IntentType) -> RoutingDecision:
        """Route LOW tier request."""
        # LOW tier: Execute tools directly, then get LLM response
        return RoutingDecision(
            tier=ComplexityTier.LOW,
            route="direct",
            requires_llm=True,  # Still need LLM for natural response
            requires_tools=intent in (IntentType.REQUEST, IntentType.INFORMATION_SHARE),
            skip_tool_execution=False,
        )

    def _route_medium_tier(self, intent: IntentType) -> RoutingDecision:
        """Route MEDIUM tier request."""
        # MEDIUM tier: LLM reasoning with tool calling
        return RoutingDecision(
            tier=ComplexityTier.MEDIUM,
            route="llm_reasoning",
            requires_llm=True,
            requires_tools=True,
            skip_tool_execution=False,
        )


# =============================================================================
# EXECUTION STRATEGIES
# =============================================================================


@dataclass
class ExecutionPlan:
    """Plan for executing a request."""

    steps: List[str]
    estimated_latency_ms: int
    requires_user_wait: bool = False


class ExecutionPlanner:
    """
    Plans execution steps based on routing decision.

    This is a simplified version - production would use full Orchestrator.
    """

    def plan(
        self,
        routing: RoutingDecision,
        classification: ClassificationResult,
    ) -> ExecutionPlan:
        """
        Create execution plan.

        Args:
            routing: The routing decision
            classification: The classification result

        Returns:
            ExecutionPlan with steps and timing estimates
        """
        steps: List[str] = []
        latency = 0

        if routing.tier == ComplexityTier.LOW:
            if routing.requires_tools:
                steps.append("execute_tools")
                latency += 100
            if routing.requires_llm:
                steps.append("generate_response")
                latency += 1500
            elif routing.custom_response:
                steps.append("return_custom_response")
                latency += 10

        elif routing.tier == ComplexityTier.MEDIUM:
            steps.append("llm_reasoning_with_tools")
            latency += 2500
            steps.append("execute_tool_calls")
            latency += 200

        return ExecutionPlan(
            steps=steps,
            estimated_latency_ms=latency,
            requires_user_wait=latency > 3000,
        )
