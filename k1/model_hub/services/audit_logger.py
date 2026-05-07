"""Audit logger for full request/response audit trail [F52].

Logs every Model Hub call with full metadata (MH-11): request_id,
consumer_id, capability, model_id, provider_id, tokens, cost, latency,
cache_hit, fallback_chain, trace_id.

Import graph (Layer 3 -- imports Layer 0 + Layer 1 + Layer 2)
--------------------------------------------------------------
k1.model_hub.services.audit_logger
  -> k1.model_hub.types   (Layer 0: HubRequest, HubResponse)
  -> stdlib only

NEVER import from any adapter or runtime module.

References
----------
- model_hub.mmd: AuditLogger service
- Invariant MH-11: Full audit trail for every call
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from k1.model_hub.types import CapabilityType, HubRequest, HubResponse

# ===========================================================================
# AuditRecord
# ===========================================================================


@dataclass(frozen=True)
class AuditRecord:
    """Full audit record for a single Model Hub call (MH-11)."""

    request_id: str
    trace_id: str
    consumer_id: str
    capability: CapabilityType
    model_id: str
    provider_id: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    latency_ms: int
    cache_hit: bool
    fallback_used: bool = False
    fallback_chain: List[str] = field(default_factory=list)
    error: Optional[str] = None


# ===========================================================================
# AuditLogger
# ===========================================================================


class AuditLogger:
    """In-memory audit logger for all Model Hub calls (MH-11).

    Every call is logged with full metadata for post-hoc analysis.
    Production deployments would push to an IEventPort or external store;
    this in-memory implementation supports testing and local dev.
    """

    def __init__(self) -> None:
        self._records: List[AuditRecord] = []

    def log(
        self,
        request: HubRequest,
        response: HubResponse,
        *,
        fallback_chain: Optional[List[str]] = None,
    ) -> AuditRecord:
        """Log a completed request/response pair.

        Args:
            request: Original HubRequest.
            response: Completed HubResponse with metadata.
            fallback_chain: Provider IDs attempted before success.

        Returns:
            The AuditRecord that was logged.
        """
        meta = response.metadata
        record = AuditRecord(
            request_id=meta.request_id,
            trace_id=meta.trace_id,
            consumer_id=request.constraints.consumer_id,
            capability=meta.capability,
            model_id=meta.model_id,
            provider_id=meta.provider_id,
            prompt_tokens=meta.usage.prompt_tokens,
            completion_tokens=meta.usage.completion_tokens,
            cost_usd=meta.cost_usd,
            latency_ms=meta.latency_ms,
            cache_hit=meta.cache_hit,
            fallback_used=meta.fallback_used,
            fallback_chain=fallback_chain or [],
        )
        self._records.append(record)
        return record

    def log_error(
        self,
        request: HubRequest,
        error: str,
        *,
        fallback_chain: Optional[List[str]] = None,
    ) -> AuditRecord:
        """Log a failed request.

        Args:
            request: Original HubRequest.
            error: Error message / exception string.
            fallback_chain: Provider IDs attempted before failure.

        Returns:
            The AuditRecord that was logged.
        """
        record = AuditRecord(
            request_id=request.request_id,
            trace_id=request.trace_id,
            consumer_id=request.constraints.consumer_id,
            capability=request.capability,
            model_id="",
            provider_id="",
            prompt_tokens=0,
            completion_tokens=0,
            cost_usd=0.0,
            latency_ms=0,
            cache_hit=False,
            fallback_chain=fallback_chain or [],
            error=error,
        )
        self._records.append(record)
        return record

    # -- Query -----------------------------------------------------------------

    @property
    def records(self) -> List[AuditRecord]:
        """All audit records."""
        return list(self._records)

    @property
    def count(self) -> int:
        """Total number of audit records."""
        return len(self._records)

    def clear(self) -> None:
        """Clear all audit records."""
        self._records.clear()


__all__ = [
    "AuditLogger",
    "AuditRecord",
]
