"""
Hippocampus Events Writer Module (M16)

Writes enriched episodic memory events to st_hipp_events after P02 enrichment pipeline.

**Purpose**: Final storage of enriched events with affect, embeddings, and semantic data.
Performs 2-table atomic transaction (st_hipp_events + st_pipeline_processed).

**Performance**: <25ms P95 (2-table INSERT with B-tree indexes)

**Contract**: k0/contracts/modules/core.hipp_events_writer.v1.yaml
**ADR**: docs/architecture/decisions-K0/modules/k010.1-hipp-events-writer.md
**Schema**: docs/pipelines/P02_data_schema.md (lines 96-185, 511-569)

**Inputs**:
- M02 (semantic_project): embedding_id
- M11 (affect_analyze): valence, arousal
- M13 (hipp_events_row): event_id, wal_pos, text, text_hash

**Output**: st_hipp_events row + st_pipeline_processed tracking

**Transaction Boundary (CORRECTED)**:
- Previously 3-table transaction (included st_embedding_queue)
- Corrected to 2-table per Sketchboard Phase 9 Q2
- M14 writes st_embedding_queue separately

**Idempotency**: Uses event_id as PRIMARY KEY with INSERT OR IGNORE.
Checks st_pipeline_processed before writing (skip if already processed).

**Version**: 1.0.0
**Last Updated**: 2025-11-17
"""

import hashlib
import time
from dataclasses import dataclass
from typing import Any

# =============================================================================
# Metrics Tracking
# =============================================================================


@dataclass
class HippEventsMetrics:
    """Metrics for hippocampus events writer operations"""

    events_written: int = 0
    duplicates_skipped: int = 0
    pipeline_tracked: int = 0
    missing_event_id: int = 0
    missing_embedding_id: int = 0
    missing_wal_pos: int = 0
    write_failures: int = 0


_metrics = HippEventsMetrics()


# =============================================================================
# Record Assembly Functions
# =============================================================================


def assemble_hipp_events_record(envelope: dict[str, Any]) -> dict[str, Any]:
    """
    Assemble st_hipp_events record from enriched envelope.

    Args:
        envelope: Envelope with header, body, and enrichment outputs

    Returns:
        Dictionary with st_hipp_events fields

    Raises:
        ValueError: If required fields missing (event_id, embedding_id, wal_pos)
    """
    header = envelope.get("header", {})
    body = envelope.get("body", {})
    outputs = envelope.get("outputs", {})

    # Extract required fields with validation
    event_id = header.get("event_id")
    if not event_id:
        _metrics.missing_event_id += 1
        raise ValueError("Missing event_id from envelope header")

    wal_pos = header.get("wal_pos")
    if wal_pos is None:
        _metrics.missing_wal_pos += 1
        raise ValueError("Missing wal_pos from envelope header")

    # Extract enrichment outputs
    semantic_output = outputs.get("semantic_project", {})
    embedding_id = semantic_output.get("embedding_id")
    if not embedding_id:
        _metrics.missing_embedding_id += 1
        raise ValueError("Missing embedding_id from M02 semantic_project output")

    affect_output = outputs.get("affect_analyze", {})
    hipp_row_output = outputs.get("hipp_events_row", {})

    # Extract text and compute hash if not provided
    text = body.get("text", "")
    text_hash = hipp_row_output.get("text_hash")
    if not text_hash and text:
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

    now = int(time.time())

    return {
        "event_id": event_id,
        "wal_pos": wal_pos,
        "tenant_id": header.get("tenant_id", "default"),
        "space_id": header.get("space_id", "unknown"),
        "embedding_id": embedding_id,
        "text": text,
        "text_hash": text_hash,
        "valence": affect_output.get("valence"),
        "arousal": affect_output.get("arousal"),
        "privacy_band": header.get("privacy_band", "GREEN"),
        "cognitive_trace_id": header.get("cognitive_trace_id", "unknown"),
        "created_at": header.get("timestamp", now),
    }


def assemble_pipeline_processed_record(
    envelope: dict[str, Any], pipeline_id: str = "P02_WRITE", status: str = "OK"
) -> dict[str, Any]:
    """
    Assemble st_pipeline_processed tracking record.

    Args:
        envelope: Envelope with header
        pipeline_id: Pipeline identifier (default: P02_WRITE)
        status: Processing status (OK/ERROR/SKIPPED)

    Returns:
        Dictionary with st_pipeline_processed fields

    Raises:
        ValueError: If wal_pos missing from header
    """
    header = envelope.get("header", {})

    wal_pos = header.get("wal_pos")
    if wal_pos is None:
        _metrics.missing_wal_pos += 1
        raise ValueError("Missing wal_pos from envelope header")

    now = int(time.time())

    return {
        "pipeline_id": pipeline_id,
        "wal_pos": wal_pos,
        "tenant_id": header.get("tenant_id", "default"),
        "space_id": header.get("space_id", "unknown"),
        "status": status,
        "processed_at": now,
    }


# =============================================================================
# Main Module Entry Point
# =============================================================================


async def run(envelope: dict[str, Any], context: Any = None, **config: Any) -> dict[str, Any]:
    """
    Write enriched event to st_hipp_events and track in st_pipeline_processed.

    This is a Phase 2 declarative module that uses syscalls for storage operations.
    Performs 2-table transaction via separate syscall invocations (each creates
    its own UnitOfWork transaction).

    **Required Inputs** (from envelope):
    - header.event_id: Unique event identifier
    - header.wal_pos: WAL position for traceability
    - outputs.semantic_project.embedding_id: From M02
    - outputs.affect_analyze.valence/arousal: From M11 (optional)

    **Required Context**:
    - context.syscalls: Must have st_hipp_events.write capability
    - context.syscalls: Must have st_pipeline_processed.write capability

    Args:
        envelope: Enriched envelope with header, body, and module outputs
        context: PipelineContext with syscalls (capability-gated storage)
        **config: Module configuration (pipeline_id override, status override)

    Returns:
        Dictionary with:
        - hipp_events_inserted: bool
        - hipp_events_status: str
        - pipeline_tracked: bool
        - event_id: str
        - wal_pos: int

    Raises:
        ValueError: If required fields missing from envelope
        PermissionError: If syscalls lacks required capabilities
        RuntimeError: If storage operations fail

    Example:
        >>> result = await run(envelope, context)
        >>> result["hipp_events_inserted"]
        True
        >>> result["pipeline_tracked"]
        True
    """
    if context is None:
        raise ValueError("PipelineContext required (must provide context with syscalls)")

    # Extract configuration
    pipeline_id = config.get("pipeline_id", "P02_WRITE")
    status = config.get("status", "OK")

    try:
        # Assemble records from envelope
        hipp_events_record = assemble_hipp_events_record(envelope)
        pipeline_processed_record = assemble_pipeline_processed_record(
            envelope, pipeline_id, status
        )

        # Write to st_hipp_events via syscalls (creates UnitOfWork transaction)
        hipp_result = await context.syscalls.hipp_events_upsert(
            event_id=hipp_events_record["event_id"],
            wal_pos=hipp_events_record["wal_pos"],
            tenant_id=hipp_events_record["tenant_id"],
            space_id=hipp_events_record["space_id"],
            embedding_id=hipp_events_record["embedding_id"],
            text=hipp_events_record["text"],
            text_hash=hipp_events_record["text_hash"],
            valence=hipp_events_record["valence"],
            arousal=hipp_events_record["arousal"],
            privacy_band=hipp_events_record["privacy_band"],
            cognitive_trace_id=hipp_events_record["cognitive_trace_id"],
            created_at=hipp_events_record["created_at"],
        )

        # Track in st_pipeline_processed via syscalls (separate UnitOfWork)
        pipeline_result = await context.syscalls.pipeline_processed_upsert(
            pipeline_id=pipeline_processed_record["pipeline_id"],
            wal_pos=pipeline_processed_record["wal_pos"],
            tenant_id=pipeline_processed_record["tenant_id"],
            space_id=pipeline_processed_record["space_id"],
            status=pipeline_processed_record["status"],
            processed_at=pipeline_processed_record["processed_at"],
        )

        # Update metrics
        if hipp_result["inserted"]:
            _metrics.events_written += 1
        else:
            _metrics.duplicates_skipped += 1

        if pipeline_result["inserted"]:
            _metrics.pipeline_tracked += 1

        return {
            "hipp_events_inserted": hipp_result["inserted"],
            "hipp_events_status": hipp_result["status"],
            "pipeline_tracked": pipeline_result["inserted"],
            "pipeline_status": pipeline_result["status"],
            "event_id": hipp_events_record["event_id"],
            "wal_pos": hipp_events_record["wal_pos"],
        }

    except ValueError:
        # Missing required fields - don't retry
        _metrics.write_failures += 1
        raise

    except (AttributeError, TypeError):
        # Missing syscalls or invalid context - configuration error
        _metrics.write_failures += 1
        raise

    except Exception as e:
        # Check if it's a PermissionError - pass through without wrapping
        if type(e).__name__ == "PermissionError":
            _metrics.write_failures += 1
            raise

        # Storage operation failed
        _metrics.write_failures += 1
        raise RuntimeError(f"Failed to write hipp events: {e}") from e


# =============================================================================
# Metrics & Observability
# =============================================================================


def get_metrics() -> dict[str, Any]:
    """Return current metrics for observability"""
    return {
        "events_written": _metrics.events_written,
        "duplicates_skipped": _metrics.duplicates_skipped,
        "pipeline_tracked": _metrics.pipeline_tracked,
        "missing_event_id": _metrics.missing_event_id,
        "missing_embedding_id": _metrics.missing_embedding_id,
        "missing_wal_pos": _metrics.missing_wal_pos,
        "write_failures": _metrics.write_failures,
    }


def reset_metrics() -> None:
    """Reset metrics (for testing)"""
    global _metrics
    _metrics = HippEventsMetrics()
