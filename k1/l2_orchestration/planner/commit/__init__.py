"""
Commit Stage - K0 WAL Integration (Stage 4 of 4)

**ADR Reference:** ADR-0007d (Commit Stage K0 WAL Integration)

**Purpose:**
Persist validated plan to K0 Write-Ahead Log and lock SessionState.

**Key Responsibilities:**
1. Serialize plan to FlatBuffers (FlowDef format, <1ms)
2. Write to K0 WAL via HTTP POST /k0/wal/append (<5ms)
3. Lock SessionState current_flow field (prevent concurrent plans)
4. Emit STATE_DELTA event for K0 sync (<2ms)
5. Generate idempotency key (hash(session+plan+time_bucket), 60s window)

**Performance Target:** <10ms P95

**Input:** ValidatedPlan (from Stage 3)
**Output:** CommitResult (flow_id: str, committed_at: float)

**K0 Integration:**
- WAL Topic: PLAN_COMMITTED
- SessionState field: control.current_flow
- STATE_DELTA emission: Field path updates
- Idempotency: Hash-based deduplication, 60s window

**Error Handling:**
- K0 WAL write failure → Retry with exponential backoff (max 3 retries)
- SessionState lock conflict → Return conflict error (concurrent plan detected)
- Idempotency violation → Return duplicate error (plan already committed)

**Observability:**
- Metrics: commit_latency_ms, commit_success_rate
- Tracing: K0 WAL write span, SessionState lock span
- Logging: commit_success, commit_failure, commit_conflict events
"""

from .flatbuffers_serializer import FlatBuffersSerializer
from .idempotency_checker import IdempotencyChecker
from .k0_wal_writer import K0WalWriter
from .session_state_locker import SessionStateLocker
from .state_delta_emitter import StateDeltaEmitter

__all__ = [
    "FlatBuffersSerializer",
    "K0WalWriter",
    "SessionStateLocker",
    "StateDeltaEmitter",
    "IdempotencyChecker",
]
