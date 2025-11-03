"""
Test suite for Question Queue integration

Tests async question routing with parallel agent execution.
Part of M7 Epic 7.1: Question Collection During Execution
"""

import asyncio
from typing import Any, Dict, Optional

from agent_base import Agent, AgentContext, AgentResponse
from agent_spawn_wrapper import AgentSpawnWrapper
from dag_builder import DAGBuilder
from dag_executor import DAGExecutor
from question_queue import QuestionQueue

# ============================================================================
# MOCK AGENT THAT ASKS CLARIFICATION QUESTIONS
# ============================================================================


class QuestioningAgent(Agent):
    """Mock agent that asks clarification questions"""

    def __init__(
        self,
        agent_type: str,
        question_to_ask: Optional[str] = None,
        required_data: Optional[list] = None,
    ):
        """Initialize questioning agent"""
        super().__init__(agent_id=f"mock_{agent_type}", agent_type=agent_type, llm_provider=None)
        self.question_to_ask = question_to_ask
        self.required_data_list = required_data or []

    def get_required_tools(self) -> list:
        """Return empty tool list"""
        return []

    async def execute(self, context: AgentContext) -> AgentResponse:
        """Execute agent with optional clarification question"""
        # Simulate some work
        await asyncio.sleep(0.05)

        result_data = {"agent_type": self.agent_type}

        # If agent needs clarification, ask user
        if self.question_to_ask:
            print(f"[{self.agent_type}] Asking question: {self.question_to_ask}")
            answer = await self.ask_user(self.question_to_ask, self.required_data_list)
            print(f"[{self.agent_type}] Got answer: {answer}")
            result_data["clarification_answer"] = answer

        return AgentResponse(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            status="completed",
            result=result_data,
            latency_ms=50.0,
        )


class QuestioningAgentSpawnWrapper(AgentSpawnWrapper):
    """Spawn wrapper that creates questioning agents"""

    def __init__(self, questions_config: Dict[str, tuple]):
        """
        Initialize spawn wrapper with question config.

        Args:
            questions_config: Dict of agent_type → (question, required_data)
        """
        self.questions_config = questions_config
        self.spawned_agents = []

    async def spawn_agent(
        self,
        agent_type: str,
        user_input: str = "",
        tools: Optional[list] = None,
        user_id: str = "user",
        user_profile: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[list] = None,
        clarification_history: Optional[list] = None,
    ) -> Agent:
        """Spawn questioning agent"""
        question, required_data = self.questions_config.get(agent_type, (None, None))

        agent = QuestioningAgent(
            agent_type=agent_type, question_to_ask=question, required_data=required_data
        )

        self.spawned_agents.append(agent)
        return agent


# ============================================================================
# TEST CASES
# ============================================================================


async def test_single_agent_question():
    """Test single agent asking clarification question"""
    print("\n=== Test 1: Single Agent Question ===")

    # Create plan with one agent that asks a question
    plan = {
        "steps": [
            {
                "id": "s1",
                "agent": "booking_agent",
                "description": "Book reservation",
                "needs": [],
                "tools": [],
            },
        ]
    }

    # Build DAG
    builder = DAGBuilder()
    dag = builder.build_from_expanded_plan(plan)

    # Configure agent to ask question
    questions_config = {"booking_agent": ("What date would you like to book?", ["date"])}
    spawn_wrapper = QuestioningAgentSpawnWrapper(questions_config)

    # Create question queue
    question_queue = QuestionQueue()

    # Create executor with question queue
    executor = DAGExecutor(spawn_wrapper, question_queue=question_queue, max_concurrent_nodes=5)

    # Start execution in background
    async def run_execution():
        results = await executor.execute(dag)
        return results

    execution_task = asyncio.create_task(run_execution())

    # Wait for question to appear
    await asyncio.sleep(0.2)

    # Check for pending questions
    pending = question_queue.get_pending_questions()
    assert len(pending) == 1
    assert "date" in pending[0].question.lower()

    print(f"Found question: {pending[0].question}")

    # Answer the question
    await question_queue.submit_answer(pending[0].node_id, "November 8th")

    # Wait for execution to complete
    results = await execution_task

    # Validate
    assert len(results) == 1
    assert results["s1"].status == "completed"
    assert results["s1"].result["clarification_answer"] == "November 8th"

    print("✅ Single agent question test passed")


async def test_multiple_parallel_questions():
    """Test multiple agents asking questions in parallel"""
    print("\n=== Test 2: Multiple Parallel Questions ===")

    # Create plan with two parallel agents that both ask questions
    plan = {
        "steps": [
            {"id": "s1", "agent": "booking_agent", "description": "Book", "needs": [], "tools": []},
            {
                "id": "s2",
                "agent": "travel_agent",
                "description": "Travel",
                "needs": [],
                "tools": [],
            },
        ]
    }

    # Build DAG
    builder = DAGBuilder()
    dag = builder.build_from_expanded_plan(plan)

    # Configure both agents to ask questions
    questions_config = {
        "booking_agent": ("What date would you like to book?", ["date"]),
        "travel_agent": ("How many people are traveling?", ["num_people"]),
    }
    spawn_wrapper = QuestioningAgentSpawnWrapper(questions_config)

    # Create question queue
    question_queue = QuestionQueue()

    # Create executor with question queue
    executor = DAGExecutor(spawn_wrapper, question_queue=question_queue, max_concurrent_nodes=5)

    # Start execution in background
    execution_task = asyncio.create_task(executor.execute(dag))

    # Wait for questions to accumulate
    await asyncio.sleep(0.3)

    # Check for pending questions
    pending = question_queue.get_pending_questions()
    assert len(pending) == 2

    print("Found questions:")
    for i, q in enumerate(pending, 1):
        print(f"  {i}. [{q.agent_type}] {q.question}")

    # Answer all questions at once (batch)
    answers = {pending[0].node_id: "November 8th", pending[1].node_id: "2 people"}
    await question_queue.submit_answers(answers)

    # Wait for execution to complete
    results = await execution_task

    # Validate
    assert len(results) == 2
    assert all(r.status == "completed" for r in results.values())

    # Check answers were received
    for node_id, result in results.items():
        assert "clarification_answer" in result.result
        print(f"  {node_id}: {result.result['clarification_answer']}")

    print("✅ Multiple parallel questions test passed")


async def test_sequential_with_questions():
    """Test sequential agents where each asks a question"""
    print("\n=== Test 3: Sequential Agents with Questions ===")

    # Create plan with sequential agents
    plan = {
        "steps": [
            {
                "id": "s1",
                "agent": "date_agent",
                "description": "Get date",
                "needs": [],
                "tools": [],
            },
            {
                "id": "s2",
                "agent": "people_agent",
                "description": "Get people count",
                "needs": ["s1"],
                "tools": [],
            },
        ]
    }

    # Build DAG
    builder = DAGBuilder()
    dag = builder.build_from_expanded_plan(plan)

    # Configure both agents to ask questions
    questions_config = {
        "date_agent": ("What date?", ["date"]),
        "people_agent": ("How many people?", ["num_people"]),
    }
    spawn_wrapper = QuestioningAgentSpawnWrapper(questions_config)

    # Create question queue
    question_queue = QuestionQueue()

    # Create executor with question queue
    executor = DAGExecutor(spawn_wrapper, question_queue=question_queue, max_concurrent_nodes=5)

    # Start execution in background
    execution_task = asyncio.create_task(executor.execute(dag))

    # Answer first question
    await asyncio.sleep(0.2)
    pending = question_queue.get_pending_questions()
    assert len(pending) == 1
    print(f"Question 1: {pending[0].question}")
    await question_queue.submit_answer(pending[0].node_id, "November 8th")

    # Answer second question
    await asyncio.sleep(0.2)
    pending = question_queue.get_pending_questions()
    assert len(pending) == 1
    print(f"Question 2: {pending[0].question}")
    await question_queue.submit_answer(pending[0].node_id, "3 people")

    # Wait for execution to complete
    results = await execution_task

    # Validate
    assert len(results) == 2
    assert all(r.status == "completed" for r in results.values())

    print("✅ Sequential agents with questions test passed")


# ============================================================================
# RUN ALL TESTS
# ============================================================================


async def run_all_tests():
    """Run all test cases"""
    print("=" * 60)
    print("QUESTION QUEUE INTEGRATION TEST SUITE")
    print("=" * 60)

    try:
        await test_single_agent_question()
        await test_multiple_parallel_questions()
        await test_sequential_with_questions()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(run_all_tests())
