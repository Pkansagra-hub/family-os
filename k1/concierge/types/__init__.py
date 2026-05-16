"""
k1.concierge.types -- Re-export hub for types used by Concierge port protocols.

Every type below already exists in its canonical location. This module
provides a single import target for Concierge adapters and tests.

No new types are invented here.
"""

from __future__ import annotations

from k1.bus.envelope import Envelope
from k1.bus.ports import SubscriptionHandle
from k1.bus.ports.bus import IBus
from k1.concierge.orchestrator.types import AggregatedResult, TaskEnvelope
from k1.fabric.types import CapabilityRequest, CapabilityResult
from k1.model_hub.types import HubChunk, HubRequest, HubResponse

__all__ = [
    "AggregatedResult",
    "CapabilityRequest",
    "CapabilityResult",
    "Envelope",
    "HubChunk",
    "HubRequest",
    "HubResponse",
    "IBus",
    "SubscriptionHandle",
    "TaskEnvelope",
]
