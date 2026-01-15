"""
M37: consolidation.batch_selector - P03 R0 Batch Selection Module

Wrapper module that adapts the P03 R0 phase implementation to the module
registry interface for use with the generic PipelineRunner.

This module bridges between:
- Module interface: async def run(message, context, **config) -> dict
- Phase interface: R0BatchSelector.run(tenant_id, space_id, ctx) -> (envelope, result)

Contract: k0/contracts/modules/consolidation.batch_selector.v1.yaml
Phase: k0/pipelines/p03/phases/r0_batch_selector.py
Dossier: P03_consolidation_dossier_v2.md §D.3.1 stage_00_select_batch

Usage (called by PipelineRunner):
    result = await run(message, context, **config)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


async def run(message: Any, context: Any, **config: Any) -> Dict[str, Any]:
    """
    Module entry point for P03 R0 Batch Selection.

    Adapts the R0BatchSelector phase to the standard module interface.

    Args:
        message: BusMessage with trigger payload (p03.consolidation.triggered.v1)
        context: PipelineContext with logger, syscalls, trace_id
        **config: Stage-specific configuration from pipeline YAML:
            - max_batch_size: Maximum events per batch (default 1000)
            - max_events_per_cycle: Hard cap on events (default 10000)
            - selection_strategy: importance_first|fifo|balanced
            - include_context_window: Whether to include context events
            - context_window_hours: Hours of context to include

    Returns:
        dict with:
            - batch_id: ULID batch identifier
            - event_count: Number of events selected
            - events: List of event records (serializable)
            - time_range: {start, end} timestamp range
            - status: "selected" | "empty" | "skip"
            - skip_reason: Reason if skipped (empty batch)

    Raises:
        ValueError: If message payload is malformed
        RuntimeError: If syscalls are not available
    """
    # Import phase implementation lazily to avoid circular imports
    from k0.pipelines.p03.phase_interface import P03RunnerContext
    from k0.pipelines.p03.phases.r0_batch_selector import R0BatchSelector, R0Config

    # Extract trigger payload from message
    try:
        if isinstance(message.payload, bytes):
            payload = json.loads(message.payload.decode("utf-8"))
        elif isinstance(message.payload, str):
            payload = json.loads(message.payload)
        else:
            payload = message.payload or {}
    except (json.JSONDecodeError, AttributeError) as e:
        logger.error(
            "Failed to parse trigger payload",
            extra={
                "module_id": "consolidation.batch_selector",
                "error": str(e),
            },
        )
        raise ValueError(f"Invalid trigger payload: {e}") from e

    # Extract tenant_id and space_id from message metadata or payload
    tenant_id = (
        getattr(message, "tenant_id", None) or message.metadata.get("tenant_id")
        if hasattr(message, "metadata")
        else None
    ) or payload.get("tenant_id", "default")

    space_id = getattr(message, "space_id", None) or "default"

    # Build R0 configuration from stage config
    r0_config = R0Config(
        batch_size=config.get("max_batch_size", 100),
        require_embedding_ready=config.get("require_embedding_ready", True),
        exclude_archived=config.get("exclude_archived", True),
        max_age_hours=config.get("context_window_hours", 0),
    )

    # Create phase instance
    phase = R0BatchSelector(config=r0_config)

    # Build P03RunnerContext from PipelineContext
    # The PipelineRunner provides context with syscalls and logger
    runner_ctx = P03RunnerContext(
        syscalls=context.syscalls,
        logger=context.logger,
        config=config,
    )

    # Execute the phase
    envelope, result = await phase.run(tenant_id, space_id, runner_ctx)

    # Convert result to module output format
    if envelope is None:
        # Empty batch or skip
        return {
            "batch_id": None,
            "event_count": 0,
            "events": [],
            "time_range": None,
            "status": "empty",
            "skip_reason": (
                result.skip_reason if hasattr(result, "skip_reason") else "No pending events"
            ),
            "duration_ms": result.duration_ms,
        }

    # Successful batch selection - serialize envelope data
    events_serializable = []
    for event in envelope.events:
        events_serializable.append(
            {
                "event_id": event.event_id,
                "content_text": event.content_text,
                "content_type": event.content_type,
                "simhash_hex": event.simhash_hex,
                "timestamp": event.timestamp,
                "channel_id": event.channel_id,
                "embedding_id": event.embedding_id,
                "sentiment_score": event.sentiment_score,
                "sentiment_label": event.sentiment_label,
            }
        )

    # Compute time range
    timestamps = [e.timestamp for e in envelope.events if e.timestamp]
    time_range = None
    if timestamps:
        time_range = {
            "start": min(timestamps),
            "end": max(timestamps),
        }

    return {
        "batch_id": envelope.context.batch_id,
        "cycle_id": envelope.context.cycle_id,
        "event_count": len(envelope.events),
        "events": events_serializable,
        "time_range": time_range,
        "status": "selected",
        "skip_reason": None,
        "duration_ms": result.duration_ms,
        # Pass envelope through for subsequent stages
        "envelope": envelope,
    }
