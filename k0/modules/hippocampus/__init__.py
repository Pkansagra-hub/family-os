"""
Hippocampus Module - Memory Formation and Pattern Separation

Provides DG (pattern separation), CA1 (semantic projection), CA3 (clustering).
Version: 0.1.0

ADRs: K003, K003.1, K003.2, K003.3
"""

from .ca1_bridge import CA1Bridge
from .ca3_service import CA3Service
from .dg_service import DGService
from .types import CA1Projection, CA3Cluster, DGFingerprint, HippocampusConfig

__version__ = "0.1.0"
__all__ = [
    "DGService",
    "CA1Bridge",
    "CA3Service",
    "DGFingerprint",
    "CA1Projection",
    "CA3Cluster",
    "HippocampusConfig",
]
