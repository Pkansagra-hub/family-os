"""Post-reconciliation hooks -- M9.6 (Universal Reconciliation Engine).

Content-generation hooks that run AFTER R7 commits StagedWrites,
BEFORE R8 bus events are published.
"""

HOOK_REGENERATE_SUMMARY = "regenerate_summary"
HOOK_RECOMPUTE_CENTROID = "recompute_centroid"

ALL_HOOKS = frozenset({HOOK_REGENERATE_SUMMARY, HOOK_RECOMPUTE_CENTROID})
