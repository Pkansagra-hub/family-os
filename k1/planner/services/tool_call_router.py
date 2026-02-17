"""ToolCallRouter -- deterministic discovery tool dispatch [F25].

Thin, deterministic routing layer that maps 4 abstract discovery
tool names to 3 backend ports.  The ONLY mutable instance state is
the monotonic ``_tool_call_count`` counter (PLAN-05).

Section references
------------------
- SS11   -- Discovery Tools Deep Dive
- SS11.1 -- discover_capabilities (4-step retrieval pipeline)
- SS11.2 -- find_relevant_prompts (prompt-type pre-filter)
- SS11.3 -- query_planning_context (SessionState read)
- SS11.4 -- recall_for_planning  (K0 Bridge)
- SS11.5 -- ToolCallRouter Internal Design
- SS17.7 -- Test catalogue (~35 tests)

Architecture
------------
Layer 2 (SS30.6).  Imports Layer 1 ports and Layer 0 types.

Invariants enforced
-------------------
- PLAN-02: all 4 routed tools are read-only, zero side effects.
- PLAN-05: ``tool_call_count < max_tool_calls_per_plan`` (default 6).
- PLAN-06: no execute route exists in the routing table.

Concurrency
-----------
Safe for concurrent dispatch (``asyncio.gather``).  Counter increment
is atomic within a single-threaded event-loop (SS24.1).

Anti-hallucination
------------------
This module is a thin, deterministic dispatch layer.  It does NOT
make LLM calls.  It does NOT interpret tool results.  It does NOT
make routing decisions based on content.  All routing is static
(class-level constant table).
"""

from __future__ import annotations

import asyncio
import logging
import types
from typing import Any, Dict, Optional

from k1.fabric.types import RetrievalResult
from k1.planner.config import PlannerConfig
from k1.planner.ports.bridge_port import IBridgePort
from k1.planner.ports.fabric_retrieval_port import IFabricRetrievalPort
from k1.planner.ports.state_read_port import IStateReadPort
from k1.planner.types import BudgetExhaustedError, RecallResponse, UnknownToolError

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry / timeout policy (SS11.5.3)
# ---------------------------------------------------------------------------
# Mapping: tool_name -> (timeout_ms, max_retries)
# Retries do NOT double-count against PLAN-05.  Counter increments
# once per *logical* call attempt, not per network request.

_RETRY_POLICY: types.MappingProxyType[str, tuple[int, int]] = types.MappingProxyType(
    {
        "discover_capabilities": (50, 1),
        "find_relevant_prompts": (50, 1),
        "query_planning_context": (10, 0),
        "recall_for_planning": (100, 0),
    }
)


class ToolCallRouter:
    """Deterministic discovery-tool dispatch with budget enforcement.

    Constructor
    -----------
    ``ToolCallRouter(fabric_retrieval, state_read, bridge_port, *, config)``

    Three required port dependencies (Layer 1) plus an optional config
    for budget limits.

    Routing table (SS11.5.1) -- class-level frozen constant
    --------------------------------------------------------
    ==================== =================== =================
    Tool name            Port attribute      Backend
    ==================== =================== =================
    discover_capabilities _fabric_retrieval  IFabricRetrievalPort
    find_relevant_prompts _fabric_retrieval  IFabricRetrievalPort
    query_planning_context _state_read       IStateReadPort
    recall_for_planning   _bridge_port       IBridgePort
    ==================== =================== =================

    No dynamic registration.  No ``register_tool()``, no ``add_route()``.

    Satisfies
    ---------
    - ``ToolCallRouterLike`` (k1.planner.stages.sketch_service)
    - ``ExpandToolRouterLike`` (k1.planner.stages.expand_service)
    """

    __slots__ = (
        "_fabric_retrieval",
        "_state_read",
        "_bridge_port",
        "_tool_call_count",
        "_config",
    )

    # -- Class-level frozen routing table (SS11.5.1) --
    # Maps abstract tool name -> instance attribute name for the port.
    # Exactly 4 entries.  No execute routes (PLAN-06).
    _ROUTING_TABLE: types.MappingProxyType[str, str] = types.MappingProxyType(
        {
            "discover_capabilities": "_fabric_retrieval",
            "find_relevant_prompts": "_fabric_retrieval",
            "query_planning_context": "_state_read",
            "recall_for_planning": "_bridge_port",
        }
    )

    def __init__(
        self,
        fabric_retrieval: IFabricRetrievalPort,
        state_read: IStateReadPort,
        bridge_port: IBridgePort,
        *,
        config: Optional[PlannerConfig] = None,
    ) -> None:
        if fabric_retrieval is None:
            raise TypeError("fabric_retrieval must not be None")
        if state_read is None:
            raise TypeError("state_read must not be None")
        if bridge_port is None:
            raise TypeError("bridge_port must not be None")

        self._fabric_retrieval = fabric_retrieval
        self._state_read = state_read
        self._bridge_port = bridge_port
        self._tool_call_count: int = 0
        self._config: PlannerConfig = config or PlannerConfig()

    # -- Properties --

    @property
    def tool_call_count(self) -> int:
        """Current monotonic tool-call counter per plan (PLAN-05)."""
        return self._tool_call_count

    # -- reset() (SS11.5.2, LC_PLAN_START / micro-replan start) --

    def reset(self) -> None:
        """Reset ``tool_call_count`` to 0.

        Called by PipelineController at LC_PLAN_START and micro-replan
        start.  This is the ONLY state mutation besides counter
        increments during dispatch.
        """
        self._tool_call_count = 0

    # -- Core dispatch (SS11.5.2) --

    async def call(self, tool_name: str, **params: Any) -> Any:
        """Validate, enforce budget, dispatch to port, increment counter.

        Algorithm (SS11.5.2):
          1. Check ``tool_name in _ROUTING_TABLE`` -> ``UnknownToolError``
          2. Check budget ``_tool_call_count < max`` -> ``BudgetExhaustedError``
          3. Resolve port via ``getattr(self, _ROUTING_TABLE[tool_name])``
          4. Dispatch async to port method with timeout/retry per policy
          5. Increment ``_tool_call_count += 1``
          6. Return result

        Retries do NOT double-count (SS11.5.3).
        """
        self._check_tool_name(tool_name)
        self._check_budget(tool_name)

        port_attr = self._ROUTING_TABLE[tool_name]
        port = getattr(self, port_attr)
        timeout_ms, max_retries = _RETRY_POLICY[tool_name]

        result = await self._dispatch(tool_name, port, timeout_ms, max_retries, params)
        self._tool_call_count += 1
        return result

    # -- Convenience methods (delegates to call()) --

    async def discover(
        self,
        intent: str,
        *,
        domain: Optional[str] = None,
        safety_band: str = "GREEN",
        top_k: int = 10,
    ) -> RetrievalResult:
        """Discover capabilities via IFabricRetrievalPort (SS11.1).

        Note: ``domain`` is ``Optional[str]`` in the convenience API
        (matching ``ToolCallRouterLike``) but
        ``IFabricRetrievalPort.discover_capabilities`` takes
        ``Optional[List[str]]``.  The router wraps ``str -> [str]``.
        """
        return await self.call(
            "discover_capabilities",
            intent=intent,
            domain=[domain] if domain else None,
            safety_band=safety_band,
            top_k=top_k,
        )

    async def find_prompts(
        self,
        intent: str,
        *,
        domain: Optional[str] = None,
        top_k: int = 5,
    ) -> RetrievalResult:
        """Find prompt templates via IFabricRetrievalPort (SS11.2).

        EXPAND-only caller.  Same domain wrapping as ``discover()``.
        """
        return await self.call(
            "find_relevant_prompts",
            intent=intent,
            domain=[domain] if domain else None,
            top_k=top_k,
        )

    async def read_context(
        self,
        session_id: str,
        sections: list[str],
    ) -> Dict[str, Any]:
        """Query planning context via IStateReadPort (SS11.3).

        Returns ``SessionSnapshot.sections`` dict (section name ->
        section data).  ``session_id`` is passed as documentation;
        the adapter already knows the active session.
        """
        return await self.call(
            "query_planning_context",
            sections=sections,
        )

    async def recall_memory(
        self,
        query: str,
        trace_id: str,
    ) -> RecallResponse:
        """Recall for planning via IBridgePort (SS11.4).

        Returns ``RecallResponse`` (Planner abstraction, NOT
        ``BridgeCommandResult``).  K0 offline handling is internal
        to the BridgeAdapter -- returns empty ``RecallResponse``
        when K0 is unavailable.
        """
        return await self.call(
            "recall_for_planning",
            query=query,
            trace_id=trace_id,
        )

    async def get_schema(
        self,
        capability_name: str,
        *,
        version: Optional[str] = None,
    ) -> Any:
        """Get capability contract by exact name (SS11.2, EXPAND only).

        This method bypasses the routing table and does NOT count
        against the PLAN-05 budget.  It is a fast, deterministic
        registry lookup (<5ms, 0 retries) used exclusively by
        ExpandService via ``ExpandToolRouterLike``.

        The backing implementation uses
        ``IFabricRetrievalPort.discover_capabilities`` with a narrow
        exact-name intent as a pragmatic bridge until a dedicated
        ``IFabricRegistryPort`` is introduced.

        Note: Does NOT increment ``_tool_call_count``.
        """
        # Pragmatic bridge: use discover with exact capability_name as intent.
        # Future: replace with IFabricRegistryPort.lookup(name, version).
        result = await self._fabric_retrieval.discover_capabilities(
            intent=capability_name,
            top_k=1,
        )
        if result.capabilities:
            return result.capabilities[0]
        return None

    # -- Private helpers --

    def _check_tool_name(self, tool_name: str) -> None:
        """Raise ``UnknownToolError`` if tool_name not in routing table."""
        if tool_name not in self._ROUTING_TABLE:
            raise UnknownToolError(
                f"Unknown tool '{tool_name}'. "
                f"Valid tools: {sorted(self._ROUTING_TABLE.keys())}",
            )

    def _check_budget(self, tool_name: str) -> None:
        """Raise ``BudgetExhaustedError`` if PLAN-05 limit reached."""
        max_calls = self._config.max_tool_calls_per_plan
        if self._tool_call_count >= max_calls:
            log.warning(
                "tool_call_budget_exhausted tool=%s count=%d max=%d",
                tool_name,
                self._tool_call_count,
                max_calls,
            )
            raise BudgetExhaustedError(
                f"Tool call budget exhausted: {self._tool_call_count}/{max_calls} "
                f"calls used. Attempted: {tool_name}",
            )

    async def _dispatch(
        self,
        tool_name: str,
        port: Any,
        timeout_ms: int,
        max_retries: int,
        params: Dict[str, Any],
    ) -> Any:
        """Dispatch to the correct port method with timeout and retry.

        Each tool_name maps to a specific port method:
          - discover_capabilities -> port.discover_capabilities(...)
          - find_relevant_prompts -> port.find_relevant_prompts(...)
          - query_planning_context -> port.read_sections(...)
          - recall_for_planning -> port.recall(...)

        On timeout/exception, retries up to ``max_retries`` times.
        Retries do NOT double-count against PLAN-05 (SS11.5.3).
        """
        method, call_params = self._resolve_port_method(tool_name, port, params)
        timeout_s = timeout_ms / 1000.0

        last_exc: Optional[BaseException] = None
        for attempt in range(1 + max_retries):
            try:
                return await asyncio.wait_for(
                    method(**call_params),
                    timeout=timeout_s,
                )
            except asyncio.TimeoutError:
                last_exc = asyncio.TimeoutError(
                    f"{tool_name} timed out after {timeout_ms}ms "
                    f"(attempt {attempt + 1}/{1 + max_retries})"
                )
                log.debug(
                    "tool_dispatch_timeout tool=%s attempt=%d/%d timeout_ms=%d",
                    tool_name,
                    attempt + 1,
                    1 + max_retries,
                    timeout_ms,
                )
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                log.debug(
                    "tool_dispatch_error tool=%s attempt=%d/%d error=%s",
                    tool_name,
                    attempt + 1,
                    1 + max_retries,
                    exc,
                )
        # All attempts exhausted -- re-raise last exception.
        raise last_exc  # type: ignore[misc]

    @staticmethod
    def _resolve_port_method(
        tool_name: str,
        port: Any,
        params: Dict[str, Any],
    ) -> tuple[Any, Dict[str, Any]]:
        """Map tool_name to the concrete port method and normalised params.

        Returns (method, call_params) tuple.
        """
        if tool_name == "discover_capabilities":
            return port.discover_capabilities, {
                "domain": params.get("domain"),
                "intent": params.get("intent", ""),
                "safety_band": params.get("safety_band", "GREEN"),
                "top_k": params.get("top_k", 10),
            }
        if tool_name == "find_relevant_prompts":
            return port.find_relevant_prompts, {
                "intent": params.get("intent", ""),
                "domain": params.get("domain"),
                "safety_band": params.get("safety_band", "GREEN"),
                "top_k": params.get("top_k", 10),
            }
        if tool_name == "query_planning_context":
            return port.read_sections, {
                "sections": params.get("sections", []),
            }
        if tool_name == "recall_for_planning":
            return port.recall, {
                "query": params.get("query", ""),
                "trace_id": params.get("trace_id", ""),
            }
        # Should never reach here -- _check_tool_name() guards entry.
        msg = f"No port method mapping for tool '{tool_name}'"
        raise UnknownToolError(msg)  # pragma: no cover


__all__ = ["ToolCallRouter"]
