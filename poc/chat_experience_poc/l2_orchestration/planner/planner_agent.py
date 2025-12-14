"""
Planner Agent - 4-Stage Planning Pipeline

ADR: 0007 - 4-Stage Planning Pipeline (Sketch → Expand → Validate → Commit)
Location: docs/architecture/decisions/03-layer2-orchestration/0007-4stage-planning-pipeline/0007.md

Performance Budgets (from ADR-0007):
- Stage 1 (Sketch): <500ms P95 (LLM inference)
- Stage 2 (Expand): <1ms P95 (deterministic lookup)
- Stage 3 (Validate): <10ms P95 (rule-based checks)
- Stage 4 (Commit): <10ms P95 (serialization + mock K0 write)
- Total: <600ms P95

Architecture:
- Pure Actor (uses mailbox for task assignment from Orchestrator Phase 2)
- AI Agent (uses LLM only in Stage 1 Sketch)
- Tier 2 Agent (spawned on-demand by Orchestrator, not always-active)
"""

import asyncio
import hashlib
import json
import time
from datetime import datetime
from time import perf_counter
from typing import Any, Dict, List, Optional, Set

from config import groq_config
from groq import AsyncGroq
from l3_execution.agents.agent_base import AgentState
from l4_runtime.deltabus.deltabus import DeltaBusEvent, get_deltabus

from .data_models import (
    CommittedPlan,
    ExpandedPlan,
    PlanComplexity,
    PlanStep,
    SketchPlan,
    StepOp,
    ValidatedPlan,
    ValidationResult,
    ValidationStatus,
)


class PlannerAgent:
    """
    4-Stage Planning Pipeline

    Receives TaskAssignment from Orchestrator Phase 2, decomposes into multi-step plan.

    Stages:
    1. Sketch: LLM generates high-level plan structure (~50ms)
    2. Expand: Deterministic tool resolution (<1ms)
    3. Validate: Safety/privacy/budget checks (<10ms)
    4. Commit: Serialize and persist to Mock K0 WAL (<5ms)

    Returns CommittedPlan to Orchestrator Phase 3 for execution via DAG Executor.
    """

    def __init__(
        self,
        agent_id: str,
        groq_client: AsyncGroq,
        tool_registry: Dict[str, Dict[str, Any]],
        agent_registry: Dict[str, Dict[str, Any]],
        session_state: Any,  # SessionState from l4_runtime
        mailbox: Optional[Any] = None,  # Mailbox from AgentFabric (Issue 1.2.2)
        batch_client: Optional[Any] = None,  # BatchClient for K0 WAL operations (Issue 2.4.1)
        mock_command_port: Optional[
            Any
        ] = None,  # MockCommandPort for K0 HTTP interface (Issue 2.4.1)
        session_state_manager: Optional[Any] = None,  # Epic 3.1 Issue 3.1.1
    ):
        """
        Initialize Planner Agent

        Args:
            agent_id: Unique agent identifier
            groq_client: AsyncGroq client for LLM calls
            tool_registry: Tool specifications (name → schema)
            agent_registry: Agent capabilities (agent_type → tools)
            session_state: Session context for user preferences
            mailbox: Mailbox from AgentFabric (Issue 1.2.2)
            batch_client: BatchClient for K0 WAL batch operations (Issue 2.4.1)
            mock_command_port: MockCommandPort for K0 HTTP interface (Issue 2.4.1)
            session_state_manager: SessionStateManager for delta-based updates (Epic 3.1)
        """
        self.agent_id = agent_id
        self.groq_client = groq_client
        self.tool_registry = tool_registry
        self.agent_registry = agent_registry
        self.session_state = session_state
        self.mailbox = mailbox
        self.batch_client = batch_client
        self.mock_command_port = mock_command_port
        self.session_state_manager = session_state_manager  # Epic 3.1 Issue 3.1.1
        self.deltabus = get_deltabus()

        # Configuration (from ADR-0007 config section)
        self.sketch_model = groq_config.DEFAULT_MODEL  # Configurable via GROQ_MODEL env var
        self.sketch_temperature = 0.3  # Low temp for consistency
        self.sketch_max_tokens = 800
        self.sketch_timeout_ms = 500  # 500ms budget

        # Validation limits (from ADR-0007c)
        self.max_steps = 12  # Max plan complexity
        self.max_latency_ms = 5000  # 5 second execution limit
        self.max_cost = 1.0  # $1.00 max cost

    async def run(self) -> None:
        """
        Main planner run loop - consumes plan requests from mailbox

        Mailbox-driven planning following AgentFabric lifecycle.
        Processes plan requests from mailbox and executes 4-stage pipeline.

        Lifecycle: WARMING → ACTIVE → IDLE → DRAINING → TERMINATED
        """
        print(f"[Planner] run() started for agent_id={self.agent_id}")

        try:
            while True:
                # Check if mailbox still exists (planner not terminated)
                if not self.mailbox:
                    print("[Planner] Mailbox closed, exiting run() loop")
                    break

                # Receive message from planner mailbox (blocking)
                message = await self.mailbox.receive()

                if message is None:
                    # Mailbox closed or drained
                    print("[Planner] Mailbox drained, exiting run() loop")
                    break

                # Publish agent.task_received event
                await self._publish_agent_event(
                    event_type="agent.task_received",
                    agent_id=self.agent_id,
                    state=AgentState.ACTIVE,
                    task_id=message.message_id,
                    trace_id=message.payload.get("trace_id", "unknown"),
                    session_id=message.payload.get("session_id", "default"),
                )

                print(
                    f"[Planner] Message received: message_id={message.message_id}, "
                    f"priority={message.priority.name if hasattr(message, 'priority') else 'UNKNOWN'}"
                )

                # Process plan request
                try:
                    committed_plan = await self._process_plan_request(message.payload)

                    # Publish response to DeltaBus for await_response()
                    response_event = DeltaBusEvent(
                        event_type=f"response.{message.message_id}",
                        session_id=message.payload.get("session_id", "default"),
                        payload={
                            "message_id": message.message_id,
                            "status": "success",
                            "plan_id": committed_plan.plan_id,
                            "plan": {
                                "intent": committed_plan.intent,
                                "steps": [
                                    {
                                        "step_id": s.step_id,
                                        "op": s.op.value,
                                        "description": s.description,
                                        "agent_id": s.agent_id,
                                        "tool_name": s.tool_name,
                                        "estimated_latency_ms": s.estimated_latency_ms,
                                    }
                                    for s in committed_plan.steps
                                ],
                                "complexity": committed_plan.complexity.value,
                                "estimated_duration_ms": committed_plan.estimated_duration_ms,
                                "estimated_cost": committed_plan.estimated_cost,
                            },
                            "trace_id": message.payload.get("trace_id"),
                        },
                        timestamp=datetime.utcnow(),
                        trace_id=message.payload.get("trace_id", "unknown"),
                    )
                    self.deltabus.publish(response_event)

                    # Publish agent.task_completed event
                    await self._publish_agent_event(
                        event_type="agent.task_completed",
                        agent_id=self.agent_id,
                        state=AgentState.ACTIVE,
                        task_id=message.message_id,
                        trace_id=message.payload.get("trace_id", "unknown"),
                        session_id=message.payload.get("session_id", "default"),
                        result_status="success",
                        latency_ms=int(committed_plan.latency_ms),
                    )

                    print(
                        f"[Planner] Task completed: plan_id={committed_plan.plan_id}, "
                        f"steps={len(committed_plan.steps)}"
                    )

                except Exception as e:
                    print(f"[Planner] Task error: {e}")

                    # Publish error response
                    error_event = DeltaBusEvent(
                        event_type=f"response.{message.message_id}",
                        session_id=message.payload.get("session_id", "default"),
                        payload={
                            "message_id": message.message_id,
                            "status": "error",
                            "error": str(e),
                            "trace_id": message.payload.get("trace_id"),
                        },
                        timestamp=datetime.utcnow(),
                        trace_id=message.payload.get("trace_id", "unknown"),
                    )
                    self.deltabus.publish(error_event)

                    # Publish agent.task_completed with error
                    await self._publish_agent_event(
                        event_type="agent.task_completed",
                        agent_id=self.agent_id,
                        state=AgentState.ACTIVE,
                        task_id=message.message_id,
                        trace_id=message.payload.get("trace_id", "unknown"),
                        session_id=message.payload.get("session_id", "default"),
                        result_status="error",
                        error=str(e),
                    )

        except asyncio.CancelledError:
            print("[Planner] run() cancelled")
            raise
        except Exception as e:
            print(f"[Planner] run() error: {e}")
            raise

    async def _publish_agent_event(
        self,
        event_type: str,
        agent_id: str,
        state: AgentState,
        task_id: str,
        trace_id: str,
        session_id: str = "default",
        result_status: Optional[str] = None,
        latency_ms: Optional[int] = None,
        error: Optional[str] = None,
    ) -> None:
        """
        Publish agent lifecycle event to DeltaBus

        Args:
            event_type: Event type (agent.task_received, agent.task_completed)
            agent_id: Agent identifier
            state: Current agent state
            task_id: Task identifier
            trace_id: Cognitive trace ID
            session_id: Session identifier
            result_status: Task result status (for task_completed)
            latency_ms: Task latency (for task_completed)
            error: Error message (for task_completed with error)
        """
        event = DeltaBusEvent(
            event_type=event_type,
            session_id=session_id,
            payload={
                "agent_id": agent_id,
                "agent_type": "planner",
                "state": state.value,
                "task_id": task_id,
                "trace_id": trace_id,
                "timestamp": time.time(),
            },
            timestamp=datetime.utcnow(),
            trace_id=trace_id,
        )

        # Add optional fields for task_completed
        if result_status:
            event.payload["result_status"] = result_status
        if latency_ms:
            event.payload["latency_ms"] = latency_ms
        if error:
            event.payload["error"] = error

        self.deltabus.publish(event)

    async def _process_plan_request(self, request_payload: Dict[str, Any]) -> CommittedPlan:
        """
        Process plan request from mailbox message

        Wraps plan_task() for mailbox-driven invocation.

        Args:
            request_payload: Plan request payload from mailbox message

        Returns:
            CommittedPlan with plan details
        """
        return await self.plan_task(
            user_input=request_payload.get("user_input", ""),
            task_type=request_payload.get("task_type", "PLANNING"),
            required_tools=request_payload.get("required_tools", []),
            budget=request_payload.get("budget", {}),
            user_context=request_payload.get("user_context", {}),
            trace_id=request_payload.get("trace_id", "unknown"),
        )

    async def plan_task(
        self,
        user_input: str,
        task_type: str,
        required_tools: List[str],
        budget: Dict[str, Any],
        user_context: Dict[str, Any],
        trace_id: str,
    ) -> CommittedPlan:
        """
        Main entry point: 4-stage planning pipeline

        Args:
            user_input: User's task description
            task_type: QUERY/PLANNING/TOOL_EXECUTION
            required_tools: Tools needed (from Orchestrator Phase 1)
            budget: Time/cost constraints
            user_context: User preferences from User KG
            trace_id: Tracing correlation ID

        Returns:
            CommittedPlan ready for Orchestrator Phase 3 execution

        Raises:
            SketchError: Stage 1 failed (LLM error, invalid JSON)
            ExpansionError: Stage 2 failed (unknown tool)
            ValidationError: Stage 3 failed (budget/safety violations)
            CommitError: Stage 4 failed (K0 WAL write error)
        """
        pipeline_start = perf_counter()

        print(f"\\n[Planner] Starting 4-stage pipeline for: {user_input[:50]}...")
        print(f"[Planner] trace_id={trace_id}")

        # Stage 1: Sketch (LLM-based high-level planning)
        sketch = await self._stage1_sketch(
            user_input=user_input,
            required_tools=required_tools,
            user_context=user_context,
            trace_id=trace_id,
        )
        print(f"[Planner] ✅ Stage 1 Sketch: {len(sketch.steps)} steps, {sketch.latency_ms:.1f}ms")

        # Stage 2: Expand (Deterministic tool resolution)
        expanded = await self._stage2_expand(sketch, trace_id)
        print(
            f"[Planner] ✅ Stage 2 Expand: {len(expanded.steps)} steps, {expanded.latency_ms:.1f}ms"
        )

        # Stage 3: Validate (Safety/budget checks)
        validated = await self._stage3_validate(expanded, budget, trace_id)
        print(f"[Planner] ✅ Stage 3 Validate: {validated.status}, {validated.latency_ms:.1f}ms")

        if validated.status == ValidationStatus.FAILED:
            failed_checks = [v.message for v in validated.validation_results if not v.passed]
            raise ValidationError(f"Plan validation failed: {'; '.join(failed_checks)}")

        # Stage 4: Commit (Serialize and persist)
        committed = await self._stage4_commit(validated, trace_id)
        print(
            f"[Planner] ✅ Stage 4 Commit: plan_id={committed.plan_id}, {committed.latency_ms:.1f}ms"
        )

        pipeline_latency = (perf_counter() - pipeline_start) * 1000
        print(f"[Planner] Pipeline complete: {pipeline_latency:.1f}ms total")

        return committed

    # ========== STAGE 1: SKETCH (LLM-Based High-Level Planning) ==========

    async def _stage1_sketch(
        self,
        user_input: str,
        required_tools: List[str],
        user_context: Dict[str, Any],
        trace_id: str,
    ) -> SketchPlan:
        """
        Stage 1: LLM generates high-level plan structure

        Budget: <500ms P95 (LLM inference TTFT + E2E)

        Based on ADR-0007a Sketch Stage
        Contract: k1/contracts/planning/pipeline/sketch_stage.yml

        Returns: SketchPlan with steps, intent, complexity
        """
        start_time = perf_counter()

        # Build prompt with few-shot examples
        prompt = self._build_sketch_prompt(user_input, required_tools, user_context)

        try:
            # Call LLM with timeout
            response = await asyncio.wait_for(
                self.groq_client.chat.completions.create(
                    model=self.sketch_model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a planning agent that creates structured task plans.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=self.sketch_temperature,
                    max_tokens=self.sketch_max_tokens,
                    response_format={"type": "json_object"},  # Force JSON mode
                ),
                timeout=self.sketch_timeout_ms / 1000,
            )

            # Parse JSON output
            sketch_json = json.loads(response.choices[0].message.content)

            # Validate structure
            self._validate_sketch_structure(sketch_json)

            # Convert to SketchPlan
            steps = []
            for step_data in sketch_json["steps"]:
                step = PlanStep(
                    step_id=step_data["id"],
                    op=StepOp(step_data["op"]),
                    description=step_data["description"],
                    needs=step_data.get("needs", []),
                    tool_name=step_data.get("tool"),  # May be present in sketch
                )
                steps.append(step)

            latency_ms = (perf_counter() - start_time) * 1000

            return SketchPlan(
                intent=sketch_json["intent"],
                steps=steps,
                complexity=PlanComplexity(sketch_json.get("complexity", "medium")),
                raw_output=response.choices[0].message.content,
                latency_ms=latency_ms,
                trace_id=trace_id,
            )

        except asyncio.TimeoutError:
            raise SketchError(f"Sketch timeout after {self.sketch_timeout_ms}ms")
        except json.JSONDecodeError as e:
            raise SketchError(f"Invalid JSON from LLM: {e}")
        except Exception as e:
            raise SketchError(f"Sketch failed: {e}")

    def _build_sketch_prompt(
        self,
        user_input: str,
        required_tools: List[str],
        user_context: Dict[str, Any],
    ) -> str:
        """
        Build Sketch prompt with few-shot examples

        Based on ADR-0007a prompt template
        """
        tool_list = "\\n".join([f"- {tool}" for tool in required_tools])

        return f"""
You are a task planning assistant.

Your job: Convert user requests into structured task plans.

Output format (JSON only):
{{
  "intent": "brief_intent_label",
  "steps": [
    {{
      "id": "unique_step_id",
      "op": "Tool|Model|Ask",
      "description": "what this step does",
      "tool": "tool_name (if op=Tool)",
      "needs": ["step_ids this depends on"]
    }}
  ],
  "complexity": "simple|medium|complex"
}}

Available tools:
{tool_list}

User context:
{json.dumps(user_context, indent=2)}

User request: "{user_input}"

Think step-by-step, then output valid JSON.
"""

    def _validate_sketch_structure(self, sketch_json: Dict[str, Any]) -> None:
        """
        Validate sketch JSON structure

        Checks:
        - Required fields present (intent, steps)
        - Steps is array
        - Each step has id, op, description
        """
        if "intent" not in sketch_json:
            raise SketchError("Missing 'intent' field")

        if "steps" not in sketch_json or not isinstance(sketch_json["steps"], list):
            raise SketchError("Missing or invalid 'steps' field")

        for step in sketch_json["steps"]:
            if "id" not in step:
                raise SketchError(f"Step missing 'id': {step}")
            if "op" not in step:
                raise SketchError(f"Step missing 'op': {step}")
            if step["op"] not in ["Tool", "Model", "Ask"]:
                raise SketchError(f"Invalid op: {step['op']}")

    # ========== STAGE 2: EXPAND (Deterministic Tool Resolution) ==========

    async def _stage2_expand(
        self,
        sketch: SketchPlan,
        trace_id: str,
    ) -> ExpandedPlan:
        """
        Stage 2: Fill in tool schemas and agent assignments (deterministic)

        Budget: <1ms P95 (pure dictionary lookup, no LLM)

        Based on ADR-0007b Expand Stage
        Contract: k1/contracts/planning/pipeline/expand_stage.yml

        Returns: ExpandedPlan with tool/agent details filled
        """
        start_time = perf_counter()

        expanded_steps = []

        for step in sketch.steps:
            # Copy basic fields
            expanded_step = PlanStep(
                step_id=step.step_id,
                op=step.op,
                description=step.description,
                needs=step.needs,
                tool_name=step.tool_name,
            )

            # If Tool operation, lookup tool schema and assign agent
            if step.op == StepOp.TOOL and step.tool_name:
                tool_spec = self.tool_registry.get(step.tool_name)
                if tool_spec:
                    # Fill in estimates from tool registry
                    expanded_step.estimated_latency_ms = tool_spec.get("latency_ms", 100)
                    expanded_step.estimated_cost = tool_spec.get("cost", 0.01)

                    # Assign agent (find agent with this tool capability)
                    expanded_step.agent_id = self._assign_agent_for_tool(step.tool_name)
                else:
                    # Tool not found - mark as invalid (will fail validation)
                    expanded_step.is_valid = False
                    expanded_step.validation_errors.append(f"Unknown tool: {step.tool_name}")

            expanded_steps.append(expanded_step)

        latency_ms = (perf_counter() - start_time) * 1000

        return ExpandedPlan(
            intent=sketch.intent,
            steps=expanded_steps,
            complexity=sketch.complexity,
            latency_ms=latency_ms,
            trace_id=trace_id,
        )

    def _assign_agent_for_tool(self, tool_name: str) -> Optional[str]:
        """
        Find best agent to execute tool

        Based on ADR-0007b agent capability matching
        """
        # Find agent with this tool capability
        for agent_type, agent_spec in self.agent_registry.items():
            if tool_name in agent_spec.get("tools", []):
                return agent_type

        return None  # No agent found (will fail validation)

    # ========== STAGE 3: VALIDATE (Safety/Budget Checks) ==========

    async def _stage3_validate(
        self,
        expanded: ExpandedPlan,
        budget: Dict[str, Any],
        trace_id: str,
    ) -> ValidatedPlan:
        """
        Stage 3: Rule-based validation (Tier 1 only for POC)

        Budget: <10ms P95 (deterministic rule checks)

        Based on ADR-0007c Validation Stage
        Contract: k1/contracts/planning/pipeline/validation_stage.yml

        Tier 1 Checks:
        - Step count within limits (≤12 steps)
        - Total latency within budget
        - Total cost within budget
        - All tools resolved (no unknown tools)
        - No circular dependencies

        Tier 2 (Arbiter): Not implemented in POC (would escalate AMBER/RED plans)

        Returns: ValidatedPlan with status and validation results
        """
        start_time = perf_counter()

        validation_results: List[ValidationResult] = []
        requires_arbiter = False

        # Check 1: Step count limit
        if len(expanded.steps) > self.max_steps:
            validation_results.append(
                ValidationResult(
                    check_name="step_count",
                    passed=False,
                    severity="ERROR",
                    message=f"Plan has {len(expanded.steps)} steps (max {self.max_steps})",
                )
            )
        else:
            validation_results.append(
                ValidationResult(
                    check_name="step_count",
                    passed=True,
                    severity="INFO",
                    message=f"Step count OK: {len(expanded.steps)}/{self.max_steps}",
                )
            )

        # Check 2: Total latency budget
        total_latency = sum(s.estimated_latency_ms for s in expanded.steps)
        if total_latency > self.max_latency_ms:
            validation_results.append(
                ValidationResult(
                    check_name="latency_budget",
                    passed=False,
                    severity="ERROR",
                    message=f"Plan latency {total_latency}ms exceeds budget {self.max_latency_ms}ms",
                )
            )
        else:
            validation_results.append(
                ValidationResult(
                    check_name="latency_budget",
                    passed=True,
                    severity="INFO",
                    message=f"Latency OK: {total_latency}ms/{self.max_latency_ms}ms",
                )
            )

        # Check 3: Total cost budget
        total_cost = sum(s.estimated_cost for s in expanded.steps)
        if total_cost > self.max_cost:
            validation_results.append(
                ValidationResult(
                    check_name="cost_budget",
                    passed=False,
                    severity="ERROR",
                    message=f"Plan cost ${total_cost:.2f} exceeds budget ${self.max_cost:.2f}",
                )
            )
        else:
            validation_results.append(
                ValidationResult(
                    check_name="cost_budget",
                    passed=True,
                    severity="INFO",
                    message=f"Cost OK: ${total_cost:.2f}/${self.max_cost:.2f}",
                )
            )

        # Check 4: All tools resolved
        unresolved_tools = [s for s in expanded.steps if not s.is_valid]
        if unresolved_tools:
            validation_results.append(
                ValidationResult(
                    check_name="tool_resolution",
                    passed=False,
                    severity="ERROR",
                    message=f"{len(unresolved_tools)} steps have unresolved tools",
                    details={"unresolved": [s.step_id for s in unresolved_tools]},
                )
            )
        else:
            validation_results.append(
                ValidationResult(
                    check_name="tool_resolution",
                    passed=True,
                    severity="INFO",
                    message="All tools resolved",
                )
            )

        # Check 5: No circular dependencies (simple check)
        if self._has_circular_dependencies(expanded.steps):
            validation_results.append(
                ValidationResult(
                    check_name="circular_dependencies",
                    passed=False,
                    severity="ERROR",
                    message="Plan contains circular dependencies",
                )
            )
        else:
            validation_results.append(
                ValidationResult(
                    check_name="circular_dependencies",
                    passed=True,
                    severity="INFO",
                    message="No circular dependencies",
                )
            )

        # Determine overall status
        has_errors = any(not v.passed and v.severity == "ERROR" for v in validation_results)
        if has_errors:
            status = ValidationStatus.FAILED
        else:
            status = ValidationStatus.PASSED

        latency_ms = (perf_counter() - start_time) * 1000

        return ValidatedPlan(
            intent=expanded.intent,
            steps=expanded.steps,
            complexity=expanded.complexity,
            status=status,
            validation_results=validation_results,
            latency_ms=latency_ms,
            requires_arbiter=requires_arbiter,
            trace_id=trace_id,
        )

    def _has_circular_dependencies(self, steps: List[PlanStep]) -> bool:
        """
        Check for circular dependencies using DFS

        Based on ADR-0007c cycle detection
        """
        # Build adjacency list
        graph: Dict[str, Set[str]] = {step.step_id: set(step.needs) for step in steps}

        # DFS to detect cycles
        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)

            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True

            rec_stack.remove(node)
            return False

        for step_id in graph.keys():
            if step_id not in visited:
                if has_cycle(step_id):
                    return True

        return False

    # ========== STAGE 4: COMMIT (Serialize and Persist) ==========

    async def _stage4_commit(
        self,
        validated: ValidatedPlan,
        trace_id: str,
    ) -> CommittedPlan:
        """
        Stage 4: Serialize plan and persist to Mock K0 WAL

        Budget: <10ms P95 (JSON serialization + mock K0 write)

        Based on ADR-0007d Commit Stage
        Contract: k1/contracts/planning/pipeline/commit_stage.yml

        Returns: CommittedPlan with plan_id and persistence confirmation
        """
        start_time = perf_counter()

        # Generate plan ID
        plan_id = f"plan_{trace_id}_{int(datetime.now().timestamp())}"

        # Serialize to JSON
        plan_dict = {
            "intent": validated.intent,
            "complexity": validated.complexity.value,
            "steps": [
                {
                    "step_id": s.step_id,
                    "op": s.op.value,
                    "description": s.description,
                    "needs": s.needs,
                    "tool_name": s.tool_name,
                    "agent_id": s.agent_id,
                    "estimated_latency_ms": s.estimated_latency_ms,
                    "estimated_cost": s.estimated_cost,
                }
                for s in validated.steps
            ],
        }
        serialized_json = json.dumps(plan_dict, indent=2)

        # Compute hash for integrity
        plan_hash = hashlib.sha256(serialized_json.encode()).hexdigest()

        # Commit plan to K0 WAL (Issue 2.4.1: Use real K0 interface)
        receipt_id = None
        if self.batch_client:
            # Option 1: Use BatchClient for K0 batch operations
            try:
                batch_response = await self.batch_client.submit_batch(
                    batch_type="plan_commit",
                    payload=plan_dict,
                    trace_id=trace_id,
                )
                receipt_id = batch_response.get("receipt_id", f"receipt_{plan_id}")
                print(f"[Planner] Plan committed via BatchClient: receipt_id={receipt_id}")
            except Exception as e:
                print(f"[Planner] WARNING: BatchClient commit failed: {e}")
                receipt_id = f"receipt_{plan_id}_fallback"
        elif self.mock_command_port:
            # Option 2: Use MockCommandPort HTTP interface
            try:
                import aiohttp

                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.mock_command_port}/api/wal/commit",
                        json={
                            "operation": "plan_commit",
                            "plan_id": plan_id,
                            "plan": plan_dict,
                            "trace_id": trace_id,
                        },
                        timeout=aiohttp.ClientTimeout(total=0.01),  # 10ms timeout
                    ) as response:
                        response_data = await response.json()
                        receipt_id = response_data.get("receipt_id", f"receipt_{plan_id}")
                        print(
                            f"[Planner] Plan committed via MockCommandPort: receipt_id={receipt_id}"
                        )
            except Exception as e:
                print(f"[Planner] WARNING: MockCommandPort commit failed: {e}")
                receipt_id = f"receipt_{plan_id}_fallback"
        else:
            # Fallback: Simulate write (POC mode)
            await asyncio.sleep(0.005)  # 5ms simulated write
            receipt_id = f"receipt_{plan_id}_simulated"
            print(f"[Planner] Plan committed (simulated): receipt_id={receipt_id}")

        latency_ms = (perf_counter() - start_time) * 1000

        # Calculate total estimates
        total_duration = sum(s.estimated_latency_ms for s in validated.steps)
        total_cost = sum(s.estimated_cost for s in validated.steps)

        # Create CommittedPlan
        committed_plan = CommittedPlan(
            plan_id=plan_id,
            intent=validated.intent,
            steps=validated.steps,
            complexity=validated.complexity,
            serialized_json=serialized_json,
            plan_hash=plan_hash,
            committed_at=datetime.now().isoformat(),
            latency_ms=latency_ms,
            trace_id=trace_id,
            estimated_duration_ms=total_duration,
            estimated_cost=total_cost,
        )

        # Publish orchestration.plan.committed event (Issue 2.4.1)
        plan_committed_event = DeltaBusEvent(
            event_type="orchestration.plan.committed",
            session_id="default",  # TODO: Extract from context
            payload={
                "plan_id": plan_id,
                "receipt_id": receipt_id,
                "trace_id": trace_id,
                "complexity": validated.complexity.value,
                "step_count": len(validated.steps),
                "estimated_duration_ms": total_duration,
                "estimated_cost": total_cost,
                "committed_at": committed_plan.committed_at,
                "plan_hash": plan_hash,
            },
            timestamp=datetime.utcnow(),
            trace_id=trace_id,
        )
        self.deltabus.publish(plan_committed_event)

        print(f"[Planner] Published orchestration.plan.committed event: plan_id={plan_id}")

        return committed_plan


# ========== EXCEPTIONS ==========


class SketchError(Exception):
    """Stage 1 Sketch failed"""

    pass


class ExpansionError(Exception):
    """Stage 2 Expand failed"""

    pass


class ValidationError(Exception):
    """Stage 3 Validate failed"""

    pass


class CommitError(Exception):
    """Stage 4 Commit failed"""

    pass
