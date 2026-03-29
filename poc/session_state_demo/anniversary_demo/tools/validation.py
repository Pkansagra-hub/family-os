"""
Parameter Validation Layer
===========================

Validates LLM tool calls against schemas before execution.
Integrates with the ToolRegistry to detect gaps and generate clarifications.

This layer sits between the LLM response parser and tool execution:
    LLM Response -> Parse Tool Calls -> VALIDATE -> Execute or Clarify
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from poc.session_state_demo.anniversary_demo.tools.registry import (
    ToolRegistry,
    ValidationResult,
    get_registry,
)


@dataclass
class ToolCall:
    """Represents a parsed tool call from the LLM."""

    name: str
    arguments: Dict[str, Any]
    call_id: Optional[str] = None  # For tracking in multi-turn

    def __post_init__(self):
        if self.call_id is None:
            import uuid

            self.call_id = str(uuid.uuid4())[:8]


@dataclass
class ValidatedToolCall:
    """A tool call that has been validated."""

    tool_call: ToolCall
    validation: ValidationResult
    can_execute: bool
    clarification_needed: bool = False
    clarification_context: Optional[Dict[str, Any]] = None

    @classmethod
    def from_validation(
        cls, tool_call: ToolCall, validation: ValidationResult
    ) -> "ValidatedToolCall":
        """Create from a tool call and validation result."""
        return cls(
            tool_call=tool_call,
            validation=validation,
            can_execute=validation.is_valid,
            clarification_needed=validation.needs_clarification,
            clarification_context=(
                validation.get_clarification_context() if validation.needs_clarification else None
            ),
        )


@dataclass
class ValidationBatch:
    """Result of validating multiple tool calls."""

    validated_calls: List[ValidatedToolCall] = field(default_factory=list)
    all_valid: bool = True
    needs_clarification: bool = False
    clarification_contexts: List[Dict[str, Any]] = field(default_factory=list)

    def get_executable_calls(self) -> List[ValidatedToolCall]:
        """Get calls that can be executed."""
        return [c for c in self.validated_calls if c.can_execute]

    def get_blocked_calls(self) -> List[ValidatedToolCall]:
        """Get calls that are blocked due to validation failures."""
        return [c for c in self.validated_calls if not c.can_execute]

    def get_clarification_needed_calls(self) -> List[ValidatedToolCall]:
        """Get calls that need clarification."""
        return [c for c in self.validated_calls if c.clarification_needed]


class ToolCallValidator:
    """
    Validates tool calls from LLM against registered schemas.

    Usage:
        validator = ToolCallValidator()

        # Single call
        validated = validator.validate_call(ToolCall("book_restaurant", {...}))
        if validated.can_execute:
            execute(validated.tool_call)
        else:
            ask_clarification(validated.clarification_context)

        # Batch
        batch = validator.validate_batch([call1, call2, call3])
        if batch.all_valid:
            execute_all(batch.validated_calls)
    """

    def __init__(self, registry: Optional[ToolRegistry] = None):
        self.registry = registry or get_registry()

    def validate_call(self, tool_call: ToolCall) -> ValidatedToolCall:
        """Validate a single tool call."""
        validation = self.registry.validate(tool_call.name, tool_call.arguments)
        return ValidatedToolCall.from_validation(tool_call, validation)

    def validate_batch(self, tool_calls: List[ToolCall]) -> ValidationBatch:
        """Validate multiple tool calls."""
        batch = ValidationBatch()

        for call in tool_calls:
            validated = self.validate_call(call)
            batch.validated_calls.append(validated)

            if not validated.can_execute:
                batch.all_valid = False

            if validated.clarification_needed:
                batch.needs_clarification = True
                batch.clarification_contexts.append(
                    {
                        "tool_name": call.name,
                        "call_id": call.call_id,
                        "context": validated.clarification_context,
                    }
                )

        return batch

    def parse_and_validate(
        self, llm_response: Dict[str, Any]
    ) -> Tuple[ValidationBatch, Optional[str]]:
        """
        Parse tool calls from LLM response and validate.

        Returns:
            Tuple of (ValidationBatch, content_text)
        """
        tool_calls = self._parse_tool_calls(llm_response)
        content = llm_response.get("content", "")

        if not tool_calls:
            # No tool calls, just text response
            return ValidationBatch(all_valid=True), content

        batch = self.validate_batch(tool_calls)
        return batch, content

    def _parse_tool_calls(self, llm_response: Dict[str, Any]) -> List[ToolCall]:
        """Parse tool calls from LLM response format."""
        calls = []

        # Handle different response formats
        raw_calls = llm_response.get("tool_calls", [])

        for raw in raw_calls:
            if isinstance(raw, dict):
                name = raw.get("name", raw.get("function", {}).get("name", ""))
                args = raw.get("arguments", raw.get("args", {}))

                # Handle string arguments (sometimes LLMs return JSON strings)
                if isinstance(args, str):
                    import json

                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}

                if name:
                    calls.append(ToolCall(name=name, arguments=args))

        return calls

    def get_missing_params_summary(self, validated: ValidatedToolCall) -> Dict[str, str]:
        """Get a summary of missing parameters with descriptions."""
        if not validated.clarification_needed:
            return {}

        return self.registry.get_missing_param_descriptions(
            validated.tool_call.name, validated.validation.missing_required
        )


class ValidationMiddleware:
    """
    Middleware that wraps tool execution with validation.

    Sits between the Concierge FSM and tool execution:
        User Input -> Concierge -> LLM -> [ValidationMiddleware] -> Tools
    """

    def __init__(
        self,
        validator: Optional[ToolCallValidator] = None,
        on_clarification_needed: Optional[callable] = None,
    ):
        self.validator = validator or ToolCallValidator()
        self.on_clarification_needed = on_clarification_needed

        # Track pending clarifications for retry
        self._pending_clarifications: Dict[str, ValidatedToolCall] = {}

    def process_llm_response(
        self, llm_response: Dict[str, Any]
    ) -> Tuple[List[ToolCall], bool, Optional[Dict[str, Any]]]:
        """
        Process an LLM response, validating any tool calls.

        Returns:
            Tuple of:
            - List of executable tool calls
            - Whether clarification is needed
            - Clarification context (if needed)
        """
        batch, content = self.validator.parse_and_validate(llm_response)

        if batch.needs_clarification:
            # Store pending for retry after clarification
            for validated in batch.get_clarification_needed_calls():
                self._pending_clarifications[validated.tool_call.call_id] = validated

            # Aggregate clarification context
            context = self._build_clarification_context(batch)

            if self.on_clarification_needed:
                self.on_clarification_needed(context)

            return [], True, context

        # All valid, return executable calls
        executable = [v.tool_call for v in batch.get_executable_calls()]
        return executable, False, None

    def _build_clarification_context(self, batch: ValidationBatch) -> Dict[str, Any]:
        """Build aggregated clarification context from batch."""
        all_missing = {}
        tools_needing_clarification = []

        for ctx in batch.clarification_contexts:
            tool_name = ctx["tool_name"]
            missing = ctx["context"]["missing_required"]
            tools_needing_clarification.append(tool_name)

            # Get descriptions
            descs = self.validator.get_missing_params_summary(
                next(
                    v
                    for v in batch.validated_calls
                    if v.tool_call.name == tool_name and v.clarification_needed
                )
            )
            all_missing[tool_name] = {
                "missing_params": missing,
                "descriptions": descs,
            }

        return {
            "tools": tools_needing_clarification,
            "missing": all_missing,
            "total_missing_count": sum(len(m["missing_params"]) for m in all_missing.values()),
        }

    def retry_with_clarification(
        self, call_id: str, additional_params: Dict[str, Any]
    ) -> Optional[ToolCall]:
        """
        Retry a pending tool call with additional parameters from clarification.

        Returns the updated tool call if valid, None if still missing params.
        """
        if call_id not in self._pending_clarifications:
            return None

        pending = self._pending_clarifications[call_id]
        original_call = pending.tool_call

        # Merge new params
        updated_args = {**original_call.arguments, **additional_params}
        updated_call = ToolCall(name=original_call.name, arguments=updated_args, call_id=call_id)

        # Re-validate
        validated = self.validator.validate_call(updated_call)

        if validated.can_execute:
            # Remove from pending
            del self._pending_clarifications[call_id]
            return updated_call
        else:
            # Still missing something, update pending
            self._pending_clarifications[call_id] = validated
            return None

    def get_pending_clarifications(self) -> Dict[str, ValidatedToolCall]:
        """Get all pending clarifications."""
        return self._pending_clarifications.copy()

    def clear_pending(self) -> None:
        """Clear all pending clarifications."""
        self._pending_clarifications.clear()
