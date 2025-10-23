"""
Expand Stage - Tool Registry Integration (Stage 2 of 4)

**ADR Reference:** ADR-0007b (Expand Stage Tool/Prompt Registry Integration)

**Purpose:**
Enrich plan sketch with tool metadata from tool registry.

**Key Responsibilities:**
1. O(1) hash table lookup for each tool in plan steps
2. Match tool prompts via keyword/category matching (>90% success)
3. Enrich steps with schema_in, schema_out, latency_hint, cost_hint, band_required
4. Return ExpandedPlan with complete metadata

**Performance Target:** <1ms P95

**Input:** PlanSketch (from Stage 1)
**Output:** ExpandedPlan (enriched with tool metadata)

**Tool Registry Integration:**
- Tool lookup: O(1) hash table by tool_id
- Prompt matching: Keyword/category search (>90% match rate)
- Schema enrichment: FlatBuffers schema references

**Error Handling:**
- Tool not found → Return error with available alternatives
- Prompt mismatch → Use fallback generic prompt
- Schema missing → Use default empty schema
"""

from .plan_enricher import PlanEnricher
from .prompt_matcher import PromptMatcher
from .tool_lookup import ToolLookup

__all__ = ["ToolLookup", "PromptMatcher", "PlanEnricher"]
