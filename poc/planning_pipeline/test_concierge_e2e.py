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
from poc_planning_pipeline import PlanningPipeline
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

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
        ("4. 📊 Concierge Stats", "Show chat/plan statistics"),
        ("5. 🔄 Reset Chat", "Clear chat history"),
        ("6. ❌ Exit", "Exit test harness"),
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

    console.print("✅ Concierge Agent initialized!\n", style="green")

    # Initialize Agent Spawn Wrapper
    console.print("[*] Initializing Agent Spawn Wrapper...", style="dim")
    agent_spawn_wrapper = AgentSpawnWrapper(llm_provider)
    console.print("✅ Agent Spawn Wrapper initialized!", style="green")
    console.print(
        f"   Available templates: {len(list(agent_spawn_wrapper.templates_dir.glob('*.prompt')))}\n",
        style="dim",
    )

    # Main test loop
    while True:
        print_scenarios()

        choice = Prompt.ask(
            "Select scenario [1/2/3/4/5/6]", choices=["1", "2", "3", "4", "5", "6"], default="1"
        )

        if choice == "1":
            await scenario_free_conversation(concierge)
        elif choice == "2":
            await scenario_planning_mode(concierge)
        elif choice == "3":
            await scenario_mixed_mode(concierge)
        elif choice == "4":
            scenario_stats(concierge)
        elif choice == "5":
            scenario_reset(concierge)
        elif choice == "6":
            console.print("\n👋 Exiting test harness. Thanks for testing!\n", style="bold green")
            break

        # Ask to continue
        if choice not in ["4", "5"]:
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
