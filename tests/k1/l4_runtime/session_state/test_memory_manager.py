"""
Integration test verifying MemoryManager tiered eviction and metrics emission.

ADRs: ADR-0018 (3-tier eviction), ADR-0024c (memory budgets), ADR-0029c (session-state metrics)
"""

import time
from typing import Tuple
from unittest.mock import AsyncMock, Mock

import flatbuffers
from prometheus_client import CollectorRegistry
from ward import fixture, test

from k0.obs.metrics import MetricsExporter
from k1.l4_runtime.session_state.control.control import SessionStateControl
from k1.l4_runtime.session_state.memory_manager import (
    CRITICAL_LIMIT_BYTES,
    MemoryManager,
    MemoryPressure,
)
from k1.l4_runtime.session_state.model.AgentScore import AgentScoreT
from k1.l4_runtime.session_state.model.BeliefsSection import BeliefsSectionT
from k1.l4_runtime.session_state.model.BlobRef import BlobRefT
from k1.l4_runtime.session_state.model.MultimodalSection import MultimodalSectionT
from k1.l4_runtime.session_state.model.ScoreboardSection import ScoreboardSectionT
from k1.l4_runtime.session_state.model.SessionState import SessionStateT
from k1.l4_runtime.session_state.model.UserFact import UserFactT
from k1.l4_runtime.session_state.model.wrapper import SessionStateWrapper
from k1.l5_infrastructure.bridge_k0.batch_client import BatchClient
from k1.l5_infrastructure.observability.metrics import K1MetricsCollector


FACT_COUNT = 200
FACT_VALUE_SIZE = 1024
TEXT_HISTORY_COUNT = 20
TEXT_ENTRY_SIZE = 512
AUDIO_BYTES = 48_000
from typing import Generator, Tuple
AGENT_SCORE_COUNT = 8


def _build_heavy_session_state() -> SessionStateWrapper:
    """Create a SessionStateWrapper seeded with large sections for eviction tests."""

    now_ms = int(time.time() * 1000)

    beliefs = BeliefsSectionT()
    facts = []
    for idx in range(FACT_COUNT):
        fact = UserFactT()
        fact.key = f"user.pref.{idx}"
        fact.value = "v" * FACT_VALUE_SIZE
        fact.source = "user_input"
        fact.createdAtMs = now_ms - 60_000
        fact.updatedAtMs = now_ms - 30_000
        fact.lastAccessedMs = now_ms - (idx * 1_000)
        fact.piiBand = 0
        facts.append(fact)
    beliefs.userFacts = facts
    beliefs.sectionSizeBytes = FACT_COUNT * (FACT_VALUE_SIZE + 64)
    beliefs.updatedAtMs = now_ms

    multimodal = MultimodalSectionT()
    audio = BlobRefT()
    audio.store = "k0_mm"
    audio.key = "audio-primary"
    audio.sizeBytes = AUDIO_BYTES
    audio.createdAtMs = now_ms - 15_000
    audio.mimeType = "audio/opus"
    multimodal.audio = audio
    multimodal.textHistory = ["t" * TEXT_ENTRY_SIZE for _ in range(TEXT_HISTORY_COUNT)]
    multimodal.lastModality = 1
    multimodal.sectionSizeBytes = AUDIO_BYTES + (TEXT_HISTORY_COUNT * TEXT_ENTRY_SIZE)
    multimodal.updatedAtMs = now_ms

    scoreboard = ScoreboardSectionT()
    scores = []
    for idx in range(AGENT_SCORE_COUNT):
        score = AgentScoreT()
        score.agentId = idx
        score.score = 0.6 + (idx * 0.05)
        score.confidence = 0.75
        score.basis = 1
        score.tasksCompleted = 10 + idx
        score.tasksFailed = idx // 2
        score.latencyP95Ms = 120 + idx
        score.lastUsedMs = now_ms - (idx * 5_000)
        scores.append(score)
    scoreboard.agentScores = scores
    scoreboard.sectionSizeBytes = AGENT_SCORE_COUNT * 32
    scoreboard.updatedAtMs = now_ms

    state_t = SessionStateT()
    state_t.sessionId = "session-memory-manager"
    state_t.userId = "user-demo"
    state_t.traceId = "trace-memory-demo"
    state_t.seqNo = 1
    state_t.beliefs = beliefs
    state_t.multimodal = multimodal
    state_t.scoreboard = scoreboard
    state_t.totalSizeBytes = (
        beliefs.sectionSizeBytes
        + multimodal.sectionSizeBytes
        + scoreboard.sectionSizeBytes
    )

    builder = flatbuffers.Builder(0)
    offset = state_t.Pack(builder)
    builder.Finish(offset)
    buffer = bytes(builder.Output())
    actual_size = len(buffer)
    if actual_size != state_t.totalSizeBytes:
        state_t.totalSizeBytes = actual_size
        builder = flatbuffers.Builder(actual_size + 1024)
        offset = state_t.Pack(builder)
        builder.Finish(offset)
        buffer = bytes(builder.Output())

    return SessionStateWrapper.from_bytes(buffer)


@fixture
def heavy_state_wrapper() -> SessionStateWrapper:
    return _build_heavy_session_state()


@fixture
def batch_client_stub() -> BatchClient:
    client = Mock(spec=BatchClient)
    client.add_delta = AsyncMock(return_value=None)
    client.flush = AsyncMock(return_value=None)
    return client


@fixture
def session_state_control(
    heavy_state_wrapper: SessionStateWrapper,
    batch_client_stub: BatchClient,
) -> SessionStateControl:
    return SessionStateControl(
        session_id="session-memory-manager",
        batch_client=batch_client_stub,
        initial_state=heavy_state_wrapper,
        flush_interval_ms=250,
        max_pending_deltas=100,
        enable_auto_flush=False,
        cognitive_trace_id="trace-memory-demo",
    )


@fixture
def isolated_metrics() -> Tuple[K1MetricsCollector, CollectorRegistry]:
    registry = CollectorRegistry()
    K1MetricsCollector._instance = None  # type: ignore[attr-defined]
    collector = K1MetricsCollector(
        metrics_exporter=MetricsExporter(
            namespace="k1_memory_test", registry=registry
        )
    )
    yield collector, registry
    K1MetricsCollector._instance = None  # type: ignore[attr-defined]


def _metric(registry: CollectorRegistry, name: str, labels: dict | None = None) -> float:
    value = registry.get_sample_value(name, labels or {})
    return 0.0 if value is None else float(value)


@test("memory manager reduces session footprint and records metrics")
async def _(
    session_state_control: SessionStateControl,
    isolated_metrics: Tuple[K1MetricsCollector, CollectorRegistry],
):
    metrics, registry = isolated_metrics
    manager = MemoryManager(
        session_state_control,
        audit_interval=0.1,
        metrics=metrics,
        cognitive_trace_id="trace-memory-demo",
    )

def isolated_metrics() -> Generator[Tuple[K1MetricsCollector, CollectorRegistry], None, None]:
    initial_fact_count = len(state_before.beliefs.userFacts or [])
    initial_scores = len(state_before.scoreboard.agentScores or [])
    assert (
        state_before.totalSizeBytes > CRITICAL_LIMIT_BYTES
    ), "Precondition: state must exceed critical limit"

    tier1_before = _metric(
        registry, "k1_memory_test_memory_evicted_bytes_total", {"tier": "tier1"}
    )
    tier2_before = _metric(
        registry, "k1_memory_test_memory_evicted_bytes_total", {"tier": "tier2"}
    )
    tier3_before = _metric(
        registry, "k1_memory_test_memory_evicted_bytes_total", {"tier": "tier3"}
    )

    audit = await manager.audit_memory()
    assert audit.pressure == MemoryPressure.CRITICAL
    assert audit.usage_bytes > CRITICAL_LIMIT_BYTES

    await manager._handle_pressure(audit)

    state_after = SessionStateT.InitFromObj(session_state_control._state._state)

    assert len(state_after.beliefs.userFacts or []) < initial_fact_count
    assert state_after.multimodal.audio is None
    assert len(state_after.scoreboard.agentScores or []) < initial_scores

    tier1_after = _metric(
    assert state_before.beliefs is not None
    assert state_before.multimodal is not None
    assert state_before.scoreboard is not None
        registry, "k1_memory_test_memory_evicted_bytes_total", {"tier": "tier1"}
    )
    tier2_after = _metric(
        registry, "k1_memory_test_memory_evicted_bytes_total", {"tier": "tier2"}
    )
    tier3_after = _metric(
        registry, "k1_memory_test_memory_evicted_bytes_total", {"tier": "tier3"}
    )

    assert tier1_after - tier1_before > 0
    assert tier2_after - tier2_before > 0
    assert tier3_after - tier3_before > 0

    pressure_value = _metric(registry, "k1_memory_test_memory_pressure_level")
    assert pressure_value == float(MemoryPressure.CRITICAL)

    eviction_events = _metric(
        registry,
        "k1_memory_test_session_state_evictions_total",
        {"tier": "tier1_pressure", "reason": "memory_pressure"},
    )
    assert eviction_events >= 1

    assert state_after.beliefs is not None
    assert state_after.multimodal is not None
    assert state_after.scoreboard is not None
    size_sample_count = _metric(
        registry,
        "k1_memory_test_session_state_size_bytes_count",
        {"section": "total"},
    )
    assert size_sample_count >= 1

    assert session_state_control.get_pending_delta_count() >= 1
