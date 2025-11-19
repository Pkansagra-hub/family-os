"""
PipelineProtocol - Canonical Interface for K0 Pipelines

All pipelines must implement this protocol for auto-discovery and lifecycle management.
This is a Protocol (not ABC) to allow structural subtyping without explicit inheritance.

Architecture:
- Protocol-based contracts (duck typing with type checking)
- Class-level properties (not instance attributes)
- Lifecycle methods: on_startup, on_shutdown, handle
- Topic-based subscription (registered in on_startup)

Reference Implementation: See k0_pipeline_architecture.md Section 6 (P02 Example)
Related: M1 R1.3, M2 R2.2 (Loader)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, Sequence, runtime_checkable

if TYPE_CHECKING:
    from logging import Logger

    from k0.bus import BusMessage  # Import for type hints only

# BusMessage is now defined in k0.bus.core and imported by runtime code
# It includes: topic, payload, offset, trace_id, space_id, metadata
# This consolidates the canonical definition in one place


@dataclass(frozen=True, slots=True)
class PipelineContext:
    """
    Context provided to pipelines during on_startup().

    Contains capability-gated syscalls, configuration, and structured logger.
    Pipelines should store this context during startup for use in handle().

    Attributes:
        syscalls: Capability-gated storage adapter (M2 R2.1)
        config: Pipeline-specific configuration (from k0/config/pipelines.yml)
        logger: Structured logger with cognitive_trace_id support
        preloaded_models: Optional dict of preloaded NLP models (spaCy, VADER) from kernel startup

    Usage:
        async def on_startup(self, ctx: PipelineContext) -> None:
            self.syscalls = ctx.syscalls  # Store for later use
            self.logger = ctx.logger
            self.config = ctx.config
            self.preloaded_models = ctx.preloaded_models  # Access preloaded models
            # ... initialize resources

    Security:
        - syscalls enforces required_caps before storage access
        - logger includes trace_id for audit trails
        - config is read-only (frozen dataclass)
    """

    syscalls: Any  # Type: Syscalls (defined in M2 R2.1)
    config: dict[str, Any]
    logger: Logger
    preloaded_models: dict[str, Any] | None = None  # Optional preloaded NLP models


@runtime_checkable
class PipelineProtocol(Protocol):
    """
    Canonical interface for K0 pipelines.

    All pipelines must implement this protocol for auto-discovery by loader.py.
    This is a Protocol (not ABC) to allow structural subtyping without inheritance.

    Contract:
        - Class-level properties (pipeline_id, contract_version, etc.)
        - Lifecycle methods (on_startup, on_shutdown, handle)
        - No __init__ required (loader calls on_startup instead)

    Discovery:
        Loader scans k0/pipelines/p*.py for classes implementing this protocol.
        Validates all 7 class properties + 3 lifecycle methods before registration.

    Example:
        >>> class P02EpisodicWrite:
        ...     # Class-level contract
        ...     pipeline_id = "P02"
        ...     contract_version = 1
        ...     declared_topics = ["cognitive.memory.write.committed.v1"]
        ...     concurrency = 1
        ...     max_queue = 512
        ...     required_caps = ["st_hipp_store.write"]
        ...
        ...     async def on_startup(self, ctx: PipelineContext) -> None:
        ...         self.syscalls = ctx.syscalls
        ...         # ... initialize
        ...
        ...     async def on_shutdown(self) -> None:
        ...         # ... cleanup
        ...
        ...     async def handle(self, msg: BusMessage) -> None:
        ...         # ... process message

    Related:
        - M1 R1.3: Protocol definition
        - M2 R2.2: Loader implementation
        - Section 4 of k0_pipeline_architecture.md: Complete specification
    """

    # ========================================================================
    # CLASS-LEVEL CONTRACT (must be class attributes, not instance)
    # ========================================================================

    pipeline_id: str
    """
    Unique pipeline identifier (e.g., "P02", "P03").

    Requirements:
        - Must be uppercase alphanumeric (P[0-9]{2})
        - Must be unique across all pipelines
        - Used in st_pipeline_processed and st_pipeline_status tables

    Example: "P02"
    """

    contract_version: int
    """
    Schema version for compatibility checking.

    Purpose:
        - Loader validates protocol compatibility
        - Enables graceful degradation on version mismatch
        - Incremented on breaking changes to handle() signature

    Example: 1 (initial version)
    """

    declared_topics: Sequence[str]
    """
    Topics this pipeline subscribes to.

    Format: Hierarchical topic names (e.g., "cognitive.memory.write.committed.v1")
    Loader calls bus_dispatcher.subscribe(topic, pipeline.handle) for each topic.

    Performance:
        - O(k) dispatch where k = handlers per topic
        - Wildcard "*" not supported (use specific topics)

    Example: ["cognitive.memory.write.committed.v1", "cognitive.memory.update.v1"]
    """

    concurrency: int
    """
    Max concurrent handlers for this pipeline.

    Purpose:
        - Controls parallelism for CPU/IO-bound work
        - Loader creates asyncio.Semaphore(concurrency)
        - handle() acquires semaphore before processing

    Guidelines:
        - CPU-bound: 1-2 (use ProcessPoolExecutor internally)
        - IO-bound: 10-50 (network calls, storage queries)
        - Memory-sensitive: 1 (e.g., large embedding batches)

    Example: 1 (sequential processing)
    """

    max_queue: int
    """
    Max pending messages before backpressure.

    Purpose:
        - Prevents unbounded queue growth (OOM protection)
        - When queue full, dispatcher returns DEFERRED status
        - Client retries with exponential backoff

    Guidelines:
        - Fast pipelines (<50ms): 512-1024
        - Slow pipelines (>500ms): 128-256
        - Memory-constrained: 64-128

    Example: 512 (typical for fast pipelines)
    """

    required_caps: Sequence[str]
    """
    Capability requirements (least-privilege security).

    Format: "<table>.<operation>" (e.g., "st_hipp_store.write")
    Syscalls adapter enforces these before allowing storage access.

    Common Capabilities:
        - "st_hipp_store.write": Write to episodic memory
        - "st_hipp_store.read": Read episodic memory
        - "working_memory.write": Write to working memory
        - "embeddings.read": Query vector index
        - "embeddings.write": Insert embeddings

    Example: ["st_hipp_store.write"]
    """

    # ========================================================================
    # LIFECYCLE METHODS
    # ========================================================================

    async def on_startup(self, ctx: PipelineContext) -> None:
        """
        Initialize pipeline resources (called once at kernel boot).

        Called by loader after protocol validation, before topic subscription.
        Use this to:
            - Store syscalls, logger, config in instance variables
            - Initialize ProcessPoolExecutor, async resources
            - Pre-load models, open connections
            - Register topic subscriptions via ctx.bus_dispatcher.subscribe()

        Signature:
            async def on_startup(self, ctx: PipelineContext) -> None

        Args:
            ctx: PipelineContext with syscalls, config, logger

        Raises:
            Exception: If initialization fails (loader logs error and skips pipeline)

        Example:
            async def on_startup(self, ctx: PipelineContext) -> None:
                self.syscalls = ctx.syscalls
                self.logger = ctx.logger
                self.config = ctx.config
                self.executor = ProcessPoolExecutor(max_workers=2)
                ctx.logger.info(f"{self.pipeline_id} started")

        Performance:
            - Should complete in <100ms (blocks kernel boot)
            - Defer heavy initialization to first handle() call if needed
            - Use lazy loading for models (10-100MB)

        Related:
            - M2 R2.2: Loader calls this during boot
            - Section 7.3: Two-Phase Architecture (Phase-2 setup)
        """
        ...

    async def on_shutdown(self) -> None:
        """
        Clean up pipeline resources (called once at kernel shutdown).

        Called by kernel during graceful shutdown (SIGTERM/SIGINT handler).
        Use this to:
            - Close ProcessPoolExecutor
            - Flush pending writes
            - Close connections
            - Record shutdown timestamp

        Signature:
            async def on_shutdown(self) -> None

        Raises:
            Exception: Logged but does not block shutdown

        Example:
            async def on_shutdown(self) -> None:
                if hasattr(self, 'executor'):
                    self.executor.shutdown(wait=True)
                self.logger.info(f"{self.pipeline_id} shutdown complete")

        Performance:
            - Should complete in <5 seconds (shutdown timeout)
            - Use wait=True for ProcessPoolExecutor (finish pending work)
            - Don't block indefinitely (kernel will force-kill after timeout)

        Related:
            - M2 R2.3: Kernel integration (shutdown handler)
            - Section 8.12: Graceful Shutdown (production guardrail)
        """
        ...

    async def handle(self, msg: BusMessage) -> None:
        """
        Process single message (called for each subscribed topic event).

        This is the core processing method. Called by BusDispatcher after Phase-1
        commit for each message matching declared_topics.

        Signature:
            async def handle(self, msg: BusMessage) -> None

        Args:
            msg: BusMessage with topic, payload, offset, trace_id

        Raises:
            Exception: Caught by dispatcher, moved to DLQ after 5 retries

        Processing Pattern:
            1. Check idempotency (st_pipeline_processed)
            2. Parse payload (JSON/FlatBuffers)
            3. Perform core work (storage, enrichment, etc.)
            4. Emit receipt (st_pipeline_status: OK/ERROR/DEFERRED)
            5. Record processed (st_pipeline_processed)

        Example:
            async def handle(self, msg: BusMessage) -> None:
                # 1. Idempotency check
                if await self._already_processed(msg.offset):
                    return

                # 2. Parse payload
                event = json.loads(msg.payload)

                # 3. Core work
                await self.syscalls.hipp_store_upsert(
                    space_id=event["space_id"],
                    event_id=event["event_id"],
                    payload=event,
                    cognitive_trace_id=msg.trace_id
                )

                # 4. Emit receipt
                await self._emit_receipt(msg.offset, status="OK")

                # 5. Record processed
                await self._mark_processed(msg.offset)

        Performance:
            - Target: P95 < 100ms for fast pipelines
            - CPU-bound work: Use ProcessPoolExecutor (non-blocking)
            - IO-bound work: Use async/await (concurrent)
            - Batch small operations (< 10ms) for efficiency

        Error Handling:
            - Transient errors: Raise exception (dispatcher retries with backoff)
            - Permanent errors: Log + emit ERROR receipt (don't raise)
            - DLQ: After 5 retries, moved to st_dlq with error_fingerprint

        Related:
            - Section 6: P02 Complete Example (500+ lines reference)
            - Section 8: 12 Production Guardrails
            - M3 R3.1: P02 Implementation (reference pipeline)
        """
        ...


# ============================================================================
# Type Aliases for Convenience
# ============================================================================

Pipeline = PipelineProtocol  # Shorter alias for type hints
