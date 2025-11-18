"""
M17: core.event_emitter - Event Emission Module (P02 Write Pipeline)

Epic 4.5.2: Event Emitter
Contract: k0/contracts/modules/core.event_emitter.v1.yaml

PURPOSE
-------
Emits 6 completion events to st_outbox after storage commit (M16).
Implements transactional outbox pattern for event-driven architecture.

Events emitted:
1. workspace.wm.updated - Working memory state change
2. affect.analyzed - Emotional analysis completion
3. space.resolution - Space routing decision
4. embedding.enqueue - Vector embedding request
5. hippocampus.pattern_separated - Memory encoding complete
6. write.complete - P02 pipeline completion

ARCHITECTURAL CONTEXT
---------------------
Phase: P02 Write Pipeline (Epic 4.5.2)
Position: Final module after M16 (hipp_events_writer)
Input: p02.storage.committed.v1 (from M16)
Output: 6 event topics (st_outbox writes)

CAPABILITY REQUIREMENTS
-----------------------
- st_outbox.write: Required for event emission

PERFORMANCE TARGETS
-------------------
- Latency: <10ms P95 for 6-event batch
- Method: Single syscall (outbox_emit_batch)
- Idempotency: Fingerprint-based deduplication

RELATED DOCS
------------
- docs/plans/P02_implementation_plan.md (Epic 4.5.2, lines 6900-7050)
- k0/contracts/modules/core.event_emitter.v1.yaml (Contract)
- docs/pipelines/P02_write_dossier.md (Section 7.3: Transactional Outbox)

AUTHOR: Intelligence Kernel Team
DATE: 2024-12-27
"""

import hashlib
from typing import Any

# Module-level metrics (non-persistent, reset on restart)
_events_emitted = 0
_events_failed = 0
_total_latency_ms = 0.0


async def run(
    envelope: dict[str, Any],
    context: Any = None,
    **config: Any,
) -> dict[str, Any]:
    """
    Emit 6 completion events after M16 storage commit.

    Reads enrichments from envelope, builds 6 event payloads, and emits
    to st_outbox via syscalls.outbox_emit_batch(). Uses transactional
    outbox pattern for guaranteed event delivery.

    Args:
        envelope: Envelope with enrichments from M01-M16
            Required keys:
                - enrichments.space_resolver (space_id, tenant_id, envelope_id)
                - enrichments.working_memory (snapshot)
                - enrichments.affect_analyzer (valence, arousal, emotion)
                - enrichments.embedding_queue (embed_event_id)
                - enrichments.hipp_events (hipp_event_id)
        context: Pipeline context with syscalls capability
        **config: Module configuration
            - retry_backoff_ms: Backoff for failed events (default: 1000)
            - max_retry_attempts: Max retry count (default: 3)
            - enable_telemetry_event: Emit telemetry events (default: false)
            - batch_emit_enabled: Use batch emission (default: true)

    Returns:
        Dict with operation summary:
            {
                "events_emitted": <count>,
                "topics": [<topic_names>],
                "operation": "event_emitter",
                "status": "success"
            }

    Raises:
        KeyError: If required enrichments missing
        ValueError: If event structure invalid
        PermissionError: If st_outbox.write capability missing

    Performance:
        - Target: <10ms P95 for 6-event batch (contract requirement)
        - Single syscall: Batch emission for efficiency
        - Idempotency: Fingerprint-based deduplication

    Example:
        >>> envelope = {
        ...     "enrichments": {
        ...         "space_resolver": {"space_id": "space_123", ...},
        ...         "working_memory": {"snapshot": {...}},
        ...         "affect_analyzer": {"valence": 0.8, ...},
        ...         "embedding_queue": {"embed_event_id": "embed_456", ...},
        ...         "hipp_events": {"hipp_event_id": "hipp_789", ...},
        ...     }
        ... }
        >>> result = await run(envelope, context)
        >>> print(result["events_emitted"])  # 6
    """
    global _events_emitted, _events_failed, _total_latency_ms

    # Extract config (for future use - retry/telemetry planned)
    _ = config.get("retry_backoff_ms", 1000)
    _ = config.get("max_retry_attempts", 3)
    _ = config.get("enable_telemetry_event", False)
    _ = config.get("batch_emit_enabled", True)

    # Validate envelope structure
    if "enrichments" not in envelope:
        raise KeyError("Envelope missing 'enrichments' key (required for event emission)")

    enrichments = envelope["enrichments"]

    # Validate required enrichments
    required_enrichments = [
        "space_resolver",
        "working_memory",
        "affect_analyzer",
        "embedding_queue",
        "hipp_events",
    ]
    missing = [e for e in required_enrichments if e not in enrichments]
    if missing:
        raise KeyError(f"Envelope missing required enrichments: {missing}")

    # Extract common fields
    space_data = enrichments["space_resolver"]
    space_id = space_data["space_id"]
    tenant_id = space_data["tenant_id"]
    envelope_id = space_data.get("envelope_id", "unknown")

    # Build 6 events
    events = []

    # Event 1: workspace.wm.updated
    wm_event = _build_workspace_wm_event(
        tenant_id=tenant_id,
        space_id=space_id,
        envelope_id=envelope_id,
        enrichments=enrichments,
    )
    events.append(wm_event)

    # Event 2: affect.analyzed
    affect_event = _build_affect_analyzed_event(
        tenant_id=tenant_id,
        space_id=space_id,
        envelope_id=envelope_id,
        enrichments=enrichments,
    )
    events.append(affect_event)

    # Event 3: space.resolution
    space_event = _build_space_resolution_event(
        tenant_id=tenant_id,
        space_id=space_id,
        envelope_id=envelope_id,
        enrichments=enrichments,
    )
    events.append(space_event)

    # Event 4: embedding.enqueue
    embed_event = _build_embedding_enqueue_event(
        tenant_id=tenant_id,
        space_id=space_id,
        envelope_id=envelope_id,
        enrichments=enrichments,
    )
    events.append(embed_event)

    # Event 5: hippocampus.pattern_separated
    hipp_event = _build_hippocampus_pattern_separated_event(
        tenant_id=tenant_id,
        space_id=space_id,
        envelope_id=envelope_id,
        enrichments=enrichments,
    )
    events.append(hipp_event)

    # Event 6: write.complete
    complete_event = _build_write_complete_event(
        tenant_id=tenant_id,
        space_id=space_id,
        envelope_id=envelope_id,
        enrichments=enrichments,
    )
    events.append(complete_event)

    # Emit events via syscalls
    import time

    start_time = time.perf_counter()

    try:
        result = await context.syscalls.outbox_emit_batch(events)

        # Update metrics
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        _events_emitted += result["events_inserted"]
        _total_latency_ms += elapsed_ms

        return {
            "events_emitted": result["events_inserted"],
            "topics": [e["driver"] for e in events],
            "operation": "event_emitter",
            "status": "success",
            "latency_ms": elapsed_ms,
        }

    except Exception:
        # Update failure metrics
        _events_failed += len(events)

        # Re-raise for pipeline error handling
        raise


def _build_workspace_wm_event(
    tenant_id: str,
    space_id: str,
    envelope_id: str,
    enrichments: dict[str, Any],
) -> dict[str, Any]:
    """
    Build workspace.wm.updated event.

    Signals working memory state change. Consumed by workspace observers
    for UI updates, notifications, and context tracking.

    Args:
        tenant_id: Tenant identifier
        space_id: Space identifier
        envelope_id: Source envelope identifier
        enrichments: Envelope enrichments (working_memory required)

    Returns:
        Event dict with st_outbox schema:
            {
                "tenant_id": <tenant>,
                "space_id": <space>,
                "driver": "workspace.wm.updated",
                "op_kind": "EVENT_EMIT",
                "payload": {
                    "envelope_id": <id>,
                    "working_memory": <snapshot>,
                    "timestamp": <iso8601>
                },
                "fingerprint": <sha256>,
                "wal_pos": 0
            }
    """
    wm_data = enrichments["working_memory"]

    payload = {
        "envelope_id": envelope_id,
        "working_memory": wm_data.get("snapshot", {}),
        "timestamp": wm_data.get("timestamp", ""),
    }

    fingerprint = _generate_fingerprint(
        space_id=space_id,
        topic="workspace.wm.updated",
        envelope_id=envelope_id,
    )

    return {
        "tenant_id": tenant_id,
        "space_id": space_id,
        "driver": "workspace.wm.updated",
        "op_kind": "EVENT_EMIT",
        "payload": payload,
        "fingerprint": fingerprint,
        "wal_pos": 0,
    }


def _build_affect_analyzed_event(
    tenant_id: str,
    space_id: str,
    envelope_id: str,
    enrichments: dict[str, Any],
) -> dict[str, Any]:
    """
    Build affect.analyzed event.

    Signals emotional analysis completion. Consumed by affect-aware
    systems for response modulation and emotional tracking.

    Args:
        tenant_id: Tenant identifier
        space_id: Space identifier
        envelope_id: Source envelope identifier
        enrichments: Envelope enrichments (affect_analyzer required)

    Returns:
        Event dict with st_outbox schema
    """
    affect_data = enrichments["affect_analyzer"]

    payload = {
        "envelope_id": envelope_id,
        "valence": affect_data.get("valence", 0.0),
        "arousal": affect_data.get("arousal", 0.0),
        "emotion": affect_data.get("emotion", "neutral"),
        "confidence": affect_data.get("confidence", 0.0),
    }

    fingerprint = _generate_fingerprint(
        space_id=space_id,
        topic="affect.analyzed",
        envelope_id=envelope_id,
    )

    return {
        "tenant_id": tenant_id,
        "space_id": space_id,
        "driver": "affect.analyzed",
        "op_kind": "EVENT_EMIT",
        "payload": payload,
        "fingerprint": fingerprint,
        "wal_pos": 0,
    }


def _build_space_resolution_event(
    tenant_id: str,
    space_id: str,
    envelope_id: str,
    enrichments: dict[str, Any],
) -> dict[str, Any]:
    """
    Build space.resolution event.

    Signals space routing decision. Consumed by routing systems for
    space-based message delivery and authorization tracking.

    Args:
        tenant_id: Tenant identifier
        space_id: Space identifier
        envelope_id: Source envelope identifier
        enrichments: Envelope enrichments (space_resolver required)

    Returns:
        Event dict with st_outbox schema
    """
    space_data = enrichments["space_resolver"]

    payload = {
        "envelope_id": envelope_id,
        "space_id": space_id,
        "resolution_method": space_data.get("resolution_method", "direct"),
        "visibility": space_data.get("visibility", "private"),
    }

    fingerprint = _generate_fingerprint(
        space_id=space_id,
        topic="space.resolution",
        envelope_id=envelope_id,
    )

    return {
        "tenant_id": tenant_id,
        "space_id": space_id,
        "driver": "space.resolution",
        "op_kind": "EVENT_EMIT",
        "payload": payload,
        "fingerprint": fingerprint,
        "wal_pos": 0,
    }


def _build_embedding_enqueue_event(
    tenant_id: str,
    space_id: str,
    envelope_id: str,
    enrichments: dict[str, Any],
) -> dict[str, Any]:
    """
    Build embedding.enqueue event.

    Signals vector embedding request. Consumed by embedding workers
    for async vector generation and index updates.

    Args:
        tenant_id: Tenant identifier
        space_id: Space identifier
        envelope_id: Source envelope identifier
        enrichments: Envelope enrichments (embedding_queue required)

    Returns:
        Event dict with st_outbox schema
    """
    embed_data = enrichments["embedding_queue"]

    payload = {
        "envelope_id": envelope_id,
        "embed_event_id": embed_data.get("embed_event_id", ""),
        "text_hash": embed_data.get("text_hash", ""),
        "priority": embed_data.get("priority", "normal"),
    }

    fingerprint = _generate_fingerprint(
        space_id=space_id,
        topic="embedding.enqueue",
        envelope_id=envelope_id,
    )

    return {
        "tenant_id": tenant_id,
        "space_id": space_id,
        "driver": "embedding.enqueue",
        "op_kind": "EVENT_EMIT",
        "payload": payload,
        "fingerprint": fingerprint,
        "wal_pos": 0,
    }


def _build_hippocampus_pattern_separated_event(
    tenant_id: str,
    space_id: str,
    envelope_id: str,
    enrichments: dict[str, Any],
) -> dict[str, Any]:
    """
    Build hippocampus.pattern_separated event.

    Signals memory encoding completion. Consumed by memory systems
    for indexing, retrieval, and consolidation workflows.

    Args:
        tenant_id: Tenant identifier
        space_id: Space identifier
        envelope_id: Source envelope identifier
        enrichments: Envelope enrichments (hipp_events required)

    Returns:
        Event dict with st_outbox schema
    """
    hipp_data = enrichments["hipp_events"]

    payload = {
        "envelope_id": envelope_id,
        "hipp_event_id": hipp_data.get("hipp_event_id", ""),
        "pattern_type": hipp_data.get("pattern_type", "episodic"),
        "encoding_timestamp": hipp_data.get("encoding_timestamp", ""),
    }

    fingerprint = _generate_fingerprint(
        space_id=space_id,
        topic="hippocampus.pattern_separated",
        envelope_id=envelope_id,
    )

    return {
        "tenant_id": tenant_id,
        "space_id": space_id,
        "driver": "hippocampus.pattern_separated",
        "op_kind": "EVENT_EMIT",
        "payload": payload,
        "fingerprint": fingerprint,
        "wal_pos": 0,
    }


def _build_write_complete_event(
    tenant_id: str,
    space_id: str,
    envelope_id: str,
    enrichments: dict[str, Any],
) -> dict[str, Any]:
    """
    Build write.complete event.

    Signals P02 pipeline completion. Consumed by orchestration systems
    for workflow coordination, SLA tracking, and completion notifications.

    Args:
        tenant_id: Tenant identifier
        space_id: Space identifier
        envelope_id: Source envelope identifier
        enrichments: Envelope enrichments (all modules)

    Returns:
        Event dict with st_outbox schema
    """
    payload = {
        "envelope_id": envelope_id,
        "pipeline": "p02_write",
        "modules_executed": list(enrichments.keys()),
        "completion_timestamp": enrichments.get("hipp_events", {}).get("encoding_timestamp", ""),
    }

    fingerprint = _generate_fingerprint(
        space_id=space_id,
        topic="write.complete",
        envelope_id=envelope_id,
    )

    return {
        "tenant_id": tenant_id,
        "space_id": space_id,
        "driver": "write.complete",
        "op_kind": "EVENT_EMIT",
        "payload": payload,
        "fingerprint": fingerprint,
        "wal_pos": 0,
    }


def _generate_fingerprint(space_id: str, topic: str, envelope_id: str) -> str:
    """
    Generate idempotency fingerprint for event.

    Uses SHA256(space_id || topic || envelope_id) to ensure uniqueness
    per event type per envelope. Prevents duplicate event emission.

    Args:
        space_id: Space identifier
        topic: Event topic name
        envelope_id: Source envelope identifier

    Returns:
        Hex-encoded SHA256 hash (64 characters)

    Example:
        >>> fingerprint = _generate_fingerprint("space_123", "workspace.wm.updated", "env_456")
        >>> len(fingerprint)  # 64
        64
    """
    data = f"{space_id}::{topic}::{envelope_id}"
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def get_metrics() -> dict[str, Any]:
    """
    Get module-level metrics.

    Returns current counters for events emitted, failures, and latency.
    Used for observability and performance monitoring.

    Returns:
        Dict with metrics:
            {
                "events_emitted": <count>,
                "events_failed": <count>,
                "total_latency_ms": <milliseconds>,
                "avg_latency_ms": <milliseconds>
            }

    Note:
        Metrics are non-persistent and reset on process restart.
        Use for runtime monitoring only.
    """
    global _events_emitted, _events_failed, _total_latency_ms

    avg_latency = _total_latency_ms / _events_emitted if _events_emitted > 0 else 0.0

    return {
        "events_emitted": _events_emitted,
        "events_failed": _events_failed,
        "total_latency_ms": _total_latency_ms,
        "avg_latency_ms": avg_latency,
    }


def reset_metrics() -> None:
    """
    Reset module-level metrics to zero.

    Used for testing and metric window resets. Should not be called
    in production code.
    """
    global _events_emitted, _events_failed, _total_latency_ms

    _events_emitted = 0
    _events_failed = 0
    _total_latency_ms = 0.0
