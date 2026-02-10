"""
Pipeline -- Full End-to-End Flow
=================================

Wires Concierge -> Planner -> Orchestrator -> Fabric into a single
callable pipeline. This is the main entry point for the POC.

Flow:
  1. User input -> Concierge (LLM classifies)
  2. Concierge builds TaskEnvelope
  3. If HIGH: Orchestrator asks Planner to build DAG
  4. Planner discovers capabilities, builds CommittedPlan
  5. Orchestrator executes DAG through Fabric
  6. Concierge synthesizes final response (LLM)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from poc.session_state_demo.llm_client import SimpleLLMClient

from .concierge import Concierge
from .discovery import filter_capabilities_by_domain, load_capability_catalog
from .orchestrator import Orchestrator
from .planner import Planner
from .types import ComplexityTier, OrchestratorResult, PlanRequest, TaskEnvelope

logger = logging.getLogger(__name__)


class Pipeline:
    """
    End-to-end Concierge -> Planner -> Orchestrator pipeline.

    Integrates all three components with real LLMs and real Fabric.
    """

    def __init__(
        self,
        concierge: Concierge,
        planner: Planner,
        orchestrator: Orchestrator,
        capabilities: List[Dict[str, Any]],
    ) -> None:
        self._concierge = concierge
        self._planner = planner
        self._orchestrator = orchestrator
        self._capabilities = capabilities

    @classmethod
    def create(
        cls,
        api_key: str,
        fabric: Any,
        model: str = "gemini-2.5-flash",
        contracts_dir: Optional[Path] = None,
    ) -> "Pipeline":
        """
        Factory: create a fully wired pipeline.

        Args:
            api_key: Google AI API key.
            fabric: CapabilityFabric instance.
            model: Gemini model name.
            contracts_dir: Path to tool contracts directory.

        Returns:
            Fully wired Pipeline instance.
        """
        llm = SimpleLLMClient(api_key=api_key, model=model)

        concierge = Concierge(llm_client=llm)
        planner = Planner(llm_client=llm)
        orchestrator = Orchestrator(fabric=fabric)

        caps_dir = contracts_dir or Path("k1/contracts/tools")
        capabilities = load_capability_catalog(caps_dir)

        return cls(
            concierge=concierge,
            planner=planner,
            orchestrator=orchestrator,
            capabilities=capabilities,
        )

    async def run(self, user_input: str) -> Dict[str, Any]:
        """
        Run the full pipeline for a user input.

        Steps:
          1. Concierge classifies (real LLM)
          2. Route based on tier
          3. If HIGH: Planner builds DAG (real LLM) -> Orchestrator executes
          4. Concierge synthesizes response (real LLM)

        Args:
            user_input: Raw user input text.

        Returns:
            Dict with envelope, plan (if HIGH), results, and response.
        """
        output: Dict[str, Any] = {"user_input": user_input}

        # Step 1: Concierge classifies
        logger.info("=" * 60)
        logger.info("PIPELINE START: %s", user_input[:80])
        logger.info("=" * 60)

        envelope = await self._concierge.classify(user_input)
        output["envelope"] = {
            "tier": envelope.tier.value,
            "intent": envelope.intent,
            "domains": envelope.domains,
        }

        logger.info(
            "CLASSIFICATION: tier=%s intent='%s' domains=%s",
            envelope.tier.value,
            envelope.intent,
            envelope.domains,
        )

        # Step 2: Route based on tier
        if envelope.tier == ComplexityTier.LOW:
            result = await self._handle_low(envelope)
        elif envelope.tier == ComplexityTier.MEDIUM:
            result = await self._handle_medium(envelope)
        else:
            result = await self._handle_high(envelope)

        output["orchestrator_result"] = {
            "success": result.success,
            "total_duration_ms": result.total_duration_ms,
            "steps": [
                {
                    "step_id": sr.step_id,
                    "capability": sr.capability_name,
                    "success": sr.success,
                    "data": sr.data,
                    "error": sr.error,
                    "duration_ms": sr.duration_ms,
                }
                for sr in result.step_results
            ],
        }

        # Step 3: Concierge synthesizes response
        step_dicts = [
            {
                "capability": sr.capability_name,
                "success": sr.success,
                "data": sr.data,
                "error": sr.error,
                "description": sr.step_id,
            }
            for sr in result.step_results
        ]

        response = await self._concierge.synthesize_response(
            user_input=user_input,
            step_results=step_dicts,
        )
        output["response"] = response

        logger.info("=" * 60)
        logger.info("PIPELINE COMPLETE")
        logger.info("=" * 60)

        return output

    async def _handle_low(self, envelope: TaskEnvelope) -> OrchestratorResult:
        """Handle LOW tier -- single direct Fabric call (no planner)."""
        logger.info("[LOW] Direct execution path")

        # For LOW tier, Concierge already knows what tool to use.
        # Find the most relevant capability for the intent.
        relevant = filter_capabilities_by_domain(
            self._capabilities,
            envelope.domains,
        )

        if not relevant:
            from .types import OrchestratorResult, StepResult

            return OrchestratorResult(
                success=False,
                step_results=[
                    StepResult(
                        step_id="low-direct",
                        success=False,
                        error="No capabilities found for domains",
                    )
                ],
                trace_id=envelope.trace_id,
            )

        # Use first matching capability
        cap = relevant[0]
        return await self._orchestrator.execute_direct(
            envelope=envelope,
            capability_name=cap["name"],
            params=envelope.context,
        )

    async def _handle_medium(self, envelope: TaskEnvelope) -> OrchestratorResult:
        """Handle MEDIUM tier -- Orchestrator with 1-2 Fabric calls (no planner)."""
        logger.info("[MEDIUM] Orchestrator direct path (no planner)")

        # For MEDIUM, still use the Planner for simplicity in this POC
        # (production would have Concierge specify the exact calls)
        return await self._handle_high(envelope)

    async def _handle_high(self, envelope: TaskEnvelope) -> OrchestratorResult:
        """Handle HIGH tier -- full Planner -> Orchestrator -> Fabric."""
        logger.info("[HIGH] Full planning pipeline")

        # Filter capabilities to relevant domains
        relevant_caps = filter_capabilities_by_domain(
            self._capabilities,
            envelope.domains,
        )

        if not relevant_caps:
            # If domain filter too strict, give all capabilities
            relevant_caps = self._capabilities

        logger.info(
            "[HIGH] %d relevant capabilities for domains %s",
            len(relevant_caps),
            envelope.domains,
        )

        # Build PlanRequest
        plan_request = PlanRequest(
            intent=envelope.intent,
            user_input=envelope.user_input,
            domains=envelope.domains,
            available_capabilities=relevant_caps,
            context=envelope.context,
            trace_id=envelope.trace_id,
        )

        # Planner builds the DAG (real LLM call)
        plan = await self._planner.build_plan(plan_request)

        if not plan.steps:
            from .types import OrchestratorResult, StepResult

            return OrchestratorResult(
                plan_id=plan.plan_id,
                success=False,
                step_results=[
                    StepResult(
                        step_id="plan-failed",
                        success=False,
                        error="Planner produced empty plan",
                    )
                ],
                trace_id=envelope.trace_id,
            )

        logger.info(
            "[HIGH] Plan: %d steps, reasoning='%s'",
            len(plan.steps),
            plan.reasoning[:100],
        )
        for step in plan.steps:
            deps = f" (depends on: {step.depends_on})" if step.depends_on else ""
            logger.info(
                "  %s: %s%s -- %s",
                step.step_id,
                step.capability_name,
                deps,
                step.description,
            )

        # Orchestrator executes the DAG (NO LLM -- mechanical execution)
        result = await self._orchestrator.execute_plan(plan)

        return result
