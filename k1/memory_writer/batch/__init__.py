"""
k1.memory_writer.batch -- Stage 5: Delta aggregation + batch emission.

Re-exports:
  - DeltaAggregator: 250ms window batching with dedup
  - BatchEmitter: flush to IBridgeCommandPort.submit_batch()
"""

from k1.memory_writer.batch.batch_emitter import BatchEmitter
from k1.memory_writer.batch.delta_aggregator import DeltaAggregator

__all__ = [
    "BatchEmitter",
    "DeltaAggregator",
]
