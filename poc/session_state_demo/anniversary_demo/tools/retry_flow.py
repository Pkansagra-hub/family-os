"""
Retry-After-Clarification Flow
===============================

Orchestrates the complete cycle:
1. LLM suggests tool call with missing params
2. System detects gaps
3. System asks user for clarification
4. User provides missing info
5. System retries tool call with merged params
6. Tool executes successfully

This module integrates:
- ValidationMiddleware (tracks pending calls)
- ClarificationGenerator (creates natural questions)
- LLMGapDetector (identifies what's missing)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from poc.session_state_demo.anniversary_demo.tools.clarification import ClarificationGenerator
from poc.session_state_demo.anniversary_demo.tools.gap_detection import LLMGapDetector
from poc.session_state_demo.anniversary_demo.tools.registry import get_registry
from poc.session_state_demo.anniversary_demo.tools.validation import ToolCall, ToolCallValidator


@dataclass
class PendingClarification:
    """Tracks a pending clarification request."""

    call_id: str
    tool_name: str
    original_params: Dict[str, Any]
    missing_params: List[str]
    user_request: str
    clarification_question: str
    param_hints: Dict[str, str]
    retry_count: int = 0
    max_retries: int = 3


@dataclass
class RetryResult:
    """Result of a retry attempt."""

    success: bool
    tool_call: Optional[ToolCall] = None
    still_missing: List[str] = field(default_factory=list)
    follow_up_question: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ToolAttemptResult:
    """Result of attempting to process a tool call."""

    can_execute: bool
    needs_clarification: bool
    tool_call: Optional[ToolCall] = None
    call_id: Optional[str] = None
    question: Optional[str] = None
    missing_params: List[str] = field(default_factory=list)
    param_hints: Dict[str, str] = field(default_factory=dict)
    tool_name: Optional[str] = None


class RetryOrchestrator:
    """
    Orchestrates the retry-after-clarification flow.

    Usage:
        orchestrator = RetryOrchestrator()

        # Step 1: Process LLM response
        result = orchestrator.process_tool_attempt(
            tool_name="book_restaurant",
            params={"restaurant_name": "Harvest Table"},
            user_request="Book dinner at Harvest Table"
        )

        if result.needs_clarification:
            print(result.question)  # "What time and date, and for how many?"

        # Step 2: User provides info
        retry = orchestrator.handle_clarification_response(
            call_id=result.call_id,
            user_response="7pm on Saturday for 2 people",
            extracted_params={"time": "7pm", "date": "Saturday", "party_size": 2}
        )

        if retry.success:
            execute(retry.tool_call)
    """

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        validator: Optional[ToolCallValidator] = None,
        gap_detector: Optional[LLMGapDetector] = None,
        clarification_generator: Optional[ClarificationGenerator] = None,
    ):
        self.llm_client = llm_client
        self.validator = validator or ToolCallValidator()
        self.gap_detector = gap_detector or LLMGapDetector()
        self.clarification_generator = clarification_generator or ClarificationGenerator(
            llm_client=llm_client, gap_detector=self.gap_detector
        )
        self.registry = get_registry()

        # Pending clarifications by call_id
        self._pending: Dict[str, PendingClarification] = {}

    def set_session_context(self, context: Dict[str, Any]) -> None:
        """Set session context for context-aware handling."""
        self.gap_detector.set_session_context(context)
        self.clarification_generator.set_session_context(context)

    def process_tool_attempt(
        self,
        tool_name: str,
        params: Dict[str, Any],
        user_request: str,
        call_id: Optional[str] = None,
    ) -> "ToolAttemptResult":
        """
        Process a tool call attempt, detecting gaps and generating clarification.

        Returns a result indicating if the tool can execute or needs clarification.
        """
        import uuid

        call_id = call_id or str(uuid.uuid4())[:8]

        # Validate against schema
        tool_call = ToolCall(name=tool_name, arguments=params, call_id=call_id)
        validated = self.validator.validate_call(tool_call)

        if validated.can_execute:
            return ToolAttemptResult(
                can_execute=True,
                needs_clarification=False,
                tool_call=tool_call,
            )

        # Gap detected - analyze and generate clarification
        gap = self.gap_detector.analyze_tool_call(tool_name, params, user_request)

        clarification = self.clarification_generator.from_gap_analysis(gap, user_request)

        # Store pending
        pending = PendingClarification(
            call_id=call_id,
            tool_name=tool_name,
            original_params=params.copy(),
            missing_params=gap.missing_params,
            user_request=user_request,
            clarification_question=clarification.question,
            param_hints=clarification.param_hints,
        )
        self._pending[call_id] = pending

        return ToolAttemptResult(
            can_execute=False,
            needs_clarification=True,
            call_id=call_id,
            question=clarification.question,
            missing_params=gap.missing_params,
            param_hints=clarification.param_hints,
            tool_name=tool_name,
        )

    def handle_clarification_response(
        self,
        call_id: str,
        user_response: str,
        extracted_params: Dict[str, Any],
    ) -> RetryResult:
        """
        Handle user's response to a clarification question.

        Args:
            call_id: The call ID from the original attempt
            user_response: The raw user response text
            extracted_params: Parameters extracted from user response (by LLM)

        Returns:
            RetryResult indicating success or what's still missing
        """
        if call_id not in self._pending:
            return RetryResult(
                success=False,
                error=f"No pending clarification for call_id: {call_id}",
            )

        pending = self._pending[call_id]

        # Merge original + new params
        merged_params = {**pending.original_params, **extracted_params}

        # Re-validate
        tool_call = ToolCall(
            name=pending.tool_name,
            arguments=merged_params,
            call_id=call_id,
        )
        validated = self.validator.validate_call(tool_call)

        if validated.can_execute:
            # Success - remove from pending
            del self._pending[call_id]
            return RetryResult(
                success=True,
                tool_call=tool_call,
            )

        # Still missing params
        pending.retry_count += 1

        if pending.retry_count >= pending.max_retries:
            del self._pending[call_id]
            return RetryResult(
                success=False,
                error=f"Max retries ({pending.max_retries}) exceeded",
                still_missing=validated.validation.missing_required,
            )

        # Generate follow-up question
        still_missing = validated.validation.missing_required
        pending.missing_params = still_missing
        pending.original_params = merged_params  # Update with partial info

        descriptions = self.registry.get_missing_param_descriptions(
            pending.tool_name, still_missing
        )
        follow_up = self.clarification_generator.generate_sync(
            tool_name=pending.tool_name,
            missing_params=still_missing,
            param_descriptions=descriptions,
            user_request=f"(continued) {user_response}",
        )

        pending.clarification_question = follow_up.question

        return RetryResult(
            success=False,
            still_missing=still_missing,
            follow_up_question=follow_up.question,
        )

    def get_pending(self, call_id: str) -> Optional[PendingClarification]:
        """Get a pending clarification by call ID."""
        return self._pending.get(call_id)

    def get_all_pending(self) -> Dict[str, PendingClarification]:
        """Get all pending clarifications."""
        return self._pending.copy()

    def cancel_pending(self, call_id: str) -> bool:
        """Cancel a pending clarification."""
        if call_id in self._pending:
            del self._pending[call_id]
            return True
        return False

    def clear_all_pending(self) -> int:
        """Clear all pending clarifications. Returns count cleared."""
        count = len(self._pending)
        self._pending.clear()
        return count


def create_retry_orchestrator(
    llm_client: Optional[Any] = None,
) -> RetryOrchestrator:
    """Create a configured retry orchestrator."""
    return RetryOrchestrator(llm_client=llm_client)
