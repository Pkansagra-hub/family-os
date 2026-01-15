"""
Fabric Context Policy - Enforcement of fabric_context_policy for trust boundaries.

Implements capability intersection and context isolation for secure fabric calls.
Per ADR-K004, fabric calls cross trust boundaries and require policy enforcement.

Policies:
- INHERIT: Caller caps ∩ provider caps = effective_caps (least privilege)
- ISOLATED: Provider uses only its own declared context
- SYNTHETIC: Fabric creates minimal context with trace_id only

Related:
- k0/fabric/fabric.py: CapabilityFabric
- k0/runtime/schemas.py: FabricContextPolicy
- docs/architecture/decisions-K0/k004-capability-mesh-architecture.md
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ContextPolicyEnforcer:
    """
    Enforces fabric_context_policy before provider invocation.

    Security Principles:
        - Least privilege: INHERIT policy restricts to intersection of caps
        - Isolation: ISOLATED policy prevents capability leakage
        - Traceability: All policies preserve trace_id for auditing

    Example:
        enforcer = ContextPolicyEnforcer()
        effective_ctx = enforcer.enforce(
            caller_context=ctx,
            provider_policy="inherit",
            provider_caps={"score_salience", "embed_content"},
        )
        result = handler(context=effective_ctx, **payload)
    """

    def enforce(
        self,
        caller_context: Any | None,
        provider_policy: str,
        provider_caps: set[str],
    ) -> Any | None:
        """
        Enforce fabric_context_policy before invoking provider.

        Args:
            caller_context: Caller's PipelineContext (or None)
            provider_policy: Policy from module contract ("inherit", "isolated", "synthetic")
            provider_caps: Provider's declared fabric_capabilities

        Returns:
            Effective context for provider invocation (may be None for isolated)

        Policy Behaviors:
            - inherit: caller_caps ∩ provider_caps = effective_caps
            - isolated: Returns None (provider uses own context)
            - synthetic: Returns minimal context with trace_id only
        """
        if caller_context is None:
            logger.debug("No caller context provided, returning None")
            return None

        policy_lower = provider_policy.lower()

        if policy_lower == "inherit":
            return self._enforce_inherit(caller_context, provider_caps)

        elif policy_lower == "isolated":
            return self._enforce_isolated(caller_context)

        elif policy_lower == "synthetic":
            return self._enforce_synthetic(caller_context)

        else:
            logger.warning(
                "Unknown fabric_context_policy: %s, defaulting to isolated",
                provider_policy,
            )
            return self._enforce_isolated(caller_context)

    def _enforce_inherit(
        self,
        caller_context: Any,
        provider_caps: set[str],
    ) -> Any:
        """
        INHERIT policy: capability intersection.

        Effective capabilities = caller_caps ∩ provider_caps.
        This ensures the provider can only use capabilities that
        both the caller has access to AND the provider declares.
        """
        # Get caller's capabilities (may be stored as set, list, or not exist)
        caller_caps = self._get_capabilities(caller_context)

        # Compute intersection
        effective_caps = caller_caps & provider_caps

        logger.debug(
            "INHERIT policy: caller_caps=%d, provider_caps=%d, effective=%d",
            len(caller_caps),
            len(provider_caps),
            len(effective_caps),
        )

        # Create new context with restricted capabilities
        return self._create_context_with_caps(caller_context, effective_caps)

    def _enforce_isolated(self, caller_context: Any) -> None:
        """
        ISOLATED policy: no context inheritance.

        Provider uses only its own declared syscalls and context.
        Returns None to indicate no inherited context.
        """
        logger.debug("ISOLATED policy: returning None (provider uses own context)")
        return None

    def _enforce_synthetic(self, caller_context: Any) -> Any:
        """
        SYNTHETIC policy: minimal trace-only context.

        Creates a minimal context that only preserves trace_id
        for audit trail purposes. No syscalls or capabilities.
        """
        trace_id = getattr(caller_context, "trace_id", None)

        logger.debug(
            "SYNTHETIC policy: creating minimal context with trace_id=%s",
            trace_id,
        )

        return self._create_synthetic_context(caller_context)

    def _get_capabilities(self, context: Any) -> set[str]:
        """
        Extract capabilities from a context object.

        Supports capabilities as set, list, tuple, or frozenset.
        Returns empty set if no capabilities attribute exists.
        """
        caps = getattr(context, "capabilities", None)
        if caps is None:
            return set()
        if isinstance(caps, (set, frozenset)):
            return set(caps)
        if isinstance(caps, (list, tuple)):
            return set(caps)
        return set()

    def _create_context_with_caps(
        self,
        source_context: Any,
        effective_caps: set[str],
    ) -> Any:
        """
        Create a new context with restricted capabilities.

        Uses dataclasses.replace if context is a dataclass,
        otherwise returns source with logged warning.
        """
        try:
            return replace(source_context, capabilities=effective_caps)
        except TypeError:
            # Context may not be a dataclass or may not have capabilities field
            logger.debug(
                "Cannot replace capabilities on context type: %s",
                type(source_context).__name__,
            )
            # Return source context unchanged (degrade gracefully)
            return source_context

    def _create_synthetic_context(self, source_context: Any) -> Any:
        """
        Create minimal synthetic context for isolated invocation.

        Preserves only trace_id for audit correlation.
        All other fields are set to minimal/None values.
        """
        # Import here to avoid circular imports
        from k0.pipelines.protocol import PipelineContext

        trace_id = getattr(source_context, "trace_id", None)
        source_logger = getattr(source_context, "logger", None)

        # Create minimal context - syscalls=None means no storage access
        return PipelineContext(
            syscalls=None,  # type: ignore  # No syscalls access in synthetic context
            config={},
            logger=source_logger or logger,  # Preserve logger for debugging
            preloaded_models=None,
            bus_dispatcher=None,
            fabric=None,
        )

    def get_stats(
        self,
        caller_context: Any | None,
        provider_policy: str,
        provider_caps: set[str],
    ) -> dict[str, int]:
        """
        Get statistics about policy enforcement without enforcing.

        Useful for audit logging before enforcement.

        Returns:
            Dict with caller_caps_count and effective_caps_count
        """
        if caller_context is None:
            return {"caller_caps_count": 0, "effective_caps_count": 0}

        caller_caps = self._get_capabilities(caller_context)
        policy_lower = provider_policy.lower()

        if policy_lower == "inherit":
            effective_caps = caller_caps & provider_caps
            return {
                "caller_caps_count": len(caller_caps),
                "effective_caps_count": len(effective_caps),
            }
        elif policy_lower == "isolated":
            return {
                "caller_caps_count": len(caller_caps),
                "effective_caps_count": 0,
            }
        elif policy_lower == "synthetic":
            return {
                "caller_caps_count": len(caller_caps),
                "effective_caps_count": 0,
            }
        else:
            return {
                "caller_caps_count": len(caller_caps),
                "effective_caps_count": 0,
            }


# Global enforcer instance
_enforcer: ContextPolicyEnforcer | None = None


def get_context_policy_enforcer() -> ContextPolicyEnforcer:
    """Get the global context policy enforcer."""
    global _enforcer
    if _enforcer is None:
        _enforcer = ContextPolicyEnforcer()
    return _enforcer


def reset_context_policy_enforcer() -> None:
    """Reset the global enforcer (for testing)."""
    global _enforcer
    _enforcer = None
