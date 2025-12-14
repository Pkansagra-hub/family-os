"""
Test/Demo Script for LearningExtractorAgent and SemanticEnricherAgent

Demonstrates:
1. LearningExtractorAgent extracting learning signals:
   - User correction detection
   - Positive/negative feedback classification
   - Task performance tracking
   - Drift detection

2. SemanticEnricherAgent extracting semantic meaning:
   - Concept extraction
   - Relationship extraction
   - Affect analysis
   - Salience scoring

References:
- Epic 5.2.1 - LearningExtractorAgent
- Epic 5.3.1 - SemanticEnricherAgent
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from l3_execution.agents.writers.learning_extractor_agent import LearningExtractorAgent
from l3_execution.agents.writers.semantic_enricher_agent import SemanticEnricherAgent


async def test_learning_extractor():
    """Test LearningExtractorAgent with various signal types."""
    print("\n" + "=" * 80)
    print("TEST 1: LearningExtractorAgent - Learning Signal Extraction")
    print("=" * 80)

    # Mock Groq client (not needed for rule-based extraction)
    mock_groq = None

    # Initialize agent
    agent = LearningExtractorAgent(
        agent_id="learner_test_001",
        session_id="session_test",
        groq_client=mock_groq,
        trace_id="test_trace_001",
    )

    # Activate agent (would subscribe to DeltaBus)
    await agent.transition_to(agent.AgentState.ACTIVE)
    print(f"✅ Agent activated: {agent.agent_id}")

    # Test 1: User Correction
    print("\n--- Test 1.1: User Correction Detection ---")
    correction_task = {
        "type": "writer_task",
        "payload": {
            "task_type": "extract_learning_signal",
            "user_input": "No, it's actually November 12, not November 10",
            "agent_response": "Your next PT is November 10 at 2pm",
            "agent_id": "healthcare_agent_001",
            "task_id": "task_001",
        },
    }
    result = await agent.process_message(correction_task)
    print(f"Signal Type: {result.get('signal_type')}")
    print(f"Confidence Delta: {result.get('confidence_delta')}")
    print(f"Status: {result.get('status')}")

    # Test 2: Positive Feedback
    print("\n--- Test 1.2: Positive Feedback Detection ---")
    positive_task = {
        "type": "writer_task",
        "payload": {
            "task_type": "extract_learning_signal",
            "user_input": "Thanks! That's perfect, exactly what I needed.",
            "agent_response": "I found 3 Italian restaurants nearby...",
            "agent_id": "researcher_agent_001",
            "task_id": "task_002",
        },
    }
    result = await agent.process_message(positive_task)
    print(f"Signal Type: {result.get('signal_type')}")
    print(f"Confidence Delta: {result.get('confidence_delta')}")
    print(f"Status: {result.get('status')}")

    # Test 3: Negative Feedback
    print("\n--- Test 1.3: Negative Feedback Detection ---")
    negative_task = {
        "type": "writer_task",
        "payload": {
            "task_type": "extract_learning_signal",
            "user_input": "No, that's wrong. That's not what I asked for.",
            "agent_response": "Here's your budget analysis...",
            "agent_id": "finance_agent_001",
            "task_id": "task_003",
        },
    }
    result = await agent.process_message(negative_task)
    print(f"Signal Type: {result.get('signal_type')}")
    print(f"Confidence Delta: {result.get('confidence_delta')}")
    print(f"Status: {result.get('status')}")

    # Test 4: Task Success
    print("\n--- Test 1.4: Task Success Signal ---")
    success_task = {
        "type": "writer_task",
        "payload": {
            "task_type": "analyze_task_performance",
            "agent_id": "planner_agent_001",
            "task_id": "task_004",
            "status": "success",
            "latency_ms": 120,
            "cost_usd": 0.005,
        },
    }
    result = await agent.process_message(success_task)
    print(f"Signal Type: {result.get('signal_type')}")
    print(f"Confidence Delta: {result.get('confidence_delta')}")
    print(f"Status: {result.get('status')}")

    # Test 5: Drift Detection
    print("\n--- Test 1.5: Drift Detection ---")
    # Simulate 10 tasks with 30% error rate (should trigger drift)
    for i in range(10):
        prediction = "November 10"
        actual = "November 10" if i < 7 else "November 12"  # 3/10 errors = 30%
        drift_task = {
            "type": "writer_task",
            "payload": {
                "task_type": "detect_drift",
                "prediction": prediction,
                "actual": actual,
                "agent_id": "healthcare_agent_001",
            },
        }
        result = await agent.process_message(drift_task)

        if i == 9:  # Last iteration
            print(f"Error Rate: {result.get('error_rate', 'N/A')}")
            print(f"Status: {result.get('status')}")
            if result.get("status") == "drift_detected":
                print(f"⚠️  DRIFT DETECTED! Confidence Delta: {result.get('confidence_delta')}")

    # Get stats
    print("\n--- Agent Statistics ---")
    stats = agent.get_stats()
    print(f"Signals Extracted: {stats.get('signals_extracted')}")
    print(f"Corrections: {stats.get('corrections_detected')}")
    print(f"Positive Feedback: {stats.get('positive_feedback_detected')}")
    print(f"Negative Feedback: {stats.get('negative_feedback_detected')}")
    print(f"Drift Signals: {stats.get('drift_signals')}")

    # Drain agent
    await agent.transition_to(agent.AgentState.DRAINING)
    print(f"\n✅ Agent drained: {agent.agent_id}")


async def test_semantic_enricher():
    """Test SemanticEnricherAgent with semantic analysis."""
    print("\n" + "=" * 80)
    print("TEST 2: SemanticEnricherAgent - Semantic Meaning Extraction")
    print("=" * 80)

    # Mock Groq client (not needed for rule-based extraction)
    mock_groq = None

    # Initialize agent
    agent = SemanticEnricherAgent(
        agent_id="semantics_test_001",
        session_id="session_test",
        groq_client=mock_groq,
        trace_id="test_trace_002",
    )

    # Activate agent
    await agent.transition_to(agent.AgentState.ACTIVE)
    print(f"✅ Agent activated: {agent.agent_id}")

    # Test 1: Complex emotional content with concepts and relationships
    print("\n--- Test 2.1: Semantic Enrichment (Complex) ---")
    complex_task = {
        "type": "writer_task",
        "payload": {
            "task_type": "enrich_semantic",
            "content": (
                "I'm frustrated about my slow knee recovery, but excited to return to running. "
                "PT helps strengthen my knee. Mom provides great emotional support."
            ),
            "session_state": {},
        },
    }
    result = await agent.process_message(complex_task)
    print(f"Enrichment ID: {result.get('enrichment_id')}")
    print(f"Concepts: {result.get('concepts')}")
    print(f"Relationships: {result.get('relationships')}")
    print(f"Affect: {result.get('affect')}")
    print(f"Salience: {result.get('salience')}")

    # Test 2: Positive content
    print("\n--- Test 2.2: Semantic Enrichment (Positive) ---")
    positive_task = {
        "type": "writer_task",
        "payload": {
            "task_type": "enrich_semantic",
            "content": "I'm so excited and happy about my progress! Running feels great again.",
            "session_state": {},
        },
    }
    result = await agent.process_message(positive_task)
    print(f"Concepts: {result.get('concepts')}")
    print(f"Affect: {result.get('affect')}")
    print(f"Salience: {result.get('salience')}")

    # Test 3: Negative content
    print("\n--- Test 2.3: Semantic Enrichment (Negative) ---")
    negative_task = {
        "type": "writer_task",
        "payload": {
            "task_type": "enrich_semantic",
            "content": "I'm really worried and anxious about this painful recovery process.",
            "session_state": {},
        },
    }
    result = await agent.process_message(negative_task)
    print(f"Concepts: {result.get('concepts')}")
    print(f"Affect: {result.get('affect')}")
    print(f"Salience: {result.get('salience')}")

    # Test 4: User KG Update
    print("\n--- Test 2.4: User KG Update ---")
    kg_task = {
        "type": "writer_task",
        "payload": {
            "task_type": "update_kg",
            "enrichment_id": "enrich_test_001",
            "concepts": ["recovery", "knee", "running", "PT"],
            "relationships": [
                {
                    "from_concept": "PT",
                    "to_concept": "knee",
                    "relation_type": "strengthens",
                    "strength": 0.9,
                },
                {
                    "from_concept": "knee",
                    "to_concept": "running",
                    "relation_type": "enables",
                    "strength": 0.8,
                },
            ],
        },
    }
    result = await agent.process_message(kg_task)
    print(f"Nodes Added: {result.get('nodes_added')}")
    print(f"Edges Added: {result.get('edges_added')}")
    print(f"Status: {result.get('status')}")

    # Get stats
    print("\n--- Agent Statistics ---")
    stats = agent.get_stats()
    print(f"Enrichments Created: {stats.get('enrichments_created')}")
    print(f"Concepts Extracted: {stats.get('concepts_extracted')}")
    print(f"Relationships Extracted: {stats.get('relationships_extracted')}")
    print(f"KG Nodes Added: {stats.get('kg_nodes_added')}")
    print(f"KG Edges Added: {stats.get('kg_edges_added')}")

    # Drain agent
    await agent.transition_to(agent.AgentState.DRAINING)
    print(f"\n✅ Agent drained: {agent.agent_id}")


async def main():
    """Run all tests."""
    print("\n🧪 Writer Agents Test Suite")
    print("Testing LearningExtractorAgent and SemanticEnricherAgent")

    try:
        # Test LearningExtractorAgent
        await test_learning_extractor()

        # Test SemanticEnricherAgent
        await test_semantic_enricher()

        print("\n" + "=" * 80)
        print("✅ ALL TESTS COMPLETED SUCCESSFULLY")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
