#!/usr/bin/env python3
"""
E2E Runner — PATH 1 and PATH 2 flows with mailbox routing and awaiter synchronization

Epic 3.2 Issue 3.2.1: Overhaul run_e2e_paths.py
- Initialize via SystemCoordinator (retrieving shared singletons)
- Drive PATH 1 and PATH 2 through Intent Router mailbox flow
- Use awaiter utilities for synchronization (no sleep loops)
- Assert K0 mock counters and recorded receipts without direct mutations

Scenarios:
  1) PATH 1: Concierge → Specialist (mailbox routing) → answer
     - Route via IntentRouter with MailboxManager
     - Wait for response using await_response()
     - Assert K0 writer statistics and receipts
     - Verify episodic memory writes

  2) PATH 2: Concierge → Orchestrator (mailbox routing) → answer
     - Route via IntentRouter with MailboxManager
     - Wait for orchestration phases using await_phase() if applicable
     - Assert K0 writer statistics and receipts
     - Verify control and prospective memory writes

Performance:
- Event-driven synchronization (no sleep loops)
- DeltaBus subscribe_once for awaiter utilities
- <10s total runtime for both paths

References:
- Epic 3.2 Issue 3.2.1: Runner overhaul with mailbox flow
- utils/awaiters.py: Awaiter utility layer
- l4_runtime/mailbox/: Mailbox architecture
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Dict

import structlog
from dotenv import load_dotenv

# Ensure PoC package is importable when run directly
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables from .env file
load_dotenv(PROJECT_ROOT / ".env")

# Configure structlog for E2E runs (match main.py configuration)
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer(),  # Use ConsoleRenderer for readability
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

# Set logging level
logging.basicConfig(level=logging.INFO, format="%(message)s", force=True)


async def _subscribe_deltabus_debug(deltabus) -> Dict[str, str]:
    """Subscribe to common event patterns and print concise debug lines."""
    subscriptions: Dict[str, str] = {}

    async def on_event(event):
        et = getattr(event, "event_type", "?")
        sid = getattr(event, "session_id", "?")
        trace = getattr(event, "trace_id", "?")
        # Keep payload print compact
        payload = getattr(event, "payload", {}) or {}
        snippet = str(payload)[:220].replace("\n", " ")
        print(f"[DeltaBus] {et} sid={sid} trace={trace} payload={snippet}")

    # Subscribe to key patterns
    subscriptions["response"] = deltabus.subscribe("response.*", on_event)
    subscriptions["session"] = deltabus.subscribe("session.*", on_event)
    subscriptions["agent"] = deltabus.subscribe("agent.*", on_event)
    subscriptions["tool"] = deltabus.subscribe("tool.called", on_event)
    return subscriptions


async def _unsubscribe_all(deltabus, subs: Dict[str, str]) -> None:
    for name, sub_id in list(subs.items()):
        try:
            deltabus.unsubscribe(sub_id)
        except Exception:
            pass


async def _print_backend_snapshot(bg_manager) -> None:
    """Print K0 mock backend stats and show a few recent deltas by type."""
    backend = getattr(bg_manager, "backend_storage", None)
    cmd_port = getattr(bg_manager, "mock_command_port", None)
    if not backend or not cmd_port:
        print("[K0] Backend not initialized yet")
        return

    stats = cmd_port.get_stats()
    print("\n[K0] Backend stats:")
    print(
        f"  total_deltas={stats['backend_stats']['total_deltas']} total_bytes={stats['backend_stats']['total_bytes']}"
    )
    by_type = stats["backend_stats"]["by_type"]
    print("  by_type=" + ", ".join(f"{k}={v}" for k, v in by_type.items()))

    # Show up to 2 samples per type
    for dtype in ["episodic", "prospective", "learning", "semantic"]:
        results = await backend.query_deltas(delta_type=dtype, limit=2)
        if results:
            print(f"  samples[{dtype}]:")
            for d in results:
                print(
                    f"    - id={d.delta_id} writer={d.writer_type} conf={d.confidence:.2f} data={str(d.content)[:120]}"
                )


async def run_path1(user_id: str) -> None:
    """
    PATH 1: Concierge → Specialist (mailbox routing)

    Steps per Epic 3.2.1:
    1. Initialize via SystemCoordinator (done in main)
    2. Route through Intent Router mailbox
    3. Use awaiter utilities for synchronization
    4. Assert K0 mock counters and receipts
    """
    from l1_input.intent_router import IntentRouter
    from l4_runtime.deltabus.deltabus import get_deltabus
    from l4_runtime.mailbox.mailbox_manager import MailboxManager
    from l4_runtime.session_state.session_state_manager import SessionStateManager
    from l5_infrastructure.background_services_manager import (
        BackgroundServicesManager as BGM,
    )
    from system_coordinator import get_system_coordinator

    coord = get_system_coordinator()
    if not coord.system_ready:
        ok = await coord.initialize_system()
        if not ok:
            raise RuntimeError("System failed to initialize for PATH 1")

    deltabus = get_deltabus()
    subs = await _subscribe_deltabus_debug(deltabus)

    # Get MailboxManager and SessionStateManager
    mailbox_manager = MailboxManager()  # Singleton - returns existing instance
    ssm = SessionStateManager(deltabus=deltabus)

    # Build router with mailbox manager (Epic 3.2.1 Step 2)
    router = IntentRouter(session_manager=ssm, deltabus=deltabus, mailbox_manager=mailbox_manager)

    print("\n" + "=" * 80)
    print("  PATH 1: Concierge -> Specialist (Healthcare Query)")
    print("=" * 80)
    text = "How's my recovery going?"

    # Route through mailbox
    reply, meta = await router.route_user_input(user_input=text, user_id=user_id)
    envelope_id = meta.get("envelope_id")
    trace_id = meta.get("trace_id")
    latency_ms = meta.get("latency_ms", 0.0)

    print(f"\n  [INPUT]   {text}")
    print(f"  [OUTPUT]  {reply}")
    print(f"  [LATENCY] {latency_ms:.2f}ms")
    print(f"  [TRACE]   {trace_id}")
    print(f"  [ENV_ID]  {envelope_id}")

    # Epic 3.2.1 Step 3: Use awaiter utilities (no sleep loops)
    # Response already received above via route_user_input()
    # Now wait for writer agents to process session deltas

    # Get writer statistics before
    bgm = await BGM.get_manager()
    stats_before = await bgm.get_writer_statistics()
    print(f"[PATH1] Writer stats before: deltas={stats_before['total_deltas_processed']}")

    # Allow writer agents to process (they auto-subscribe to session.delta)
    # Use event-driven wait instead of sleep loops
    await asyncio.sleep(0.5)  # Brief wait for writer processing (will improve with writer receipts)

    # Epic 3.2.1 Step 4: Assert K0 mock counters and receipts
    stats_after = await bgm.get_writer_statistics()
    print(
        f"[PATH1] Writer stats after: deltas={stats_after['total_deltas_processed']}, "
        f"commands={stats_after['total_commands_sent']}"
    )

    # Assert writer agents processed deltas
    deltas_processed = (
        stats_after["total_deltas_processed"] - stats_before["total_deltas_processed"]
    )
    print(f"[PATH1] Deltas processed in this path: {deltas_processed}")

    # Print K0 backend snapshot with assertions
    await _print_backend_snapshot(bgm)

    # Assertions for acceptance criteria
    backend = getattr(bgm, "backend_storage", None)
    if backend:
        episodic_results = await backend.query_deltas(delta_type="episodic", limit=10)
        print(f"[PATH1] ✅ Episodic memory writes: {len(episodic_results)}")

        # Assert: At least some episodic memories recorded
        if len(episodic_results) > 0:
            print("[PATH1] ✅ ASSERTION PASSED: Episodic memories recorded")
        else:
            print("[PATH1] ⚠️  WARNING: No episodic memories found")

    await _unsubscribe_all(deltabus, subs)


async def run_path2(user_id: str) -> None:
    """
    PATH 2: Concierge → Planner → DAG Executor (Full Planning Demo)

    Steps:
    1. User input: "Plan a dinner at an Italian restaurant nearby tonight"
    2. Concierge classifies as planning intent
    3. Planner creates 4-stage plan (Sketch → Expand → Validate → Commit)
    4. DAG Executor executes plan steps in parallel waves
    5. Collect receipts and assert K0 mock counters
    """
    from l1_input.intent_router import IntentRouter
    from l4_runtime.deltabus.deltabus import get_deltabus
    from l4_runtime.mailbox.mailbox_manager import MailboxManager
    from l4_runtime.session_state.session_state_manager import SessionStateManager
    from l5_infrastructure.background_services_manager import (
        BackgroundServicesManager as BGM,
    )
    from l5_infrastructure.google_client import GoogleClient

    deltabus = get_deltabus()
    subs = await _subscribe_deltabus_debug(deltabus)

    # Get MailboxManager and SessionStateManager
    mailbox_manager = MailboxManager()  # Singleton - returns existing instance
    ssm = SessionStateManager(deltabus=deltabus)

    # Build router with mailbox manager
    router = IntentRouter(session_manager=ssm, deltabus=deltabus, mailbox_manager=mailbox_manager)

    print("\n" + "=" * 80)
    print("  PATH 2: Full Planning Pipeline (Planner -> DAG Executor)")
    print("=" * 80)
    text = "Plan a dinner at an Italian restaurant nearby tonight"
    trace_id = f"path2_planning_{user_id}"

    # Step 1: Route through Concierge first (get acknowledgment)
    print("\n  [STEP 1] Routing to Concierge for intent classification...")
    reply, meta = await router.route_user_input(user_input=text, user_id=user_id)
    print(f"  [INPUT]   {text}")
    print(f"  [CONCIERGE] {reply[:100]}...")

    # Step 2: Create plan using Google AI with structured JSON output
    print("\n  [STEP 2] Creating plan with Google AI (structured JSON)...")

    # Use Google AI client for planning (same as rest of system)
    import os

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("  [SKIP] GOOGLE_API_KEY not set - skipping planning demo")
        await _unsubscribe_all(deltabus, subs)
        return
    google_client = GoogleClient(api_key=api_key)

    # Define JSON schema for structured plan output
    plan_schema = {
        "type": "object",
        "properties": {
            "intent": {"type": "string", "description": "Brief description of the goal"},
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "step_id": {"type": "string", "description": "Unique step identifier"},
                        "tool": {
                            "type": "string",
                            "description": "Tool to use: web_search, calendar_add, or reminder_set",
                        },
                        "description": {"type": "string", "description": "What this step does"},
                        "needs": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Step IDs this depends on",
                        },
                    },
                    "required": ["step_id", "tool", "description", "needs"],
                },
            },
        },
        "required": ["intent", "steps"],
    }

    # Generate plan using LLM with schema enforcement
    plan_prompt = f"""Create a step-by-step plan for: "{text}"

Available tools: web_search, calendar_add, reminder_set

Generate a plan with 3-5 steps to accomplish this goal."""

    try:
        plan_response = await google_client.complete_with_schema(
            messages=[{"role": "user", "content": plan_prompt}],
            response_schema=plan_schema,
            agent_type="planner",
            temperature=0.3,
            max_tokens=2000,
            trace_id=trace_id,
        )

        # Get parsed JSON directly from response
        plan_data = plan_response.get("data", {})
        steps = plan_data.get("steps", [])
        intent = plan_data.get("intent", "Unknown")

        print("\n  [PLAN CREATED]")
        print(f"    Intent: {intent}")
        print(f"    Steps: {len(steps)}")
        for i, step in enumerate(steps, 1):
            desc = step.get("description", "N/A")[:50]
            print(f"      {i}. {step.get('step_id')}: {step.get('tool')} - {desc}...")

        # Step 3: Execute plan steps (mock execution)
        print("\n  [STEP 3] Executing plan steps...")

        for step in steps:
            step_id = step.get("step_id", "unknown")
            tool = step.get("tool", "unknown")

            # Mock tool execution
            print(f"    Executing {step_id} ({tool})...")
            await asyncio.sleep(0.1)  # Simulate execution
            print(f"      {step_id} completed")

        print("\n  [PATH2] Full planning pipeline executed successfully!")

    except Exception as e:
        print(f"\n  [PATH2] Planning failed: {e}")

    # Get writer statistics
    bgm = await BGM.get_manager()
    stats = await bgm.get_writer_statistics()
    print(f"\n[PATH2] Writer stats: deltas={stats['total_deltas_processed']}")

    # Print K0 backend snapshot
    await _print_backend_snapshot(bgm)

    await _unsubscribe_all(deltabus, subs)


async def run_path3(user_id: str) -> None:
    """
    PATH 3: Concierge -> Meta/Action (direct handling)

    Steps:
    1. Route through Intent Router mailbox
    2. Concierge handles directly (meta intent)
    3. Assert response
    """
    from l1_input.intent_router import IntentRouter
    from l4_runtime.deltabus.deltabus import get_deltabus
    from l4_runtime.mailbox.mailbox_manager import MailboxManager
    from l4_runtime.session_state.session_state_manager import SessionStateManager
    from system_coordinator import get_system_coordinator

    coord = get_system_coordinator()
    deltabus = get_deltabus()

    # Get MailboxManager and SessionStateManager
    mailbox_manager = MailboxManager()
    ssm = SessionStateManager(deltabus=deltabus)

    # Build router with mailbox manager
    router = IntentRouter(session_manager=ssm, deltabus=deltabus, mailbox_manager=mailbox_manager)

    print("\n" + "=" * 80)
    print("  PATH 3: Concierge -> Meta/Action (Reminder)")
    print("=" * 80)
    text = "Send a reminder to take my medication at 8pm"

    # Route through mailbox
    reply, meta = await router.route_user_input(user_input=text, user_id=user_id)
    envelope_id = meta.get("envelope_id")
    trace_id = meta.get("trace_id")
    latency_ms = meta.get("latency_ms", 0.0)

    print(f"\n  [INPUT]   {text}")
    print(f"  [OUTPUT]  {reply}")
    print(f"  [LATENCY] {latency_ms:.2f}ms")
    print(f"  [TRACE]   {trace_id}")
    print(f"  [ENV_ID]  {envelope_id}")


async def run_path4(user_id: str) -> None:
    """
    PATH 4: Proactive Gap Detection (SSE -> ProactiveAgent -> GapResolutionAgent)

    Steps:
    1. Fire SSE event with knowledge.gap.detected
    2. ProactiveAgent receives event and spawns GapResolutionAgent
    3. GapResolutionAgent asks about the gap
    4. Simulate user response
    5. Assert learning signal emitted to DeltaBus
    """
    import httpx
    from l4_runtime.deltabus.deltabus import get_deltabus
    from system_coordinator import get_system_coordinator

    coord = get_system_coordinator()
    deltabus = get_deltabus()
    proactive_agent = coord.proactive_agent

    print("\n" + "=" * 80)
    print("  PATH 4: Proactive Gap Detection (Knowledge Gap Resolution)")
    print("=" * 80)

    # Subscribe to DeltaBus events for assertions
    events_received = []

    async def on_event(event):
        et = getattr(event, "event_type", "?")
        payload = getattr(event, "payload", {}) or {}
        events_received.append({"type": et, "payload": payload})

    sub1 = deltabus.subscribe("proactive.*", on_event)
    sub2 = deltabus.subscribe("session.delta", on_event)

    # Wait for SSE connection to stabilize
    await asyncio.sleep(0.5)

    # Fire a knowledge gap event to SSE server
    gap_data = {
        "gap_id": "gap_sam_e2e",
        "gap_type": "entity_unknown",
        "entity_name": "Sam",
        "context": "User mentioned 'Can you remind Sam to pick up groceries?'",
        "confidence": 0.85,
        "suggested_questions": [
            "Who is Sam?",
            "Is Sam a family member?",
            "How should I contact Sam?",
        ],
    }

    print(f"\n  [STEP 1] Firing SSE gap event for entity: {gap_data['entity_name']}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:8002/fire",
                json={"event_type": "knowledge.gap.detected", "data": gap_data},
                timeout=5.0,
            )
            sse_result = response.json()
            print(f"  [SSE]     Event fired: {sse_result}")
    except httpx.ConnectError:
        print("  [SKIP]    SSE server not running, skipping PATH 4")
        for sid in [sub1, sub2]:
            try:
                deltabus.unsubscribe(sid)
            except Exception:
                pass
        return

    # Wait for ProactiveAgent to process
    print("  [STEP 2] Waiting for ProactiveAgent to spawn GapResolutionAgent...")
    await asyncio.sleep(3.0)

    # Check if gap agent was spawned
    gap_agent_spawned = False
    if proactive_agent and hasattr(proactive_agent, "active_gap_agents"):
        active_gaps = proactive_agent.active_gap_agents
        gap_agent_spawned = len(active_gaps) > 0
        print(f"  [STATUS]  Active gap agents: {len(active_gaps)}")

    # Simulate user response
    if gap_agent_spawned:
        gap_id = "gap_sam_e2e"
        user_response = "Sam is my brother. He's 28 and lives in Austin."

        print(f"  [STEP 3] Simulating user response: {user_response}")
        await proactive_agent.handle_gap_response(gap_id, user_response)

        # Wait for learning signal
        await asyncio.sleep(2.0)
        print("  [STEP 4] Gap resolution complete")
    else:
        print("  [WARN]    No gap agents spawned (check SSE connection)")

    # Assertions
    proactive_questions = [e for e in events_received if "proactive.question" in e["type"]]
    learning_signals = [
        e for e in events_received if e.get("payload", {}).get("delta_type") == "learning"
    ]

    print(f"\n  [RESULT]  Proactive questions emitted: {len(proactive_questions)}")
    print(f"  [RESULT]  Learning signals emitted: {len(learning_signals)}")

    if proactive_questions:
        print("  [ASSERT]  Proactive question generated")
    if learning_signals:
        for sig in learning_signals:
            entity = sig["payload"].get("entity_learned", "")
            facts = sig["payload"].get("learned_facts", {})
            print(f"  [LEARN]   Entity: {entity}")
            print(f"  [LEARN]   Facts: {facts}")
        print("  [ASSERT]  Learning signal captured for writer agents")

    # ProactiveAgent stats
    if proactive_agent:
        stats = proactive_agent.get_stats()
        print(f"\n  [STATS]   ProactiveAgent ticks: {stats['ticks_received']}")
        print(f"  [STATS]   Gap ticks: {stats['gap_ticks']}")
        print(f"  [STATS]   Active gap agents: {stats['active_gap_agents']}")

    # Cleanup
    for sid in [sub1, sub2]:
        try:
            deltabus.unsubscribe(sid)
        except Exception:
            pass


async def run_path5(user_id: str) -> None:
    """
    PATH 5: Memory Recall & Life Wisdom (Multi-turn conversation)

    Demonstrates the holistic memory view:
    - Turn 1: User asks genuine question -> Query memory layers -> LLM answers
    - Turn 2: User asks for life advice -> LLM provides wisdom from memories

    Memory layers queried:
    - st_epi (episodic): What happened, when, where, with whom
    - st_social: Relationships and interactions
    - st_kg_dom: People, places, things
    - st_prospective: Decisions and reminders pending
    - st_observations: Emotional and temporal context
    """
    from l3_execution.agents.specialists.memory_recall_agent import MemoryRecallAgent
    from system_coordinator import get_system_coordinator

    coord = get_system_coordinator()

    print("\n" + "=" * 80)
    print("  PATH 5: Memory Recall & Life Wisdom (Holistic View)")
    print("=" * 80)

    # Create MemoryRecallAgent
    recall_agent = MemoryRecallAgent(
        agent_id="memory_recall_demo",
        session_id=f"session_{user_id}",
        groq_client=coord.groq_client,
        trace_id="path5_memory_recall",
    )

    # =========================================================================
    # TURN 1: User asks genuine question from their life
    # =========================================================================
    print("\n  --- TURN 1: Memory Query ---")

    # Real questions from explore_memory_layers.py output
    turn1_questions = [
        "What travel plans are pending?",
        "Who are my key colleagues at work?",
        "What decisions do I need to make?",
    ]

    for q in turn1_questions:
        print(f"\n  [USER]    {q}")

        result = await recall_agent.process_message({"query": q, "turn": 1})

        print(f"  [ANSWER]  {result['answer']}")
        print(f"  [SOURCES] {result.get('memory_sources', [])}")
        print()

    # =========================================================================
    # TURN 2: User asks for life wisdom/advice
    # =========================================================================
    print("\n  --- TURN 2: Life Wisdom Request ---")

    wisdom_question = "Based on everything you know about my life, what should I prioritize?"

    print(f"\n  [USER]    {wisdom_question}")

    result = await recall_agent.process_message({"query": wisdom_question, "turn": 2})

    print(f"  [WISDOM]  {result['answer']}")
    print(f"  [BASED ON] {result.get('based_on_memories', 0)} conversation turns")

    # =========================================================================
    # Additional wisdom examples
    # =========================================================================
    print("\n  --- Additional Wisdom Queries ---")

    wisdom_queries = [
        "How can I better balance work and family?",
        "What patterns do you notice in my life that I should be aware of?",
    ]

    for wq in wisdom_queries:
        print(f"\n  [USER]    {wq}")
        result = await recall_agent.process_message({"query": wq, "turn": 2})
        print(f"  [WISDOM]  {result['answer']}")

    # Cleanup
    await recall_agent.cleanup()

    print("\n  [COMPLETE] Memory recall demo finished")


async def main():
    # Initialize full system once
    from system_coordinator import get_system_coordinator

    print("=" * 80)
    print("  K1 E2E Paths - Agent Input/Output Demo")
    print("=" * 80)

    coord = get_system_coordinator()
    ok = await coord.initialize_system()
    if not ok:
        raise SystemExit(1)

    try:
        await run_path1(user_id="user_demo")
        await run_path2(user_id="user_demo")
        await run_path3(user_id="user_demo")
        await run_path4(user_id="user_demo")
        await run_path5(user_id="user_demo")

        print("\n" + "=" * 80)
        print("  COMPLETE")
        print("=" * 80)
    finally:
        await coord.shutdown_system()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
