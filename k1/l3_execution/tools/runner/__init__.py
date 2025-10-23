"""
K1 Layer 3 Execution — tools/runner/

PURPOSE:
========
Tool execution engine (MCP/WASM/Process) with <3000ms P95.
Executes tools via selected protocol+sandbox with timeout enforcement.

RESPONSIBILITIES:
=================
1. Tool Execution: Execute tool via selected protocol+sandbox
2. Timeout Enforcement: Per-tool timeout (5s-300s), SIGTERM→5s→SIGKILL
3. Result Collection: Capture stdout/stderr, parse JSON response

PRIMARY ADRs:
=============
- ADR-0033: Tool Execution (2D selection: protocol × sandbox)
- ADR-0034: MCP Protocol (JSON-RPC 2.0, 608 tools)

RELATED ADRs:
=============
- ADR-0024: Performance Budgets (tools <3000ms)
- ADR-0029: Prometheus Metrics (tool execution latency, success rate)
- ADR-0032: Egress Control (sandbox integration)

PERFORMANCE METRICS:
====================
- Tool execution: <3000ms P95
- Timeout compliance: 95% (12K enforcements)
- Execution success rate: >90%

AUTHOR: K1 Intelligence Module
VERSION: 1.0.0
LAST UPDATED: October 2025
"""
