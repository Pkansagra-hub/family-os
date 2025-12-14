"""
Manual Test: Concierge Agent with REAL Groq API Calls

This script tests Concierge with actual LLM calls to verify:
  - Prompt Registry integration works
  - Template Engine merging works
  - Groq API responses are parsed correctly
  - Intent classification works with real LLM reasoning
  - Specialist routing generates real responses

⚠️ WARNING: This makes REAL API calls and consumes tokens!
Only run manually when you want to verify end-to-end integration.

Usage:
  python tests/manual/test_concierge_live_llm.py

Requirements:
  - GROQ_API_KEY environment variable set
  - Internet connection
  - Groq API credits
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# Load .env file first
from dotenv import load_dotenv

# Add poc directory to path BEFORE other imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

from l3_execution.agents.concierge_agent import ConciergeAgent
from l5_infrastructure.groq_client import GroqClient


async def test_concierge_with_live_llm():
    """
    Test Concierge with real Groq API calls.

    Tests multiple scenarios:
      1. Meta-intent (greeting)
      2. Query-intent (health question → specialist routing)
      3. Planning-intent (complex task → planner routing)
      4. Time query (simple meta-intent)
    """
    print("=" * 80)
    print("CONCIERGE AGENT - LIVE LLM TEST")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Check API key
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("❌ ERROR: GROQ_API_KEY environment variable not set!")
        print("Set it with: $env:GROQ_API_KEY='your-api-key-here'")
        return

    print("✅ GROQ_API_KEY found")
    print()

    # Initialize Groq client
    groq_client = GroqClient(api_key=api_key, trace_id="manual-test-001")
    print("✅ Groq client initialized")
    print()

    # Initialize Concierge
    concierge = ConciergeAgent(
        agent_id="concierge-manual-test",
        session_id="session-manual-test",
        groq_client=groq_client,
        trace_id="manual-test-001",
    )
    print("✅ Concierge agent initialized")
    print(f"   Agent ID: {concierge.agent_id}")
    print(f"   Agent Type: {concierge.agent_type}")
    print(f"   State: {concierge.state.value}")
    print()

    # Transition to ACTIVE
    await concierge.transition_to(concierge.state.__class__.ACTIVE)
    print("✅ Concierge transitioned to ACTIVE state")
    print()

    # Test scenarios
    test_cases = [
        {
            "name": "Test 1: Greeting (Meta-Intent)",
            "message": "hey there! how are you?",
            "expected_intent": "meta",
            "expected_subtype": "GREETING",
        },
        {
            "name": "Test 2: Health Query (Specialist Routing)",
            "message": "How's my knee recovery going? I did PT yesterday.",
            "expected_intent": "query",
            "expected_specialist": "healthcare",
        },
        {
            "name": "Test 3: Finance Query (Specialist Routing)",
            "message": "What's my spending this month?",
            "expected_intent": "query",
            "expected_specialist": "finance",
        },
        {
            "name": "Test 4: Planning Request (Planner Routing)",
            "message": "Help me plan a trip to Hawaii for my family",
            "expected_intent": "planning",
        },
        {
            "name": "Test 5: Small Talk (Meta-Intent)",
            "message": "what's up?",
            "expected_intent": "meta",
            "expected_subtype": "SMALL_TALK",
        },
    ]

    results = []

    for i, test in enumerate(test_cases, 1):
        print("-" * 80)
        print(f"{test['name']}")
        print("-" * 80)
        print(f"User Input: \"{test['message']}\"")
        print()

        # Create message
        message = {
            "payload": {"content": test["message"]},
            "sender_id": "manual-test-user",
            "trace_id": f"manual-test-{i}",
        }

        # Process message (REAL LLM CALLS HAPPEN HERE)
        try:
            start_time = datetime.now()
            response = await concierge.process_message(message)
            latency_ms = (datetime.now() - start_time).total_seconds() * 1000

            # Display results
            print(f"✅ Response received (latency: {latency_ms:.0f}ms)")
            print()
            print(f"Status: {response.get('status')}")
            print(f"Intent: {response.get('intent')}")
            print(f"Subtype: {response.get('intent_subtype', 'N/A')}")
            print(f"Specialist: {response.get('specialist_type', 'N/A')}")

            if response.get("feedback_message"):
                print(f"Feedback: {response.get('feedback_message')}")

            print()
            print("Response Content:")
            print(f"  {response.get('content')}")
            print()
            print(f"Tokens Used: {response.get('tokens_used', 'N/A')}")
            print()

            # Validation
            passed = True
            if response.get("intent") != test.get("expected_intent"):
                print(
                    f"⚠️ UNEXPECTED: Expected intent '{test.get('expected_intent')}', got '{response.get('intent')}'"
                )
                passed = False

            if test.get("expected_specialist") and response.get("specialist_type") != test.get(
                "expected_specialist"
            ):
                print(
                    f"⚠️ UNEXPECTED: Expected specialist '{test.get('expected_specialist')}', got '{response.get('specialist_type')}'"
                )
                passed = False

            results.append(
                {
                    "test": test["name"],
                    "passed": passed,
                    "latency_ms": latency_ms,
                    "tokens": response.get("tokens_used", 0),
                }
            )

            if passed:
                print("✅ Test PASSED")
            else:
                print("❌ Test FAILED (unexpected intent/routing)")

        except Exception as e:
            print(f"❌ ERROR: {str(e)}")
            results.append(
                {
                    "test": test["name"],
                    "passed": False,
                    "latency_ms": 0,
                    "tokens": 0,
                    "error": str(e),
                }
            )

        print()

    # Summary
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print()

    passed_count = sum(1 for r in results if r["passed"])
    total_count = len(results)
    total_tokens = sum(r.get("tokens", 0) for r in results)
    avg_latency = sum(r["latency_ms"] for r in results) / total_count if total_count > 0 else 0

    print(f"Tests Passed: {passed_count}/{total_count}")
    print(f"Total Tokens Used: {total_tokens}")
    print(f"Average Latency: {avg_latency:.0f}ms")
    print()

    # Concierge stats
    stats = concierge.get_concierge_stats()
    print("Concierge Metrics:")
    print(f"  Meta-intents handled: {stats['meta_intents_handled']}")
    print(f"  Specialists routed: {stats['specialists_routed']}")
    print(f"  Planner routed: {stats['planner_routed']}")
    print(f"  LLM calls: {stats['llm_calls']}")
    print(f"  Errors: {stats['errors']}")
    print()

    # Groq client stats
    groq_stats = groq_client.get_stats()
    print("Groq Client Metrics:")
    print(f"  Total tokens: {groq_stats['token_count']}")
    print(f"  Total requests: {groq_stats['request_count']}")
    print(f"  Errors: {groq_stats['error_count']}")
    print(f"  Avg tokens/request: {groq_stats['average_tokens_per_request']:.1f}")
    print()

    # Final result
    if passed_count == total_count:
        print("🎉 ALL TESTS PASSED! Concierge working correctly with real LLM.")
    else:
        print(f"⚠️ {total_count - passed_count} test(s) failed. Check intent classification.")

    print()
    print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)


if __name__ == "__main__":
    # Run async test
    asyncio.run(test_concierge_with_live_llm())
