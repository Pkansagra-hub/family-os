"""
K0 Embedding Modules

M22-M27: Embedding lifecycle management modules.
Primary generation via M22 (P02 inline), management via M24-M27 (P08).

ADR Reference: ADR-K003 (Inline Embedding via UltraBERT)
"""

from .extract_from_cache import run as extract_from_cache_run

__all__ = [
    "extract_from_cache_run",
]
