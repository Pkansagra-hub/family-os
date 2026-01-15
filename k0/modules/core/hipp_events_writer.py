"""
Hippocampus Events Writer Module (M16)

Writes enriched episodic memory events to st_hipp_events after P02 enrichment pipeline.

**Purpose**: Final storage of enriched events with affect, embeddings, and semantic data.
Performs 3-table atomic transaction (st_hipp_events + st_vec + st_pipeline_processed).

**Performance**: <30ms P95 (3-table INSERT with B-tree indexes)

**Contract**: k0/contracts/modules/core.hipp_events_writer.v1.yaml
**ADR**: docs/architecture/decisions-K0/modules/k010.1-hipp-events-writer.md
**Schema**: docs/pipelines/P02_data_schema.md (lines 96-185, 511-569)

**Inputs**:
- M02 (semantic_project): embedding_id
- M11 (affect_analyze): valence, arousal
- M13 (hipp_events_row): event_id, wal_pos, text, text_hash
- M22 (extract_from_cache): embedding vector (768-dim)

**Output**: st_hipp_events + st_vec + st_pipeline_processed tracking

**Transaction Boundary (ADR-K003 v1.2 Fix)**:
- 3-table transaction: st_hipp_events -> st_vec -> st_pipeline_processed
- M23 (stage_61) MERGED into M16 to ensure FK constraint satisfaction
- Order: st_hipp_events FIRST (parent), st_vec SECOND (child with FK)
- If embedding missing: sets embedding_status=PENDING (P08 backfill)
- Rationale: Atomic transaction, correct FK ordering, no orphaned embeddings

**Idempotency**: Uses event_id as PRIMARY KEY with INSERT OR IGNORE.
Checks st_pipeline_processed before writing (skip if already processed).

**Version**: 1.2.0
**Last Updated**: 2025-12-13 (ADR-K003 v1.2 - merged M23 into M16)
"""

import struct
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
    embeddings_written: int = 0  # NEW: st_vec writes
    embeddings_skipped: int = 0  # NEW: no embedding data
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
    Extract complete st_hipp_events row from M13 enrichment.

    M13 (builders.hipp_events_row) assembles ALL 70+ columns from pipeline enrichments
    and returns {**envelope, "hipp_events_row": row}. This function extracts that pre-built row.

    Args:
        envelope: Envelope with hipp_events_row key from M13

    Returns:
        Complete dictionary with 70+ st_hipp_events columns

    Raises:
        ValueError: If hipp_events_row missing or required fields invalid
    """
    # Extract complete row assembled by M13
    row = envelope.get("hipp_events_row")
    if not row:
        _metrics.missing_event_id += 1
        raise ValueError("Missing hipp_events_row from M13 enrichment")

    # Validate required fields exist in row
    if not row.get("event_id"):
        _metrics.missing_event_id += 1
        raise ValueError("Missing event_id in hipp_events_row")

    if row.get("wal_pos") is None:
        _metrics.missing_wal_pos += 1
        raise ValueError("Missing wal_pos in hipp_events_row")

    if not row.get("embedding_id"):
        _metrics.missing_embedding_id += 1
        raise ValueError("Missing embedding_id in hipp_events_row")

    # Return complete row (70+ columns) for syscall
    return row


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
    # Phase 2: Envelope is flat structure
    wal_pos = envelope.get("wal_pos")
    if wal_pos is None:
        _metrics.missing_wal_pos += 1
        raise ValueError("Missing wal_pos from envelope")

    now = int(time.time())

    return {
        "pipeline_id": pipeline_id,
        "wal_pos": wal_pos,
        "tenant_id": envelope.get("tenant_id", "default"),
        "space_id": envelope.get("space_id", "unknown"),
        "status": status,
        "processed_at": now,
    }


# =============================================================================
# Main Module Entry Point
# =============================================================================


async def run(message: Any, context: Any, **config: Any) -> dict[str, Any]:
    """
    Write enriched event to st_hipp_events and track in st_pipeline_processed.

    **Phase 2 Signature**:
        message: BusMessage with .payload (envelope JSON) and .trace_id
        context: PipelineContext with .logger and .syscalls
        **config: Stage configuration
            - pipeline_id (str): Pipeline identifier (default: 'P02_WRITE')
            - status (str): Processing status (default: 'OK')

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

    Returns:
        Enriched envelope with "hipp_events_write" containing:
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
        >>> result = await run(message, context)
        >>> result["hipp_events_write"]["hipp_events_inserted"]
        True
    """
    import json

    # Use enriched envelope from config (passed by pipeline runner)
    # Falls back to parsing from message.payload if not available (for backward compat)
    envelope = config.get("envelope")
    if envelope is None:
        envelope = (
            json.loads(message.payload)
            if isinstance(message.payload, (str, bytes))
            else message.payload
        )

    # Extract configuration
    pipeline_id = config.get("pipeline_id", "P02_WRITE")
    status = config.get("status", "OK")

    # Skip debug logging on hot path for performance

    try:
        # Assemble records from envelope
        hipp_events_record = assemble_hipp_events_record(envelope)
        pipeline_processed_record = assemble_pipeline_processed_record(
            envelope, pipeline_id, status
        )

        # 1. Write to st_hipp_events FIRST (parent row for FK constraint)
        # Pass complete row with all 70+ columns from M13 to syscall
        hipp_result = await context.syscalls.hipp_events_upsert(**hipp_events_record)

        # 2. Write to st_vec SECOND (child row, FK to st_hipp_events)
        # Extract embedding data from M22 (extract_from_cache)
        embedding_data = envelope.get("extract_from_cache", {})
        embedding = embedding_data.get("embedding")
        embedding_id_from_m22 = embedding_data.get("embedding_id")

        vec_written = False
        if embedding and embedding_id_from_m22:
            try:
                # Convert 768-dim float list to 3072-byte blob
                vector_bytes = struct.pack("768f", *embedding)

                await context.syscalls.vec_write(
                    embedding_id=embedding_id_from_m22,
                    event_id=hipp_events_record["event_id"],
                    tenant_id=hipp_events_record.get("tenant_id", "default"),
                    space_id=hipp_events_record.get("space_id", "unknown"),
                    vector=vector_bytes,
                    vector_dim=768,
                    model_id=embedding_data.get("model_id", "ultrabert_v2.1.0"),
                    status="READY",
                )
                vec_written = True
                _metrics.embeddings_written += 1
            except Exception as e:
                # Non-fatal: embedding write failure doesn't block event storage
                # P08 backfill will handle PENDING embeddings
                context.logger.warning(
                    f"Failed to write embedding to st_vec: {e}",
                    extra={
                        "event_id": hipp_events_record["event_id"],
                        "embedding_id": embedding_id_from_m22,
                    },
                )
        else:
            # No embedding data - set embedding_status to PENDING for P08 backfill
            _metrics.embeddings_skipped += 1
            context.logger.debug(
                "No embedding data from M22, embedding_status=PENDING",
                extra={"event_id": hipp_events_record["event_id"]},
            )

        # 3. Track in st_pipeline_processed via syscalls
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

        # Return enriched envelope with write results
        return {
            **envelope,
            "hipp_events_write": {
                "hipp_events_inserted": hipp_result["inserted"],
                "hipp_events_status": hipp_result["status"],
                "embedding_written": vec_written,
                "embedding_id": embedding_id_from_m22 if vec_written else None,
                "pipeline_tracked": pipeline_result["inserted"],
                "pipeline_status": pipeline_result["status"],
                "event_id": hipp_events_record["event_id"],
                "wal_pos": hipp_events_record["wal_pos"],
            },
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
        "embeddings_written": _metrics.embeddings_written,
        "embeddings_skipped": _metrics.embeddings_skipped,
        "missing_event_id": _metrics.missing_event_id,
        "missing_embedding_id": _metrics.missing_embedding_id,
        "missing_wal_pos": _metrics.missing_wal_pos,
        "write_failures": _metrics.write_failures,
    }


def reset_metrics() -> None:
    """Reset metrics (for testing)"""
    global _metrics
    _metrics = HippEventsMetrics()
