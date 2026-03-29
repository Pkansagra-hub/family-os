"""
Visual Pipeline Runner
========================

Runs the full Concierge -> Planner -> Orchestrator -> Fabric pipeline
with rich terminal output showing EVERY internal operation.

Usage:
    python -m poc.concierge_planner_orchestrator.runner
    python -m poc.concierge_planner_orchestrator.runner --auto  # Auto-select scenario 1
    python -m poc.concierge_planner_orchestrator.runner --fast  # Skip pauses
    python -m poc.concierge_planner_orchestrator.runner --verbose  # Show all prompts, IO, payloads
    python -m poc.concierge_planner_orchestrator.runner --live  # Use real MCP servers (not stubs)
    python -m poc.concierge_planner_orchestrator.runner --auto --fast --live  # Real data, full speed

Shows:
  - Pipeline header / banner
  - User input box
  - LLM calls (START + latency + tool calls returned)
  - Classification result (tier / intent / domains / reasoning)
  - Routing decision
  - Capability discovery (total contracts scanned, filtered by domain)
  - Plan DAG visualization (waves, parallel vs sequential, dependencies)
  - Fabric execution step-by-step (each step OK/FAIL + data + timing)
  - Response synthesis LLM call
  - Final Concierge response box
  - End-to-end stats (timings, success rates, LLM call count)
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load env files
load_dotenv(Path(__file__).parent.parent / "chat_experience_poc" / ".env")
load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Quiet noisy loggers
logging.basicConfig(level=logging.WARNING)
for _logger_name in (
    "k1.fabric",
    "k1.fabric.core",
    "k1.fabric.core.module_loader",
    "urllib3",
    "google",
    "httpx",
    "httpcore",
    "poc.concierge_planner_orchestrator",
):
    logging.getLogger(_logger_name).setLevel(logging.CRITICAL)

from poc.session_state_demo.llm_client import SimpleLLMClient  # noqa: E402

from . import display as D  # noqa: E402
from .concierge import (  # noqa: E402
    CLASSIFY_SYSTEM_PROMPT,
    CLASSIFY_TOOLS,
    RESPONSE_SYSTEM_PROMPT,
    Concierge,
)
from .discovery import create_discovery_handler, load_capability_catalog  # noqa: E402
from .orchestrator import Orchestrator  # noqa: E402
from .planner import PLANNER_SYSTEM_PROMPT, PLANNER_TOOLS, Planner  # noqa: E402
from .types import (  # noqa: E402
    CommittedPlan,
    ComplexityTier,
    OrchestratorResult,
    PlanRequest,
    StepResult,
)

# ====================================================================
# Demo Scenarios
# ====================================================================

SCENARIOS = [
    {
        "name": "Multi-Domain HIGH (Weather + Recipes + Notes)",
        "input": (
            "Check the weather forecast for London this week, "
            "find me a good spaghetti recipe, and create a note "
            "with the meal plan and weather summary."
        ),
    },
    {
        "name": "Single-Domain LOW (Weather only)",
        "input": "What's the weather going to be like in Tokyo?",
    },
    {
        "name": "Multi-Step MEDIUM (Calendar + Date)",
        "input": "List my calendar events and calculate how many days until Christmas.",
    },
    {
        "name": "Two-Domain (Recipes + Calendar)",
        "input": "Find a chicken parmesan recipe and add a cooking event to my calendar for Saturday.",
    },
    {
        "name": "Meta-Agent Creation (build recipe+notes agent)",
        "input": (
            "Create a new agent called 'meal_planner' that can search for recipes "
            "and create notes. It should be in the FOOD and NOTES domains. "
            "Use the 'meal_planner_prompt' template."
        ),
    },
]


# ====================================================================
# Visual Pipeline Runner
# ====================================================================


class VisualPipelineRunner:
    """
    Runs the Concierge -> Planner -> Orchestrator -> Fabric pipeline
    with rich visual output for every internal operation.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        contracts_dir: str | Path = "k1/contracts/tools",
        fast: bool = False,
        verbose: bool = False,
        live: bool = False,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._contracts_dir = Path(contracts_dir)
        self._fast = fast
        self._verbose = verbose
        self._live = live

        # Stats
        self._stats: dict = {
            "llm_calls": 0,
            "classify_ms": 0,
            "plan_ms": 0,
            "fabric_ms": 0,
            "synthesis_ms": 0,
            "total_ms": 0,
            "steps_executed": 0,
            "steps_succeeded": 0,
            "steps_failed": 0,
            "capabilities_total": 0,
        }

    def _pause(self, label: str = "") -> None:
        """Tiny delay for dramatic effect (skipped in --fast mode)."""
        if not self._fast:
            time.sleep(0.3)

    async def run(self, user_input: str) -> dict:
        """
        Execute the full pipeline with rich visual output.

        Returns the pipeline result dict.
        """
        pipeline_start = time.monotonic()

        # -- Setup --
        from k1.fabric.factory import FabricFactory

        D.print_pipeline_header()
        self._pause()

        # Create components
        llm = SimpleLLMClient(api_key=self._api_key, model=self._model)
        concierge = Concierge(llm_client=llm)
        planner = Planner(llm_client=llm)

        # Wire Planner's discovery handler to the real Fabric registry
        discovery_handler = create_discovery_handler(self._contracts_dir)
        planner.set_discovery_handler(discovery_handler)

        # Build MCP transport: live servers or test stubs
        mcp_transport = None
        if self._live:
            from k1.fabric.adapters.live_mcp_transport import LiveMCPTransport

            mcp_transport = LiveMCPTransport()
            print(D.c(f"  {D.CHECK} Live MCP transport initialized (real servers)", D.GREEN))
        else:
            print(D.c(f"  {D.GEAR} Using test MCP transport (stub responses)", D.DIM))

        fabric_container = FabricFactory.create_for_testing(
            capture_events=True,
            contracts_dir="k1/contracts",
            mcp_transport=mcp_transport,
        )
        orchestrator = Orchestrator(fabric=fabric_container.facade)

        # Load capability catalog for stats only
        all_capabilities = load_capability_catalog(self._contracts_dir)
        self._stats["capabilities_total"] = len(all_capabilities)

        # ============================================================
        # PHASE 1: USER INPUT
        # ============================================================

        D.print_phase(1, "USER INPUT", D.ARROW_R)
        D.print_user_input(user_input)
        self._pause()

        # ============================================================
        # PHASE 2: CONCIERGE CLASSIFICATION (LLM Call #1)
        # ============================================================

        D.print_phase(2, "CONCIERGE CLASSIFICATION", D.LIGHTNING)

        D.print_llm_call_start(
            agent="Concierge",
            purpose="Classify intent, complexity, domains",
            model=self._model,
        )

        if self._verbose:
            D.print_system_prompt("Concierge", CLASSIFY_SYSTEM_PROMPT)
            D.print_user_message("Concierge", user_input)
            D.print_tool_definitions(CLASSIFY_TOOLS)

        classify_start = time.monotonic()
        envelope = await concierge.classify(user_input)
        classify_ms = int((time.monotonic() - classify_start) * 1000)
        self._stats["classify_ms"] = classify_ms
        self._stats["llm_calls"] += 1

        D.print_llm_call_end(
            latency_ms=classify_ms,
            tool_calls=1,
        )

        if self._verbose:
            D.print_llm_raw_response(
                tool_calls=[
                    {
                        "name": "classify_request",
                        "args": {
                            "tier": envelope.tier.value,
                            "intent": envelope.intent,
                            "domains": envelope.domains,
                        },
                    }
                ],
            )

        D.print_classification(
            tier=envelope.tier.value,
            intent=envelope.intent,
            domains=envelope.domains,
            latency_ms=classify_ms,
        )

        D.print_routing(envelope.tier.value)
        self._pause()

        # ============================================================
        # PHASE 3: AGENTIC PLANNER (Discovery + DAG Construction)
        # ============================================================
        # The Planner discovers capabilities on its own via multi-turn
        # function calling. No pre-loaded catalog is passed.

        plan: CommittedPlan | None = None
        orch_result: OrchestratorResult

        if envelope.tier in (ComplexityTier.HIGH, ComplexityTier.MEDIUM):
            D.print_phase(3, "AGENTIC PLANNER (DISCOVER + PLAN)", D.STAR)

            D.print_llm_call_start(
                agent="Planner (Agentic)",
                purpose=f"Discover capabilities + build DAG for '{envelope.intent}'",
                model=self._model,
            )

            if self._verbose:
                D.print_system_prompt("Planner", PLANNER_SYSTEM_PROMPT)
                planner_user_msg = (
                    f'The user said: "{user_input}"\n\n'
                    f"Their intent: {envelope.intent}\n"
                    f"Relevant domains: {', '.join(envelope.domains)}\n\n"
                    f"Discover capabilities for these domains, then build a plan."
                )
                D.print_user_message("Planner", planner_user_msg)
                D.print_tool_definitions(PLANNER_TOOLS)

            plan_request = PlanRequest(
                intent=envelope.intent,
                user_input=user_input,
                domains=envelope.domains,
                context=envelope.context,
                trace_id=envelope.trace_id,
            )

            # Track discovery calls for stats
            discovery_call_count = 0
            discovery_cap_count = 0

            def _on_tool_call(
                tool_name: str,
                args: dict,
                result: Any,
                turn: int,
            ) -> None:
                nonlocal discovery_call_count, discovery_cap_count
                D.print_agentic_tool_call(tool_name, args, result, turn)
                if self._verbose:
                    D.print_raw_tool_call(tool_name, args)
                    if result is not None:
                        D.print_raw_tool_result(tool_name, result)
                if tool_name == "discover_capabilities" and isinstance(result, dict):
                    discovery_call_count += 1
                    discovery_cap_count += result.get("capabilities_found", 0)

            plan_start = time.monotonic()
            plan = await planner.build_plan(
                plan_request,
                on_tool_call=_on_tool_call,
            )
            plan_ms = int((time.monotonic() - plan_start) * 1000)
            self._stats["plan_ms"] = plan_ms
            self._stats["llm_calls"] += 1
            self._stats["discovery_calls"] = discovery_call_count
            self._stats["discovery_caps"] = discovery_cap_count

            D.print_llm_call_end(
                latency_ms=plan_ms,
                tool_calls=(discovery_call_count + (1 if plan.steps else 0)),
            )

            if plan.steps:
                D.print_plan(
                    steps=plan.steps,
                    reasoning=plan.reasoning,
                    plan_id=plan.plan_id,
                    latency_ms=plan_ms,
                )
            else:
                print(D.c(f"  {D.WARNING} Planner produced empty plan", D.YELLOW))
                print()

            self._pause()

            # ============================================================
            # PHASE 4: FABRIC DAG EXECUTION (NO LLM -- Mechanical)
            # ============================================================

            D.print_phase(4, "FABRIC DAG EXECUTION", D.GEAR)

            if plan and plan.steps:
                D.print_fabric_start(len(plan.steps), "DAG")

                if self._verbose:
                    # Show each request detail before execution
                    for step in plan.steps:
                        D.print_fabric_request_detail(
                            step_id=step.step_id,
                            capability=step.capability_name,
                            params=step.params,
                            safety_band="AMBER",
                            trace_id=plan.trace_id,
                        )

                fabric_start = time.monotonic()
                orch_result = await orchestrator.execute_plan(plan)
                fabric_ms = int((time.monotonic() - fabric_start) * 1000)
                self._stats["fabric_ms"] = fabric_ms

                for sr in orch_result.step_results:
                    if self._verbose:
                        D.print_fabric_response_detail(
                            step_id=sr.step_id,
                            capability=sr.capability_name,
                            success=sr.success,
                            data=sr.data,
                            error=sr.error,
                            duration_ms=sr.duration_ms,
                        )
                    else:
                        D.print_fabric_step(
                            step_id=sr.step_id,
                            capability=sr.capability_name,
                            success=sr.success,
                            duration_ms=sr.duration_ms,
                            data=sr.data,
                            error=sr.error,
                        )

                self._stats["steps_executed"] = len(orch_result.step_results)
                self._stats["steps_succeeded"] = len(orch_result.successful_steps)
                self._stats["steps_failed"] = len(orch_result.failed_steps)

                D.print_fabric_end(
                    total_ms=orch_result.total_duration_ms,
                    success_count=len(orch_result.successful_steps),
                    fail_count=len(orch_result.failed_steps),
                )
            else:
                orch_result = OrchestratorResult(
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
                print(D.c(f"  {D.CROSS} No steps to execute", D.RED))
                print()

        else:
            # LOW tier -- direct execution with discovery
            D.print_phase(3, "DIRECT FABRIC EXECUTION (LOW TIER)", D.GEAR)

            # For LOW tier, do a quick discovery to find the best capability
            from .discovery import filter_capabilities_by_domain

            low_caps = filter_capabilities_by_domain(all_capabilities, envelope.domains)
            if not low_caps:
                low_caps = all_capabilities
            cap = low_caps[0] if low_caps else None
            if cap:
                D.print_fabric_start(1, "DIRECT")

                fabric_start = time.monotonic()
                orch_result = await orchestrator.execute_direct(
                    envelope=envelope,
                    capability_name=cap["name"],
                    params=envelope.context,
                )
                fabric_ms = int((time.monotonic() - fabric_start) * 1000)
                self._stats["fabric_ms"] = fabric_ms
                self._stats["steps_executed"] = 1
                self._stats["steps_succeeded"] = 1 if orch_result.success else 0
                self._stats["steps_failed"] = 0 if orch_result.success else 1

                for sr in orch_result.step_results:
                    D.print_fabric_step(
                        step_id=sr.step_id,
                        capability=sr.capability_name,
                        success=sr.success,
                        duration_ms=sr.duration_ms,
                        data=sr.data,
                        error=sr.error,
                    )

                D.print_fabric_end(
                    total_ms=orch_result.total_duration_ms,
                    success_count=self._stats["steps_succeeded"],
                    fail_count=self._stats["steps_failed"],
                )
            else:
                orch_result = OrchestratorResult(
                    success=False,
                    step_results=[],
                    trace_id=envelope.trace_id,
                )
                print(D.c(f"  {D.CROSS} No capabilities found", D.RED))
                print()

        self._pause()

        # ============================================================
        # PHASE 5: RESPONSE SYNTHESIS (LLM Call)
        # ============================================================

        D.print_phase(5, "RESPONSE SYNTHESIS", D.BRAIN)

        D.print_llm_call_start(
            agent="Concierge (Synthesizer)",
            purpose="Generate natural language response from tool results",
            model=self._model,
        )

        step_dicts = [
            {
                "capability": sr.capability_name,
                "success": sr.success,
                "data": sr.data,
                "error": sr.error,
                "description": sr.step_id,
            }
            for sr in orch_result.step_results
        ]

        if self._verbose:
            D.print_system_prompt("Synthesizer", RESPONSE_SYSTEM_PROMPT)
            D.print_synthesis_context(user_input, step_dicts)

        synth_start = time.monotonic()
        response = await concierge.synthesize_response(
            user_input=user_input,
            step_results=step_dicts,
        )
        synth_ms = int((time.monotonic() - synth_start) * 1000)
        self._stats["synthesis_ms"] = synth_ms
        self._stats["llm_calls"] += 1

        D.print_llm_call_end(
            latency_ms=synth_ms,
            text_length=len(response),
        )

        if self._verbose:
            D.print_llm_raw_response(content=response)

        D.print_response(response)
        self._pause()

        # ============================================================
        # FINAL: STATS
        # ============================================================

        self._stats["total_ms"] = int((time.monotonic() - pipeline_start) * 1000)

        D.print_divider(D.HZ_D, D.CYAN)
        print()
        D.print_stats(self._stats)
        D.print_pipeline_complete(success=orch_result.success)

        return {
            "user_input": user_input,
            "envelope": {
                "tier": envelope.tier.value,
                "intent": envelope.intent,
                "domains": envelope.domains,
            },
            "plan": {
                "plan_id": plan.plan_id if plan else None,
                "steps": len(plan.steps) if plan else 0,
                "reasoning": plan.reasoning if plan else None,
            },
            "orchestrator_result": {
                "success": orch_result.success,
                "total_duration_ms": orch_result.total_duration_ms,
                "steps": [
                    {
                        "step_id": sr.step_id,
                        "capability": sr.capability_name,
                        "success": sr.success,
                        "duration_ms": sr.duration_ms,
                    }
                    for sr in orch_result.step_results
                ],
            },
            "response": response,
            "stats": dict(self._stats),
        }


# ====================================================================
# Main
# ====================================================================


async def main() -> None:
    """Entry point for the visual runner."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_API_KEY not set.")
        print("Set it in your environment or in poc/chat_experience_poc/.env")
        sys.exit(1)

    # Parse args
    auto = "--auto" in sys.argv
    fast = "--fast" in sys.argv
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    live = "--live" in sys.argv

    runner = VisualPipelineRunner(
        api_key=api_key,
        fast=fast,
        verbose=verbose,
        live=live,
    )

    if auto:
        user_input = SCENARIOS[0]["input"]
    else:
        D.setup_unicode_console()
        print()
        print(D.c(D.TL_D + D.HZ_D * D.W + D.TR_D, D.CYAN, bold=True))
        print(
            D._box_line(
                D.c(f"  {D.NETWORK} CONCIERGE-PLANNER-ORCHESTRATOR POC", D.CYAN, bold=True), D.CYAN
            )
        )
        print(D.c(D.BL_D + D.HZ_D * D.W + D.BR_D, D.CYAN, bold=True))

        idx = D.print_scenario_menu(SCENARIOS)
        if idx >= 0:
            user_input = SCENARIOS[idx]["input"]
        else:
            user_input = input(D.c(f"\n  {D.ARROW_R} Enter your request: ", D.CYAN)).strip()
            if not user_input:
                user_input = SCENARIOS[0]["input"]

    await runner.run(user_input)


def run() -> None:
    """Sync entry point."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
