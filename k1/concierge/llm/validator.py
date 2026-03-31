"""
LLM Output Validator -- Guardrails Against Hallucinated Tool Calls
===================================================================

V2 Design Ref: Section 10.8 (Output Validation)
Epic 4, Issue 4.1

Validates every ConciergeModelResponse before acceptance:
  1. Tool allowlist  -- all tool_calls reference known schemas
  2. Required params -- each tool call supplies required arguments
  3. Param type spot-check -- top-level type mismatches caught early

If validation fails, _attempt_fix strips invalid tool calls and returns
a cleaned response. If no valid calls remain, returns None so the caller
can apply a safe fallback.

Usage (inside react_loop):
    validator = LLMOutputValidator(tool_schemas)
    vr = validator.validate(response, actor=actor, iteration=iteration)
    if not vr.valid:
        if vr.fixed_response:
            response = vr.fixed_response
            response.finish_reason = FinishReason.VALIDATION_FALLBACK
        else:
            # caller applies fallback
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from k1.concierge.llm.types import ConciergeModelResponse, FinishReason, ToolCallResult, ToolSchema

logger = logging.getLogger(__name__)


# =========================================================================
# ValidationResult
# =========================================================================


@dataclass
class ValidationResult:
    """Result of validating a ConciergeModelResponse.

    Attributes:
        valid: True if all checks passed.
        issues: Human-readable list of issues found.
        fixed_response: A cleaned copy of the response with invalid tool
            calls stripped. None if no valid response can be salvaged.
    """

    valid: bool
    issues: list[str] = field(default_factory=list)
    fixed_response: ConciergeModelResponse | None = None


# =========================================================================
# LLMOutputValidator
# =========================================================================


class LLMOutputValidator:
    """Validate LLM outputs before accepting them.

    Constructed with the actor's tool schemas. Validates each response
    from model.generate() to catch hallucinated tool names, missing
    required parameters, and protocol violations.

    Args:
        tool_schemas: List of ToolSchema objects for the active actor.
            The validator builds an internal lookup dict by name.
    """

    def __init__(self, tool_schemas: list[ToolSchema]) -> None:
        self._schemas: dict[str, ToolSchema] = {s.name: s for s in tool_schemas}
        logger.info(
            "LLMOutputValidator initialised  schema_count=%d schemas=%s",
            len(self._schemas),
            list(self._schemas.keys()),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(
        self,
        response: ConciergeModelResponse,
        *,
        actor: str = "",
        iteration: int = 0,
        available_tool_names: frozenset[str] | set[str] | None = None,
    ) -> ValidationResult:
        """Validate tool calls, params, and ordering.

        Args:
            response: The model response to validate.
            actor: "front" or "back".
            iteration: ReAct loop iteration (0-based).
            available_tool_names: Set of tool names available in this call.

        Returns:
            ValidationResult with valid flag, issues list, and optional
            fixed_response.
        """
        issues: list[str] = []

        if not response.has_tool_calls:
            # Nothing to validate -- text-only responses pass
            return ValidationResult(valid=True)

        # 1. Tool allowlist check
        for tc in response.tool_calls:
            if tc.name not in self._schemas:
                issues.append(f"Tool '{tc.name}' not in allowlist")

        # 2. Required params check
        for tc in response.tool_calls:
            schema = self._schemas.get(tc.name)
            if schema is None:
                continue  # already flagged in allowlist check
            required = self._get_required_params(schema)
            for param in required:
                if param not in tc.arguments:
                    issues.append(f"Tool '{tc.name}': missing required param '{param}'")

        # 3. Param type spot-check (string vs non-string for top-level)
        for tc in response.tool_calls:
            schema = self._schemas.get(tc.name)
            if schema is None:
                continue
            type_issues = self._check_param_types(tc, schema)
            issues.extend(type_issues)

        if not issues:
            return ValidationResult(valid=True)

        # Attempt fix
        logger.warning(
            "LLMOutputValidator: %d issue(s) for actor=%s iter=%d: %s",
            len(issues),
            actor,
            iteration,
            "; ".join(issues),
        )
        fixed = self._attempt_fix(response, actor, iteration)
        return ValidationResult(
            valid=False,
            issues=issues,
            fixed_response=fixed,
        )

    # ------------------------------------------------------------------
    # Schema lookup helpers
    # ------------------------------------------------------------------

    @property
    def schema_names(self) -> set[str]:
        """Set of known tool names."""
        return set(self._schemas.keys())

    def has_schema(self, name: str) -> bool:
        """Check if a tool name is known."""
        return name in self._schemas

    # ------------------------------------------------------------------
    # Private validation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_required_params(schema: ToolSchema) -> list[str]:
        """Extract required parameter names from a ToolSchema."""
        params = schema.parameters
        if not params:
            return []
        return params.get("required", [])

    @staticmethod
    def _check_param_types(tc: ToolCallResult, schema: ToolSchema) -> list[str]:
        """Spot-check top-level parameter types against schema.

        Only checks string vs non-string for now. Returns list of issues.
        """
        issues: list[str] = []
        properties = (schema.parameters or {}).get("properties", {})
        for param_name, param_value in tc.arguments.items():
            if param_name not in properties:
                continue  # extra params are OK (additionalProperties)
            expected_type = properties[param_name].get("type")
            if expected_type == "string" and not isinstance(param_value, str):
                issues.append(
                    f"Tool '{tc.name}': param '{param_name}' expected string, "
                    f"got {type(param_value).__name__}"
                )
            elif expected_type == "number" and not isinstance(param_value, (int, float)):
                issues.append(
                    f"Tool '{tc.name}': param '{param_name}' expected number, "
                    f"got {type(param_value).__name__}"
                )
            elif expected_type == "boolean" and not isinstance(param_value, bool):
                issues.append(
                    f"Tool '{tc.name}': param '{param_name}' expected boolean, "
                    f"got {type(param_value).__name__}"
                )
            elif expected_type == "object" and not isinstance(param_value, dict):
                issues.append(
                    f"Tool '{tc.name}': param '{param_name}' expected object, "
                    f"got {type(param_value).__name__}"
                )
            elif expected_type == "array" and not isinstance(param_value, list):
                issues.append(
                    f"Tool '{tc.name}': param '{param_name}' expected array, "
                    f"got {type(param_value).__name__}"
                )
        return issues

    # ------------------------------------------------------------------
    # Fix attempt
    # ------------------------------------------------------------------

    def _attempt_fix(
        self,
        response: ConciergeModelResponse,
        actor: str,
        iteration: int,
    ) -> ConciergeModelResponse | None:
        """Try to salvage a response by stripping invalid tool calls.

        Strategy:
          1. Keep only tool calls that pass allowlist + required params.
          2. If no valid calls remain, return None.

        Returns:
            A cleaned ConciergeModelResponse, or None if unsalvageable.
        """
        valid_calls: list[ToolCallResult] = []

        for tc in response.tool_calls:
            # Skip unknown tools
            if tc.name not in self._schemas:
                continue
            # Skip tools with missing required params
            schema = self._schemas[tc.name]
            required = self._get_required_params(schema)
            if any(p not in tc.arguments for p in required):
                continue
            valid_calls.append(tc)

        if not valid_calls:
            return None

        # Build fixed response (copy fields, replace tool_calls)
        fixed = ConciergeModelResponse(
            text=response.text,
            tool_calls=valid_calls,
            json_output=response.json_output,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            tokens_thoughts=response.tokens_thoughts,
            latency_ms=response.latency_ms,
            model_id=response.model_id,
            finish_reason=FinishReason.VALIDATION_FALLBACK,
            thought_text=response.thought_text,
        )
        return fixed
