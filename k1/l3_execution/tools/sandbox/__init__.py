"""
K1 Layer 3 Execution — tools/sandbox/

PURPOSE:
========
Isolation layers (MCP/WASM/Process/Container) with <100ms sandbox setup.
Implements 4-layer defense for process sandbox with band enforcement.

RESPONSIBILITIES:
=================
1. WASM Sandbox: Wasmtime runtime, zero native syscalls, WASI capabilities, <10ms instantiation
2. Process Sandbox: OS process isolation, 4-layer defense (network, filesystem, resource, audit)
3. Container Sandbox: Firecracker MicroVM (125ms boot), gVisor (user-space kernel)

PRIMARY ADRs:
=============
- ADR-0033: Tool Execution (sandbox selection)
- ADR-0033b: WASM Sandbox (Wasmtime runtime)
- ADR-0033c: Process Sandbox (4-layer defense)
- ADR-0032: Egress Control (network, filesystem, resource)

RELATED ADRs:
=============
- ADR-0024: Performance Budgets (sandbox <100ms)

PERFORMANCE METRICS:
====================
- WASM instantiation: <10ms
- Process spawn: <100ms
- Firecracker boot: 125ms
- Sandbox overhead: 10× slower (WASM), 1× (Process)

AUTHOR: K1 Intelligence Module
VERSION: 1.0.0
LAST UPDATED: October 2025
"""
