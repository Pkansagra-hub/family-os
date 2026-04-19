"""FabricRetrievalAdapter -- production capability discovery adapter [F30].

Implements ``IFabricRetrievalPort`` (SS15.4) by wrapping a
``FabricRetrieval`` API object (Fabric Role 1: Discovery).

Adapter wiring (SS16.1.3, SS16.3):
    IFabricRetrievalPort -> FabricRetrievalAdapter -> FabricRetrieval

Design:
    - In-process method call (NOT HTTP, NOT event-based)
    - Same Python runtime as Fabric -- direct object reference
    - 50ms timeout per call, retry once on failure
    - No circuit breaker (in-process)
    - PLAN-06: no execution path on this interface

Import graph (Layer 2)
----------------------
k1.planner.adapters.fabric_retrieval_adapter
  -> k1.planner.ports.fabric_retrieval_port  (IFabricRetrievalPort)
  -> k1.fabric.types                         (RetrievalResult)
  -> asyncio, logging
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from k1.fabric.fabric import IRetrievalEngine
from k1.fabric.types import RetrievalResult

logger = logging.getLogger(__name__)


class FabricRetrievalAdapter:
    """Production capability discovery adapter (SS16.1.3).

    Wraps ``FabricRetrieval`` (Fabric Role 1) for in-process
    capability discovery and prompt retrieval.
    """

    __slots__ = ("_fabric", "_timeout_s", "_max_retries")

    def __init__(
        self,
        fabric_retrieval: IRetrievalEngine,
        timeout_ms: int = 50,
        max_retries: int = 1,
    ) -> None:
        self._fabric = fabric_retrieval
        self._timeout_s: float = timeout_ms / 1000.0
        self._max_retries: int = max_retries

    # ------------------------------------------------------------------
    # IFabricRetrievalPort implementation
    # ------------------------------------------------------------------

    async def discover_capabilities(
        self,
        domain: Optional[List[str]] = None,
        intent: str = "",
        safety_band: str = "GREEN",
        session_context: Optional[Dict[str, Any]] = None,
        top_k: int = 10,
    ) -> RetrievalResult:
        """Discover capabilities matching query from Fabric Registry.

        4-stage pipeline: Embed -> HardFilter -> SoftRank -> TopK.
        Timeout: ``timeout_ms`` per attempt, retries ``max_retries`` times.
        On failure: returns empty ``RetrievalResult`` (degraded, not fatal).
        """
        for attempt in range(1 + self._max_retries):
            try:
                return await asyncio.wait_for(
                    self._fabric.discover_capabilities(
                        domain=domain,
                        intent=intent,
                        safety_band=safety_band,
                        session_context=session_context,
                        top_k=top_k,
                    ),
                    timeout=self._timeout_s,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "discover_capabilities timed out (attempt %d/%d)",
                    attempt + 1,
                    1 + self._max_retries,
                    extra={"intent": intent, "timeout_s": self._timeout_s},
                )
            except Exception:
                logger.exception(
                    "discover_capabilities failed (attempt %d/%d)",
                    attempt + 1,
                    1 + self._max_retries,
                    extra={"intent": intent},
                )
        # All retries exhausted -- return empty result (degraded)
        logger.warning("discover_capabilities returning empty result (degraded)")
        return RetrievalResult()

    async def find_relevant_prompts(
        self,
        intent: str = "",
        domain: Optional[List[str]] = None,
        safety_band: str = "GREEN",
        top_k: int = 10,
    ) -> RetrievalResult:
        """Find prompt templates for agent-type steps.

        Same pipeline as ``discover_capabilities``, filtered to
        prompt-type contracts only.
        """
        for attempt in range(1 + self._max_retries):
            try:
                return await asyncio.wait_for(
                    self._fabric.find_relevant_prompts(
                        intent=intent,
                        domain=domain,
                        safety_band=safety_band,
                        top_k=top_k,
                    ),
                    timeout=self._timeout_s,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "find_relevant_prompts timed out (attempt %d/%d)",
                    attempt + 1,
                    1 + self._max_retries,
                    extra={"intent": intent, "timeout_s": self._timeout_s},
                )
            except Exception:
                logger.exception(
                    "find_relevant_prompts failed (attempt %d/%d)",
                    attempt + 1,
                    1 + self._max_retries,
                    extra={"intent": intent},
                )
        logger.warning("find_relevant_prompts returning empty result (degraded)")
        return RetrievalResult()


__all__ = ["FabricRetrievalAdapter"]
