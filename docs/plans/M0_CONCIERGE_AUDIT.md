# M0 E0.4 — K1 Concierge Target Structure Audit

**Date**: 2026-03-30

---

## E0.4.1 — Current k1/concierge/ Contents

The existing `k1/concierge/` directory contains **10 files** across 5 subdirectories.
All Python files are empty stubs (`__init__.py` with 0 bytes). All `.md` files are design docs.

```
k1/concierge/
├── __init__.py              (empty)
├── concierge.md             (design doc)
├── concierge.mmd            (Mermaid diagram)
├── concierge_fsm_flows.md   (FSM flow design)
├── README.md                (overview)
├── affective/
│   └── __init__.py          (empty)
├── empathy/
│   └── __init__.py          (empty)
├── rhythm/
│   └── __init__.py          (empty)
└── tools/
    ├── __init__.py          (empty)
    └── README.md            (tools overview)
```

### Impact of Migration

| Existing Item | Action | Rationale |
| --- | --- | --- |
| `__init__.py` | **OVERWRITE** | Will contain concierge exports post-M5 |
| `concierge.md` | **KEEP** | Historical design doc — no conflict |
| `concierge.mmd` | **KEEP** | Mermaid diagram — no conflict |
| `concierge_fsm_flows.md` | **KEEP** | FSM design doc — no conflict |
| `README.md` | **UPDATE** | Will describe post-migration structure |
| `affective/__init__.py` | **REPLACE** | Empty → `experience/` covers this domain |
| `empathy/__init__.py` | **REPLACE** | Empty → `experience/` covers this domain |
| `rhythm/__init__.py` | **REPLACE** | Empty → `experience/` covers this domain |
| `tools/__init__.py` | **OVERWRITE** | POC `tools/` has actual implementations |
| `tools/README.md` | **UPDATE** | Will describe migrated tools |

**Key decision**: The plan says `experience/` "replaces empty `affective/`, `empathy/`, `rhythm/`."
These three stub dirs can be safely deleted in M5 since they contain only empty `__init__.py` files
and no code anywhere imports from `k1.concierge.affective`, etc.

---

## E0.4.2 — POC → K1 Mapping Table (Verified)

All 22 POC production directories map 1:1 into `k1/concierge/`.

| # | POC Source | K1 Target | Status | Notes |
| --- | --- | --- | --- | --- |
| 1 | `poc/k1_poc/actors/` | `k1/concierge/actors/` | New dir | 7 files |
| 2 | `poc/k1_poc/bus/` | `k1/concierge/bus/` | New dir | 5 files; wraps `k1/bus/` |
| 3 | `poc/k1_poc/compression/` | `k1/concierge/compression/` | New dir | 2 files |
| 4 | `poc/k1_poc/config/` | `k1/concierge/config/` | New dir | 3 .py + defaults.yaml |
| 5 | `poc/k1_poc/delta/` | `k1/concierge/delta/` | New dir | 9 files |
| 6 | `poc/k1_poc/events/` | `k1/concierge/events/` | New dir | 10 files |
| 7 | `poc/k1_poc/experience/` | `k1/concierge/experience/` | New dir | 8 files; replaces `affective/`, `empathy/`, `rhythm/` |
| 8 | `poc/k1_poc/fabric/` | `k1/concierge/fabric/` | New dir | 5 files; bridges to `k1/fabric/` |
| 9 | `poc/k1_poc/fsm/` | `k1/concierge/fsm/` | New dir | 19 files |
| 10 | `poc/k1_poc/identity/` | `k1/concierge/identity/` | New dir | 2 files |
| 11 | `poc/k1_poc/kernel/` | `k1/concierge/kernel/` | New dir | 3 files; bootstrap = entry point |
| 12 | `poc/k1_poc/ledger/` | `k1/concierge/ledger/` | New dir | 5 files |
| 13 | `poc/k1_poc/llm/` | `k1/concierge/llm/` | New dir | 7 files; port+adapter for model hub |
| 14 | `poc/k1_poc/obs/` | `k1/concierge/obs/` | New dir | 4 files |
| 15 | `poc/k1_poc/orchestrator/` | `k1/concierge/orchestrator/` | New dir | 7 files; bridges to `k1/orchestrator/` |
| 16 | `poc/k1_poc/prompt/` | `k1/concierge/prompt/` | New dir | 9 files |
| 17 | `poc/k1_poc/protocols/` | `k1/concierge/protocols/` | New dir | 20 files |
| 18 | `poc/k1_poc/react/` | `k1/concierge/react/` | New dir | 3 files |
| 19 | `poc/k1_poc/scheduler/` | `k1/concierge/scheduler/` | New dir | 2 files |
| 20 | `poc/k1_poc/sessionstate/` | `k1/concierge/sessionstate/` | New dir | 129 files; already has ports |
| 21 | `poc/k1_poc/task/` | `k1/concierge/task/` | New dir | 12 files |
| 22 | `poc/k1_poc/tools/` | `k1/concierge/tools/` | Overwrite | 7 files; replaces empty stub |

**Totals**: 22 folders, 267 production .py files to copy.

---

## E0.4.3 — Config Strategy Decision

### Current State

| Layer | Location | Contents |
| --- | --- | --- |
| POC Config | `poc/k1_poc/config/` | `__init__.py`, `loader.py`, `defaults.yaml` (~180-200 params) |
| K1 Config | `k1/config/` | `__init__.py` (empty — 0 bytes) |

### Decision: **Concierge carries its own config**

Rationale:
1. `k1/config/` is completely empty — there is no existing config framework to merge into.
2. POC config is self-contained: `loader.py` loads `defaults.yaml` and exposes `get_config()`.
3. Every production module calls `from poc.k1_poc.config import get_config` — after migration this becomes `from k1.concierge.config import get_config`.
4. Port-First means concierge owns its internal config; other k1 modules don't depend on it.
5. If k1 develops a shared config system later, concierge config can delegate to it via a port.

**Result**: Copy `poc/k1_poc/config/` → `k1/concierge/config/` with zero changes to `loader.py` or `defaults.yaml`. Update import paths in M5 (Big Copy).

### Plan Error: Param Count

Plan says "59 tunable parameters" in `defaults.yaml`. Actual count from E0.2 audit is **~180-200** (the plan's 59 likely counted only top-level YAML keys, not nested parameters). Noted for M3 accuracy.
