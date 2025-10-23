"""
K1 Layer 3 Execution — tools/adapters/

PURPOSE:
========
Protocol adapters (MCP, REST, CLI) with <5ms overhead.
Provides unified interface across different tool protocols.

RESPONSIBILITIES:
=================
1. MCP Adapter: JSON-RPC 2.0 client, stdio/HTTP transport (80% of tools)
2. REST Adapter: HTTP client, JSON payloads (15% of tools)
3. CLI Adapter: Subprocess invocation, stdin/stdout (5% of tools)

PRIMARY ADRs:
=============
- ADR-0033: Tool Execution (protocol selection)
- ADR-0034: MCP Protocol (JSON-RPC adapter)

PERFORMANCE METRICS:
====================
- Adapter overhead: <5ms P95
- Protocol support: 3 protocols (MCP, REST, CLI)

AUTHOR: K1 Intelligence Module
VERSION: 1.0.0
LAST UPDATED: October 2025
"""
