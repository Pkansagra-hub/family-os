
# ADR Reorganization Plan - AI-Searchable & Layer-Aware

**Status:** PROPOSED
**Date:** 2025-11-03
**Purpose:** Reorganize 200+ ADR files for AI agent searchability and architectural propagation tracking

---

## 🎯 Goals

1. **AI-Searchable Structure**: Add semantic metadata (YAML frontmatter) for AI agents to query ADRs by layer, module, concern, status
2. **Intuitive Organization**: Group ADRs by architectural layer/concern, not just numbering
3. **Propagation Tracking**: When modifying a module/layer, automatically identify affected ADRs
4. **Maintainability**: Clear folder structure, automated link validation, drift detection

---

## 📋 Current Problems

### Problem 1: Flat Directory Chaos

```
docs/architecture/decisions/
├── 0001-k0-k1-kernel-split.md
├── 0001a-k0-bridge-communication-protocol.md
├── 0001b-model-hub-architecture-llm-integration.md
├── 0001c-k0-k1-pipeline-boundary-enforcement.md
├── 0001d-state-boundary-management-k1-k0.md
├── 0001e-p21-integration-pipeline-layer.md
├── 0002-actor-model-agent-isolation.md
├── 0002a-mailbox-mpsc-queue-implementation.md
... (200+ files)
```

**Issues:**

- ❌ Cannot browse by architectural concern (Layer 3 execution? Security? Performance?)
- ❌ Sub-ADRs scattered (0005a far from 0005, breaks semantic grouping)
- ❌ Meta files (readme.md, adr_master_reference.md, DRIFT_DETECTED_IN_ADRS.md) mixed with ADRs
- ❌ AI agents must parse filenames to understand content

### Problem 2: No Semantic Metadata

```markdown
# ADR-0004: 56-Module 5-Layer Architecture
**Status:** Accepted
**Date:** 2025-10-10
```

**Issues:**

- ❌ No layer tags (which layers does this ADR affect?)
- ❌ No module tags (which of 56 modules?)
- ❌ No concern tags (performance? security? observability?)
- ❌ No propagation map (changing Layer 3 → which ADRs to review?)
- ❌ AI agents cannot filter by "all ADRs affecting Layer 3 execution"

### Problem 3: Stale Index

`readme.md` says:

- "52 modules" (actually 56 per ADR-0004 Amendment #2)
- "0 completed, 47 in progress" (actually 4 completed: ADR-0050 family)
- All ADRs marked "Not Started" (many are ACCEPTED)

### Problem 4: No Propagation Tracking

**Scenario:** Developer adds new module to Layer 3 (e.g., `k1/l3_execution/agents/negotiator`)

**Questions:**

1. Which ADRs must be updated? (ADR-0004 module count? ADR-0002 actor patterns? ADR-0005 lifecycle?)
2. Which contracts need new schemas? (FlatBuffers? REST API?)
3. Which tests must be added? (Integration? Performance?)
4. Which diagrams need updates? (k1_architecture_diagram.mmd?)

**Current Answer:** Manual search, grep, hope you don't miss anything ❌

---

## ✅ Proposed Solution: 3-Tier Reorganization

### Tier 1: Layered Folder Structure (Matches K1 Architecture)

```
docs/architecture/decisions/
├── 00-meta/                          # Meta-documentation (templates, guides, indices)
│   ├── 0000-template.md              # ADR template
│   ├── readme.md                     # Master index (AI-queryable)
│   ├── adr_master_reference.md       # Cross-reference table
│   ├── ADR_REFERENCE_CROSS_CUTTING.md
│   ├── DRIFT_DETECTED_IN_ADRS.md
│   └── propagation_maps/             # NEW: Propagation tracking
│       ├── layer1_input.yml
│       ├── layer2_orchestration.yml
│       ├── layer3_execution.yml
│       ├── layer4_runtime.yml
│       └── layer5_infrastructure.yml
│
├── 01-foundation/                    # Core architectural decisions (K0/K1 split, Actor Model, MPST)
│   ├── 0001-k0-k1-kernel-split/
│   │   ├── 0001.md                   # Parent ADR
│   │   ├── 0001a-k0-bridge-communication-protocol.md
│   │   ├── 0001b-model-hub-architecture-llm-integration.md
│   │   ├── 0001c-k0-k1-pipeline-boundary-enforcement.md
│   │   ├── 0001d-state-boundary-management-k1-k0.md
│   │   └── 0001e-p21-integration-pipeline-layer.md
│   ├── 0002-actor-model-agent-isolation/
│   │   ├── 0002.md
│   │   ├── 0002a-mailbox-mpsc-queue-implementation.md
│   │   ├── 0002b-supervisor-monitoring-crash-recovery.md
│   │   ├── 0002c-actor-router-admission-control.md
│   │   └── 0002d-observability-schema-actor-messaging.md
│   ├── 0003-mpst-protocol-validation/
│   │   ├── 0003.md
│   │   ├── 0003a-protocol-definition-language-pdl-specification.md
│   │   ├── 0003b-6-core-protocol-implementations.md
│   │   ├── 0003c-protocol-monitor-runtime-implementation.md
│   │   └── 0003d-role-attestation-capability-verification.md
│   ├── 0004-56-module-5-layer-architecture/
│   │   ├── 0004.md
│   │   ├── 0004a-layer1-2-event-bus-communication.md
│   │   ├── 0004b-module-dependency-management.md
│   │   ├── 0004c-module-readme-template.md
│   │   ├── 0004d-per-layer-integration-testing.md
│   │   └── 0004f-stream-switch-multi-modal-bus.md
│   └── index.yml                     # NEW: AI-queryable index
│
├── 02-layer1-input/                  # Layer 1: Input Processing (4 modules)
│   ├── 0004f-stream-switch-multi-modal-bus/
│   │   └── 0004f.md
│   ├── 0031a-streaming-asr-integration/
│   │   └── 0031a.md
│   ├── 0056-voice-pipeline-implementation/
│   │   ├── 0056.md
│   │   ├── 0056a-asr-ingress.md
│   │   ├── 0056b-intent-bridge.md
│   │   ├── 0056c-tool-interleaving.md
│   │   ├── 0056d-tts-synthesis.md
│   │   ├── 0056e-audio-out.md
│   │   └── 0056f-voice-persona-persistence-cross-session.md
│   ├── 0057-voice-specific-backpressure/
│   ├── 0058-intent-classification-voice/
│   └── index.yml
│
├── 03-layer2-orchestration/          # Layer 2: Orchestration (3 modules)
│   ├── 0005-agent-lifecycle-fsm/
│   │   ├── 0005.md
│   │   ├── 0005a-agent-warming-state.md
│   │   ├── 0005b-agent-idle-pooling.md
│   │   ├── 0005c-agent-draining-shutdown.md
│   │   ├── 0005d-supervisor-blacklist.md
│   │   └── 0005e-agent-personality-capabilities.md
│   ├── 0006-3-phase-orchestration/
│   │   ├── 0006.md
│   │   ├── 0006a-contract-net-negotiation.md
│   │   ├── 0006b-multi-criteria-scoring.md
│   │   ├── 0006c-parallel-dag-execution.md
│   │   ├── 0006d-saga-pattern-integration.md
│   │   ├── 0006e-multi-agent-coordination.md
│   │   └── 0006f-3phase-orchestration-contract-net.md
│   ├── 0007-4stage-planning-pipeline/
│   └── index.yml
│
├── 04-layer3-execution/              # Layer 3: Execution (22 modules - Agent Fabric, Model Hub, Tools, Dialogue)
│   ├── 0073-agent-lifecycle-fsm-enhancements/
│   ├── 0086-dynamic-agent-creation-subsystem/
│   │   ├── 0086.md
│   │   ├── 0086a-agent-factory-pattern.md
│   │   ├── 0086b-agent-template-system.md
│   │   ├── 0086c-resource-reservation-system.md
│   │   ├── 0086d-agent-composition-pattern.md
│   │   ├── 0086e-prompt-directory-template-management.md
│   │   ├── 0086f-dynamic-agent-lifecycle-integration.md
│   │   ├── 0086g-agent-registry-extension.md
│   │   └── 0086h-agent-metrics-observability.md
│   ├── 0033-three-tier-tool-sandboxing-strategy/
│   ├── 0034-mcp-protocol-adoption/
│   └── index.yml
│
├── 05-layer4-runtime/                # Layer 4: Runtime Core (8 modules - Leases, SessionState, Flow Engine, Learning)
│   ├── 0017-sessionstate-6-section-design/
│   │   ├── 0017.md
│   │   ├── 0017a-beliefs-section-user-facts-preferences.md
│   │   ├── 0017b-scoreboard-section-common-ground-qud.md
│   │   ├── 0017c-control-section-agent-leases-flow.md
│   │   ├── 0017d-persona-section-personality-style.md
│   │   ├── 0017e-multimodal-section-audio-vision.md
│   │   └── 0017f-meta-section-telemetry-metrics.md
│   ├── 0018-3-tier-eviction-strategy/
│   ├── 0059-learning-loop/
│   │   ├── 0059.md
│   │   ├── 0059a-feedback-signal-taxonomy.md
│   │   ├── 0059b-drift-detection.md
│   │   ├── 0059c-planner-parameter-contracts.md
│   │   ├── 0059d-audit-rollback.md
│   │   └── 0059e-synthetic-data-pipeline.md
│   └── index.yml
│
├── 06-layer5-infrastructure/         # Layer 5: Infrastructure (19 modules - Scheduler, Backpressure, Thermal, Observability)
│   ├── 0024-performance-budgets/
│   ├── 0028-weighted-fair-queuing-scheduler/
│   ├── 0029-prometheus-metrics-red-method/
│   ├── 0030-intelligent-trace-sampling/
│   ├── 0091-k0-observability-architecture/
│   └── index.yml
│
├── 07-contracts-serialization/       # Cross-layer: Contracts, FlatBuffers, API specs
│   ├── 0011-flatbuffers-serialization/
│   ├── 0012-76-flatbuffers-schemas/
│   ├── 0013-pipeline-versioning-policy/
│   ├── 0014-json-rest-api-dual-format/
│   ├── 0047-openapi-3-1-rest-specs/
│   └── index.yml
│
├── 08-security-privacy/              # Cross-layer: Security, Privacy, Capabilities
│   ├── 0010-capability-based-security/
│   ├── 0032-band-based-egress-rules/
│   ├── 0035-pii-detection-and-redaction/
│   ├── 0036-e2ee-for-red-band/
│   ├── 0037-jwt-authentication/
│   ├── 0089-k0-bridge-policy-enforcement/
│   └── index.yml
│
├── 09-communication/                 # Cross-layer: K0↔K1 Bridge, WebSocket, SSE, REST
│   ├── 0015-websocket-binary-protocol/
│   ├── 0040-websocket-realtime-chat/
│   ├── 0042-k0-sse-event-streaming/
│   ├── 0044-k0-bridge-http2-flatbuffers/
│   ├── 0048-k1-internal-event-bus/
│   └── index.yml
│
├── 10-multi-device-sync/             # Cross-cutting: Multi-device family sync (NEW in 2025-11-03)
│   ├── 0050-multi-device-family-sync-strategy/
│   │   ├── 0050.md
│   │   ├── 0050a-sessionstate-coherence-guarantees.md
│   │   ├── 0050b-crdt-device-to-device-merge.md
│   │   ├── 0050c-lan-first-sync-implementation.md
│   │   └── 0050d-p2p-e2ee-internet-sync.md
│   └── index.yml
│
├── 11-ux-product/                    # Cross-cutting: UX, Product Craft, Conversational Delight
│   ├── 0065-product-craft-ux-micro-interactions/
│   ├── 0067-conversational-delight-factors/
│   ├── 0068-voice-quality-measurement/
│   └── index.yml
│
├── 12-knowledge-memory/              # Cross-cutting: Knowledge Graph, Memory, Episodic Consolidation
│   ├── 0081-k0-knowledge-graph-architecture/
│   ├── 0084-k0-memory-consolidation-pipeline/
│   └── index.yml
│
├── 13-advanced/                      # Advanced capabilities (Ambient, Embodied, Multi-Party)
│   ├── 0082-multi-party-dialogue-coordination/
│   ├── 0083-ambient-sensor-fusion/
│   ├── 0085-embodied-awareness-device-presence/
│   └── index.yml
│
└── 14-deployment-ops/                # Deployment, Operations, Configuration
    ├── 0080-continuous-config-hot-reload/
    ├── 0088-k0-local-env-paths-migration/
    ├── 0090-deployment-strategy-edge-rollout/
    └── index.yml
```

**Benefits:**

- ✅ Browse by architectural concern (Layer 3? Check `04-layer3-execution/`)
- ✅ Sub-ADRs grouped with parents (0001/ folder contains 0001.md + 0001a-e.md)
- ✅ AI agents query `index.yml` per folder (semantic search by layer/module/concern)
- ✅ Clear separation: foundation vs layers vs cross-cutting concerns

---

### Tier 2: AI-Searchable YAML Frontmatter (Semantic Metadata)

**Add to every ADR file:**

```yaml
---
adr_number: 0004
title: "56-Module 5-Layer Microkernel Architecture"
status: ACCEPTED
date_created: 2025-10-10
date_updated: 2025-10-22
authors: ["K1 Architecture Team"]

# Layer/Module Mapping (KEY FOR PROPAGATION)
affected_layers:
  - layer1_input        # Does this ADR affect Layer 1?
  - layer2_orchestration
  - layer3_execution
  - layer4_runtime
  - layer5_infrastructure

affected_modules:
  - "k1/l1_input/streams/stream_switch"
  - "k1/l1_input/streams/operators"
  - "k1/l2_orchestration/planner"
  - "k1/l2_orchestration/orchestrator"
  - "k1/l3_execution/agents/registry"
  # ... (all 56 modules)

# Concern Tags (for AI filtering)
concerns:
  - architecture        # High-level structure
  - modularity          # Module boundaries
  - performance         # Performance impact
  - maintainability     # Code maintainability
  - testing             # Test strategy

# Cross-References
supersedes: []
superseded_by: []
related_adrs:
  - ADR-0001  # K0/K1 Kernel Split
  - ADR-0002  # Actor Model
  - ADR-0003  # MPST Protocol

# Implementation
implementation_status: COMPLETED
implementation_date: 2025-10-15
implementation_phase: "Phase 1 (Foundation)"

# Contracts & Diagrams
related_contracts:
  - "k1/contracts/flatbuffers/layer1_input/*.fbs"
  - "k1/contracts/flatbuffers/layer2_orchestration/*.fbs"
related_diagrams:
  - "architecture_diagrams/k1/k1_complete_with_flows.mmd"
  - "docs/architecture/diagrams/k1/README.md"

# Propagation Map (WHO MUST UPDATE THIS ADR?)
propagation:
  triggers:
    - "Adding new module to any layer"
    - "Changing layer dependency rules"
    - "Updating module count"
  affected_adrs:
    - ADR-0001  # K0/K1 split (if cross-layer changes)
    - ADR-0002  # Actor Model (if new actors)
  affected_contracts:
    - "k1/contracts/api/module_registry.yaml"
  affected_tests:
    - "tests/k1/architecture/test_layer_dependencies.py"
    - "tests/k1/architecture/test_import_linter.py"
---

# ADR-0004: 56-Module 5-Layer Microkernel Architecture

**Status:** Accepted
**Date:** 2025-10-10 (Updated: 2025-10-22)
...
```

**AI Query Examples:**

```python
# Query 1: Find all ADRs affecting Layer 3 execution
SELECT * FROM adrs WHERE 'layer3_execution' IN affected_layers;

# Query 2: Find all ACCEPTED ADRs with performance concerns
SELECT * FROM adrs WHERE status = 'ACCEPTED' AND 'performance' IN concerns;

# Query 3: Find all ADRs affecting module 'k1/l3_execution/agents/registry'
SELECT * FROM adrs WHERE 'k1/l3_execution/agents/registry' IN affected_modules;

# Query 4: Find all ADRs that must be updated when adding new module
SELECT * FROM adrs WHERE 'Adding new module to any layer' IN propagation.triggers;
```

**Implementation:**

- Script to extract YAML frontmatter → SQLite database
- GitHub Copilot can query this database
- Pre-commit hook validates frontmatter (required fields present)

---

### Tier 3: Propagation Maps (Auto-Generate Checklists)

**File:** `docs/architecture/decisions/00-meta/propagation_maps/layer3_execution.yml`

```yaml
# Layer 3 Execution - Propagation Map
# When modifying Layer 3, this checklist ensures all dependencies are updated

layer: layer3_execution
modules:
  - k1/l3_execution/agents/registry
  - k1/l3_execution/agents/hire_fire
  - k1/l3_execution/agents/supervisor
  - k1/l3_execution/agents/personality
  - k1/l3_execution/agents/mailbox
  - k1/l3_execution/agents/active_roster
  - k1/l3_execution/model_hub/router
  - k1/l3_execution/model_hub/placement_planner
  - k1/l3_execution/model_hub/adapters
  - k1/l3_execution/model_hub/kv_cache_broker
  - k1/l3_execution/model_hub/prompt_library
  - k1/l3_execution/model_hub/fallback_cascade
  - k1/l3_execution/model_hub/safety_filter
  - k1/l3_execution/tools/runner
  - k1/l3_execution/tools/sandbox
  - k1/l3_execution/tools/registry
  - k1/l3_execution/tools/adapters
  - k1/l3_execution/tools/control
  - k1/l3_execution/dialogue/scoreboard
  - k1/l3_execution/dialogue/state_tracker
  - k1/l3_execution/dialogue/turn_manager
  - k1/l3_execution/dialogue/repair

# Propagation Rules
scenarios:
  - scenario: "Add new agent to Layer 3"
    description: "When adding new agent (e.g., k1/l3_execution/agents/negotiator)"
    checklist:
      adrs_to_update:
        - ADR-0004: "Update module count (56 → 57)"
        - ADR-0002: "Document actor patterns if new pattern"
        - ADR-0005: "Update agent lifecycle FSM if new state"
        - ADR-0086: "Update dynamic agent registry if runtime creation"
      contracts_to_update:
        - "k1/contracts/flatbuffers/layer3_execution/agent_registry.fbs"
        - "k1/contracts/api/agent_management.yaml"
      tests_to_add:
        - "tests/k1/l3_execution/agents/test_negotiator.py"
        - "tests/k1/architecture/test_module_count.py (update assertion)"
      diagrams_to_update:
        - "architecture_diagrams/k1/k1_complete_with_flows.mmd"
        - "docs/architecture/diagrams/k1/agent_lifecycle.mmd"
      code_locations:
        - "k1/l3_execution/agents/registry/agents.yml (add negotiator.yml)"
        - "k1/l3_execution/agents/__init__.py (export NegotiatorAgent)"

  - scenario: "Add new Model Hub adapter (e.g., Gemini)"
    description: "When adding new LLM provider adapter"
    checklist:
      adrs_to_update:
        - ADR-0001b: "Update Model Hub architecture"
        - ADR-0004: "No change (adapter is sub-component, not new module)"
      contracts_to_update:
        - "k1/contracts/flatbuffers/layer3_execution/model_request.fbs"
        - "k1/contracts/api/model_hub.yaml"
      tests_to_add:
        - "tests/k1/l3_execution/model_hub/adapters/test_gemini_adapter.py"
      code_locations:
        - "k1/l3_execution/model_hub/adapters/gemini.py"
        - "k1/l3_execution/model_hub/router.py (register adapter)"

  - scenario: "Add new tool sandbox type (e.g., Docker)"
    description: "When adding new tool isolation mechanism"
    checklist:
      adrs_to_update:
        - ADR-0033: "Update 3-tier sandbox strategy (add Docker tier)"
        - ADR-0034: "Document MCP integration if applicable"
      contracts_to_update:
        - "k1/contracts/flatbuffers/layer3_execution/tool_execution.fbs"
      tests_to_add:
        - "tests/k1/l3_execution/tools/sandbox/test_docker_sandbox.py"
      code_locations:
        - "k1/l3_execution/tools/sandbox/docker.py"
        - "k1/l3_execution/tools/sandbox/__init__.py (export DockerSandbox)"

# Upstream Dependencies (Layer 3 depends on these)
depends_on_layers:
  - layer4_runtime     # SessionState, Leases, Flow Engine
  - layer5_infrastructure  # Scheduler, Backpressure, Observability

# Downstream Dependencies (These depend on Layer 3)
depended_on_by_layers:
  - layer2_orchestration  # Orchestrator hires agents from Layer 3

# Cross-Cutting Concerns
cross_cutting:
  - "All Layer 3 changes must update contracts in 07-contracts-serialization/"
  - "All Layer 3 agents must follow Actor Model (ADR-0002)"
  - "All Layer 3 performance changes must update budgets (ADR-0024)"
```

**Usage:**

```bash
# Developer adds new agent
$ python scripts/check_propagation.py --scenario "Add new agent to Layer 3"

✅ Checklist for: Add new agent to Layer 3
─────────────────────────────────────────────
ADRs to Update:
  [ ] ADR-0004: Update module count (56 → 57)
  [ ] ADR-0002: Document actor patterns if new pattern
  [ ] ADR-0005: Update agent lifecycle FSM if new state
  [ ] ADR-0086: Update dynamic agent registry if runtime creation

Contracts to Update:
  [ ] k1/contracts/flatbuffers/layer3_execution/agent_registry.fbs
  [ ] k1/contracts/api/agent_management.yaml

Tests to Add:
  [ ] tests/k1/l3_execution/agents/test_negotiator.py
  [ ] tests/k1/architecture/test_module_count.py (update assertion)

Diagrams to Update:
  [ ] architecture_diagrams/k1/k1_complete_with_flows.mmd
  [ ] docs/architecture/diagrams/k1/agent_lifecycle.mmd

Code Locations:
  [ ] k1/l3_execution/agents/registry/agents.yml (add negotiator.yml)
  [ ] k1/l3_execution/agents/__init__.py (export NegotiatorAgent)

Would you like to generate a checklist file? (y/n)
```

---

## 🤖 AI Agent Integration

### 1. Semantic Search Index

**File:** `docs/architecture/decisions/00-meta/adr_index.json`

```json
{
  "version": "1.0.0",
  "generated_at": "2025-11-03T10:00:00Z",
  "total_adrs": 92,
  "adrs": [
    {
      "adr_number": "0004",
      "title": "56-Module 5-Layer Microkernel Architecture",
      "status": "ACCEPTED",
      "folder": "01-foundation/0004-56-module-5-layer-architecture/",
      "file": "0004.md",
      "affected_layers": ["layer1_input", "layer2_orchestration", "layer3_execution", "layer4_runtime", "layer5_infrastructure"],
      "affected_modules": ["k1/l1_input/*", "k1/l2_orchestration/*", "k1/l3_execution/*", "k1/l4_runtime/*", "k1/l5_infrastructure/*"],
      "concerns": ["architecture", "modularity", "performance", "maintainability", "testing"],
      "implementation_status": "COMPLETED",
      "propagation_triggers": ["Adding new module to any layer", "Changing layer dependency rules"],
      "related_adrs": ["0001", "0002", "0003"],
      "summary": "Defines 56-module, 5-layer microkernel architecture for K1 Intelligence Module with strict layering rules and Actor Model foundation."
    }
  ]
}
```

**AI Query Interface:**

```python
# GitHub Copilot / Claude / GPT-4 can query this JSON

# Example 1: "Show me all ADRs affecting Layer 3"
query = {"affected_layers": "layer3_execution"}
results = search_adrs(query)
# Returns: ADR-0004, ADR-0005, ADR-0086, ADR-0033, ADR-0034, ...

# Example 2: "Which ADRs must I update if I add a new module?"
query = {"propagation_triggers": "Adding new module to any layer"}
results = search_adrs(query)
# Returns: ADR-0004 (module count), ADR-0002 (actor patterns)

# Example 3: "Show me all ACCEPTED ADRs with performance concerns"
query = {"status": "ACCEPTED", "concerns": "performance"}
results = search_adrs(query)
# Returns: ADR-0024, ADR-0025, ADR-0026, ADR-0027, ADR-0028, ...
```

### 2. Natural Language Query API (For AI Agents)

**File:** `scripts/query_adrs.py`

```python
#!/usr/bin/env python3
"""
Natural language ADR query interface for AI agents.
Usage: python scripts/query_adrs.py "Which ADRs affect Layer 3 execution?"
"""

import json
import yaml
from pathlib import Path
from typing import List, Dict

class ADRQueryEngine:
    def __init__(self, index_path: str):
        with open(index_path) as f:
            self.index = json.load(f)

    def query(self, natural_language_query: str) -> List[Dict]:
        """
        Parse natural language query and return matching ADRs.

        Supported patterns:
        - "Which ADRs affect <layer>?"
        - "Show me <status> ADRs"
        - "What ADRs must I update if <scenario>?"
        - "Find ADRs with <concern> concerns"
        """

        # Simple keyword matching (can be enhanced with NLP)
        results = []

        query_lower = natural_language_query.lower()

        # Pattern: "affect <layer>"
        if "affect" in query_lower:
            for layer in ["layer1", "layer2", "layer3", "layer4", "layer5"]:
                if layer in query_lower:
                    results = [adr for adr in self.index["adrs"]
                              if layer + "_" in " ".join(adr["affected_layers"])]

        # Pattern: "<status> ADRs"
        if "accepted" in query_lower:
            results = [adr for adr in self.index["adrs"] if adr["status"] == "ACCEPTED"]

        # Pattern: "update if <scenario>"
        if "add" in query_lower and "module" in query_lower:
            results = [adr for adr in self.index["adrs"]
                      if "Adding new module" in " ".join(adr.get("propagation_triggers", []))]

        return results

# CLI interface
if __name__ == "__main__":
    import sys
    query = " ".join(sys.argv[1:])
    engine = ADRQueryEngine("docs/architecture/decisions/00-meta/adr_index.json")
    results = engine.query(query)

    print(f"\n🔍 Query: {query}")
    print(f"📊 Found {len(results)} ADRs:\n")

    for adr in results:
        print(f"  ADR-{adr['adr_number']}: {adr['title']}")
        print(f"    Status: {adr['status']}")
        print(f"    Folder: {adr['folder']}")
        print(f"    Layers: {', '.join(adr['affected_layers'])}")
        print()
```

**Usage:**

```bash
$ python scripts/query_adrs.py "Which ADRs affect Layer 3 execution?"

🔍 Query: Which ADRs affect Layer 3 execution?
📊 Found 8 ADRs:

  ADR-0004: 56-Module 5-Layer Microkernel Architecture
    Status: ACCEPTED
    Folder: 01-foundation/0004-56-module-5-layer-architecture/
    Layers: layer1_input, layer2_orchestration, layer3_execution, layer4_runtime, layer5_infrastructure

  ADR-0005: Agent Lifecycle FSM (6 States)
    Status: ACCEPTED
    Folder: 03-layer2-orchestration/0005-agent-lifecycle-fsm/
    Layers: layer2_orchestration, layer3_execution

  ADR-0086: Dynamic Agent Creation Subsystem
    Status: ACCEPTED
    Folder: 04-layer3-execution/0086-dynamic-agent-creation-subsystem/
    Layers: layer3_execution
```

---

## 📋 Implementation Phases

### Phase 1: Preparation (Week 1, Days 1-2)

**Goal:** Set up infrastructure without moving files yet

#### Day 1: Create Folder Structure

```bash
# Create 14 category folders
mkdir -p docs/architecture/decisions/{00-meta,01-foundation,02-layer1-input,03-layer2-orchestration,04-layer3-execution,05-layer4-runtime,06-layer5-infrastructure,07-contracts-serialization,08-security-privacy,09-communication,10-multi-device-sync,11-ux-product,12-knowledge-memory,13-advanced,14-deployment-ops}

# Create propagation_maps subfolder
mkdir -p docs/architecture/decisions/00-meta/propagation_maps

# Create index.yml templates
for dir in docs/architecture/decisions/{01..14}-*/; do
  echo "# Auto-generated index" > "$dir/index.yml"
done
```

#### Day 2: Create Tooling

```bash
# Script 1: Extract YAML frontmatter → JSON index
scripts/build_adr_index.py

# Script 2: Validate ADR frontmatter
scripts/validate_adr_metadata.py

# Script 3: Natural language query interface
scripts/query_adrs.py

# Script 4: Generate propagation checklists
scripts/check_propagation.py

# Script 5: Update relative links after move
scripts/update_adr_links.py
```

### Phase 2: Add Metadata (Week 1, Days 3-5)

**Goal:** Add YAML frontmatter to all 92 ADRs (don't move files yet)

**Strategy:** Process in batches by category

#### Batch 1: Foundation ADRs (10 ADRs)

- ADR-0001 through ADR-0010
- Add full frontmatter (layers, modules, concerns, propagation)
- Validate with `scripts/validate_adr_metadata.py`

#### Batch 2: Layer-Specific ADRs (40 ADRs)

- Layer 1: ADR-0056, 0057, 0058
- Layer 2: ADR-0005, 0006, 0007
- Layer 3: ADR-0086, 0073, 0033, 0034
- Layer 4: ADR-0017, 0018, 0059, 0060
- Layer 5: ADR-0024, 0025, 0028, 0029, 0030, 0091

#### Batch 3: Cross-Cutting ADRs (42 ADRs)

- Contracts: ADR-0011, 0012, 0013, 0014, 0015, 0016, 0047
- Security: ADR-0010, 0032, 0035, 0036, 0037, 0089
- Communication: ADR-0040, 0042, 0044, 0048
- Multi-Device: ADR-0050 family (4 ADRs)
- UX: ADR-0065, 0067, 0068
- Knowledge: ADR-0081, 0084
- Advanced: ADR-0082, 0083, 0085
- Deployment: ADR-0080, 0088, 0090

**Automation:**

```python
# scripts/add_frontmatter.py
import frontmatter
from pathlib import Path

def add_frontmatter(adr_file: Path, metadata: dict):
    """Add YAML frontmatter to existing ADR file."""
    content = adr_file.read_text()

    # Check if frontmatter exists
    if content.startswith("---"):
        print(f"⚠️  {adr_file.name} already has frontmatter")
        return

    # Create frontmatter
    post = frontmatter.Post(content, **metadata)

    # Write back
    adr_file.write_text(frontmatter.dumps(post))
    print(f"✅ Added frontmatter to {adr_file.name}")

# Example usage
metadata = {
    "adr_number": "0004",
    "title": "56-Module 5-Layer Microkernel Architecture",
    "status": "ACCEPTED",
    "affected_layers": ["layer1_input", "layer2_orchestration", "layer3_execution", "layer4_runtime", "layer5_infrastructure"],
    "concerns": ["architecture", "modularity", "performance"],
    # ...
}

add_frontmatter(Path("docs/architecture/decisions/0004-56-module-5-layer-architecture.md"), metadata)
```

### Phase 3: Link Audit (Week 2, Day 1)

**Goal:** Find all internal ADR references before moving files

```bash
# Find all ADR references
rg "ADR-\d{4}" docs/ --type md --json > adr_references.json
rg "\[ADR-\d{4}\]" docs/ --type md --json >> adr_references.json
rg "docs/architecture/decisions/\d{4}" docs/ --type md --json >> adr_references.json

# Find all relative links
rg "\]\(\.\./" docs/architecture/decisions/ --type md > relative_links.txt
rg "\]\(\.\/" docs/architecture/decisions/ --type md >> relative_links.txt

# Find diagram references
rg "architecture_diagrams/" docs/architecture/decisions/ --type md > diagram_refs.txt
```

**Expected Output:**

```
Found 847 ADR references across 256 files
Found 423 relative links in ADRs
Found 89 diagram references
```

### Phase 4: File Migration (Week 2, Days 2-4)

**Goal:** Move ADRs to new folder structure, update links

**Strategy:** Move category-by-category, validate after each batch

#### Move Script Template

```bash
#!/bin/bash
# scripts/move_adrs.sh

set -e  # Exit on error

# Function to move ADR family (parent + sub-ADRs)
move_adr_family() {
  local adr_num=$1
  local target_folder=$2

  echo "Moving ADR-$adr_num family to $target_folder..."

  # Create ADR-specific subfolder
  mkdir -p "docs/architecture/decisions/$target_folder/$adr_num-*/"

  # Find parent and sub-ADRs
  local parent=$(find docs/architecture/decisions/ -maxdepth 1 -name "${adr_num}-*.md" -not -name "${adr_num}[a-z]-*.md")
  local subs=$(find docs/architecture/decisions/ -maxdepth 1 -name "${adr_num}[a-z]-*.md")

  # Move parent (rename to folder/0004.md)
  if [ -f "$parent" ]; then
    local folder_name=$(basename "$parent" .md)
    mv "$parent" "docs/architecture/decisions/$target_folder/$folder_name/${adr_num}.md"
    echo "  ✅ Moved parent: $parent"
  fi

  # Move sub-ADRs (keep original names)
  for sub in $subs; do
    local folder_name=$(basename "$parent" .md)
    mv "$sub" "docs/architecture/decisions/$target_folder/$folder_name/"
    echo "  ✅ Moved sub-ADR: $sub"
  done
}

# Batch 1: Foundation (10 ADRs)
move_adr_family "0001" "01-foundation"
move_adr_family "0002" "01-foundation"
move_adr_family "0003" "01-foundation"
move_adr_family "0004" "01-foundation"
# ... (continue for all)

echo "✅ All ADRs moved successfully"
```

#### After Each Batch

```bash
# Update relative links
python scripts/update_adr_links.py --folder "01-foundation"

# Validate links work
python scripts/validate_links.py --folder "01-foundation"

# Rebuild index
python scripts/build_adr_index.py
```

### Phase 5: Propagation Maps (Week 2, Day 5)

**Goal:** Create propagation map YAML files for each layer

```bash
# Generate propagation maps
python scripts/generate_propagation_maps.py

# Output:
# ✅ Created docs/architecture/decisions/00-meta/propagation_maps/layer1_input.yml
# ✅ Created docs/architecture/decisions/00-meta/propagation_maps/layer2_orchestration.yml
# ✅ Created docs/architecture/decisions/00-meta/propagation_maps/layer3_execution.yml
# ✅ Created docs/architecture/decisions/00-meta/propagation_maps/layer4_runtime.yml
# ✅ Created docs/architecture/decisions/00-meta/propagation_maps/layer5_infrastructure.yml
```

### Phase 6: Documentation Update (Week 3, Days 1-2)

**Goal:** Update all documentation referring to old ADR paths

#### Files to Update

1. `docs/architecture/decisions/00-meta/readme.md` — Master index
2. `.github/copilot-instructions.md` — Update ADR references
3. All sub-ADR links (423 relative links found in Phase 3)
4. Architecture diagrams (if they reference ADR paths)

```bash
# Auto-update documentation
python scripts/update_documentation.py
```

### Phase 7: Validation & Testing (Week 3, Days 3-5)

**Goal:** Ensure everything works

#### Validation Checklist

```bash
# 1. All ADRs have valid frontmatter
python scripts/validate_adr_metadata.py --all
# Expected: ✅ 92/92 ADRs have valid frontmatter

# 2. All internal links work
python scripts/validate_links.py --all
# Expected: ✅ 847/847 ADR references valid

# 3. All relative links work
python scripts/validate_links.py --relative
# Expected: ✅ 423/423 relative links valid

# 4. Index is up-to-date
python scripts/build_adr_index.py --validate
# Expected: ✅ Index contains 92 ADRs, matches filesystem

# 5. Propagation maps are complete
python scripts/validate_propagation_maps.py
# Expected: ✅ 5/5 layer maps complete

# 6. AI query interface works
python scripts/query_adrs.py "Which ADRs affect Layer 3?"
# Expected: Returns 8 ADRs

# 7. No orphaned files
find docs/architecture/decisions/ -maxdepth 1 -name "*.md" | grep -v "00-meta"
# Expected: Empty (all ADRs moved)
```

---

## 🎯 Success Criteria

### For AI Agents

- ✅ Can query ADRs by layer, module, concern, status via JSON index
- ✅ Natural language queries work ("Which ADRs affect Layer 3?")
- ✅ Propagation checklists auto-generate for common scenarios
- ✅ Search returns results in <1 second

### For Developers

- ✅ Intuitive folder structure (layer-based + cross-cutting)
- ✅ Sub-ADRs grouped with parents (easy to find related decisions)
- ✅ Propagation maps answer "What must I update?" automatically
- ✅ Links work after reorganization (zero 404s)

### For Maintainers

- ✅ Automated tooling (index generation, link validation, frontmatter checks)
- ✅ Pre-commit hooks prevent invalid ADRs
- ✅ Stale index detection (auto-update on ADR changes)
- ✅ Clear ownership (index.yml per folder)

---

## 🛠️ Tooling Requirements

### Scripts to Build

1. **`scripts/build_adr_index.py`**
   - Extract YAML frontmatter from all ADRs
   - Generate `docs/architecture/decisions/00-meta/adr_index.json`
   - Run in CI on every commit to `docs/architecture/decisions/`

2. **`scripts/validate_adr_metadata.py`**
   - Check required frontmatter fields (adr_number, title, status, affected_layers)
   - Fail if missing or invalid
   - Run in pre-commit hook

3. **`scripts/query_adrs.py`**
   - Natural language query interface
   - JSON query interface
   - CLI and Python API

4. **`scripts/check_propagation.py`**
   - Load propagation maps from `00-meta/propagation_maps/*.yml`
   - Generate checklist for scenario
   - Optional: auto-create GitHub issue with checklist

5. **`scripts/update_adr_links.py`**
   - Find all ADR references in moved files
   - Update relative paths
   - Run after file moves

6. **`scripts/validate_links.py`**
   - Check all internal ADR links resolve
   - Check all relative links resolve
   - Fail CI if broken links detected

7. **`scripts/generate_propagation_maps.py`**
   - Analyze ADR frontmatter
   - Generate propagation YAML files
   - Run weekly to keep maps up-to-date

### Pre-Commit Hook

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: validate-adr-metadata
        name: Validate ADR Metadata
        entry: python scripts/validate_adr_metadata.py
        language: python
        files: ^docs/architecture/decisions/.*\.md$
        pass_filenames: true

      - id: rebuild-adr-index
        name: Rebuild ADR Index
        entry: python scripts/build_adr_index.py
        language: python
        files: ^docs/architecture/decisions/.*\.md$
        pass_filenames: false

      - id: validate-adr-links
        name: Validate ADR Links
        entry: python scripts/validate_links.py
        language: python
        files: ^docs/architecture/decisions/.*\.md$
        pass_filenames: true
```

---

## 📊 Expected Outcomes

### Before Reorganization

- ❌ 200+ files in flat directory (chaos)
- ❌ No semantic metadata (AI agents can't search)
- ❌ No propagation tracking (manual grep + hope)
- ❌ Stale index (says "52 modules", actually 56)

### After Reorganization

- ✅ 14 category folders + 92 ADR subfolders (intuitive structure)
- ✅ YAML frontmatter on all ADRs (AI-searchable)
- ✅ Propagation maps for 5 layers (auto-generate checklists)
- ✅ Up-to-date index (JSON + YAML, auto-generated)
- ✅ Automated validation (pre-commit hooks, CI checks)

### Time Savings

- **Before:** "Which ADRs affect Layer 3?" → 30 minutes of grep + manual reading
- **After:** `python scripts/query_adrs.py "Layer 3"` → 2 seconds

- **Before:** "What must I update if I add new module?" → 1 hour of cross-referencing
- **After:** `python scripts/check_propagation.py --scenario "Add new module"` → 5 seconds (auto-generated checklist)

---

## 🚀 Next Steps

### Immediate (This Week)

1. **Review this plan** with architecture team
2. **Approve folder structure** (14 categories OK? Need changes?)
3. **Pilot test** on 5 ADRs (Foundation category)
   - Add frontmatter to ADR-0001, 0002, 0003, 0004, 0005
   - Move to `01-foundation/` folder
   - Validate links still work
   - Get team feedback

### Week 1 (Preparation)

- Create folder structure
- Build tooling (7 scripts)
- Add frontmatter to Foundation ADRs (10 ADRs)

### Week 2 (Migration)

- Add frontmatter to remaining 82 ADRs
- Move all ADRs to new structure
- Update all links
- Generate propagation maps

### Week 3 (Validation)

- Update documentation (readme, copilot-instructions)
- Run full validation suite
- Deploy pre-commit hooks
- Train team on new structure

---

## 📝 Open Questions

1. **Folder Naming:** OK with `01-foundation`, `02-layer1-input`, etc? Or prefer `foundation/`, `layer1-input/` (no numbers)?

2. **Sub-ADR Organization:** Keep parent in `0004/0004.md` or `0004/index.md`? (Currently proposing `0004.md` for consistency)

3. **Propagation Map Granularity:** Should we have per-module maps (56 files) or per-layer maps (5 files)? (Currently proposing per-layer for simplicity)

4. **AI Integration:** Should we build REST API for ADR queries, or is JSON file + Python script sufficient for GitHub Copilot?

5. **Versioning:** Should ADR folders be versioned (e.g., `0004-v2/` for amendments) or keep amendments in same file?

---

## 📚 References

- **Michael Nygard (2011):** "Documenting Architecture Decisions" — Original ADR concept
- **ThoughtWorks Radar:** "Lightweight Architecture Decision Records" — Best practices
- **ADR GitHub Organization:** <https://adr.github.io/> — Tools and templates
- **YAML Frontmatter Spec:** <https://jekyllrb.com/docs/front-matter/> — Metadata format

---
