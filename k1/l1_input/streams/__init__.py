"""
Layer 1 - Input Processing

ADR References:
- ADR-0004: 52-Module 5-Layer Architecture (Layer 1 definition)
- ADR-0004a: Layer 1-2 Communication (Event Bus)
- ADR-0004b: Layer Dependency Rules (L1→L5 only)

Purpose:
Unified multi-modal input bus + 3-tier intent routing with
ambient context awareness and multi-speaker support.

Performance Budget: <10ms P95 total

Modules:
- streams/stream_switch: Multi-modal input bus (<5ms)
- streams/operators: VAD, ASR, TTS, speaker ID, location
- orchestration/intent_router: 3-tier intent classification (<50ms)
- orchestration/meta_policy: Proactivity & clarification (<5ms)
- sensors: Ambient sensor fusion (PIR, mmWave, BLE)
"""

from . import stream_switch
from . import operators
from ..orchestration import intent_router
from ..orchestration import meta_policy
from .. import sensors

__all__ = [
    "stream_switch",
    "operators",
    "intent_router",
    "meta_policy",
    "sensors",
]
