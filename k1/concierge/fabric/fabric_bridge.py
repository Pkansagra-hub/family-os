"""
FabricPOCBridge -- IFabricPort → Existing CapabilityRegistry
=============================================================

Implements IFabricPort (K1 Fabric types) but delegates to the existing
POC CapabilityRegistry (dict-based discover/invoke). Translates between
K1 CapabilityRequest/CapabilityResult and POC dict patterns.

After M5 (Big Copy), the bridge swaps for the real K1 Fabric instance.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from k1.fabric.types import (
    CapabilityContract,
    CapabilityRequest,
    CapabilityResult,
    ErrorInfo,
    RetrievalResult,
    ScoredCapability,
)
from k1.concierge.fabric.capability_registry import CapabilityRegistry

logger = logging.getLogger(__name__)


class FabricPOCBridge:
    """Implements IFabricPort by delegating to the POC CapabilityRegistry.

    Constructor accepts the existing CapabilityRegistry instance.
    All 40 POC capabilities remain accessible through the bridge.
    """

    def __init__(self, registry: CapabilityRegistry) -> None:
        self._registry = registry

    # ------------------------------------------------------------------
    # IFabricPort: execute
    # ------------------------------------------------------------------

    async def execute(self, request: CapabilityRequest) -> CapabilityResult:
        """Execute a capability via the POC registry.

        Extracts capability_name + params from CapabilityRequest,
        calls registry.invoke(), wraps result in CapabilityResult.
        """
        start_ms = int(time.time() * 1000)

        try:
            poc_result = await self._registry.invoke(
                capability_name=request.capability_name,
                params=request.params,
                session_id=request.session_id or None,
            )
            duration = int(time.time() * 1000) - start_ms
            return self._to_k1_result(poc_result, request.request_id, request.trace_id, duration)
        except Exception as e:
            duration = int(time.time() * 1000) - start_ms
            logger.error("FabricPOCBridge.execute failed: %s", e)
            return CapabilityResult.failure_result(
                request_id=request.request_id,
                error_code="execution_error",
                error_message=str(e),
                retriable=False,
                provider_id="poc-bridge",
                trace_id=request.trace_id,
                duration_ms=duration,
            )

    # ------------------------------------------------------------------
    # IFabricPort: execute_batch
    # ------------------------------------------------------------------

    async def execute_batch(
        self,
        requests: List[CapabilityRequest],
        strategy: str = "PARALLEL",
    ) -> List[CapabilityResult]:
        """Execute multiple capabilities sequentially (POC doesn't support true parallel)."""
        results: List[CapabilityResult] = []
        for req in requests:
            result = await self.execute(req)
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # IFabricPort: discover_capabilities
    # ------------------------------------------------------------------

    async def discover_capabilities(
        self,
        domain: Optional[List[str]] = None,
        intent: str = "",
        safety_band: str = "GREEN",
        session_context: Optional[Dict[str, Any]] = None,
        top_k: int = 10,
    ) -> RetrievalResult:
        """Discover capabilities via POC registry fuzzy matching.

        Translates K1 list[str] domain to single POC domain string,
        wraps POC dict results as RetrievalResult with ScoredCapability items.
        """
        start_ms = int(time.time() * 1000)

        # POC discover() takes a single domain string
        poc_domain = domain[0] if domain else None

        try:
            poc_result = await self._registry.discover(
                intent=intent,
                domain=poc_domain,
            )
            duration = int(time.time() * 1000) - start_ms
            return self._to_k1_retrieval(poc_result, intent, duration)
        except Exception as e:
            duration = int(time.time() * 1000) - start_ms
            logger.error("FabricPOCBridge.discover_capabilities failed: %s", e)
            return RetrievalResult(
                capabilities=[],
                total_matched=0,
                query_latency_ms=duration,
                query_intent=intent,
            )

    # ------------------------------------------------------------------
    # IFabricPort: find_relevant_prompts
    # ------------------------------------------------------------------

    async def find_relevant_prompts(
        self,
        intent: str = "",
        domain: Optional[List[str]] = None,
        safety_band: str = "GREEN",
        top_k: int = 10,
    ) -> RetrievalResult:
        """POC has no prompt registry — returns empty."""
        return RetrievalResult(
            capabilities=[],
            total_matched=0,
            query_intent=intent,
        )

    # ------------------------------------------------------------------
    # Translation: POC result dict → K1 CapabilityResult
    # ------------------------------------------------------------------

    def _to_k1_result(
        self,
        poc_result: dict[str, Any],
        request_id: str,
        trace_id: str,
        duration_ms: int,
    ) -> CapabilityResult:
        """Convert POC handler result dict to K1 CapabilityResult.

        POC result shape: {success: bool, data: Any, error: str, duration_ms: int, ...}
        """
        success = poc_result.get("success", True)
        error_msg = poc_result.get("error", "")

        if success and not error_msg:
            # Extract data — POC handlers return various shapes
            data = poc_result.get("data") or poc_result
            if not isinstance(data, dict):
                data = {"result": data}
            return CapabilityResult.success_result(
                request_id=request_id,
                data=data,
                provider_id="poc-bridge",
                trace_id=trace_id,
                duration_ms=duration_ms,
                execution_time_ms=duration_ms,
            )
        else:
            return CapabilityResult.failure_result(
                request_id=request_id,
                error_code="capability_error",
                error_message=error_msg or "Unknown error",
                retriable=False,
                provider_id="poc-bridge",
                trace_id=trace_id,
                duration_ms=duration_ms,
            )

    # ------------------------------------------------------------------
    # Translation: POC discover result → K1 RetrievalResult
    # ------------------------------------------------------------------

    def _to_k1_retrieval(
        self,
        poc_result: dict[str, Any],
        intent: str,
        duration_ms: int,
    ) -> RetrievalResult:
        """Convert POC discover() result to K1 RetrievalResult.

        POC result shape: {capabilities: list[dict], count: int, hint?: str}
        Each capability dict: {name, description, domain, required_inputs, ...}
        """
        poc_caps = poc_result.get("capabilities", [])
        scored: list[ScoredCapability] = []

        for i, cap_dict in enumerate(poc_caps):
            contract = CapabilityContract(
                name=cap_dict.get("name", ""),
                description=cap_dict.get("description", ""),
                domain=[cap_dict.get("domain", "")] if cap_dict.get("domain") else [],
            )
            # POC uses word-overlap; assign descending scores for ordering
            score = max(0.0, 1.0 - (i * 0.05))
            scored.append(ScoredCapability(contract=contract, score=score))

        return RetrievalResult(
            capabilities=scored,
            total_matched=poc_result.get("count", len(scored)),
            query_latency_ms=duration_ms,
            query_intent=intent,
            index_size=self._registry.count,
        )
