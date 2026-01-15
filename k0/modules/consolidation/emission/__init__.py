"""
R8 Emission Module — Issue 5.0.1

Provides components for R8 phase: emit events from outbox,
publish gaps to P06, update offsets, and emit cycle metrics.

Spec Reference:
    - Dossier §4.9 (R8 — Event Emission)
    - M5_EXECUTION.md (Epic 5.2)

Components (populated as issues complete):
    - EventEmitter: Bus event emission from outbox (Issue 5.2.11)
    - GapEmitter: Gap emission for P06 Active Learning (Issue 5.2.12)
    - OffsetManager: Offset and checkpoint persistence (Issue 5.2.13)
    - MetricsAggregator: Cycle metrics emission (Issue 5.2.14)

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

# Issue 5.2.11 — EventEmitter
from k0.modules.consolidation.emission.emitter import (
    CircuitBreakerConfig,
    EmitResult,
    EventEmitter,
    EventTopic,
    create_event_emitter,
)

# Issue 5.2.12 — GapEmitterModule
from k0.modules.consolidation.emission.gap_emitter import (
    GapEmitStats,
    GapEmitterConfig,
    GapEmitterModule,
    create_gap_emitter,
)

# Pending exports (added as issues complete):
# from k0.modules.consolidation.emission.offset_manager import OffsetManager
# from k0.modules.consolidation.emission.metrics import MetricsAggregator

__all__: list[str] = [
    # Issue 5.2.11 — EventEmitter
    "EventEmitter",
    "EmitResult",
    "CircuitBreakerConfig",
    "EventTopic",
    "create_event_emitter",
    # Issue 5.2.12 — GapEmitterModule
    "GapEmitterModule",
    "GapEmitStats",
    "GapEmitterConfig",
    "create_gap_emitter",
    # Issue 5.2.13 (to be added)
    # "OffsetManager",
    # Issue 5.2.14 (to be added)
    # "MetricsAggregator",
]
