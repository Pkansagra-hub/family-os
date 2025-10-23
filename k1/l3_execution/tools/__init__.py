"""
K1 Layer 3 Execution — tools/

PURPOSE:
========
Tool execution engine with MCP/WASM/Process sandboxing (<3000ms P95).
Implements 2D selection algorithm (protocol × sandbox) for 758 tools.

ARCHITECTURE:
=============
5 sub-modules implementing tool execution:

1. runner/    - Tool execution engine (MCP/WASM/Process, <3000ms P95)
2. sandbox/   - Isolation layers (MCP/WASM/Process/Container, <100ms setup)
3. registry/  - Tool catalog (JSON specs, 758 tools, <1ms lookup)
4. adapters/  - Protocol adapters (MCP, REST, CLI, <5ms overhead)
5. control/   - Runtime tool management (<10ms control operation)

PRIMARY ADRs:
=============
- ADR-0033: Tool Execution (2D selection: protocol × sandbox)
- ADR-0033a: MCP Protocol (JSON-RPC 2.0, stdio/HTTP transport)
- ADR-0033b: WASM Sandbox (Wasmtime runtime, <10ms instantiation)
- ADR-0033c: Process Sandbox (4-layer defense, band enforcement)
- ADR-0033d: Selection Logic (2D algorithm, fallback cascade)
- ADR-0034: MCP Protocol (JSON-RPC 2.0, 608 MCP-compatible tools)
- ADR-0078: Tool Call Batching (50ms window, dependency graph, parallel execution)

RELATED ADRs:
=============
- ADR-0007b: Stage 2 Expand (tool registry lookup)
- ADR-0009: Circuit Breaker (tool resilience)
- ADR-0010: Capability Security (tool capability declarations)
- ADR-0024: Performance Budgets (tools <3000ms P95)
- ADR-0029: Prometheus Metrics (tool execution latency, success rate)
- ADR-0032: Egress Control (sandbox integration)

PERFORMANCE BUDGETS:
====================
- Tool execution: <3000ms P95
- Tool sandbox setup: <100ms
- Tool lookup: <1ms P95
- Protocol adapter overhead: <5ms
- Control operation: <10ms

AUTHOR: K1 Intelligence Module
VERSION: 1.0.0
LAST UPDATED: October 2025
"""
