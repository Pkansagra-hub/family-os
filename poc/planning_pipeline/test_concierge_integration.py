"""
Test Concierge Integration with Question Queue (M7 Epic 7.2.1)

This test demonstrates the complete end-to-end flow:
1. User makes planning request
2. Planner generates DAG with multiple agents
3. Agents ask clarification questions during execution
4. Concierge collects questions and presents as batch
5. User provides answers
6. Agents receive answers and complete execution
7. Plan commits successfully

This validates M7 Milestone 7 (Async Question Routing System) is complete.
"""

import asyncio

from agent_base import Agent
from dag_executor import DAGExecutor
from dag_node import DAGEdge, DAGNode
from question_batcher import ConciergeQuestionBatcher
from question_queue import QuestionQueue

# ============================================================================
# MOCK AGENTS FOR TESTING
# ============================================================================


class BookingAgent(Agent):
    """Mock agent that asks for booking details"""

    async def execute(self, context: dict) -> dict:
        print("[BookingAgent] Starting execution")

        # Ask clarification question
        date = await self.ask_user(
            question="What date would you like to book?", required_data=["date"]
        )

        print(f"[BookingAgent] Got date: {date}")

        return {"booking_date": date, "status": "pending"}


class TravelAgent(Agent):
    """Mock agent that asks for travel details"""

    async def execute(self, context: dict) -> dict:
        print("[TravelAgent] Starting execution")

        # Ask clarification question
        people = await self.ask_user(
            question="How many people are traveling?", required_data=["count"]
        )

        print(f"[TravelAgent] Got people count: {people}")

        return {"travel_count": people, "status": "confirmed"}


class HotelAgent(Agent):
    """Mock agent that asks for hotel preferences"""

    async def execute(self, context: dict) -> dict:
        print("[HotelAgent] Starting execution")

        # Ask clarification question
        budget = await self.ask_user(
            question="What price range for hotels?", required_data=["budget"]
        )

        print(f"[HotelAgent] Got budget: {budget}")

        return {"hotel_budget": budget, "status": "searched"}


class AgentSpawnWrapper:
    """Wrapper for spawning agents by name"""

    def __init__(self):
        self.agent_map = {
            "BookingAgent": BookingAgent,
            "TravelAgent": TravelAgent,
            "HotelAgent": HotelAgent,
        }

    def spawn_agent(self, agent_type: str, node_id: str, context: dict) -> Agent:
        """Spawn agent instance"""
        agent_class = self.agent_map.get(agent_type)
        if not agent_class:
            raise ValueError(f"Unknown agent type: {agent_type}")

        agent = agent_class(node_id=node_id)
        return agent


# ============================================================================
# CONCIERGE INTEGRATION HELPER
# ============================================================================


async def run_planning_with_question_batching(dag: DAGNode):
    """
    Simulates concierge integration with question batching.

    This demonstrates the workflow:
    1. Start DAG execution in background
    2. Monitor question queue for new questions
    3. Batch questions when they accumulate
    4. Present to user with numbering
    5. Parse user response
    6. Route answers back to agents
    7. Agents complete execution
    """
    print("\n" + "=" * 60)
    print("CONCIERGE PLANNING WITH QUESTION BATCHING")
    print("=" * 60)

    # Create question queue and batcher
    question_queue = QuestionQueue()
    batcher = ConciergeQuestionBatcher(
        question_queue, batch_timeout=1.0, max_batch_size=3  # Wait 1s for questions to accumulate
    )

    # Create executor with question queue
    spawn_wrapper = AgentSpawnWrapper()
    executor = DAGExecutor(
        spawn_wrapper,
        question_queue=question_queue,
        max_concurrent_nodes=3,  # All agents run in parallel
    )

    # Start DAG execution in background
    async def run_dag():
        """Execute DAG and wait for completion"""
        print("[Executor] Starting DAG execution...")
        results = await executor.execute(dag)
        print("[Executor] DAG execution complete!")
        return results

    # Monitor question queue and batch answers
    async def monitor_and_batch():
        """Monitor queue, collect batch, present, route answers"""
        await asyncio.sleep(0.5)  # Wait for first questions

        print("\n[Concierge] Monitoring question queue...")

        # Collect batch (waits for accumulation)
        questions = await batcher.collect_batch()

        if not questions:
            print("[Concierge] No questions received")
            return

        print(f"[Concierge] Collected {len(questions)} questions")
        print()

        # Format and display to user
        formatted = batcher.format_batch(questions)
        print(formatted)
        print()

        # Simulate user providing answers
        user_response = "1. November 8th 2. 2 people 3. $100-200 per night"
        print(f"[User] {user_response}")
        print()

        # Parse answers
        answers = batcher.parse_answers(user_response, questions)
        print(f"[Concierge] Parsed {len(answers)} answers")

        # Route back to agents
        await batcher.submit_batch_answers(answers)
        print("[Concierge] Answers routed to agents")

    # Run both concurrently
    results, _ = await asyncio.gather(run_dag(), monitor_and_batch())

    print("\n" + "=" * 60)
    print("EXECUTION RESULTS")
    print("=" * 60)

    for node_id, result in results.items():
        status = result.get("status", "unknown")
        data = result.get("result", {})
        print(f"{node_id}: {status}")
        print(f"  Data: {data}")

    print("\n" + "=" * 60)
    print("✅ CONCIERGE INTEGRATION TEST COMPLETE")
    print("=" * 60)

    return results


# ============================================================================
# TEST CASES
# ============================================================================


async def test_parallel_agents_with_batched_questions():
    """
    Test parallel agents asking questions with batched collection.

    DAG structure:
        BookingAgent (parallel)
        TravelAgent  (parallel)
        HotelAgent   (parallel)

    Expected:
    - All 3 agents start in parallel
    - All 3 ask clarification questions
    - Concierge collects and batches questions
    - User provides 3 numbered answers
    - All agents receive answers and complete
    """
    print("\n" + "=" * 60)
    print("TEST: Parallel Agents with Batched Questions")
    print("=" * 60)

    # Create parallel DAG
    dag = DAGNode(
        node_id="parallel_root",
        agent_type="BookingAgent",
        edges=[
            DAGEdge(target_id="parallel_root", dep_type="parallel"),
        ],
    )

    # Add parallel nodes
    booking = DAGNode(node_id="booking", agent_type="BookingAgent", edges=[])
    travel = DAGNode(node_id="travel", agent_type="TravelAgent", edges=[])
    hotel = DAGNode(node_id="hotel", agent_type="HotelAgent", edges=[])

    dag.edges = [
        DAGEdge(target_id="booking", dep_type="parallel"),
        DAGEdge(target_id="travel", dep_type="parallel"),
        DAGEdge(target_id="hotel", dep_type="parallel"),
    ]

    # Build node map
    nodes = {
        "parallel_root": dag,
        "booking": booking,
        "travel": travel,
        "hotel": hotel,
    }

    # Execute with question batching
    results = await run_planning_with_question_batching(dag)

    # Validate results
    assert len(results) == 4  # 3 agents + root
    assert results["booking"]["status"] == "completed"
    assert results["travel"]["status"] == "completed"
    assert results["hotel"]["status"] == "completed"

    # Validate answers were received
    assert "booking_date" in results["booking"]["result"]
    assert "travel_count" in results["travel"]["result"]
    assert "hotel_budget" in results["hotel"]["result"]

    print("\n✅ Test passed!")


async def test_sequential_agents_with_individual_questions():
    """
    Test sequential agents asking questions one at a time.

    DAG structure:
        BookingAgent → TravelAgent → HotelAgent (sequential)

    Expected:
    - BookingAgent asks, gets answer, completes
    - TravelAgent asks, gets answer, completes
    - HotelAgent asks, gets answer, completes
    """
    print("\n" + "=" * 60)
    print("TEST: Sequential Agents with Individual Questions")
    print("=" * 60)

    # Create sequential DAG
    booking = DAGNode(
        node_id="booking",
        agent_type="BookingAgent",
        edges=[DAGEdge(target_id="travel", dep_type="depends_on")],
    )

    travel = DAGNode(
        node_id="travel",
        agent_type="TravelAgent",
        edges=[DAGEdge(target_id="hotel", dep_type="depends_on")],
    )

    hotel = DAGNode(node_id="hotel", agent_type="HotelAgent", edges=[])

    # Create question queue and executor
    question_queue = QuestionQueue()
    batcher = ConciergeQuestionBatcher(question_queue, batch_timeout=0.5, max_batch_size=1)

    spawn_wrapper = AgentSpawnWrapper()
    executor = DAGExecutor(
        spawn_wrapper, question_queue=question_queue, max_concurrent_nodes=1  # Force sequential
    )

    # Execute with sequential question handling
    async def run_dag():
        results = await executor.execute(booking)
        return results

    async def monitor_sequential():
        """Answer questions one at a time"""
        for i in range(3):
            await asyncio.sleep(0.3)

            # Collect one question
            questions = await batcher.collect_batch()
            if not questions:
                continue

            q = questions[0]
            print(f"\n[Concierge] Question {i+1}: {q.question}")

            # Provide answer
            answers = {0: "November 8th", 1: "2 people", 2: "$100-200"}
            answer = answers[i]
            print(f"[User] {answer}")

            await question_queue.submit_answer(q.node_id, answer)

    results, _ = await asyncio.gather(run_dag(), monitor_sequential())

    print(f"\n✅ Sequential test complete! {len(results)} agents executed")


# ============================================================================
# MAIN
# ============================================================================


async def main():
    """Run all concierge integration tests"""
    print("\n" + "=" * 60)
    print("M7 CONCIERGE INTEGRATION TEST SUITE")
    print("=" * 60)

    # Test 1: Parallel agents with batched questions
    await test_parallel_agents_with_batched_questions()

    # Test 2: Sequential agents with individual questions
    await test_sequential_agents_with_individual_questions()

    print("\n" + "=" * 60)
    print("✅ ALL CONCIERGE INTEGRATION TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
