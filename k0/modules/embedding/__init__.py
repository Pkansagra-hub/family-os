"""
K0 Embedding Modules

M22-M27: Embedding lifecycle management modules.
Primary generation via M22 (P02 inline), management via M24-M27 (P08).

ADR Reference: ADR-K003 (Inline Embedding via UltraBERT)
"""

from .backfill import run as backfill_run
from .cleanup import run as cleanup_run
from .extract_from_cache import run as extract_from_cache_run
from .faiss_indexer import run as faiss_indexer_run
from .recompute import run as recompute_run

__all__ = [
    "extract_from_cache_run",
    "faiss_indexer_run",
    "backfill_run",
    "recompute_run",
    "cleanup_run",
]
