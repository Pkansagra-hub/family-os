"""
Tier-1 Tool Call Validator
==========================

Validates tool call bundles BEFORE execution to enforce:
1. ACK-first rule: effectful tools require acknowledge() first
2. ACK-tool bundle: acknowledge must be followed by declared next_tool
3. Message quality: ACK messages must be specific, no filler phrases

This is the "hard governance" layer that prevents malformed tool plans
from executing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from poc.session_state_demo.anniversary_demo.tools.registry import EFFECTFUL_TOOLS


@dataclass
class ValidationResult:
    """Result of validating a tool call bundle."""

    valid: bool
    errors: List[str]
    warnings: List[str]
    should_replan: bool = False  # If True, reject and ask LLM to try again

    @property
    def passed(self) -> bool:
        return self.valid and not self.should_replan


# Banned phrases in ACK messages (case-insensitive)
BANNED_ACK_PHRASES = [
    r"\bgot it\b",
    r"\bunderstood\b",
    r"\bnoted\b",
    r"\bi see\b",
    r"\bi understand\b",
    r"\blet me\b",
    r"\bi'll help\b",
    r"\bi will help\b",
    r"\bi've noted\b",
    r"\bi have noted\b",
]


def validate_tool_bundle(
    tool_calls: List[Dict[str, Any]],
    strict: bool = True,
) -> ValidationResult:
    """
    Validate a bundle of tool calls before execution.

    Args:
        tool_calls: List of tool calls from LLM response
        strict: If True, enforce all rules. If False, only warn.

    Returns:
        ValidationResult with pass/fail and details
    """
    errors: List[str] = []
    warnings: List[str] = []

    if not tool_calls:
        # No tools called - this is fine (pure text response)
        return ValidationResult(valid=True, errors=[], warnings=[])

    # Extract tool names and args
    tools = []
    for call in tool_calls:
        name = call.get("name", call.get("function", {}).get("name", ""))
        args = call.get("arguments", call.get("function", {}).get("arguments", {}))
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        tools.append({"name": name, "args": args})

    if not tools:
        return ValidationResult(valid=True, errors=[], warnings=[])

    first_tool = tools[0]
    has_effectful = any(t["name"] in EFFECTFUL_TOOLS for t in tools)

    # ==========================================================================
    # RULE 1: ACK-first for effectful tools
    # ==========================================================================
    if has_effectful and first_tool["name"] != "acknowledge":
        msg = f"EFFECTFUL tool '{tools[0]['name']}' called without acknowledge() first"
        if strict:
            errors.append(msg)
        else:
            warnings.append(msg)

    # ==========================================================================
    # RULE 2: ACK must be bundled with declared next_tool
    # ==========================================================================
    if first_tool["name"] == "acknowledge":
        ack_args = first_tool["args"]
        next_tool = ack_args.get("next_tool", "none")

        if next_tool != "none":
            # Must have a second tool
            if len(tools) < 2:
                msg = f"acknowledge declared next_tool='{next_tool}' but no tool follows"
                if strict:
                    errors.append(msg)
                else:
                    warnings.append(msg)
            else:
                # Second tool must match declared next_tool
                actual_next = tools[1]["name"]
                if actual_next != next_tool:
                    msg = f"acknowledge declared next_tool='{next_tool}' but actual next tool is '{actual_next}'"
                    if strict:
                        errors.append(msg)
                    else:
                        warnings.append(msg)

        # Validate ACK message quality
        message = ack_args.get("message", "")
        _validate_ack_message(message, errors, warnings, strict)

    # ==========================================================================
    # RULE 3: No duplicate tool calls in same bundle
    # ==========================================================================
    tool_names = [t["name"] for t in tools]
    seen = set()
    for name in tool_names:
        if name in seen and name != "acknowledge":
            warnings.append(f"Tool '{name}' called multiple times in same bundle")
        seen.add(name)

    # Determine if we should force a replan
    should_replan = len(errors) > 0

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        should_replan=should_replan,
    )


def _validate_ack_message(
    message: str,
    errors: List[str],
    warnings: List[str],
    strict: bool,
) -> None:
    """Validate ACK message doesn't contain banned filler phrases."""
    message_lower = message.lower()

    for pattern in BANNED_ACK_PHRASES:
        if re.search(pattern, message_lower):
            msg = f"ACK message contains banned phrase matching '{pattern}': '{message[:50]}...'"
            # Filler phrases are warnings, not errors (let LLM learn)
            warnings.append(msg)


def validate_and_fix_tool_order(
    tool_calls: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Attempt to fix tool order if possible.

    If acknowledge exists but is not first, move it first.
    Returns fixed list and list of fixes applied.
    """
    if not tool_calls:
        return tool_calls, []

    fixes = []
    tools = list(tool_calls)

    # Find acknowledge if it exists
    ack_idx = None
    for i, call in enumerate(tools):
        name = call.get("name", call.get("function", {}).get("name", ""))
        if name == "acknowledge":
            ack_idx = i
            break

    # If acknowledge exists but not first, move it
    if ack_idx is not None and ack_idx > 0:
        ack_call = tools.pop(ack_idx)
        tools.insert(0, ack_call)
        fixes.append(f"Moved acknowledge from position {ack_idx} to position 0")

    return tools, fixes


class ToolBundleValidator:
    """
    Stateful validator that tracks tool calls across a turn.

    Can be used as a guard before tool execution.
    """

    def __init__(self, strict: bool = True):
        self.strict = strict
        self._last_ack: Optional[Dict[str, Any]] = None
        self._tools_this_turn: List[str] = []

    def reset_turn(self) -> None:
        """Reset state for new turn."""
        self._last_ack = None
        self._tools_this_turn = []

    def validate_before_execution(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
    ) -> ValidationResult:
        """
        Validate a single tool call before execution.

        Call this for each tool in sequence during a turn.
        """
        errors = []
        warnings = []

        # Track this tool
        self._tools_this_turn.append(tool_name)

        # If this is acknowledge, store it
        if tool_name == "acknowledge":
            self._last_ack = tool_args
            return ValidationResult(valid=True, errors=[], warnings=[])

        # If this is an effectful tool, check ACK was called first
        if tool_name in EFFECTFUL_TOOLS:
            if self._last_ack is None:
                msg = f"Effectful tool '{tool_name}' executed without acknowledge() first this turn"
                if self.strict:
                    errors.append(msg)
                else:
                    warnings.append(msg)
            else:
                # Check if this matches declared next_tool
                declared_next = self._last_ack.get("next_tool", "none")
                if declared_next != "none" and declared_next != tool_name:
                    msg = f"ACK declared next_tool='{declared_next}' but executing '{tool_name}'"
                    warnings.append(msg)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def validate_turn_complete(self) -> ValidationResult:
        """
        Validate at end of turn that ACK contract was fulfilled.

        Call this after all tools in a turn have executed.
        """
        errors = []
        warnings = []

        if self._last_ack:
            declared_next = self._last_ack.get("next_tool", "none")
            if declared_next != "none":
                # Check if declared tool was actually called
                if declared_next not in self._tools_this_turn:
                    msg = f"ACK declared next_tool='{declared_next}' but it was never called this turn"
                    warnings.append(msg)

        return ValidationResult(
            valid=True,  # End-of-turn is just warnings
            errors=errors,
            warnings=warnings,
        )
