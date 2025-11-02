#!/usr/bin/env python3
"""
Test the circular hub-and-spoke agent architecture.

Demonstrates:
1. User at center
2. Agents spawned on-demand
3. Prompt templates loaded/generated
4. Agent execution with tools
5. Agent collaboration (circular model)
"""

import asyncio
import os
import sys
from pathlib import Path

# Setup environment
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ["GROQ_API_KEY"] = "gsk_sXGDUx0HIxA2fJoyuwmWGdyb3FYX3bg1NhbJGg5iaRUeGY6wTG1"

from agent_spawn_wrapper import AgentSpawnWrapper
from llm_provider import LLMProvider


async def demonstrate_circular_architecture():
    """Demonstrate the circular hub-and-spoke agent architecture."""

    print("\n" + "=" * 80)
    print("🔄 CIRCULAR HUB-AND-SPOKE AGENT ARCHITECTURE")
    print("=" * 80)

    print("\nArchitecture:")
    print(
        """
                    ┌─────────────────┐
                    │  AGENT FACTORY  │
                    │  (Spawn/Config) │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────┐
        │                    │                │
        ▼                    ▼                ▼
    ┌─────────┐      ┌──────────────┐   ┌──────────┐
    │AGENT 1  │      │TRAVEL AGENT  │   │AGENT N   │
    │(Tools)  │      │(Tools)       │   │(Tools)   │
    └────┬────┘      └──────┬───────┘   └────┬─────┘
         │                  │               │
         │   ┌──────────────┼───────────────┤
         │   │              │               │
         └──→│ USER CENTER  │←──────────────┘
            │              │
       ┌────┴──────────────┴────┐
       │                         │
    PLANNER              CONCIERGE
    (Route)              (Clarify)
    """
    )

    # Initialize LLM provider
    print("\n1️⃣  Initializing LLM Provider...")
    llm_provider = LLMProvider(prefer_local=False)
    print(f"   ✅ LLM Backend: {llm_provider.get_backend().upper()}")

    # Initialize Agent Spawn Wrapper
    print("\n2️⃣  Initializing Agent Spawn Wrapper...")
    spawn_wrapper = AgentSpawnWrapper(llm_provider)
    print("   ✅ Templates dir: agents/templates/")
    print("   ✅ Cache dir: agents/cache/")

    # List available templates
    templates = list(spawn_wrapper.templates_dir.glob("*.prompt"))
    print(f"   ✅ Templates available: {len(templates)}")
    for template in templates:
        print(f"      - {template.stem}")

    # Test 1: Load existing template
    print("\n3️⃣  Loading TRAVEL_AGENT template...")
    template = spawn_wrapper.load_template("travel_agent")
    if template:
        print(f"   ✅ Template loaded ({len(template)} chars)")
        print(f"   📝 First 100 chars: {template[:100]}...")
    else:
        print("   ⚠️  Template not found")

    # Test 2: Spawn agent with tools
    print("\n4️⃣  Spawning Travel Agent (with mock tools)...")
    tools = {
        "search_flights": lambda **kwargs: {"status": "searching", "query": kwargs},
        "search_hotels": lambda **kwargs: {"status": "searching", "query": kwargs},
        "check_availability": lambda **kwargs: {"available": True},
    }

    agent = await spawn_wrapper.spawn_agent(
        agent_type="travel_agent",
        user_input="I want to plan a trip to California in November",
        tools=tools,
        user_id="prince",
        user_profile={"preferences": "luxury", "frequent_destinations": ["SF", "LA"]},
    )

    print(f"   ✅ Agent spawned: {agent.agent_id}")
    print(f"   ✅ Agent type: {agent.agent_type}")
    if agent.context:
        print(f"   ✅ Tools available: {list(agent.context.tools.keys())}")

    # Test 3: Execute agent
    print("\n5️⃣  Executing Travel Agent...")
    if agent.context:
        result = await agent.execute(agent.context)

    print(f"   ✅ Execution completed in {result.latency_ms:.1f}ms")
    print(f"   ✅ Status: {result.status}")
    if result.clarification_question:
        print(f"   ❓ Clarification needed: {result.clarification_question}")
    if result.result:
        print("   📊 Result preview:")
        for key, value in list(result.result.items())[:3]:
            print(f"      - {key}: {str(value)[:60]}...")

    # Test 4: Demonstrate agent spawning for non-existent type
    print("\n6️⃣  Spawning agent for non-existent type (will generate prompt)...")
    print("   ⏳ Generating custom_booking_agent prompt with LLM...")

    try:
        agent2 = await spawn_wrapper.spawn_agent(
            agent_type="custom_booking_agent",
            user_input="Book me a ticket",
            tools={"search_tickets": lambda **kw: {}, "book_ticket": lambda **kw: {}},
        )
        print(f"   ✅ Custom agent spawned: {agent2.agent_id}")
        print("   ✅ Prompt was generated and cached")

        # Verify it's in cache
        cached = spawn_wrapper.cache_dir / "custom_booking_agent.prompt"
        if cached.exists():
            print(f"   ✅ Cached at: {cached}")
    except Exception as e:
        print(f"   ⚠️  Generation failed: {e}")

    # Summary
    print("\n" + "=" * 80)
    print("✅ CIRCULAR ARCHITECTURE DEMONSTRATION COMPLETE")
    print("=" * 80)
    print("\n📊 Summary:")
    print("   1. User at CENTER of circular architecture")
    print("   2. Agents spawn on-demand as WORKERS")
    print("   3. Templates loaded or generated dynamically")
    print("   4. Each agent gets specific TOOLS for its domain")
    print("   5. Agents can ask user for clarification")
    print("   6. Agents can collaborate in the circle")
    print("   7. Planner orchestrates but doesn't block")
    print("\n🎯 Next: Integrate into Planning Pipeline for full E2E flow")


if __name__ == "__main__":
    asyncio.run(demonstrate_circular_architecture())
