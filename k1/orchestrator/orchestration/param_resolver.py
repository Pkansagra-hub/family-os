"""
k1.orchestrator.orchestration.param_resolver -- DAG step parameter resolution (4.5.9).

Resolves dynamic $step_id.result.path references in DAG step definitions
before handing them to Fabric for execution.

Two resolution modes:
  1. Param resolution -- resolves $-refs in step["params"] values
  2. Capability resolution -- resolves $-refs in step["capability"] field
     (enables meta-agent creation: build_agent -> execute created agent)

Design:
  - Sits BEFORE the Fabric boundary. Fabric NEVER sees $-references.
  - Constructor-injected RegistryPort for capability existence checks.
  - Stateless: resolve_step() creates new dicts per call.
  - Thread-safe: safe for concurrent use by DAGExecutor wave parallelism.

References:
  - param_resolver_spec.md (4.5.9)
  - meta-agent-creation-integration-proposal.md
  - ADR-0005 (Agent Lifecycle), ADR-K004 (Capability Fabric Adaptation)
  - PLAN-06: Planner NEVER executes writes. Orchestrator executes all steps.

Exports:
  ParamResolver
  RegistryPort
  UnresolvedCapabilityError
  StepReferenceError
  PathResolutionError
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Registry port (Protocol -- avoids circular imports)
# ---------------------------------------------------------------------------


class RegistryPort(Protocol):
    """Minimal registry protocol for capability existence checks."""

    def contains(self, name: str) -> bool: ...


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class StepReferenceError(Exception):
    """Raised when a referenced step_id is not in completed_results."""

    def __init__(self, step_id: str, ref: str) -> None:
        self.step_id = step_id
        self.ref = ref
        super().__init__(
            f"Step reference failed: step_id '{step_id}' not found "
            f"in completed results (from ref '{ref}')"
        )


class PathResolutionError(Exception):
    """Raised when path traversal on CapabilityResult.data fails."""

    def __init__(self, ref: str, path_segment: str, reason: str) -> None:
        self.ref = ref
        self.path_segment = path_segment
        super().__init__(
            f"Path resolution failed for '{ref}': " f"segment '{path_segment}' -- {reason}"
        )


class UnresolvedCapabilityError(Exception):
    """Raised when a $-reference in capability field cannot be resolved."""

    def __init__(
        self,
        step_id: str,
        capability_ref: str,
        resolved_value: str,
    ) -> None:
        self.step_id = step_id
        self.capability_ref = capability_ref
        self.resolved_value = resolved_value
        super().__init__(
            f"Step '{step_id}': capability ref '{capability_ref}' "
            f"resolved to '{resolved_value}' which is not registered"
        )


# ---------------------------------------------------------------------------
# ParamResolver
# ---------------------------------------------------------------------------


class ParamResolver:
    """
    Resolves dynamic $step_id.result.path references in DAG step defs.

    Used by DAGExecutor between waves: after step N completes, resolver
    substitutes $-refs in step N+1 params and capability fields before
    sending to Fabric.

    Constructor injection:
      registry: RegistryPort for capability existence checks (contains()).
                If None, capability existence checks are skipped (POC mode).

    Thread safety: stateless, creates new dicts per call.
    """

    __slots__ = ("_registry",)

    def __init__(self, registry: Optional[RegistryPort] = None) -> None:
        self._registry = registry

    def resolve_step(
        self,
        step: Dict[str, Any],
        completed_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Resolve all $-references in a step definition.

        Creates a shallow copy of step with resolved values.
        Original step dict is NEVER mutated.

        Args:
            step: DAG step dict. May contain "capability" and "params" keys.
            completed_results: Dict of step_id -> CapabilityResult from
                previously completed steps.

        Returns:
            New step dict with all $-references resolved.

        Raises:
            StepReferenceError: Referenced step_id not in completed_results.
            PathResolutionError: Path traversal on result data failed.
            UnresolvedCapabilityError: Capability ref resolved to invalid value.
        """
        resolved = dict(step)  # shallow copy

        # 1. Resolve capability field
        capability = resolved.get("capability", "")
        if isinstance(capability, str) and capability.startswith("$"):
            resolved_cap = self._resolve_reference(capability, completed_results)
            step_id = resolved.get("id", resolved.get("step_id", ""))

            if not isinstance(resolved_cap, str) or not resolved_cap:
                raise UnresolvedCapabilityError(
                    step_id=step_id,
                    capability_ref=capability,
                    resolved_value=str(resolved_cap),
                )
            if self._registry is not None and not self._registry.contains(resolved_cap):
                raise UnresolvedCapabilityError(
                    step_id=step_id,
                    capability_ref=capability,
                    resolved_value=resolved_cap,
                )
            resolved["capability"] = resolved_cap
            logger.info(
                "[ParamResolver] Resolved capability: %s -> %s",
                capability,
                resolved_cap,
            )

        # 2. Resolve params
        params = resolved.get("params")
        if isinstance(params, dict):
            resolved_params = {}
            for key, value in params.items():
                if isinstance(value, str) and value.startswith("$"):
                    resolved_params[key] = self._resolve_reference(value, completed_results)
                    logger.debug(
                        "[ParamResolver] Resolved param %s: %s -> %s",
                        key,
                        value,
                        resolved_params[key],
                    )
                else:
                    resolved_params[key] = value
            resolved["params"] = resolved_params

        return resolved

    def _resolve_reference(
        self,
        ref: str,
        completed_results: Dict[str, Any],
    ) -> Any:
        """
        Resolve $step_id.result.path.to.value references.

        Parse: "$step_1a.result.agent_name"
          -> step_id = "step_1a"
          -> path    = ["result", "agent_name"]

        Traversal:
          1. completed_results["step_1a"] -> CapabilityResult
          2. "result" keyword -> access CapabilityResult.data
          3. "agent_name" -> data["agent_name"]

        Args:
            ref: Reference string starting with $.
            completed_results: Dict of step_id -> CapabilityResult.

        Returns:
            The resolved value (any type).

        Raises:
            StepReferenceError: step_id not in completed_results.
            PathResolutionError: path traversal fails.
        """
        # Strip leading $ and split on .
        parts = ref.lstrip("$").split(".")

        if not parts:
            raise PathResolutionError(ref, "", "Empty reference")

        step_id = parts[0]
        path = parts[1:]

        # Lookup step result
        if step_id not in completed_results:
            raise StepReferenceError(step_id, ref)

        result = completed_results[step_id]

        # Check step succeeded
        if hasattr(result, "success") and not result.success:
            raise PathResolutionError(ref, step_id, "Referenced step failed (success=False)")

        # Traverse path
        current: Any = result
        for i, segment in enumerate(path):
            if segment == "result":
                # "result" keyword => access .data (CapabilityResult)
                if hasattr(current, "data"):
                    current = current.data
                elif isinstance(current, dict):
                    current = current.get("data", current.get("result"))
                else:
                    raise PathResolutionError(
                        ref, segment, f"Cannot access 'result' on {type(current).__name__}"
                    )
                if current is None:
                    raise PathResolutionError(ref, segment, "Result data is None")
            elif isinstance(current, dict):
                if segment not in current:
                    raise PathResolutionError(
                        ref,
                        segment,
                        f"Key '{segment}' not found in dict "
                        f"(available: {list(current.keys())})",
                    )
                current = current[segment]
            elif hasattr(current, segment):
                current = getattr(current, segment)
            else:
                raise PathResolutionError(
                    ref, segment, f"Cannot traverse '{segment}' on {type(current).__name__}"
                )

        return current

    def __repr__(self) -> str:
        return f"ParamResolver(registry={self._registry!r})"
