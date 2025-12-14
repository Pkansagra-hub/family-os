"""
DAG Executor - Parallel Wave Execution with Barriers and Saga Pattern

ADR-0006c: Parallel DAG Execution (Wave computation with topological sort)
ADR-0008: Saga Pattern Error Recovery (LIFO compensation on failure)

Performance Budgets:
- DAG parsing: <10ms
- Wave computation: <5ms (topological sort)
- Step execution: Variable (depends on agent/tool latency)
- Compensation: <3s per step
- Max concurrent tasks: 3 per wave (semaphore limit)
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from time import perf_counter
from typing import Any, Dict, List, Optional

import networkx as nx
from l2_orchestration.planner.data_models import CommittedPlan, PlanStep, StepOp
from l3_execution.agents.agent_base import AgentState
from l4_runtime.deltabus.deltabus import DeltaBusEvent, get_deltabus

# ========== DATA MODELS ==========


@dataclass
class StepResult:
    """
    Result of executing a single step

    Used by wave execution to track step outcomes
    """

    step_id: str
    status: str  # "success", "failure", "timeout"
    output_data: Dict[str, Any] = field(default_factory=dict)  # Step outputs
    agent_id: str = ""  # Agent that executed step
    latency_ms: int = 0  # Step execution time
    receipts: List[Dict[str, Any]] = field(default_factory=list)  # Tool call receipts
    error: str = ""  # Error message if failure


@dataclass
class CompensationResult:
    """
    Result of Saga Pattern compensation

    Tracks compensated steps and errors during rollback
    """

    compensated_steps: List[str]  # Step IDs that were compensated
    compensation_errors: List[str]  # Errors during compensation
    total_latency_ms: int  # Time taken for full compensation
    user_message: str = ""  # User-facing error message


# ========== EXCEPTIONS ==========


class ExecutionError(Exception):
    """Base exception for DAG execution errors"""

    pass


class CyclicDependencyError(ExecutionError):
    """Raised when DAG has circular dependencies"""

    pass


class StepExecutionError(ExecutionError):
    """Raised when step execution fails"""

    pass


class CompensationError(ExecutionError):
    """Raised when compensation fails"""

    pass


# ========== DAG EXECUTOR ==========


class DAGExecutor:
    """
    DAG Executor - Parallel Wave Execution with Barriers

    Implements Epic 6.3: DAG Executor (Parallel Wave Execution)

    Flow:
    1. Parse committed plan → DAG (nodes=steps, edges=dependencies)
    2. Compute waves via topological sort (Kahn's algorithm)
    3. Execute waves in parallel with barriers (asyncio.gather)
    4. On critical failure: trigger Saga Pattern compensation (LIFO)

    Performance:
    - DAG parsing: <10ms
    - Wave computation: <5ms
    - Max concurrent: 3 tasks per wave
    - Compensation: <3s per step
    """

    def __init__(
        self,
        agent_registry: Dict[str, Dict[str, Any]],
        tool_registry: Dict[str, Dict[str, Any]],
        max_concurrent: int = 3,
        mailbox: Optional[Any] = None,
        agent_fabric: Optional[Any] = None,
        agent_id: str = "dag_executor",
        session_state_manager: Optional[Any] = None,  # Epic 3.1 Issue 3.1.1
    ):
        """
        Initialize DAG Executor

        Args:
            agent_registry: Registry of available agents
            tool_registry: Registry of available tools
            max_concurrent: Max concurrent tasks per wave (default 3)
            mailbox: Mailbox for mailbox-driven execution (optional)
            agent_fabric: AgentFabric for spawning/reusing agents (optional)
            agent_id: Executor agent ID (default: "dag_executor")
            session_state_manager: SessionStateManager for delta-based updates (Epic 3.1)
        """
        self.agent_registry = agent_registry
        self.tool_registry = tool_registry
        self.max_concurrent = max_concurrent
        self.mailbox = mailbox
        self.agent_fabric = agent_fabric
        self.agent_id = agent_id
        self.session_state_manager = session_state_manager  # Epic 3.1 Issue 3.1.1
        self.deltabus = get_deltabus()

        # Execution state
        self.execution_context: Dict[str, Any] = {}  # Step outputs for dependency data flow
        self.completed_steps: List[str] = []  # LIFO stack for compensation

        # Compensation registry (tool → undo action)
        self.compensation_registry = {
            "book_restaurant": "cancel_booking",
            "charge_payment": "refund_payment",
            "create_calendar_event": "delete_calendar_event",
            "send_email": "send_cancellation_email",
            "web_search": None,  # No compensation needed (read-only)
            "query_k0_health": None,  # Read-only
            "query_k0_finance": None,  # Read-only
        }

    # ========== EVENT PUBLISHING HELPERS ==========

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
        Publish executor-level agent lifecycle event to DeltaBus

        Args:
            event_type: Event type (agent.task_received, agent.task_completed)
            agent_id: Executor agent identifier
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
                "agent_type": "dag_executor",
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

    async def _publish_step_event(
        self,
        event_type: str,
        step_id: str,
        agent_id: str,
        trace_id: str,
        session_id: str = "default",
        tool_name: Optional[str] = None,
        receipt_id: Optional[str] = None,
        latency_ms: Optional[int] = None,
        status: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """
        Publish step-level event to DeltaBus

        Events: agent.task_started, tool.called, agent.task_completed, failure

        Args:
            event_type: Event type (agent.task_started, tool.called, agent.task_completed)
            step_id: Step identifier
            agent_id: Agent executing step
            trace_id: Cognitive trace ID
            session_id: Session identifier
            tool_name: Tool name (for tool.called)
            receipt_id: Receipt ID (for tool.called)
            latency_ms: Step latency (for agent.task_completed)
            status: Step status (for agent.task_completed)
            error: Error message (for failure events)
        """
        event = DeltaBusEvent(
            event_type=event_type,
            session_id=session_id,
            payload={
                "step_id": step_id,
                "agent_id": agent_id,
                "trace_id": trace_id,
                "timestamp": time.time(),
            },
            timestamp=datetime.utcnow(),
            trace_id=trace_id,
        )

        # Add optional fields
        if tool_name:
            event.payload["tool_name"] = tool_name
        if receipt_id:
            event.payload["receipt_id"] = receipt_id
        if latency_ms:
            event.payload["latency_ms"] = latency_ms
        if status:
            event.payload["status"] = status
        if error:
            event.payload["error"] = error

        self.deltabus.publish(event)

    # ========== MAILBOX CONSUMER LOOP ==========

    async def run(self) -> None:
        """
        Main executor run loop - consumes committed plans from mailbox

        Mailbox-driven execution following AgentFabric lifecycle.
        Processes committed plans from mailbox and executes DAG waves.

        Lifecycle: WARMING → ACTIVE → IDLE → DRAINING → TERMINATED
        """
        print(f"[DAGExecutor] run() started for agent_id={self.agent_id}")

        try:
            while True:
                # Check if mailbox still exists (executor not terminated)
                if not self.mailbox:
                    print("[DAGExecutor] Mailbox closed, exiting run() loop")
                    break

                # Receive message from executor mailbox (blocking)
                message = await self.mailbox.receive()

                if message is None:
                    # Mailbox closed or drained
                    print("[DAGExecutor] Mailbox drained, exiting run() loop")
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
                    f"[DAGExecutor] Message received: message_id={message.message_id}, "
                    f"priority={message.priority.name if hasattr(message, 'priority') else 'UNKNOWN'}"
                )

                # Process plan execution
                try:
                    # Extract committed plan from message payload
                    committed_plan_data = message.payload.get("committed_plan")

                    if not committed_plan_data:
                        raise ValueError("Message payload missing 'committed_plan'")

                    # Execute DAG plan
                    result = await self.execute_plan(committed_plan_data)

                    # Publish response to DeltaBus for await_response()
                    response_event = DeltaBusEvent(
                        event_type=f"response.{message.message_id}",
                        session_id=message.payload.get("session_id", "default"),
                        payload={
                            "message_id": message.message_id,
                            "status": "success",
                            "result": result,
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
                        latency_ms=result.get("latency_ms", 0),
                    )

                    print(
                        f"[DAGExecutor] Task completed: task_id={result['task_id']}, "
                        f"status={result['status']}, waves={result['waves']}"
                    )

                except Exception as e:
                    print(f"[DAGExecutor] Task error: {e}")

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
            print("[DAGExecutor] run() cancelled")
            raise
        except Exception as e:
            print(f"[DAGExecutor] run() error: {e}")
            raise

    # ========== ISSUE 6.3.1: DAG PARSER & WAVE COMPUTATION ==========

    async def execute_plan(
        self, committed_plan: CommittedPlan, trace_id: str = "unknown", session_id: str = "default"
    ) -> Dict[str, Any]:
        """
        Main entry point: Execute committed plan with parallel waves

        Args:
            committed_plan: Plan from Planner Stage 4
            trace_id: Cognitive trace ID for event correlation
            session_id: Session identifier for event routing

        Returns:
            Task result with step results, latency, receipts

        Raises:
            CyclicDependencyError: If DAG has cycles
            StepExecutionError: If critical step fails
        """
        print(f"\n[DAGExecutor] Executing plan: {committed_plan.plan_id}")
        print(f"[DAGExecutor] Intent: {committed_plan.intent}")
        print(f"[DAGExecutor] Steps: {len(committed_plan.steps)}")

        start_time = perf_counter()

        try:
            # Step 1: Parse DAG
            dag = self._parse_dag(committed_plan)
            parse_latency = (perf_counter() - start_time) * 1000
            print(
                f"[DAGExecutor] ✅ DAG parsed: {dag.number_of_nodes()} nodes, {dag.number_of_edges()} edges, {parse_latency:.1f}ms"
            )

            # Step 2: Compute waves
            waves = self._compute_waves(dag, committed_plan.steps)
            wave_latency = (perf_counter() - start_time - parse_latency / 1000) * 1000
            print(f"[DAGExecutor] ✅ Waves computed: {len(waves)} waves, {wave_latency:.1f}ms")

            # Log wave structure
            self._log_wave_structure(waves)

            # Step 3: Execute waves with barriers
            wave_results = await self._execute_waves(waves, committed_plan, trace_id, session_id)

            total_latency = (perf_counter() - start_time) * 1000

            # Collect all receipts
            all_receipts = []
            for results in wave_results:
                for result in results:
                    all_receipts.extend(result.receipts)

            print(f"[DAGExecutor] ✅ Execution complete: {total_latency:.1f}ms total")

            return {
                "task_id": committed_plan.plan_id,
                "status": "SUCCESS",
                "step_results": wave_results,
                "latency_ms": int(total_latency),
                "receipts": all_receipts,
                "waves": len(waves),
            }

        except Exception as e:
            print(f"[DAGExecutor] ❌ Execution failed: {e}")
            raise

    def _parse_dag(self, committed_plan: CommittedPlan) -> nx.DiGraph:
        """
        Parse committed plan into directed acyclic graph (DAG)

        Creates: nodes = steps, edges = dependencies (step.needs)

        Args:
            committed_plan: Plan with steps and dependencies

        Returns:
            nx.DiGraph with step_id nodes and dependency edges

        Raises:
            CyclicDependencyError: If DAG has cycles
        """
        dag = nx.DiGraph()

        # Add nodes (steps)
        for step in committed_plan.steps:
            dag.add_node(step.step_id, step=step)

        # Add edges (dependencies)
        for step in committed_plan.steps:
            for dep_id in step.needs:
                # Edge from dependency → dependent
                # (Step depends on dep_id, so dep_id must complete first)
                dag.add_edge(dep_id, step.step_id)

        # Validate: no cycles (topological sort must be possible)
        if not nx.is_directed_acyclic_graph(dag):
            cycles = list(nx.simple_cycles(dag))
            raise CyclicDependencyError(f"DAG has circular dependencies: {cycles}")

        return dag

    def _compute_waves(self, dag: nx.DiGraph, steps: List[PlanStep]) -> List[List[str]]:
        """
        Compute parallel execution waves via topological sort

        Wave N: All steps with in-degree = 0 after Wave N-1 completes

        Uses Kahn's algorithm (1962) for topological ordering:
        1. Wave 1: All nodes with in-degree = 0 (no dependencies)
        2. Remove Wave 1 nodes from graph
        3. Wave 2: New nodes with in-degree = 0
        4. Repeat until all nodes processed

        Args:
            dag: Directed acyclic graph from _parse_dag
            steps: List of plan steps

        Returns:
            List of waves, each wave is list of step_ids
            Example: [["step_1", "step_2"], ["step_3"], ["step_4", "step_5"]]
        """
        waves = []
        remaining_dag = dag.copy()

        while remaining_dag.number_of_nodes() > 0:
            # Find all nodes with in-degree = 0 (no dependencies)
            wave = [node for node in remaining_dag.nodes() if remaining_dag.in_degree(node) == 0]

            if not wave:
                # Should never happen if DAG is acyclic
                raise CyclicDependencyError(
                    "Cannot compute wave: all remaining nodes have dependencies"
                )

            # Split wave if >max_concurrent (enforce parallelism limit)
            if len(wave) > self.max_concurrent:
                # Split into sub-waves of size max_concurrent
                for i in range(0, len(wave), self.max_concurrent):
                    sub_wave = wave[i : i + self.max_concurrent]
                    waves.append(sub_wave)
            else:
                waves.append(wave)

            # Remove wave nodes from graph
            remaining_dag.remove_nodes_from(wave)

        return waves

    def _log_wave_structure(self, waves: List[List[str]]) -> None:
        """
        Log wave structure for debugging

        Example output:
        Wave 1: [step_1, step_2, step_3] (parallel)
        Barrier
        Wave 2: [step_4, step_5] (parallel, depends on Wave 1)
        Barrier
        Wave 3: [step_6] (depends on Wave 2)
        """
        print("\n[DAGExecutor] Wave Structure:")
        for i, wave in enumerate(waves, start=1):
            print(f"  Wave {i}: {wave} (parallel, {len(wave)} steps)")
            if i < len(waves):
                print("  ──── Barrier ────")
        print()

    # ========== ISSUE 6.3.2: WAVE EXECUTION WITH BARRIERS ==========

    async def _execute_waves(
        self,
        waves: List[List[str]],
        committed_plan: CommittedPlan,
        trace_id: str = "unknown",
        session_id: str = "default",
    ) -> List[List[StepResult]]:
        """
        Execute waves in parallel with barriers

        For each wave:
        1. Execute all steps in parallel (asyncio.gather)
        2. Wait for all to complete (barrier)
        3. Check for failures (trigger compensation if critical)
        4. Proceed to next wave

        Args:
            waves: List of waves from _compute_waves
            committed_plan: Plan with step details
            trace_id: Cognitive trace ID for event correlation
            session_id: Session identifier for event routing

        Returns:
            List of wave results (each wave is list of StepResult)

        Raises:
            StepExecutionError: If critical step fails and compensation fails
        """
        all_wave_results = []

        # Map step_id → step for lookups
        step_map = {step.step_id: step for step in committed_plan.steps}

        for wave_num, wave in enumerate(waves, start=1):
            print(f"\n[DAGExecutor] Executing Wave {wave_num}: {wave}")

            # Execute all steps in wave concurrently (with trace_id/session_id)
            tasks = [
                self._execute_step(step_map[step_id], trace_id, session_id) for step_id in wave
            ]

            # Barrier: Wait for all steps in wave to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            wave_results = []
            for i, result in enumerate(results):
                step_id = wave[i]

                if isinstance(result, Exception):
                    # Step raised exception
                    print(f"[DAGExecutor] ❌ Step {step_id} failed: {result}")

                    # Critical failure: trigger compensation
                    await self._trigger_compensation(committed_plan, step_id, str(result))

                    # Raise to abort execution
                    raise StepExecutionError(f"Critical step {step_id} failed: {result}")

                elif result.status == "failure":
                    # Step returned failure status
                    print(f"[DAGExecutor] ❌ Step {step_id} failed: {result.error}")

                    # Trigger compensation
                    await self._trigger_compensation(committed_plan, step_id, result.error)

                    raise StepExecutionError(f"Critical step {step_id} failed: {result.error}")

                else:
                    # Success: store result, update execution context
                    print(
                        f"[DAGExecutor] ✅ Step {step_id}: {result.status}, {result.latency_ms}ms"
                    )
                    wave_results.append(result)
                    self.completed_steps.append(step_id)  # Push to compensation stack
                    self.execution_context[step_id] = result.output_data  # Store outputs

            all_wave_results.append(wave_results)

            print(
                f"[DAGExecutor] Wave {wave_num} complete: {len(wave_results)}/{len(wave)} steps succeeded"
            )

        return all_wave_results

    async def _execute_step(
        self, step: PlanStep, trace_id: str = "unknown", session_id: str = "default"
    ) -> StepResult:
        """
        Execute single step with event publishing

        In production:
        1. Check if executor agent active in Agent Roster
        2. If not: request spawn from Agent Factory
        3. Send StepTask to agent's mailbox
        4. Wait for agent response (timeout: 30s)
        5. Collect tool call receipts

        For PoC: Mock execution with asyncio.sleep + event publishing

        Args:
            step: Plan step to execute
            trace_id: Cognitive trace ID for event correlation
            session_id: Session identifier for event routing

        Returns:
            StepResult with outputs, latency, receipts
        """
        start_time = perf_counter()
        agent_id = step.agent_id or "mock_agent"

        # Publish agent.task_started event
        await self._publish_step_event(
            event_type="agent.task_started",
            step_id=step.step_id,
            agent_id=agent_id,
            trace_id=trace_id,
            session_id=session_id,
            tool_name=step.tool_name,
        )

        # Mock execution latency (varies by op type)
        if step.op == StepOp.TOOL:
            execution_time = (
                step.estimated_latency_ms / 1000 if step.estimated_latency_ms > 0 else 0.1
            )
        elif step.op == StepOp.MODEL:
            execution_time = 0.2  # LLM reasoning
        else:  # ASK
            execution_time = 0.05

        await asyncio.sleep(execution_time)

        # Mock output data (in production: actual tool/agent results)
        output_data = {
            "result": f"{step.description} completed",
            "step_id": step.step_id,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Add dependency data from previous steps
        for dep_id in step.needs:
            if dep_id in self.execution_context:
                output_data[f"from_{dep_id}"] = self.execution_context[dep_id]

        latency_ms = int((perf_counter() - start_time) * 1000)

        # Mock receipt
        receipt_id = f"receipt_{step.step_id}_{int(time.time() * 1000)}"
        receipt = {
            "receipt_id": receipt_id,
            "step_id": step.step_id,
            "tool_name": step.tool_name or "N/A",
            "status": "success",
            "latency_ms": latency_ms,
            "cost_usd": step.estimated_cost,
        }

        # Publish tool.called event (if TOOL operation)
        if step.op == StepOp.TOOL and step.tool_name:
            await self._publish_step_event(
                event_type="tool.called",
                step_id=step.step_id,
                agent_id=agent_id,
                trace_id=trace_id,
                session_id=session_id,
                tool_name=step.tool_name,
                receipt_id=receipt_id,
                latency_ms=latency_ms,
                status="success",
            )

        # Publish agent.task_completed event
        await self._publish_step_event(
            event_type="agent.task_completed",
            step_id=step.step_id,
            agent_id=agent_id,
            trace_id=trace_id,
            session_id=session_id,
            latency_ms=latency_ms,
            status="success",
        )

        return StepResult(
            step_id=step.step_id,
            status="success",
            output_data=output_data,
            agent_id=agent_id,
            latency_ms=latency_ms,
            receipts=[receipt],
        )

    # ========== ISSUE 6.3.3: SAGA PATTERN COMPENSATION ==========

    async def _trigger_compensation(
        self, committed_plan: CommittedPlan, failed_step_id: str, error_message: str
    ) -> CompensationResult:
        """
        Trigger Saga Pattern compensation: undo completed steps in reverse order

        Based on ADR-0008 Saga Pattern Error Recovery

        Flow:
        1. Reverse completed_steps stack (LIFO)
        2. For each completed step:
           - Lookup compensation action from registry
           - Execute compensation (reverse step)
           - Log result (success/failure)
        3. Return CompensationResult with user message

        Args:
            committed_plan: Original plan
            failed_step_id: Step that triggered compensation
            error_message: Error from failed step

        Returns:
            CompensationResult with compensated steps and errors
        """
        print("\n[DAGExecutor] 🔄 Triggering Saga Pattern compensation")
        print(f"[DAGExecutor] Failed step: {failed_step_id}")
        print(f"[DAGExecutor] Completed steps to compensate: {self.completed_steps}")

        start_time = perf_counter()
        compensated = []
        errors = []

        # Map step_id → step
        step_map = {step.step_id: step for step in committed_plan.steps}

        # Reverse order (LIFO: last completed first compensated)
        for step_id in reversed(self.completed_steps):
            step = step_map[step_id]

            # Lookup compensation action
            compensation_action = self.compensation_registry.get(step.tool_name)

            if compensation_action is None:
                # No compensation needed (read-only operation)
                print(f"[DAGExecutor]   {step_id}: No compensation needed (read-only)")
                compensated.append(step_id)
                continue

            print(
                f"[DAGExecutor]   Compensating {step_id}: {step.tool_name} → {compensation_action}"
            )

            try:
                # Execute compensation (mock: 3s timeout per ADR-0008)
                await asyncio.wait_for(
                    self._execute_compensation(step, compensation_action), timeout=3.0
                )
                compensated.append(step_id)
                print(f"[DAGExecutor]   ✅ {step_id} compensated successfully")

            except asyncio.TimeoutError:
                error_msg = f"{step_id}: Compensation timeout (>3s)"
                errors.append(error_msg)
                print(f"[DAGExecutor]   ❌ {error_msg}")

            except Exception as e:
                error_msg = f"{step_id}: {str(e)}"
                errors.append(error_msg)
                print(f"[DAGExecutor]   ❌ Compensation failed: {e}")

        total_latency = int((perf_counter() - start_time) * 1000)

        # Generate user-facing message
        user_message = self._generate_compensation_message(
            committed_plan, failed_step_id, error_message, compensated, errors
        )

        print(f"\n[DAGExecutor] Compensation complete: {total_latency}ms")
        print(f"[DAGExecutor] Compensated: {len(compensated)}/{len(self.completed_steps)} steps")
        print(f"[DAGExecutor] Errors: {len(errors)}")
        print(f"[DAGExecutor] User message: {user_message}")

        return CompensationResult(
            compensated_steps=compensated,
            compensation_errors=errors,
            total_latency_ms=total_latency,
            user_message=user_message,
        )

    async def _execute_compensation(self, step: PlanStep, compensation_action: str) -> None:
        """
        Execute compensation action (mock for PoC)

        In production: Send compensation message to responsible agent

        Args:
            step: Original step to compensate
            compensation_action: Undo action (e.g., "cancel_booking")
        """
        # Mock compensation latency
        await asyncio.sleep(0.01)  # 10ms mock compensation

        # In production: call actual API/agent for undo
        # Example: DELETE /bookings/{booking_id}

    def _generate_compensation_message(
        self,
        committed_plan: CommittedPlan,
        failed_step_id: str,
        error_message: str,
        compensated: List[str],
        errors: List[str],
    ) -> str:
        """
        Generate user-facing error message with compensation summary

        Args:
            committed_plan: Original plan
            failed_step_id: Failed step ID
            error_message: Error from failed step
            compensated: Successfully compensated step IDs
            errors: Compensation errors

        Returns:
            User-friendly message
        """
        step_map = {step.step_id: step for step in committed_plan.steps}
        failed_step = step_map.get(failed_step_id)

        if failed_step:
            failed_desc = failed_step.description
        else:
            failed_desc = failed_step_id

        compensated_descriptions = [
            step_map[sid].description for sid in compensated if sid in step_map
        ]

        if errors:
            return (
                f"I couldn't complete '{failed_desc}' because: {error_message}. "
                f"I've cancelled {len(compensated)} actions ({', '.join(compensated_descriptions[:2])}...), "
                f"but {len(errors)} compensations failed. Please check your account."
            )
        else:
            return (
                f"I couldn't complete '{failed_desc}' because: {error_message}. "
                f"I've successfully cancelled {len(compensated)} actions ({', '.join(compensated_descriptions[:2])}...)."
            )
