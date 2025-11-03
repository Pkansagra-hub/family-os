"""
Question Queue - Async clarification routing for parallel agents

Enables multiple agents to ask clarification questions without blocking each other.
Questions are collected in a shared queue and batched for user interaction.

Part of M7 Epic 7.1: Question Collection During Execution
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# ============================================================================
# CLARIFICATION QUESTION DATA STRUCTURES
# ============================================================================


class QuestionStatus(Enum):
    """Status of clarification question"""

    PENDING = "pending"  # Waiting for answer
    ANSWERED = "answered"  # Answer provided
    SKIPPED = "skipped"  # User skipped this question
    EXPIRED = "expired"  # Question timed out


@dataclass
class ClarificationQuestion:
    """
    Clarification question from an agent.

    Agents submit questions to the queue and wait for answers.
    The queue batches questions and routes answers back to agents.
    """

    node_id: str  # DAG node that asked
    agent_type: str  # Type of agent
    question: str  # Question text
    required_data: List[str]  # What data is needed
    timestamp: float  # When question was asked
    status: QuestionStatus = QuestionStatus.PENDING
    answer: Optional[str] = None  # User's answer
    answered_event: asyncio.Event = field(default_factory=asyncio.Event)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def mark_answered(self, answer: str):
        """Mark question as answered and unblock waiting agent"""
        self.answer = answer
        self.status = QuestionStatus.ANSWERED
        self.answered_event.set()

    def mark_skipped(self):
        """Mark question as skipped by user"""
        self.status = QuestionStatus.SKIPPED
        self.answered_event.set()

    def mark_expired(self):
        """Mark question as expired (timeout)"""
        self.status = QuestionStatus.EXPIRED
        self.answered_event.set()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "node_id": self.node_id,
            "agent_type": self.agent_type,
            "question": self.question,
            "required_data": self.required_data,
            "timestamp": self.timestamp,
            "status": self.status.value,
            "answer": self.answer,
            "metadata": self.metadata,
        }


# ============================================================================
# QUESTION QUEUE
# ============================================================================


class QuestionQueue:
    """
    Thread-safe queue for collecting clarification questions from parallel agents.

    Features:
    - Async operations (non-blocking)
    - Multiple agents can submit questions concurrently
    - Agents wait for answers without blocking others
    - Batch retrieval for efficient user interaction
    - Answer routing back to correct agents

    Usage:
        queue = QuestionQueue()

        # Agent submits question (in parallel with other agents)
        question = await queue.add_question(
            node_id="s1",
            agent_type="booking_agent",
            question="What date would you like to book?",
            required_data=["date"]
        )

        # Agent waits for answer (blocks this agent, not others)
        answer = await queue.wait_for_answer("s1")

        # Concierge collects all pending questions
        questions = queue.get_pending_questions()

        # Concierge submits answers
        await queue.submit_answer("s1", "November 8th")
    """

    def __init__(self, timeout: float = 300.0):
        """
        Initialize question queue.

        Args:
            timeout: Max seconds to wait for answer (default 5 minutes)
        """
        self.questions: Dict[str, ClarificationQuestion] = {}
        self.lock = asyncio.Lock()
        self.timeout = timeout

    async def add_question(
        self,
        node_id: str,
        agent_type: str,
        question: str,
        required_data: List[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ClarificationQuestion:
        """
        Add clarification question to queue.

        Args:
            node_id: ID of DAG node asking question
            agent_type: Type of agent
            question: Question text
            required_data: List of data fields needed
            metadata: Optional additional context

        Returns:
            ClarificationQuestion object
        """
        async with self.lock:
            q = ClarificationQuestion(
                node_id=node_id,
                agent_type=agent_type,
                question=question,
                required_data=required_data,
                timestamp=time.time(),
                metadata=metadata or {},
            )
            self.questions[node_id] = q
            return q

    async def wait_for_answer(self, node_id: str, timeout: Optional[float] = None) -> Optional[str]:
        """
        Wait for answer to question (blocks this agent, not others).

        Args:
            node_id: ID of node that asked question
            timeout: Max seconds to wait (uses queue default if None)

        Returns:
            Answer string, or None if skipped/expired

        Raises:
            KeyError: If node_id not in queue
            asyncio.TimeoutError: If timeout exceeded
        """
        if node_id not in self.questions:
            raise KeyError(f"No question found for node {node_id}")

        question = self.questions[node_id]
        timeout_value = timeout if timeout is not None else self.timeout

        try:
            # Wait for answer with timeout
            await asyncio.wait_for(question.answered_event.wait(), timeout=timeout_value)
            return question.answer

        except asyncio.TimeoutError:
            question.mark_expired()
            return None

    def get_pending_questions(self) -> List[ClarificationQuestion]:
        """
        Get all pending questions (not yet answered).

        Returns:
            List of pending questions, sorted by timestamp
        """
        pending = [q for q in self.questions.values() if q.status == QuestionStatus.PENDING]
        return sorted(pending, key=lambda q: q.timestamp)

    def get_all_questions(self) -> List[ClarificationQuestion]:
        """
        Get all questions regardless of status.

        Returns:
            List of all questions, sorted by timestamp
        """
        return sorted(self.questions.values(), key=lambda q: q.timestamp)

    async def submit_answer(self, node_id: str, answer: Optional[str]):
        """
        Submit answer for a question.

        Args:
            node_id: ID of node that asked question
            answer: Answer string, or None to skip
        """
        async with self.lock:
            if node_id not in self.questions:
                raise KeyError(f"No question found for node {node_id}")

            question = self.questions[node_id]

            if answer is None:
                question.mark_skipped()
            else:
                question.mark_answered(answer)

    async def skip_question(self, node_id: str):
        """
        Mark question as skipped by user.

        Args:
            node_id: ID of node that asked question
        """
        await self.submit_answer(node_id, None)

    async def submit_answers(self, answers: Dict[str, str]):
        """
        Submit multiple answers at once (batch).

        Args:
            answers: Dict of node_id → answer
        """
        for node_id, answer in answers.items():
            await self.submit_answer(node_id, answer)

    def get_question(self, node_id: str) -> Optional[ClarificationQuestion]:
        """Get question by node ID"""
        return self.questions.get(node_id)

    def clear(self):
        """Clear all questions (useful for testing)"""
        self.questions.clear()

    def get_summary(self) -> Dict[str, int]:
        """
        Get summary statistics.

        Returns:
            Dict with counts by status
        """
        summary = {
            "total": len(self.questions),
            "pending": sum(
                1 for q in self.questions.values() if q.status == QuestionStatus.PENDING
            ),
            "answered": sum(
                1 for q in self.questions.values() if q.status == QuestionStatus.ANSWERED
            ),
            "skipped": sum(
                1 for q in self.questions.values() if q.status == QuestionStatus.SKIPPED
            ),
            "expired": sum(
                1 for q in self.questions.values() if q.status == QuestionStatus.EXPIRED
            ),
        }
        return summary


# ============================================================================
# EXAMPLE USAGE
# ============================================================================


async def example_usage():
    """Example of question queue usage"""
    print("=" * 60)
    print("QUESTION QUEUE - EXAMPLE")
    print("=" * 60)

    queue = QuestionQueue()

    # Simulate two agents asking questions in parallel
    async def agent1_ask():
        print("\n[Agent 1] Asking question...")
        q = await queue.add_question(
            node_id="s1",
            agent_type="booking_agent",
            question="What date would you like to book?",
            required_data=["date"],
        )
        print(f"[Agent 1] Question submitted: {q.question}")

        # Wait for answer (blocks this agent)
        print("[Agent 1] Waiting for answer...")
        answer = await queue.wait_for_answer("s1")
        print(f"[Agent 1] Got answer: {answer}")
        return answer

    async def agent2_ask():
        print("\n[Agent 2] Asking question...")
        await asyncio.sleep(0.5)  # Simulate some work
        q = await queue.add_question(
            node_id="s2",
            agent_type="travel_agent",
            question="How many people are traveling?",
            required_data=["num_people"],
        )
        print(f"[Agent 2] Question submitted: {q.question}")

        # Wait for answer (blocks this agent)
        print("[Agent 2] Waiting for answer...")
        answer = await queue.wait_for_answer("s2")
        print(f"[Agent 2] Got answer: {answer}")
        return answer

    async def concierge_answer():
        """Simulate Concierge collecting and answering questions"""
        await asyncio.sleep(1)  # Wait for questions to accumulate

        print("\n[Concierge] Checking for questions...")
        pending = queue.get_pending_questions()
        print(f"[Concierge] Found {len(pending)} pending questions")

        for i, q in enumerate(pending, 1):
            print(f"  {i}. [{q.agent_type}] {q.question}")

        # Simulate user providing answers
        print("\n[Concierge] Submitting answers...")
        await queue.submit_answers({"s1": "November 8th", "s2": "2 people"})
        print("[Concierge] Answers submitted!")

    # Run agents and concierge in parallel
    results = await asyncio.gather(agent1_ask(), agent2_ask(), concierge_answer())

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Agent 1 answer: {results[0]}")
    print(f"Agent 2 answer: {results[1]}")
    print(f"\nQueue summary: {queue.get_summary()}")
    print("\n✅ Question queue example complete!")


if __name__ == "__main__":
    asyncio.run(example_usage())
