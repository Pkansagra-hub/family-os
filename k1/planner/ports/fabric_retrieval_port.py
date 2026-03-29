"""IFabricRetrievalPort -- Planner capability discovery protocol [F14].

The Fabric Retrieval port provides read-only access to the Capability
Registry's discovery and prompt retrieval API.  It is the Planner's window
into "what can the system do?" without executing anything (PLAN-06).

Design decisions (SS15.4)
-------------------------
- Discovery methods ONLY -- no ``invoke_capability``, no ``execute``, no
  write methods.  PLAN-06 is enforced at the interface level.
- Wraps FabricRetrieval's 4-stage pipeline: Embed -> HardFilter ->
  SoftRank -> TopK.
- In-process method call (NOT HTTP, NOT event-based).  <50ms per call.

Callers (SS11, tool budget PLAN-05: max 6 per plan)
----------------------------------------------------
- ToolCallRouter: ``discover_capabilities()`` in SKETCH and EXPAND
- ToolCallRouter: ``find_relevant_prompts()`` in EXPAND
- ValidateService: direct ``discover_capabilities()`` for capability
  existence checks

Adapter: FabricRetrievalAdapter [F30]

Import graph (Layer 1)
----------------------
k1.planner.ports.fabric_retrieval_port
  -> k1.fabric.types  (RetrievalResult)
  -> typing
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from k1.fabric.types import RetrievalResult


@runtime_checkable
class IFabricRetrievalPort(Protocol):
    """Read-only Fabric capability discovery port.

    This is a structural protocol (``typing.Protocol``).  Any object with
    matching method signatures satisfies it via structural subtyping.

    PLAN-06 enforcement
    -------------------
    This port exposes ``discover_capabilities()`` and
    ``find_relevant_prompts()`` ONLY.  There is no execution path on
    this interface.  A developer cannot accidentally execute a capability
    through this port because no execution method exists.
    """

    async def discover_capabilities(
        self,
        domain: Optional[List[str]] = None,
        intent: str = "",
        safety_band: str = "GREEN",
        session_context: Optional[Dict[str, Any]] = None,
        top_k: int = 10,
    ) -> RetrievalResult:
        """Discover capabilities matching the query from Fabric Registry.

        4-stage pipeline: Embed -> HardFilter -> SoftRank -> TopK.

        Args:
            domain: Domain tag filter(s) for hard-filtering.
            intent: Natural-language description of what is needed.
            safety_band: Caller's effective safety band (``"GREEN"``,
                ``"AMBER"``, ``"RED"``).
            session_context: Available session keys for context-aware
                filtering.
            top_k: Maximum number of results to return (max 25).

        Returns:
            ``RetrievalResult`` containing ranked ``ScoredCapability``
            items with similarity scores.
        """
        ...  # pragma: no cover

    async def find_relevant_prompts(
        self,
        intent: str = "",
        domain: Optional[List[str]] = None,
        safety_band: str = "GREEN",
        top_k: int = 10,
    ) -> RetrievalResult:
        """Find prompt templates for agent-type steps.

        Same pipeline as ``discover_capabilities``, filtered to
        prompt-type contracts only.  Used by ToolCallRouter during
        EXPAND to find prompt templates for ``PlanStep.prompt_template``.

        Args:
            intent: Natural-language description of the step intent.
            domain: Domain tag filter(s).
            safety_band: Caller's effective safety band.
            top_k: Maximum number of results to return.

        Returns:
            ``RetrievalResult`` containing ranked prompt-type contracts.
        """
        ...  # pragma: no cover


__all__ = ["IFabricRetrievalPort"]
