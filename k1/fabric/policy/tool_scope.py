"""
k1.fabric.policy.tool_scope -- ToolScope enforcement (3.2.6).

Enforces that sub-agents can only invoke capabilities from their
``tools_granted[]`` set.  This is the standalone enforcement component
used by AgentFactory (4.3.1) when creating scoped ``invoke_capability``
callables for sub-agents.

Unlike SecurityContext (which checks tool scope as one of its 3 checks),
ToolScope is a **dedicated** component that:
  - Is constructed with a specific ``tools_granted`` set per sub-agent.
  - Validates before each invocation attempt.
  - Raises ``AccessDeniedError`` on violation (consistent with SecurityContext).

Enforces FAB-07: Sub-agent tool scoping enforced via tools_granted[].

Design:
  - Standalone (no port dependencies).
  - Immutable after construction.
  - Thread-safe (no mutable state).

References:
  - fabric_discussion.md Section 10 (Security Context, tool scoping)
  - Epic 3.2.6 in fabric-implementation-plan.md
  - FAB-07 invariant

Exports:
  ToolScope      -- Tool-scope enforcement component
  ToolScopeError -- Base exception for tool scope violations
"""

from __future__ import annotations

import logging
from typing import FrozenSet, Iterable

from k1.fabric.policy.security_context import AccessDeniedError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ToolScopeError(Exception):
    """Base exception for ToolScope operations."""


# ---------------------------------------------------------------------------
# ToolScope
# ---------------------------------------------------------------------------


class ToolScope:
    """
    Sub-agent tool-scope enforcement (3.2.6).

    Created per sub-agent with the set of capabilities that agent is
    allowed to invoke.  Validates each capability invocation against
    this set before execution proceeds.

    Usage::

        scope = ToolScope(tools_granted=["tool.execute.weather", "tool.execute.calendar"])
        scope.validate("tool.execute.weather")   # ok
        scope.validate("tool.execute.payments")  # raises AccessDeniedError

    Used by AgentFactory (4.3.1) step 5 to wrap invoke_capability with
    scope enforcement.

    Attributes (read-only):
        tools_granted: Frozen set of allowed capability names.
    """

    __slots__ = ("_tools_granted",)

    def __init__(
        self,
        *,
        tools_granted: Iterable[str],
    ) -> None:
        """
        Args:
            tools_granted: Collection of capability names the sub-agent
                is allowed to invoke.  Converted to frozenset on construction.
                Must be non-empty.

        Raises:
            ToolScopeError: If tools_granted is empty.
        """
        fs = frozenset(tools_granted)
        if not fs:
            raise ToolScopeError("tools_granted must be non-empty")
        self._tools_granted: FrozenSet[str] = fs

    @property
    def tools_granted(self) -> FrozenSet[str]:
        """The frozen set of allowed capability names."""
        return self._tools_granted

    # ======================================================================
    # Public API
    # ======================================================================

    def validate(self, capability_name: str) -> bool:
        """
        Check whether a capability is in the allowed set.

        Args:
            capability_name: The capability the sub-agent wants to invoke.

        Returns:
            True if the capability is allowed.

        Raises:
            AccessDeniedError: If capability_name is not in tools_granted.
                Uses check="tool_scope" for consistency with SecurityContext.
        """
        if not capability_name:
            raise AccessDeniedError(
                check="tool_scope",
                detail="capability_name is empty",
            )

        if capability_name not in self._tools_granted:
            logger.warning(
                "ToolScope denied: %s not in tools_granted (%d tools)",
                capability_name,
                len(self._tools_granted),
            )
            raise AccessDeniedError(
                check="tool_scope",
                detail=(
                    f"'{capability_name}' not in tools_granted "
                    f"({len(self._tools_granted)} tools allowed)"
                ),
            )

        logger.debug("ToolScope allowed: %s", capability_name)
        return True

    def is_allowed(self, capability_name: str) -> bool:
        """
        Non-raising check for capability access.

        Args:
            capability_name: The capability name to check.

        Returns:
            True if allowed, False otherwise (does NOT raise).
        """
        return bool(capability_name) and capability_name in self._tools_granted

    def __repr__(self) -> str:
        return f"ToolScope(tools_granted={sorted(self._tools_granted)})"
