---
adr_id: ORCH-010
title: "MCP Connector Security -- Discovery-Only Boundary with Fabric Isolation"
status: Accepted
date: 2026-02-11
module: orchestrator
layer: "L2"
authors:
  - "K1 Architecture Team"
related_adrs:
  - "ORCH-001"
  - "ORCH-006"
  - "FAB-005"
related_events:
  - "k1.fabric.capability.registered.v1"
  - "k1.fabric.capability.unregistered.v1"
related_contracts:
  - "k1/contracts/schemas/modules/orchestrator/module.contract.yaml"
related_ports:
  - "IFabricGatewayPort"
implements_issue: "1.1.10"
superseded_by: ""
tags:
  - architecture
  - orchestrator
  - mcp
  - security
  - connector
  - edge-first
---

# ORCH-010: MCP Connector Security -- Discovery-Only Boundary with Fabric Isolation

## Context

### Problem Statement

Orchestrator hosts MCP (Model Context Protocol) connector lifecycle management -- discovering MCP servers, registering their tools as capabilities into Fabric, and monitoring their availability. A security model must define:

1. What Orchestrator owns (discovery + registration)
2. What Fabric owns (execution isolation, sandboxing, circuit breakers)
3. How authentication flows through K0 proxy
4. How tools are named to prevent collisions

### Current Situation

Fabric owns ALL execution-time security: CircuitBreaker per provider, output validation, timeout enforcement, and sandbox isolation. Orchestrator's ConnectorLifecycleManager is a thin discovery layer that scans config-driven MCP server definitions and registers tools into Fabric's capability registry.

### Constraints

- Orchestrator is a blind executor -- it does NOT execute MCP tools directly (ORCH-03, ORCH-04)
- K1 never stores authentication tokens (K0 manages all credentials)
- MCP servers can be local (stdio) or remote (SSE/HTTP)
- Tool naming must prevent cross-server collisions in the shared Fabric registry
- All MCP operations must be auditable via trace_id

### Requirements

- Discovery is config-driven (no runtime auto-discovery in V1)
- Registration goes through Fabric's existing register_from_dict API
- K0 proxy handles all auth for remote MCP servers
- Tool names include server_id prefix for collision prevention
- All registrations and K0 proxy calls logged with trace_id

---

## Decision

### Chosen Approach

**Orchestrator owns discovery + registration only. Fabric owns all execution-time isolation. K0 proxy manages credentials.**

### Key Design

**Security Boundary Split:**

```text
ORCHESTRATOR (ConnectorLifecycleManager):
  - Config-driven MCP server discovery
  - Schema extraction from MCP server manifests
  - Tool registration into Fabric via IFabricGatewayPort.register_from_dict()
  - Lifecycle monitoring (subscribe to Fabric health events)
  - Refresh/unregister on config change

FABRIC (MCPProvider + CircuitBreaker + OutputValidator):
  - Per-tool execution isolation
  - CircuitBreaker (CB_MCP: 10s timeout, 3/min threshold)
  - Output validation against registered schema
  - Transport management (stdio/SSE connection pooling)

K0 PROXY (Bridge):
  - Credential storage and injection for remote MCP servers
  - Auth token rotation
  - Network boundary enforcement
  - K1 never sees raw credentials -- K0 injects auth headers
```

**Tool Naming Convention:**

```text
Pattern: mcp.{server_id}.{tool_name}
Example: mcp.github.create_issue
         mcp.calendar.search_events
         mcp.filesystem.read_file

Rules:
  - server_id: lowercase alphanumeric + underscores, max 32 chars
  - tool_name: as declared by MCP server manifest
  - Full capability_name is unique in Fabric registry
  - Prevents collision: two servers with same tool_name get different prefixes
```

**Safety Band Defaults:**

All MCP tools register with GREEN safety band (most conservative) unless explicitly overridden in config:

```yaml
# orchestrator_config.yaml
mcp_servers:
  - server_id: "github"
    type: "remote"
    endpoint: "https://mcp.github.com"
    critical: true
    safety_band_override: "AMBER"  # optional, defaults to GREEN
    tools:
      - name: "create_issue"
        # inherits GREEN safety band from default
      - name: "delete_repo"
        safety_band_override: "RED"  # explicit per-tool override
```

GREEN default means MCP tools are always available regardless of current session safety band level. AMBER/RED tools require elevated safety band to execute.

**Audit Protocol:**

Every MCP operation is logged with structured fields:

```json
{
  "event": "mcp.registration",
  "server_id": "github",
  "tool_count": 5,
  "tools_registered": ["mcp.github.create_issue", "..."],
  "safety_band": "GREEN",
  "trace_id": "abc-123",
  "timestamp": 1707600000.0
}
```

K0 proxy calls include additional audit:

```json
{
  "event": "mcp.k0_proxy_call",
  "server_id": "github",
  "operation": "auth_refresh",
  "k0_available": true,
  "trace_id": "abc-123"
}
```

**What Was Removed from Orchestrator Scope:**

| Concern | Owner | Rationale |
|---------|-------|-----------|
| Per-connector process isolation | Fabric MCPProvider | Fabric manages transport (stdio subprocess, SSE connection) |
| Resource limits (CPU, memory) | Fabric CircuitBreaker + OS | CB timeouts bound execution; OS-level cgroup limits are deployment concern |
| Network allowlist | K0 Proxy (V2) | Advisory only in V1; K0 proxy enforces network boundary |
| Output sanitization | Fabric OutputValidator | Fabric validates all CapabilityResult outputs |
| Connection pooling | Fabric MCPProvider | Transport-level concern, not discovery-level |

### Rationale

- Thin discovery layer minimizes Orchestrator's attack surface
- Fabric's existing security infrastructure (CB, output validation, sandboxing) is reused, not duplicated
- K0 credential management follows the established K1-never-stores-secrets principle
- server_id prefix is simple, deterministic, and prevents all naming collisions
- GREEN default is maximally conservative -- tools are available in all safety contexts

---

## Alternatives Considered

### Alternative 1: Orchestrator Owns Full MCP Execution Pipeline

**Rejected because:** Duplicates Fabric's MCPProvider, CircuitBreaker, and OutputValidator. Violates ORCH-04 (every step through Fabric). Creates parallel security infrastructure that must be maintained separately.

### Alternative 2: Runtime Auto-Discovery of MCP Servers

**Rejected because:** Auto-discovery (mDNS, network scanning) introduces security risks (rogue servers) and non-determinism. Config-driven discovery is explicit, auditable, and testable. V2 may add supervised auto-discovery with user confirmation.

### Alternative 3: K1 Manages MCP Credentials Locally

**Rejected because:** Violates the K0/K1 security boundary. K0 is the credential authority. K1 managing secrets on edge devices increases attack surface (local file access, memory dumps). K0 proxy injection ensures secrets never touch K1 memory.

---

## Consequences

### Positive

- Minimal Orchestrator attack surface (discovery only, no execution)
- Zero credential exposure in K1 process
- Reuses Fabric's battle-tested security infrastructure
- Deterministic tool naming prevents registry collisions

### Negative

- Config-driven only -- no automatic MCP server discovery (V1)
- K0 offline means no auth refresh for remote MCP servers (local servers unaffected)
- Green default may be too conservative for some tools (requires explicit config override)

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| MCP server config out of date | Medium | Low | Config reload on K1 restart; V2: file watcher |
| K0 proxy unavailable for remote MCP | Low | Medium | Edge-First: local MCP servers always work; remote degrade gracefully |
| Rogue MCP server in config | Very Low | High | Config is admin-controlled; Fabric output validation catches malformed results |

---

## Implementation

### Affected Code Paths

| Component | File | Change Type |
|-----------|------|-------------|
| MCPDiscovery | `k1/orchestrator/connectors/mcp_discovery.py` | New |
| MCPRegistrationBridge | `k1/orchestrator/connectors/mcp_registrar.py` | New |
| K0ConnectorProxyClient | `k1/orchestrator/connectors/k0_proxy_client.py` | New |
| ConnectorLifecycleManager | `k1/orchestrator/connectors/lifecycle_manager.py` | New |
| MCPServerRegistration type | `k1/orchestrator/types.py` | New |

### Success Metrics

- All MCP tools registered with server_id prefix (zero collisions)
- Zero credentials in K1 process memory (verified by test)
- All registrations carry trace_id in audit log

### Testing Strategy

- [ ] Unit tests: tool naming convention (server_id prefix)
- [ ] Unit tests: safety band default (GREEN) and overrides
- [ ] Integration tests: config-driven discovery -> Fabric registration
- [ ] Contract tests: K0 proxy call protocol (auth injection)

---

## Amendment History

| Date | Author | Change |
|------|--------|--------|
| 2026-02-11 | K1 Architecture Team | Initial decision -- discovery-only boundary with Fabric isolation |
