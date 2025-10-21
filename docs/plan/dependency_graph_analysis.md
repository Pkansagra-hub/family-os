# DEPENDENCY_GRAPH.mmd Analysis Report
**Date:** 2025-10-16  
**Status:** Review & Validation Against ADRs  
**Reviewer:** Chief Planner (Context from Recommendations + ADR Cross-Reference)

---

## Executive Summary

The DEPENDENCY_GRAPH.mmd is **🔥 excellent structural work** with high-quality layer organization, correct module topology, and comprehensive edge coverage. However, there are **5 semantic + syntax issues** that affect both rendering reliability and correctness. These issues are **NOT architectural violations**, but rather **edge direction corrections** and **labeling refinements** to align with ADRs (specifically ADR-0056 Voice Pipeline, ADR-0006 Orchestration, ADR-0005 Agent Lifecycle, and Layer 5 policy routing).

**Grade: A- (Needs minor corrections for A+)**

---

## ✅ What Is Correct

### 1. **Layer Structure & Module Organization** ✅
- **5-layer decomposition:** Correctly follows ADR-0012 (Layer Architecture)
- **52-module inventory:** Matches COMPONENT_CONNECTIONS.md exactly
- **L1: 12 modules** (core kernel: Agent Fabric, Orchestrator, Planner, Protocol Monitor, Supervisor, Mailbox, Capability Enforcer, Arbiter, Saga, Circuit Breaker, Role Attestation, Actor Router)
- **L2: 8 modules** (state: SessionState, Eviction, Hot/Warm/Cold tiers, Retention, Receipt Manager, K0 Bridge)
- **L3: 10 modules** (execution: Tool Runner, MCP/WASM/Process sandboxes, Model Hub, Streaming, Registry, Result Processor, Error Handler, Cost Estimator)
- **L4: 12 modules** (ingress: API Gateway, WebSocket/SSE managers, Topic Router, Voice Pipeline, ASR/TTS, Intent, Barge-In, Clarification, Audio I/O)
- **L5: 10 modules** (infrastructure: Authenticator, Band Manager, Encryption, PII Redactor, Thermal, Model Placement, KV Cache, Backpressure, Metrics, Throttle)

### 2. **Intra-Layer Dependencies** ✅
- **L1 messaging fabric:** Agent Fabric ↔ Orchestrator ↔ Planner (correct proposal → task → plan flow)
- **L1 validation chain:** Protocol Monitor → all L1 agents (correct)
- **L1 supervision:** Supervisor → Agent Fabric with health checks (correct per ADR-0002b)
- **L2 tiering:** Hot (RAM) → Warm (SSD) → Cold (S3) eviction chain (correct per ADR-0018)
- **L3 routing:** Tool Runner routes to MCP/WASM/Process sandboxes (correct per ADR-0033)
- **L4 voice:** ASR → Intent → TTS (mostly correct, but see FIX #1 below)
- **L5 policy:** Band Manager → Encryption/Redaction/Sandbox policies (correct per ADR-0061)

### 3. **Inter-Layer Dependencies** ✅
- **L1 → L2:** Agent Fabric/Orchestrator/Planner update SessionState with context/results (correct per ADR-0023)
- **L1 → L3:** Planner triggers Tool Runner; Agent Fabric queries Model Hub (correct per ADR-0033)
- **L4 → L1:** API Gateway/Voice Pipeline trigger Planner (correct per ADR-0012c, ADR-0056)
- **L4 → L3:** Voice Intent Classifier calls Model Hub; Streaming Engine routes tokens (correct per ADR-0056b)
- **L5 → L1:** Capability Enforcer checks permissions on all L1 agents (correct per ADR-0010)
- **L2 → K0:** K0 Bridge queries P01-P20 pipelines and receives SSE events (correct per ADR-0001, ADR-0002)

### 4. **Emoji Icons & Readability** ✅
- Clear visual distinction per layer and function
- Icons aid quick reference (🤖 agents, 🧠 state, ⚙️ tools, 🌐 ingress, 🔧 infrastructure)
- Well-organized subgraph layout with `direction LR` for readability

### 5. **External System Integration** ✅
- **K0 bridge:** Correctly shows L2.8 querying K0 (P01-P20) and receiving SSE + pipeline outputs
- **Cost Tracker:** Correctly shows L3.5 (Model Hub) + L3.1 (Tool Runner) reporting costs, and COST feeding cost signals back
- **No K0 misrepresentation:** Graph respects ADR-0001 K0/K1 boundary (K0 owns P01-P20 pipelines, K1 owns orchestration)

### 6. **Styling & Color Coding** ✅
- Layer colors are distinct and aid visual parsing
- External systems clearly separated
- Stroke/fill contrast makes layers obvious

---

## ❌ Issues to Fix (5 High-Impact Corrections)

### **FIX #1: Voice I/O Arrow Directions (Semantic Correctness)**

**Current State:**
```mermaid
L4_6 -->|audio frame| L4_11    %% ASR Engine → Microphone (BACKWARDS!)
L4_12 -->|stream to| L4_8      %% Speaker → TTS (BACKWARDS!)
```

**Problem:**
- **Microphone → ASR** flow: Audio ENTERS microphone first, then flows to ASR. Current graph reverses this.
- **TTS → Speaker** flow: TTS generates audio, then flows to speaker. Current graph reverses this.

**ADR Reference:**
- **ADR-0056 (Voice Pipeline Implementation):** Section "3. Streaming Architecture" explicitly shows:
  ```
  Audio In → ASR → Intent → Tools → TTS → Audio Out
  ```
- **ADR-0056a (ASR Ingress):** "Frame Size, VAD, Partials" shows WebSocket audio enters ASR engine.
- **ADR-0056e (Audio Output):** "Device handshake, buffer management" shows TTS output flows to speaker.

**Whiteboard Reference:**
- `whiteboard.md` L927-1317 (Voice Pipeline Overload & Backpressure) consistently shows:
  - Input flow: Microphone → ASR pipeline
  - Output flow: TTS pipeline → Speaker

**Fix:**
```mermaid
%% REMOVE these (backwards):
%% L4_6 -->|audio frame| L4_11
%% L4_12 -->|stream to| L4_8

%% REPLACE with (correct direction):
L4_11 -->|audio frame| L4_6      %% Microphone → ASR Engine
L4_8 -->|stream to| L4_12        %% TTS Engine → Speaker
```

**Impact:** 
- ✅ Aligns with ADR-0056 voice pipeline spec
- ✅ Corrects semantic flow for human readers
- ✅ Enables proper mermaid rendering without confusion

---

### **FIX #2: Planner/Orchestrator Execution Edge (Backward Edge)**

**Current State:**
```mermaid
L1_2 -->|executes plans| L1_3     %% Orchestrator → Planner (BACKWARDS!)
L1_3 -->|submits plans| L1_2      %% Planner → Orchestrator (CORRECT)
```

**Problem:**
- Planner generates plans, Orchestrator executes them.
- Current edge `Orchestrator → Planner` creates a cycle: Planner sends plan → Orchestrator receives → Orchestrator sends back to Planner.
- This represents execution result flow, but the label "executes plans" is misleading. Orchestrator should execute Tool Runner, not loop back to Planner.

**ADR Reference:**
- **ADR-0006 (3-Phase Orchestration):** Section "Decision" shows:
  - Phase 1 (Negotiation): Orchestrator announces task to agents
  - Phase 2 (Selection): Orchestrator selects winning agent
  - Phase 3 (Execution): Orchestrator executes plan **via Tool Runner** (ADR-0033)
  - Result flows back to Planner for learning feedback
- **ADR-0007 (4-Stage Planner):** Commit stage persists plans; no execution by Planner itself.
- **COMPONENT_CONNECTIONS.md (E1.4.I3):** "Orchestrator selection phase → Tool Runner execution (L3.1)"

**Whiteboard Reference:**
- `whiteboard.md` Section 7 (Orchestration) shows: "Planner ← (receives results) ← Orchestrator ← (executes via) ← Tool Runner"

**Fix:**
```mermaid
%% REMOVE this (incorrect label + unnecessary bidirectional):
%% L1_2 -->|executes plans| L1_3

%% KEEP this (correct):
L1_3 -->|submits plans| L1_2

%% ADD this (execution via Tool Runner):
L1_2 -->|executes plan via| L3_1   %% Orchestrator → Tool Runner
```

**Impact:**
- ✅ Removes confusing backward edge
- ✅ Shows Orchestrator → Tool Runner execution path (correct per ADR-0006c)
- ✅ Planner ← receives results still implied by Planner input
- ✅ Eliminates cycle confusion

---

### **FIX #3: Warm Tier Label Clarification (Terminology)**

**Current State:**
```mermaid
L2_4["☀️ Warm Tier L2<br/>(SSD K0 WAL)"]
```

**Problem:**
- Label conflates **K1's local SSD cache** (Warm Tier) with **K0's Write-Ahead Log (WAL)**.
- K0 WAL is K0's internal durability mechanism; it is NOT the same as K1's Warm Tier.
- Per ADR-0001 (K0/K1 Boundary): K1 accesses K0 WAL **only via K0 Bridge Manager** (L2.8), not directly.
- Misleading label could cause architectural confusion.

**ADR Reference:**
- **ADR-0001 (K0/K1 Boundary):** "K0 owns WAL and all K0 storage; K1 owns session cache tiers."
- **ADR-0018 (3-Tier Storage):** Section "Tier 2 (Warm)": "SSD local cache for SessionState delta snapshots."
- **ADR-0023 (SessionState Management):** "Eviction tier 2: SSD (local, no K0 dependency)."

**Contract Reference:**
- `contracts/sessionstate/eviction_manager.yml`: "Warm tier = local SSD (/var/cache/k1/sessions), not K0 WAL."

**Fix:**
```mermaid
%% REMOVE this:
%% L2_4["☀️ Warm Tier L2<br/>(SSD K0 WAL)"]

%% REPLACE with (clear separation):
L2_4["☀️ Warm Tier L2<br/>(SSD Local Cache)"]

%% KEEP existing K0 WAL interaction implicit via L2.8 Bridge:
%% L2_8 -->|WAL batched writes| K0  (already exists, correct)
```

**Impact:**
- ✅ Clarifies K1 cache tiers vs K0 WAL separation
- ✅ Reduces architectural misunderstanding
- ✅ Correctly represents ADR-0001 boundary

---

### **FIX #4: Arbiter Gating Path (Missing Edge)**

**Current State:**
```mermaid
L1_3 -->|validates| L1_12        %% Planner → Arbiter (validation request)
%% NO return edge from Arbiter
```

**Problem:**
- Planner validates plans with Arbiter (correct).
- But **no visible gate from Arbiter back to Orchestrator** showing approval/denial.
- Orchestrator needs Arbiter's decision before executing plans (ADR-0007c).
- Missing edge makes it unclear how Arbiter decision influences orchestration.

**ADR Reference:**
- **ADR-0007c (Validation Stage - 2-Tier):** 
  - "Rule-based validation + Arbiter ML validation"
  - "Arbiter → approve/deny decision"
  - Result flows to Orchestrator for execution gate
- **ADR-0006 (3-Phase Orchestration):** Selection phase includes Arbiter approval gate
- **SEQUENTIAL_ROADMAP.yaml (I1.5.3):** "Arbiter validation < 100ms, rejects plans violating rules, provides decision to Orchestrator"

**Whiteboard Reference:**
- `whiteboard.md` Section 8.4: "Validation gate: Arbiter approve/deny → Orchestrator execute/reject"

**Fix:**
```mermaid
%% KEEP existing:
L1_3 -->|validates| L1_12        %% Planner → Arbiter

%% ADD this (missing gate):
L1_12 -->|approve/deny| L1_2      %% Arbiter → Orchestrator (execution gate)
```

**Impact:**
- ✅ Shows full validation pipeline: Planner → Arbiter → Orchestrator
- ✅ Demonstrates execution gate per ADR-0007c
- ✅ Clarifies Arbiter's role in 3-phase orchestration

---

### **FIX #5: Band/Capabilities Policy Routing (Incomplete Path)**

**Current State:**
```mermaid
L5_2 -->|band rules| L3_4         %% Band Manager → Process Sandbox only
L5_2 -->|classify| L5_3           %% Band Manager → Encryption (correct)
L5_2 -->|classify| L5_4           %% Band Manager → PII Redactor (correct)
%% NO edge to Capability Enforcer or Arbiter
```

**Problem:**
- Band Manager routes privacy policies **only to Process Sandbox** (L3.4).
- But privacy bands affect **ALL policy decisions**: admission (Capability Enforcer), plan validation (Arbiter), and capability checks.
- Missing edges to L1.8 (Capability Enforcer) and L1.12 (Arbiter) make policy routing incomplete.

**ADR Reference:**
- **ADR-0061 (3-Tier Backpressure & Policy Cascade):** Section "Band Manager":
  - "Band policy feeds Capability Enforcer (admission control)"
  - "Band policy feeds Arbiter (plan validation)"
  - "Band policy feeds Process Sandbox (execution context)"
- **ADR-0010 (Capability Enforcer):** "Checks band + capability against request"
- **ADR-0007c (Validation Stage):** "Arbiter considers band classification in approval decision"

**Contract Reference:**
- `contracts/privacy/band_manager.yml`: "Band rules route to: Capability Enforcer (admission), Arbiter (validation), Sandbox (execution)"

**Fix:**
```mermaid
%% KEEP existing:
L5_2 -->|band rules| L3_4         %% Band Manager → Process Sandbox

%% ADD these (missing policy routing):
L5_2 -->|band rules| L1_8         %% Band Manager → Capability Enforcer (admission control)
L5_2 -->|band rules| L1_12        %% Band Manager → Arbiter (plan validation)
```

**Impact:**
- ✅ Shows full band policy cascade per ADR-0061
- ✅ Demonstrates multi-layer policy enforcement
- ✅ Aligns with admission control + validation design

---

## 🔧 Mermaid Rendering Optimization (Optional Polish)

### **Current Mermaid Header (Good, but Not Standard):**
```mermaid
graph TB
```

### **Recommended Header (Better Renderer Control):**
```mermaid
%%{init: {"flowchart": {"defaultRenderer": "elk"}}}%%
graph TB
```

**Why:**
- `elk` renderer (Eclipse Layout Kernel) handles large graphs with 50+ nodes better
- More consistent edge routing
- Better subgraph nesting visualization

**Note:** Your current graph renders fine without this, but adding it future-proofs for larger diagrams.

---

## 📊 Validation Checklist

| Aspect | Status | Notes |
|--------|--------|-------|
| **Layer decomposition** | ✅ CORRECT | 5 layers, 52 modules, matches ADR-0012 |
| **L1 messaging** | ✅ CORRECT | Agent Fabric ↔ Orchestrator ↔ Planner flows correct |
| **L2 eviction** | ✅ CORRECT | Hot → Warm → Cold chain correct |
| **L3 sandboxing** | ✅ CORRECT | Tool Runner → MCP/WASM/Process routing correct |
| **L4 voice input** | ❌ NEEDS FIX #1 | Microphone → ASR direction incorrect |
| **L4 voice output** | ❌ NEEDS FIX #1 | TTS → Speaker direction incorrect |
| **L1 orchestration** | ❌ NEEDS FIX #2 | Orchestrator backward edge to Planner unnecessary |
| **L1 arbitration** | ❌ NEEDS FIX #4 | Arbiter approval gate to Orchestrator missing |
| **L2 warm tier** | ❌ NEEDS FIX #3 | K0 WAL terminology misleading |
| **L5 policy** | ❌ NEEDS FIX #5 | Band Manager → Capability/Arbiter paths missing |
| **K0 boundary** | ✅ CORRECT | K0 interactions via L2.8 bridge only (correct) |
| **Cost tracking** | ✅ CORRECT | L3.5/L3.1 → COST → L5.6/L3.5 cycle correct |
| **Styling** | ✅ EXCELLENT | Colors, emojis, subgraphs all clear |
| **DAG property** | ⚠️ NEEDS CHECK | Remove L1.2 backward edge (FIX #2) to preserve acyclicity |

---

## 📝 Corrected Mermaid Snippet (Drop-In Replacement)

Here are the exact line changes to apply:

```mermaid
%% ========== FIX #1: VOICE I/O DIRECTIONS ==========
%% REMOVE (backward):
%% L4_6 -->|audio frame| L4_11
%% L4_12 -->|stream to| L4_8

%% REPLACE with (correct):
L4_11 -->|audio frame| L4_6      %% Microphone → ASR Engine
L4_8 -->|stream to| L4_12        %% TTS Engine → Speaker

%% ========== FIX #2: PLANNER ORCHESTRATOR EDGE ==========
%% REMOVE (backward edge):
%% L1_2 -->|executes plans| L1_3

%% ADD (execution via Tool Runner):
L1_2 -->|executes plan via| L3_1   %% Orchestrator → Tool Runner

%% ========== FIX #3: WARM TIER LABEL ==========
%% CHANGE node label:
%% FROM: L2_4["☀️ Warm Tier L2<br/>(SSD K0 WAL)"]
%% TO:   L2_4["☀️ Warm Tier L2<br/>(SSD Local Cache)"]

%% ========== FIX #4: ARBITER GATING ==========
%% ADD (missing gate):
L1_12 -->|approve/deny| L1_2      %% Arbiter → Orchestrator

%% ========== FIX #5: BAND POLICY ROUTING ==========
%% ADD (missing paths):
L5_2 -->|band rules| L1_8         %% Band Manager → Capability Enforcer
L5_2 -->|band rules| L1_12        %% Band Manager → Arbiter

%% ========== OPTIONAL: MERMAID HEADER ==========
%% ADD at top (for better rendering):
%% %%{init: {"flowchart": {"defaultRenderer": "elk"}}}%%
```

---

## ✨ Summary: Correctness Assessment

### **Architectural Soundness**
- ✅ **Layer decomposition:** Perfect (ADR-0012 compliant)
- ✅ **Module inventory:** Complete (52 modules accounted for)
- ✅ **Intra-layer deps:** ~95% correct (L1 messaging, L2 tiering, L3 sandboxing excellent)
- ✅ **Inter-layer deps:** ~90% correct (L1↔L2↔L3↔L4 flows mostly right)
- ❌ **Voice pipeline:** 2 edges reversed (FIX #1)
- ❌ **Orchestration:** 1 unnecessary backward edge + 1 missing gate (FIX #2, #4)
- ❌ **Policy routing:** 2 missing paths (FIX #5)
- ⚠️ **Terminology:** 1 label conflation (FIX #3)

### **Final Grade**
- **Current:** A- (Excellent structure, minor semantic fixes needed)
- **After fixes:** A+ (Production-ready dependency graph)

### **Recommendation**
**PROCEED with confidence.** Apply the 5 fixes above, validate against DEPENDENCY_GRAPH.mmd one more time, and the diagram will be ready for:
1. Team architecture review
2. Planning documents (SEQUENTIAL_ROADMAP.yaml references)
3. CI/CD validation pipeline
4. Maintenance documentation

The graph is semantically sound and only needs these surgical edits for perfect correctness.

---

## 🔗 Cross-References for Validation

| ADR | Section | Validation |
|-----|---------|-----------|
| ADR-0001 | K0/K1 Boundary | K0 WAL interactions correct via L2.8 ✅ |
| ADR-0006 | 3-Phase Orchestration | Needs Arbiter gate (FIX #4) ⚠️ |
| ADR-0007c | Validation Stage | Arbiter → Orchestrator gate needed ⚠️ |
| ADR-0010 | Capability Enforcer | Band → Capability path missing (FIX #5) ⚠️ |
| ADR-0012 | Layer Architecture | 5-layer structure correct ✅ |
| ADR-0018 | 3-Tier Storage | Hot → Warm → Cold chain correct ✅ |
| ADR-0023 | SessionState Management | Warm tier terminology needs fix (FIX #3) ⚠️ |
| ADR-0033 | Tool Runner | Orchestrator → Tool Runner path needed (FIX #2) ⚠️ |
| ADR-0056 | Voice Pipeline | Microphone/ASR/TTS/Speaker directions wrong (FIX #1) ❌ |
| ADR-0056a | ASR Ingress | Microphone → ASR direction wrong (FIX #1) ❌ |
| ADR-0056d | TTS Synthesis | TTS → Speaker direction wrong (FIX #1) ❌ |
| ADR-0061 | Backpressure Cascade | Band policy routing incomplete (FIX #5) ⚠️ |

---

**Report Compiled By:** Chief Planner (Sequential Development)  
**Next Step:** Apply fixes and revalidate with `mmd_validate`
