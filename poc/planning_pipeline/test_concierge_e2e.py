"""
End-to-End Interactive Test for Concierge Agent

Tests the complete Concierge + Planning Pipeline integration:
1. Chat mode: Casual conversation
2. Planning mode: Actionable tasks
3. Intent detection: Seamless transitions
4. Clarification flow: Proxy between user and planner
5. Plan history: Contextual awareness

Usage:
    python test_concierge_e2e.py

Test Scenarios:
- Pure chat: "Hi", "How are you?", "Tell me about the weather"
- Direct planning: "Book dinner at 7pm"
- Mixed transitions: Chat → Planning
- Multi-turn clarifications: Planner asks, Concierge proxies
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from agent_spawn_wrapper import AgentSpawnWrapper

# Import components
from concierge_agent import ConciergeAgent

# Import DAG components
from dag_builder import DAGBuilder
from dag_executor import DAGExecutor
from dag_visualizer import DAGVisualizer
from plan_aggregator import PlanAggregator
from poc_planning_pipeline import PlanningPipeline
from question_batcher import ConciergeQuestionBatcher
from question_queue import QuestionQueue
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from simple_commit import SimpleCommitHandler

# Add grandparent for llm_provider
sys.path.insert(0, str(Path(__file__).parent.parent))
from llm_provider import LLMProvider

# Rich console for pretty output
console = Console()


def print_header():
    """Print test harness header"""
    console.print("\n" + "=" * 80, style="bold cyan")
    console.print(" " * 20 + "🤖 CONCIERGE AGENT - INTERACTIVE TEST", style="bold cyan")
    console.print("=" * 80 + "\n", style="bold cyan")

    console.print(
        Panel(
            """✅ Concierge Integration
✅ Chat Mode (LLM-based conversation)
✅ Planning Mode (Invoke pipeline)
✅ Intent Detection (Chat vs Plan)
✅ Clarification Proxy (Concierge ↔ Planner ↔ User)""",
            title="Architecture Status",
            border_style="green",
        )
    )


def print_scenarios():
    """Print available test scenarios"""
    console.print("\n" + "=" * 80, style="bold yellow")
    console.print(" " * 30 + "📋 TEST SCENARIOS", style="bold yellow")
    console.print("=" * 80 + "\n", style="bold yellow")

    scenarios = [
        ("1. 💬 Free Conversation", "Chat naturally with the concierge"),
        ("2. 🎯 Planning Mode", "Give actionable task to invoke planner"),
        ("3. 🔀 Mixed Mode", "Start with chat, transition to planning"),
        ("4. ⚡ DAG Workflow Test", "Test parallel DAG execution directly"),
        ("5. 📊 Concierge Stats", "Show chat/plan statistics"),
        ("6. 🔄 Reset Chat", "Clear chat history"),
        ("7. ❌ Exit", "Exit test harness"),
    ]

    for label, desc in scenarios:
        console.print(f"  {label}")
        console.print(f"      {desc}\n")


async def scenario_free_conversation(concierge: ConciergeAgent):
    """Scenario 1: Free conversation with concierge"""
    console.print("\n" + "▶" * 35, style="bold green")
    console.print("💬 SCENARIO 1: Free Conversation", style="bold green")
    console.print("Chat naturally - concierge will decide when to plan", style="green")
    console.print("▶" * 35 + "\n", style="bold green")

    while True:
        user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]")

        if not user_input or user_input.lower() in ["exit", "quit", "back"]:
            console.print("↩️  Returning to main menu...\n", style="yellow")
            break

        # Process message
        result = await concierge.process_message(user_input)

        # Display response
        mode = result.get("mode", "unknown")
        response = result.get("response", "")
        latency = result.get("latency_ms", 0)

        if mode == "chat":
            console.print(
                Panel(
                    response,
                    title="💬 Concierge (Chat Mode)",
                    border_style="blue",
                )
            )
        elif mode == "plan":
            plan_result = result.get("plan_result", {})
            status = plan_result.get("status", "UNKNOWN")
            flow_id = plan_result.get("flow_id", "N/A")

            console.print(
                Panel(
                    f"{response}\n\nStatus: {status}\nFlow ID: {flow_id}\nLatency: {latency:.1f}ms",
                    title="🎯 Concierge (Planning Mode)",
                    border_style="green",
                )
            )
        elif mode == "clarification":
            console.print(
                Panel(
                    response,
                    title="❓ Clarification Needed",
                    border_style="yellow",
                )
            )

        console.print(f"⏱️  Latency: {latency:.1f}ms | Mode: {mode}", style="dim")


async def scenario_planning_mode(concierge: ConciergeAgent):
    """Scenario 2: Direct planning mode"""
    console.print("\n" + "▶" * 35, style="bold green")
    console.print("🎯 SCENARIO 2: Planning Mode", style="bold green")
    console.print("Give actionable tasks - concierge will invoke planner", style="green")
    console.print("▶" * 35 + "\n", style="bold green")

    examples = [
        "Book dinner at 7pm",
        "Schedule a meeting tomorrow at 2pm",
        "Order pizza for delivery",
    ]

    console.print("[dim]Examples:[/dim]")
    for ex in examples:
        console.print(f"  • {ex}", style="dim")
    console.print()

    while True:
        user_input = Prompt.ask("\n[bold cyan]Planning Request[/bold cyan]")

        if not user_input or user_input.lower() in ["exit", "quit", "back"]:
            console.print("↩️  Returning to main menu...\n", style="yellow")
            break

        # Process message
        result = await concierge.process_message(user_input)

        # Display response
        mode = result.get("mode", "unknown")
        response = result.get("response", "")

        if mode == "plan":
            plan_result = result.get("plan_result", {})
            status = plan_result.get("status", "UNKNOWN")
            flow_id = plan_result.get("flow_id", "N/A")
            latency = result.get("latency_ms", 0)

            console.print(
                Panel(
                    f"{response}\n\n"
                    f"Status: {status}\n"
                    f"Flow ID: {flow_id}\n"
                    f"Latency: {latency:.1f}ms",
                    title="✅ Planning Result",
                    border_style="green",
                )
            )
        elif mode == "clarification":
            # Handle clarification loop
            clarification_response = response
            while mode == "clarification":
                console.print(
                    Panel(
                        clarification_response,
                        title="❓ Clarification Needed",
                        border_style="yellow",
                    )
                )

                user_response = Prompt.ask("\n[bold cyan]Your answer[/bold cyan]")

                if not user_response or user_response.lower() == "cancel":
                    console.print("🚫 Planning cancelled", style="red")
                    break

                # Send clarification response
                result = await concierge.process_message(user_response)
                mode = result.get("mode", "unknown")
                clarification_response = result.get("response", "")

            # Show final result if planning completed
            if mode == "plan":
                plan_result = result.get("plan_result", {})
                status = plan_result.get("status", "UNKNOWN")
                flow_id = plan_result.get("flow_id", "N/A")

                console.print(
                    Panel(
                        f"{clarification_response}\n\n" f"Status: {status}\n" f"Flow ID: {flow_id}",
                        title="✅ Planning Complete",
                        border_style="green",
                    )
                )


async def scenario_mixed_mode(concierge: ConciergeAgent):
    """Scenario 3: Mixed chat and planning"""
    console.print("\n" + "▶" * 35, style="bold green")
    console.print("🔀 SCENARIO 3: Mixed Mode", style="bold green")
    console.print("Start with chat, naturally transition to planning", style="green")
    console.print("▶" * 35 + "\n", style="bold green")

    console.print("[dim]Example flow: 'Hi' → 'I'm hungry' → 'Book dinner at 7pm'[/dim]\n")

    await scenario_free_conversation(concierge)


async def scenario_dag_workflow(
    pipeline: PlanningPipeline,
    agent_spawn_wrapper: AgentSpawnWrapper,
    question_queue: QuestionQueue,
    question_batcher: ConciergeQuestionBatcher,
    visualizer: DAGVisualizer,
    aggregator: PlanAggregator,
    commit_handler: SimpleCommitHandler,
):
    """Scenario 4: Test DAG workflow directly"""
    console.print("\n" + "▶" * 35, style="bold green")
    console.print("⚡ SCENARIO 4: DAG Workflow Test", style="bold green")
    console.print("Test parallel DAG execution with question batching", style="green")
    console.print("▶" * 35 + "\n", style="bold green")

    examples = [
        "Book dinner at 7pm and notify family",
        "Schedule meeting, send invites, and reserve room",
        "Order supplies and update inventory",
    ]

    console.print("[dim]Examples (multi-step tasks for parallel execution):[/dim]")
    for ex in examples:
        console.print(f"  • {ex}", style="dim")
    console.print()

    while True:
        intent = Prompt.ask("\n[bold cyan]Task (or 'back' to return)[/bold cyan]")

        if not intent or intent.lower() in ["exit", "quit", "back"]:
            console.print("↩️  Returning to main menu...\n", style="yellow")
            break

        # Run DAG workflow
        try:
            result = await run_dag_workflow(
                intent=intent,
                pipeline=pipeline,
                agent_spawn_wrapper=agent_spawn_wrapper,
                question_queue=question_queue,
                question_batcher=question_batcher,
                visualizer=visualizer,
                aggregator=aggregator,
                commit_handler=commit_handler,
            )

            if result["status"] == "completed":
                console.print(
                    Panel(
                        f"""✅ Task Completed Successfully!

Flow ID: {result['flow_id']}
Total Latency: {result['latency_ms']:.1f}ms

You can retrieve this plan later using:
    commit_handler.retrieve('{result['flow_id']}')
""",
                        title="⚡ DAG Workflow Complete",
                        border_style="green",
                    )
                )
            elif result["status"] == "needs_clarification":
                console.print(
                    Panel(
                        "Clarification handling not yet implemented in DAG workflow.\n"
                        "Use Planning Mode (Scenario 2) for clarification support.",
                        title="⚠️ Clarification Needed",
                        border_style="yellow",
                    )
                )

        except Exception as e:
            console.print(
                Panel(
                    f"Error: {e}\n\nStack trace:\n{e.__traceback__}",
                    title="❌ Execution Failed",
                    border_style="red",
                )
            )


def scenario_stats(concierge: ConciergeAgent):
    """Scenario 4: Show concierge statistics"""
    console.print("\n" + "▶" * 35, style="bold green")
    console.print("📊 SCENARIO 4: Concierge Statistics", style="bold green")
    console.print("▶" * 35 + "\n", style="bold green")

    stats = concierge.get_stats()

    console.print(
        Panel(
            f"""Chat Messages: {stats['chat_messages']}
Plans Completed: {stats['plans_completed']}
Active Planning: {stats['active_planning']}
Pending Clarification: {stats['pending_clarification']}""",
            title="Concierge Stats",
            border_style="cyan",
        )
    )

    # Show chat history
    if concierge.chat_history:
        console.print("\n[bold]Recent Chat History:[/bold]")
        for msg in concierge.chat_history[-5:]:
            role_style = "cyan" if msg.role == "user" else "green"
            console.print(
                f"  [{role_style}]{msg.role.upper()}:[/{role_style}] {msg.content[:80]}..."
            )

    # Show plan history
    if concierge.plan_history:
        console.print("\n[bold]Plan History:[/bold]")
        for plan in concierge.plan_history[-5:]:
            console.print(f"  • {plan.intent}: {plan.summary[:60]}... ({plan.status})")

    console.print()


def scenario_reset(concierge: ConciergeAgent):
    """Scenario 5: Reset chat history"""
    console.print("\n" + "▶" * 35, style="bold green")
    console.print("🔄 SCENARIO 5: Reset Chat History", style="bold green")
    console.print("▶" * 35 + "\n", style="bold green")

    confirm = Prompt.ask(
        "Are you sure you want to clear chat history?", choices=["y", "n"], default="n"
    )

    if confirm == "y":
        concierge.reset_chat()
        console.print("✅ Chat history cleared!\n", style="green")
    else:
        console.print("↩️  Reset cancelled\n", style="yellow")


async def run_dag_workflow(
    intent: str,
    pipeline: PlanningPipeline,
    agent_spawn_wrapper: AgentSpawnWrapper,
    question_queue: QuestionQueue,
    question_batcher: ConciergeQuestionBatcher,
    visualizer: DAGVisualizer,
    aggregator: PlanAggregator,
    commit_handler: SimpleCommitHandler,
) -> dict:
    """
    Run complete DAG workflow: Plan → Build → Execute → Aggregate → Commit

    Returns:
        dict with keys: flow_id, status, dag, aggregated_plan, latency_ms
    """
    import time

    start_time = time.time()

    # Step 1: Generate expanded plan (sketch → expand)
    console.print("\n[bold cyan]📝 Step 1: Generating Plan...[/bold cyan]")
    expanded_plan = await pipeline.run_with_clarifications(intent)

    if expanded_plan.get("needs_clarification"):
        # Return early if clarification needed
        return {
            "status": "needs_clarification",
            "questions": expanded_plan.get("questions", []),
            "latency_ms": (time.time() - start_time) * 1000,
        }

    sketch = expanded_plan.get("sketch", {})
    expanded_steps = expanded_plan.get("expanded_steps", [])

    console.print(f"✅ Plan generated: {len(expanded_steps)} steps")

    # Step 2: Build DAG from expanded plan
    console.print("\n[bold cyan]🔨 Step 2: Building DAG...[/bold cyan]")
    builder = DAGBuilder()
    dag = builder.build_from_expanded_plan(sketch, expanded_steps)

    console.print(f"✅ DAG built: {len(dag.nodes)} nodes, {len(dag.edges)} edges")

    # Step 3: Visualize DAG (ASCII)
    console.print("\n[bold cyan]📊 Step 3: DAG Structure[/bold cyan]")
    ascii_dag = visualizer.render_ascii(dag)
    console.print(ascii_dag)

    # Step 4: Execute DAG with question batching
    console.print("\n[bold cyan]⚡ Step 4: Executing DAG (Parallel)...[/bold cyan]")

    # Start question batcher in background
    batcher_task = asyncio.create_task(question_batcher.start_batching(question_queue))

    # Execute DAG
    executor = DAGExecutor(agent_spawn_wrapper, question_queue)
    results = await executor.execute(dag)

    # Stop batcher
    question_batcher.stop()
    await batcher_task

    console.print(f"✅ Execution complete: {len(results)} results")

    # Step 5: Aggregate results
    console.print("\n[bold cyan]📦 Step 5: Aggregating Results...[/bold cyan]")
    aggregated_plan = aggregator.aggregate(
        dag=dag,
        results=results,
        intent=intent,
        flow_id=None,  # Will be generated
    )

    console.print(f"✅ Status: {aggregated_plan.status}")
    console.print(f"   Successful: {len(aggregated_plan.successful_steps)}")
    console.print(f"   Failed: {len(aggregated_plan.failed_steps)}")
    console.print(f"   Blocked: {len(aggregated_plan.blocked_steps)}")

    # Step 6: Commit to storage
    console.print("\n[bold cyan]💾 Step 6: Committing Plan...[/bold cyan]")
    flow_id = commit_handler.commit(aggregated_plan)
    console.print(f"✅ Committed: {flow_id}")

    # Step 7: Display metrics
    console.print("\n[bold cyan]📈 Step 7: Performance Metrics[/bold cyan]")
    metrics = aggregated_plan.dag_metrics

    if metrics:
        metrics_dict = metrics.to_dict() if hasattr(metrics, "to_dict") else {}
        max_parallelism = metrics_dict.get("max_parallelism", 1)
        per_agent_latencies = metrics_dict.get("per_agent_latencies", {})

        latency_lines = "\n".join(
            [f"  • {agent}: {latency:.1f}ms" for agent, latency in per_agent_latencies.items()]
        )

        console.print(
            Panel(
                f"""Total Latency: {aggregated_plan.total_latency_ms:.1f}ms
Max Parallelism: {max_parallelism}
Agents Used: {', '.join(aggregated_plan.agents_used)}

Per-Agent Latencies:
{latency_lines or '  (No agent latencies recorded)'}""",
                title="⚡ DAG Execution Metrics",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel(
                f"""Total Latency: {aggregated_plan.total_latency_ms:.1f}ms
Agents Used: {', '.join(aggregated_plan.agents_used)}

(Detailed metrics not available)""",
                title="⚡ DAG Execution Metrics",
                border_style="green",
            )
        )

    total_latency = (time.time() - start_time) * 1000

    return {
        "status": "completed",
        "flow_id": flow_id,
        "dag": dag,
        "aggregated_plan": aggregated_plan,
        "latency_ms": total_latency,
    }


async def main():
    """Main test harness"""
    print_header()

    # Initialize components
    console.print("Initializing components...", style="yellow")

    # LLM Provider
    llm_provider = LLMProvider()

    # Planning Pipeline (with return_clarifications mode)
    pipeline = PlanningPipeline(
        llm_provider=llm_provider,
        enable_clarifications=True,
        use_flatbuffers=True,
    )
    # Enable return_clarifications for Concierge integration
    pipeline.return_clarifications = True

    # Concierge Agent
    concierge = ConciergeAgent(
        llm_provider=llm_provider,
        planning_pipeline=pipeline,
        max_history=20,
    )

    console.print("✅ Concierge Agent initialized!", style="green")

    # Initialize Agent Spawn Wrapper
    console.print("[*] Initializing Agent Spawn Wrapper...", style="dim")
    agent_spawn_wrapper = AgentSpawnWrapper(llm_provider)
    console.print("✅ Agent Spawn Wrapper initialized!", style="green")
    console.print(
        f"   Available templates: {len(list(agent_spawn_wrapper.templates_dir.glob('*.prompt')))}\n",
        style="dim",
    )

    # Initialize DAG components
    console.print("[*] Initializing DAG components...", style="dim")
    question_queue = QuestionQueue()
    question_batcher = ConciergeQuestionBatcher(
        question_queue=question_queue,
        batch_timeout=2.0,
        max_batch_size=3,
    )
    visualizer = DAGVisualizer()
    aggregator = PlanAggregator()
    commit_handler = SimpleCommitHandler(storage_dir="poc_commits")
    console.print("✅ DAG components initialized!\n", style="green")

    # Main test loop
    while True:
        print_scenarios()

        choice = Prompt.ask(
            "Select scenario [1/2/3/4/5/6/7]",
            choices=["1", "2", "3", "4", "5", "6", "7"],
            default="1",
        )

        if choice == "1":
            await scenario_free_conversation(concierge)
        elif choice == "2":
            await scenario_planning_mode(concierge)
        elif choice == "3":
            await scenario_mixed_mode(concierge)
        elif choice == "4":
            await scenario_dag_workflow(
                pipeline=pipeline,
                agent_spawn_wrapper=agent_spawn_wrapper,
                question_queue=question_queue,
                question_batcher=question_batcher,
                visualizer=visualizer,
                aggregator=aggregator,
                commit_handler=commit_handler,
            )
        elif choice == "5":
            scenario_stats(concierge)
        elif choice == "6":
            scenario_reset(concierge)
        elif choice == "7":
            console.print("\n👋 Exiting test harness. Thanks for testing!\n", style="bold green")
            break

        # Ask to continue
        if choice not in ["5", "6"]:
            continue_test = Prompt.ask("\nContinue testing?", choices=["y", "n"], default="y")
            if continue_test == "n":
                console.print(
                    "\n👋 Exiting test harness. Thanks for testing!\n", style="bold green"
                )
                break


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n\n👋 Interrupted by user. Goodbye!\n", style="yellow")
    except Exception as e:
        console.print(f"\n\n❌ Error: {e}\n", style="bold red")
        raise
