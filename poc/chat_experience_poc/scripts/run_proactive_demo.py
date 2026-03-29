#!/usr/bin/env python3
"""
Proactive Gap Detection Demo

Demonstrates the proactive knowledge gap resolution flow:
1. SSE event arrives with knowledge.gap.detected (e.g., "Who is Sam?")
2. ProactiveAgent receives the event and spawns GapResolutionAgent
3. GapResolutionAgent asks the user about the gap
4. User responds with information
5. Learning signal is emitted to DeltaBus for writer agents to persist

Usage:
    python scripts/run_proactive_demo.py

Flow:
    [Mock SSE Server] ---> [ProactiveAgent] ---> [GapResolutionAgent]
                                                       |
                                                       v
                                              Ask: "Who is Sam?"
                                                       |
                                              [User Response]
                                                       |
                                                       v
                                           [Emit Learning Signal]
                                                       |
                                                       v
                                            [DeltaBus] --> [Writers]
"""

import asyncio
import logging
import sys
from pathlib import Path

import httpx
import structlog

# Ensure PoC package is importable
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Configure logging
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
        structlog.dev.ConsoleRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logging.basicConfig(level=logging.INFO, format="%(message)s", force=True)


async def fire_gap_event(gap_data: dict):
    """Fire a knowledge gap event to the SSE server."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8002/fire",
            json={
                "event_type": "knowledge.gap.detected",
                "data": gap_data,
            },
            timeout=5.0,
        )
        print(f"[SSE] Fired gap event: {response.json()}")
        return response.json()


async def subscribe_to_deltabus_events(deltabus):
    """Subscribe to DeltaBus events for demo output."""
    events_received = []

    async def on_event(event):
        et = getattr(event, "event_type", "?")
        payload = getattr(event, "payload", {}) or {}
        events_received.append({"type": et, "payload": payload})

        if "proactive.question" in et:
            question = payload.get("question", "")
            entity = payload.get("entity_name", "")
            print(f"\n{'='*60}")
            print(f"[PROACTIVE QUESTION] About: {entity}")
            print(f"[QUESTION] {question}")
            print(f"{'='*60}")

        elif "session.delta" in et and payload.get("delta_type") == "learning":
            entity = payload.get("entity_learned", "")
            facts = payload.get("learned_facts", {})
            print(f"\n{'='*60}")
            print(f"[LEARNING SIGNAL] Entity: {entity}")
            print(f"[FACTS] {facts}")
            print(f"{'='*60}")

    # Subscribe to relevant patterns
    sub1 = deltabus.subscribe("proactive.*", on_event)
    sub2 = deltabus.subscribe("session.delta", on_event)

    return events_received, [sub1, sub2]


async def run_proactive_demo():
    """Run the proactive gap detection demo."""
    print("=" * 80)
    print("  PROACTIVE GAP DETECTION DEMO")
    print("=" * 80)
    print()

    # Initialize system
    from system_coordinator import get_system_coordinator

    coord = get_system_coordinator()
    if not coord.system_ready:
        print("[1/5] Initializing system...")
        ok = await coord.initialize_system()
        if not ok:
            print("[ERROR] System failed to initialize")
            return
        print("[1/5] System initialized ✅")
    else:
        print("[1/5] System already ready ✅")

    # Get components
    from l4_runtime.deltabus.deltabus import get_deltabus

    deltabus = get_deltabus()
    proactive_agent = coord.proactive_agent

    # Subscribe to DeltaBus for demo output
    print("[2/5] Subscribing to DeltaBus events...")
    events, subs = await subscribe_to_deltabus_events(deltabus)
    print("[2/5] DeltaBus subscribed ✅")

    # Wait a moment for SSE connection to establish
    await asyncio.sleep(1.0)

    # Fire a knowledge gap event
    print("\n[3/5] Firing knowledge gap event...")
    gap_data = {
        "gap_id": "gap_sam_demo",
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

    await fire_gap_event(gap_data)
    print("[3/5] Gap event fired ✅")

    # Wait for ProactiveAgent to process and spawn GapResolutionAgent
    print("\n[4/5] Waiting for ProactiveAgent to process gap...")
    await asyncio.sleep(3.0)

    # Check if gap agent was spawned
    if proactive_agent and hasattr(proactive_agent, "active_gap_agents"):
        active_gaps = proactive_agent.active_gap_agents
        print(f"[4/5] Active gap agents: {len(active_gaps)}")

        if active_gaps:
            # Simulate user response
            gap_id = "gap_sam_demo"
            user_response = "Sam is my brother. He's 28 years old and lives in Austin."

            print(f"\n[USER RESPONSE] {user_response}")
            print()

            # Route response to gap agent
            print("[5/5] Processing user response...")
            await proactive_agent.handle_gap_response(gap_id, user_response)

            # Wait for learning signal to be emitted
            await asyncio.sleep(2.0)
            print("[5/5] Gap resolution complete ✅")
        else:
            print("[4/5] No gap agents spawned yet (check ProactiveAgent logs)")
    else:
        print("[4/5] ProactiveAgent not available")

    # Show summary
    print("\n" + "=" * 80)
    print("  DEMO SUMMARY")
    print("=" * 80)

    print(f"\nEvents captured: {len(events)}")
    for evt in events:
        evt_type = evt["type"]
        if "proactive.question" in evt_type:
            print(f"  - Proactive question asked about: {evt['payload'].get('entity_name')}")
        elif evt["payload"].get("delta_type") == "learning":
            print(f"  - Learning signal emitted for: {evt['payload'].get('entity_learned')}")

    if proactive_agent:
        stats = proactive_agent.get_stats()
        print("\nProactiveAgent stats:")
        print(f"  - Total ticks received: {stats['ticks_received']}")
        print(f"  - Gap ticks: {stats['gap_ticks']}")
        print(f"  - Active gap agents: {stats['active_gap_agents']}")

    # Cleanup subscriptions
    for sub_id in subs:
        try:
            deltabus.unsubscribe(sub_id)
        except Exception:
            pass

    # Graceful shutdown
    print("\n[SHUTDOWN] Shutting down...")
    await coord.shutdown_system()
    print("[SHUTDOWN] Complete ✅")


if __name__ == "__main__":
    asyncio.run(run_proactive_demo())
