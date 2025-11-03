"""
Question Batching Logic for Concierge Integration (M7 Epic 7.1.3)

This module collects multiple clarification questions from parallel agents
and presents them as a single numbered batch to minimize user interruption.

Key Features:
- Wait for question accumulation (2s timeout or 3 questions)
- Present questions as numbered list
- Parse multi-part answers (numbered responses)
- Route answers back to correct agents
- Handle partial answers (skipped questions)

Example:
    Questions from agents:
    1. [booking_agent] What date would you like to book?
    2. [travel_agent] How many people are traveling?
    3. [hotel_agent] What price range?

    User response:
    1. November 8th
    2. 2 people
    3. skip

Research Foundation:
- Batching reduces context switching cost (Card et al., 2001)
- Multi-item presentation improves decision efficiency (Payne et al., 1993)
- Numbered format reduces parsing ambiguity (ISO 9241-110:2020)
"""

import asyncio
from dataclasses import dataclass
from typing import Dict, List, Optional

from question_queue import ClarificationQuestion, QuestionQueue


@dataclass
class BatchedAnswer:
    """Parsed answer from multi-part user response."""

    node_id: str  # Changed from question_id to match ClarificationQuestion
    answer: Optional[str]  # None if skipped
    skipped: bool


class ConciergeQuestionBatcher:
    """
    Collects questions from parallel agents and presents as numbered batch.

    The batcher waits for questions to accumulate (either 2s timeout or 3 questions),
    then presents them as a single numbered list to minimize user interruption.

    Attributes:
        question_queue: Shared queue for collecting questions
        batch_timeout: Time to wait for question accumulation (seconds)
        max_batch_size: Maximum questions per batch
    """

    def __init__(
        self, question_queue: QuestionQueue, batch_timeout: float = 2.0, max_batch_size: int = 3
    ):
        """
        Initialize question batcher.

        Args:
            question_queue: Shared queue for collecting questions
            batch_timeout: Time to wait for accumulation (default: 2s)
            max_batch_size: Max questions per batch (default: 3)
        """
        self.question_queue = question_queue
        self.batch_timeout = batch_timeout
        self.max_batch_size = max_batch_size

    async def collect_batch(self) -> List[ClarificationQuestion]:
        """
        Wait for questions to accumulate into a batch.

        Waits until either:
        - batch_timeout seconds elapse
        - max_batch_size questions accumulated

        Returns:
            List of accumulated questions (may be empty if timeout with no questions)
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            # Get current pending questions (not async)
            pending = self.question_queue.get_pending_questions()

            # Check if we have enough questions for a batch
            if len(pending) >= self.max_batch_size:
                return pending[: self.max_batch_size]

            # Check if timeout elapsed
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= self.batch_timeout and pending:
                return pending

            # Check if timeout elapsed with no questions
            if elapsed >= self.batch_timeout:
                return []

            # Wait a bit before checking again (100ms polling)
            await asyncio.sleep(0.1)

    def format_batch(self, questions: List[ClarificationQuestion]) -> str:
        """
        Format questions as numbered list for display.

        Example output:
            Multiple clarification questions:
            1. [booking_agent] What date would you like to book?
            2. [travel_agent] How many people are traveling?
            3. [hotel_agent] What price range?

            Please answer with numbered responses:
            1. <your answer>
            2. <your answer>
            3. <your answer>

            (Type 'skip' for any question you want to skip)

        Args:
            questions: List of questions to format

        Returns:
            Formatted multi-line string for display
        """
        lines = ["Multiple clarification questions:"]

        for i, q in enumerate(questions, 1):
            lines.append(f"{i}. [{q.agent_type}] {q.question}")

        lines.append("")
        lines.append("Please answer with numbered responses:")
        for i in range(1, len(questions) + 1):
            lines.append(f"{i}. <your answer>")

        lines.append("")
        lines.append("(Type 'skip' for any question you want to skip)")

        return "\n".join(lines)

    def parse_answers(
        self, user_response: str, questions: List[ClarificationQuestion]
    ) -> Dict[str, BatchedAnswer]:
        """
        Parse numbered answers from user response.

        Supports multiple formats:
        - "1. answer 2. answer 3. skip"
        - "1. answer\n2. answer\n3. skip"
        - "1) answer 2) answer 3) skip"

        Args:
            user_response: Multi-part user response with numbered answers
            questions: Original questions for mapping

        Returns:
            Dict mapping node_id to BatchedAnswer
        """
        answers: Dict[str, BatchedAnswer] = {}

        # Use regex to split on number patterns (1., 2., 3., etc.)
        import re

        # Split on patterns like "1.", "2.", "3)" but keep them
        parts = re.split(r"(\d+[\.\):])\s*", user_response)

        # Process parts in pairs (number, answer)
        for i in range(1, len(parts), 2):
            if i + 1 < len(parts):
                num_str = parts[i]
                answer_text = parts[i + 1].strip()

                # Extract number
                match = re.search(r"\d+", num_str)
                if not match:
                    continue
                number = int(match.group())

                # Store answer
                self._store_answer(answers, questions, number, answer_text)

        # Mark unanswered questions as skipped
        for q in questions:
            if q.node_id not in answers:
                answers[q.node_id] = BatchedAnswer(node_id=q.node_id, answer=None, skipped=True)

        return answers

    def _store_answer(
        self,
        answers: Dict[str, BatchedAnswer],
        questions: List[ClarificationQuestion],
        number: int,
        text: str,
    ):
        """Helper to store parsed answer in dictionary."""
        if 1 <= number <= len(questions):
            q = questions[number - 1]

            # Check if user typed "skip"
            if text.lower() == "skip":
                answers[q.node_id] = BatchedAnswer(node_id=q.node_id, answer=None, skipped=True)
            else:
                answers[q.node_id] = BatchedAnswer(node_id=q.node_id, answer=text, skipped=False)

    async def submit_batch_answers(self, answers: Dict[str, BatchedAnswer]):
        """
        Route parsed answers back to agents via question queue.

        Args:
            answers: Dict of node_id -> BatchedAnswer
        """
        answer_dict = {}
        skip_list = []

        for node_id, batched in answers.items():
            if batched.skipped:
                skip_list.append(node_id)
            else:
                answer_dict[node_id] = batched.answer

        # Submit answers to queue
        if answer_dict:
            await self.question_queue.submit_answers(answer_dict)

        # Mark skipped questions
        for node_id in skip_list:
            await self.question_queue.skip_question(node_id)

    async def collect_and_answer(self) -> int:
        """
        Complete workflow: collect batch, format, parse, route answers.

        This is the main entry point for concierge integration.

        Returns:
            Number of questions processed
        """
        # Wait for questions to accumulate
        questions = await self.collect_batch()

        if not questions:
            return 0

        # Format for display
        formatted = self.format_batch(questions)
        print(formatted)

        # Get user response (in real integration, this comes from Rich input)
        user_response = input("\nYour answers: ")

        # Parse answers
        answers = self.parse_answers(user_response, questions)

        # Route back to agents
        await self.submit_batch_answers(answers)

        return len(questions)


# Example usage
async def example():
    """Demonstrate question batching with 3 parallel agents."""
    from question_queue import QuestionQueue

    queue = QuestionQueue()
    batcher = ConciergeQuestionBatcher(queue, batch_timeout=1.0, max_batch_size=3)

    # Simulate 3 agents asking questions in parallel
    async def agent1():
        question = await queue.add_question(
            node_id="booking_agent",
            agent_type="BookingAgent",
            question="What date would you like to book?",
            required_data=["date"],
        )
        answer = await queue.wait_for_answer(question.node_id)
        print(f"[Agent 1] Got answer: {answer}")

    async def agent2():
        await asyncio.sleep(0.3)  # Slight delay
        question = await queue.add_question(
            node_id="travel_agent",
            agent_type="TravelAgent",
            question="How many people are traveling?",
            required_data=["count"],
        )
        answer = await queue.wait_for_answer(question.node_id)
        print(f"[Agent 2] Got answer: {answer}")

    async def agent3():
        await asyncio.sleep(0.5)  # Slight delay
        question = await queue.add_question(
            node_id="hotel_agent",
            agent_type="HotelAgent",
            question="What price range?",
            required_data=["budget"],
        )
        answer = await queue.wait_for_answer(question.node_id)
        print(f"[Agent 3] Got answer: {answer}")

    async def concierge():
        """Concierge collects questions and routes answers."""
        await asyncio.sleep(0.2)  # Wait for first question

        # Collect batch (waits up to 1s for more questions)
        questions = await batcher.collect_batch()
        print(f"\n[Concierge] Collected {len(questions)} questions")

        # Format and display
        formatted = batcher.format_batch(questions)
        print(formatted)

        # Simulate user response
        user_response = "1. November 8th 2. 2 people 3. $100-200"
        print(f"\n[User] {user_response}")

        # Parse and route
        answers = batcher.parse_answers(user_response, questions)
        await batcher.submit_batch_answers(answers)

        print("[Concierge] Answers routed back to agents")

    # Run all in parallel
    await asyncio.gather(agent1(), agent2(), agent3(), concierge())

    print("\n" + "=" * 60)
    print("✅ Question batching example complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(example())
