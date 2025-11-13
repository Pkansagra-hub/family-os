"""
Affect Storage

Persist affect annotations in st_hipp_store and EMA states in memory cache.

Reference: ADR-0012a (Affect Contracts & Storage Mapping)
"""

from .storage import AffectStorage

__all__ = ["AffectStorage"]
