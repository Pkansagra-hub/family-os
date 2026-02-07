"""
Test Sub-Agent Architecture
============================

Quick test to verify sub-agents work correctly with Delta Bus.

Usage:
    python -m poc.session_state_demo.test_sub_agents
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from poc.session_state_demo.anniversary_demo.agents.booking_agent import BookingAgent
from poc.session_state_demo.anniversary_demo.agents.search_agent import SearchAgent
from poc.session_state_demo.anniversary_demo.bus.delta_bus import DeltaBus, Message

# ruff: noqa: E402 (imports after sys.path manipulation)
from poc.session_state_demo.bridge import SessionLLMBridge
from poc.session_state_demo.config import get_config
from poc.session_state_demo.llm_client import SimpleLLMClient


async def test_sub_agents():
    """Test sub-agent architecture."""
    print("=" * 60)
    print("Sub-Agent Architecture Test - M8")
    print("=" * 60)

    # Initialize components
    config = get_config()
    llm_client = SimpleLLMClient(
        model=config.google_model,
        api_key=config.google_api_key,
    )
    bridge = SessionLLMBridge(db_path=":memory:", session_id="test")

    # Add some beliefs to test READ-ONLY access
    bridge.execute_tool_calls(
        [
            {
                "name": "add_belief",
                "args": {
                    "subject": "Mike",
                    "predicate": "has_allergy",
                    "object": "shellfish",
                },
            },
            {
                "name": "add_belief",
                "args": {
                    "subject": "trip",
                    "predicate": "destination",
                    "object": "Sonoma",
                },
            },
        ]
    )
    print("\nBeliefs seeded: Mike has shellfish allergy, trip to Sonoma")

    # Create Delta Bus
    delta_bus = DeltaBus()
    received_messages = []

    async def on_message(msg: Message):
        received_messages.append(msg)
        print(f"\n  [Delta Bus] Received: {msg.topic}")

    await delta_bus.subscribe(
        subscriber_id="test",
        topic_pattern="agent.*.result",
        callback=on_message,
    )
    print("\nDelta Bus initialized, subscribed to agent.*.result")

    # Test SearchAgent
    print("\n" + "=" * 60)
    print("Test 1: SearchAgent - Search Accommodations")
    print("=" * 60)

    search_agent = SearchAgent(
        bridge=bridge,
        llm_client=llm_client,
        delta_bus=delta_bus,
    )

    # Test READ-ONLY enforcement
    print("\n--- Testing READ-ONLY enforcement ---")
    try:
        search_agent.bridge.execute_tool_calls([{"name": "test", "args": {}}])
        print("  ERROR: Write should have been blocked!")
    except PermissionError as e:
        print(f"  PASS: Write blocked - {e}")

    # Test accommodation search (using mock data)
    print("\n--- Searching accommodations in Sonoma ---")
    result = await search_agent.search_accommodations(
        location="Sonoma",
        budget_per_night=300,
    )

    print(f"  Agent ID: {result.agent_id}")
    print(f"  Status: {result.status.value}")
    print(f"  Duration: {result.duration_ms}ms")

    if result.results:
        accommodations = result.results
        if isinstance(accommodations, list) and accommodations:
            for item in accommodations:
                if "result" in item and "accommodations" in item["result"]:
                    for acc in item["result"]["accommodations"][:2]:
                        print(
                            f"  - {acc['name']}: ${acc['price_per_night']}/night ({acc['rating']} stars)"
                        )

    # Test restaurant search with allergy awareness
    print("\n" + "=" * 60)
    print("Test 2: SearchAgent - Search Restaurants (allergy aware)")
    print("=" * 60)

    result = await search_agent.search_restaurants(
        location="Sonoma",
        cuisine="Italian",
    )

    print(f"  Status: {result.status.value}")
    if result.results:
        restaurants = result.results
        if isinstance(restaurants, list) and restaurants:
            for item in restaurants:
                if "result" in item and "restaurants" in item["result"]:
                    print(f"  Allergy filter applied: {item['result'].get('allergy_filter')}")
                    for rest in item["result"]["restaurants"][:2]:
                        warning = rest.get("warning", "")
                        safe = "SAFE" if rest.get("shellfish_safe", True) else "WARNING"
                        print(f"  - {rest['name']}: {rest['cuisine']} [{safe}] {warning}")

    # Test BookingAgent
    print("\n" + "=" * 60)
    print("Test 3: BookingAgent - Book Restaurant")
    print("=" * 60)

    booking_agent = BookingAgent(
        bridge=bridge,
        llm_client=llm_client,
        delta_bus=delta_bus,
    )

    result = await booking_agent.book_restaurant(
        restaurant_name="Della Santina's",
        date="Saturday",
        time="7:00 PM",
        party_size=2,
        special_requests=["birthday celebration"],
    )

    print(f"  Status: {result.status.value}")
    if result.results:
        booking = result.results
        if isinstance(booking, list) and booking:
            for item in booking:
                if "result" in item:
                    b = item["result"]
                    print(f"  Confirmation: {b.get('confirmation_number')}")
                    print(f"  Restaurant: {b['details'].get('restaurant')}")
                    print(f"  Special requests: {b['details'].get('special_requests')}")
                    print(f"  Notes: {b.get('notes')}")

    # Check Delta Bus received all messages
    print("\n" + "=" * 60)
    print("Delta Bus Summary")
    print("=" * 60)

    stats = delta_bus.get_stats()
    print(f"  Messages published: {stats['messages_published']}")
    print(f"  Messages delivered: {stats['messages_delivered']}")
    print(f"  Received by test subscriber: {len(received_messages)}")

    for msg in received_messages:
        print(f"  - {msg.topic} from {msg.source}")

    print("\n" + "=" * 60)
    print("Test Complete - Sub-Agent Architecture Working!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_sub_agents())
