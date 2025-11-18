"""
Hippocampus Module - Episodic Memory Formation (Phase 2)

Phase 2 Declarative Modules:
- pattern_separate: M01 - DG pattern separation (SimHash + MinHash) ✅ Implemented
- semantic_project: M02 - CA1 semantic projection (spaCy NER + KG triples) ✅ Implemented
- ca3_consolidation: M03 - CA3 clustering (P03 scope)

Version: 1.1.0
ADRs: K003, K003.1, K003.2, K003.3

Migration Status (2025-11-17):
- Removed Phase 1 class-based stubs (DGService, CA1Bridge, CA3Service)
- Implemented Phase 2 pure function modules
- M01 tests: 16/16 passing ✅
- M02 tests: Pending
"""

from . import pattern_separate, semantic_project

__version__ = "1.1.0"
__all__ = [
    "pattern_separate",  # Phase 2 module (M01) - IMPLEMENTED
    "semantic_project",  # Phase 2 module (M02) - IMPLEMENTED
]
