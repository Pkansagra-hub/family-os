"""
k1.memory_writer.pipeline -- Phase 4: Pipeline orchestration.

Re-exports:
  - MemoryWriterPipeline: 5-stage linear pipeline
  - PipelineResult: Outcome dataclass for a single turn
  - TurnDispatcher: Routes turn.complete.v1 events to pipeline
"""

from k1.memory_writer.pipeline.pipeline import MemoryWriterPipeline, PipelineResult
from k1.memory_writer.pipeline.turn_dispatcher import TurnDispatcher

__all__ = [
    "MemoryWriterPipeline",
    "PipelineResult",
    "TurnDispatcher",
]
