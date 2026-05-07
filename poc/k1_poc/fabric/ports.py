"""
IFabricPort -- Typed Port Protocol for POC ↔ K1 Fabric Bridge
===============================================================

ADR: M2 (ICapabilityPort — Bridge POC Tools → K1 Fabric)
Spec: k1/fabric/fabric.py — Fabric container class (L1257-1340)

This protocol matches K1 Fabric's public API surface so that:
  1. POC tools call IFabricPort instead of untyped callbacks
  2. FabricPOCBridge satisfies it during M2-M5 (delegates to CapabilityRegistry)
  3. After M5, the real K1 Fabric instance satisfies it natively (zero-change swap)

Types used: K1 Fabric types (CapabilityRequest, CapabilityResult, RetrievalResult)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from k1.fabric.types import CapabilityRequest, CapabilityResult, RetrievalResult


@runtime_checkable
class IFabricPort(Protocol):
    """Typed port for capability execution and discovery.

    Matches K1 Fabric container's public API (k1/fabric/fabric.py Fabric class).
    All POC tool functions call this instead of untyped callbacks.
    """

    async def execute(self, request: CapabilityRequest) -> CapabilityResult:
        """Execute a single capability request through the Fabric pipeline."""
        ...

    async def execute_batch(
        self,
        requests: List[CapabilityRequest],
        strategy: str = "PARALLEL",
    ) -> List[CapabilityResult]:
        """Execute multiple capability requests. Strategy: PARALLEL or SEQUENTIAL."""
        ...

    async def discover_capabilities(
        self,
        domain: Optional[List[str]] = None,
        intent: str = "",
        safety_band: str = "GREEN",
        session_context: Optional[Dict[str, Any]] = None,
        top_k: int = 10,
    ) -> RetrievalResult:
        """Discover capabilities matching intent/domain via semantic retrieval."""
        ...

    async def find_relevant_prompts(
        self,
        intent: str = "",
        domain: Optional[List[str]] = None,
        safety_band: str = "GREEN",
        top_k: int = 10,
    ) -> RetrievalResult:
        """Find relevant prompt templates. POC returns empty."""
        ...
