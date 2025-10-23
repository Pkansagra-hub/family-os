"""
K1 Layer 3 Execution — tools/registry/

PURPOSE:
========
Tool catalog (JSON specs) with <1ms lookup.
758 total tools (608 MCP-compatible + 150 direct API).

RESPONSIBILITIES:
=================
1. Tool Catalog: 608 MCP-compatible tools + 150 direct API tools = 758 total
2. ToolSpec: schema_in, schema_out, latency_hint, cost_hint, band_required, capabilities
3. O(1) Lookup: Hash table by tool_id

PRIMARY ADRs:
=============
- ADR-0033: Tool Execution (registry integration)
- ADR-0007b: Stage 2 Expand (tool registry lookup)

RELATED ADRs:
=============
- ADR-0010: Capability Security (tool capability declarations)

PERFORMANCE METRICS:
====================
- Tool lookup: <1ms P95
- Registry size: 758 tools
- Specification parsing: <50ms at startup

AUTHOR: K1 Intelligence Module
VERSION: 1.0.0
LAST UPDATED: October 2025
"""
