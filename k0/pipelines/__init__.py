"""
K0 Pipelines - User-Space Processing Infrastructure

This package provides the protocol interface and discovery system for pluggable
pipelines that process events after Phase-1 ACID commit.

Architecture Pattern:
- Immutable K0 kernel (k0/kernel/, k0/bus/, k0/storage/)
- Pluggable pipelines (k0/pipelines/p*.py)
- Auto-discovery via loader.py (M2)
- Topic-based subscription (O(k) dispatch)

Usage:
    from k0.pipelines import PipelineProtocol, BusMessage, PipelineContext

    class P02EpisodicWrite:
        # Implement protocol...
        pipeline_id = "P02"
        # ... (see protocol.py for complete interface)

See: docs/whiteboard/k0_pipeline_architecture.md for complete design
"""

from k0.bus import BusMessage
from k0.pipelines.protocol import Pipeline, PipelineContext, PipelineProtocol

__all__ = [
    "PipelineProtocol",
    "Pipeline",  # Alias
    "BusMessage",  # Re-exported from k0.bus for convenience
    "PipelineContext",
]
