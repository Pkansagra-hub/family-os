"""Async workers for V1.4 (Performance Optimization).

Background workers for:
  - Embedding computation (moved from sync commit path)
  - FTS indexing (moved from sync commit path)

Reduces commit latency from ~150ms to ~80-100ms.

Note: Worker modules (embedding_worker, fts_worker) are designed to run as
standalone scripts via `python -m k0.workers.embedding_worker`. They are NOT
imported here to avoid RuntimeWarning about module execution.

The coordinator is also not imported here to prevent circular import of workers.
Import coordinator directly where needed:
    from k0.workers.coordinator import AsyncWorkerCoordinator
"""

# NOTE: Nothing is imported at package level to avoid sys.modules pollution
# when running workers as -m scripts. Import what you need directly:
#
#   from k0.workers.coordinator import AsyncWorkerCoordinator
#   from k0.workers.embedding_worker import EmbeddingWorker
#   from k0.workers.fts_worker import FtsIndexingWorker
