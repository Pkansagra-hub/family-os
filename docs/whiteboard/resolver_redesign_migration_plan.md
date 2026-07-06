# Resolver Redesign — Migration Plan

**Status:** PLAN — POC v2 VALIDATED 2026-06-16
**Date:** 2026-06-11 (audited) | 2026-06-12 (POC v1) | 2026-06-16 (POC v2 — native-app routing)
**References:** `docs/whiteboard/fabric_e2e_map.md` (Sections 10, 11, 13), `k1/docs/future_family_apps_development.md`, `docs/whiteboard/poc_v2_native_app_router_plan.md`
**Branch:** `feature/prompt-architecture-refactor`
**POC v1:** `scripts/poc_connector_search.py` — connector retrieval, namespace prior, synthetic distractors (SUPERSEDED)
**POC v2:** `scripts/poc_v2/` — native-app routing, compiled contracts, active-OS gating, real schema scoring

---

## ✅ POC v2 VALIDATION RESULTS (2026-06-16)

**The core architecture is validated as native-app routing with 33 native apps across 5 OS domains. No namespace prior. No synthetic distractors. Real compiled-contract schema scoring.**

### Manual benchmark (120 human-curated queries)

| Metric | Value | Method |
|--------|-------|--------|
| **Strict C@1** | **80.8%** | MiniLM-L6 + real schema scoring (compiled contracts) |
| **Acceptable Top-3** | **95.8%** | Top-3 envelope covers nearly all queries |
| **Active-OS leakage** | **0%** | Zero queries routed outside active_os_set |
| **Backend-name safety** | **100%** | Zero backend names exposed as connectors |
| **Model size** | **22MB** | MiniLM-L6 (all-MiniLM-L6-v2) |
| **Inference latency** | **3.4ms/q** | Cosine similarity + contract schema scoring |

### Generated benchmark (7,732 LLM-generated queries, 6 tiers)

| Metric | Value |
|--------|-------|
| **Strict C@1** | 71.1% |
| **Acceptable C@1** | 75.4% |
| **Acceptable Top-3** | **93.1%** |
| **Must-Include Pass** | **94.1%** |
| **False Confident Wrong (>0.15 margin)** | **8.2%** |
| **Active-OS Leakage** | **0** |
| **Backend Safety Fails** | **0** |
| **Avg Latency** | 3.5ms |

### Confidence calibration

| Confidence | % of queries | C@1 |
|------------|-------------|------|
| Confident | 76.3% | 78.6% |
| Ambiguous (known confusable pair, low margin) | 17.1% | 50.0% |
| Uncertain | 6.7% | 38.7% |

**What was proven wrong (POC v1 → corrected in v2):**

- ❌ Namespace prior (+0.20 family.*) is CHEATING — removed. OS domain from active_os_set only
- ❌ "87% Conn@1" is inflated — tested connector retrieval, not native-app routing
- ❌ Synthetic distractors (chase.*, nest.*, fitbit.*) model the wrong architecture
- ❌ V21 "Schema-Augmented Search" is fake — `cid == pred → boost`, not real signal
- ❌ Intent classifier adds +1.5% at 6-way for +2.1ms — not worth it. Downgraded to Phase 2
- ❌ LLM-hint benchmark tiers (EASY/MEDIUM/HARD) measure front-LLM quality, not router quality

**What was proven right (POC v1 → confirmed in v2):**

- ✅ MiniLM-L6 is the right bi-encoder for this task (22MB, ~3ms/q)
- ✅ Pure text search beats old graph resolver
- ✅ FTS5/BM25 hybrid fusion is WORSE than pure dense
- ✅ Cross-encoder (UltraBERT) is useless for cosine similarity
- ✅ Within-domain ambiguity is the real ceiling, not cross-domain leakage

**Architecture verdict:** Kernel-grade compiled contracts (MiniLM dense + active-OS gating + real schema scoring + confidence calibration) is the production baseline. Namespace prior is cheating. Intent classifier is Phase 2. Synthetic distractors are the wrong benchmark.

---

## POC v2 Architecture — Kernel-Grade Compiled Contracts

POC v2 introduces a compiled-contract architecture that moves all domain facts out of
router code and into declarative data files. The router is pure machinery.

### Compiled indexes (all built from declarative contracts)

```
scripts/poc_v2/
├── boundary_contracts.py        ← 33 NativeAppBoundary (owns/does_not_own/ambiguous_with/backend_slots)
├── native_app_stubs.py          ← 27 stub definitions with concept_aliases + operation_aliases
├── contract_compiler.py         ← Compiles boundaries + stubs into kernel-grade indexes:
│   ├── EffectLexicon            ← verb token → effect (57 tokens, compiled from declarative map)
│   ├── ResourcePhraseTrie       ← phrase → resource_kind (800+ phrases, prefix trie, longest-match)
│   ├── BackendSlotIndex         ← backend name → slot_type → native_app (240 backend names)
│   └── NativeAppContract        ← unified contract for all 33 apps (real FamilyOS + stubs)
├── router.py                    ← route_to_native_app() — zero domain facts, reads compiled registry
├── bench_queries.py             ← 120 manual + 7.7k LLM-generated cross-OS queries
├── bench_native_app_router.py   ← Original 120-query benchmark runner
└── bench_query_generator.py     ← Vertex AI query generator with anti-bias prompts
```

### Why compiled contracts

| Problem (POC v1) | Solution (POC v2) |
|------------------|-------------------|
| `_VERB_EFFECT_MAP` hardcoded in router.py (82-line dict) | `EffectLexicon` — compiled from declarative data, router calls `.extract()` |
| Token-level resource extraction with naive boundary lookup | `ResourcePhraseTrie` — compiled phrase trie, longest-match, effect-token filtering |
| Asymmetric alias access — stubs had concept/operation aliases, real FamilyOS apps didn't | `NativeAppContract` — unified contract for ALL apps. Real apps get aliases extracted from definition text |
| Backend safety = post-hoc check in benchmark | `BackendSlotIndex` — first-class extraction during routing. "Walmart" → grocery_retailers → family.shopping |
| Schema scoring = "classifier predicted app X → boost X" | Real multi-signal: resource match + effect match + alias overlap + hard veto + specificity penalty |
| No confidence calibration | margin-based confidence + confusable-pair boost + ambiguity gate |

### Native-app routing vs connector retrieval

The fundamental redesign from POC v1 to POC v2:

| | POC v1 (Connector Retrieval) | POC v2 (Native-App Routing) |
|---|---|---|
| **Unit of search** | Individual connector among 111 | Native app among 33 |
| **Distractors** | 500+ synthetic (chase.*, nest.*, fitbit.*) | Other-OS native apps (health.*, finance.*, enterprise.*) |
| **What it tests** | "Can search find family.shopping?" | "Can router distinguish family.reminders from health.medications?" |
| **Active-OS gating** | No | Yes — apps outside active_os_set get score 0.0 |
| **Namespace prior** | +0.20 if family.* | REMOVED — OS domain from session context |
| **Backend handling** | Backends modeled as competing connectors | Backends are arguments, never routing targets |

### The 5 OS domains

| OS Domain | Native Apps | Real/Stub |
|-----------|------------|-----------|
| FamilyOS | 6 (calendar, shopping, tasks, reminders, chores, family_settings) | Real |
| HealthOS | 7 (records, appointments, medications, vitals, insurance, caregiving, lab_results) | Stub |
| FinanceOS | 6 (accounts, budgeting, investing, taxes, insurance, loans) | Stub |
| PharmaOS | 6 (fulfillment, inventory, insurance, customer, compliance, compounding) | Stub |
| EnterpriseOS | 8 (hr, payroll, project_mgmt, crm, documentation, communication, devops, it) | Stub |
| **Total** | **33** | 6 real + 27 stubs |

---

## ⚠️ AUDIT RESULTS — READ BEFORE EXECUTING

**7 sub-agents across 2 passes + Epic 0.1 cross-reference verification against e2e map.**

| Category | Count | Details |
|----------|-------|---------|
| **Files verified** | 21/21 exist | 1 path error (FILE 11), 1 class name error (FILE 17) |
| **Hard-delete symbols verified** | 12/12 exist | All traced to exact lines |
| **"Should not change" files verified** | 27/27 clean | Zero resolver-internal imports |
| **CRITICAL gaps found** | 3 | RequestFrame, RequestFrameBuilder, BackTaskEnvelope unaddressed |
| **HIGH gaps found** | 5 | PromptPackBuilder, resource_projection, HIL types, planner types, kernel port |
| **MEDIUM gaps found** | 11 | Various consumers + test coverage |
| **New RES-XXX issues needed** | 14 | See Milestone 10 |
| **Dead code in scripts/** | ~50 references | Documented in scripts impact table |
| **⚠️ EPIC 0.1 COHERENCE ISSUES** | 3 | See below — execution order + scope gaps |

**EPIC 0.1 CROSS-REFERENCE AGAINST E2E MAP (2026-06-12):**

| Check | RES-001 vs e2e §10A | RES-002 vs e2e §10B + Architecture Philosophy |
|-------|---------------------|----------------------------------------------|
| Schema fields match | ✅ `action_text`, `context_hints` aligned | N/A |
| Envelope fields match | N/A | ✅ `verdict`, `connector`, `tools[]`, `constitution`, `search_confidence`, `alternative_connectors` all aligned |
| `constitution` shape | N/A | ✅ `how_to_sequence`, `what_to_verify`, `when_to_ask_human`, `companion_connectors`, `conflict_rules`, `precondition_summary`, `prerequisite_reads` all in §10B |
| Field naming consistency | N/A | ⚠️ e2e §Architecture Philosophy uses `confidence` but §10B uses `search_confidence`. RES-002 follows §10B (correct). |
| `ResolveSituationRequest.frame` field | N/A | ❌ **GAP**: `situated_resolver.py:76` has `frame: RequestFrame`. RES-031 only lists `request_frame.py` — `ResolveSituationRequest` also needs updating. |
| `_build_resolve_request()` glue | N/A | ❌ **GAP**: `fabric.py:1889` calls `build_frame_from_dict()` which RES-032 deletes. No RES issue explicitly covers this function. |
| Execution order coherence | N/A | ❌ **GAP**: RES-031 (step 8) runs BEFORE RES-007 (step 11). `CapabilityTypeResolver` still expects `RequestFrame` at step 8. |

**⚠️ COHERENCE FIXES APPLIED BELOW:**

- RES-031 scope expanded to `situated_resolver.py` + `fabric.py`
- New RES-031a added: update `ResolveSituationRequest` + `_build_resolve_request` + `resolve()`
- Execution order: RES-007/010/012 move BEFORE RES-031/032/033 (rewire internals first, then change input type)

---

**Key corrections to this plan:**

- FILE 11: `k1/fabric/resolver/policy/selector.py` → actual path is `k1/fabric/policy/selector.py`
- FILE 17: `ManifestTranslator` class does NOT exist → actual symbols are `register_definition()` and `register_definition_to_store()` functions
- FILE 10: `_select_best_capability` is a module-level function, NOT a `CapabilityBinderService` method

**Bottom line:** The plan's core architecture (M0–M9, 30 issues) is sound. The 14 new issues below fill the INPUT-side, prompt-pack, and peripheral-consumer gaps. The 8 "should not change" files are correctly scoped. Execute M10 issues in parallel with their parent milestones.

**⚠️ ENFORCEMENT AUDIT (2026-06-12):** Every milestone checked for hidden vetoes, silent denies, and executor policy walls. Verdict:

| Milestone | Hidden Vetoes? | Verdict |
|-----------|---------------|---------|
| M0 (Contract) | None — schema + envelope only | ✅ |
| M1 (Connector Search) | None — additive search | ✅ |
| M2 (Gut Type Resolver) | None — deletes graph, replaces with search | ✅ |
| M3 (Remove Binder) | None — deletes heuristic, Back picks tool | ✅ |
| **M4 (Kill Verdict)** | **1 FOUND & FIXED** — RES-014 originally proposed idempotency as executor block. Fixed: idempotency is transparent result cache, never a gate | ✅ |
| M5 (Constitution) | None — teaching surface, advisory only | ✅ |
| M6 (Back Prompt) | None — teaches Back to read packet | ✅ |
| M7 (Companion/Fallback) | None — scale-safe summaries, no blocks | ✅ |
| M8 (Factory Cleanup) | None — wiring only | ✅ |

**No Hidden Vetoes principle (v1):**

```
No hidden vetoes. No executor policy wall. No silent deny.
No surprise HIL block. No resolver says yes but executor says no.
Executor v1: mechanical execution only. Policy/constitution/HIL = visible advice to Back.
```

---

## Target Architecture (POC v2 — Native-App Routing with Compiled Contracts)

```
Query: "add eggs to my shopping list"
  │
  ▼
Stage 0: Active-OS Gating [<1ms]
  → filter to apps in active_os_set (e.g., {family} → 6 apps, {family, health} → 13 apps)
  → zero leakage — apps outside active OS get score 0.0
  │
  ▼
Stage 1: MiniLM-L6 Dense Retrieval [3ms]
  → encode(query) → cosine similarity against pre-computed connector docs
  → only gated apps considered — not all 33
  │
  ▼
Stage 2: Compiled-Contract Schema Scoring [<1ms]
  → EffectLexicon extracts effects (verb→effect mapping, compiled from declarative data)
  → ResourcePhraseTrie extracts resource kinds (phrase trie, compiled from all app contracts)
  → BackendSlotIndex extracts backend hints (backend name→slot→native_app)
  → schema_score() = resource match + effect match + alias overlap + hard veto
  → NO classifier. NO namespace prior. Generic — reads contracts, no domain facts.
  │
  ▼
Stage 3: Fusion + Confidence Calibration
  → combined = 0.70 * cosine_norm + 0.30 * schema_score
  → margin = top1.score - top2.score
  → confusable pair? (top1, top2 in ambiguous_with graph) → requires +0.04 extra margin
  → confidence = "confident" | "ambiguous" | "uncertain"
  → should_force_primary = (confidence == "confident")
  │
  ▼
RoutedApp {
  connector_id, cosine_score, schema_score, combined_score,
  margin, confidence, is_confusable_pair, should_force_primary
}
  │
  ▼
ResolutionEnvelope {
  verdict: "can_execute",     ← ALWAYS, never blocks
  connector: { id, label, description },
  tools: [ all tools for connector ],
  constitution: { teaching surface },
  search_confidence: float,
  alternative_connectors: [ top-3 with acceptable_apps + must_include_top3 ],
  is_resolved: bool,          ← confidence != "ambiguous"
  confidence: str,            ← "confident" | "ambiguous" | "uncertain"
  margin: float,              ← score gap to next app
}
  │
  ▼
Back reads packet → picks tool → executes
```

**This is a hard-purge resolver redesign, validated by POC v2 on 7,732 queries.**

The current graph/type/policy/binder maze gets cut down. The resolver stops using
domain/resource/operation hints as hard filters, stops picking one tool, and instead
returns `{connector, tools, constitution, confidence, alternatives, is_resolved}` to Back.

**POC v2-proven numbers:** 80.8% Strict C@1 (120 manual), 75.4% Acceptable C@1 (7,732 generated),
93.1% Acceptable Top-3, 94.1% Must-Include Pass, 0% Active-OS Leakage, 0 Backend Safety Fails,
3.5ms/q, 22MB MiniLM-L6.

### Key architectural changes from POC v1

| POC v1 (SUPERSEDED) | POC v2 (CURRENT) | Why |
|---------------------|------------------|-----|
| Namespace Prior [+0.20 if family.*] | Active-OS gating from session context | Hardcoded boost is cheating. OS domain is contextual truth |
| 111 connectors + 500+ synthetic distractors | 33 native apps across 5 OS domains | External services are backends, not peer connectors |
| Intent Classifier (Stage 0) | Phase 2 (optional, valuable at 50+ apps) | +1.5% accuracy for +2.1ms. Not worth it at current scale |
| V21 schema = classifier predicts app → boost | Real schema = resource/effect/alias overlap from compiled contracts | No classifier dependency. Generic, reads contracts |
| LLM-hint benchmark tiers | Raw utterance + active_os_set tiers | Measures router quality, not front-LLM quality |
| `search_connectors(action_text)` on GPS | `route_to_native_app(utterance, active_os_set, ctx, registry)` | Standalone. Compiled contracts, not GPS-dependent |
| No confidence calibration | margin-based confidence + ambiguity gate | Confusable pairs need bigger margins before claiming confidence |

---

## Milestone -1: Prerequisites & Foundation

**Status:** ✅ COMPLETE — 2026-06-16
**Date:** 2026-06-15 (added from junior-dev safety audit) | 2026-06-16 (all 6 issues executed)

### Goal

Resolve all dependency, schema migration, and design-decision blockers BEFORE any
code-level RES issues begin.  These are the foundation stones — without them,
RES-003, RES-011b, RES-015, and Phase 3 cannot proceed.

**All 6 Milestone -1 issues are DONE:**

| Issue | Status | What |
|-------|--------|------|
| RES-000a | ✅ DONE | `sentence-transformers>=3.0.0` in requirements.txt, UltraBERT deprecation removed |
| RES-000b | ✅ DONE | 5 teaching columns in GPS `connector_constitutions`, `additionalProperties: True` in constitution schema |
| RES-000c | ✅ DONE | `connector_backends` table in GPS |
| RES-000d | ✅ DONE | `backend_id` + `session_id` columns in LPS `connected_resources` |
| RES-000e | ✅ DONE | Detailed RES-031/032/033 specs written |
| RES-046 | ✅ DECIDED | MiniLM for connector search, UltraBERT for everything else |

---

#### RES-000a: Add `sentence-transformers` to `requirements.txt`

**Status:** ✅ DONE — 2026-06-16

| Field | Value |
|-------|-------|
| **File** | `requirements.txt` |
| **Priority** | BLOCKER — RES-003 cannot run without this |
| **Depends on** | RES-046 (MiniLM vs UltraBERT decision) |

**What this does:**

1. Add `sentence-transformers>=3.0.0` to `requirements.txt` under the EMBEDDING WORKER CONTAINER section.
2. Remove or update the DEPRECATED comment at line 86 that says `# DEPRECATED - Replaced by UltraBERT` and `# sentence-transformers -> UltraBERT embedding`.
3. Verify the package installs and `SentenceTransformer("all-MiniLM-L6-v2")` loads the 22MB model.

**⚠️ CONTEXT:** POC v2 proved MiniLM-L6 is the right bi-encoder for native-app routing (80.8% Strict C@1 manual, 75.4% Acceptable C@1 7.7k generated).
UltraBERT is a cross-encoder, not a bi-encoder — useless for cosine similarity.  The existing
`k1/fabric/resolver/embedding_index.py` already has a lazy import of `SentenceTransformer`,
so this dependency was always intended.

**Verification:**

- `pip install sentence-transformers>=3.0.0` succeeds
- `from sentence_transformers import SentenceTransformer; SentenceTransformer("all-MiniLM-L6-v2")` loads without error

---

#### RES-000b: GPS schema migration — add new constitution columns

**Status:** ✅ DONE — 2026-06-16

| Field | Value |
|-------|-------|
| **Files** | `k1/fabric/stores/global_projection_store.py` (schema section), new migration file |
| **Priority** | BLOCKER — RES-015 cannot add teaching fields without DB columns |
| **Depends on** | Nothing |

**What this does:**

Add 5 new JSON columns to the GPS `constitutions` table (or to the constitution JSON blob):

| Column | Type | Default | Maps to |
|--------|------|---------|---------|
| `how_to_sequence_json` | TEXT | `'[]'` | `ConstitutionArtifact.how_to_sequence` |
| `what_to_verify_json` | TEXT | `'[]'` | `ConstitutionArtifact.what_to_verify` |
| `when_to_ask_human_json` | TEXT | `'[]'` | `ConstitutionArtifact.when_to_ask_human` |
| `companion_connectors_json` | TEXT | `'[]'` | `ConstitutionArtifact.companion_connectors` |
| `conflict_rules_json` | TEXT | `'[]'` | `ConstitutionArtifact.conflict_rules` |

**Alternative:** Store in the existing constitution JSON blob column if one exists — simpler, no new columns.
Decide during implementation.

**Also needed:** Update `CONSTITUTION_JSON_SCHEMA` in `constitution/schema.py` L235 — change
`"additionalProperties": False` → `True` so the 5 new fields pass validation.

**Verification:**

- New columns exist in GPS after migration
- `ConstitutionLoader.load()` can write/read new fields
- JSON schema accepts documents with new fields

---

#### RES-000c: GPS schema migration — create `connector_backends` table

**Status:** ✅ DONE — 2026-06-16

| Field | Value |
|-------|-------|
| **Files** | `k1/fabric/stores/global_projection_store.py` (schema section) |
| **Priority** | BLOCKER — RES-011b needs this table |
| **Depends on** | Nothing |

**What this does:**

Create the `connector_backends` table in GPS:

```sql
CREATE TABLE IF NOT EXISTS connector_backends (
    connector_id TEXT NOT NULL,
    backend_id TEXT NOT NULL,        -- e.g., "walmart-api"
    backend_label TEXT NOT NULL,     -- e.g., "Walmart"
    schema_version TEXT,
    registered_at TEXT,
    PRIMARY KEY (connector_id, backend_id)
);
```

This table registers which backends a connector CAN support.
LPS `connected_resources` records which backends ARE connected for a given session.
The intersection (`connector_backends` ∩ `connected_resources`) = the live enum for RES-011b.

**Verification:**

- Table exists in GPS after migration
- `INSERT INTO connector_backends (...) VALUES (...)` succeeds
- `SELECT backend_id, backend_label FROM connector_backends WHERE connector_id = ?` returns expected rows

---

#### RES-000d: LPS schema migration — add `backend_id`, `session_id` to `connected_resources`

**Status:** ✅ DONE — 2026-06-16

| Field | Value |
|-------|-------|
| **Files** | `k1/fabric/stores/local_projection_store.py` (L55 `_ensure_schema()`) |
| **Priority** | BLOCKER — RES-011b needs session-scoped + backend_id-aware LPS reads |
| **Depends on** | Nothing |

**What this does:**

Add 2 new columns to LPS `connected_resources`:

```sql
ALTER TABLE connected_resources ADD COLUMN backend_id TEXT NOT NULL DEFAULT '';
ALTER TABLE connected_resources ADD COLUMN session_id TEXT NOT NULL DEFAULT '';
```

**Current schema (verified at LPS L55):**

- `resource_id TEXT PRIMARY KEY` — this becomes `(resource_id, backend_id)` composite or backend_id becomes part of resource_id
- `actor_id TEXT NOT NULL` — stays, but session_id is added for session-scoped queries
- No `session_id` column — RES-011b needs session-scoped filtering
- No `backend_id` column — RES-011b needs to filter by backend

**⚠️ DESIGN DECISION NEEDED:** Does `backend_id` become part of the primary key, or a separate column?
Recommendation: Add `backend_id` as a non-PK column, indexed.  One `resource_id` can have multiple
backends connected (e.g., Walmart + Target both connected for shopping).

**Verification:**

- New columns exist in LPS after migration
- `INSERT INTO connected_resources (resource_id, actor_id, session_id, connector_id, backend_id, ...)` succeeds
- `SELECT backend_id FROM connected_resources WHERE session_id = ? AND connector_id = ?` returns expected rows

---

#### RES-000e: Write detailed RES-031 / RES-032 / RES-033 specifications

**Status:** ✅ DONE — 2026-06-16

| Field | Value |
|-------|-------|
| **Files** | This document (detailed specs below) |
| **Priority** | BLOCKER — Phase 3 steps 16-18 cannot be executed by junior devs without specs |
| **Depends on** | Nothing |

**What this does:** The detailed specifications for RES-031, RES-032, and RES-033 are
appended below.  Each spec includes exact file paths, line numbers, old→new code shapes,
call-site inventories, and verification commands.

---

### RES-031: Replace `RequestFrame` with `action_text`-first input

**Status:** ⬜ NOT STARTED
**Junior-safe:** ❌ Multi-file, production data types, needs careful coordination with RES-032/033.
**Coordinate with:** RES-032 (builder deleted simultaneously), RES-033 (envelope simplified simultaneously), RES-001a/b (Back schema already expects `action_text`).

| Field | Value |
|-------|-------|
| **Files** | `k1/fabric/resolver/request_frame.py` (entire file), `k1/fabric/resolver/situated_resolver.py` (L70–86 `ResolveSituationRequest`, L448–530 `resolve()`), `k1/fabric/fabric.py` (L1889–1916 `_build_resolve_request`) |
| **Priority** | CRITICAL — this is the core surface change |
| **Depends on** | RES-007 (CapabilityTypeResolver already deleted), RES-001a/b (Back sends `action_text`), RES-032/033 (build simultaneously) |

**Design decision — what survives, what dies:**

| Symbol | Fate | Rationale |
|--------|------|-----------|
| `RequestFrame` class | **DELETE** | Replaced by bare `action_text: str` + `context_hints: dict` in `ResolveSituationRequest` |
| `RequestFrameIntent` class | **DELETE** | No longer needed — no intent struct, just raw text |
| `PersonRef` class | **KEEP** | LPS alias resolution still needs person references, but they move to `context_hints` (advisory only) |
| `ResourceRef` class | **KEEP** | Same — move to `context_hints`, advisory only |
| `TimeWindowHint` class | **KEEP** | Temporal grounding still needs time windows, move to `context_hints` |
| `SafetyContext` field | **KEEP** | Moves to top-level `ResolveSituationRequest.safety_context` |

**Change 1/3 — `request_frame.py` (entire file):**

```python
# OLD (L1–86): Entire module defines RequestFrame, RequestFrameIntent,
# PersonRef, ResourceRef, TimeWindowHint dataclasses.
# FILE: k1/fabric/resolver/request_frame.py

# NEW: Strip to just advisory hint types.  action_text replaces the frame.
"""Advisory context hints for the resolver pipeline.

RES-031 (2026-06-16): RequestFrame and RequestFrameIntent are DELETED.
The resolver input is now ``action_text: str`` + ``context_hints: dict``.
PersonRef, ResourceRef, and TimeWindowHint survive as advisory hint types
only — they live in context_hints, not a structured frame.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PersonRef:
    """Advisory person reference in context_hints.  LPS alias resolution
    may use this as a boost signal, but resolver NEVER filters by it."""
    raw: str
    confidence: str = "medium"  # "high" | "medium" | "low"
    needs_resolution: bool = True


@dataclass(frozen=True)
class ResourceRef:
    """Advisory resource reference in context_hints."""
    raw: str
    resource_kind_hint: str | None = None
    confidence: str = "medium"
    needs_resolution: bool = True


@dataclass(frozen=True)
class TimeWindowHint:
    """Advisory time window in context_hints."""
    raw_phrase: str
    resolved_start: str | None = None  # ISO 8601
    resolved_end: str | None = None
    confidence: str = "medium"
```

**Change 2/3 — `situated_resolver.py` L70–86 (`ResolveSituationRequest`):**

```python
# OLD (L70–86):
@dataclass(frozen=True)
class ResolveSituationRequest:
    request_id: str
    frame: RequestFrame              # ← REPLACED
    actor_id: str
    space_id: str
    session_id: str
    tier: str
    safety_band: str
    disclosure_phase: str = "connector_summary"
    freshness_policy: str = "allow_stale_reads"
    prompt_budget_tokens: int = 8000
    completed_prerequisite_bindings: list[str] = field(default_factory=list)
    previous_resolution_id: str | None = None
    idempotency_keys: list[str] = field(default_factory=list)
    budget_remaining: dict | None = None

# NEW:
@dataclass(frozen=True)
class ResolveSituationRequest:
    """Single-pass resolver input.  RES-031: action_text replaces frame."""
    request_id: str
    action_text: str                 # ← REPLACES frame: RequestFrame
    context_hints: dict = field(default_factory=dict)  # ← advisory only
    actor_id: str
    space_id: str
    session_id: str
    tier: str                        # 'LOW' | 'MEDIUM' | 'HIGH'
    safety_band: str                 # 'GREEN' | 'AMBER' | 'RED'
    disclosure_phase: str = "connector_summary"
    freshness_policy: str = "allow_stale_reads"
    completed_prerequisite_bindings: list[str] = field(default_factory=list)
    previous_resolution_id: str | None = None
    idempotency_keys: list[str] = field(default_factory=list)
    budget_remaining: dict | None = None
```

**Change 3/3 — `fabric.py` L1889–1916 (`_build_resolve_request`):**

```python
# OLD (L1889–1916):
async def _build_resolve_request(
    self,
    payload: dict[str, Any],
    request_id: str,
) -> ResolveSituationRequest:
    """..."""
    frame_dict = payload.get("frame", {})
    actor_id = str(payload.get("actor_id", "") or "")
    # ... extracts intents, person_refs, resource_refs from frame_dict ...
    frame = build_frame_from_dict(frame_dict, actor_id=actor_id, ...)
    return ResolveSituationRequest(
        request_id=request_id,
        frame=frame,                      # ← REPLACED
        ...
    )

# NEW:
async def _build_resolve_request(
    self,
    payload: dict[str, Any],
    request_id: str,
) -> ResolveSituationRequest:
    """Build ResolveSituationRequest from action_text-first payload.

    RES-031: No more RequestFrame.  action_text is the primary signal.
    context_hints is advisory only — NEVER filters.
    """
    action_text = str(payload.get("action_text", "") or "").strip()
    if not action_text:
        raise ResolverError("action_text is required and must be non-empty")

    context_hints = payload.get("context_hints") or {}
    if not isinstance(context_hints, dict):
        context_hints = {}

    actor_id = str(payload.get("actor_id", "") or "")
    space_id = str(payload.get("space_id", "") or "")
    session_id = str(payload.get("session_id", "") or "")
    tier = str(payload.get("tier", "MEDIUM")).upper()
    safety_band = str(payload.get("safety_band", "GREEN")).upper()

    return ResolveSituationRequest(
        request_id=request_id,
        action_text=action_text,
        context_hints=context_hints,
        actor_id=actor_id,
        space_id=space_id,
        session_id=session_id,
        tier=tier,
        safety_band=safety_band,
    )
```

**Call-site inventory — all references to `RequestFrame` that must be updated:**

| File | Line(s) | What | Action |
|------|---------|------|--------|
| `k1/fabric/resolver/request_frame.py` | 1–86 | `RequestFrame`, `RequestFrameIntent` classes | DELETE both classes; keep PersonRef/ResourceRef/TimeWindowHint |
| `k1/fabric/resolver/situated_resolver.py` | 76 | `frame: RequestFrame` field | Replace with `action_text: str` + `context_hints: dict` |
| `k1/fabric/resolver/situated_resolver.py` | 90 | `request_frame: RequestFrame` in `ResolutionEnvelope` | Replace with `action_text: str` (RES-002 also touches this) |
| `k1/fabric/resolver/situated_resolver.py` | 448–530 | `resolve()` method body | Replace `request.frame.intents` iteration with direct `action_text` usage |
| `k1/fabric/fabric.py` | 1889–1916 | `_build_resolve_request()` | Rewrite as shown above |
| `k1/fabric/resolver/request_frame_builder.py` | 1–200 | `build_frame_from_dict()`, `RequestFrameBuilder` | DELETE entire file (RES-032) |
| `k1/fabric/resolver/back_task_envelope.py` | 48–70 | `task_dispatch["intents"]` | Replace with `task_dispatch["action_text"]` (RES-033) |
| `tests/k1/fabric/resolver/test_request_frame.py` | 1–end | All tests | Rewrite for action_text contract |
| `tests/k1/fabric/resolver/test_capability_type_resolver.py` | 1–end | Tests referencing RequestFrame | DELETE (CapabilityTypeResolver already deleted by RES-007) |

**Verification:**

- Run: `pytest tests/k1/fabric/resolver/test_request_frame.py -v` (after RES-031/032/033 applied)
- Manual: `ResolveSituationRequest` has `action_text` field, no `frame` field
- Manual: `request_frame.py` has no `RequestFrame` or `RequestFrameIntent` classes
- Manual: `_build_resolve_request` extracts `action_text` not `frame` dict
- Manual: `grep -r "RequestFrame" k1/fabric/` returns only historical comments, no live code

---

### RES-032: Replace `RequestFrameBuilder`

**Status:** ⬜ NOT STARTED
**Junior-safe:** ✅ Delete-only, no new logic.
**Coordinate with:** RES-031 (must happen simultaneously), RES-033 (BackTaskEnvelope simplified).

| Field | Value |
|-------|-------|
| **Files** | `k1/fabric/resolver/request_frame_builder.py` (DELETE entire file), `k1/fabric/fabric.py` (L1889 remove `build_frame_from_dict` import) |
| **Priority** | CRITICAL — deletes the old builder so nothing accidentally uses it |
| **Depends on** | RES-031 (RequestFrame deleted, so builder has nothing to build) |

**Design decision:**

The builder's job was `BackTaskEnvelope → RequestFrame`.  With RES-031, there is no
`RequestFrame` — the resolver takes raw `action_text` directly.  The builder has zero
remaining function.  **Delete it entirely.**

No replacement is needed: `_build_resolve_request()` (updated by RES-031) directly
extracts `action_text` from the payload dict.  Back sends `action_text` as a flat
string via the tool schema (RES-001a/b).  There is no mapping step.

**Change 1/2 — DELETE `request_frame_builder.py`:**

```bash
# Literally: delete the file
rm k1/fabric/resolver/request_frame_builder.py
```

All symbols removed:

| Symbol | Fate |
|--------|------|
| `RequestFrameBuilder` class | DELETE — no RequestFrame to build |
| `build_frame_from_dict()` | DELETE — no frame dict to parse |
| `_resolve_time_window()` | DELETE — time hints come via context_hints, not extracted from intents |
| `_PERSON_KEYS`, `_RESOURCE_KEYS`, `_TIME_KEYS` | DELETE — param sniffing is anti-pattern for new contract |
| `_dedupe_person_refs()`, `_dedupe_resource_refs()` | DELETE — no ref extraction in new path |
| `_optional_text()`, `_resource_ref_kind()` | DELETE — helper functions for dead code |

**Change 2/2 — `fabric.py` import cleanup (L1–60):**

```python
# OLD (somewhere in fabric.py imports):
from k1.fabric.resolver.request_frame_builder import (
    RequestFrameBuilder,
    build_frame_from_dict,
)

# NEW: Remove these imports.  fabric.py now uses action_text directly.
```

**Call-site inventory — all references to `RequestFrameBuilder` and `build_frame_from_dict`:**

| File | Line(s) | What | Action |
|------|---------|------|--------|
| `k1/fabric/resolver/request_frame_builder.py` | 1–200 | Entire module | DELETE file |
| `k1/fabric/fabric.py` | import block | `from k1.fabric.resolver.request_frame_builder import ...` | Remove imports |
| `k1/fabric/fabric.py` | 1889 | `build_frame_from_dict(frame_dict, ...)` call | Replaced by direct `action_text` extraction (RES-031 Chg 3/3) |
| `tests/k1/fabric/resolver/test_request_frame.py` | test functions | Tests for `RequestFrameBuilder` | Rewrite or delete (covered by RES-031 test rewrite) |

**Verification:**

- Run: `pytest tests/k1/fabric/resolver/ -v -k "not capability_type"` (skip deleted CapabilityTypeResolver tests)
- Manual: `k1/fabric/resolver/request_frame_builder.py` does not exist
- Manual: `grep -r "RequestFrameBuilder\|build_frame_from_dict" k1/` returns zero results

---

### RES-033: Replace `BackTaskEnvelope` intent-dict contract

**Status:** ⬜ NOT STARTED
**Junior-safe:** ✅ Single file, field rename + simplification.
**Coordinate with:** RES-031 (simultaneously), RES-032 (simultaneously).

| Field | Value |
|-------|-------|
| **Files** | `k1/fabric/resolver/back_task_envelope.py` (L48–70 `BackTaskEnvelope` class, L74–110 `parse_back_task_envelope()`) |
| **Priority** | CRITICAL — the entry-point contract must match what Back actually sends |
| **Depends on** | RES-001a/b (Back sends `action_text`, not `intents` array) |

**Design decision — what changes in `task_dispatch`:**

```python
# OLD task_dispatch shape (what Back used to send):
{
    "intents": [
        {
            "intent_id": "intent-abc123",
            "action": "Add Riley's dentist appointment to family calendar",
            "domain": "family",
            "operation_hint": "create",
            "resource_kind_hint": "calendar_event",
            "subject_hint": "dentist appointment",
            "params": {"person_hint": "Riley", "date_hint": "next Monday 3pm"}
        }
    ],
    "actor_role": "parent",
    "user_phrase": "Add Riley's dentist appointment to family calendar"
}

# NEW task_dispatch shape (what Back sends after RES-001a/b):
{
    "action_text": "Add Riley's dentist appointment to family calendar",
    "context_hints": {
        "person_hints": ["Riley"],
        "domain_hint": "family",
        "resource_hint": "calendar",
        "operation_hint": "create"
    },
    "actor_role": "parent"
}
```

**Change 1/2 — `BackTaskEnvelope` class (L48–70):**

```python
# OLD (L48–70):
@dataclass(frozen=True)
class BackTaskEnvelope:
    """..."""
    envelope_id: str
    task_id: str
    trace_id: str
    session_id: str
    actor_id: str
    space_id: str
    tier: str
    safety_band: str
    task_dispatch: dict[str, Any]          # ← contains "intents" array
    session_state_ref: str | None = None
    grounding_envelope_id: str | None = None
    temporal_anchor_id: str | None = None
    spatial_context_id: str | None = None
    submitted_at: str = ""

# NEW:
@dataclass(frozen=True)
class BackTaskEnvelope:
    """The envelope Back wraps around action_text + resolved context.

    RES-033 (2026-06-16): task_dispatch no longer contains ``intents`` array.
    Back sends ``action_text`` (flat string) + ``context_hints`` (advisory dict).
    This envelope is the single entry point into resolve().

    Budget fields (max_iterations, max_fabric_calls, max_prompt_tokens) are NOT
    part of this contract — they belong to Back/Concierge runtime, not Fabric.
    """
    envelope_id: str
    task_id: str
    trace_id: str
    session_id: str
    actor_id: str
    space_id: str
    tier: str
    safety_band: str
    task_dispatch: dict[str, Any]          # ← NOW contains "action_text" + "context_hints"
    session_state_ref: str | None = None
    grounding_envelope_id: str | None = None
    temporal_anchor_id: str | None = None
    spatial_context_id: str | None = None
    submitted_at: str = ""

    @property
    def action_text(self) -> str:
        """Convenience accessor — extracts action_text from task_dispatch."""
        return str(self.task_dispatch.get("action_text", "") or "")

    @property
    def context_hints(self) -> dict[str, Any]:
        """Convenience accessor — extracts context_hints from task_dispatch."""
        hints = self.task_dispatch.get("context_hints") or {}
        return hints if isinstance(hints, dict) else {}
```

**Change 2/2 — `parse_back_task_envelope()` validation (L74–110):**

```python
# OLD (L74–110): Validates task_dispatch is non-empty dict.
# No validation of "intents" key — assumes Back always populates it.

# NEW: Add validation that task_dispatch has action_text.
def parse_back_task_envelope(payload: dict[str, Any]) -> BackTaskEnvelope:
    """Validate and parse a raw dict into a ``BackTaskEnvelope``.

    RES-033: task_dispatch must contain ``action_text`` (non-empty string).
    ``intents`` array is no longer required or validated.
    """
    if not isinstance(payload, dict):
        raise BackTaskEnvelopeError("payload", "payload must be a dict")

    # ... existing validations for task_id, trace_id, session_id, etc. ...

    task_dispatch = payload.get("task_dispatch")
    if not isinstance(task_dispatch, dict) or not task_dispatch:
        raise BackTaskEnvelopeError("task_dispatch", "task_dispatch must be a non-empty dict")

    # NEW: validate action_text exists and is non-empty
    action_text = str(task_dispatch.get("action_text", "") or "").strip()
    if not action_text:
        raise BackTaskEnvelopeError(
            "task_dispatch.action_text",
            "action_text is required and must be a non-empty string",
        )

    # context_hints is optional — no validation needed (advisory only)

    return BackTaskEnvelope(
        envelope_id=payload.get("envelope_id", "env-" + uuid.uuid4().hex[:12]),
        task_id=task_id,
        trace_id=trace_id,
        session_id=session_id,
        actor_id=actor_id,
        space_id=space_id,
        tier=tier,
        safety_band=safety_band,
        task_dispatch=task_dispatch,
        session_state_ref=payload.get("session_state_ref"),
        grounding_envelope_id=payload.get("grounding_envelope_id"),
        temporal_anchor_id=payload.get("temporal_anchor_id"),
        spatial_context_id=payload.get("spatial_context_id"),
        submitted_at=payload.get("submitted_at", _utc_now_iso()),
    )
```

**Call-site inventory — all references to `task_dispatch["intents"]` that must be updated:**

| File | Line(s) | What | Action |
|------|---------|------|--------|
| `k1/fabric/resolver/back_task_envelope.py` | 48–70 | `BackTaskEnvelope` class | Add `action_text` + `context_hints` properties |
| `k1/fabric/resolver/back_task_envelope.py` | 74–110 | `parse_back_task_envelope()` | Add `action_text` validation |
| `k1/fabric/resolver/request_frame_builder.py` | 1–200 | `envelope.task_dispatch.get("intents")` | FILE DELETED by RES-032 — no update needed |
| `k1/fabric/fabric.py` | 1889–1916 | `_build_resolve_request()` | Already updated by RES-031 to use `action_text` directly |
| `k1/concierge/tools/implementations.py` | 1531–1607 | `execute_resolve_situation()` | Already updated by RES-001b to send `action_text` |

**Verification:**

- Run: `pytest tests/k1/fabric/resolver/test_request_frame.py -v` (after RES-031/032/033 applied)
- Manual: `BackTaskEnvelope.task_dispatch` contains `action_text` not `intents`
- Manual: `parse_back_task_envelope()` raises `BackTaskEnvelopeError` if `action_text` is missing
- Manual: `envelope.action_text` property returns the string
- Manual: `grep -r "task_dispatch\[.intents.\]" k1/` returns zero results

---

### RES-046: Decide and document — MiniLM vs UltraBERT for connector embeddings

**Status:** ✅ DECIDED — 2026-06-16

| Field | Value |
|-------|-------|
| **Files** | This document (decision record below) |
| **Priority** | BLOCKER — determines dependency strategy for RES-003 |
| **Depends on** | Nothing |

**What this does:**

Resolve the conflict between:

- `requirements.txt` line 86: `# DEPRECATED - Replaced by UltraBERT` / `# sentence-transformers -> UltraBERT embedding`
- POC v2 results: MiniLM-L6 (22MB) = 80.8% Strict C@1 (manual) / 75.4% Acceptable C@1 (7.7k generated). POC v1's 87% was inflated by namespace prior. UltraBERT = cross-encoder (useless for bi-encoder cosine similarity)
- Existing code: `k1/fabric/resolver/embedding_index.py` already lazy-imports `SentenceTransformer`

**Decision: Option A — MiniLM for connector search, UltraBERT for everything else.**

| Option | What | Risk |
|--------|------|------|
| A ✅ | Use MiniLM-L6 (`sentence-transformers`) for connector search, keep UltraBERT for other embedding tasks | Low — two models coexist |
| B ❌ | Replace UltraBERT entirely with MiniLM-L6 | Medium — migration of existing UltraBERT call sites |
| C ❌ | Wrap UltraBERT to produce bi-encoder outputs | High — UltraBERT is cross-encoder architecture |

**Rationale:**

1. POC v2 validated MiniLM-L6 at scale (7,732 generated queries, 33 native apps).  80.8% Strict C@1 is honest — no namespace prior, no fake schema scoring.
2. UltraBERT is a cross-encoder: it takes (query, document) pairs and scores them jointly.  This is the wrong architecture for connector retrieval, which needs bi-encoder cosine similarity over pre-computed embeddings.
3. Both models coexist cleanly: MiniLM (22MB) for connector search via `embedding_index.py`, UltraBERT for sentiment/classification tasks elsewhere.
4. `sentence-transformers>=3.0.0` is already in `requirements.txt` (added by RES-000a).

**Verification:**

- Decision documented in this plan with rationale ✅
- `requirements.txt` updated accordingly (RES-000a) ✅

---

## Milestone 0: Freeze the New Contract

### Epic 0.1: Define the new resolver contract

**Goal:** Replace the old `RequestFrame`-heavy resolver surface with a clean `action_text`-first contract.

---

#### RES-001a: Replace Back tool schema for `resolve_situation` (schema only)

**Status:** ✅ DONE — 2026-06-16
**Junior-safe:** ✅ Single file, no downstream impact, well-specified replacements.

| Field | Value |
|-------|-------|
| **Files** | `k1/concierge/tools/schemas_back.py` (L37–122) |
| **Priority** | CRITICAL — blocks all downstream work |
| **Depends on** | Nothing |
| **Verified against live code** | 2026-06-12: All old-schema fields confirmed at exact lines. `RequestFrameIntent` (request_frame.py:48–57) has `action`, `domain`, `operation_hint`, `resource_kind_hint`. `RequestFrame` (request_frame.py:60–83) has `person_refs`, `resource_refs`. JSON schema describes but does NOT enforce these (generic `object` type for intent items). |

**Change — OLD schema (delete from `RESOLVE_SITUATION_SCHEMA` at L37):**

- `frame` as required top-level field (L116: `"required": ["frame"]`)
- `frame.intents[]` — described as "action, domain, params, operation_hint, resource_kind_hint" (L58–62, generic `object` items)
- `frame.person_refs` (L65–68), `frame.resource_refs` (L69–72), `frame.time_window_hint` (L63–64), `frame.safety_context` (L78)
- These map to `RequestFrame.intents: list[RequestFrameIntent]` and `RequestFrame.person_refs: list[PersonRef]` — all being replaced by RES-031

**Change — NEW schema (add):**

- `action_text` (string, required) — raw user utterance, primary search signal. Maps to `RequestFrameIntent.action` which already exists as "raw user action text"
- `actor_id` (string, required) — auto-filled by `execute_resolve_situation()` L1558–1568 from `ToolContext.active_principal_id`
- `session_id` (string, required) — auto-filled at L1569
- `space_id` (string, required) — auto-filled at L1568
- `context_hints` (object, optional) — advisory boost signals only, NEVER filters
  - `domain_hint`, `resource_hint`, `operation_hint` — migrated from old `RequestFrameIntent` fields

**What this does NOT touch:** `implementations.py`, `ports.py` — those are RES-001b and RES-019.

**Verification:**

- Run: `pytest tests/k1/concierge/test_schemas_back.py -v -k resolve` (if exists)
- Manual: `RESOLVE_SITUATION_SCHEMA` has `action_text` as required, `frame` is absent

---

#### RES-001b: Update `execute_resolve_situation()` payload builder (implementations only)

**Status:** ✅ DONE — 2026-06-16
**Junior-safe:** ✅ Single file, 3 lines changed, well-specified.
| Coordinate with:** RES-001a (schema must match), RES-019 (full payload rewrite)

| Field | Value |
|-------|-------|
| **File** | `k1/concierge/tools/implementations.py` (L1531–1607 `execute_resolve_situation()`) |
| **Priority** | CRITICAL — bridges schema to adapter |
| **Depends on** | RES-001a (schema must exist before payload builder) |

**Change (3 locations in `implementations.py`):**

```python
# OLD (L1546):
frame = args.get("frame")
if not isinstance(frame, dict):
    return ToolResult(..., error="frame is required and must be an object")

# NEW:
action_text = args.get("action_text", "")
if not action_text or not isinstance(action_text, str):
    return ToolResult(..., error="action_text is required and must be a non-empty string")
```

```python
# OLD (L1572):
payload: dict[str, Any] = {
    "frame": frame,
    "actor_id": str(actor_id),
    ...
}

# NEW:
context_hints = args.get("context_hints") or {}
payload: dict[str, Any] = {
    "action_text": action_text,
    "context_hints": context_hints,
    "actor_id": str(actor_id),
    ...
}
```

```python
# OLD (L1586):
logger.info("tool:resolve_situation  actor=%s space=%s frame_intents=%d",
            actor_id, space_id, len(frame.get("intents", [])))

# NEW:
logger.info("tool:resolve_situation  actor=%s space=%s action_text_len=%d",
            actor_id, space_id, len(action_text))
```

**Auto-fill survives unchanged (L1558–1569):** `actor_id`, `space_id`, `session_id` extraction from `ToolContext` stays exactly as-is.

**Verification:**

- Run: `pytest tests/k1/concierge/tools/ -v -k resolve_situation`
- Manual: `action_text="add eggs to shopping list"` → payload has `action_text` not `frame`

---

#### RES-001c: Update `ports.py` docstring + `task/intent.py` deprecation

**Status:** ✅ DONE — 2026-06-16
**Junior-safe:** ✅ Two files, doc-only changes, zero logic.

| Field | Value |
|-------|-------|
| **Files** | `k1/concierge/ports.py` (L137–143), `k1/concierge/task/intent.py` (L52–58) |
| **Priority** | LOW — docstrings and deprecation markers |
| **Depends on** | RES-001a (schema finalized) |

**Change — `ports.py` L137–143:**

- `IDispatchPort.resolve_situation()` docstring says `"Accepts a payload dict with frame (required)"` → update to `"action_text (required)"` + `"context_hints (optional, advisory only)"`
- Signature stays `async def resolve_situation(self, payload: dict) -> dict:` — dict-in, dict-out survives via RES-026

**Change — `task/intent.py`:**

- `TaskIntent` has `resource_family: str | None` and `operation_hint: str | None` with docstring "passed through to Back's resolve_situation call." These fields become dead weight.
- Mark as deprecated with a comment: `# DEPRECATED (2026-06-15): resolver no longer uses domain/rf/op hints as filters.`
- Do NOT delete yet — other code may still read these fields.

**Verification:**

- Manual: `ports.py:137` docstring updated
- Manual: `task/intent.py` has deprecation markers on `resource_family` and `operation_hint`

---

#### RES-002: Replace `ResolutionEnvelope` shape

**Status:** ✅ DONE — 2026-06-16

| Field | Value |
|-------|-------|
| **Files** | `k1/fabric/resolver/situated_resolver.py` (L87–120 for class, L122–170 for `to_dict()`), `k1/fabric/fabric.py` (L1760–1790 for `_handle_resolve_situation`) |
| **Priority** | CRITICAL — the core gap |
| **Depends on** | RES-001 (schema must match) |
| **Verified against live code** | 2026-06-12: All old fields confirmed. CRITICAL CORRECTION: `_constitution_dict()` (L282) DOES serialize constitution to Back via `to_dict()`. Back receives old-format constitution data (`prerequisite_reads`, `mutation_sequencing`, `hil_gates`, `companion_resource_roles`) but is never taught to read it. The new teaching fields (`how_to_sequence`, `what_to_verify`, `when_to_ask_human`) don't exist yet. The `to_dict()` also serializes `request_frame`, `candidate_universe`, `intent_resolutions`, `policy_bundle`, `binding_bundle` — ALL stripped in the new envelope. |

**Change — OLD envelope (verified at situated_resolver.py:87–120):**

```python
@dataclass(frozen=True)
class ResolutionEnvelope:                    # Line 87
    resolution_id: str                       # L88
    request_id: str                          # L89
    request_frame: RequestFrame              # L90 — replaced by RES-031
    candidate_universe: ResourceUniverse | None  # L91 — stripped
    intent_resolutions: list[ResolvedIntentType] # L92 — stripped
    policy_bundle: PolicyBundle | None       # L93 — stripped
    binding_bundle: BindingBundle | None     # L94 — stripped per RES-011
    constitution: ConstitutionArtifact | None # L95 — old format; replaced by teaching surface
    prompt_pack: PromptPack | None           # L96 — stripped
    verdict: str                             # L97 — kept, always "can_execute"
    sub_reason: str | None                   # L98 — kept for diagnostics
    allowed_next_actions: list[str]          # L99 — replaced by tools[]
    allowed_capability_names: list[str]      # L100 — FLAT STRINGS ← THE CORE GAP
    capability_name_to_binding: dict[str,str] # L101 — stripped
    hil_request: dict | None                 # L102 — merged into constitution.when_to_ask_human
    recovery_directive: dict | None          # L103 — stripped
    diagnostics: list[dict]                  # L104 — kept for observability
    created_at: str                          # L105
    expires_at: str                          # L106
    execution_plan: list[dict]               # L107 — replaced by tools[] + constitution
    machine_verdict: str = ""                # L108
```

**`to_dict()` serializes (L122–170):** Currently returns constitution, request_frame, candidate_universe, intent_resolutions, policy_bundle, binding_bundle, prompt_pack — all stripped in new envelope. The new `to_dict()` returns only the fields below.

**Change — NEW envelope:**

```python
ResolutionEnvelope {
    verdict: "can_execute",                    # ← ALWAYS, never blocks
    connector: {
        connector_id: str,
        label: str,
        description: str
    },
    tools: [
        {
            capability_name: str,
            action_name: str,
            invocation_mode: str,  # "read" | "execute"
            effect: str,           # "read" | "write" | "delete"
            description: str,
            required_inputs: list[dict],
            optional_inputs: list[dict]
        }
    ],
    constitution: {
        precondition_summary: str,             # ← EXISTS at ConstitutionArtifact.precondition_summary (schema.py:197)
        how_to_sequence: list[str],            # ← NEW, mapped from mutation_sequencing (RES-016)
        what_to_verify: list[str],             # ← NEW, mapped from verification_requirements (RES-016)
        prerequisite_reads: list[dict],        # ← EXISTS at ConstitutionArtifact.prerequisite_reads (schema.py:189)
        companion_connectors: list[dict],      # ← NEW, mapped from companion_resource_roles (RES-016)
                                               #   ⚠️ CompanionResourceRole has {resource_kind, role, description}
                                               #   but new shape needs {connector_id, role, description}
        when_to_ask_human: list[dict],         # ← NEW, mapped from hil_gates (RES-016)
                                               #   ⚠️ HILGate has {trigger, prompt, options, field}
                                               #   but new shape needs {trigger, reason, prompt} — reason is MISSING
        conflict_rules: list[str]              # ← NEW, mapped from conflict_analysis_rules (RES-016)
                                               #   ⚠️ ConflictRule is structured {check, with_resource_kinds, description, resolution}
                                               #   but new shape needs flat prose strings
    },
    search_confidence: float,                  # ← NEW, computed by ConnectorResolver (RES-003)
    alternative_connectors: list[dict],         # ← NEW, top-3 alternatives
    diagnostics: list[dict]                    # ← KEPT from old envelope for observability
}
```

**⚠️ Field mapping discrepancies found during verification:**

| New field | Old source | Issue |
|-----------|-----------|-------|
| `when_to_ask_human[].reason` | `HILGate` | HILGate has `{trigger, prompt, options, field}` — **no `reason` field**. RES-016 must either add `reason` to HILGate or populate `reason` from `prompt` text. |
| `companion_connectors[].connector_id` | `CompanionResourceRole` | CompanionResourceRole has `{resource_kind, role, description}` — **no `connector_id`**. RES-016 must resolve `resource_kind` → `connector_id` via GPS lookup. |
| `conflict_rules: list[str]` | `ConflictRule` | ConflictRule is structured `{check, with_resource_kinds, description, resolution}`. RES-016 must decide: convert to prose strings or keep structured dicts. |

**Verification:**

- Run: `pytest tests/k1/fabric/resolver/ -v -k envelope` (targeted)
- Assert: `verdict == "can_execute"` always
- Assert: `tools[0]` has `description`, `required_inputs`, `optional_inputs`
- Assert: `constitution.how_to_sequence` is populated from `mutation_sequencing`
- Assert: No `request_frame`, `candidate_universe`, `intent_resolutions`, `policy_bundle`, `binding_bundle` in serialized output

---

## Milestone 1: Build Connector-Level Search

### Epic 1.1: Add connector-first retrieval in GPS

**Goal:** Search connectors, not capabilities.

---

#### RES-003-deps: Add `sentence-transformers` dependency + model loading infrastructure

**Status:** ✅ SUPERSEDED by RES-000a — 2026-06-16
**Junior-safe:** N/A — superseded, verification-only.

| Field | Value |
|-------|-------|
| **File** | `requirements.txt` |
| **Priority** | ~~BLOCKER~~ → VERIFICATION-ONLY — RES-000a already added the dependency |
| **Depends on** | RES-046 (MiniLM vs UltraBERT decision), RES-000a (completed) |

**⚠️ SUPERSEDED by RES-000a.** `sentence-transformers>=3.0.0` is already in `requirements.txt`.
This issue is reduced to a verification check only:

**Verification only:**

- `pip install sentence-transformers>=3.0.0` succeeds ✅ (already in requirements.txt)
- `from sentence_transformers import SentenceTransformer; m = SentenceTransformer("all-MiniLM-L6-v2"); print(m.encode("test").shape)` prints `(384,)`

---

#### RES-003-core: Add native-app router with compiled contracts + active-OS gating

**Status:** ✅ DONE — 2026-06-17 (MiniLM dense retrieval integrated into GPS)
**Junior-safe:** ⚠️ MEDIUM — contract compilation, phrase trie, confidence calibration.
**Depends on** RES-003-deps (`sentence-transformers` must be importable)

| Field | Value |
|-------|-------|
| **Files** | `scripts/poc_v2/router.py` (reference implementation), `scripts/poc_v2/contract_compiler.py` (compiled indexes), `scripts/poc_v2/boundary_contracts.py` (per-app contracts) |
| **Priority** | HIGH — blocks native-app routing architecture |
| **Depends on** | RES-003-deps, RES-000a |
| **POC v2 Result** | 80.8% Strict C@1 (120 manual), 75.4% Acceptable C@1 (7.7k generated), 93.1% Acceptable Top-3, 0% leakage, 0 backend fails, 3.5ms/q |

**⚠️ POC v2 CORRECTION:** POC v1 used namespace prior [+0.20 if family.*]. POC v2 proved this is CHEATING. The correct approach is active-OS gating from session context — OS domain comes from the user's active_os_set, not a hardcoded boost. All apps outside the active OS set get score 0.0 (gated BEFORE dense retrieval).

**🔧 EXECUTION NOTES (2026-06-17):**

- Built `search_connectors(action_text, top_k=5, active_os_domains=None)` on GPS — MiniLM-L6 dense retrieval.
- GPS lazy-loads SentenceTransformer on first call; embedding matrix cached; invalidated on connector FTS changes.
- Reads from `connectors_fts` (built by RES-004/005) to construct document text.
- Also fixed a pre-existing bug: `upsert_capability` now auto-populates `domain_id` from connector_id prefix.
- All 20 GPS tests pass. E2E smoketest validates shopping/tasks ranking.

**Implementation — Kernel-grade router:**

```python
def route_to_native_app(
    utterance: str,
    active_os_set: set[str],       # e.g., {"family", "health"}
    ctx: PocContext,                # embedding index + documents
    registry: NativeAppContractRegistry,  # compiled contracts
    *,
    top_k: int = 5,
    use_schema: bool = True,
) -> list[RoutedApp]:
    """No namespace prior. No classifier. No domain facts in router code."""
    # 1. Active-OS gating — apps outside active_os_set get score 0.0
    candidate_ids = {cid for cid, domain in ctx.os_domain_map.items()
                     if domain in active_os_set}

    # 2. Signal extraction — generic, reads compiled indexes
    signals = registry.signal_extractor.extract(utterance)

    # 3. MiniLM dense retrieval — only gated apps
    dense_results = ctx.index.search(utterance, candidate_ids=candidate_ids)

    # 4. Schema scoring — resource/effect/alias overlap, hard veto
    for cid, cosine in dense_results:
        schema = registry.schema_score(cid, signals,
                                       _all_visible_apps=candidate_ids)
        combined = 0.70 * cosine_norm + 0.30 * schema

    # 5. Confidence calibration — margin + confusable-pair graph
    # Returns RoutedApp with confidence, margin, should_force_primary
```

**Key differences from POC v1 RES-003-core:**

| POC v1 | POC v2 |
|--------|--------|
| `search_connectors(action_text)` on GPS | `route_to_native_app(utterance, active_os_set, ctx, registry)` — standalone |
| `namespace prior [+0.20 if family.*]` | Active-OS gating from session context |
| Intent classifier (Stage 0) | Phase 2 (optional, valuable at 50+ apps) |
| V21 schema = classifier predicts app → boost | Real schema = resource/effect/alias from compiled contracts |
| No confidence calibration | margin-based confidence + confusable-pair boost + ambiguity gate |

**Verification:**

- Run: `python scripts/poc_v2/bench_native_app_router.py`
- Manual: `"add eggs to shopping list"` with `active_os_set={"family"}` → top result is `family.shopping`
- Assert: 0 active-OS leakage, 0 backend-name safety fails
- Assert: POC benchmark at 87% Conn@1 with 111 connectors

---

#### RES-004: Add connector FTS indexing during manifest admission

**Status:** ✅ DONE — 2026-06-16

| Field | Value |
|-------|-------|
| **Files** | `k1/fabric/manifest_admission.py` (L106 + `_ingest_connector_fts()`), `k1/fabric/stores/global_projection_store.py` (`connectors_fts` + `upsert_connector_fts_text()`) |
| **Priority** | HIGH |
| **Depends on** | RES-003 (need `search_connectors` first) |
| **Verified** | 2026-06-12: `ManifestAdmissionService.admit()` at L83 calls `_ingest_connector()`, `_ingest_capabilities()`, `_ingest_constitution()`, `_ingest_resource_kinds()`, `_ingest_ontology()`. Insertion point: after `_ingest_ontology()` at L106, add connector text indexing. For the fast path (RES-003), no explicit indexing needed — `search_connectors` queries existing `capabilities_fts` with GROUP BY. For the better path (dedicated `connectors_fts`), add `_ingest_connector_fts_text()` after L106. |

**Change:** When a connector is admitted, build connector search text from:

- connector label + description (from `connectors` table)
- capability names + descriptions (from `capabilities` table, already indexed by FTS5)
- concept aliases (from `concept_aliases` table)
- operation aliases (from `operation_aliases` table)
- resource families (from `connector_resource_families` or `resource_connector_edges`)

**For fast path:** No code change needed — `search_connectors` SQL already JOINs `connectors` + `capabilities_fts`. The existing `_ingest_capabilities()` already populates `capabilities_fts`.
**For better path:** Add `store.upsert_connector_fts_text(connector_id, search_text)` called after `_ingest_capabilities()`.

**Verification:**

- Run: `pytest tests/k1/fabric/test_manifest_admission.py -v`

---

#### RES-005: Add connector FTS indexing during family bootstrap

**Status:** ✅ DONE — 2026-06-16

| Field | Value |
|-------|-------|
| **Files** | `k1/tools/family/registry.py` (L150 `_ingest_connector_fts_for_family()`), `k1/fabric/stores/global_projection_store.py` (`upsert_connector_fts_text()`) |
| **Priority** | HIGH |
| **Depends on** | RES-004 |
| **Verified** | 2026-06-12: `ToolRegistry.register_class()` at registry.py:140 calls `register_definition_to_store(svc.DEFINITION, gps)` which writes ConnectorRecord + CapabilityRecords + ConstitutionRecord + graph edges. The existing `capabilities_fts` is auto-populated via content-sync when capabilities are UPSERTed. For the fast path, no additional work needed. For the better path (dedicated `connectors_fts`), add connector text aggregation after `register_definition_to_store()` returns. |

**Change:**

- Keep capability and constitution writes into GPS (unchanged)
- **Stop** relying on graph writes (`concept_resource_edges`, `resource_connector_edges`) for routing (they're still written but not used by resolver)
- **For fast path:** No code change — the existing FTS5 content-sync already indexes capabilities. `search_connectors` SQL JOINs connectors + capabilities_fts.
- **For better path:** Add `store.upsert_connector_fts_text(connector_id, connector_search_text)` after `register_definition_to_store()` at registry.py:143. Build `connector_search_text` from: definition.title, definition.description, all action names, all action descriptions, concept aliases, operation aliases, resource families.

**Verification:**

- Run: `pytest tests/k1/tools/family/calendar/test_bootstrap_calendar.py -v`
- Manual: After bootstrap, `search_connectors("add eggs to shopping list")` returns `family.shopping` as top result

---

### Epic 1.2: Intent Schema Classifier (Universal Domain Routing)

**Goal:** Fine-tune a lightweight classifier that predicts `(effect, resource_kind, domain_tag)` from a user query. The classifier is trained on synthetic `(query → schema)` pairs — zero dependency on any connector's English prose. Stable across Tesla, Google, Kodi — any compliant developer.

**Status:** ✅ POC VALIDATED — 88% val accuracy, integrated as V21 in POC benchmark.

**POC Results:**

- 17,703 training examples across 20 verticals (FamilyOS + 14 enterprise domains)
- MiniLM-L6 frozen encoder + 3 classification heads (effect 6cls, resource 163cls, domain 80cls)
- Unfrozen top 4 layers: 88% val accuracy (94% effect, 87% resource, 81% domain)
- 28 fresh-query test: 82% effect, 68% domain (85% with synonym merging)
- Model: 286MB saved at `k1/fabric/resolver/intent_classifier/best_model.pt`

---

#### RES-003b: Build Intent Classifier Training Pipeline

**Status:** ✅ COMPLETE

| Field | Value |
|-------|-------|
| **Script** | `scripts/train_intent_classifier.py` |
| **Data** | `scripts/intent_schema_generator.py` — programmatic + Vertex AI generation |
| **Model** | `k1/fabric/resolver/intent_classifier/best_model.pt` |

**What it does:**

1. Generate synthetic `(query → schema_fields)` training pairs via Vertex AI (gemini-2.5-flash-lite)
2. Train MiniLM-L6 with 3 parallel classification heads
3. Output: effect (94% acc), resource_kind (87% acc), domain_tag (81% acc)

**Why schema-level, not doc-level training:**

- Tesla writes "activate climate pre-conditioning" — not "create calendar event"
- The classifier maps "schedule charging" → `{effect: create, domain: vehicle}` regardless of Tesla's prose
- Training data is unlimited synthetic pairs — zero dependency on third-party connector docs

---

#### RES-003c: Integrate Schema Scoring into Connector Resolver

**Status:** ✅ POC VALIDATED (V21 SchemaAugmentedSearch)

**Architecture:**

```
query → intent classifier (3ms)
      → {effect, resource_kind, domain_tag, confidence}
      → schema_score[cid] += effect_boost * domain_confidence  (if connector.domain matches)
      → dense_score[cid] = cosine(query_emb, doc_emb[cid])
      → final[cid] = 0.4*schema + 0.4*dense + 0.2*namespace
      → sort
```

**Key design rule:** Schema scores are soft boosts, NEVER hard filters. Wrong classifier output = less boost, not elimination. Confidence-weighted: low confidence (<0.72) → lean on dense retrieval more heavily.

**POC result:** V21 = V11b (87%) on FamilyOS-only. V21 WINS on multi-domain — correctly routes "schedule charging" → Tesla not Calendar, "send invoice" → Stripe not Tasks.

---

### Epic 1.3: Systematic Connector Document Structure

**Goal:** Build connector documents for embedding quality using ONLY developer-provided fields (title, description, action names, domain tags, concept aliases, resource families). No hand-crafted enrichment. Fully automated. Scales to 7,000+ connectors.

**Status:** ✅ POC VALIDATED — Document structure rules proven at 111 connectors.

**POC-proven document structure rules:**

1. Title anchor repeated 3x — dominates MiniLM's positional mean pooling
2. Boundary fields (use_when, not_when, boundary_notes) — positioned early for high weight
3. Effect taxonomy — derived from action names ("add_" → create, "check_off" → complete)
4. Developer's description — their own words
5. Action names — strongest query→document bridge
6. Domain vocabulary — tags + concept aliases
7. Action descriptions — first sentence only, max 8, avoids noise dilution
8. Closing namespace anchor — repeated at end

**Design constraint:** No per-connector enrichment. Every connector gets the SAME structure. The structure is designed to maximize embedding signal from whatever text the developer wrote.

---

## Milestone 2: Gut the Old Type Resolver

### Epic 2.1: Delete graph traversal from runtime routing

**Goal:** `CapabilityTypeResolver` should no longer be the brain. The graph priest is fired.

---

#### RES-006: Delete 4-step graph traversal path

**Status:** ✅ DONE — 2026-06-17

| Field | Value |
|-------|-------|
| **File** | `k1/fabric/resolver/capability_type_resolver.py` (class renamed, graph methods deleted, new MiniLM resolve()) |
| **Priority** | HIGH |
| **Depends on** | RES-003 (`search_connectors` must exist) |
| **Verified** | 2026-06-12: All 4 methods confirmed at exact lines. |

**🔧 EXECUTION NOTES (2026-06-17):**

- Executed together with RES-007a. File reduced from ~650 lines to 179 lines.
- **Deleted:** `_resolve_one()`, `_resolve_operation()`, `_resolve_concept()`, `_extract_concept_from_action()`, `_STOP_WORDS`, `_WRITE_OPERATIONS`, `_READ_OPERATIONS`, all knobs (`_domain_mode`, `_rf_mode`, `_op_mode`, `_search_method`, `_query_mode`, `_index_content`, `_retrieval_backend`, `_embedding_index`).
- **Kept:** `UNIVERSAL_OPERATION_ALIASES` (imported by `manifest_admission.py:21` for effect classification — will migrate later). `ResolvedIntentType` (imported by `situated_resolver.py`, `capability_binder.py`, `policy/selector.py` — marked DEPRECATED, removal in RES-007b/010/013).
- **⚠️ BREAKING:** `CapabilityTypeResolver` class no longer exists. Importers (`factory.py:1067`, `situated_resolver.py:25`) will fail until RES-007b is applied.

**Hard delete — NO flag, NO fallback:**

- `_resolve_operation()` (L532) — universal alias lookup + graph table fallback + first-word extraction
- `_resolve_concept()` (L567) — concept_aliases table traversal + action text word splitting
- `_extract_concept_from_action()` — multi-word phrase fallback extraction
- `_resolve_one()` (L163) — 4-step graph walk orchestrator (op → concept → resource_family → capability)
- `UNIVERSAL_OPERATION_ALIASES` dict (L48) — 48 hardcoded verb mappings (no longer used; text search handles this)
- `_STOP_WORDS` set (L28) — concept extraction stop words
- `_WRITE_OPERATIONS` / `_READ_OPERATIONS` sets — operation classification
- `ResolvedIntentType` dataclass (L95) — implicit deletion; no production consumers after this file is gutted

**Why:** Wrong LLM hints for domain/resource/operation are the root failure — graph finds wrong results with high confidence. Text search (FTS5 + embeddings) replaces all of this.

**Verification:**

- File compiles without these methods
- No imports reference them from other modules
- `ResolvedIntentType` not imported in production code outside this file

---

#### RES-007a: Rename `CapabilityTypeResolver` → `ConnectorResolver`, replace `resolve()` internals

**Status:** ✅ DONE — 2026-06-17
**Junior-safe:** ⚠️ MEDIUM — single file, but core class rename + new return type.
| Split from:** RES-007 (original).  This is the class-level change only.  Caller updates are in RES-007b.

| Field | Value |
|-------|-------|
| **File** | `k1/fabric/resolver/capability_type_resolver.py` (L107 class, L150 `resolve()`) |
| **Priority** | HIGH |
| **Depends on** | RES-003-core (GPS `search_connectors` must exist), RES-006 (graph methods deleted) |

**What this does (single-file changes):**

1. Rename class `CapabilityTypeResolver` → `ConnectorResolver`.
2. Add `RankedConnectorSet` dataclass (new, in same file).
3. Replace `resolve()` — old: `resolve(frame, universe) -> list[ResolvedIntentType]` → new: `resolve(action_text, context_hints=None) -> RankedConnectorSet`.
4. Change constructor: `__init__(self, global_store: GlobalProjectionStore)` — no more `local_store` dependency.

**🔧 EXECUTION NOTES (2026-06-17):**

- Done together with RES-006. `ConnectorResolver.resolve()` calls `self.gps.search_connectors(action_text, top_k=5, active_os_domains=...)`.
- `RankedConnectorSet.primary` is `dict[str, Any] | None` (not a named dataclass — returns the GPS hit dict directly: `{connector_id, label, domain_id, score}`).
- `context_hints` accepts optional `active_os_domains` list for session-aware gating.
- `ResolvedIntentType` kept (DEPRECATED) for backward compat with situated_resolver, capability_binder, policy/selector.
- E2E validated: "add eggs to my shopping list" → family.shopping (0.50), "remind me to finish homework" → family.tasks (0.30).

**⚠️ What this does NOT touch:** Factory wiring (`factory.py`), `situated_resolver.py` callers — those are RES-007b.

**Verification:**

- `python -c "from k1.fabric.resolver.capability_type_resolver import ConnectorResolver; print('import ok')"` succeeds
- `RankedConnectorSet` is importable from the same module

---

#### RES-007b: Update factory + situated_resolver callers for `ConnectorResolver`

**Status:** ✅ DONE — 2026-06-17
**Junior-safe:** ⚠️ MEDIUM — 2 files, but clear import/wiring changes only.
| Split from:** RES-007 (original).  Depends on RES-007a (class must be renamed first).

| Field | Value |
|-------|-------|
| **Files** | `k1/fabric/factory.py` (L1067 import, L1090 instantiation, L1105 wiring), `k1/fabric/resolver/situated_resolver.py` (L459 call site) |
| **Priority** | HIGH |
| **Depends on** | RES-007a |

**Factory changes (factory.py):**

- L1067: `from k1.fabric.resolver.capability_type_resolver import ConnectorResolver`
- L1090: `connector_resolver = ConnectorResolver(global_projection_store)`
- L1105: `connector_resolver=connector_resolver,`

**situated_resolver.py changes:**

- Constructor parameter: accept `connector_resolver` instead of `type_resolver`
- L459: Replace `type_resolver.resolve(frame, universe)` call with:

```python
action_text = frame.intents[0].action if frame.intents else ""
connector_hits = self.connector_resolver.resolve(action_text)
```

**🔧 EXECUTION NOTES (2026-06-17):**

- factory.py: import changed, `ConnectorResolver(global_projection_store)` (dropped local_store), wiring param renamed `connector_resolver=`.
- situated_resolver.py: import + constructor param + assignment updated. Knob configuration (`self.type_resolver._domain_mode` etc.) DELETED — ConnectorResolver has no knobs. Embedding index setup (K11 block) DELETED — GPS handles embeddings internally.
- `configure()` still sets `self.capability_binder._return_mode` (unchanged).
- `resolve()` sets `intent_types = []` as placeholder — downstream policy/binder/verdict cascade still expects `list[ResolvedIntentType]`. These will be rewired in RES-010 + RES-012a.
- Imports verified clean for factory + situated_resolver.

**Verification:**

- Run: `pytest tests/k1/fabric/test_factory.py -v`
- Run: `pytest tests/k1/fabric/resolver/test_situated_resolver.py -v` (update tests per RES-027)
- Manual: `connector_resolver.resolve("add eggs to shopping list")` returns `family.shopping` as primary

---

#### RES-008: Remove runtime calls to `lookup_capability_by_type()`

**Status:** ✅ DONE — 2026-06-17 (no-op: all call sites deleted by RES-006)

| Field | Value |
|-------|-------|
| **Files** | `k1/fabric/stores/global_projection_store.py` (L1460 definition), `k1/fabric/resolver/capability_type_resolver.py` (L272, L282, L308 — all call sites in `_resolve_one()`) |
| **Priority** | HIGH |
| **Depends on** | RES-007 (RES-006 already deletes all call sites) |
| **Verified** | 2026-06-12: ALL production call sites are in `capability_type_resolver.py._resolve_one()` — deleted by RES-006. Zero external production consumers. Test call sites exist at `test_global_projection_store.py:432`, `test_family_phase11_projection.py:138,143,238`. Script call at `probe_fabric_api.py:271`. Method definition at GPS L1460 can remain for offline diagnostics or be deleted. |

**Hard delete from runtime path:**

- `lookup_capability_by_type()` — ALL call sites already deleted by RES-006
- `capability_type_index` table dependency in resolver path — no longer queried

**Keep only if:** Some offline diagnostic needs it. Otherwise delete the table migration too. Since RES-006 deletes all call sites, this RES is effectively a NO-OP for production code — the method becomes dead code in GPS. Remove or keep for offline use.

**Verification:**

- Grep: `lookup_capability_by_type` only appears in GPS definition (L1460) + tests + scripts
- No resolver code calls it after RES-006
- Tests at `test_global_projection_store.py` + `test_family_phase11_projection.py` updated or deleted per RES-027

**Verification:**

- Grep: `lookup_capability_by_type` only appears in store definition (for offline use) or tests
- No resolver code calls it

---

## Milestone 3: Remove Binder-Based Tool Picking

### Epic 3.1: Stop resolver from selecting one capability

**Goal:** Resolver picks connector. Back picks tool.

---

#### RES-009: Delete `_select_best_capability()` from routing

**Status:** ✅ DONE — 2026-06-17

| Field | Value |
|-------|-------|
| **File** | `k1/fabric/resolver/capability_binder.py` (L694 module-level function, called at L314 + L330 in `bind()`) |
| **Priority** | HIGH |
| **Depends on** | RES-007 (connector search replaces it) |
| **Verified** | 2026-06-12: Module-level function at L694. Called in `bind()` at L314 (K5 `all-tools-for-connector` path — used to find `connector_id` for expansion) and L330 (primary binding — used to find best capability). Also implicitly deletes `UNIVERSAL_ACTION_MAP` (L42) which maps verbs to `(invocation_mode, effect)` — no longer needed; tool records have these fields natively. |

**Hard delete — NO flag:**

```python
def _select_best_capability(          # L694 — DELETE ENTIRE FUNCTION
    caps: list[CapabilityRecord],
    operation: str | None = None,
    action_text: str | None = None,
) -> CapabilityRecord:
```

**Also delete:**

- `UNIVERSAL_ACTION_MAP` dict (L42) — 8 hardcoded verb→(mode,effect) mappings. Tools carry `invocation_mode` + `effect` natively now.
- `_WRITE_EFFECTS` set (L51) — effect classification. Back reads effect from `tools[]`.
- `_GENERIC_ACTIONS` set (L727, inside function) — generic action name filtering. Back picks tool by description, not action_name heuristics.

**Why:** Heuristic fails 65% of queries. `"add eggs"` + `op_hint="create"` → `create_list` wins over `add_item`. After RES-010, Back picks the tool from 10-15 described tools — no heuristic needed.

**Verification:**

- File compiles without this function
- No imports reference it (module-level, only called in `bind()` within same file)
- `UNIVERSAL_ACTION_MAP` not imported elsewhere

---

#### RES-010: Replace binder output with all tools for selected connector

**Status:** ✅ DONE — 2026-06-17

| Field | Value |
|-------|-------|
| **Files** | `k1/fabric/resolver/capability_binder.py` (L179 class, L199 `bind()`), **`k1/fabric/resolver/situated_resolver.py`** (L468 `binding_bundle = self.capability_binder.bind(...)`), `k1/fabric/stores/global_projection_store.py` (L907 `get_capabilities_by_connector()`) |
| **Priority** | HIGH |
| **Depends on** | RES-007 (ConnectorResolver), RES-009 |
| **Verified** | 2026-06-12: `bind()` at L199 takes `resolved_intents: list[ResolvedIntentType]` — after RES-007, this is replaced by `connector_hits: RankedConnectorSet`. `get_capabilities_by_connector()` at GPS L907 exists and works. ⚠️ Coherence: `bind()` signature must change from `resolved_intents` → `connector_hits`. |

**⚠️ COHERENCE — New `bind()` signature:**

```python
def bind(
    self,
    connector_hits: RankedConnectorSet,  # ← REPLACES resolved_intents
    *,
    actor_id: str,
    session_id: str,
    constitution_loader: ConstitutionLoader | None = None,
) -> tuple[list[CapabilityRecord], ConstitutionArtifact | None]:
```

**New behavior:**

```python
primary_connector = connector_hits.primary
if primary_connector is None:
    return [], None

# Get ALL tools for the matched connector (10-15 tools)
tools = self.global_store.get_capabilities_by_connector(
    primary_connector.connector_id
)

# Load constitution teaching surface
constitution = None
if constitution_loader is not None:
    constitution = constitution_loader.load(primary_connector.connector_id)

return tools, constitution
```

**What gets deleted from `bind()`:**

- 3-pass discovery loop (`for candidate in candidates`) — L220-390
- K5 `all-tools-for-connector` path — L310-325 (replaced by direct `get_capabilities_by_connector()`)
- `_select_best_capability()` calls — L314, L330 (deleted by RES-009)
- `_make_binding()` calls — L332, L349 (no more `CapabilityBinding` objects needed)
- `_bind_constitution_roles()` call — L377-390 (constitution becomes advisory teaching surface, not binding roles)
- `_mode_effect()` — L247 (invocation_mode/effect now from CapabilityRecord directly)
- `_find_all_capabilities()` — L454 (3-pass discovery replaced by connector search)
- Synthetic candidate creation — L222-243 (no more resource universe needed)

**What stays (simplified):** Single method: `connector_hits` → `get_capabilities_by_connector()` → `constitution_loader.load()` → return `(tools, constitution)`.

**situated_resolver.py update (L468):**

```python
# OLD: binding_bundle = self.capability_binder.bind(intent_types, universe, policy_bundle, ...)
# NEW:
tools, constitution = self.capability_binder.bind(
    connector_hits,
    actor_id=request.actor_id,
    session_id=request.session_id,
    constitution_loader=self.constitution_loader,
)
```

**Verification:**

- `get_capabilities_by_connector()` returns all tools for a connector
- Tools include descriptions and input schemas from `CapabilityRecord`
- `constitution_loader.load()` returns teaching-surface constitution

---

#### RES-011: Remove `BindingBundle` from the Back-facing path

**Status:** ✅ DONE — 2026-06-17

| Field | Value |
|-------|-------|
| **Files** | `k1/fabric/resolver/situated_resolver.py` (L94 envelope field, L468 `bind()` call, L480 constitution load, L498 envelope construction), `k1/fabric/prompt_pack/builder.py`, `k1/fabric/resolver/capability_binder.py` (L103 `BindingBundle` class, L57 `CapabilityBinding`, L92 `UnboundRole`, L169 `ToolSelectionCommit`) |
| **Priority** | MEDIUM |
| **Depends on** | RES-010 |
| **Verified** | 2026-06-12: `BindingBundle` is defined at capability_binder.py L103, returned by `bind()` at L199, stored in `ResolutionEnvelope.binding_bundle` at L94, used at L480 to load constitution from `binding_bundle.primary.connector_id`. After RES-010, constitution is loaded directly from `connector_hits.primary.connector_id` — no `BindingBundle` needed. Zero external production consumers. |

**⚠️ COHERENCE — situated_resolver.py L480 must change:**

```python
# OLD (L480):
constitution = self.constitution_loader.load(binding_bundle.primary.connector_id)

# NEW:
constitution = connector_constitution  # already loaded by RES-010's bind() call
```

**Implicitly deleted dataclasses (all in capability_binder.py):**

- `BindingBundle` (L103) + `to_dict()` (L139) + `all_bindings` property (L118) + `allowed_capability_names` property (L128) + `capability_name_to_binding` property (L132)
- `CapabilityBinding` (L57) — 27-field dataclass for individual bound capabilities
- `UnboundRole` (L92) — failed binding representation
- `ToolSelectionCommit` (L169) — post-selection validation

**`ResolutionEnvelope` fields removed (situated_resolver.py):**

- L94: `binding_bundle: BindingBundle | None`
- L141: `"binding_bundle": self.binding_bundle.to_dict() if self.binding_bundle else None` (in `to_dict()`)

**Verification:**

- `ResolutionEnvelope` has no `binding_bundle` field
- Back prompt references `tools[]` and `constitution`, not `binding_bundle.primary`
- L480 uses `connector_hits.primary.connector_id` not `binding_bundle.primary.connector_id`
- All 4 dataclasses (`BindingBundle`, `CapabilityBinding`, `UnboundRole`, `ToolSelectionCommit`) compilable for removal

---

### Epic 3.2: Session-Aware Dynamic Tool Schema Injection

**Goal:** When a connector's tools have `backend_id`-style enums, those enum values must be dynamically populated from LPS (LocalProjectionStore) at resolution time — reflecting which backends are actually connected in this user's session. The resolver injects live enum values into tool schemas before the envelope reaches Back.

**Context (from architecture design 2026-06-14):**

The `family.shopping.place_order` tool has a `backend_id` field with enum `["walmart-api", "target-api", "samsclub-api"]`. These are NOT hardcoded — they come from which backends the user has connected in their FamilyOS shopping app. If a user only has Walmart and Sam's Club connected, the enum should be `["walmart-api", "samsclub-api"]`. If they later add Target, it becomes `["walmart-api", "target-api", "samsclub-api"]`.

This is a **resolution-time injection**: the resolver queries LPS for the session's `connected_resources`, filters to the connector's registered backends, and populates the enum before returning the envelope to Back. Back LLM then maps natural language ("order on Target") → the correct enum value ("target-api").

**⚠️ CRITICAL BOUNDARY — LPS Write Path Is NOT Part of This Redesign:**

The resolver is an **LPS reader**, never an LPS writer. The data flow is:

```
USER opens FamilyOS shopping app
  → taps "Connect Walmart" → OAuth flow completes
  → NATIVE FAMILYOS APP INBOUND API writes to LPS:
      session_id=X, connector_id="family.shopping",
      connected_resources=[{backend_id:"walmart-api", label:"Walmart"}]
  → LPS now has: session X has walmart-api connected

LATER:
  USER says "order eggs from Walmart"
  → Back calls resolve_situation(action_text=...)
  → RESOLVER READS LPS (RES-011b):
      lps.get_connected_resources(session_id, "family.shopping")
      → returns [{backend_id:"walmart-api", label:"Walmart"}]
  → Resolver injects enum: ["walmart-api"] into place_order.backend_id
  → Back sees enum: ["walmart-api"], enum_labels: ["Walmart"]
  → Back maps "Walmart" → backend_id="walmart-api"
```

**The LPS write path is owned by the native FamilyOS app inbound API — a completely separate code path from the resolver.** The native app's inbound API handles OAuth token storage, backend connection CRUD, and LPS population. The resolver redesign migration plan (M0–M11) does NOT touch this code. The resolver only adds a READ from LPS — a query against `connected_resources` filtered by `session_id` + `connector_id`. If that read returns nothing (no backends connected, or LPS unavailable), the resolver returns tools with empty enums.

**What the native app inbound API owns (NOT in this plan):**

- User taps "Connect Walmart" → OAuth2 flow → token storage
- Writes to LPS: `INSERT INTO connected_resources (session_id, connector_id, backend_id, label, ...)`
- User taps "Disconnect Target" → removes from LPS
- Backend connection CRUD UI

**What the resolver owns (IN this plan — RES-011b):**

- Reads LPS: `SELECT backend_id, label FROM connected_resources WHERE session_id=? AND connector_id=?`
- Intersects with GPS `connector_backends` (which backends the connector CAN support)
- Injects live enum values into tool schemas before envelope construction

---

#### RES-011b: Add session-aware dynamic enum injection for tool schemas

**Status:** ✅ DONE — 2026-06-17

| Field | Value |
|-------|-------|
| **Files** | `k1/fabric/resolver/situated_resolver.py` (post-RES-010 tool assembly), `k1/fabric/stores/local_projection_store.py` (LPS `connected_resources` — **READ ONLY, no write path changes**), `k1/fabric/stores/global_projection_store.py` (connector backend registry — GPS `connector_backends` table) |
| **Priority** | HIGH — required for multi-backend connectors (shopping, food, money) |
| **Depends on** | RES-010 (tools fetched for connector), RES-002 (envelope shape) |
| **Does NOT touch** | Native FamilyOS app inbound API (LPS write path), OAuth flows, backend connection CRUD |

**What this does:**

After RES-010 fetches `tools = get_capabilities_by_connector(connector_id)`, and before building the `ResolutionEnvelope`, the resolver inspects each tool's `required_inputs` and `optional_inputs` for fields with a special marker indicating they need session-aware enum injection.

**Design — LPS-backed dynamic enums:**

```python
# In tool schema (as registered in GPS):
{
    "capability_name": "tool.execute.shopping.place_order",
    "required_inputs": [
        {"name": "backend_id", "type": "string",
         "enum_source": "lps.connected_backends",  # ← MARKER: dynamic enum
         "enum_filter": {"connector_id": "family.shopping"}},
        {"name": "items", "type": "array", ...}
    ]
}
```

**Resolution-time injection logic:**

```python
async def _inject_session_aware_enums(
    self,
    tools: list[CapabilityRecord],
    session_id: str,
    connector_id: str,
) -> list[CapabilityRecord]:
    """Populate dynamic enum values from LPS connected backends."""
    # Query LPS for this session's connected backends
    connected = await self.lps.get_connected_resources(
        session_id=session_id,
        connector_id=connector_id,
    )
    # connected = [{"backend_id": "walmart-api", "label": "Walmart", ...},
    #              {"backend_id": "samsclub-api", "label": "Sam's Club", ...}]

    backend_ids = [r["backend_id"] for r in connected]
    backend_labels = [r["label"] for r in connected]

    for tool in tools:
        for inp in tool.required_inputs + tool.optional_inputs:
            if inp.get("enum_source") == "lps.connected_backends":
                # Replace the static placeholder with live session data
                inp["enum"] = backend_ids
                inp["enum_labels"] = backend_labels  # For Back LLM readability
                # If no backends connected, mark as unavailable
                if not backend_ids:
                    inp["enum"] = ["__no_connected_backends__"]
                    inp["description"] += (
                        " (No backends connected. User must connect a backend "
                        "in the shopping app first.)")
    return tools
```

**Alternative — `$dynamic_enum` schema extension:**

A more declarative approach using JSON Schema `$dynamic_enum` extension:

```python
# In GPS, the tool declares:
"backend_id": {
    "type": "string",
    "$dynamic_enum": {
        "source": "lps",
        "table": "connected_resources",
        "key_field": "backend_id",
        "label_field": "label",
        "filter": {"connector_id": "$parent.connector_id"}
    }
}

# Resolver resolves $dynamic_enum → concrete enum at envelope-build time:
"backend_id": {
    "type": "string",
    "enum": ["walmart-api", "target-api", "samsclub-api"]
}
```

**Phase 1 implementation (simpler, recommended):**

1. Add `enum_source` field to input schemas in GPS for tools that need dynamic enums
2. In `situated_resolver.py`, after RES-010's tool fetch, call `_inject_session_aware_enums(tools, session_id, connector_id)`
3. LPS already has `connected_resources` table — query it by `session_id` + `connector_id`
4. If LPS is unavailable (stateless mode), return the tools with empty enums + a warning in `constitution.when_to_ask_human`

**GPS schema addition — connector backend registry:**

```sql
-- New table in GPS: connector_backends
CREATE TABLE IF NOT EXISTS connector_backends (
    connector_id TEXT NOT NULL,
    backend_id TEXT NOT NULL,        -- e.g., "walmart-api"
    backend_label TEXT NOT NULL,     -- e.g., "Walmart"
    schema_version TEXT,
    registered_at TEXT,
    PRIMARY KEY (connector_id, backend_id)
);
```

This table registers which backends a connector CAN support. LPS `connected_resources` records which backends ARE connected for a given session. The intersection (connector_backends ∩ connected_resources) = the live enum.

**What this enables for Back LLM:**

```
# Back sees (after injection):
tools[3] = {
    capability_name: "tool.execute.shopping.place_order",
    description: "Place an order at a specific retailer backend",
    required_inputs: [
        {name: "backend_id", type: "string",
         enum: ["walmart-api", "target-api", "samsclub-api"],
         enum_labels: ["Walmart", "Target", "Sam's Club"]},
        {name: "items", type: "array", ...}
    ]
}

# Back maps: "order on Target" → backend_id="target-api"
# Back maps: "buy from Walmart" → backend_id="walmart-api"
```

**Verification:**

- Run: `pytest tests/k1/fabric/resolver/test_session_aware_enums.py -v` (new)
- Assert: `place_order` tool's `backend_id.enum` = `["walmart-api", "samsclub-api"]` when those 2 are connected
- Assert: `backend_id.enum_labels` = `["Walmart", "Sam's Club"]`
- Assert: When zero backends connected, `enum` = `["__no_connected_backends__"]` and description updated
- Assert: Tools WITHOUT `enum_source` marker are unchanged

---

#### RES-011c: Add LPS `get_connected_backends(session_id, connector_id)` method

**Status:** ✅ DONE — 2026-06-17
**Junior-safe:** ✅ Single method on LPS, well-specified query, no write path changes.
| New issue — extracted from RES-011b dependency.  Depends on RES-000d (LPS schema migration).

| Field | Value |
|-------|-------|
| **Files** | `k1/fabric/stores/local_projection_store.py` (new method) |
| **Priority** | HIGH — RES-011b cannot inject dynamic enums without this |
| **Depends on** | RES-000d (LPS schema must have `backend_id`, `session_id` columns) |

**What this does:**

Add a new read-only method to LPS:

```python
def get_connected_backends(
    self,
    session_id: str,
    connector_id: str,
) -> list[dict]:
    """Return backends connected for this session + connector.

    Returns list of {backend_id, label, status}.
    Used by RES-011b to populate dynamic enums on tool schemas.
    """
    rows = self._db.execute(
        """
        SELECT DISTINCT backend_id, label, status
        FROM connected_resources
        WHERE session_id = ? AND connector_id = ? AND status = 'active'
        """,
        (session_id, connector_id),
    ).fetchall()
    return [dict(r) for r in rows]
```

**⚠️ This is a READ-ONLY method.** The LPS write path (native FamilyOS app inbound API) is NOT part of this issue.

**Verification:**

- Run: `pytest tests/k1/fabric/stores/test_local_projection_store.py -v -k connected`
- Empty result when no backends connected
- Returns `[{backend_id, label, status}]` when backends are connected

---

## Milestone 4: Simplify Verdict Logic

### Epic 4.1: Kill blocking verdict cascade

**Goal:** Resolver never blocks. It returns tools and advice. Back/HIL handles execution decisions.

---

#### RES-012a: Replace `_determine_verdict()` 13-step cascade with always-`can_execute`

**Status:** ✅ DONE — 2026-06-17
**Junior-safe:** ✅ Single method replacement — replace 90-line cascade with 1-line return.
| Split from:** RES-012 (original).  This is the verdict change only.  Dead helper cleanup is RES-012b.

| Field | Value |
|-------|-------|
| **File** | `k1/fabric/resolver/situated_resolver.py` (L544 `_determine_verdict()`) |
| **Priority** | HIGH |
| **Depends on** | RES-007 (connector search replaces old routing), RES-010 (binder simplified) |
| **Verified** | 2026-06-12: All 13 steps confirmed at L559–635. |

**13-step cascade (all at L559–635 — fate of each):**

| Step | Line | Old Verdict | Fate |
|------|------|-------------|------|
| 1. Budget exhausted | L559 | `cannot_execute` | DELETE — Back manages its own budget |
| 2. Idempotency duplicate | L563 | `cannot_execute` | DELETE — moved to invoke_capability (RES-014) |
| 3. Ambiguous person | L569 | `needs_disambiguation` | BYPASS — return alternatives, let Back decide |
| 4. Stale projection | L573 | `stale_projection` | DELETE — no LPS-based resource projection after RES-035 |
| 5. Unresolved ambiguous | L579 | `needs_disambiguation` | BYPASS — return alternatives |
| 6. Unresolved not_found | L584 | `missing_required_params` | DELETE — no resource universe after RES-035 |
| 7. Intent too vague | L589 | `missing_required_params` | BYPASS — text search handles vague queries |
| 8. Promote to Tier 3 | L593 | `promote_to_tier3` | DELETE — no tier promotion from resolver |
| 9. Policy denied | L598 | `blocked_by_policy` | BYPASS — policy becomes advisory (RES-013) |
| 10. Stale binding | L602 | `stale_projection` | DELETE — no bindings to go stale after RES-011 |
| 11. Missing capability | L607 | `missing_capability` | DELETE — never block; return alternatives + warning |
| 11b. No viable bindings | L618 | `missing_capability` | DELETE — same; return alternatives |
| 12. Incomplete prereqs | L627 | `can_execute_with_gate` | BYPASS — advisory in constitution.how_to_sequence |
| 13. HIL gate | L632 | `needs_hil` | BYPASS — advisory in constitution.when_to_ask_human |

**New behavior (single line):**

```python
def _determine_verdict(self, ...) -> tuple[str, str | None]:
    return "can_execute", None  # ALWAYS — never blocks
```

The old 90-line body is deleted.  All 13 checks are removed.  Post-RES-012b will delete the dead helpers.

**Verification:**

- Run: `pytest tests/k1/fabric/resolver/test_situated_resolver.py -v -k verdict`
- Assert: verdict is always `"can_execute"` for any input
- Assert: `_determine_verdict()` is exactly a one-liner

---

#### RES-012b: Delete dead helper functions after verdict cascade removal

**Status:** ✅ DONE — 2026-06-17
**Junior-safe:** ✅ Deletions only — remove dead code, no new logic.
| Split from:** RES-012 (original).  Depends on RES-012a (cascade must be replaced first).

| Field | Value |
|-------|-------|
| **File** | `k1/fabric/resolver/situated_resolver.py` (L658–750+) |
| **Priority** | MEDIUM |
| **Depends on** | RES-012a |

**Dead methods to delete (all in `situated_resolver.py`):**

| Method | Line | Why dead |
|--------|------|----------|
| `_allowed_next_actions()` | L658–710 | Branched on verdict; simplified to return all tools for matched connector |
| `_hil_request()` | L712–740 | Branched on `needs_disambiguation`/`needs_hil`; HIL now advisory in constitution |
| `_recovery_directive()` | L750+ | Branched on verdict; dead after cascade removal |
| `_budget_exhausted_field()` | helper | Dead — budget check removed |
| `_first_ambiguous_person()` | helper | Dead — ambiguity check removed |
| `_intent_too_vague()` | helper | Dead — vagueness check removed |
| `_should_promote_to_tier3()` | helper | Dead — tier promotion removed |
| `_incomplete_prerequisite()` | helper | Dead — prerequisite check moved to constitution |
| `_hil_gate_triggered()` | helper | Dead — HIL gate moved to constitution |

**What to KEEP:** `_determine_verdict()` (now a one-liner from RES-012a).

**Verification:**

- File compiles without these functions
- Grep: none of the deleted function names appear elsewhere in `situated_resolver.py`
- No imports reference them from other modules

---

#### RES-013: Convert policy from gate to advisory

**Status:** ✅ DONE — 2026-06-17 (PolicySelectorService removed from resolver pipeline; class retained for fabric.py attribute)

| Field | Value |
|-------|-------|
| **Files** | `k1/fabric/policy/selector.py` (L98 `PolicySelectorService`, L100 `select()`, L66 `PolicyBundle`), **`k1/fabric/resolver/situated_resolver.py`** (L468 `policy_bundle = self.policy_selector.select(...)`) |
| **Priority** | MEDIUM |
| **Depends on** | RES-012 |
| **Verified** | 2026-06-12: `PolicySelectorService.select()` at L100 returns `PolicyBundle` with `policy_verdict` field that can be `"deny"`, `"needs_hil"`, `"allow_with_gate"`, or `"allow"`. `_determine_verdict` step 9 (L598) checks `policy_bundle.policy_verdict == "deny"` → `"blocked_by_policy"`. After RES-012 deletes step 9, `PolicyBundle.policy_verdict` is unused. ⚠️ Coherence: `PolicySelectorService` imports `ResolvedIntentType` + `ResourceUniverse` — both deleted by RES-006 + RES-035. |

**⚠️ COHERENCE — `select()` signature change:**

```python
# OLD:
def select(self, resource_universe: ResourceUniverse,
           intent_types: list[ResolvedIntentType],
           actor_role: str, safety_band: str) -> PolicyBundle:

# NEW (after RES-007 + RES-035):
def select(self, connector_id: str, actor_role: str,
           safety_band: str) -> PolicyBundle:
```

**Change:** Policy never denies in resolver. Returns advisory notes surfaced in constitution:

```python
PolicyBundle(
    ...
    policy_verdict="allow",  # ALWAYS — never deny
    gates=[...],  # Advisory gates, surfaced to Back as policy_advice
    ...
)
```

**Where policy advice goes:** Appended to `constitution` in the new `ResolutionEnvelope`:

```python
"policy_advice": [
    {
        "kind": "human_approval",
        "reason": "Irreversible financial action",
        "recommended_action": "ask_human"
    }
]
```

**Factory wiring (factory.py L1091, L1104):** `PolicySelectorService` stays wired but its output is advisory-only. `policy_selector` parameter on `ResolveSituationService` stays for backward compat; the verdict cascade just ignores the deny.

**Verification:**

- `PolicySelectorService.select()` returns `policy_verdict="allow"` always
- No `policy_verdict == "deny"` in resolver path
- `policy_advice` appears in constitution teaching surface

---

#### RES-014: Keep idempotency outside resolver routing

**Status:** ✅ DONE — 2026-06-17 (idempotency_store removed from ResolveSituationService constructor + factory wiring)

| Field | Value |
|-------|-------|
| **Files** | `k1/fabric/stores/idempotency_store.py` (L26 class, L71 `check()`), `k1/fabric/resolver/situated_resolver.py` (L563 step 2), `k1/concierge/tools/implementations.py` (execution path) |
| **Priority** | MEDIUM |
| **Depends on** | RES-012 |
| **Verified** | 2026-06-12: `IdempotencyStore.check()` at L71 returns `IdempotencyCheckResult` with state `"not_seen"`, `"in_flight"`, `"succeeded"`, `"failed"`. Called at `_determine_verdict` step 2 (L563): `if self.idempotency_store.check(key).state == "succeeded": return "cannot_execute"`. After RES-012 deletes step 2, idempotency is no longer checked in the resolver. Factory wires `idempotency_store` to `ResolveSituationService` at L1109 — parameter becomes dead. RES-024 removes it. |

**Decision:** Resolver should not say "cannot execute" because of duplicate. `invoke_capability` or execution provider enforces idempotency at mutation time.

**Where idempotency moves to (execution path):**

- `k1/concierge/tools/implementations.py`: `execute_invoke_capability()` calls `ctx.dispatch.dispatch_direct(CapabilityRequest)` → `FabricDispatchAdapter.dispatch_direct()` → `fabric.execute(request)`.
- The `fabric.execute()` path MAY check `idempotency_store.check(key)` as a mechanical concern — but MUST NOT block execution.
- **⚠️ CORRECTION (2026-06-12):** Per the "No Hidden Vetoes" principle (see audit below), idempotency is a MECHANICAL transparency, not a gate. If a duplicate is detected, the executor returns the PRIOR RESULT transparently — Back sees "this was already done, here's the prior outcome." The executor NEVER says "cannot execute because duplicate."

**Allowed executor checks (v1 — mechanical only):**

1. `capability_name` exists in registry ✅
2. `params` are valid JSON/dict ✅
3. Required params are present ✅
4. Tool implementation does not crash ✅
5. Return transparent error if invocation fails ✅

**NOT allowed in v1 executor:**

1. Policy deny ❌
2. Hidden HIL requirement ❌
3. Idempotency duplicate BLOCK ❌ (return prior result instead)
4. Permission maze ❌
5. Effect-based mutation refusal ❌
6. "Constitution says ask human so executor refuses" ❌

**What changes:**

- **situated_resolver.py**: Delete `self.idempotency_store` attribute + step 2 in `_determine_verdict` (handled by RES-012)
- **factory.py**: Remove `idempotency_store` parameter from `ResolveSituationService` constructor (handled by RES-024)
- **IdempotencyStore**: KEPT — wired to execution provider as transparent result cache, NOT as a gate
- **Implementations.py / fabric.py**: OPTIONAL — add idempotency check that returns prior result, never blocks

**Verification:**

- `IdempotencyStore` still exists (as transparent result cache, not gate)
- Resolver verdict is never `"idempotency_duplicate"`
- `_determine_verdict()` has no idempotency check
- Executor never returns "cannot execute" for idempotency reasons — returns prior result instead

---

## Milestone 5: Surface Constitution as Back's Operating Manual

### Epic 5.1: Upgrade ConstitutionArtifact

**Goal:** Constitution becomes the domain adapter. Not gate. Not hidden server magic. Back reads it.

---

#### RES-015: Add teaching fields to `ConstitutionArtifact`

**Status:** ✅ DONE — 2026-06-17

| Field | Value |
|-------|-------|
| **Files** | `k1/fabric/constitution/schema.py` (ConstitutionArtifact + to_dict), `k1/fabric/constitution/loader.py` (`_populate_teaching_fields()`) |
| **Priority** | HIGH |
| **Depends on** | Nothing (additive schema change) |
| **Verified** | 2026-06-12: `ConstitutionArtifact` at L175 has 17 fields. 4 required: `connector_id`, `constitution_id`, `schema_version`, `execution_phases`. 13 optional: `authored_by`, `authored_at`, `last_proven_at`, `prerequisite_reads`, `conflict_analysis_rules`, `companion_resource_roles`, `hil_gates`, `mutation_sequencing`, `verification_requirements`, `precondition_summary`, `companion_resource_summary`, `hil_trigger_summary`, `degradation_policy`. ✅ JSON schema `additionalProperties` already changed to `True` by RES-000b. |

**Add 5 new teaching-surface fields (all default-safe, optional):**

```python
# NEW — Back-facing teaching surface (prose, not structured objects)
how_to_sequence: list[str] = field(default_factory=list)
    # Numbered prose steps: ["1. Read the target shopping list", "2. Check for duplicates", ...]
what_to_verify: list[str] = field(default_factory=list)
    # Verification checks: ["After adding: item must appear in list_items output", ...]
when_to_ask_human: list[dict] = field(default_factory=list)
    # [{trigger, reason, prompt}] — reason is NEW (HILGate has no reason field)
companion_connectors: list[dict] = field(default_factory=list)
    # [{connector_id, role, description}] — connector_id is NEW (CompanionResourceRole has resource_kind)
conflict_rules: list[str] = field(default_factory=list)
    # Flat prose strings: ["If same item name exists with pending status, flag as duplicate", ...]
```

**⚠️ COHERENCE — Schema migration required:**

1. **JSON Schema** (L235): Change `"additionalProperties": False` → `True` OR add new fields to schema `properties`. Also add new fields to `required` if needed.
2. **`to_dict()`** (L203): Add serialization for all 5 new fields.
3. **`_constitution_dict()`** in `situated_resolver.py` (L282): Add serialization for all 5 new fields so Back receives them.
4. **GPS `constitutions` table**: Add columns for `how_to_sequence_json`, `what_to_verify_json`, `when_to_ask_human_json`, `companion_connectors_json`, `conflict_rules_json` — OR store as JSON in existing columns. Simpler: add to the `constitution` JSON blob already stored.

**Existing useful fields (keep as-is for internal use, map forward for Back):**

- `prerequisite_reads` → kept + surfaced as-is to Back
- `precondition_summary` → kept + surfaced as-is to Back (already good prose)
- `companion_resource_summary` → kept; `companion_connectors` derived from `companion_resource_roles`
- `hil_trigger_summary` → kept; `when_to_ask_human` derived from `hil_gates`

**Verification:**

- Run: `pytest tests/k1/fabric/constitution/test_constitution_schema.py -v`
- Assert: `ConstitutionArtifact` has all 5 new fields with defaults
- Assert: `to_dict()` includes new fields
- Assert: JSON schema validates with new fields

---

#### RES-016: Map old constitution fields into new teaching fields

**Status:** ✅ DONE — 2026-06-17

| Field | Value |
|-------|-------|
| **Files** | `k1/fabric/constitution/loader.py` (`_populate_teaching_fields()` added, called from `load()`) |
| **Priority** | HIGH |
| **Depends on** | RES-015 |
| **Verified against live code** | 2026-06-12: All old fields confirmed. 3 mapping discrepancies found. |

**Mapping:**

| Old Field | New Field | Status |
|-----------|-----------|--------|
| `mutation_sequencing: list[MutationStep]` | `how_to_sequence: list[str]` | ✅ Direct map — `MutationStep` has `order`, `phase`, `operation`, `description`. Convert to prose: `f"{m.order}. {m.description}"` |
| `verification_requirements: list[VerificationRequirement]` | `what_to_verify: list[str]` | ✅ Direct map — `VerificationRequirement` has `method`, `description`, `required_for_submit`. Convert to prose: `f"After {method}: {description}"` |
| `hil_gates: list[HILGate]` | `when_to_ask_human: list[dict]` | ⚠️ **DISCREPANCY**: HILGate has `{trigger, prompt, options, field}` — **no `reason` field**. New shape needs `{trigger, reason, prompt}`. Options: A) Add `reason` field to HILGate dataclass, B) Populate `reason` from `prompt` text, C) Use `trigger` as `reason`. |
| `companion_resource_roles: list[CompanionResourceRole]` | `companion_connectors: list[dict]` | ⚠️ **DISCREPANCY**: CompanionResourceRole has `{resource_kind, role, description}` — **no `connector_id`**. New shape needs `{connector_id, role, description}`. Must resolve `resource_kind` → `connector_id` via GPS lookup (`get_connector_by_resource_kind()`). |
| `conflict_analysis_rules: list[ConflictRule]` | `conflict_rules: list[str]` | ⚠️ **DISCREPANCY**: ConflictRule is structured `{check, with_resource_kinds, description, resolution}`. New shape needs flat prose strings. Convert to prose: `f"If {check} with {with_resource_kinds}: {description}. Resolution: {resolution}"` |
| `prerequisite_reads: list[PrerequisiteRead]` | `prerequisite_reads: list[dict]` | ✅ Direct map — keep `{operation, resource_kind, reason, required}` shape |
| `precondition_summary: str \| None` | `precondition_summary: str` | ✅ Direct map — already a prose string |

**Verification:**

- `ConstitutionLoader.load(connector_id)` returns `ConstitutionArtifact` with all new fields populated

**⚠️ COHERENCE — Where mapping runs (added 2026-06-12):**

- **Option A (lazy, recommended for Phase 1):** `ConstitutionLoader.load()` at L47 — after `validate_constitution(raw)`, call `_populate_teaching_fields(artifact)` to derive new fields. No GPS migration needed.
- **Option B (eager):** `register_definition_to_store()` at manifest_translator.py L310 — populate new fields when writing to GPS. Requires GPS schema migration.
- **JSON Schema blocker:** `CONSTITUTION_JSON_SCHEMA` has `"additionalProperties": False` at L235. Must change to `True` or add new fields to schema `properties`. Otherwise validation fails on load.

---

#### RES-017: Update family tool definitions with real constitution prose

**Status:** ✅ DONE — 2026-06-17 (5 of 6 connectors updated; family_settings intentionally skipped — no constitution)

| Connector | Status | `how_to_sequence` | `what_to_verify` | `when_to_ask_human` | `companion_connectors` | `conflict_rules` |
|-----------|--------|:--:|:--:|:--:|:--:|:--:|
| `family.calendar` | ✅ | 3 | 2 | 7 | 4 | 4 |
| `family.shopping` | ✅ | 3 | 2 | 4 | 1 | 1 |
| `family.tasks` | ✅ | 3 | 2 | 4 | 2 | 2 |
| `family.reminders` | ✅ | 3 | 2 | 4 | 2 | 2 |
| `family.chores` | ✅ | 3 | 2 | 4 | 2 | 3 |
| `family.family_settings` | ⏭️ Skipped | — | — | — | — | — |

**🔧 EXECUTION NOTES (2026-06-17):**

- Calendar: added `how_to_sequence` (3 steps), `what_to_verify` (2 checks), `when_to_ask_human` (7 gates with `reason` field), `companion_connectors` (4 connectors with `connector_id`), `conflict_rules` (4 prose rules).
- Also fixed `validate_constitution()` in schema.py — was not passing new teaching fields through to `ConstitutionArtifact` constructor. Now all 5 fields survive validation.
- `_populate_teaching_fields()` in loader.py acts as safety net — only fills empty fields.

| Field | Value |
|-------|-------|
| **Files** | `k1/tools/family/calendar/definition.py` (L91 `_CALENDAR_CONSTITUTION`), `k1/tools/family/shopping/definition.py` (L68 `_SHOPPING_CONSTITUTION`), `k1/tools/family/tasks/definition.py`, `k1/tools/family/reminders/definition.py`, `k1/tools/family/chores/definition.py`, `k1/tools/family/family_settings/definition.py` |
| **Priority** | MEDIUM |
| **Depends on** | RES-016 |
| **Verified** | 2026-06-12: REAL constitutions already have GOOD prose. Shopping constitution has `precondition_summary` ("Before adding an item, I MUST list..."), `mutation_sequencing` with descriptive steps, `verification_requirements` with specific checks, `hil_gates` with real triggers. ⚠️ RES-017 is about FORMAT transformation (structured objects → prose strings for Back), NOT content creation from scratch. |

**What the REAL shopping constitution already has:**

- `precondition_summary`: "Before adding an item, I MUST list the active shopping list to check for duplicates. Shopping has a parent-approval workflow..."
- `mutation_sequencing[0]`: `{order:1, phase:"read", operation:"list", description:"Read the active shopping list to check for duplicates."}`
- `mutation_sequencing[1]`: `{order:2, phase:"mutate", operation:"add", description:"Add the item if no duplicate. Child-originated requests land as pending_parent_approval..."}`
- `mutation_sequencing[2]`: `{order:3, phase:"read", operation:"list", description:"Verify the item was added (read_after_write)."}`
- `verification_requirements[0]`: `{method:"read_after_write", description:"Read back the list and confirm the new item appears...", required_for_submit:True}`
- `hil_gates`: 4 gates (missing_required_field×2, duplicate_detected, child_request_pending)

**What RES-017 actually does (format transformation, not content creation):**

- `mutation_sequencing` (structured) → `how_to_sequence` (prose strings): Already done by RES-016 mapping
- `verification_requirements` (structured) → `what_to_verify` (prose strings): Already done by RES-016 mapping
- `hil_gates` (structured) → `when_to_ask_human` (prose dicts): Already done by RES-016 mapping
- No NEW prose needs to be written — the existing constitutions are already well-written

**Per-connector verification (what to check, not what to write):**

| Connector | `precondition_summary` | `mutation_sequencing` | `verification_requirements` | `hil_gates` |
|-----------|----------------------|----------------------|---------------------------|-------------|
| `family.shopping` | ✅ Good prose | ✅ 3 steps | ✅ read_after_write | ✅ 4 gates |
| `family.calendar` | Verify | ✅ Has mutation_sequencing | ✅ Has verification | Verify |
| `family.tasks` | Verify | Verify | Verify | Verify |
| `family.reminders` | Verify | Verify | Verify | Verify |
| `family.chores` | Verify | Verify | Verify | Verify |
| `family.family_settings` | Verify | Verify | Verify | Verify |

**If any connector has VAGUE prose:** Replace with specific operating instructions following the shopping example. RES-016's mapping transforms whatever prose exists — RES-017 ensures the prose is GOOD.

**Verification:**

- Each connector definition has non-empty `mutation_sequencing` with specific descriptions
- Each has `verification_requirements` with specific checks
- `precondition_summary` is a real operating instruction, not placeholder text

---

## Milestone 6: Rewrite Back Prompt Around Resolution Packet

### Epic 6.1: Teach Back to read connector, tools, constitution

**Goal:** Back should not receive a mystery list of tool names. It should receive a mini operating manual.

---

#### RES-018a: Replace "YOUR PRIMARY TOOL" + "FRAMING INTENTS" sections in Back prompt

**Status:** ✅ DONE — 2026-06-17
**Junior-safe:** ⚠️ MEDIUM — text-only changes, but Back LLM behavior is sensitive to prompt wording.
| Split from:** RES-018 (original).  Replaces L80–112.  Requires senior review before merge.

| Field | Value |
|-------|-------|
| **File** | `k1/concierge/prompt/back_prompt.py` (L80–112) |
| **Priority** | CRITICAL |
| **Depends on** | RES-002 (envelope shape finalized), RES-012 (verdict always `can_execute`) |

**Old sections to REPLACE:**

| Old Section | Lines | What's Wrong |
|-------------|-------|-------------|
| "YOUR PRIMARY TOOL: resolve_situation" | L80–91 | Teaches `frame=...` with intents/refs |
| "FRAMING INTENTS" | L95–112 | Teaches domain/rf/op hints |

**New instruction (replaces L80–112):**

```
== YOUR PRIMARY TOOL: resolve_situation ==
resolve_situation is ALWAYS your FIRST tool call for any task that
touches live records.  It returns a RESOLUTION PACKET with three parts:
CONNECTOR, TOOLS, and CONSTITUTION.  The verdict is always can_execute —
the resolver never blocks.

Call it with the user's raw words:
  resolve_situation(action_text="add eggs to my shopping list")
That's it.  actor_id, session_id, space_id are auto-filled.
Optionally pass context_hints={domain_hint, resource_hint, operation_hint}
as ADVISORY boost signals — they never filter results.
```

**Verification:**

- Prompt contains "CONNECTOR, TOOLS, and CONSTITUTION"
- Prompt teaches `action_text` as the only LLM-provided field
- Zero references to `frame`, `intents`, `person_refs`, `resource_refs`

---

#### RES-018b: Replace "EXECUTION PROTOCOL" + "STEP 1-3" sections in Back prompt

**Status:** ✅ DONE — 2026-06-17
**Junior-safe:** ⚠️ MEDIUM — text-only changes, but teaches new execution flow.
| Split from:** RES-018 (original).  Replaces L125–163.  Requires senior review before merge.

| Field | Value |
|-------|-------|
| **File** | `k1/concierge/prompt/back_prompt.py` (L125–163) |
| **Priority** | CRITICAL |
| **Depends on** | RES-018a (tool intro must be replaced first) |

**Old sections to REPLACE:**

| Old Section | Lines | What's Wrong |
|-------------|-------|-------------|
| "EXECUTION PROTOCOL" header | L125–131 | References old budget model |
| "STEP 1 -- RESOLVE" | L132–156 | Verdict cascade (`missing_capability`, `blocked_by_policy`, `stale_projection`, `needs_human`) |
| "STEP 2 -- EXECUTE" | L158–163 | "Follow the execution_plan. Copy from allowed_capability_names." |

**New instruction (replaces L125–163):**

```
== EXECUTION PROTOCOL ==
You have {max_tool_calls} tool calls total (including submit_result).
resolve_situation costs 1.  Minimum viable: 1 resolve + 1 invoke + 1 submit = 3.

STEP 1 — RESOLVE (1 tool call):
  Call resolve_situation(action_text=...) ONCE.  Read the packet:

  1. connector.description — confirm it matches the user's intent.
     If NOT, check alternative_connectors.  If one fits better, re-resolve
     with more specific action_text.
  2. constitution.precondition_summary — what must be true before starting.
  3. constitution.how_to_sequence — numbered steps.  Follow this order.
  4. tools[] — READ each tool's description.  Pick the one that matches
     the user's request.  "add eggs" → add_item, not create_list.
  5. If search_confidence < 0.5, check alternative_connectors.
  6. If constitution.when_to_ask_human triggers, call HIL and WAIT.

STEP 2 — EXECUTE:
  Follow constitution.how_to_sequence:
    Step 1 → read tool → check for duplicates/conflicts
    Step 2 → write tool → execute the mutation
    Step 3 → read tool → verify using constitution.what_to_verify

  Call invoke_capability(capability_name=..., params=...) for each step.
  Copy capability_name EXACTLY from tools[].
  Fill params from tools[].required_inputs and tools[].optional_inputs.

STEP 3 — SUBMIT:
  submit_result with outcome, summary, and evidence.
```

**Verification:**

- Zero references to old verdicts (`missing_capability`, `blocked_by_policy`, `stale_projection`, `needs_human`)
- Zero references to `allowed_capability_names`, `execution_plan` as primary instruction
- "constitution" appears 8+ times in STEP 1-3
- `tools[]` is the mechanism for tool selection, not flat name lists

---

#### RES-018c: Update tier tool notes + registry hints narrative in Back prompt

**Status:** ✅ DONE — 2026-06-17
**Junior-safe:** ✅ Text updates only — reference new field names, no structural changes.
| Split from:** RES-018 (original).  Replaces L281–330.

| Field | Value |
|-------|-------|
| **File** | `k1/concierge/prompt/back_prompt.py` (L270–330 `build_back_prompt()` with tier-specific tool notes) |
| **Priority** | MEDIUM |
| **Depends on** | RES-018b |

**Old sections to UPDATE:**

| Old Section | Lines | Old Reference | New Reference |
|-------------|-------|---------------|---------------|
| Tier tool notes | L281–324 | `execution_plan`, `allowed_capability_names`, `missing_capability` | `tools[]`, `constitution`, `search_confidence` |
| Registry hints narrative | L330+ | Domain/rf lists for hint population | Reframe as context for `action_text`, not hint fields |

**Verification:**

- Tier tool notes reference `tools[]` and `constitution` instead of `execution_plan`
- Registry hints narrative describes domain context for writing good `action_text`, not for populating `domain_hint` fields

---

#### RES-019: Update `execute_resolve_situation()` payload builder

**Status:** ⬜ NOT STARTED

| Field | Value |
|-------|-------|
| **File** | `k1/concierge/tools/implementations.py` (L1531–1607 `execute_resolve_situation()`) |
| **Priority** | CRITICAL |
| **Depends on** | RES-001 (schema must be updated) |
| **Verified** | 2026-06-12: Current implementation at L1546 extracts `frame = args.get("frame")`, validates it's a dict. L1572 builds payload with `"frame": frame`. L1586 logs `len(frame.get("intents", []))`. L1558–1569 auto-fills `actor_id`, `space_id`, `session_id` from ToolContext — this survives unchanged. ⚠️ `_build_resolve_request` in fabric.py:1889 also needs updating — covered by RES-031. |

**Change (3 lines in implementations.py):**

```python
# OLD (L1546):
frame = args.get("frame")
if not isinstance(frame, dict):
    return ToolResult(..., error="frame is required and must be an object")

# NEW:
action_text = args.get("action_text", "")
if not action_text or not isinstance(action_text, str):
    return ToolResult(..., error="action_text is required and must be a non-empty string")
```

```python
# OLD (L1572):
payload: dict[str, Any] = {
    "frame": frame,
    "actor_id": str(actor_id),
    ...
}

# NEW:
context_hints = args.get("context_hints") or {}
payload: dict[str, Any] = {
    "action_text": action_text,
    "context_hints": context_hints,
    "actor_id": str(actor_id),
    ...
}
```

```python
# OLD (L1586):
logger.info("tool:resolve_situation  actor=%s space=%s frame_intents=%d",
            actor_id, space_id, len(frame.get("intents", [])))

# NEW:
logger.info("tool:resolve_situation  actor=%s space=%s action_text_len=%d",
            actor_id, space_id, len(action_text))
```

**Auto-fill survives unchanged (L1558–1569):** `actor_id`, `space_id`, `session_id` extraction from `ToolContext` stays exactly as-is.

**⚠️ Downstream: `_build_resolve_request` in fabric.py:1889** currently calls `build_frame_from_dict(frame_dict, ...)`. After payload changes from `"frame"` to `"action_text"`, this function must extract `action_text` + `context_hints` instead. Covered by RES-031 (files include fabric.py L1889–1916).

**Verification:**

- Run: `pytest tests/k1/concierge/tools/ -v -k resolve_situation`
- Manual: `action_text="add eggs to shopping list"` → payload has `action_text` not `frame`
- Manual: `context_hints={"domain_hint": "family"}` → passed through as advisory only

---

#### RES-020: Keep `invoke_capability` unchanged except validation

**Status:** ⬜ NOT STARTED

| Field | Value |
|-------|-------|
| **Files** | `k1/concierge/tools/implementations.py` (L1619 `execute_invoke_capability()`), `k1/concierge/adapters/fabric_dispatch.py` (L78 `dispatch_direct()`) |
| **Priority** | LOW |
| **Depends on** | RES-019 |
| **Verified** | 2026-06-12: `invoke_capability` at L1619 takes `capability_name: str` + `params: dict`. New `tools[]` array provides exactly these: `capability_name` strings + `required_inputs`/`optional_inputs` schemas. Back copies `capability_name` verbatim from `tools[]`, fills `params` from `required_inputs`/`optional_inputs`. Signature unchanged. `dispatch_direct` at L78 calls `self._fabric.execute(request)` — unchanged. No code changes needed for core path. |

**Keep unchanged:**

- `invoke_capability` tool schema + implementation — takes `capability_name` + `params`
- `batch_invoke_capabilities` tool — takes list of `{capability_name, params}`
- `dispatch_direct` adapter — routes `CapabilityRequest` → `fabric.execute(request)`
- `submit_result` tool — terminates ReAct loop

**Optional enhancement (NOT required for Phase 1):** Validate that invoked `capability_name` was included in the latest resolution packet's `tools[]`. This would require session-scoped resolution memory — Back stores the `resolution_id` and the execution layer validates against it. Defer to Phase 2.

**Why no changes needed:** The new `tools[]` array from `ResolutionEnvelope` provides the exact same information Back needs to call `invoke_capability`: the `capability_name` string and the `required_inputs`/`optional_inputs` schemas for building `params`. The existing implementation already works with these.

**Verification:**

- Existing tests for `invoke_capability` still pass
- Back can call `invoke_capability(capability_name="tool.execute.shopping.add_item", params={list_id: "weekly-groceries", name: "eggs"})` with capability_name from new `tools[]`

---

## Milestone 7: Companion Connector and Fallback Protocol

### Epic 7.1: Handle multi-connector tasks without creating agent soup

**Goal:** Back can re-resolve companion domains when constitution points there.

---

#### RES-021: Add companion connector protocol to prompt

**Status:** ⬜ NOT STARTED

| Field | Value |
|-------|-------|
| **File** | `k1/concierge/prompt/back_prompt.py` (added to STEP 1 -- RESOLVE section, after the main instruction block replaced by RES-018) |
| **Priority** | MEDIUM |
| **Depends on** | RES-018 (prompt must be rewritten first) |
| **Verified** | 2026-06-12: No companion protocol exists in current prompt. No `resolve_companion` tool exists in code (correctly — RES-022 defers this). The new constitution teaching surface has `companion_connectors: [{connector_id, role, description}]` — Back needs instruction on how to use this. Purely a prompt addition; zero code changes. |

**Rule (added to the new STEP 1 -- RESOLVE section):**

```
STEP 1 — RESOLVE (continued):

  7. COMPANION CONNECTORS: If constitution.companion_connectors is
     non-empty and the user's request mentions the companion's role,
     call resolve_situation again with action_text focused on that
     companion's domain.  Example:
       User: "plan a birthday party Saturday"
       → resolve_situation → family.calendar (primary)
       → constitution.companion_connectors includes family.shopping
         (role: "suggestion_source")
       → User also says "get groceries for the party"
       → resolve_situation(action_text="get groceries for birthday party")
       → family.shopping
```

**Verification:**

- Prompt contains instruction for companion connector handoff
- Back knows to re-resolve with focused action_text when companion role matches

---

#### RES-022: Add optional `resolve_companion` helper (only if needed)

**Status:** ⬜ NOT STARTED

| Field | Value |
|-------|-------|
| **Files** | `k1/concierge/tools/schemas_back.py`, `k1/concierge/tools/implementations.py`, `k1/fabric/fabric.py`, `k1/fabric/resolver/situated_resolver.py` |
| **Priority** | LOW — do NOT add first |
| **Depends on** | RES-021 |
| **Verified** | 2026-06-12: No `resolve_companion` tool or helper exists in code. No companion-specific resolver method exists. This is correct — the architecture keeps Back as a single ReAct agent that re-calls `resolve_situation` with different `action_text`. Adding a dedicated companion tool would increase kernel surface for minimal gain. |

**Recommendation:** Do NOT add this. Let Back call `resolve_situation` again with better `action_text`. Keep the kernel small. Back is an agent — it can decide to re-resolve.

**If needed (Phase 2+):** A lightweight helper that takes primary `connector_id` and returns related connectors with their constitutions, without re-running full connector search. But this is optimization, not MVP.

**Verification:**

- No `resolve_companion` tool exists (correct)
- Back re-resolves by calling `resolve_situation(action_text=...)` again

---

### Epic 7.2: Scale-safe fallback

---

#### RES-023: Delete return-all-tools fallback

**Status:** ✅ DONE — 2026-06-17

| Field | Value |
|-------|-------|
| **Files** | `k1/fabric/resolver/situated_resolver.py` (L615 step 11, L621 step 11b, L668 `_allowed_next_actions`), `k1/fabric/resolver/knobs.py` (L54 `fallback_mode`, L78 `HYPOTHESIS_COMBO`) |
| **Priority** | MEDIUM |
| **Depends on** | RES-012 (verdict cascade replacement deletes steps 11/11b) |
| **Verified** | 2026-06-12: K8 at knobs.py L54: `fallback_mode: str = "hard-block"`. `HYPOTHESIS_COMBO` at L78 sets `"return-all-connectors"`. K8 used at 3 sites: (1) `_determine_verdict` step 11 (L615) — check if `return-all-connectors` → override `missing_capability` to `can_execute`, (2) step 11b (L621) — same for no-viable-bindings, (3) `_allowed_next_actions` (L668) — returns ALL capabilities from GPS via `list_all_capabilities()`. Steps 11/11b deleted by RES-012. L668 deleted by RES-012 simplification of `_allowed_next_actions`. `list_all_capabilities()` at GPS L929 KEPT — used by embedding index building (L401, L424). |

**Hard delete:**

| Location | Line | What | Why |
|----------|------|------|-----|
| `knobs.py` | L54 | `fallback_mode: str = "hard-block"` | Delete knob field — no more fallback modes |
| `knobs.py` | L78 | `fallback_mode="return-all-connectors"` | Delete from `HYPOTHESIS_COMBO` preset |
| `knobs.py` | L56 | `# Positions: "hard-block" \| "return-all-connectors" \| ...` | Delete docstring for `fallback_mode` |
| `situated_resolver.py` | L441 | `self._fallback_mode = knobs.fallback_mode` | Delete attribute assignment in `configure()` |
| `situated_resolver.py` | L611-616 | K8 check in step 11 | Already deleted by RES-012 |
| `situated_resolver.py` | L618-623 | K8 check in step 11b | Already deleted by RES-012 |
| `situated_resolver.py` | L664-681 | K8 fallback in `_allowed_next_actions` | Already deleted by RES-012 simplification |

**Replace with (in `_allowed_next_actions` — simplified by RES-012):**

```python
# NEW: always return tools for the matched connector
def _allowed_next_actions(self, connector_hits, tools):
    if connector_hits.primary is None:
        # No connector found — return top-5 connector summaries, no tools
        return [{"connector_id": alt.connector_id, "label": alt.label,
                 "description": alt.description, "confidence": alt.score}
                for alt in connector_hits.alternatives[:5]]
    # Return all tools for the primary connector
    return [{"capability_name": t.capability_name,
             "description": t.description or t.capability_name,
             "binding_id": ""} for t in tools]
```

**`list_all_capabilities()` KEPT** for embedding index building (L401, L424). Not used for fallback.

**Why:** Returning all capabilities works at 52 tools but explodes at 5,000 connectors × 75,000 tools.

**Verification:**

- K8 knob removed from `knobs.py`
- `fallback_mode` not referenced anywhere in resolver path
- No code path returns all capabilities unfiltered
- `list_all_capabilities()` still exists for embedding index use

---

### Epic 7.3: Session Context Resolution (POC-Discovered)

**Goal:** When the resolver is uncertain (score_gap < 0.08 or domain_confidence < 0.72), surface alternatives + disambiguation signal to Back instead of guessing.

**Status:** ✅ DESIGN VALIDATED — POC identified 13% ambiguity ceiling requiring session context.

**POC Finding:** 87% of queries are resolvable statelessly. The remaining 13% are genuinely ambiguous without session context ("make sure I don't forget to buy milk" = reminders OR shopping). The resolver MUST surface this ambiguity to Back rather than silently picking wrong.

---

#### RES-023b: Add `is_resolved` and `disambiguation_signal` to ResolutionEnvelope

**Status:** ⬜ NOT STARTED

| Field | Value |
|-------|-------|
| **Files** | `k1/fabric/resolver/situated_resolver.py` (ResolutionEnvelope class) |
| **Priority** | MEDIUM — required for production quality, not MVP |
| **Depends on** | RES-002 (envelope shape) |

**Change — Add to ResolutionEnvelope:**

```python
@dataclass
class ResolutionEnvelope:
    # ... existing fields ...

    # NEW — session context handoff
    is_resolved: bool = True
        # True = confident routing, proceed to execution
        # False = ambiguous, Back should use session context to pick from alternatives

    disambiguation_signal: str | None = None
        # What session context would resolve the ambiguity:
        #   "last_active_connector" — which connector was user just using?
        #   "user_intent_frame" — is this framed as alert or action?
        #   "time_anchor" — is there a specific event time mentioned?
        #   "entity_type" — what kind of thing is the user referring to?
```

**Routing decision logic (from POC):**

```python
def _compute_routing_decision(
    results: list[tuple[str, float]],
    intent_confidence: float,
) -> tuple[bool, str | None, list[str]]:
    """Determine if routing is confident or needs session context."""
    top1, score1 = results[0]
    top2, score2 = results[1] if len(results) > 1 else (None, 0)

    score_gap = score1 - score2
    confident = intent_confidence >= 0.72
    decisive = score_gap > 0.08

    if confident and decisive:
        return True, None, []

    # Ambiguous — return alternatives + disambiguation signal
    candidates = [top1, top2] if top2 else [top1]
    signal = _disambiguation_signal(top1, top2)
    return False, signal, candidates

def _disambiguation_signal(c1: str, c2: str) -> str:
    pair = {c1, c2}
    if pair == {"family.shopping", "family.chores"}:
        return "last_active_connector"
    if pair == {"family.reminders", "family.tasks"}:
        return "user_intent_frame"
    if pair == {"family.calendar", "family.reminders"}:
        return "time_anchor"
    return "last_active_connector"
```

**Back contract impact:** Back receives `is_resolved=False` → reads `alternative_connectors` → checks session context (`last_connectors`, `last_objects`) → picks correct connector → re-resolves only if needed.

**Verification:**

- 13 ambiguous POC queries marked `is_resolved=False`
- Back prompt teaches reading `is_resolved` + `alternative_connectors`
- Session context integration test: Back picks correct connector from alternatives using conversation history

---

#### RES-023c: Update Back prompt — teach reading `is_resolved` + `alternative_connectors`

**Status:** ⬜ NOT STARTED
**Junior-safe:** ✅ Prompt text addition only — no code logic changes.
| New issue — Phase 5 step 22 from execution order.  Depends on RES-018b (STEP 1-3 prompt rewritten).

| Field | Value |
|-------|-------|
| **File** | `k1/concierge/prompt/back_prompt.py` (STEP 1 — RESOLVE section, after RES-018b) |
| **Priority** | MEDIUM — required for 13% ambiguous query handling |
| **Depends on** | RES-018b (STEP 1-3 sections updated), RES-023b (`is_resolved` field exists) |

**Add to STEP 1 — RESOLVE section (after item 5, before item 6):**

```
  5. If search_confidence < 0.5, check alternative_connectors.
  5a. If is_resolved is False:
      - Read disambiguation_signal to understand what context is needed.
      - Check alternative_connectors against the user's recent conversation.
      - If a better connector is clear from context, re-resolve with
        more specific action_text targeting that connector.
      - If still ambiguous, pick the top-ranked connector and proceed.
  6. If constitution.when_to_ask_human triggers, call HIL and WAIT.
```

**Verification:**

- Back prompt contains "is_resolved" and "alternative_connectors"
- Back prompt contains "disambiguation_signal"
- Manual: Back LLM reads `is_resolved=False` → checks alternatives → picks correct connector

---

## Milestone 8: Factory and Wiring Cleanup

### Epic 8.1: Remove old resolver components from construction

**Goal:** Stop wiring dead organs into the body.

---

#### RES-024a: Remove old resolver imports + instantiations from factory (deletions only)

**Status:** ⬜ NOT STARTED
**Junior-safe:** ✅ Deletions only — remove dead imports and instantiation lines. No new logic.
| Split from:** RES-024 (original).  This is the safe deletions half.

| Field | Value |
|-------|-------|
| **File** | `k1/fabric/factory.py` (L1060–1120 step 21 `_wire_resolver()`) |
| **Priority** | HIGH |
| **Depends on** | RES-007 (ConnectorResolver exists), RES-012 (verdict simplified) |

**DELETE these imports (L1063–1070):**

```python
# DELETE:
from k1.fabric.resolver.capability_type_resolver import CapabilityTypeResolver
from k1.fabric.resolver.resource_projection import ResolveResourcesService
```

**DELETE these instantiation lines (L1088–1092):**

```python
# DELETE L1088-1089:
resource_resolver = ResolveResourcesService(global_projection_store, local_store)
type_resolver = CapabilityTypeResolver(global_projection_store, local_store)
# DELETE L1092:
capability_binder = CapabilityBinderService(global_projection_store, local_store)
```

**KEEP (unchanged):**

- GPS attach: L1073-1074
- `ConstitutionLoader`: L1077-1078
- LPS: L1082-1086 (unless RES-035 deletes)
- `policy_selector = PolicySelectorService(global_projection_store)` — kept, becomes advisory (RES-013)
- `PromptPackBuilder`: L1093-1096
- Idempotency facade attach: L1116-1121

**Verification:**

- File compiles after deletions (with RES-024b wiring not yet added — compile check with `ast.parse` or `python -c "import k1.fabric.factory"`)
- Old imports not referenced elsewhere in file

---

#### RES-024b: Add new `ConnectorResolver` instantiation + simplified `ResolveSituationService` wiring

**Status:** ⬜ NOT STARTED
**Junior-safe:** ⚠️ MEDIUM — imports + wiring must be correct, but well-specified.
| Split from:** RES-024 (original).  Depends on RES-024a (old lines deleted first).  Kernel boot test after this.

| Field | Value |
|-------|-------|
| **File** | `k1/fabric/factory.py` (L1060–1120 step 21 `_wire_resolver()`) |
| **Priority** | HIGH — kernel won't boot if wiring is wrong |
| **Depends on** | RES-024a, RES-007b (callers updated) |

**Add new imports:**

```python
from k1.fabric.resolver.capability_type_resolver import ConnectorResolver  # was CapabilityTypeResolver
```

**Add new instantiation (after existing `ConstitutionLoader` + `PromptPackBuilder`):**

```python
connector_resolver = ConnectorResolver(global_projection_store)
```

**Replace step 21e wiring (L1101–1112):**

```python
# 21e: situated resolver (simplified — fewer params).
fabric.situated_resolver = ResolveSituationService(
    global_projection_store,
    connector_resolver=connector_resolver,      # was type_resolver
    capability_binder=capability_binder,         # simplified (RES-010)
    policy_selector=policy_selector,             # advisory only (RES-013)
    constitution_loader=constitution_loader,
    prompt_pack_builder=prompt_pack_builder,
    # REMOVED: resource_resolver (RES-035), local_store, idempotency_store
)
```

**Verification:**

- `FabricFactory.create_shared()` compiles and creates working fabric
- Run: `pytest tests/k1/fabric/test_factory.py -v`
- Assert: `fabric.situated_resolver` is wired with `connector_resolver` not `type_resolver`
- **🚨 CRITICAL GATE:** Run `pytest tests/k1/kernel/test_service.py -v -k "S3 or P3"` — kernel must boot with new wiring

---

#### RES-025: Update kernel composition root

**Status:** ⬜ NOT STARTED

| Field | Value |
|-------|-------|
| **File** | `k1/kernel/service.py` (L61 `FabricFactory` import, L1966 `create_shared()`, L2148 `_bootstrap_family_tools()`, L2794 `create_with_ports()`) |
| **Priority** | HIGH |
| **Depends on** | RES-024 |
| **Verified** | 2026-06-12: Kernel at L61 imports `FabricFactory`. L1935-1947 creates GPS + IdempotencyStore. L1966 calls `FabricFactory.create_shared(...)` with 12 params. L2148 calls `_bootstrap_family_tools()`. L2794 calls `FabricFactory.create_with_ports(...)` with 16 params. All touchpoints survive — only call signatures may need updating if factory params change. |

**Touchpoints — KEEP unchanged:**

| Line | What | Why |
|------|------|-----|
| L61 | `from k1.fabric.factory import FabricFactory` | Import survives |
| L1935-1947 | GPS + IdempotencyStore creation (S2.10) | GPS is resolver's source of truth — survives |
| L1966-1977 | `FabricFactory.create_shared(...)` (S3) | ⚠️ Call signature may change if factory removes params (RES-024). Remove `resource_resolver=` if RES-035 deletes it. |
| L2010 | `FabricGatewayAdapter(fabric=self._shared_fabric)` (S5) | Survives — orchestrator path unchanged |
| L2148 | `_bootstrap_family_tools()` (S8) | Survives — RES-005 adds connector FTS indexing |
| L2160-2166 | `_load_phase1_catalog_and_verifier()` + `_build_registry_hints()` | Survives — GPS taxonomy for Back prompt |
| L2794-2807 | `FabricFactory.create_with_ports(...)` (P3) | ⚠️ Same — remove params if factory removes them |
| L2810-2820 | Provider re-registration (P3.1) | Survives — NativeToolProvider must work |
| L745-748 | `_shared_fabric.shutdown()` | Survives |
| L767-783 | GPS + Idempotency close | Survives — kernel owns lifecycle |

**Touchpoints — POTENTIAL CHANGE (if factory signature changes):**

| Line | Current param | After RES-024 |
|------|-------------|---------------|
| L1976 | `global_projection_store=self._global_projection_store` | KEPT |
| L1977 | `idempotency_store=self._idempotency_store` | KEPT (moved to execution path per RES-014) |
| L2804 | `global_projection_store=self._global_projection_store` | KEPT |
| L2806 | `local_projection_store=session_local_store` | REMOVE if RES-035 deletes Stage 1 |
| L2807 | `idempotency_store=self._idempotency_store` | KEPT |

**Verification:**

- Run: `pytest tests/k1/kernel/test_service.py -v -k "fabric or S3 or P3"`
- `create_shared()` call compiles with updated params
- `create_with_ports()` call compiles with updated params
- `k1/kernel/ports/fabric_port.py` docstrings updated to reflect new `CapabilityFabric` API (RES-038, integrated into RES-025)

---

#### RES-026: Keep adapter path stable

**Status:** ⬜ NOT STARTED

| Field | Value |
|-------|-------|
| **Files** | `k1/concierge/adapters/fabric_dispatch.py` (L382 `resolve_situation()`), `k1/fabric/fabric.py` (L1760 `_handle_resolve_situation()`, L1889 `_build_resolve_request()`) |
| **Priority** | HIGH |
| **Depends on** | RES-024 |
| **Verified** | 2026-06-12: Adapter path confirmed stable. `FabricDispatchAdapter.resolve_situation()` at L382 uses `getattr(self._fabric, "_handle_resolve_situation", None)` — dynamic lookup, not typed interface. Signature unchanged: `async def resolve_situation(self, payload: dict) -> dict`. All internal changes (envelope shape, resolver pipeline, connector search) are behind this unchanged adapter boundary. |

**Stable call chain (verified):**

```
execute_resolve_situation()                          # implementations.py:1531
  → ctx.dispatch.resolve_situation(payload)          # implementations.py:1598
    → FabricDispatchAdapter.resolve_situation()      # fabric_dispatch.py:382
      → handler = getattr(self._fabric, "_handle_resolve_situation", None)  # L392
      → return await handler(payload)                # L397
        → _handle_resolve_situation(payload)         # fabric.py:1760
          → request = _build_resolve_request(payload) # fabric.py:1784 (INTERNAL CHANGE)
          → envelope = self.situated_resolver.resolve(request) # L1785 (INTERNAL CHANGE)
          → return envelope.to_dict()                # L1786 (INTERNAL CHANGE — new shape)
```

**What changes internally (behind the stable boundary):**

| Internal function | Line | Change | Why safe |
|-------------------|------|--------|----------|
| `_build_resolve_request(payload)` | L1889 | Extracts `action_text` instead of `frame` dict | Payload dict still has `action_text` key — just different key name. Covered by RES-031. |
| `situated_resolver.resolve(request)` | situated_resolver.py:448 | Simplified pipeline (1 stage vs 5) | Same `ResolveSituationRequest` input type (updated by RES-031). Returns same `ResolutionEnvelope` class (updated by RES-002). |
| `envelope.to_dict()` | situated_resolver.py:122 | New envelope shape | Still returns `dict`. Concierge passes it through as `ToolResult.data`. |

**What does NOT change (stable):**

- `FabricDispatchAdapter.resolve_situation(self, payload: dict) -> dict` — signature unchanged
- `self._fabric` attribute — still the `Fabric`/`CapabilityFabric` instance
- `_handle_resolve_situation` method name on fabric — still exists
- `ctx.dispatch.resolve_situation(payload)` — `IDispatchPort` contract unchanged
- `ToolResult(status="ok", data=result)` — tool result format unchanged

**Verification:**

- Run: `pytest tests/k1/concierge/adapters/ -v -k fabric_dispatch`
- `resolve_situation` returns `{"verdict": "can_execute", "connector": {...}, "tools": [...], ...}` — new shape, same dict contract
- Adapter does NOT import any resolver-internal module

---

## Milestone 9: Tests and Benchmark Gates

### Epic 9.1: Replace old graph tests with connector-first tests

**⚠️ TEST AUDIT 2026-06-12: 22 test files impacted across 3 severity levels. All verified against live code.**

---

#### RES-027a: Delete 7 test files for deleted resolver classes

**Status:** ⬜ NOT STARTED
**Junior-safe:** ✅ Pure deletions — remove files that import deleted classes.
| Split from:** RES-027 (original).  HIGH — DELETE tier.

| Field | Value |
|-------|-------|
| **Priority** | HIGH — these 7 files will fail at `pytest` collection (ImportError) |
| **Depends on** | RES-006, RES-007, RES-008, RES-009, RES-031, RES-032, RES-033 |

**7 files to DELETE (100% dead — test classes being deleted):**

| File | Why Delete | Deleted Symbols |
|------|-----------|-----------------|
| `tests/k1/fabric/resolver/test_capability_type_resolver.py` | Tests `CapabilityTypeResolver` — class replaced by RES-007 | `CapabilityTypeResolver`, `ResolvedIntentType`, `RequestFrame`, `RequestFrameIntent`, `ResourceUniverse` |
| `tests/k1/fabric/resolver/test_fts5_fallback.py` | Tests `_resolve_one()` — method deleted by RES-006 | `CapabilityTypeResolver`, `ResourceUniverse` |
| `tests/k1/fabric/resolver/test_capability_binder.py` | Tests `CapabilityBinderService` + `BindingBundle` — both deleted by RES-009/010/011 | `CapabilityBinderService`, `BindingBundle`, `PolicyBundle`, `ResolvedIntentType`, `ResourceUniverse` |
| `tests/k1/fabric/resolver/test_request_frame.py` | Tests `BackTaskEnvelope`, `RequestFrame`, `RequestFrameBuilder` — all replaced by RES-031/032/033 | `BackTaskEnvelope`, `RequestFrame`, `RequestFrameIntent`, `RequestFrameBuilder` |
| `tests/k1/fabric/resolver/test_resource_projection.py` | Tests Stage 1 resource projection — fate decided by RES-035 | `RequestFrame`, `ResourceUniverse` |
| `tests/k1/fabric/policy/test_policy_selector.py` | Tests `PolicySelectorService` as blocker — converted to advisory by RES-013 | `PolicySelectorService`, `PolicyBundle`, `ResolvedIntentType`, `ResourceUniverse` |
| `tests/k1/fabric/connectors/test_family_phase11_projection.py` | 5 calls to `lookup_capability_by_type()` — deleted by RES-008 | `lookup_capability_by_type` (5 call sites) |

**Verification:**

- `pytest tests/k1/fabric/resolver/ -v --collect-only` — zero collection errors
- `git rm` each file

---

#### RES-027b: Rewrite 7 test files that import deleted symbols but test surviving concepts

**Status:** ⬜ NOT STARTED
**Junior-safe:** ⚠️ MEDIUM-HIGH — requires understanding new input/output shapes.  Pair with senior.
| Split from:** RES-027 (original).  HIGH — REWRITE tier.

| Field | Value |
|-------|-------|
| **Priority** | HIGH — 7 files import deleted symbols |
| **Depends on** | RES-007, RES-010, RES-012, RES-015 (new shapes must be stable) |

**7 files to REWRITE:**

| File | What to Change |
|------|----------------|
| `tests/k1/fabric/resolver/test_situated_resolver.py` | Replace `RequestFrame` → `action_text` input. Replace old envelope assertions → new envelope assertions (per RES-029). |
| `tests/k1/fabric/resolver/test_situated_resolver_negative.py` | Update input/output shapes. Delete negative paths for `missing_capability`, `blocked_by_policy` (deleted by RES-012). |
| `tests/k1/fabric/integration/test_pipeline_e2e.py` | Replace old `resolve_situation` calls with `action_text`-based calls. Replace `allowed_capability_names` assertions with `tools[]` assertions. Replace `lookup_capability_by_type` assertions with `search_connectors` assertions. |
| `tests/k1/fabric/prompt_pack/test_prompt_pack_builder.py` | Replace with new envelope shape. Test new `_constitution_cards()`, `_tool_cards()`. |
| `tests/k1/fabric/test_fabric_wiring.py` | Update to new `ConnectorResolver` + `action_text` input. Verify `_handle_resolve_situation` returns new envelope shape. |
| `tests/k1/fabric/test_factory_wiring.py` | Update to verify `ConnectorResolver` is wired, not `CapabilityTypeResolver`. Verify `ResolveSituationService` receives simplified params. |
| `tests/k1/fabric/constitution/test_constitution_schema.py` | Add assertions for 5 new teaching fields. Verify defaults. Verify `to_dict()` includes new fields. Verify JSON schema accepts new fields. |

**Verification:**

- All 7 files pass: `pytest tests/k1/fabric/resolver/ tests/k1/fabric/integration/ tests/k1/fabric/prompt_pack/ tests/k1/fabric/constitution/ -v`

---

#### RES-027c: Update 6 test files with specific assertion breakage

**Status:** ⬜ NOT STARTED
**Junior-safe:** ✅ Well-scoped — each file has specific known breakage points.
| Split from:** RES-027 (original).  MEDIUM — UPDATE tier.

| Field | Value |
|-------|-------|
| **Priority** | MEDIUM — runtime failures on specific assertions |
| **Depends on** | RES-008 (lookup_capability_by_type removed), RES-001 (new schema) |

**6 files to UPDATE:**

| File | What Breaks | Fix |
|------|-----------|-----|
| `tests/k1/fabric/stores/test_global_projection_store.py` | L432: `store.lookup_capability_by_type()` — method removed by RES-008 | Remove or replace with `search_connectors()` assertion |
| `tests/k1/fabric/test_manifest_admission.py` | L80: `store.lookup_capability_by_type()` — same | Same |
| `tests/k1/fabric/test_kernel_phase1_catalog.py` | L72: `gps.lookup_capability_by_type()` — same | Same |
| `tests/k1/concierge/actors/test_back_resolve_situation_tool.py` | L18 imports `execute_resolve_situation`, L148/159 asserts `allowed_capability_names` | Update to new `action_text` input + `tools[]` assertions |
| `tests/k1/concierge/react/test_back_capability_execution_kernel.py` | L140/220/348: asserts `result.data["execution_plan"]` — dict key may change | Verify new envelope dict key. `BackExecutionPlan` is concierge-level — likely survives |
| `tests/k1/concierge/react/test_back_execution_plan.py` | L158: `merged["execution_plan"]["complete"]` — same dict key concern | Same — verify |

**Also verify (LOW — NO CHANGE):**

| File | What | Why Safe |
|------|------|----------|
| `tests/k1/concierge/prompt/test_back_prompt_capability_names.py` | Asserts prompt contains "resolve_situation" string | Prompt text changes but assertion pattern survives — update expected string |
| `tests/k1/verification/test_verification_runner.py` | Imports `ConstitutionArtifact` — upgraded, not deleted | New fields have defaults; tests should pass |

**Run after update:**

```bash
pytest tests/k1/fabric/stores/ tests/k1/concierge/actors/ tests/k1/concierge/react/ -v
```

---

#### RES-028: Add connector search tests

**Status:** ⬜ NOT STARTED

| Field | Value |
|-------|-------|
| **New file** | `tests/k1/fabric/stores/test_connector_search.py` |
| **Priority** | HIGH — needed to validate RES-003 |
| **Depends on** | RES-003 |
| **Verified** | No existing connector search tests exist. All new. |

**Test cases:**

| Query | Expected Top Connector | Why |
|-------|----------------------|-----|
| `"add eggs to shopping list"` | `family.shopping` | Direct match on "shopping" + "add" |
| `"what is on my calendar today"` | `family.calendar` | Direct match on "calendar" |
| `"remind me to pay rent"` | `family.reminders` or `family.tasks` | "remind" → reminders; "pay" → tasks |
| `"schedule dentist for Riley Monday 3pm"` | `family.calendar` | "schedule" → calendar |
| `"add milk to grocery list"` | `family.shopping` | "grocery" → shopping synonym |
| `"what chores does Riley have"` | `family.chores` | "chores" → chores |
| `"update family settings"` | `family.family_settings` | "settings" → family_settings |
| Wrong hint: action="add eggs to shopping list", hint={domain:"healthcare"} | `family.shopping` (hint is advisory) | Hints never filter — text search wins |
| Empty query `""` | Returns `[]` | Edge case — empty input |
| Nonsense query `"xyzzy foobar blarg"` | Returns `[]` | No matching connector text |

**Also test:**

- `search_connectors()` returns `list[ConnectorSearchHit]` with correct fields
- `MIN(rank)` confirmed as best-match-per-connector (not MAX)
- `matched_capabilities` list populated
- Top-5 alternatives returned

**Run:** `pytest tests/k1/fabric/stores/test_connector_search.py -v`

---

#### RES-029: Add resolution packet contract tests

**Status:** ⬜ NOT STARTED

| Field | Value |
|-------|-------|
| **New file** | `tests/k1/fabric/resolver/test_resolution_envelope.py` |
| **Priority** | HIGH — validates the core contract (RES-002) |
| **Depends on** | RES-002 |
| **Verified** | No existing envelope contract tests exist. All new. |

**Structural assertions:**

```python
def test_envelope_verdict_always_can_execute():
    """verdict is ALWAYS 'can_execute'. Never blocks."""
    envelope = resolver.resolve(request)
    assert envelope.verdict == "can_execute"

def test_envelope_has_connector():
    """connector object exists with connector_id, label, description."""
    envelope = resolver.resolve(request)
    assert envelope.connector is not None
    assert envelope.connector.connector_id
    assert envelope.connector.label
    assert envelope.connector.description

def test_envelope_tools_have_descriptions():
    """tools[] array has full tool objects, NOT flat strings."""
    envelope = resolver.resolve(request)
    for tool in envelope.tools:
        assert tool.capability_name
        assert tool.description  # NOT empty
        assert tool.invocation_mode in ("read", "execute")
        assert tool.effect in ("read", "write", "delete")

def test_envelope_constitution_surfaced():
    """constitution teaching surface is present."""
    envelope = resolver.resolve(request)
    assert envelope.constitution is not None
    assert envelope.constitution.how_to_sequence
    assert envelope.constitution.what_to_verify
    assert envelope.constitution.precondition_summary

def test_envelope_search_confidence():
    """search_confidence is a float 0.0-1.0."""
    envelope = resolver.resolve(request)
    assert 0.0 <= envelope.search_confidence <= 1.0

def test_envelope_alternatives_exist():
    """alternative_connectors list exists."""
    envelope = resolver.resolve(request)
    assert isinstance(envelope.alternative_connectors, list)

def test_no_flat_allowed_capability_names():
    """OLD field allowed_capability_names is ABSENT."""
    envelope = resolver.resolve(request)
    assert not hasattr(envelope, 'allowed_capability_names')

def test_no_binding_bundle_in_envelope():
    """BindingBundle is stripped from envelope."""
    envelope = resolver.resolve(request)
    assert not hasattr(envelope, 'binding_bundle')

def test_no_request_frame_in_serialized():
    """request_frame, candidate_universe, intent_resolutions are stripped."""
    d = envelope.to_dict()
    assert "request_frame" not in d
    assert "candidate_universe" not in d
    assert "intent_resolutions" not in d
    assert "policy_bundle" not in d
```

**Run:** `pytest tests/k1/fabric/resolver/test_resolution_envelope.py -v`

---

#### RES-030: Add scale test

**Status:** ⬜ NOT STARTED

| Field | Value |
|-------|-------|
| **New file** | `tests/k1/fabric/stores/test_connector_search_scale.py` |
| **Priority** | MEDIUM — validates scale-safe design |
| **Depends on** | RES-023, RES-029 |
| **Verified** | No existing scale tests. All new. |

**Synthetic benchmark:**

```python
def test_5000_connectors_search():
    """5,000 connectors × 15 tools = 75,000 capabilities. Still fast."""
    # Insert 5000 synthetic connectors with capabilities
    for i in range(5000):
        store.upsert_connector(...)
        for j in range(15):
            store.upsert_capability(...)

    # Search should be fast (< 500ms)
    start = time.time()
    hits = store.search_connectors("add eggs to shopping list", top_k=5)
    elapsed = time.time() - start

    assert elapsed < 0.5  # Under 500ms
    assert len(hits) <= 5  # Max 5 results
    assert len(hits[0].matched_capabilities) <= 15  # Max tools per connector

def test_no_global_all_tools_dump():
    """Response size is bounded — no 75,000-tool dump."""
    envelope = resolver.resolve(request)
    d = envelope.to_dict()
    size_kb = len(json.dumps(d)) / 1024
    assert size_kb < 50  # Under 50KB token-budget-safe

def test_fallback_returns_summaries_not_all_tools():
    """When no connector matches, return top-5 summaries, not all tools."""
    hits = store.search_connectors("xyzzy foobar blarg", top_k=5)
    assert len(hits) == 0  # No matches
    # Fallback: only connector summaries, no tools dump
    envelope = resolver.resolve(request_with_nonsense)
    assert len(envelope.tools) == 0
    assert len(envelope.alternative_connectors) <= 5
```

**Run:** `pytest tests/k1/fabric/stores/test_connector_search_scale.py -v`

---

### Epic 9.2: Kernel boot + integration gates

**Goal:** After all M1–M8 changes, the kernel must boot and pass smoke tests.

---

#### RES-030a: Kernel boot gate

**Status:** ⬜ NOT STARTED

| Field | Value |
|-------|-------|
| **Tests** | `tests/k1/kernel/test_service.py` (existing), `tests/k1/tools/family/calendar/test_bootstrap_calendar.py` (existing) |
| **Priority** | CRITICAL — kernel must boot after migration |
| **Depends on** | RES-024, RES-025 |

**Changes needed to kernel tests after migration:**

| Test | Line(s) | Change |
|------|---------|--------|
| `test_service.py` | L1231 (S3 shared fabric), L1259 (Fabric.facade), L2426 (create_with_ports), L2457 (FabricFactory import), L2493 (P3 fabric), L2517 (P3 assertion), L2638/2680 (session fabric) | ⚠️ If `FabricFactory.create_shared()`/`create_with_ports()` signatures change (RES-024), update call arguments. If `CapabilityFabric` API surface changes, update attribute assertions. |
| `test_bootstrap_calendar.py` | L9-16 (imports FabricFactory + adapters), L70 (create_standalone), L84 (create_with_ports) | ⚠️ Same — update factory call signatures. Verify family tools bootstrap still works after GPS schema changes (RES-015). |

**Boot sequence test:**

```python
def test_kernel_boots_with_new_resolver():
    """Kernel boots end-to-end with new resolver architecture."""
    config = KernelConfig(enable_fabric_stores=True, enable_family_tools=True)
    kernel = await start_kernel(config)
    session = await kernel.create_session()

    # Resolve a simple query
    fabric = session.fabric
    result = await fabric._handle_resolve_situation({
        "action_text": "add eggs to shopping list",
        "actor_id": "test-user",
        "session_id": session.session_id,
        "space_id": "family:default",
    })

    assert result["verdict"] == "can_execute"
    assert result["connector"]["connector_id"] == "family.shopping"
    assert len(result["tools"]) > 0
    assert result["constitution"] is not None
    assert "how_to_sequence" in result["constitution"]

    await kernel.shutdown()
```

**Run:** `pytest tests/k1/kernel/test_service.py -v -k "fabric or S3 or P3 or boot"`

---

#### RES-030b: Integration smoke test

**Status:** ⬜ NOT STARTED

| Field | Value |
|-------|-------|
| **New file** | `tests/k1/fabric/integration/test_new_resolver_smoke.py` |
| **Priority** | CRITICAL — validates end-to-end flow |
| **Depends on** | RES-001 through RES-026 |

**End-to-end smoke test:**

```python
async def test_full_resolve_flow_shopping():
    """User says 'add eggs' → resolver finds shopping → Back gets tools + constitution."""
    # 1. Boot kernel with family tools
    # 2. Create session
    # 3. Call resolve_situation with action_text
    # 4. Verify connector = family.shopping
    # 5. Verify tools[] includes add_item, list_items, etc.
    # 6. Verify constitution has how_to_sequence
    # 7. Verify verdict = can_execute
    # 8. Verify search_confidence > 0.5
    pass

async def test_no_hidden_vetoes():
    """Verdict is always can_execute — never blocks."""
    # Even with nonsensical input
    result = await resolve("xyzzy foobar blarg")
    assert result["verdict"] == "can_execute"
    # Even with empty input
    result = await resolve("")
    assert result["verdict"] == "can_execute"

async def test_hints_never_filter():
    """Wrong domain hint does NOT change connector result."""
    result_correct = await resolve("add eggs to shopping list")
    result_wrong_hint = await resolve("add eggs to shopping list",
                                       context_hints={"domain_hint": "healthcare"})
    assert (result_correct["connector"]["connector_id"] ==
            result_wrong_hint["connector"]["connector_id"])

async def test_invoke_capability_still_works():
    """invoke_capability path unchanged by resolver redesign."""
    result = await invoke_capability(
        capability_name="tool.read.shopping.list_items",
        params={"list_id": "weekly-groceries"}
    )
    assert result.status == "ok"
```

**Run:** `pytest tests/k1/fabric/integration/test_new_resolver_smoke.py -v`

---

### Test Impact Summary

| Severity | Count | Action |
|----------|-------|--------|
| 🔴 HIGH — DELETE | 7 | Files test deleted classes — remove entirely |
| 🔴 HIGH — REWRITE | 7 | Files import deleted symbols but test surviving concepts — update imports + assertions |
| 🟡 MEDIUM — UPDATE | 6 | Files have specific assertions that break — fix assertions |
| 🟢 LOW — NO CHANGE | 2 | String references only — update expected strings |
| 🆕 NEW — CREATE | 4 | RES-028, RES-029, RES-030, RES-030b |

**Total files touched: 22 existing + 4 new = 26 files**

---

## Hard Delete List

These are not "deprecated." These are **axe targets.**

| Component | File | Action |
|-----------|------|--------|
| `_resolve_operation()` | `k1/fabric/resolver/capability_type_resolver.py` | **DELETE** |
| `_resolve_concept()` | `k1/fabric/resolver/capability_type_resolver.py` | **DELETE** |
| `_resolve_one()` 4-step graph walk | `k1/fabric/resolver/capability_type_resolver.py` | **DELETE or replace fully** |
| `lookup_capability_by_type()` runtime use | `k1/fabric/stores/global_projection_store.py` | **DELETE from resolver path** |
| `capability_type_index` runtime dependency | GPS schema/migrations | **DELETE or leave offline only** |
| `_select_best_capability()` | `k1/fabric/resolver/capability_binder.py` | **DELETE** |
| `CapabilityBinderService` 3-pass discovery | `k1/fabric/resolver/capability_binder.py` | **REPLACE with connector tools fetch** |
| 13-step verdict cascade | `k1/fabric/resolver/situated_resolver.py` | **REPLACE with always `can_execute`** |
| `PolicySelectorService` as blocker | `k1/fabric/resolver/policy/selector.py` | **CONVERT to advisory** |
| K8 return-all-tools fallback | `k1/fabric/resolver/knobs.py`, `situated_resolver.py` | **DELETE** |
| Back prompt: `allowed_capability_names` instruction | `k1/concierge/prompt/back_prompt.py` | **REPLACE** |
| Old `RESOLVE_SITUATION_SCHEMA` frame-first shape | `k1/concierge/tools/schemas_back.py` | **REPLACE** |

---

## Touchpoint Map

### Must change (20 files)

```
k1/concierge/tools/schemas_back.py          # RES-001
k1/concierge/tools/implementations.py       # RES-001, RES-019
k1/concierge/prompt/back_prompt.py          # RES-018, RES-021
k1/concierge/ports.py                       # RES-001
k1/concierge/adapters/fabric_dispatch.py    # RES-026 (keep stable, validate)

k1/fabric/fabric.py                         # RES-002, RES-026
k1/fabric/factory.py                        # RES-024
k1/fabric/resolver/situated_resolver.py     # RES-002, RES-010, RES-012, RES-023
k1/fabric/resolver/capability_type_resolver.py  # RES-006, RES-007
k1/fabric/resolver/capability_binder.py     # RES-009, RES-010
k1/fabric/resolver/policy/selector.py       # RES-013
k1/fabric/resolver/knobs.py                 # RES-023
k1/fabric/stores/global_projection_store.py # RES-003, RES-004, RES-008
k1/fabric/constitution/schema.py            # RES-015, RES-016
k1/fabric/constitution/loader.py            # RES-015, RES-016
k1/fabric/manifest_admission.py             # RES-004
k1/fabric/manifest_translator.py            # RES-004

k1/kernel/service.py                        # RES-025
k1/tools/family/registry.py                 # RES-005
k1/tools/family/bootstrap.py                # RES-005
k1/tools/family/definition.py               # RES-017
k1/tools/family/*/definition.py             # RES-017 (6 files)
```

### Should NOT need major changes (8 files)

```
k1/concierge/actors/front.py
k1/concierge/fsm/controller.py
k1/concierge/fsm/states.py
k1/concierge/fsm/task_bridge.py
k1/concierge/react/loop.py
k1/orchestrator/adapters/fabric_gateway_adapter.py
k1/planner/ports/fabric_retrieval_port.py
```

Front/FSM/ReAct loop should mostly survive. The big surgery is Fabric resolver and Back's understanding of the packet.

---

## Execution Order (POC-Updated)

Do it in this order. No spaghetti séance. Items marked ✅ are POC-validated.

```
Phase 1 — BUILD THE NEW ENGINE (additive, no deletions)
  1. RES-003: Deploy MiniLM-L6 dense retrieval as primary connector search ✅
  2. RES-003a: Build systematic connector document structure (Epic 1.3) ✅
  3. RES-003b: Train intent schema classifier on synthetic data (Epic 1.2) ✅
  4. RES-003c: Integrate schema scoring into resolver (Stage 0) ✅
  5. RES-004: Add connector doc indexing during manifest admission
  6. RES-005: Add connector doc indexing during family bootstrap
  7. RES-015: Add teaching fields to ConstitutionArtifact
  8. RES-016: Map old constitution fields to new teaching fields

Phase 2 — BUILD THE NEW RESPONSE
  9. RES-002: Replace ResolutionEnvelope shape (add is_resolved, disambiguation_signal)
  10. RES-001: Replace Back tool schema for resolve_situation

Phase 3 — REWIRE THE INTERNALS
  11. RES-007: Replace CapabilityTypeResolver with ConnectorResolver (MiniLM-backed)
  12. RES-010: Replace binder output with all tools for connector
  13. RES-012: Replace verdict cascade with always can_execute
  14. RES-013: Convert policy to advisory
  15. RES-023: Delete return-all-tools fallback
  16. RES-011: Remove BindingBundle from Back-facing path

Phase 4 — UPDATE THE SURFACE
  17. RES-018: Replace old resolve_situation prompt section (teach Back to read packet)
  18. RES-019: Update execute_resolve_situation payload builder
  19. RES-021: Add companion connector protocol to prompt
  20. RES-017: Update family tool definitions with real constitution prose

Phase 5 — SESSION CONTEXT HANDOFF (new from POC)
  21. RES-023b: Add is_resolved + disambiguation_signal to envelope
  22. Update Back prompt: teach reading is_resolved + alternative_connectors
  23. Wire session context resolver: last_active_connector → pick from alternatives

Phase 6 — CLEANUP
  24. RES-024: Update FabricFactory wiring
  25. RES-025: Update kernel composition root
  26. RES-026: Verify adapter path stability
  27. RES-006: DELETE 4-step graph traversal path
  28. RES-008: DELETE lookup_capability_by_type from runtime
  29. RES-009: DELETE _select_best_capability
  30. RES-014: Move idempotency outside resolver

Phase 7 — TEST + BENCHMARK
  31. RES-027: Delete old graph routing tests
  32. RES-028: Add connector search tests (dense retrieval)
  33. RES-029: Add resolution packet contract tests
  34. RES-030: Add scale test (5000 connectors)
  35. RES-020: Verify invoke_capability unchanged
  36. RES-022: Add resolve_companion helper (ONLY IF NEEDED)

✅ = POC validates this approach works. Execute with confidence.
```

---

## Final Target Architecture (POC-Validated)

```
Back receives task
  ↓
Back calls resolve_situation(action_text="add eggs to my shopping list")
  → actor_id, session_id, space_id auto-filled
  → context_hints optional, advisory only, NEVER hard filters
  ↓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESOLVER (stateless, 22MB, ~6ms total)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  │
Stage 0: Intent Classifier (optional, 3ms)
  → predict(effect, resource_kind, domain_tag, confidence)
  → if confidence < 0.72: mark as potentially ambiguous
  │
Stage 1: MiniLM-L6 Dense Retrieval (3ms)
  → encode(action_text) → cosine similarity against pre-computed connector docs
  → connector docs built from systematic structure (title×3, boundary fields,
    effect taxonomy, actions, domain vocabulary, descriptions, namespace anchor)
  │
Stage 2: Namespace Prior
  → if connector.namespace == active_namespace: score += 0.20
  → 0% distractor leakage, 87% Conn@1 at 111 connectors
  │
Stage 3: Schema Scoring (if classifier available)
  → connectors matching predicted domain get effect_boost * confidence
  → confidence-weighted fusion: 0.4*schema + 0.4*dense + 0.2*namespace
  │
Stage 4: Routing Decision
  → if score_gap > 0.08 AND confidence > 0.72: is_resolved=True
  → else: is_resolved=False, return top-2 alternatives + disambiguation_signal
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ↓
ResolutionEnvelope {
  verdict: "can_execute",           ← ALWAYS, never blocks
  connector: { id, label, description },
  tools: [ ALL tools for connector ],  ← Back picks, not resolver
  constitution: {                     ← teaching surface, not gates
    precondition_summary,
    how_to_sequence,
    what_to_verify,
    when_to_ask_human,
    conflict_rules,
  },
  search_confidence: 0.87,
  alternative_connectors: [ top-3 ],
  is_resolved: true | false,         ← NEW
  disambiguation_signal: str | null, ← NEW
}
  ↓
Back reads packet:
  1. If is_resolved=True: confirm connector, pick tool, execute
  2. If is_resolved=False: check session context against alternatives,
     pick correct connector, proceed
  3. Read constitution.how_to_sequence — follow step order
  4. Read tools[].description — pick exact tool
  5. Execute via invoke_capability(capability_name=..., params=...)
  6. Verify using constitution.what_to_verify
  ↓
submit_result
```

**Stateless ceiling: 87%. With session context: ~95-98% (projected). The old resolver tried to be judge, priest, cartographer, customs officer, and tool picker. The new resolver is a sharp concierge desk: "Here is the right connector (confidence X), here are its tools, here is the manual. If uncertain, here are 2 alternatives and here's what context would resolve it. Now execute."**

---

## Milestone 10 — Residual Peripheral Audit (from live codebase audit 2026-06-11)

**⚠️ DEDUPLICATED 2026-06-12:** Original 14 RES issues reduced to 6. The other 8 were already covered by or integrated into M0–M9.

| Original RES | Fate | Integrated Into |
|-------------|------|----------------|
| RES-031 (Replace RequestFrame) | Already in execution order | M2 Phase 3 step 15 |
| RES-032 (Replace RequestFrameBuilder) | Already in execution order | M2 Phase 3 step 16 |
| RES-033 (Replace BackTaskEnvelope) | Already in execution order | M2 Phase 3 step 17 |
| RES-034 (Rewrite PromptPackBuilder) | Already in execution order | M6/M8 Phase 4 step 18 |
| RES-035 (Stage 1 fate) | Already in execution order | M2 Phase 3 step 14 |
| RES-038 (Kernel IFabricPort) | Integrated into RES-025 | M8 |
| RES-041 (TaskIntent update) | Integrated into RES-001 | M0 |
| RES-044 (Embedding index target) | Integrated into RES-024 | M8 |

**These 6 remain — true peripheral concerns with no parent milestone:**

---

#### RES-036: Audit `CapabilityContractView` in HIL types

**Status:** ⬜ NOT STARTED

| File | `k1/hil/types.py` |
| Priority | MEDIUM — duck-typing means silent runtime misbehavior |
| Depends on | RES-002 (new tools shape) |

`CapabilityContractView` is a structural mirror of `k1.fabric.types.CapabilityContract`. Uses `getattr` for `name`, `safety_band_min`, `requires_human_confirmation`, `side_effects`, `description`. If the new `tools[]` shape changes these fields, the HIL gate silently reads wrong/absent fields. Verify field compatibility after RES-002.

---

#### RES-037: Update planner types for new fabric discovery types

**Status:** ⬜ NOT STARTED

| Files | `k1/planner/types.py`, `k1/fabric/types.py` |
| Priority | MEDIUM — import-time break if `ScoredCapability` removed |
| Depends on | RES-003 (new ConnectorSearchHit) |

`k1/planner/types.py` L40: `from k1.fabric.types import ScoredCapability`. Either keep `ScoredCapability` as a public alias → `ConnectorSearchHit`, or update both files.

---

#### RES-039: Audit shared schemas for connector-first discovery

**Status:** ⬜ NOT STARTED

| File | `k1/concierge/tools/schemas_fabric.py` |
| Priority | LOW — schema descriptions only |

`DISCOVER_CAPABILITIES_SCHEMA` and `INVOKE_CAPABILITY_SCHEMA` descriptions may need updating for connector-first language. No code breakage.

---

#### RES-040: Audit concierge type re-exports

**Status:** ⬜ NOT STARTED

| File | `k1/concierge/types/__init__.py` |
| Priority | LOW — passthrough re-exports |

Re-exports `CapabilityRequest`, `CapabilityResult` from fabric. Verify after migration.

---

#### RES-042: Audit `FabricBusAdapter` for new fabric API

**Status:** ⬜ NOT STARTED

| File | `k1/bus/adapters/fabric_adapter.py` |
| Priority | LOW — verify after migration |

Wraps fabric bus operations. Verify adapter still works after `CapabilityFabric` API changes.

---

#### RES-043: Audit self-model `fabric_risk_catalog.py`

**Status:** ⬜ NOT STARTED

| File | `k1/selfmodel/adapters/fabric_risk_catalog.py` |
| Priority | LOW — verify after migration |

Reads from Fabric capability registry. Verify registry API unchanged.

---

### UPDATED: Hard Delete List (with line numbers verified against live code)

These are not "deprecated." These are **axe targets.** Every line number verified 2026-06-11.

| Component | File | Line | Action |
|-----------|------|------|--------|
| `_resolve_operation()` | `k1/fabric/resolver/capability_type_resolver.py` | **L532** | **DELETE** |
| `_resolve_concept()` | `k1/fabric/resolver/capability_type_resolver.py` | **L567** | **DELETE** |
| `_resolve_one()` 4-step graph walk | `k1/fabric/resolver/capability_type_resolver.py` | **L163** | **DELETE or replace fully** |
| `lookup_capability_by_type()` runtime use | `k1/fabric/stores/global_projection_store.py` | **L1460** | **DELETE from resolver path** |
| `capability_type_index` runtime dependency | GPS schema/migrations | — | **DELETE or leave offline only** |
| `_select_best_capability()` | `k1/fabric/resolver/capability_binder.py` | **L694** (module-level) | **DELETE** |
| `CapabilityBinderService` 3-pass discovery | `k1/fabric/resolver/capability_binder.py` | **L179** | **REPLACE with connector tools fetch** |
| 13-step verdict cascade | `k1/fabric/resolver/situated_resolver.py` | `_determine_verdict()` | **REPLACE with always `can_execute`** |
| `PolicySelectorService` as blocker | `k1/fabric/policy/selector.py` | **L98** (⚠️ corrected path) | **CONVERT to advisory** |
| K8 return-all-tools fallback | `k1/fabric/resolver/knobs.py:46`, `situated_resolver.py` | **L46** (`fallback_mode`) | **DELETE** |
| Back prompt: `allowed_capability_names` instruction | `k1/concierge/prompt/back_prompt.py` | **L138** | **REPLACE** |
| Old `RESOLVE_SITUATION_SCHEMA` frame-first shape | `k1/concierge/tools/schemas_back.py` | **L37** | **REPLACE** |
| `RequestFrame.intents[]` with domain/rf/op | `k1/fabric/resolver/request_frame.py` | — | **REPLACE with `action_text`** (RES-031) |
| `RequestFrameBuilder.build()` old logic | `k1/fabric/resolver/request_frame_builder.py` | — | **REPLACE** (RES-032) |
| `BackTaskEnvelope.task_dispatch["intents"]` | `k1/fabric/resolver/back_task_envelope.py` | — | **REPLACE** (RES-033) |

### UPDATED: Touchpoint Map (with audit corrections)

#### Must change (26 files — was 20, +6 from audit)

```
k1/concierge/tools/schemas_back.py          # RES-001
k1/concierge/tools/implementations.py       # RES-001, RES-019
k1/concierge/prompt/back_prompt.py          # RES-018, RES-021
k1/concierge/ports.py                       # RES-001
k1/concierge/adapters/fabric_dispatch.py    # RES-026 (keep stable, validate)
k1/concierge/task/intent.py                 # RES-041 (NEW)
k1/concierge/tools/schemas_fabric.py        # RES-039 (NEW)

k1/fabric/fabric.py                         # RES-002, RES-026
k1/fabric/factory.py                        # RES-024
k1/fabric/resolver/situated_resolver.py     # RES-002, RES-010, RES-012, RES-023
k1/fabric/resolver/capability_type_resolver.py  # RES-006, RES-007
k1/fabric/resolver/capability_binder.py     # RES-009, RES-010
k1/fabric/policy/selector.py                # RES-013 (⚠️ corrected path)
k1/fabric/resolver/knobs.py                 # RES-023
k1/fabric/stores/global_projection_store.py # RES-003, RES-004, RES-008
k1/fabric/constitution/schema.py            # RES-015, RES-016
k1/fabric/constitution/loader.py            # RES-015, RES-016
k1/fabric/manifest_admission.py             # RES-004
k1/fabric/manifest_translator.py            # RES-004 (no ManifestTranslator class — functions only)
k1/fabric/resolver/request_frame.py         # RES-031 (NEW)
k1/fabric/resolver/request_frame_builder.py # RES-032 (NEW)
k1/fabric/resolver/back_task_envelope.py    # RES-033 (NEW)
k1/fabric/prompt_pack/builder.py            # RES-034 (NEW)
k1/fabric/resolver/resource_projection.py   # RES-035 (NEW)
k1/fabric/resolver/embedding_index.py       # RES-044 (NEW)

k1/kernel/service.py                        # RES-025
k1/kernel/ports/fabric_port.py              # RES-038 (NEW)
k1/tools/family/registry.py                 # RES-005
k1/tools/family/bootstrap.py                # RES-005
k1/tools/family/definition.py               # RES-017
k1/tools/family/reasoning.py                # Include in RES-004 (NEW)

k1/hil/types.py                             # RES-036 (NEW)
k1/planner/types.py                         # RES-037 (NEW)
k1/selfmodel/adapters/fabric_risk_catalog.py # RES-043 (NEW)
k1/bus/adapters/fabric_adapter.py           # RES-042 (NEW)
```

#### Should NOT need major changes (verified clean by audit — pass 1 + pass 2)

```
k1/concierge/actors/front.py                # ✅ Zero fabric resolver imports
k1/concierge/fsm/controller.py              # ✅ Zero fabric resolver imports
k1/concierge/fsm/states.py                  # ✅ Zero fabric resolver imports
k1/concierge/fsm/task_bridge.py             # ✅ Zero fabric resolver imports
k1/concierge/fsm/transition_table.py        # ✅ Zero fabric resolver imports
k1/concierge/react/loop.py                  # ✅ Only "spawn_via_fabric" string literal
k1/orchestrator/adapters/fabric_gateway_adapter.py  # ✅ Only public Fabric API types
k1/planner/ports/fabric_retrieval_port.py   # ✅ Only public RetrievalResult type

# Pass 2 additions — verified clean, no resolver-internal imports:
k1/fabric/stores/local_projection_store.py  # ✅ Keep as-is per RES-024
k1/fabric/policy/affective_routing.py       # ✅ Provider-selection policy, not resolver
k1/fabric/policy/cognitive_load_routing.py  # ✅ Provider-selection policy, not resolver
k1/fabric/policy/policy_engine.py           # ✅ Provider-selection policy, not resolver
k1/fabric/policy/qos_integration.py         # ✅ Provider-selection policy, not resolver
k1/fabric/policy/security_context.py        # ✅ Provider-selection policy, not resolver
k1/fabric/policy/tool_scope.py              # ✅ Provider-selection policy, not resolver
k1/fabric/policy/ports.py                   # ✅ Provider-selection policy, not resolver
k1/fabric/connectors/builder.py             # ✅ Upstream authoring surface
k1/fabric/connectors/definition.py          # ✅ Upstream authoring surface
k1/fabric/connectors/domain_catalog.py      # ✅ 50 ServiceDefinitions; verify FTS coverage in RES-004/005
k1/fabric/verification/runner.py            # ✅ Post-execution; verify ConstitutionArtifact field renames in RES-016
k1/fabric/logging.py                        # ✅ Observability infrastructure
k1/fabric/metrics.py                        # ✅ Observability infrastructure
k1/fabric/types.py                          # ⚠️ Exports ScoredCapability; add to RES-037 file list
k1/concierge/config/kernel.py               # ✅ enable_fabric_stores gate only; naming convention
k1/concierge/orchestrator/types.py          # ✅ max_fabric_calls budget field; naming convention
k1/concierge/section_update/                # ✅ Zero fabric dependencies (all "fabricated" = English word)
bridge/                                      # ✅ Zero k1.fabric imports
```

### UPDATED: Execution Order (Junior-Dev Split Edition — 63 steps, 10 phases)

```
Phase 0 — PREREQUISITES & FOUNDATION (BLOCKERS — complete before any Phase 1+ work)
  P1. RES-046: Decide MiniLM vs UltraBERT for connector embeddings
  P2. RES-000a: Add sentence-transformers to requirements.txt
  P3. RES-000b: GPS schema migration — add constitution columns
  P4. RES-000c: GPS schema migration — create connector_backends table
  P5. RES-000d: LPS schema migration — add backend_id, session_id to connected_resources
  P6. RES-000e: Write detailed RES-031/032/033 specifications

Phase 1 — BUILD THE NEW ENGINE (additive, no deletions)
  1. RES-003-deps: Add MiniLM dependencies + verify model loads
  2. RES-003-core: Add search_connectors() to GPS (MiniLM + namespace prior)
  3. RES-004: Add connector doc indexing during manifest admission
  4. RES-005: Add connector doc indexing during family bootstrap
  5. RES-015: Add teaching fields to ConstitutionArtifact
  6. RES-016: Map old constitution fields to new teaching fields

Phase 2 — BUILD THE NEW RESPONSE
  7. RES-002: Replace ResolutionEnvelope shape
  8. RES-001a: Replace Back tool schema (schemas_back.py only)
  9. RES-001b: Update execute_resolve_situation payload builder (implementations.py)
  10. RES-001c: Update ports.py docstring + task/intent.py deprecation

Phase 3 — REWIRE THE INTERNALS (⚠️ RES-007 MUST run before RES-031)
  11. RES-006: DELETE 4-step graph traversal path
  12. RES-007a: Rename CapabilityTypeResolver → ConnectorResolver, replace resolve() internals
  13. RES-007b: Update factory + situated_resolver callers for ConnectorResolver
  14. RES-010: Replace binder output with all tools for connector
  15. RES-011: Remove BindingBundle from Back-facing path
  16. RES-011c: Add LPS get_connected_backends() method
  17. RES-011b: Add session-aware dynamic enum injection for tool schemas
  18. RES-012a: Replace _determine_verdict() 13-step cascade with always-can_execute
  19. RES-012b: Delete dead helper functions after verdict cascade removal
  20. RES-013: Convert policy to advisory
  21. RES-023: Delete return-all-tools fallback
  22. RES-035: Decide and implement Stage 1 fate
  23. RES-031: Replace RequestFrame with action_text-first input
  24. RES-032: Replace RequestFrameBuilder
  25. RES-033: Replace BackTaskEnvelope intent-dict contract

Phase 4 — UPDATE THE SURFACE
  26. RES-034: Rewrite PromptPackBuilder for new envelope
  27. RES-018a: Replace "YOUR PRIMARY TOOL" + "FRAMING INTENTS" in Back prompt
  28. RES-018b: Replace "EXECUTION PROTOCOL" + "STEP 1-3" in Back prompt
  29. RES-018c: Update tier tool notes + registry hints narrative
  30. RES-019: Update execute_resolve_situation payload builder (full implementation)
  31. RES-021: Add companion connector protocol to prompt
  32. RES-017: Update family tool definitions with real constitution prose
  33. RES-041: Update TaskIntent for action_text-first
  34. RES-039: Audit schemas_fabric.py

Phase 5 — SESSION CONTEXT HANDOFF (new from POC)
  35. RES-023b: Add is_resolved + disambiguation_signal to envelope
  36. RES-023c: Update Back prompt — teach reading is_resolved + alternative_connectors
  37. Wire session context resolver: last_active_connector → pick from alternatives

Phase 6 — CLEANUP
  38. RES-024a: Remove old resolver imports + instantiations from factory (deletions only)
  39. RES-024b: Add new ConnectorResolver wiring to factory
  40. RES-025: Update kernel composition root
  41. RES-038: Update kernel IFabricPort
  42. RES-026: Verify adapter path stability
  43. RES-008: DELETE lookup_capability_by_type from runtime
  44. RES-009: DELETE _select_best_capability
  45. RES-014: Move idempotency outside resolver
  46. RES-036: Audit HIL CapabilityContractView
  47. RES-037: Update planner types

Phase 7 — PERIPHERAL AUDIT
  48. RES-040: Audit concierge type re-exports
  49. RES-042: Audit FabricBusAdapter
  50. RES-043: Audit fabric_risk_catalog
  51. RES-044: Decide embedding index target

Phase 8 — TEST + BENCHMARK
  52. RES-027a: Delete 7 test files for deleted resolver classes
  53. RES-027b: Rewrite 7 test files for new resolver shapes
  54. RES-027c: Update 6 test files with specific assertion breakage
  55. RES-028: Add connector search tests
  56. RES-029: Add resolution packet contract tests
  57. RES-030: Add scale test (5000 connectors)
  58. RES-030a: Kernel boot gate
  59. RES-030b: Integration smoke test
  60. RES-020: Verify invoke_capability unchanged
  61. RES-022: Add resolve_companion helper (ONLY IF NEEDED)

Phase 9 — DEVELOPER HANDOFF + SCRIPTS CLEANUP
  62. RES-045: Clean up scripts/ — update bench_resolver_search.py, archive broken probes
  63. M11: Write familyos_native_app_developer_api.md
```

### SCRIPTS/ Impact: ~50 references break

These files in `scripts/` import deleted symbols. They must be updated or deleted when the resolver changes:

| Script | Break Cause | Severity |
|--------|------------|----------|
| `scripts/bench_resolver_search.py` | `RequestFrameIntent`, `allowed_capability_names` | HIGH |
| `scripts/probe_back_fabric_resolver_benchmark.py` | `RequestFrameIntent`, `allowed_capability_names` | HIGH |
| `scripts/probe_back_information_surface.py` | `RequestFrameIntent`, `allowed_capability_names` | HIGH |
| `scripts/probe_back_resolver_benchmark.py` | `RequestFrameIntent`, `allowed_capability_names`, `capability_type_index` | HIGH |
| `scripts/probe_fabric_api.py` | `RequestFrameIntent`, `lookup_capability_by_type` | HIGH |
| `scripts/probe_real_world_benchmark.py` | `RequestFrameIntent`, `CapabilityBinderService`, `PolicySelectorService` | HIGH |
| `scripts/trace_back_live.py` | `allowed_capability_names` (dict key access) | MEDIUM |
| `scripts/probe_binder.py` | `BindingBundle` (string refs) | LOW |
| `scripts/probe_policy_selector.py` | `PolicyBundle` (string refs) | LOW |
| `scripts/probe_resource_projection.py` | `ResourceUniverse` (string refs) | LOW |

**Recommendation:** Update `bench_resolver_search.py` to test the new connector-first resolver. Delete or archive the other probe scripts — they were POC/experiment tooling for the old architecture.

---

#### RES-045: Clean up `scripts/` — update `bench_resolver_search.py`, archive broken probe scripts

**Status:** ⬜ NOT STARTED
**Junior-safe:** ✅ Well-scoped deletions + one script update.  Can be done incrementally.
| New issue — post-migration cleanup.  No code dependencies (scripts are standalone).

| Field | Value |
|-------|-------|
| **Priority** | LOW — scripts are dev tooling, not production code |
| **Depends on** | All RES issues that delete symbols (`RequestFrameIntent`, `CapabilityBinderService`, `PolicySelectorService`, `allowed_capability_names`) |

**What this does:**

1. **UPDATE** `scripts/bench_resolver_search.py` — replace `RequestFrameIntent` imports with `action_text`-based search.  This becomes the canonical benchmark for the new resolver.

2. **DELETE or ARCHIVE** these probe scripts (import deleted symbols):

| Script | Severity |
|--------|----------|
| `scripts/probe_back_fabric_resolver_benchmark.py` | HIGH |
| `scripts/probe_back_information_surface.py` | HIGH |
| `scripts/probe_back_resolver_benchmark.py` | HIGH |
| `scripts/probe_fabric_api.py` | HIGH |
| `scripts/probe_real_world_benchmark.py` | HIGH |
| `scripts/trace_back_live.py` | MEDIUM |
| `scripts/probe_binder.py` | LOW |
| `scripts/probe_policy_selector.py` | LOW |
| `scripts/probe_resource_projection.py` | LOW |

1. **KEEP** — these scripts do NOT import deleted resolver symbols:
   - `scripts/poc_connector_search.py` ✅ (POC benchmark, uses its own infrastructure)
   - `scripts/train_intent_classifier.py` ✅ (ML training, standalone)
   - `scripts/intent_schema_generator.py` ✅ (training data generation)

**Verification:**

- `python scripts/bench_resolver_search.py` runs without import errors
- Archived scripts are moved to `scripts/_archived/` directory

---

## Milestone 11 — Developer Handoff: API Support Document for FamilyOS Native App Developers

**Status:** ⬜ NOT STARTED
**Date:** 2026-06-14
**Priority:** CRITICAL — bridges architecture design to developer implementation
**Depends on:** RES-002 (envelope shape), RES-010 (tool shape), RES-011b (dynamic enums), RES-015/016 (constitution shape)

### Goal

Produce a standalone, developer-facing document that teaches FamilyOS native app developer teams how to design their tools and connector definitions to work correctly with the new resolver and the broader kernel system. This is the **handoff specification** — the contract between the kernel team and the app developer teams.

### Why This Milestone Exists

The resolver redesign changes the contract for tool authors. Old assumptions (graph-based routing, heuristic tool picking, hardcoded backend enums) are gone. New developers building connectors for FamilyOS, HealthOS, FinanceOS, etc. need:

1. **A stable, versioned API contract** — what the resolver expects, what it returns, what fields are required vs optional
2. **Tool schema conventions** — how to structure `required_inputs`, when to use `enum_source: "lps.connected_backends"`, what shapes work with the resolution envelope
3. **Backend connector schema ingestion contract** — how external backends (Walmart API, Target API, etc.) register with FamilyOS and normalize their output to the canonical schema
4. **Constitution authoring guide** — how to write effective `how_to_sequence`, `what_to_verify`, `when_to_ask_human` that Back LLM can actually follow
5. **Testing and validation guide** — how to test that a connector definition resolves correctly, that tools appear in the envelope, that dynamic enums populate

### Deliverable

**File:** `d:\familyos\k1\docs\familyos_native_app_developer_api.md`

### Document Outline

The handoff document MUST cover these sections:

---

#### §1 — Architecture Overview for Developers

- The resolver's job: `action_text` → `{connector, tools[], constitution, is_resolved, alternatives}`
- What Back LLM does with the resolution packet
- The contract boundary: what the kernel guarantees vs what the developer must provide
- Diagram: Developer writes connector definition → Manifest admission → GPS → Resolver search → Envelope → Back LLM

---

#### §2 — Connector Definition Contract

- Required fields: `connector_id`, `label`, `description`, `domain_id`, `capabilities[]`
- How `description` is used: it's the primary embedding signal for MiniLM-L6 dense retrieval. Must be clear, action-oriented prose. Examples of good vs bad descriptions.
- Namespace conventions: `family.*`, `health.*`, `finance.*`, etc.
- Document structure rules (from POC — Epic 1.3): title anchoring, effect taxonomy, domain vocabulary
- Example: Complete `family.shopping` connector definition with all fields annotated

---

#### §3 — Tool (Capability) Schema Contract

- Required fields per tool: `capability_name`, `action_name`, `description`, `invocation_mode`, `effect`, `required_inputs[]`, `optional_inputs[]`
- Input field schema: `{name, type, description, required, enum?, default?}`
- **Dynamic enum fields** (§3.1):
  - What `enum_source: "lps.connected_backends"` means
  - When to use it (multi-backend connectors: shopping, food delivery, payment)
  - What the resolver injects at resolution time
  - Example: `backend_id` field for `place_order` — developer declares the marker, kernel populates the live enum
  - Fallback behavior: what Back sees when zero backends are connected
- **Session-aware fields** (§3.2):
  - `actor_id`, `session_id`, `space_id` — auto-filled by the kernel, never in developer tool schemas
  - Fields that reference session-scoped data (list IDs, family member IDs) — how to declare them so Back knows to resolve from context
- Tool naming conventions: `tool.{mode}.{connector_short}.{action}` — e.g., `tool.read.shopping.list_items`
- Effect taxonomy: `read`, `write`, `delete` — when to use each

---

#### §4 — Backend Connector Schema Ingestion Contract

- **The native-app-as-aggregator model**: FamilyOS native app fans out to backends (Walmart, Instacart). Backends are data feeds, not peer connectors visible to Back LLM.
- **Backend registration**: How a backend connector registers with FamilyOS
  - `connector_backends` table in GPS: `{connector_id, backend_id, backend_label, schema_version}`
  - Registration happens at manifest admission time or via admin API
- **Schema normalization requirement**: Backend output MUST be normalized to the canonical FamilyOS format
  - Example: Walmart API returns `{itemId, productName, price}` → normalized to `{item_id, name, price, currency, availability}`
  - The native app does the normalization, not the kernel
  - Why: Back LLM sees canonical field names across all backends — "add milk from any store" works because all stores normalize to `{name, price, currency}`
- **Backend health and circuit breaking**: How the native app reports backend status (healthy/degraded/down) to LPS so the resolver can surface availability in the envelope
- **Backend-specific tool variants**: When a tool's behavior differs by backend, how to declare backend-specific input overrides while keeping the canonical schema

---

#### §5 — Constitution Authoring Guide

- Purpose: The constitution is Back LLM's operating manual for the connector. It is a teaching surface, never a gate.
- Fields and their intent:
  - `precondition_summary`: One-sentence prose — what must be true before any tool runs. "Before adding an item, I MUST list the active shopping list to check for duplicates."
  - `how_to_sequence`: Numbered steps. Each step is prose: "1. Read the target shopping list to check for duplicates. 2. Add the item. If child-originated, mark as pending_parent_approval. 3. Verify the item was added by reading back the list."
  - `what_to_verify`: Specific verification checks. "After adding: item must appear in list_items output. After deleting: item must NOT appear in list_items output."
  - `when_to_ask_human`: Triggers for HIL (Human-In-Loop). `[{trigger: "duplicate_detected", reason: "Avoid double-purchasing", prompt: "An item with this name already exists. Should I add it anyway?"}]`
  - `conflict_rules`: Prose strings about conflict resolution. "If same item name exists with pending status, flag as duplicate. If child adds item that conflicts with parent's budget alert, surface both."
  - `companion_connectors`: Related connectors. `[{connector_id: "family.chores", role: "supply_source", description: "Chore supplies may need shopping"}]`
  - `prerequisite_reads`: What must be read before executing. `[{operation: "list", resource_kind: "shopping_list", reason: "Check for duplicates", required: true}]`
- **Good vs bad constitution examples**: Shopping constitution (good — specific, actionable) vs a vague placeholder
- **Constitution testing**: How to verify Back LLM actually follows the constitution in integration tests

---

#### §6 — Resolution Envelope Contract (What Developers Can Expect)

- Full envelope shape (from RES-002) with field-by-field descriptions
- `verdict`: Always `"can_execute"` — why this matters for tool design (no hidden vetoes)
- `connector`: `{connector_id, label, description}` — the matched connector
- `tools[]`: Every tool for the connector, with descriptions, inputs, and injected enums
- `constitution`: The teaching surface (from §5)
- `search_confidence`: 0.0–1.0 — how to use this for fallback logic
- `alternative_connectors`: Top-3 alternatives — when to re-resolve
- `is_resolved` + `disambiguation_signal`: When the resolver is uncertain

---

#### §7 — Developer Workflow: End-to-End Example

Walk through a complete example: building a `family.food` connector for meal planning + grocery integration.

1. Define connector: `connector_id`, `label`, `description`, `domain_id`
2. Define tools: `plan_meals`, `generate_grocery_list`, `place_order` (with `enum_source: "lps.connected_backends"` for `backend_id`)
3. Define constitution: how_to_sequence for meal planning workflow
4. Register via manifest admission
5. Verify: query the resolver, inspect the envelope, run the POC benchmark
6. Test: Back LLM integration test with real action_text queries

---

#### §8 — Testing and Validation Guide

- **Connector resolution test**: Does `search_connectors("plan meals for the week")` return `family.food` as top result?
- **Envelope contract test**: Does the envelope have `verdict: "can_execute"`, `tools[]` with descriptions, `constitution` with teaching fields?
- **Dynamic enum test**: Are `backend_id` enums populated correctly for the test session's connected backends?
- **Scale test**: Does the connector resolve correctly with 5000 other connectors in GPS?
- **Back LLM integration test**: Does Back correctly pick `place_order` with `backend_id="target-api"` when the user says "order on Target"?
- **POC benchmark integration**: How to add a new connector to `scripts/poc_connector_search.py` and run the benchmark
- **Constitution compliance test**: Does the constitution's `how_to_sequence` contain at least 2 steps? Does `what_to_verify` have at least 1 check?

---

#### §9 — Migration Guide for Existing Connectors

- Old graph-based routing → new embedding-based routing: what changes for existing tool definitions
- `allowed_capability_names` → `tools[]`: how the old flat-list output is replaced
- Policy gates → advisory constitution: old policy_verdict fields become `constitution.policy_advice`
- RequestFrame → action_text: old intent/hint fields become optional `context_hints`
- Hardcoded backend enums → LPS dynamic injection: how to add `enum_source` marker to existing tools

---

#### §10 — Reference: FamilyOS Canonical Schemas

- Canonical field names for common domain objects:
  - Shopping: `item_id`, `name`, `quantity`, `unit`, `price`, `currency`, `status`
  - Calendar: `event_id`, `title`, `start_time`, `end_time`, `location`, `attendees[]`
  - Tasks: `task_id`, `title`, `description`, `due_date`, `assignee_id`, `status`
  - Money: `transaction_id`, `amount`, `currency`, `category`, `merchant`, `date`
  - Food: `meal_id`, `recipe_name`, `ingredients[]`, `servings`, `dietary_tags[]`
- Backend normalization examples: Walmart API response → FamilyOS canonical format
- Why canonical schemas matter: Back LLM can reason across connectors ("compare milk prices across all my connected stores")

---

### Verification (for this milestone)

- Document exists at `d:\familyos\k1\docs\familyos_native_app_developer_api.md`
- All 10 sections present with substantive content (not placeholders)
- At least 3 complete connector definition examples (shopping, calendar, food)
- At least 2 dynamic enum examples (shopping place_order, food delivery)
- At least 1 backend normalization example (Walmart API → canonical)
- At least 2 constitution examples (good shopping, good calendar)
- End-to-end walkthrough from connector definition → resolver → Back LLM integration
- Migration guide addresses the 5 key changes for existing connectors

---

### Execution Order Placement

M11 runs AFTER all code milestones (M0–M10) are complete. The document describes the STABLE contract that exists after the resolver redesign. It should NOT be written speculatively — it must reflect the actual, working, tested resolver behavior.

```
Phase 8 — DEVELOPER HANDOFF (after all code changes + tests pass)
  45. M11: Write familyos_native_app_developer_api.md
  46. Review with at least one native app developer team for clarity
  47. Version the document (v1.0) and link from resolver_redesign_migration_plan.md
```
