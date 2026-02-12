"""
k1.orchestrator.orchestration.param_resolver -- DAG step parameter resolution.

Resolves dynamic $step_id.result.path references in DAG step definitions
before handing them to Fabric for execution.

Two resolution modes:
  1. Param resolution -- resolves $-refs in step params values (recursive)
  2. Capability resolution -- resolves $-refs in step capability field
     (enables meta-agent creation: build_agent -> execute created agent)

Design:
  - Sits BEFORE the Fabric boundary. Fabric NEVER sees $-references.
  - Constructor-injected RegistryPort for capability existence checks.
  - Stateless: resolve()/resolve_step() creates new dicts per call.
  - Thread-safe: safe for concurrent use by DAGExecutor wave parallelism.

API:
  resolve(step: PlanStep, prior_results: Dict[str, CapabilityResult])
    -> Tuple[Dict[str, Any], Optional[str]]
    Typed API for Orchestrator DAG execution (2.3.5).

  resolve_step(step: Dict, completed_results: Dict) -> Dict
    Legacy dict-based API (Fabric 4.5.9). Backward-compat alias.
    Remove in M7.

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

import copy
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol, Tuple

if TYPE_CHECKING:
    from k1.orchestrator.types import PlanStep

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

    # ------------------------------------------------------------------
    # Typed API (2.3.5) -- used by DAGExecutor
    # ------------------------------------------------------------------

    def resolve(
        self,
        step: PlanStep,
        prior_results: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """Resolve all $-references in a PlanStep.

        Typed API for Orchestrator DAG execution. Returns resolved
        params and optionally a resolved capability name (for dynamic
        meta-agent resolution).

        Args:
            step: PlanStep dataclass (1.2.18). Fields: .id, .capability,
                  .params. capability may start with $ for dynamic resolution.
            prior_results: Dict of step_id -> CapabilityResult (or any
                duck-typed object with .success and .data fields) from
                previously completed steps.

        Returns:
            Tuple of:
              - resolved_params: Dict with all $-references resolved.
                Deep-copied from step.params; original never mutated.
              - resolved_capability_name: str if capability was dynamic
                ($-ref resolved), None if capability was static.

        Raises:
            StepReferenceError: Referenced step_id not in prior_results,
                or referenced step has success=False.
            PathResolutionError: Path traversal on result.data failed.
            UnresolvedCapabilityError: Capability ref resolved to invalid
                value or not found in registry.
        """
        resolved_cap: Optional[str] = None

        # 1. Resolve capability field (meta-agent dynamic resolution)
        capability = step.capability
        if isinstance(capability, str) and capability.startswith("$"):
            resolved_value = self._resolve_reference(capability, prior_results)

            if not isinstance(resolved_value, str) or not resolved_value:
                raise UnresolvedCapabilityError(
                    step_id=step.id,
                    capability_ref=capability,
                    resolved_value=str(resolved_value),
                )
            if self._registry is not None and not self._registry.contains(resolved_value):
                raise UnresolvedCapabilityError(
                    step_id=step.id,
                    capability_ref=capability,
                    resolved_value=resolved_value,
                )
            resolved_cap = resolved_value
            logger.info(
                "[ParamResolver] Resolved capability: %s -> %s (step %s)",
                capability,
                resolved_cap,
                step.id,
            )

        # 2. Resolve params (recursive deep walk)
        resolved_params = self._resolve_params(
            copy.deepcopy(dict(step.params)) if step.params else {},
            prior_results,
        )

        return (resolved_params, resolved_cap)

    # ------------------------------------------------------------------
    # Legacy dict API (Fabric 4.5.9) -- backward compat, remove in M7
    # ------------------------------------------------------------------

    def resolve_step(
        self,
        step: Dict[str, Any],
        completed_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Resolve all $-references in a step definition (legacy dict API).

        Creates a shallow copy of step with resolved values.
        Original step dict is NEVER mutated.

        Kept for backward compatibility with existing DAGExecutor
        integration. Will be removed in M7 when DAGExecutor is
        updated to call resolve() directly.

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

        # 2. Resolve params (flat -- legacy behavior)
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

    # ------------------------------------------------------------------
    # Recursive param walker (2.3.5 -- nested dict support)
    # ------------------------------------------------------------------

    def _resolve_params(
        self,
        params: Dict[str, Any],
        prior_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Recursively walk params dict and resolve all $-references.

        Only string values starting with '$' are resolved. Non-string
        values (int, bool, list, None) pass through unchanged. Nested
        dicts are recursed. Lists are walked element-by-element.

        V1 scope: dot-navigation only (no array indexing in refs).

        Args:
            params: Deep-copied params dict (safe to mutate).
            prior_results: Completed step results for reference lookup.

        Returns:
            params dict with all $-references resolved in place.
        """
        for key, value in params.items():
            if isinstance(value, str) and value.startswith("$"):
                params[key] = self._resolve_reference(value, prior_results)
                logger.debug(
                    "[ParamResolver] Resolved param %s: %s -> %s",
                    key,
                    value,
                    params[key],
                )
            elif isinstance(value, dict):
                self._resolve_params(value, prior_results)
            elif isinstance(value, list):
                self._resolve_list(value, prior_results)
        return params

    def _resolve_list(
        self,
        items: List[Any],
        prior_results: Dict[str, Any],
    ) -> None:
        """Walk list elements and resolve $-references in place.

        Only mutates string elements that start with '$'.
        Nested dicts and lists are recursed.
        """
        for i, item in enumerate(items):
            if isinstance(item, str) and item.startswith("$"):
                items[i] = self._resolve_reference(item, prior_results)
            elif isinstance(item, dict):
                self._resolve_params(item, prior_results)
            elif isinstance(item, list):
                self._resolve_list(item, prior_results)

    # ------------------------------------------------------------------
    # Reference resolution
    # ------------------------------------------------------------------

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
        for segment in path:
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
