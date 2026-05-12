# K1 Kernel Full Boot Plan

# Web UI + Family Data + Pseudo-K0 + Native Family Tools

**Created**: May 2026
**Status**: Planning
**Depends on**: M10 (POC_MIGRATION_PLAN.md) complete — `k1.kernel.*` production stack live
**Goal**: Make the production K1 kernel boot with a browser UI, family data, working memory recall, and native family tools — all matching the quality of `poc/k1_poc/demo/`

---

## Context and Problem Statement

The production K1 kernel (`k1/kernel/`) boots today via `scripts/boot_kernel.ps1` into a blocking
terminal REPL (`k1.kernel.chat_repl`). It works but has no UI, no observability panels, no family
data, and memory recall always returns empty (K0 bridge is permanently offline via
`SinkBridgeAdapter`).

The POC demo (`poc/k1_poc/demo/`) has exactly what we want — browser UI, FSM badge, affect meter,
timeline, session state panel, streaming responses, family identity switching — but it runs against
a parallel POC kernel stack (`poc.k1_poc.kernel.*`), not the production one.

This plan bridges the two.

---

## Architecture After This Plan

```
Browser (port 8765)
    │  WebSocket /ws
    ▼
ui/web/app.py  (FastAPI + uvicorn)
    │
    ▼
UiCoordinator  (ui/web/coordinator.py — uses k1 as library)
    │  start_kernel() + create_session()
    ▼
k1/kernel/bootstrap.py  ← production kernel, unchanged
    │  S4 bridge wiring
    ▼
HttpBridgeClient ──────────────────────────────────┐
    │  HTTP :8090                                   │
    ▼                                               │
scripts/pseudo_k0/  (FastAPI pseudo-K0 server)      │
    ├── /k0/command.submit    (memory writes)        │
    ├── /k0/query.recall      (memory reads)         │
    ├── /k0/connector.execute (tool dispatch)  ◄─────┘
    └── SQLite wal.db
         │
         ├── MCP Server: calendar   (subprocess or in-process)
         ├── MCP Server: tasks
         ├── MCP Server: messaging
         ├── MCP Server: reminders
         ├── MCP Server: chores
         ├── MCP Server: budget
         ├── MCP Server: school
         └── MCP Server: health
```

**Key architectural decision for M11**: Native family MCP servers are hosted INSIDE pseudo-K0 and
exposed via `/k0/connector.execute`. K1 calls them through the bridge (`BridgeProvider` with
`route_ifl` or `execute_connector`), not via stdio subprocess. This means:

- K1 kernel never spawns MCP subprocesses in production
- All tool state lives in pseudo-K0's SQLite (same WAL as memory — unified store)
- Tools work whether or not K1 is running (K0 is the owner of tool state)
- When real K0 ships, pseudo-K0 is replaced with no K1 changes

---

## Milestone Overview

| Milestone | Name | Depends on | Bootable without? |
|---|---|---|---|
| **M0**  | Domain-Agnostic Self-Model (SpaceGraph migration) | M10 | ✅ pure refactor, no boot change |
| **M12** | Production Web UI | M0 | ✅ UI works K0_OFFLINE |
| **M13** | Space Data Seeding (Family vertical) | M12 | ✅ works without M14 |
| **M14** | Pseudo-K0 Kernel | M12 | ✅ M12/M13 work without it |
| **M11** | Native Family Tools via Bridge | M14 | ❌ requires pseudo-K0 |

> **M0 runs FIRST.** It is a pure internal refactor of `k1/selfmodel/` to remove the
> family-specific naming so every later milestone (M12–M15) lands on a domain-agnostic
> kernel. See ADR-2 / ADR-3 at the end of this document for rationale.

---

## M0 — Domain-Agnostic Self-Model (SpaceGraph Migration)

**Goal**: Rename the family-coupled symbols inside `k1/selfmodel/` to a generic
`SpaceGraph` vocabulary so the kernel has zero hard-coded knowledge of "family". The
family domain becomes one vertical (`verticals/family/`) that produces `SpaceGraphSnapshot`
instances; future verticals (Health, School, Finance, Gov, Agri) plug in the same way.

**Why this milestone is FIRST**:

- M12 (`UiCoordinator`) creates `SelfModelServiceBundle` via `start_kernel()`; reading
  `bundle.space_id` is much cleaner than `bundle.family_space_id` since the web layer is
  not family-specific (it serves whatever vertical is mounted).
- M13's `SpaceDataSeeder` writes a `SpaceGraphSnapshot` — that contract must exist first.
- M14's pseudo-K0 / M15's tool registry both consume `KernelConfig.selfmodel_space_id`
  (was `selfmodel_family_space_id`). Renaming late forces churn across every milestone.
- The refactor is **pure rename + file moves + test path updates**. Zero logic changes.
  Zero new behavior. Risk is bounded.

**Scope**: Only `k1/selfmodel/`, the two `KernelConfig` fields, the wiring lines in
`k1/kernel/service.py`, and three prompt-builder strings. Total surface ≈ 18 files +
~15 test files. No public API outside `k1.selfmodel.*` changes shape — only names.

**Out of scope for M0**: Adding new domain VERTICALS (`health/`, `school/`, etc.) — those
are future work. M0 only proves the abstraction by keeping family as the sole vertical
and renaming kernel-side symbols to match.

### M0 Architecture — Before vs After

```
BEFORE (family-coupled kernel)              AFTER (domain-agnostic kernel)
──────────────────────────────              ──────────────────────────────
k1/selfmodel/                               k1/selfmodel/
  contracts/family_model.py     ─────►        contracts/space_graph.py
    FamilyMemberRef             ─────►          ActorRef
    RelationshipEdge            ─────►          SpaceEdge
    RoutineRef                  (kept)          RoutineRef
    FamilySelfModelSnapshot     ─────►          SpaceGraphSnapshot
      .family_space_id          ─────►            .space_id
  ports/selffamily.py           ─────►        ports/selfspace.py
    ISelfFamilyPort             ─────►          ISelfSpacePort
      .get_family_view()        ─────►            .get_space_view()
  ports/projection_store.py
    IProjectionStorePort
      .read_family()            ─────►          .read_space()
      .write_family()           ─────►          .write_space()
  service/family_model.py       ─────►        service/space_graph.py
    FamilyModelService          ─────►          SpaceGraphService
    FAMILY_MODEL_WRITER_ID      ─────►          SPACE_GRAPH_WRITER_ID
    FamilyViewResult            ─────►          SpaceViewResult
  kernel/bootstrap.py
    SelfModelServiceBundle.family_model   ─►    SelfModelServiceBundle.space_graph
    SelfModelServiceBundle.family_space_id ─►   SelfModelServiceBundle.space_id

k1/concierge/config/kernel.py
  KernelConfig.selfmodel_family_space_id  ─►    KernelConfig.selfmodel_space_id

k1/concierge/prompt/builder.py
  [household] preamble label              ─►    [space] preamble label
  "WHAT family context applies"           ─►    "WHAT space context applies"

k1/selfmodel/contracts/capsule.py
  GroundingCapsule.household_block        ─►    GroundingCapsule.space_graph_block
                                                (family_block kept as legacy fallback)
```

### Read first before coding

- [k1/selfmodel/contracts/family_model.py](k1/selfmodel/contracts/family_model.py) —
  contains the four dataclasses being renamed. Only `dataclasses` stdlib import.
- [k1/selfmodel/ports/selffamily.py](k1/selfmodel/ports/selffamily.py) —
  `@runtime_checkable Protocol` with three methods. Imported by composer.
- [k1/selfmodel/ports/projection_store.py](k1/selfmodel/ports/projection_store.py) —
  ABC with 9 abstract methods. `read_family`/`write_family` are the two being renamed.
- [k1/selfmodel/service/family_model.py](k1/selfmodel/service/family_model.py) —
  `FamilyModelService.get_view()` is the path `Composer → store.read_family()`.
- [k1/selfmodel/adapters/memory_projection_store.py](k1/selfmodel/adapters/memory_projection_store.py) —
  in-memory ABC impl; updates `_family` dict (rename internal symbol to `_space`).
- [k1/selfmodel/adapters/sqlite_projection_store.py](k1/selfmodel/adapters/sqlite_projection_store.py) —
  durable impl; SQL DDL table name `family_projection` becomes `space_projection`. See E0.4.
- [k1/selfmodel/kernel/bootstrap.py](k1/selfmodel/kernel/bootstrap.py) —
  `SelfModelServiceBundle` dataclass + `build_self_model_bundle(family_space_id=...)`.
- [k1/selfmodel/service/situation_composer.py](k1/selfmodel/service/situation_composer.py) —
  consumer of `FamilyModelService.get_view()`; builds `RelationsSubset`.
- [k1/selfmodel/service/capsule_builder.py](k1/selfmodel/service/capsule_builder.py) —
  `_render_household()` reads `frame.relations.projected_others` and emits the
  `household_block` text. Rename method to `_render_space_graph()` and assign to
  `space_graph_block`.
- [k1/concierge/config/kernel.py](k1/concierge/config/kernel.py) —
  `KernelConfig.selfmodel_family_space_id` (line ~144).
- [k1/kernel/service.py](k1/kernel/service.py) — S2.6 block (lines ~1218–1251)
  and P3.5 block (lines ~1759) pass `family_space_id=` kwarg.
- [k1/concierge/prompt/builder.py](k1/concierge/prompt/builder.py) — stage 9.5
  preamble (line ~919) hardcodes `[household]` and `WHAT family context`.
- [k1/concierge/actors/front.py](k1/concierge/actors/front.py) — calls
  `self_model.render_capsule()` (line ~842). No rename needed; just verify it still works.

### E0.1 — Rename `contracts/family_model.py` → `contracts/space_graph.py`

#### Issue E0.1.1 — File move + symbol rename

```powershell
git mv k1/selfmodel/contracts/family_model.py k1/selfmodel/contracts/space_graph.py
```

In the new file, apply these exact symbol renames:

| Old | New |
|---|---|
| `FamilyMemberRef` | `ActorRef` |
| `RelationshipEdge` | `SpaceEdge` |
| `FamilySelfModelSnapshot` | `SpaceGraphSnapshot` |
| `RoutineRef` | _(unchanged)_ |
| `FamilySelfModelSnapshot.family_space_id` | `SpaceGraphSnapshot.space_id` |
| `__all__ = ["FamilyMemberRef", "RelationshipEdge", "RoutineRef", "FamilySelfModelSnapshot"]` | `__all__ = ["ActorRef", "SpaceEdge", "RoutineRef", "SpaceGraphSnapshot"]` |

Field shapes (count, types, defaults) MUST be preserved exactly. Only names change.

Update docstrings:

- `"Stable reference to a household member."` → `"Stable reference to an actor in a space."`
- `"One directed edge in the family graph adjacent to the actor."` → `"One directed edge in the space graph adjacent to the actor."`
- `"Family view projected for a single actor at (T, D)."` → `"Space graph projected for a single actor at (T, D)."`

#### Issue E0.1.2 — Keep deprecated aliases for one release

Add at the bottom of `contracts/space_graph.py`:

```python
# --- Deprecated aliases (kept for one release; remove in next major) ---
# Existing call sites outside k1/selfmodel/ are zero (verified May 2026), but the
# YAML constitution bodies and external integrations may still reference the old
# names. Removing them is a follow-up task tracked separately.
FamilyMemberRef = ActorRef                  # noqa: PYI042
RelationshipEdge = SpaceEdge                # noqa: PYI042
FamilySelfModelSnapshot = SpaceGraphSnapshot  # noqa: PYI042
```

These aliases let any forgotten import path still resolve. Remove them in a future
cleanup once a grep confirms zero references.

#### Issue E0.1.3 — Update intra-selfmodel imports

Search and replace inside `k1/selfmodel/` only:

```powershell
# Verify hits first:
grep -rn "from k1.selfmodel.contracts.family_model" k1/selfmodel/
grep -rn "from .family_model" k1/selfmodel/contracts/
grep -rn "from .contracts.family_model" k1/selfmodel/
```

Then update each hit:

| Old import | New import |
|---|---|
| `from k1.selfmodel.contracts.family_model import FamilyMemberRef` | `from k1.selfmodel.contracts.space_graph import ActorRef` |
| `from k1.selfmodel.contracts.family_model import RelationshipEdge` | `from k1.selfmodel.contracts.space_graph import SpaceEdge` |
| `from k1.selfmodel.contracts.family_model import FamilySelfModelSnapshot` | `from k1.selfmodel.contracts.space_graph import SpaceGraphSnapshot` |
| `from k1.selfmodel.contracts.family_model import RoutineRef` | `from k1.selfmodel.contracts.space_graph import RoutineRef` |

Known internal call sites (from grep at planning time):

- `contracts/situation.py` — imports `RelationshipEdge`, `RoutineRef`
- `contracts/pattern.py` — imports `RoutineRef`
- `ports/projection_store.py` — imports `FamilySelfModelSnapshot`
- `ports/selffamily.py` — imports `FamilySelfModelSnapshot`
- `service/family_model.py` — imports all four
- `service/situation_composer.py` — imports `FamilySelfModelSnapshot`, `RelationshipEdge`
- `service/capsule_builder.py` — uses `family_block` / `household_block`
- `adapters/memory_projection_store.py` — imports `FamilySelfModelSnapshot`
- `adapters/sqlite_projection_store.py` — imports `FamilySelfModelSnapshot`

### E0.2 — Rename ports

#### Issue E0.2.1 — `ports/selffamily.py` → `ports/selfspace.py`

```powershell
git mv k1/selfmodel/ports/selffamily.py k1/selfmodel/ports/selfspace.py
```

Apply renames in the new file:

| Old | New |
|---|---|
| `ISelfFamilyPort` | `ISelfSpacePort` |
| `def get_family_view(self, ...)` | `def get_space_view(self, ...)` |
| Return type `FamilySelfModelSnapshot` | `SpaceGraphSnapshot` |
| Imports updated to `space_graph` module | |

The other two methods (`get_self`, `update_layer`) keep their signatures unchanged.

#### Issue E0.2.2 — `ports/projection_store.py` method renames

Two abstract methods on `IProjectionStorePort` are renamed:

```python
# OLD
@abstractmethod
def read_family(self, family_space_id: str) -> tuple[FamilySelfModelSnapshot | None, StoreReadResult]: ...
@abstractmethod
def write_family(self, snapshot: FamilySelfModelSnapshot, *, writer_id: str) -> StoreWriteResult: ...

# NEW
@abstractmethod
def read_space(self, space_id: str) -> tuple[SpaceGraphSnapshot | None, StoreReadResult]: ...
@abstractmethod
def write_space(self, snapshot: SpaceGraphSnapshot, *, writer_id: str) -> StoreWriteResult: ...
```

The other 7 abstract methods (`read_self`, `write_self`, `read_constitution`,
`write_constitution`, `upsert_amendment`, `append_signature`, `freshness`) are unchanged.

Update the module imports to pull `SpaceGraphSnapshot` from `contracts.space_graph`.

#### Issue E0.2.3 — `ports/__init__.py` re-exports

Replace `ISelfFamilyPort` with `ISelfSpacePort` in `__all__` and the import line.
Other re-exports unchanged.

### E0.3 — Rename `service/family_model.py` → `service/space_graph.py`

#### Issue E0.3.1 — File move + symbol renames

```powershell
git mv k1/selfmodel/service/family_model.py k1/selfmodel/service/space_graph.py
```

| Old | New |
|---|---|
| `FAMILY_MODEL_WRITER_ID = "selfmodel:family_model_service"` | `SPACE_GRAPH_WRITER_ID = "selfmodel:space_graph_service"` |
| `class FamilyViewResult` | `class SpaceViewResult` |
| `class FamilyModelService` | `class SpaceGraphService` |
| `FamilyModelService.get_view(actor_id, family_space_id)` | `SpaceGraphService.get_view(actor_id, space_id)` |
| `FamilyModelService.get_member(family_space_id, member_id)` | `SpaceGraphService.get_member(space_id, member_id)` |
| `FamilyModelService.freshness(family_space_id)` | `SpaceGraphService.freshness(space_id)` |
| `FamilyModelService.update_routines(family_space_id, routines)` | `SpaceGraphService.update_routines(space_id, routines)` |
| Internal calls `self._store.read_family(...)` | `self._store.read_space(...)` |
| Internal calls `self._store.write_family(...)` | `self._store.write_space(...)` |

Module-private helpers `_filter_adjacent_edges` and `_adjacent_member_ids` keep their
signatures; their type annotations switch `RelationshipEdge` → `SpaceEdge`.

#### Issue E0.3.2 — `service/__init__.py` re-exports

```python
# OLD: from k1.selfmodel.service.family_model import FAMILY_MODEL_WRITER_ID, FamilyModelService, FamilyViewResult
# NEW:
from k1.selfmodel.service.space_graph import (
    SPACE_GRAPH_WRITER_ID,
    SpaceGraphService,
    SpaceViewResult,
)

__all__ = [
    ...,
    "SPACE_GRAPH_WRITER_ID",
    "SpaceGraphService",
    "SpaceViewResult",
    ...,
]
```

### E0.4 — Update adapters

#### Issue E0.4.1 — `adapters/memory_projection_store.py`

Apply these in-place edits (no file move):

- `_family` instance dict → `_space`
- `read_family()` method → `read_space()` (rename + parameter `family_space_id` → `space_id`)
- `write_family()` method → `write_space()`
- Imports update to `contracts.space_graph.SpaceGraphSnapshot`
- Test helper `mark_stale("family:smith")` still uses the projection key string as-is —
  that key format is opaque and unchanged.

#### Issue E0.4.2 — `adapters/sqlite_projection_store.py`

Two surfaces:

**(a) Python method signatures**: same rename as the in-memory adapter
(`read_family` → `read_space`, `write_family` → `write_space`).

**(b) SQLite DDL** (`migrations/0001_initial.sql` or a new migration):

The table `family_projection` is renamed to `space_projection`. Because the kernel
ships with an `enable_self_model=False` default and the SQLite store has no published
production data yet (M0/M3 scaffold only), the safest path is:

```sql
-- migrations/0002_rename_family_to_space.sql
ALTER TABLE family_projection RENAME TO space_projection;
ALTER TABLE space_projection RENAME COLUMN family_space_id TO space_id;
```

Plus update `adapters/sqlite_migrations.py` to register `0002` and bump the schema
version constant. Existing SQLite files (if any in dev environments) will migrate
automatically on next boot.

#### Issue E0.4.3 — `adapters/grounding_capsule_renderer.py`

Reads `bundle.family_model` and `bundle.family_space_id` — update to
`bundle.space_graph` and `bundle.space_id`. No other shape changes.

#### Issue E0.4.4 — `adapters/__init__.py`

No changes (only re-exports `InMemoryProjectionStore` which keeps its class name).

### E0.5 — Update `kernel/bootstrap.py` (the `SelfModelServiceBundle`)

#### Issue E0.5.1 — `SelfModelServiceBundle` field renames

```python
@dataclass
class SelfModelServiceBundle:
    store: IProjectionStorePort
    self_model: SelfModelService
    space_graph: SpaceGraphService    # was: family_model: FamilyModelService
    constitution: ConstitutionService
    composer: SituationFrameComposer
    evaluator: PolicyEvaluator
    identity: IdentitySessionManager
    amendments: AmendmentService
    validator: Ed25519SignatureChainValidator
    bootstrap: BootstrapResult
    capsule_builder: GroundingCapsuleBuilder
    citation_builder: CitationPackBuilder
    space_id: str                     # was: family_space_id: str
    constitution_id: str = BOOTSTRAP_CONSTITUTION_ID_V1
    safe_mode: bool = False
    started_at_ms: int = 0
```

#### Issue E0.5.2 — `build_self_model_bundle()` kwarg rename

```python
# OLD
def build_self_model_bundle(
    *, bus, hil_service, projection_db_path, family_space_id, ...
) -> SelfModelServiceBundle: ...

# NEW
def build_self_model_bundle(
    *, bus, hil_service, projection_db_path, space_id, ...
) -> SelfModelServiceBundle: ...
```

Inside the function:

- `family_model = FamilyModelService(store=store)` → `space_graph = SpaceGraphService(store=store)`
- `family_space_id=family_space_id` (assigned to bundle) → `space_id=space_id`
- `SituationFrameComposer(..., family_model=family_model, family_space_id=family_space_id)` →
  `SituationFrameComposer(..., space_graph=space_graph, space_id=space_id)` _(see E0.5.3)_

#### Issue E0.5.3 — `SituationFrameComposer` constructor

`SituationFrameComposer.__init__` accepts the new names; internal references
(`self._family_model`, `self._family_space_id`) → (`self._space_graph`, `self._space_id`).
Method call `self._family_model.get_view(actor_id, self._family_space_id)` →
`self._space_graph.get_view(actor_id, self._space_id)`.

The `RelationsSubset` dataclass field `family_routines` (referenced by capsule renderer)
is renamed to `space_routines` _only if_ it exists — verify via grep before editing.
If absent, skip.

### E0.6 — Update `KernelConfig` + kernel service wiring

#### Issue E0.6.1 — `k1/concierge/config/kernel.py`

```python
# OLD
selfmodel_family_space_id: str = "family:default"

# NEW
selfmodel_space_id: str = "family:default"   # value kept; only field name changes
```

The default value `"family:default"` stays unchanged — `space_id` is just a string;
the family vertical chooses `family:smith`, the health vertical would choose
`clinic:mayo:ward_3`, etc.

#### Issue E0.6.2 — `k1/kernel/service.py` S2.6 + P3.5

S2.6 block (line ~1218):

```python
self._self_model_bundle = build_self_model_bundle(
    bus=self._async_bus,
    hil_service=self._hil_service,
    projection_db_path=self._config.selfmodel_projection_db_path,
    space_id=self._config.selfmodel_space_id,           # renamed kwarg + field
)
```

P3.5 block (line ~1759) — no field rename needed; only verify it does not access
`bundle.family_space_id` anywhere. If it does, switch to `bundle.space_id`.

#### Issue E0.6.3 — `k1/kernel/WIRING.md`

One line references `family_space_id=config.selfmodel_family_space_id`. Update both
sides: `space_id=config.selfmodel_space_id`.

### E0.7 — Update concierge prompt builder + capsule renderer block labels

> **Context (May 2026 prompt refactor)**: The Stage 9.5 assembly pipeline was
> significantly redesigned after M0 was originally drafted. The old flat
> `[grounding]` preamble no longer exists. The current live architecture is:
>
> ```
> IDENTITY
>   └─ GROUNDING PROTOCOL names [self]/[household]/[space_graph_block]
> ACTIVE MEMBER block  ← _build_active_member_block() promotes self_block + household_block
> == NOW ==
> == AFFECT STATE ==
> == CONSCIENCE ==
> ... rule sections ...
> == REFERENCE PROFILE ==  ← _render_capsule_without_conscience() body (prefs/hobbies/goals/routines/context/freshness)
> ```
>
> M0 must update ALL five surfaces below. Missing any one leaves `household_block`
> references scattered across production code after the rename.

#### Issue E0.7.1 — `GroundingCapsule.household_block` → `space_graph_block`

In `k1/selfmodel/contracts/capsule.py`:

```python
@dataclass(frozen=True)
class GroundingCapsule:
    # ... other blocks unchanged ...
    space_graph_block: str = ""        # was: household_block: str = ""
    # ... other blocks unchanged ...
```

In `as_prompt_text()`, replace the `household_block` reference with `space_graph_block`.
Keep `family_block` as the legacy fallback (deprecated since M0–M5).

#### Issue E0.7.2 — `service/capsule_builder.py`

```python
# OLD
def _render_household(self, frame: SituationFrame) -> str: ...
# at the bottom of build():
household_block = self._render_household(frame)

# NEW
def _render_space_graph(self, frame: SituationFrame) -> str: ...
# at the bottom of build():
space_graph_block = self._render_space_graph(frame)
```

The block text format is unchanged. Only the method name and the dataclass field
assignment change. The `_render_household` body that joins `[household]` header lines
should switch the header to `[space]`.

#### Issue E0.7.3 — `k1/concierge/prompt/builder.py` — four surfaces

After the May 2026 prompt refactor, `builder.py` has four distinct references to
`household_block` / `[household]` that all need updating:

**(a) `_build_active_member_block()` helper (line ~1179)**

This method promotes `self_block + household_block` to the very top of the prompt.
After the rename, update the two `getattr` calls and the local variable names:

```python
# OLD
self_block = getattr(grounding_capsule, "self_block", "") or ""
household_block = getattr(grounding_capsule, "household_block", "") or ""
if not self_block and not household_block:
    return ""
# ...
if household_block:
    parts.append(household_block)

# NEW
self_block = getattr(grounding_capsule, "self_block", "") or ""
space_graph_block = getattr(grounding_capsule, "space_graph_block", "") or ""
if not self_block and not space_graph_block:
    return ""
# ...
if space_graph_block:
    parts.append(space_graph_block)
```

Also update the docstring: `"``household_block`` only"` → `"``space_graph_block`` only"`.

**(b) `_render_capsule_without_conscience()` helper (line ~1208)**

This method renders the REFERENCE PROFILE tail WITHOUT conscience/self/household blocks.
After the rename:

```python
# OLD
household_block = getattr(grounding_capsule, "household_block", "") or ""
# ...
household_slot = (
    "" if household_block else (getattr(grounding_capsule, "family_block", "") or "")
)
ordered = [
    identity_slot,
    ...
    household_slot,
    ...
]

# NEW
space_graph_block = getattr(grounding_capsule, "space_graph_block", "") or ""
# ...
space_slot = (
    "" if space_graph_block else (getattr(grounding_capsule, "family_block", "") or "")
)
ordered = [
    identity_slot,
    ...
    space_slot,
    ...
]
```

Also update the docstring: `"household_block (promoted to ACTIVE MEMBER…)"` →
`"space_graph_block (promoted to ACTIVE MEMBER…)"`.

**(c) `== REFERENCE PROFILE ==` preamble strings (line ~1003)**

The late grounding preamble currently reads:

```python
preamble = (
    "== REFERENCE PROFILE (live projection) ==\n"
    "Look up facts here when personalizing a response. These supplement\n"
    "the [self]/[household] blocks already shown above.\n"   # <-- update
    "- [preferences]  ..."
    ...
)
```

Update the `[household]` reference to `[space]`:

```python
preamble = (
    "== REFERENCE PROFILE (live projection) ==\n"
    "Look up facts here when personalizing a response. These supplement\n"
    "the [self]/[space] blocks already shown above.\n"   # updated
    "- [preferences]  ..."
    ...
)
```

**(d) Stage 9.5 comment block (line ~946)**

The multi-line comment above Stage 9.5 currently says:
`"The remaining capsule blocks ([self] / [preferences] / [household] / etc.)"`
Update `[household]` → `[space]` in both the comment and the `== ACTIVE MEMBER ==`
banner string inside `_build_active_member_block`:

```python
# OLD banner
"== ACTIVE MEMBER (authoritative — read before all rules) ==",
"Ground truth for who you are talking to and their household.\n"

# NEW banner
"== ACTIVE MEMBER (authoritative — read before all rules) ==",
"Ground truth for who you are talking to and their space.\n"
```

#### Issue E0.7.4 — `k1/concierge/prompt/sections.py` IDENTITY GROUNDING PROTOCOL

The May 2026 IDENTITY rewrite added an explicit GROUNDING PROTOCOL section that
names `[household]` twice. After the rename both must say `[space]`:

```python
# OLD (lines ~62–65 and ~93 in sections.py)
  [household]  Everyone in the home: roster, roles, relationships.
               → Before naming, referencing, or inferring ANY family member,
                 look them up here.
# ...
- [self] + [household]: Injected at the top. Authoritative ground truth.

# NEW
  [space]      Everyone in the space: roster, roles, relationships.
               → Before naming, referencing, or inferring ANY member,
                 look them up here.
# ...
- [self] + [space]: Injected at the top. Authoritative ground truth.
```

Verify that `k1/concierge/prompt/back_prompt.py` line 200 (`household - chores, laundry…`)
and `k1/concierge/fsm/phase1.py` line 303 are domain-routing terms — **leave those
alone**. They describe a routing domain, not the selfmodel block.

### E0.8 — Update tests

#### Issue E0.8.1 — File renames under `tests/k1/selfmodel/`

```powershell
git mv tests/k1/selfmodel/contracts/test_family_model_shapes.py `
       tests/k1/selfmodel/contracts/test_space_graph_shapes.py

git mv tests/k1/selfmodel/service/test_family_model_service.py `
       tests/k1/selfmodel/service/test_space_graph_service.py
```

#### Issue E0.8.2 — Mass import update

Apply the same import/name substitutions used in production code to every test file
under `tests/k1/selfmodel/`. Affected test files (from inventory):

- `contracts/test_space_graph_shapes.py` (renamed)
- `service/test_space_graph_service.py` (renamed)
- `service/test_situation_composer.py`
- `service/test_capsule_builder.py`
- `service/test_composer_helpers.py`
- `ports/test_projection_store_abc.py`
- `ports/test_protocols.py`
- `adapters/test_memory_projection_store.py`
- `adapters/test_sqlite_projection_store.py`
- `adapters/test_grounding_capsule_renderer.py`
- `invariants/test_e2_default_deny_visibility.py`
- `invariants/test_e5_no_raw_other_self.py`
- `invariants/test_e9_capsule_grounding.py`
- `integration/test_composer_to_policy.py`
- `integration/test_invariants_e2e.py`
- `test_module_layout.py`

Test class names follow source names: `TestFamilyModelService` → `TestSpaceGraphService`,
etc. Test method names that include `family` (e.g. `test_get_view_returns_family_snapshot`)
become `test_get_view_returns_space_snapshot`.

#### Issue E0.8.3 — `test_module_layout.py`

This test enforces "no cross-layer imports" and "port surface matches `__init__.py`".
Update the canonical port list it checks against:

```python
# OLD expected set:
{"IIdentityPort", "ICredentialPort", "IConstitutionPort", "ISelfFamilyPort", ...}

# NEW:
{"IIdentityPort", "ICredentialPort", "IConstitutionPort", "ISelfSpacePort", ...}
```

### E0.9 — Create `k1/selfmodel/docs/VERTICAL_INTEGRATION.md`

Create a new file at `k1/selfmodel/docs/VERTICAL_INTEGRATION.md` (create the `docs/`
subdirectory if missing) that documents how a new vertical hooks into the
domain-agnostic self-model. Required sections:

1. **Why SpaceGraph is domain-agnostic** — the same `SpaceGraphSnapshot` shape
   serves family, health, school, finance, gov, agri.
2. **Required artifacts for a new vertical** under `verticals/<name>/`:
   - `profile.py` — the source-of-truth profile dataclass (e.g. `FamilyProfile`,
     `PatientProfile`, `ClassroomProfile`)
   - `seeder.py` — a `SpaceDataSeeder` subclass that builds a `SpaceGraphSnapshot`
     from the profile and writes via `store.write_space(...)`
   - `acl_rules.py` — `VisibilityPolicy` rules specific to the vertical
   - `constitution.yaml` — the vertical's bootstrap constitution body
3. **`SpaceGraphSnapshot` semantics for each vertical** — the role taxonomy and
   edge kinds table (re-use the ADR-3 table).
4. **Wiring checklist** — exact code changes:
   - Set `KernelConfig.selfmodel_space_id = "<vertical>:<instance>"`
   - Mount the vertical's seeder in the boot sequence after `start_kernel()`
   - Register the vertical's `VisibilityPolicy` rules
   - Load the vertical's constitution via `ensure_bootstrap_constitution(body_path=...)`
5. **Anti-patterns** — what NOT to do:
   - Do not import from `verticals/<name>/` inside `k1/selfmodel/`
   - Do not add domain-specific fields to `SpaceGraphSnapshot` (use the generic
     `dict[str, object]` payload on `ActorRef.visible_attributes` if you need extra data)
   - Do not hardcode `[household]` / `[care_team]` / `[classroom]` strings in
     `k1/concierge/prompt/builder.py` — the capsule renderer is responsible for the
     final block text via `space_graph_block`
6. **Multi-vertical deployments** — discussion of how one K1 instance could host
   multiple `space_id` values (e.g. a SchoolOS+FamilyOS hybrid) by running multiple
   `KernelService` sessions, each with its own `space_id`.

Use the exact template provided in **Appendix A** below (under the ADR section).

### E0.10 — Acceptance criteria

M0 is complete when **all** of these pass:

1. `grep -rn "FamilyModelService\|FAMILY_MODEL_WRITER_ID\|FamilySelfModelSnapshot\|FamilyMemberRef\|RelationshipEdge\|ISelfFamilyPort\|read_family\|write_family\|get_family_view\|selfmodel_family_space_id\|family_space_id\|household_block" k1/ --include="*.py"`
   returns **only** the deprecated-alias lines in `contracts/space_graph.py` and the
   YAML constitution bodies (which are data, not code).
   Note: `household_block` should return **zero** hits — the field is renamed to
   `space_graph_block` in `contracts/capsule.py`, `service/capsule_builder.py`,
   `concierge/prompt/builder.py` (two helpers), and `concierge/prompt/sections.py`.
2. `python -m pytest tests/k1/selfmodel/ -q --no-cov` → 100% pass (no rename misses).
3. `python -c "from k1.selfmodel.contracts.space_graph import ActorRef, SpaceEdge, SpaceGraphSnapshot, RoutineRef; print('OK')"` → `OK`.
4. `python -c "from k1.selfmodel.service import SpaceGraphService, SPACE_GRAPH_WRITER_ID; print('OK')"` → `OK`.
5. `python -c "from k1.selfmodel.ports import ISelfSpacePort, IProjectionStorePort; assert hasattr(IProjectionStorePort, 'read_space') and hasattr(IProjectionStorePort, 'write_space'); print('OK')"` → `OK`.
6. `python -c "from k1.selfmodel.contracts.capsule import GroundingCapsule; import dataclasses; assert 'space_graph_block' in {f.name for f in dataclasses.fields(GroundingCapsule)}; print('OK')"` → `OK`.
7. `python -c "from k1.concierge.config.kernel import KernelConfig; import dataclasses; assert 'selfmodel_space_id' in {f.name for f in dataclasses.fields(KernelConfig)}; print('OK')"` → `OK`.
8. `python -c "from k1.kernel.bootstrap import start_kernel; print('OK')"` boots cleanly with
   `KernelConfig(enable_self_model=True, selfmodel_space_id='family:smith')` in test mode.
9. New file `k1/selfmodel/docs/VERTICAL_INTEGRATION.md` exists and renders correctly.
10. Existing M10 production smoke test (`scripts/boot_kernel.ps1`) still boots and reaches
    the REPL with no regressions.

### M0 Implementation Order

```text
Step 1:  git mv k1/selfmodel/contracts/family_model.py → space_graph.py; rename symbols + add aliases
Step 2:  git mv k1/selfmodel/ports/selffamily.py → selfspace.py; rename ISelfFamilyPort + get_family_view
Step 3:  Edit ports/projection_store.py: read_family/write_family → read_space/write_space
Step 4:  Edit ports/__init__.py re-exports
Step 5:  git mv k1/selfmodel/service/family_model.py → space_graph.py; rename symbols
Step 6:  Edit service/__init__.py re-exports
Step 7:  Edit service/situation_composer.py (constructor + internal calls)
Step 8:  Edit service/capsule_builder.py (_render_household → _render_space_graph)
Step 9:  Edit adapters/memory_projection_store.py (method renames, _family → _space)
Step 10: Edit adapters/sqlite_projection_store.py + add migration 0002
Step 11: Edit adapters/grounding_capsule_renderer.py (bundle.family_model → bundle.space_graph)
Step 12: Edit kernel/bootstrap.py (SelfModelServiceBundle fields + build_self_model_bundle kwarg)
Step 13: Edit contracts/capsule.py (household_block → space_graph_block)
Step 14: Edit k1/concierge/config/kernel.py (selfmodel_family_space_id → selfmodel_space_id)
Step 15: Edit k1/kernel/service.py S2.6 (family_space_id= → space_id=)
Step 16: Edit k1/concierge/prompt/builder.py — four surfaces (E0.7.3):
         (a) _build_active_member_block: household_block → space_graph_block
         (b) _render_capsule_without_conscience: household_block/household_slot → space_graph_block/space_slot
         (c) == REFERENCE PROFILE == preamble: [household] → [space]
         (d) Stage 9.5 comment block + ACTIVE MEMBER banner string
 Step 16b: Edit k1/concierge/prompt/sections.py IDENTITY GROUNDING PROTOCOL (E0.7.4):
          [household] → [space] in two places
Step 17: Edit k1/kernel/WIRING.md
Step 18: Rename test files (test_family_model_shapes.py, test_family_model_service.py)
Step 19: Mass-update all tests/k1/selfmodel/**/*.py imports and class names
Step 20: Create k1/selfmodel/docs/VERTICAL_INTEGRATION.md (see Appendix A)
Step 21: Run: python -m pytest tests/k1/selfmodel/ -q --no-cov  (must be 100%)
Step 22: Run: scripts/boot_kernel.ps1 -TestMode (must reach REPL prompt)
Step 23: Final grep sweep (acceptance criterion #1)
```

**Estimated touch surface**: ~20 production files + ~16 test files + 1 new doc file.
Pure renames; zero new logic.

### M0 Key gotchas

1. **YAML constitution bodies** under `k1/selfmodel/contracts/bootstrap_constitution.v0.yaml`
   and `.v1.yaml` may reference `FamilyMemberRef` or `FamilySelfModelSnapshot` as string
   identifiers. Those are data, not code — leave them; the deprecated aliases handle them.
2. **`RelationsSubset.family_routines`** — verify presence first via grep; only rename
   to `space_routines` if it exists, and update all readers.
3. **SQLite migration** — `ALTER TABLE … RENAME COLUMN` requires SQLite 3.25+ (released
   2018). Confirm CI's SQLite version before relying on it; otherwise use the
   create-new-table + copy-rows pattern.
4. **Deprecated aliases trap** — keep the aliases ONLY in `contracts/space_graph.py`.
   Do not add aliases for `FamilyModelService`, `ISelfFamilyPort`, `read_family`,
   `write_family`, `FAMILY_MODEL_WRITER_ID`, or `selfmodel_family_space_id` —
   those are internal API; a hard rename forces every caller to update.
5. **`bundle.family_space_id` external callers** — none today (verified May 2026 by grep
   over `k1/`), but the M12 `UiCoordinator` (not yet written) will read it. Make sure
   the rename lands before M12 starts.
6. **Prompt builder has four `household_block` references, not one** — `_build_active_member_block`,
   `_render_capsule_without_conscience`, the `== REFERENCE PROFILE ==` preamble string, and
   the Stage 9.5 comment block. The IDENTITY section in `sections.py` adds a fifth `[household]`
   in the GROUNDING PROTOCOL text. Missing any of these leaves cross-contamination that makes
   the acceptance criterion #1 grep fail and may cause the capsule to silently drop the
   space graph block at runtime (because `getattr(capsule, "household_block")` returns `""`
   while the actual data is in `space_graph_block`).
7. **Test class names** — the test class `TestSeedSpaceProjection` in M13 already
   exists in this plan (search for it). It depends on `SPACE_GRAPH_WRITER_ID` from
   `k1.selfmodel.service.space_graph` — confirming M0 must complete before M13 tests
   can be authored.

---

## M12 — Production Web UI Layer

**Goal**: Run the POC demo UI on top of the production K1 kernel. Browser chat with FSM badge,
affect meter, timeline, dashboard, and session state panels — all wired to `k1.kernel.bootstrap`.

**Read first before coding:**

- [poc/k1_poc/demo/web/app.py](poc/k1_poc/demo/web/app.py) — the FastAPI app to adapt
- [poc/k1_poc/demo/coordinator.py](poc/k1_poc/demo/coordinator.py) — the coordinator to adapt
  _(note: lives at `poc/k1_poc/demo/coordinator.py`, NOT under `web/`)_
- [poc/k1_poc/demo/web/renderer.py](poc/k1_poc/demo/web/renderer.py) — copy verbatim, zero POC deps
- [k1/kernel/bootstrap.py](k1/kernel/bootstrap.py) — production `start_kernel()` + `KernelRuntime` fields
- [k1/kernel/chat_repl.py](k1/kernel/chat_repl.py) — existing production terminal entry-point for patterns
- [k1/concierge/bus/topics.py](k1/concierge/bus/topics.py) — all production topic constants
- [k1/concierge/bus/builders.py](k1/concierge/bus/builders.py) — `build_user_input()`

**Critical discovery — how `start_kernel()` works in production:**

The production `k1.kernel.bootstrap.start_kernel()` already calls both `KernelService.startup()`
AND `KernelService.create_session()` internally in one shot and returns a complete `KernelRuntime`:

```python
# k1/kernel/bootstrap.py (actual production code — do NOT change this file)
async def start_kernel(config: KernelConfig | None = None) -> KernelRuntime:
    svc = KernelService(cfg)
    await svc.startup()                           # tier-1: bus, fabric, planner…
    session = await svc.create_session(session_id) # tier-2: SSM, concierge, writer…
    return KernelRuntime(
        bus=session.bus,
        hil_port=session.hil_port,       # ← NOTE: hil_port NOT hitl_coordinator
        weave_batcher=...,               # ← top-level field, NOT on runtime.fsm
        weave_policy=...,                # ← top-level field, NOT on runtime.fsm
        activity_tracker=...,            # ← top-level field, NOT on runtime.fsm
        capability_registry=None,        # ← always None in production
        adapter=None,                    # ← always None in production
        _service=svc,
        ...
    )
```

The coordinator calls `start_kernel(config)` **once** and gets back a fully started runtime.
No separate `_service.create_session()` call is needed in M12. The M13 seeding extension will
add a hook inside `KernelService.create_session()` itself.

**POC → Production field mapping — commit to memory before writing any code:**

| POC reads from `self._kernel.*` | Production reads from `runtime.*` | Why |
|---|---|---|
| `hitl_coordinator` | `hil_port` | field renamed in production KernelRuntime |
| `capability_registry` | NOT USED (always `None`) | skip `register_storyline_capabilities()` |
| `adapter` | NOT USED (always `None`) | not needed by web layer |
| `fsm.weave_batcher` | `weave_batcher` | moved to top-level in production |
| `fsm.weave_policy` | `weave_policy` | moved to top-level in production |
| `fsm.activity_tracker` | `activity_tracker` | moved to top-level in production |
| `poc.k1_poc.bus.topics.TOPIC_*` | `k1.concierge.bus.topics.TOPIC_*` | production module path |
| `poc.k1_poc.bus.builders.build_user_input` | `k1.concierge.bus.builders.build_user_input` | production module path |
| `poc.k1_poc.kernel.bootstrap.start_kernel` | `k1.kernel.bootstrap.start_kernel` | production bootstrap |
| `poc.k1_poc.kernel.bootstrap.KernelConfig` | `k1.concierge.config.kernel.KernelConfig` | production config |

**Production topic constants (`k1/concierge/bus/topics.py`) — verified by grep:**

```python
# Import either of these forms — both work:
from k1.concierge.bus.topics import (
    TOPIC_USER_INPUT,       # "k1.session.user.input.v1"
    TOPIC_FINAL_RESPONSE,   # "k1.response.final.v1"
    TOPIC_RESPONSE_STREAM,  # "k1.response.stream.v1"
    TOPIC_STATE_UPDATED,    # "k1.session.state.updated.v1"
    TOPIC_AFFECT_UPDATE,    # "k1.affect.update.v1"
    TOPIC_TOOL_STARTED,     # "k1.tool.started.v1"
    TOPIC_TOOL_COMPLETED,   # "k1.tool.completed.v1"
)
```

**Principle**: The POC web layer (`app.py`, `renderer.py`, `app.js`, `index.html`, `styles.css`)
is already correct. All surgery is in the coordinator and boot script.

---

### E12.1 — Package Scaffold and Static Assets

#### Issue E12.1.1 — Create `ui/web/__init__.py`

```python
"""ui.web — Web UI layer for the K1 kernel. Lives OUTSIDE k1/ (see ADR-1).

Entry point: python -m ui.web [--port 8765] [--host 127.0.0.1] [--test-mode]

Package structure:
    __main__.py    — uvicorn CLI entrypoint
    app.py         — FastAPI application (HTTP routes + WebSocket)
    coordinator.py — UiCoordinator (wraps k1.kernel as a library)
    renderer.py    — WebSocketRenderer (IRenderer over WebSocket)
    static/        — index.html, app.js, styles.css (copied from poc/k1_poc/demo/web/static/)
"""
from ui.web.coordinator import UiCoordinator
from ui.web.renderer import WebSocketRenderer

__all__ = ["UiCoordinator", "WebSocketRenderer"]
```

#### Issue E12.1.2 — Copy static assets verbatim

Run exactly these three copies (no edits to any of the three files):

```powershell
New-Item -ItemType Directory -Force ui\web\static | Out-Null
Copy-Item poc\k1_poc\demo\web\static\index.html  ui\web\static\index.html
Copy-Item poc\k1_poc\demo\web\static\app.js      ui\web\static\app.js
Copy-Item poc\k1_poc\demo\web\static\styles.css  ui\web\static\styles.css
```

These files are pure browser assets. `index.html` references `/static/styles.css` and loads
`app.js`. `app.js` connects WebSocket to `ws://` + `window.location.host` + `/ws`. Both
these paths are served identically by the production `app.py`. **No changes to either file.**

Verify after copy: `index.html` has `<title>FamilyOS`, `app.js` has `new WebSocket(`.

#### Issue E12.1.3 — Copy `renderer.py` verbatim

```powershell
Copy-Item poc\k1_poc\demo\web\renderer.py  ui\web\renderer.py
```

Open [poc/k1_poc/demo/web/renderer.py](poc/k1_poc/demo/web/renderer.py) and verify: its only
imports are `asyncio`, `json`, `logging`, `time`, `typing`. Zero `poc.*` imports. Safe to copy
unchanged into production.

The `WebSocketRenderer` class exposes:

- `add_connection(ws)` / `remove_connection(ws)` — async, uses `asyncio.Lock`
- `_broadcast(message: dict)` — async; prunes dead connections on error
- `_broadcast_sync(message: dict)` — sync fire-and-forget via `asyncio.ensure_future`
- `render_response(text, member, affect)` → `{type: "response", ...}`
- `render_stream_chunk(text, chunk_type)` → `{type: "stream_chunk", ...}`
- `render_proactive(text)` → `{type: "proactive", ...}`
- `render_weave(texts)` → `{type: "weave", ...}`
- `render_system(text)` → `{type: "system", ...}`
- `send_fsm_state(from_state, to_state, trigger)` → `{type: "fsm_state", ...}`
- `send_affect_update(emotion, valence)` → `{type: "affect_update", ...}`
- `send_tool_event(tool_name, actor, phase, **extra)` → `{type: "tool_event", ...}`
- `send_turn_info(turn, member)` → `{type: "turn_info", ...}`
- `send_activity(data)` → `{type: "activity", ...}`
- `send_timeline_entry(entry)` → `{type: "timeline", ...}`

---

### E12.2 — `coordinator.py` — `UiCoordinator`

**File**: `ui/web/coordinator.py`
**Template**: Read [poc/k1_poc/demo/coordinator.py](poc/k1_poc/demo/coordinator.py) fully before starting.
That file is 1725 lines. All changes are surgical import/field replacements.

#### Issue E12.2.1 — Module header and imports

```python
"""ui.web.coordinator — UiCoordinator: web adapter that uses k1 kernel as a library.

Template: poc/k1_poc/demo/coordinator.py (1725 lines).
Key differences from POC K1DemoCoordinator:
  1. Imports from k1.* not poc.k1_poc.*
  2. hil_port (not hitl_coordinator) — renamed in production KernelRuntime
  3. weave_batcher/policy/activity_tracker are top-level KernelRuntime fields, not on .fsm
  4. capability_registry is always None — skip register_storyline_capabilities()
  5. adapter is always None — not used by web layer
  6. No seed_memories in KernelConfig — seeding via SpaceDataSeeder in M13
  7. BackPool/BackTopicRouter/ReadyQueue: try k1.concierge.actors.* first, fall back to poc
  8. All bus topics from k1.concierge.bus.topics (not poc.k1_poc.bus.topics)
  9. start_kernel() already calls create_session() internally — one call is enough
"""
from __future__ import annotations
import asyncio, json, logging, time, uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
```

#### Issue E12.2.2 — `__init__()` — slot declarations

Copy the POC `__init__` structure. Apply these changes:

1. **Remove** `self.hitl_coordinator: Any = None` → **Replace with** `self.hil_port: Any = None`
2. **Remove** `self.capability_registry: Any = None` — never populated in production
3. **Remove** `self.adapter: Any = None` — never populated in production
4. **Add** these production-specific top-level slots:

```python
# Production weave fields (top-level on KernelRuntime, NOT on .fsm)
self.weave_batcher: Any = None
self.weave_policy: Any = None
self.activity_tracker: Any = None

# Production context refs
self.front_ctx: Any = None
self.back_ctx: Any = None
self.delta_applicator: Any = None
```

Full signature: `def __init__(self, *, test_mode: bool = False) -> None:`

#### Issue E12.2.3 — `initialize_system()` — 5-phase orchestrator

```python
async def initialize_system(self) -> bool:
    """Boot all 5 phases. Returns True on success."""
    try:
        await self._phase1_web_data()       # <1s: family profile stub
        await self._phase2_kernel_startup() # <5s: start_kernel() → full runtime
        await self._phase3_web_wiring()     # <1s: OutputChannel + bus subscriptions
        await self._phase4_consumer()       # <0.1s: start mailbox consumer task
        await self._phase5_health_check()   # <0.5s: 7 assertions

        self.system_ready = True
        logger.info("INIT: ALL 5 PHASES COMPLETE — system_ready=True")
        return True
    except Exception as exc:
        logger.error("INIT: Failed: %s", exc, exc_info=True)
        return False
```

#### Issue E12.2.4 — `_phase1_web_data()` — load family profile

```python
async def _phase1_web_data(self) -> None:
    """Phase 1: Load family profile and session config (<1s budget)."""
    family_config_path = getattr(self, "_family_config_path", None)
    if family_config_path:
        import json as _json
        with open(family_config_path, encoding="utf-8") as fh:
            data = _json.load(fh)
        self.family_profile = data.get("family_profile", {})
        self.session_config = data.get("session_config", {})
        self.device_registry = data.get("devices", {})
    else:
        # Default: POC Smith family stubs (pure data, no kernel dep — safe)
        from poc.k1_poc.demo.smith_family import (
            DEVICE_REGISTRY, SMITH_FAMILY_PROFILE, SMITH_SESSION_CONFIG,
        )
        self.family_profile = SMITH_FAMILY_PROFILE
        self.session_config = SMITH_SESSION_CONFIG
        self.device_registry = DEVICE_REGISTRY
    logger.info("Phase 1: family=%s members=%d",
        self.family_profile.get("family_name", "?"),
        len(self.family_profile.get("members", [])))
```

**Why import from `poc.k1_poc.demo.smith_family`?** That module is pure dicts/lists with no
kernel dependency. Safe to use in production for M12. Replaced by `data/families/smith.json` in M13.

#### Issue E12.2.5 — `_phase2_kernel_startup()` — production `start_kernel()` call

This is the core transformation. Compare with POC's `_phase2_kernel_startup()` in
[poc/k1_poc/demo/coordinator.py](poc/k1_poc/demo/coordinator.py) lines ~320–420.

```python
async def _phase2_kernel_startup(self) -> None:
    """Phase 2: Start production K1 kernel (<5s budget)."""
    phase_start = time.time()

    # PRODUCTION imports — NOT poc.k1_poc.kernel.bootstrap
    from k1.kernel.bootstrap import start_kernel
    from k1.concierge.config.kernel import KernelConfig

    config = KernelConfig(
        ordered_bus=True,
        capture_bus=False,
        test_mode=self._test_mode,
        session_mode="testing",
        session_id=f"web-{uuid.uuid4().hex[:8]}",
        enable_experience=True,
        enable_delta=True,
        enable_orchestrator=True,
        auto_start_consumer=False,   # UiCoordinator manages its own consumer
        # NO seed_memories here — done via SpaceDataSeeder in M13
        # Check k1/concierge/config/kernel.py for exact field names before coding
        # Run: grep -n "enable_hil\|enable_hitl" k1/concierge/config/kernel.py
    )

    # Single call: startup() + create_session() both happen inside start_kernel()
    runtime = await start_kernel(config)
    self._kernel = runtime

    # --- Copy runtime refs — USE PRODUCTION FIELD NAMES ---
    # Full field list: see k1/kernel/bootstrap.py KernelRuntime @dataclass
    self.bus               = runtime.bus
    self.router            = runtime.router
    self.front_mailbox     = runtime.front_mailbox
    self.back_mailbox      = runtime.back_mailbox
    self.session_state     = runtime.session_state
    self.model             = runtime.model
    self.fsm               = runtime.fsm
    self.front_dispatcher  = runtime.front_dispatcher
    self.back_dispatcher   = runtime.back_dispatcher
    self.experience_layer  = runtime.experience_layer
    self.delta_aggregator  = runtime.delta_aggregator
    self.delta_applicator  = runtime.delta_applicator
    self.orchestrator      = runtime.orchestrator
    self.ledger            = runtime.ledger
    self.ledger_store      = runtime.ledger_store
    self.dead_letter_consumer = runtime.dead_letter_consumer
    self.front_ctx         = runtime.front_ctx
    self.back_ctx          = runtime.back_ctx

    # CRITICAL: hil_port NOT hitl_coordinator
    self.hil_port          = runtime.hil_port

    # CRITICAL: top-level fields, NOT on runtime.fsm
    self.weave_batcher     = runtime.weave_batcher
    self.weave_policy      = runtime.weave_policy
    self.activity_tracker  = runtime.activity_tracker

    # --- BackPool / BackTopicRouter / ReadyQueue ---
    # Search k1 first: grep -rn "class BackPool" k1/
    # If migrated to k1.concierge.actors.*, use that. Otherwise fall back to poc.
    try:
        from k1.concierge.actors.back_pool import BackPool, BackPoolConfig
    except ImportError:
        from poc.k1_poc.actors.back_pool import BackPool, BackPoolConfig  # type: ignore[no-redef]
    self.back_pool = BackPool(BackPoolConfig())

    try:
        from k1.concierge.actors.back_router import BackTopicRouter
    except ImportError:
        from poc.k1_poc.actors.back_router import BackTopicRouter  # type: ignore[no-redef]
    self.back_topic_router = BackTopicRouter(back_pool=self.back_pool)

    try:
        from k1.concierge.actors.ready_queue import ReadyQueue
    except ImportError:
        from poc.k1_poc.actors.ready_queue import ReadyQueue  # type: ignore[no-redef]
    self.ready_queue = ReadyQueue()

    logger.info("Phase 2: kernel started test_mode=%s in %.3fs",
        self._test_mode, time.time() - phase_start)
```

#### Issue E12.2.6 — `_phase3_web_wiring()` — OutputChannel + bus subscriptions

```python
async def _phase3_web_wiring(self) -> None:
    """Phase 3: Wire OutputChannel for web rendering."""
    # Search for OutputChannel in k1: grep -rn "class OutputChannel" k1/
    # If it exists in k1, use it. Otherwise use the POC version (pure demo logic, safe).
    try:
        from k1.concierge.output.channel import OutputChannel
    except ImportError:
        from poc.k1_poc.demo.output_channel import OutputChannel  # type: ignore[no-redef]

    self.output_channel = OutputChannel(
        bus=self.bus,
        router=self.router,
        test_mode=self._test_mode,
    )
    # setup() subscribes to TOPIC_FINAL_RESPONSE and TOPIC_RESPONSE_STREAM
    if hasattr(self.output_channel, "setup"):
        self.output_channel.setup()
    logger.info("Phase 3: OutputChannel wired")
```

#### Issue E12.2.7 — `_phase4_consumer()` — start consumer task

```python
async def _phase4_consumer(self) -> None:
    self._consumer_task = asyncio.create_task(
        self._mailbox_consumer(), name="k1-web-mailbox-consumer"
    )
    logger.info("Phase 4: mailbox consumer task started")
```

#### Issue E12.2.8 — `_mailbox_consumer()` — poll loop

Copy the POC's `_mailbox_consumer()` exactly. **One change only**: import path for topics.

```python
async def _mailbox_consumer(self) -> None:
    """50ms poll loop for front and back mailboxes."""
    dedup_seen: set[int] = set()
    while True:
        try:
            work_found = False

            # Front mailbox — dedup + handler + experience tick
            if self.front_mailbox:
                for env in self.front_mailbox.drain():
                    eid = id(env)
                    if eid in dedup_seen:
                        continue
                    dedup_seen.add(eid)
                    if len(dedup_seen) > 500:
                        dedup_seen.clear()
                    work_found = True
                    try:
                        self.front_ctx.handler(env)
                        self._tick_experience_layer()
                    except RecursionError:
                        logger.critical("RecursionError in front handler — resetting FSM")
                        if self.fsm and hasattr(self.fsm, "force_reset"):
                            self.fsm.force_reset()
                    except Exception as exc:
                        logger.error("Front handler error: %s", exc, exc_info=True)

            # Back mailbox — create task per envelope
            if self.back_mailbox:
                for env in self.back_mailbox.drain():
                    work_found = True
                    asyncio.create_task(
                        self._run_back_handler(env),
                        name=f"back-{env.topic[:30]}",
                    )

            await asyncio.sleep(0.0 if work_found else 0.05)

        except asyncio.CancelledError:
            logger.info("Mailbox consumer cancelled")
            break
        except Exception as exc:
            logger.error("Consumer error: %s", exc, exc_info=True)
            await asyncio.sleep(0.1)
```

#### Issue E12.2.9 — `_run_back_handler()`, `_tick_experience_layer()`

```python
async def _run_back_handler(self, envelope: Any) -> None:
    try:
        self.back_ctx.handler(envelope)
    except RecursionError:
        logger.critical("RecursionError in back handler — resetting FSM")
        if self.fsm and hasattr(self.fsm, "force_reset"):
            self.fsm.force_reset()
    except Exception as exc:
        logger.error("Back handler error topic=%s: %s", envelope.topic, exc, exc_info=True)

def _tick_experience_layer(self) -> None:
    if self.experience_layer and hasattr(self.experience_layer, "tick"):
        try:
            self.experience_layer.tick()
        except Exception as exc:
            logger.warning("Experience layer tick error: %s", exc)
```

#### Issue E12.2.10 — `_phase5_health_check()`

```python
async def _phase5_health_check(self) -> None:
    failures = []
    if self.bus is None: failures.append("bus is None")
    if self.fsm is None: failures.append("fsm is None")
    if self.front_mailbox is None: failures.append("front_mailbox is None")
    if self.session_state is None: failures.append("session_state is None")
    if self.output_channel is None: failures.append("output_channel is None")
    if self._consumer_task is None or self._consumer_task.done():
        failures.append("consumer_task not running")
    if self.model is None and not self._test_mode:
        failures.append("model is None (non-test mode)")
    if failures:
        raise RuntimeError(f"Health check failed: {failures}")
    logger.info("Phase 5: health OK")
```

#### Issue E12.2.11 — `send_message()`

```python
async def send_message(self, text: str, member: str, device: str, turn: int) -> None:
    """Publish user message to bus and wait for response."""
    if not text.strip():
        return
    for d in (self.front_dispatcher, self.back_dispatcher):
        if d and hasattr(d, "reset"):
            try: d.reset()
            except Exception: pass
    if self.output_channel:
        if hasattr(self.output_channel, "set_member"):
            self.output_channel.set_member(member)
        if hasattr(self.output_channel, "start_turn"):
            self.output_channel.start_turn(turn)

    # PRODUCTION builder — NOT poc.k1_poc.bus.builders
    from k1.concierge.bus.builders import build_user_input
    envelope = build_user_input(payload={"text": text, "member": member, "device": device, "turn": turn})
    self.bus.publish(envelope)

    if self.output_channel and hasattr(self.output_channel, "wait_for_response"):
        try:
            await self.output_channel.wait_for_response(timeout=180.0)
        except Exception as exc:
            logger.error("Response wait failed: %s", exc)
```

#### Issue E12.2.12 — `get_status_report()`, `shutdown_system()`, singleton factory

```python
def get_status_report(self) -> dict:
    return {
        "system_ready": self.system_ready,
        "test_mode": self._test_mode,
        "fsm_state": self.fsm.state.name if self.fsm else "UNKNOWN",
        "bus_alive": self.bus is not None,
        "session_state_ready": self.session_state is not None,
        "output_channel_ready": self.output_channel is not None,
        "consumer_running": self._consumer_task is not None and not self._consumer_task.done(),
        "model_type": type(self.model).__name__ if self.model else "None",
        "hil_port_ready": self.hil_port is not None,
        "weave_batcher_ready": self.weave_batcher is not None,
    }

async def shutdown_system(self) -> None:
    if self._consumer_task and not self._consumer_task.done():
        self._consumer_task.cancel()
        try: await self._consumer_task
        except asyncio.CancelledError: pass
    if self.output_channel and hasattr(self.output_channel, "teardown"):
        self.output_channel.teardown()
    if self._kernel is not None:
        from k1.kernel.bootstrap import stop_kernel
        await stop_kernel(self._kernel)
    self.system_ready = False
    logger.info("UiCoordinator shutdown complete")


# --- Module-level singleton ---
_coordinator_instance: Optional[UiCoordinator] = None

def get_web_coordinator(*, test_mode: bool = False) -> UiCoordinator:
    global _coordinator_instance
    if _coordinator_instance is None:
        _coordinator_instance = UiCoordinator(test_mode=test_mode)
    return _coordinator_instance

def reset_coordinator() -> None:
    global _coordinator_instance
    _coordinator_instance = None
```

---

### E12.3 — `app.py` — FastAPI Application

**File**: `ui/web/app.py`
**Template**: Read [poc/k1_poc/demo/web/app.py](poc/k1_poc/demo/web/app.py) fully. The production
version has 4 targeted changes and otherwise copies everything.

#### Issue E12.3.1 — Module header and globals

```python
"""ui.web.app — FastAPI + WebSocket server for the K1 production web UI.

Adapted from poc/k1_poc/demo/web/app.py. Changes from POC:
  1. coordinator: ui.web.coordinator (not poc.k1_poc.demo.coordinator)
  2. family profile: from coordinator.family_profile slot (not POC SMITH_FAMILY_PROFILE import)
  3. session/control: no safe_get_section import from poc.k1_poc.actors
  4. _wire_web_timeline_hooks: uses k1.concierge.bus.topics (not poc.k1_poc.bus.topics)
"""
from __future__ import annotations
import asyncio, json, logging, time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ui.web.renderer import WebSocketRenderer

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="FamilyOS K1 Concierge")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

_coordinator: Any = None
_renderer: WebSocketRenderer = WebSocketRenderer()
_initialized: bool = False
_init_lock = asyncio.Lock()
_test_mode: bool = False
_family_config_path: str = ""
_turn_counter: int = 0
_current_member: str = "Alex"
_current_device: str = "alex_phone"
```

#### Issue E12.3.2 — `_ensure_coordinator()` — lazy init

```python
async def _ensure_coordinator() -> Any:
    global _coordinator, _initialized
    async with _init_lock:
        if _initialized and _coordinator is not None:
            return _coordinator

        # CHANGE 1: production coordinator
        from ui.web.coordinator import get_web_coordinator, reset_coordinator
        reset_coordinator()
        coord = get_web_coordinator(test_mode=_test_mode)
        if _family_config_path:
            coord._family_config_path = _family_config_path

        success = await coord.initialize_system()
        if not success:
            raise RuntimeError("UiCoordinator initialization failed")

        # Wire WebSocketRenderer into output channel
        if coord.output_channel and hasattr(coord.output_channel, "_renderer"):
            coord.output_channel._renderer = _renderer
            coord.output_channel._enable_spinner = False

        _wire_web_timeline_hooks(coord)
        _coordinator = coord
        _initialized = True
        logger.info("UiCoordinator initialized (test_mode=%s)", _test_mode)
        return _coordinator
```

#### Issue E12.3.3 — `_wire_web_timeline_hooks()` — bus → renderer subscriptions

```python
def _wire_web_timeline_hooks(coord: Any) -> None:
    """Wire FSM/affect/tool events from bus to WebSocket renderer."""
    # CHANGE 4: production topic import path
    from k1.concierge.bus.topics import (
        TOPIC_AFFECT_UPDATE, TOPIC_STATE_UPDATED,
        TOPIC_TOOL_COMPLETED, TOPIC_TOOL_STARTED,
    )
    from k1.bus.envelope import Envelope

    bus = coord.bus

    def _on_fsm(env: Envelope) -> None:
        try:
            p = json.loads(env.payload) if env.payload else {}
            _renderer.send_fsm_state(p.get("from_state","?"), p.get("to_state","?"), p.get("trigger","?"))
        except Exception: pass

    def _on_affect(env: Envelope) -> None:
        try:
            p = json.loads(env.payload) if env.payload else {}
            _renderer.send_affect_update(p.get("emotion","neutral"), p.get("valence",0.0))
        except Exception: pass

    def _on_tool(env: Envelope) -> None:
        try:
            p = json.loads(env.payload) if env.payload else {}
            phase = "started" if TOPIC_TOOL_STARTED in env.topic else "completed"
            _renderer.send_tool_event(
                tool_name=p.get("tool_name","?"), actor=p.get("actor","?"),
                phase=phase, duration_ms=p.get("duration_ms",0),
                success=p.get("success",True),
                args_summary=p.get("args_summary",""), result_summary=p.get("result_summary",""),
            )
        except Exception: pass

    bus.subscribe(TOPIC_STATE_UPDATED, _on_fsm)
    bus.subscribe(TOPIC_AFFECT_UPDATE, _on_affect)
    bus.subscribe(TOPIC_TOOL_STARTED, _on_tool)
    bus.subscribe(TOPIC_TOOL_COMPLETED, _on_tool)
```

#### Issue E12.3.4 — HTTP routes

Copy all 7 routes from [poc/k1_poc/demo/web/app.py](poc/k1_poc/demo/web/app.py) with these changes:

**`GET /api/family`** — CHANGE 2: use `_coordinator.family_profile`:

```python
@app.get("/api/family")
async def get_family() -> dict:
    if _coordinator and _coordinator.family_profile:
        return _coordinator.family_profile
    from poc.k1_poc.demo.smith_family import SMITH_FAMILY_PROFILE
    return SMITH_FAMILY_PROFILE
```

**`GET /api/session/control`** — CHANGE 3: inline `get_section` call, no POC import:

```python
@app.get("/api/session/control")
async def get_session_control() -> dict:
    if _coordinator is None or _coordinator.session_state is None:
        return {"available": False}
    try:
        ss = _coordinator.session_state
        control = ss.get_section("control")
        if control is None:
            return {"available": False, "reason": "control section not found"}
        result: dict = {"available": True}
        if hasattr(control, "to_dict"): result["data"] = control.to_dict()
        if hasattr(control, "fsm_overlay"):
            result["fsm_overlay"] = control.fsm_overlay
            result["overlay_bound"] = control.fsm_overlay is not None
        if hasattr(control, "get_metadata"): result["metadata"] = control.get_metadata()
        return result
    except Exception as exc:
        return {"available": False, "error": str(exc)}
```

**All other routes** (`GET /`, `/api/status`, `/api/dead-letters`, `/api/ledger/stats`,
`/api/session/state`) — copy verbatim from POC `app.py`. They reference `_coordinator.*` which
is identical in production.

#### Issue E12.3.5 — WebSocket handler

Copy the `@app.websocket("/ws")` handler from POC `app.py` verbatim with two changes:

**Change A** — init message: use `coord.family_profile` instead of importing `SMITH_FAMILY_PROFILE`:

```python
# POC:   from poc.k1_poc.demo.smith_family import SMITH_FAMILY_PROFILE; family_data = SMITH_FAMILY_PROFILE
# Prod:
family_data = coord.family_profile or {}
```

**Change B** — message handling: delegate user messages to `coord.send_message()`:

```python
# Instead of inlining build_user_input / bus.publish / output.wait_for_response:
if msg_type == "message":
    await _handle_user_message(coord, ws, msg)

# _handle_user_message becomes:
async def _handle_user_message(coord: Any, ws: WebSocket, msg: dict) -> None:
    global _turn_counter
    text = msg.get("text", "").strip()
    if not text: return
    member = msg.get("member", _current_member)
    device = msg.get("device", _current_device)
    _turn_counter += 1
    _renderer.send_turn_info(_turn_counter, member)
    await coord.send_message(text=text, member=member, device=device, turn=_turn_counter)
    # Send FSM state after response
    if coord.fsm:
        await ws.send_text(json.dumps({"type": "fsm_current", "state": coord.fsm.state.name}))
```

Copy `_handle_switch_member()`, `_handle_command()`, `_send_timeline()` verbatim from POC `app.py`
(they reference only `_current_member`, `_current_device`, and `coord.timeline` — all identical).

---

### E12.4 — `__main__.py` — uvicorn CLI Entrypoint

**File**: `ui/web/__main__.py`

```python
"""ui.web.__main__ — CLI entrypoint for the production web UI.

Usage: python -m ui.web [options]
  --port INT          uvicorn port (default: 8765)
  --host STR          bind host (default: 127.0.0.1)
  --test-mode         no real LLM (test stubs)
  --family-config PATH  path to family JSON
  --log-level STR     DEBUG|INFO|WARNING|ERROR (default: WARNING)
  --k0-endpoint URL   pseudo-K0 endpoint, e.g. http://localhost:8090
                      (also read from K0_ENDPOINT env var)
"""
from __future__ import annotations
import argparse, logging, os, sys

def main() -> None:
    parser = argparse.ArgumentParser(description="FamilyOS K1 Concierge — Web UI")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--test-mode", action="store_true")
    parser.add_argument("--family-config", default="")
    parser.add_argument("--log-level", default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--k0-endpoint", default=os.environ.get("K0_ENDPOINT", ""))
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )

    # Inject settings into app module globals BEFORE uvicorn imports app
    import ui.web.app as _app_module
    _app_module._test_mode = args.test_mode
    _app_module._family_config_path = args.family_config

    # Wire K0_ENDPOINT for KernelConfig (M14 hook)
    if args.k0_endpoint:
        os.environ["K0_ENDPOINT"] = args.k0_endpoint

    print(f"\n  FamilyOS K1 Concierge — Web UI")
    print(f"  Open http://{args.host}:{args.port} in your browser\n")

    import uvicorn
    uvicorn.run("ui.web.app:app", host=args.host, port=args.port,
        log_level=args.log_level.lower())

if __name__ == "__main__":
    main()
```

---

### E12.5 — `scripts/boot_web.ps1` — Boot Script

**File**: `scripts/boot_web.ps1`
**Read first**: [scripts/boot_kernel.ps1](scripts/boot_kernel.ps1) — copy its `.env` loading block exactly.

```powershell
[CmdletBinding()]
param(
    [int]    $Port         = 8765,
    [string] $FamilyConfig = "",
    [switch] $WithK0,
    [switch] $Test,
    [string] $LogLevel     = "WARNING"
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Load .env (copy this block verbatim from boot_kernel.ps1)
$EnvFile = Join-Path $PSScriptRoot ".." ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            [System.Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim(), "Process")
        }
    }
}

# Start pseudo-K0 if requested (M14)
$K0Job = $null
if ($WithK0) {
    $DbPath = Join-Path $PSScriptRoot ".." "data" "pseudo_k0.db"
    $K0Job = Start-Job -ScriptBlock {
        param($db); python -m scripts.pseudo_k0 --port 8090 --db $db
    } -ArgumentList $DbPath

    # Poll /k0/health for 10 seconds
    $ready = $false
    for ($i = 0; $i -lt 10; $i++) {
        Start-Sleep 1
        try {
            $r = Invoke-RestMethod "http://localhost:8090/k0/health" -TimeoutSec 1 -ErrorAction Stop
            if ($r.available -eq $true) { $ready = $true; break }
        } catch { }
    }
    if (-not $ready) {
        if ($K0Job) { Remove-Job -Job $K0Job -Force }
        throw "pseudo-K0 did not start within 10s"
    }
    $env:K0_ENDPOINT = "http://localhost:8090"
}

# Build args and launch
$PyArgs = @("--port", $Port, "--log-level", $LogLevel)
if ($Test)          { $PyArgs += "--test-mode" }
if ($FamilyConfig)  { $PyArgs += @("--family-config", $FamilyConfig) }
if ($env:K0_ENDPOINT) { $PyArgs += @("--k0-endpoint", $env:K0_ENDPOINT) }

try {
    python -m ui.web @PyArgs
} finally {
    if ($K0Job) { Stop-Job $K0Job -EA SilentlyContinue; Remove-Job $K0Job -Force -EA SilentlyContinue }
}
```

---

### E12.6 — Tests

#### Issue E12.6.1 — `tests/ui/web/__init__.py`

Empty file.

#### Issue E12.6.2 — `tests/ui/web/test_coordinator.py`

```python
"""Tests for UiCoordinator.
Run: python -m pytest tests/ui/web/test_coordinator.py -q --no-cov
"""
import asyncio, pytest
from unittest.mock import AsyncMock
from ui.web.coordinator import UiCoordinator, get_web_coordinator, reset_coordinator


class TestSlots:
    def test_hil_port_exists_hitl_coordinator_does_not(self):
        c = UiCoordinator()
        assert hasattr(c, "hil_port"), "hil_port must exist (production field name)"
        assert not hasattr(c, "hitl_coordinator"), "hitl_coordinator must NOT exist"

    def test_weave_fields_top_level(self):
        c = UiCoordinator()
        assert hasattr(c, "weave_batcher")
        assert hasattr(c, "weave_policy")
        assert hasattr(c, "activity_tracker")

    def test_no_capability_registry(self):
        c = UiCoordinator()
        assert not hasattr(c, "capability_registry")

    def test_no_adapter(self):
        c = UiCoordinator()
        assert not hasattr(c, "adapter")

    def test_system_ready_false_at_init(self):
        c = UiCoordinator()
        assert c.system_ready is False


class TestBoot:
    @pytest.mark.asyncio
    async def test_initialize_test_mode(self):
        reset_coordinator()
        coord = get_web_coordinator(test_mode=True)
        result = await coord.initialize_system()
        assert result is True
        assert coord.system_ready is True
        assert coord.bus is not None
        assert coord.fsm is not None
        assert coord.session_state is not None
        assert coord.output_channel is not None
        await coord.shutdown_system()

    @pytest.mark.asyncio
    async def test_consumer_task_running_after_boot(self):
        reset_coordinator()
        coord = get_web_coordinator(test_mode=True)
        await coord.initialize_system()
        assert coord._consumer_task is not None
        assert not coord._consumer_task.done()
        await coord.shutdown_system()
        assert coord._consumer_task.done()

    @pytest.mark.asyncio
    async def test_failure_returns_false(self):
        reset_coordinator()
        coord = UiCoordinator(test_mode=True)
        async def _fail(): raise RuntimeError("simulated")
        coord._phase2_kernel_startup = _fail
        result = await coord.initialize_system()
        assert result is False

    @pytest.mark.asyncio
    async def test_weave_not_on_fsm(self):
        reset_coordinator()
        coord = get_web_coordinator(test_mode=True)
        await coord.initialize_system()
        if coord.fsm is not None:
            assert not hasattr(coord.fsm, "weave_batcher"), \
                "weave_batcher must be on KernelRuntime not fsm"
        await coord.shutdown_system()

    @pytest.mark.asyncio
    async def test_shutdown_before_boot_is_safe(self):
        coord = UiCoordinator(test_mode=True)
        await coord.shutdown_system()  # must not raise


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_publishes_to_bus(self):
        reset_coordinator()
        coord = get_web_coordinator(test_mode=True)
        await coord.initialize_system()
        published = []
        coord.bus.publish = lambda env: published.append(env)
        if coord.output_channel and hasattr(coord.output_channel, "wait_for_response"):
            coord.output_channel.wait_for_response = AsyncMock(return_value=None)
        await coord.send_message("Hello", "Alex", "alex_phone", turn=1)
        assert len(published) == 1
        assert hasattr(published[0], "topic")
        await coord.shutdown_system()

    @pytest.mark.asyncio
    async def test_empty_message_no_publish(self):
        reset_coordinator()
        coord = get_web_coordinator(test_mode=True)
        await coord.initialize_system()
        published = []
        coord.bus.publish = lambda env: published.append(env)
        await coord.send_message("   ", "Alex", "alex_phone", turn=1)
        assert len(published) == 0
        await coord.shutdown_system()


class TestStatusReport:
    @pytest.mark.asyncio
    async def test_after_boot(self):
        reset_coordinator()
        coord = get_web_coordinator(test_mode=True)
        await coord.initialize_system()
        r = coord.get_status_report()
        assert r["system_ready"] is True
        assert r["bus_alive"] is True
        assert r["consumer_running"] is True
        assert r["fsm_state"] != "UNKNOWN"
        await coord.shutdown_system()

    def test_before_boot(self):
        c = UiCoordinator(test_mode=True)
        r = c.get_status_report()
        assert r["system_ready"] is False
```

#### Issue E12.6.3 — `tests/ui/web/test_app_routes.py`

```python
"""Tests for ui.web.app FastAPI routes.
Run: python -m pytest tests/ui/web/test_app_routes.py -q --no-cov
Requires: pip install httpx pytest-asyncio
"""
import json, pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

import ui.web.app as _app_module
from ui.web.app import app
from ui.web.coordinator import reset_coordinator


@pytest.fixture(autouse=True)
def reset_app():
    _app_module._coordinator = None
    _app_module._initialized = False
    _app_module._test_mode = True
    _app_module._turn_counter = 0
    reset_coordinator()
    yield
    _app_module._coordinator = None
    _app_module._initialized = False
    reset_coordinator()


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


class TestHTTPRoutes:
    @pytest.mark.asyncio
    async def test_get_index(self, client):
        r = await client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert b"FamilyOS" in r.content

    @pytest.mark.asyncio
    async def test_get_family(self, client):
        r = await client.get("/api/family")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    @pytest.mark.asyncio
    async def test_get_status_before_init(self, client):
        r = await client.get("/api/status")
        assert r.status_code == 200
        assert r.json()["system_ready"] is False

    @pytest.mark.asyncio
    async def test_dead_letters_before_init(self, client):
        r = await client.get("/api/dead-letters")
        assert r.status_code == 200
        assert "enabled" in r.json()

    @pytest.mark.asyncio
    async def test_ledger_stats_before_init(self, client):
        r = await client.get("/api/ledger/stats")
        assert r.status_code == 200
        assert "enabled" in r.json()

    @pytest.mark.asyncio
    async def test_session_state_before_init(self, client):
        r = await client.get("/api/session/state")
        assert r.status_code == 200
        data = r.json()
        assert data.get("available") is False or "reason" in data

    @pytest.mark.asyncio
    async def test_session_control_before_init(self, client):
        r = await client.get("/api/session/control")
        assert r.status_code == 200
        assert r.json().get("available") is False

    @pytest.mark.asyncio
    async def test_static_app_js(self, client):
        r = await client.get("/static/app.js")
        assert r.status_code == 200
```

#### Issue E12.6.4 — `tests/ui/web/test_renderer.py`

```python
"""Tests for WebSocketRenderer (copy from poc, zero kernel dep)."""
import asyncio, json, pytest
from unittest.mock import AsyncMock, MagicMock
from ui.web.renderer import WebSocketRenderer


@pytest.fixture
def renderer(): return WebSocketRenderer()

@pytest.fixture
def mock_ws():
    ws = MagicMock(); ws.send_text = AsyncMock(); return ws


class TestRenderer:
    @pytest.mark.asyncio
    async def test_add_remove_connection(self, renderer, mock_ws):
        await renderer.add_connection(mock_ws)
        assert mock_ws in renderer._connections
        await renderer.remove_connection(mock_ws)
        assert mock_ws not in renderer._connections

    @pytest.mark.asyncio
    async def test_broadcast_sends_json(self, renderer, mock_ws):
        await renderer.add_connection(mock_ws)
        await renderer._broadcast({"type": "test", "value": 42})
        mock_ws.send_text.assert_called_once()
        data = json.loads(mock_ws.send_text.call_args[0][0])
        assert data["type"] == "test"

    @pytest.mark.asyncio
    async def test_dead_connection_removed(self, renderer):
        dead = MagicMock()
        dead.send_text = AsyncMock(side_effect=Exception("gone"))
        await renderer.add_connection(dead)
        await renderer._broadcast({"type": "x"})
        assert dead not in renderer._connections

    def test_send_fsm_state_sync(self, renderer, mock_ws):
        asyncio.get_event_loop().run_until_complete(renderer.add_connection(mock_ws))
        renderer.send_fsm_state("LISTENING", "THINKING", "user_input")
        asyncio.get_event_loop().run_until_complete(asyncio.sleep(0))

    def test_send_affect_update_sync(self, renderer, mock_ws):
        asyncio.get_event_loop().run_until_complete(renderer.add_connection(mock_ws))
        renderer.send_affect_update("joy", 0.8)
        asyncio.get_event_loop().run_until_complete(asyncio.sleep(0))

    def test_send_tool_event_sync(self, renderer, mock_ws):
        asyncio.get_event_loop().run_until_complete(renderer.add_connection(mock_ws))
        renderer.send_tool_event("calendar_list_events", "alex", "started")
        asyncio.get_event_loop().run_until_complete(asyncio.sleep(0))
```

---

### E12.7 — Pre-flight Checklist (Run Before Writing Any Code)

```powershell
# 1. Verify production bootstrap — confirm hil_port and top-level weave fields
python -c "
from k1.kernel.bootstrap import KernelRuntime
import dataclasses
fields = {f.name for f in dataclasses.fields(KernelRuntime)}
assert 'hil_port' in fields, 'hil_port missing from KernelRuntime'
assert 'hitl_coordinator' not in fields, 'hitl_coordinator must not exist'
assert 'weave_batcher' in fields, 'weave_batcher must be top-level'
assert 'weave_policy' in fields, 'weave_policy must be top-level'
assert 'activity_tracker' in fields, 'activity_tracker must be top-level'
print('KernelRuntime fields OK')
"

# 2. Verify all 4 web timeline topics exist in production
python -c "
from k1.concierge.bus.topics import (
    TOPIC_STATE_UPDATED, TOPIC_AFFECT_UPDATE,
    TOPIC_TOOL_STARTED, TOPIC_TOOL_COMPLETED,
    TOPIC_FINAL_RESPONSE, TOPIC_RESPONSE_STREAM,
)
print('Topics OK')
"

# 3. Verify build_user_input signature
python -c "from k1.concierge.bus.builders import build_user_input; import inspect; print(inspect.signature(build_user_input))"

# 4. Check if BackPool is in k1 (may need POC fallback)
python -c "
try:
    from k1.concierge.actors.back_pool import BackPool
    print('BackPool: k1.concierge.actors.back_pool')
except ImportError:
    print('BackPool: NOT in k1, will use poc fallback')
"

# 5. Check if OutputChannel is in k1
python -c "
try:
    from k1.concierge.output.channel import OutputChannel
    print('OutputChannel: k1.concierge.output.channel')
except ImportError:
    print('OutputChannel: NOT in k1, will use poc fallback')
"

# 6. Check KernelConfig field for HIL (exact name may differ)
python -c "
import dataclasses
from k1.concierge.config.kernel import KernelConfig
fields = {f.name: f.default for f in dataclasses.fields(KernelConfig)}
print('HIL fields:', {k: v for k, v in fields.items() if 'hil' in k.lower()})
print('auto_start_consumer:', fields.get('auto_start_consumer', 'NOT FOUND'))
"
```

### E12.8 — Implementation Order

```
Step 1:  Create ui/web/__init__.py (E12.1.1)
Step 2:  Run powershell: Copy-Item for renderer.py and static/ (E12.1.2, E12.1.3)
Step 3:  Run pre-flight checklist (E12.7) — answer all 6 questions first
Step 4:  Write coordinator.py top-to-bottom (E12.2.1 → E12.2.12)
Step 5:  Write app.py (E12.3.1 → E12.3.5)
Step 6:  Write __main__.py (E12.4)
Step 7:  Write scripts/boot_web.ps1 (E12.5)
Step 8:  Write tests/ (E12.6.1 → E12.6.4)
Step 9:  Run: python -m pytest tests/ui/web/ -q --no-cov
Step 10: Boot manually: python -m ui.web --test-mode --port 8765
Step 11: Open browser http://localhost:8765 — verify FSM badge, member switcher
Step 12: Type "Hello" — verify streaming response in browser
```

---

## M13 — Family Data Seeding

**Goal**: Feed a real family profile (members, preferences, memories) into the production K1 kernel
at boot — into session beliefs (immediate) and optionally into the self-model projection store
(persistent). Available to Concierge on turn 1, no retrieval needed.

**Read first before coding:**

- [poc/k1_poc/demo/smith_family.py](poc/k1_poc/demo/smith_family.py) — `SMITH_FAMILY_PROFILE`, `DEVICE_REGISTRY`, `SMITH_SESSION_CONFIG`, `STORYLINE_TURNS` — the source of truth for Smith family data
- [poc/k1_poc/demo/preloaded_memories.py](poc/k1_poc/demo/preloaded_memories.py) — `PRELOADED_MEMORIES` list of 19 dicts, each with `type`, `content`, `source`, `tags`
- [k1/concierge/config/kernel.py](k1/concierge/config/kernel.py) — `KernelConfig.seed_memories: list[dict]` — the primary injection field
- [k1/concierge/config/concierge.py](k1/concierge/config/concierge.py) — `ConciergeConfig.seed_memories` — how seed_memories flows to Concierge
- [k1/selfmodel/contracts/space_graph.py](k1/selfmodel/contracts/space_graph.py) — `ActorRef`, `SpaceEdge`, `RoutineRef`, `SpaceGraphSnapshot` (was `family_model.py`)
- [k1/selfmodel/service/space_graph.py](k1/selfmodel/service/space_graph.py) — `SpaceGraphService.update_routines()`, `SPACE_GRAPH_WRITER_ID` (was `family_model.py`)
- [k1/selfmodel/ports/projection_store.py](k1/selfmodel/ports/projection_store.py) — `IProjectionStorePort.read_space()`, `write_space()`
- [k1/selfmodel/kernel/bootstrap.py](k1/selfmodel/kernel/bootstrap.py) — `SelfModelServiceBundle` dataclass with `store`, `space_graph`, `space_id`
- [k1/kernel/service.py](k1/kernel/service.py) — `KernelService` + `create_session()` phase markers
- [ui/web/coordinator.py](ui/web/coordinator.py) — `_phase2_kernel_startup()` where `KernelConfig` is built (M12 file)

**Critical architecture — 3 injection layers:**

| Layer | Mechanism | When seeded | Phase |
|---|---|---|---|
| L0 Session Beliefs | `KernelConfig.seed_memories` list passed to `start_kernel()` | Before `start_kernel()` | M12 phase2 |
| L1/L2 Self-Model | `store.write_space(SpaceGraphSnapshot)` | After `start_kernel()` returns | M13 phase2.5 |
| L3 K0 Episodic | `IBridgeCommandPort.submit_batch()` | After K0 bridge available | M14 prerequisite |

**Critical discovery — `KernelConfig.seed_memories` already works:**

`seed_memories` is a `list[dict]` on `KernelConfig` that flows into `ConciergeConfig.seed_memories`
during service setup. The Concierge reads these on every session creation and loads them into the
session's hot beliefs context — no changes to `KernelService` are needed for L0.

The seeder's job is only to **build** the `seed_memories` list from the `FamilyProfile` before
`KernelConfig` is created.

**Critical discovery — self-model writer_id:**

```python
# From k1/selfmodel/service/space_graph.py:
SPACE_GRAPH_WRITER_ID = "selfmodel:space_graph_service"

# The projection store's allowed_writers set must include this constant.
# Use it directly: store.write_space(snapshot, writer_id=SPACE_GRAPH_WRITER_ID)
```

**Critical discovery — `SpaceGraphSnapshot` fields (from `k1/selfmodel/contracts/space_graph.py`):**

```python
@dataclass(frozen=True)
class ActorRef:
    member_id: str        # "alex" "jordan" "riley" "nana_liz"
    display_name: str = ""
    role: str = ""        # "guardian" | "child" | "adult" | "guest"
    age_band: str = ""    # "infant" | "child" | "teen" | "adult"

@dataclass(frozen=True)
class SpaceGraphSnapshot:
    space_id: str          # "family:smith" — from KernelConfig.selfmodel_space_id
    revision: str = ""
    members: tuple[ActorRef, ...] = ()
    relations: tuple[SpaceEdge, ...] = ()
    routines: tuple[RoutineRef, ...] = ()
    composed_at_ms: int = 0
```

**Integration with M12:** The M12 coordinator's `_phase2_kernel_startup()` must be updated to:

1. Call `seeder.build_seed_memories(profile, device_id)` before creating `KernelConfig`
2. Pass result as `seed_memories=[...]` in `KernelConfig`
3. After `start_kernel()`, if `enable_self_model=True`, call `seeder.seed_space_projection(runtime._service.self_model_bundle, profile)`

---

### E13.1 — `verticals/family/profile.py` — Canonical FamilyProfile Schema

**No `verticals/family/` directory exists yet.** Create from scratch.

#### Issue E13.1.1 — Create `verticals/family/__init__.py`

```python
"""verticals.family — FamilyProfile schema and seeding utilities. Lives in verticals/, not k1/ (see ADR-3).

Main classes:
    FamilyProfile     — canonical family data model (loaded from JSON)
    FamilyMember      — single member with actor_id, preferences, device_ids
    FamilyMemoryEntry — a single preloaded memory (type/content/tags)
    SpaceDataSeeder   — converts FamilyProfile → KernelConfig.seed_memories + self-model

Designed so ui.web.coordinator can import ONLY from verticals.family.*
and have zero dependency on poc.k1_poc.*.
"""
from verticals.family.profile import FamilyMember, FamilyMemoryEntry, FamilyProfile
from verticals.family.seeder import SpaceDataSeeder

__all__ = ["FamilyProfile", "FamilyMember", "FamilyMemoryEntry", "SpaceDataSeeder"]
```

#### Issue E13.1.2 — Create `verticals/family/profile.py`

The `FamilyProfile` schema must map cleanly to `SpaceGraphSnapshot.members` (for self-model
seeding) and to the `seed_memories` list format (for L0 beliefs).

Note: `ActorRef` already exists in `k1.selfmodel.contracts.space_graph`. Do NOT re-define
it. `FamilyMember` (production data class) is a richer structure that gets **projected into**
`ActorRef` during self-model seeding.

```python
"""verticals.family.profile — Canonical FamilyProfile dataclass.

JSON schema: data/families/smith.json
Load: FamilyProfile.from_json("data/families/smith.json")
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class FamilyMember:
    """Single family member — richer than ActorRef, not frozen."""
    actor_id: str               # stable ID: "alex", "jordan", "riley", "nana_liz"
    name: str                   # display name: "Alex", "Riley"
    relation: str               # "parent" | "child" | "grandparent"
    age: int
    device_ids: list[str]       # e.g. ["alex_phone", "alex_laptop"]
    preferences: dict[str, Any] = field(default_factory=dict)
    access_level: str = "full_adult"  # "full_adult" | "child" | "limited" | "family_shared"
    occupation: str = ""
    grade: str = ""             # only for children

    def to_seed_dict(self) -> dict[str, Any]:
        """Convert to dict format for KernelConfig.seed_memories context block."""
        return {
            "actor_id": self.actor_id,
            "name": self.name,
            "relation": self.relation,
            "age": self.age,
            "access_level": self.access_level,
            "preferences": self.preferences,
            "device_ids": self.device_ids,
            "occupation": self.occupation,
            "grade": self.grade,
        }

    def age_band(self) -> str:
        """Convert age to ActorRef.age_band format."""
        if self.age < 3: return "infant"
        if self.age < 13: return "child"
        if self.age < 18: return "teen"
        return "adult"

    def role(self) -> str:
        """Convert relation to ActorRef.role format."""
        mapping = {
            "parent": "guardian",
            "child": "child",
            "grandparent": "adult",
            "adult": "adult",
            "guest": "guest",
        }
        return mapping.get(self.relation, "adult")


@dataclass
class FamilyMemoryEntry:
    """Single preloaded memory from the family's history."""
    memory_type: str            # "episodic" | "semantic" | "procedural"
    content: str
    tags: list[str] = field(default_factory=list)
    source: str = ""
    actor_id: Optional[str] = None  # None = family-level memory

    def to_seed_dict(self) -> dict[str, Any]:
        """Convert to KernelConfig.seed_memories dict format."""
        return {
            "type": self.memory_type,
            "content": self.content,
            "tags": self.tags,
            "source": self.source,
            "actor_id": self.actor_id,
        }


@dataclass
class FamilyProfile:
    """Canonical family profile — the central data object for M13.

    Loaded from JSON or imported from poc.k1_poc.demo.smith_family.
    Used by SpaceDataSeeder to produce seed_memories and self-model projections.
    """
    family_name: str
    space_id: str               # maps to KernelConfig.selfmodel_space_id: "family:smith"
    location: str
    timezone: str
    members: list[FamilyMember]
    devices: dict[str, dict]    # device_id → {member_actor_id, device_type, access_level}
    memories: list[FamilyMemoryEntry]
    session_config: dict[str, str] = field(default_factory=dict)  # tone, formality, verbosity
    dietary_restrictions: list[str] = field(default_factory=list)
    accessibility_needs: list[str] = field(default_factory=list)
    preferred_language: str = "en"

    @staticmethod
    def from_json(path: str | Path) -> "FamilyProfile":
        """Load FamilyProfile from a JSON file."""
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return FamilyProfile.from_dict(data)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "FamilyProfile":
        """Deserialize from a raw dict (e.g. parsed JSON)."""
        members = [
            FamilyMember(
                actor_id=m["actor_id"],
                name=m["name"],
                relation=m["relation"],
                age=m["age"],
                device_ids=m.get("device_ids", []),
                preferences=m.get("preferences", {}),
                access_level=m.get("access_level", "full_adult"),
                occupation=m.get("occupation", ""),
                grade=m.get("grade", ""),
            )
            for m in data.get("members", [])
        ]
        memories = [
            FamilyMemoryEntry(
                memory_type=e["type"],
                content=e["content"],
                tags=e.get("tags", []),
                source=e.get("source", ""),
                actor_id=e.get("actor_id"),
            )
            for e in data.get("memories", [])
        ]
        return FamilyProfile(
            family_name=data["family_name"],
            space_id=data.get("space_id", f"family:{data['family_name'].lower()}"),
            location=data.get("location", ""),
            timezone=data.get("timezone", "UTC"),
            members=members,
            devices=data.get("devices", {}),
            memories=memories,
            session_config=data.get("session_config", {}),
            dietary_restrictions=data.get("dietary_restrictions", []),
            accessibility_needs=data.get("accessibility_needs", []),
            preferred_language=data.get("preferred_language", "en"),
        )

    def member_by_device(self, device_id: str) -> Optional[FamilyMember]:
        """Return the FamilyMember who owns device_id, or None."""
        entry = self.devices.get(device_id)
        if entry is None:
            return None
        actor_id = entry.get("member_actor_id") or entry.get("member", "").lower()
        return self.member_by_actor(actor_id)

    def member_by_actor(self, actor_id: str) -> Optional[FamilyMember]:
        """Return FamilyMember by actor_id (case-insensitive)."""
        actor_id_lc = actor_id.lower().replace(" ", "_")
        for m in self.members:
            if m.actor_id.lower() == actor_id_lc:
                return m
        # Fallback: match by name
        for m in self.members:
            if m.name.lower() == actor_id.lower():
                return m
        return None

    def memories_for_actor(self, actor_id: str) -> list[FamilyMemoryEntry]:
        """Return memories tagged for actor_id OR family-level (actor_id=None)."""
        return [
            e for e in self.memories
            if e.actor_id is None or e.actor_id.lower() == actor_id.lower()
            or actor_id.lower() in [t.lower() for t in e.tags]
        ]

    def primary_device(self, actor_id: str) -> str:
        """Return the first device_id that maps to actor_id, or empty string."""
        for device_id, entry in self.devices.items():
            dev_actor = entry.get("member_actor_id") or entry.get("member", "").lower()
            if dev_actor.lower() == actor_id.lower():
                return device_id
        return ""
```

File: `verticals/family/profile.py`

#### Issue E13.1.3 — Create `verticals/family/smith.py` — Smith family as Python constants

This module is the production replacement for `poc.k1_poc.demo.smith_family` imports. Same data,
wrapped in `FamilyProfile`. After M13, all `poc.k1_poc.demo.smith_family` imports in `coordinator.py`
switch to `from verticals.family.smith import SMITH_PROFILE`.

```python
"""verticals.family.smith — Smith family default profile as a FamilyProfile instance.

Production replacement for poc.k1_poc.demo.smith_family.SMITH_FAMILY_PROFILE.
Data source: poc/k1_poc/demo/smith_family.py + poc/k1_poc/demo/preloaded_memories.py
JSON export: data/families/smith.json
"""
from __future__ import annotations

from verticals.family.profile import FamilyMember, FamilyMemoryEntry, FamilyProfile

# Members — actor_id is the stable lowercase identifier used by selfmodel
_MEMBERS = [
    FamilyMember(
        actor_id="alex", name="Alex", relation="parent", age=38,
        device_ids=["alex_phone", "alex_laptop"],
        occupation="Software engineer",
        access_level="full_adult",
        preferences={"office_temp_f": 72, "stress_eating": True, "dinner_no_screens": True},
    ),
    FamilyMember(
        actor_id="jordan", name="Jordan", relation="parent", age=36,
        device_ids=["jordan_phone"],
        occupation="Pediatric nurse",
        access_level="full_adult",
        preferences={"dietary": "shellfish allergy", "sleep_temp_f": 68,
                     "wake_buffer_hours": 2.5, "wake_style": "gentle"},
    ),
    FamilyMember(
        actor_id="riley", name="Riley", relation="child", age=8,
        device_ids=[],           # Riley has no device — parents relay her requests
        grade="3rd",
        access_level="child",
        preferences={"motivation_style": "mission",
                     "bedtime_routine": {"bath": "20:00", "story": "20:20", "lights_out": "20:40"}},
    ),
    FamilyMember(
        actor_id="nana_liz", name="Nana Liz", relation="grandparent", age=67,
        device_ids=["nana_ipad"],
        access_level="limited",
        preferences={"interface": "simplified",
                     "medication": {"name": "Amlodipine", "dose": "5mg", "time": "09:00"}},
    ),
]

_DEVICES = {
    "alex_phone":   {"member_actor_id": "alex",     "device_type": "iPhone",  "access_level": "full_adult"},
    "alex_laptop":  {"member_actor_id": "alex",     "device_type": "MacBook", "access_level": "full_adult"},
    "jordan_phone": {"member_actor_id": "jordan",   "device_type": "Android", "access_level": "full_adult"},
    "nana_ipad":    {"member_actor_id": "nana_liz", "device_type": "iPad",    "access_level": "limited"},
    "kitchen_hub":  {"member_actor_id": "shared",   "device_type": "Hub",     "access_level": "family_shared"},
}

_MEMORIES = [
    FamilyMemoryEntry("episodic",
        "Last Tuesday, Riley's swim bag was left at school. Jordan had to drive back. Riley cried for 20 minutes.",
        tags=["riley", "swim", "bag", "school", "forgot"], source="Session 2 weeks ago"),
    FamilyMemoryEntry("episodic",
        "Alex's last client demo (Meridian Corp) went over time by 25 min because slides weren't ready. Alex was stressed for 3 days after.",
        tags=["alex", "demo", "slides", "stress", "work"], source="Session 6 weeks ago"),
    FamilyMemoryEntry("semantic",
        "Jordan prefers to be woken no later than 12:30pm before a 3pm shift -- needs 2.5 hours to eat, shower, commute.",
        tags=["jordan", "wake", "shift", "schedule"], source="Learned from 14 sessions"),
    FamilyMemoryEntry("semantic",
        "Riley does best on homework when it's framed as a 'mission' with rewards. Sticker chart on fridge.",
        tags=["riley", "homework", "mission", "motivation"], source="Learned from 8 sessions"),
    FamilyMemoryEntry("semantic",
        "Nana Liz's doctor changed her BP meds to Amlodipine 5mg on Jan 15. She has trouble remembering the new pill vs. the old one.",
        tags=["nana", "nana_liz", "medication", "amlodipine", "bp"], source="Session 3 weeks ago"),
    FamilyMemoryEntry("semantic",
        "Alex stress-eats when anxious about work. Jordan has asked FamilyOS to subtly suggest healthy options instead.",
        tags=["alex", "eating", "stress", "health", "private"], source="Session from Jordan, private"),
    FamilyMemoryEntry("procedural",
        "Wednesday grocery delivery from New Seasons Market arrives between 4-6pm. Order must be placed by 10am.",
        tags=["grocery", "wednesday", "new_seasons", "delivery"], source="Routine, confirmed 11 times"),
    FamilyMemoryEntry("procedural",
        "Riley's bedtime routine: 8pm bath, 8:20 story, 8:40 lights out. Deviation causes next-day irritability.",
        tags=["riley", "bedtime", "routine", "bath"], source="Confirmed 23 times"),
    FamilyMemoryEntry("semantic",
        "Alex and Jordan have a rule: no screens at dinner table. FamilyOS should not interrupt between 6-7pm unless URGENT.",
        tags=["dinner", "dnd", "screens", "family_rule"], source="Set explicitly"),
    FamilyMemoryEntry("semantic",
        "Shellfish allergy -- Jordan. Severity: moderate. EpiPen location: kitchen drawer left of sink.",
        tags=["jordan", "allergy", "shellfish", "epipen", "medical"], source="Medical profile"),
    FamilyMemoryEntry("procedural",
        "Monday agenda: Riley school drop-off 7:45am, Alex standup 9am, grocery list review 10am, Riley swim practice pickup 4pm, family dinner 6pm.",
        tags=["monday", "agenda", "schedule", "todo", "riley", "alex"], source="Weekly planner"),
    FamilyMemoryEntry("procedural",
        "Tuesday agenda: Jordan dentist 10am, Alex client call 2pm, Riley homework help 4:30pm, taco Tuesday dinner 6pm.",
        tags=["tuesday", "agenda", "schedule", "todo", "jordan", "alex", "riley"], source="Weekly planner"),
    FamilyMemoryEntry("procedural",
        "Wednesday agenda: grocery order by 10am (New Seasons), Alex deep-work block 9am-12pm, Riley art class 3:30pm, grocery delivery 4-6pm, Jordan night shift starts 3pm.",
        tags=["wednesday", "agenda", "schedule", "todo", "alex", "riley", "jordan", "grocery"], source="Weekly planner"),
    FamilyMemoryEntry("procedural",
        "Thursday agenda: Alex team retrospective 10am, Riley piano lesson 4pm, Nana Liz video call 5pm, pizza night 6:30pm.",
        tags=["thursday", "agenda", "schedule", "todo", "alex", "riley", "nana"], source="Weekly planner"),
    FamilyMemoryEntry("procedural",
        "Friday agenda: Riley show-and-tell at school, Alex half-day (off after 1pm), family movie night 7pm.",
        tags=["friday", "agenda", "schedule", "todo", "riley", "alex"], source="Weekly planner"),
    FamilyMemoryEntry("procedural",
        "Weekend agenda: Saturday -- Riley soccer 9am, park playdate 11am, errands afternoon. Sunday -- family brunch 10am, meal prep 3pm, Riley school prep 6pm.",
        tags=["saturday", "sunday", "weekend", "agenda", "riley"], source="Weekly planner"),
    FamilyMemoryEntry("semantic",
        "Alex's standing to-do list: review quarterly OKRs, update 1:1 doc for manager, renew car registration, schedule Riley's annual checkup.",
        tags=["alex", "todo", "tasks", "okrs", "car", "checkup"], source="Alex's personal list, 3 sessions ago"),
    FamilyMemoryEntry("semantic",
        "Jordan's standing to-do list: pick up dry cleaning, refill Nana's prescription, fix leaky kitchen faucet, book vet appointment for Max.",
        tags=["jordan", "todo", "tasks", "dry_cleaning", "prescription", "faucet", "vet"], source="Jordan's personal list, last session"),
    FamilyMemoryEntry("semantic",
        "Current grocery list (New Seasons Market): milk, Dave's Killer Bread, bananas, Honeycrisp apples, baby carrots, string cheese, turkey deli slices, whole wheat wraps, avocados (2), Greek yogurt (32oz), eggs (dozen), Mary's Gone Crackers, Peet's decaf, dish soap.",
        tags=["grocery", "list", "shopping", "new_seasons", "items"], source="Running list, updated 2 sessions ago"),
]

SMITH_PROFILE: FamilyProfile = FamilyProfile(
    family_name="Smith",
    space_id="family:smith",
    location="Denton, Texas",
    timezone="America/Chicago",
    members=_MEMBERS,
    devices=_DEVICES,
    memories=_MEMORIES,
    session_config={"tone": "warm", "formality": "casual", "verbosity": "concise"},
    dietary_restrictions=["shellfish allergy (Jordan)"],
    accessibility_needs=["simplified interface (Nana Liz)"],
    preferred_language="en",
)
```

File: `verticals/family/smith.py`

---

### E13.2 — `data/families/smith.json` — JSON Export

#### Issue E13.2.1 — Create `data/families/smith.json`

This JSON file is the default loaded by `UiCoordinator._phase1_web_data()` when
`--family-config data/families/smith.json` is passed. It is a serialized `FamilyProfile`.

Write a script to generate it from `verticals.family.smith`:

```python
# scripts/generate_smith_json.py
"""Generate data/families/smith.json from verticals.family.smith.SMITH_PROFILE."""
import json
from pathlib import Path
from verticals.family.smith import SMITH_PROFILE, _DEVICES, _MEMORIES

output = {
    "family_name": SMITH_PROFILE.family_name,
    "space_id": SMITH_PROFILE.space_id,
    "location": SMITH_PROFILE.location,
    "timezone": SMITH_PROFILE.timezone,
    "preferred_language": SMITH_PROFILE.preferred_language,
    "dietary_restrictions": SMITH_PROFILE.dietary_restrictions,
    "accessibility_needs": SMITH_PROFILE.accessibility_needs,
    "session_config": SMITH_PROFILE.session_config,
    "members": [
        {
            "actor_id": m.actor_id,
            "name": m.name,
            "relation": m.relation,
            "age": m.age,
            "device_ids": m.device_ids,
            "occupation": m.occupation,
            "grade": m.grade,
            "access_level": m.access_level,
            "preferences": m.preferences,
        }
        for m in SMITH_PROFILE.members
    ],
    "devices": _DEVICES,
    "memories": [
        {
            "type": e.memory_type,
            "content": e.content,
            "tags": e.tags,
            "source": e.source,
            "actor_id": e.actor_id,
        }
        for e in SMITH_PROFILE.memories
    ],
}

Path("data/families").mkdir(parents=True, exist_ok=True)
Path("data/families/smith.json").write_text(json.dumps(output, indent=2, ensure_ascii=False))
print(f"Written {len(output['members'])} members, {len(output['memories'])} memories")
```

Run: `python scripts/generate_smith_json.py`

Touch point: NEW `data/families/smith.json`, NEW `scripts/generate_smith_json.py`

---

### E13.3 — `verticals/family/seeder.py` — `SpaceDataSeeder`

**File**: `verticals/family/seeder.py`

This is the core M13 class. It has three methods, one per injection layer.

#### Issue E13.3.1 — Module header

```python
"""verticals.family.seeder — SpaceDataSeeder: bridge FamilyProfile → KernelConfig + SelfModel.

Three injection layers:
  L0 build_seed_memories()   → KernelConfig.seed_memories (session beliefs, always)
  L1 seed_space_projection() → IProjectionStorePort.write_space() (self-model, if enabled)
  L3 seed_k0_memories()      → IBridgeCommandPort.submit_batch() (K0, if bridge available)

Caller pattern (in UiCoordinator._phase2_kernel_startup):
    seeder = SpaceDataSeeder()
    seed_mems = seeder.build_seed_memories(profile, device_id="alex_phone")
    config = KernelConfig(seed_memories=seed_mems, ...)
    runtime = await start_kernel(config)

    if runtime._service.self_model_bundle:
        seeder.seed_space_projection(runtime._service.self_model_bundle, profile)
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, Optional

from verticals.family.profile import FamilyMember, FamilyMemoryEntry, FamilyProfile

if TYPE_CHECKING:
    from k1.selfmodel.kernel.bootstrap import SelfModelServiceBundle

logger = logging.getLogger(__name__)
```

#### Issue E13.3.2 — `build_seed_memories()` — L0 session beliefs (the most important method)

This method converts `FamilyProfile` into the `seed_memories` list format that `KernelConfig`
accepts. Read [k1/concierge/config/concierge.py](k1/concierge/config/concierge.py) to see how
`seed_memories` is consumed — each dict is loaded as a belief context entry.

```python
class SpaceDataSeeder:
    """Converts FamilyProfile into the three injection layers."""

    def build_seed_memories(
        self,
        profile: FamilyProfile,
        device_id: str = "",
    ) -> list[dict[str, Any]]:
        """Build the KernelConfig.seed_memories list from a FamilyProfile.

        This is called BEFORE start_kernel(). The result is passed directly
        as KernelConfig(seed_memories=result).

        Output format: list of dicts, each has at minimum:
          {"type": str, "content": str, "tags": list[str]}

        Also injects 4 synthetic context memories:
          1. family_context   — summary of all members
          2. active_member    — who is speaking (resolved from device_id)
          3. session_config   — tone/formality/verbosity
          4. dietary_access   — dietary restrictions + accessibility needs

        All 19 preloaded memories from FamilyProfile.memories are appended after.
        """
        result: list[dict[str, Any]] = []

        # --- 1. Family context summary ---
        member_summaries = []
        for m in profile.members:
            member_summaries.append(
                f"{m.name} ({m.relation}, age {m.age}"
                + (f", {m.occupation}" if m.occupation else "")
                + (f", grade {m.grade}" if m.grade else "")
                + ")"
            )
        result.append({
            "type": "semantic",
            "content": (
                f"Family: {profile.family_name}. Location: {profile.location}. "
                f"Timezone: {profile.timezone}. "
                f"Members: {', '.join(member_summaries)}."
            ),
            "tags": ["family_context", "members", "household"],
            "source": "FamilyProfile.family_context",
        })

        # --- 2. Active member (resolved from device_id) ---
        active_member: Optional[FamilyMember] = None
        if device_id:
            active_member = profile.member_by_device(device_id)
        if active_member is None and profile.members:
            active_member = profile.members[0]

        if active_member is not None:
            prefs_text = "; ".join(
                f"{k}: {v}" for k, v in active_member.preferences.items()
                if not isinstance(v, dict)  # skip nested dicts for readability
            )
            nested_prefs = {k: v for k, v in active_member.preferences.items() if isinstance(v, dict)}
            for k, v in nested_prefs.items():
                prefs_text += f"; {k}: {json_like(v)}"

            result.append({
                "type": "semantic",
                "content": (
                    f"Currently speaking: {active_member.name} "
                    f"(actor_id={active_member.actor_id}, "
                    f"access_level={active_member.access_level}). "
                    f"Preferences: {prefs_text}."
                ),
                "tags": ["active_member", active_member.actor_id, "context"],
                "source": "FamilyProfile.active_member",
                "actor_id": active_member.actor_id,
            })

        # --- 3. Session tone/formality ---
        if profile.session_config:
            tone = profile.session_config.get("tone", "warm")
            formality = profile.session_config.get("formality", "casual")
            verbosity = profile.session_config.get("verbosity", "concise")
            result.append({
                "type": "semantic",
                "content": (
                    f"Communication style: tone={tone}, "
                    f"formality={formality}, verbosity={verbosity}. "
                    f"Preferred language: {profile.preferred_language}."
                ),
                "tags": ["session_config", "tone", "communication"],
                "source": "FamilyProfile.session_config",
            })

        # --- 4. Dietary + accessibility ---
        if profile.dietary_restrictions or profile.accessibility_needs:
            parts = []
            if profile.dietary_restrictions:
                parts.append("Dietary restrictions: " + ", ".join(profile.dietary_restrictions))
            if profile.accessibility_needs:
                parts.append("Accessibility needs: " + ", ".join(profile.accessibility_needs))
            result.append({
                "type": "semantic",
                "content": ". ".join(parts) + ".",
                "tags": ["dietary", "accessibility", "safety", "medical"],
                "source": "FamilyProfile.restrictions",
            })

        # --- 5. All preloaded memories from FamilyProfile.memories ---
        for entry in profile.memories:
            result.append(entry.to_seed_dict())

        logger.info(
            "build_seed_memories: profile=%s device=%s → %d entries",
            profile.family_name, device_id or "(default)", len(result),
        )
        return result
```

Helper at module top:

```python
def json_like(d: dict) -> str:
    """Format a dict as compact human-readable string for seed_memories."""
    return "{" + ", ".join(f"{k}: {v}" for k, v in d.items()) + "}"
```

#### Issue E13.3.3 — `seed_space_projection()` — L1 self-model (idempotent)

```python
    def seed_space_projection(
        self,
        bundle: "SelfModelServiceBundle",
        profile: FamilyProfile,
    ) -> None:
        """Write the space graph snapshot to the self-model projection store.

        Uses SPACE_GRAPH_WRITER_ID as required by IProjectionStorePort.
        Idempotent: if a space snapshot already exists for the space_id,
        this method does NOT overwrite it (existing data takes priority).

        Call: seeder.seed_space_projection(runtime._service.self_model_bundle, profile)
        Guard: only call this when runtime._service.self_model_bundle is not None
               (i.e. KernelConfig.enable_self_model=True)
        """
        if bundle is None:
            logger.debug("seed_space_projection: bundle is None, skipping")
            return

        # Read-before-write: idempotent guard
        existing, _ = bundle.store.read_space(profile.space_id)
        if existing is not None and existing.members:
            logger.info(
                "seed_space_projection: space snapshot already exists for %s (%d members), skipping",
                profile.space_id, len(existing.members),
            )
            return

        # Import contracts here to avoid top-level circular dep
        from k1.selfmodel.contracts.space_graph import (
            ActorRef, SpaceGraphSnapshot, SpaceEdge,
        )
        from k1.selfmodel.service.space_graph import SPACE_GRAPH_WRITER_ID

        # Build ActorRef list from FamilyMember list
        member_refs = tuple(
            ActorRef(
                member_id=m.actor_id,
                display_name=m.name,
                role=m.role(),
                age_band=m.age_band(),
            )
            for m in profile.members
        )

        # Build relationship edges (parent → child for known patterns)
        relations: list[SpaceEdge] = []
        parents = [m for m in profile.members if m.relation == "parent"]
        children = [m for m in profile.members if m.relation == "child"]
        for p in parents:
            for c in children:
                relations.append(SpaceEdge(
                    from_member=p.actor_id,
                    to_member=c.actor_id,
                    kind="parent_of",
                    weight=1.0,
                ))

        snapshot = SpaceGraphSnapshot(
            space_id=profile.space_id,
            revision="seed-v1",
            members=member_refs,
            relations=tuple(relations),
            routines=(),  # routines seeded separately (M13.E13.4)
            composed_at_ms=int(time.time() * 1000),
        )

        result = bundle.store.write_space(snapshot, writer_id=SPACE_GRAPH_WRITER_ID)
        if result.ok:
            logger.info(
                "seed_space_projection: wrote %d members to %s",
                len(member_refs), profile.space_id,
            )
        else:
            logger.error(
                "seed_space_projection: write_space failed: %s", result
            )
```

#### Issue E13.3.4 — `seed_k0_memories()` — L3 K0 episodic memories (M14 prereq)

This method is wired now but only activates when the K0 bridge is live (M14). During M13, the
bridge is always `SinkBridgeAdapter` (offline) so `is_available()` returns `False` and this
method is a no-op.

```python
    async def seed_k0_memories(
        self,
        bridge_command_port: Any,
        profile: FamilyProfile,
        *,
        memory_types: tuple[str, ...] = ("episodic", "semantic"),
    ) -> int:
        """Submit episodic/semantic memories to K0 via IBridgeCommandPort.

        Only runs when bridge_command_port.is_available() returns True.
        Returns the number of memories submitted (0 if bridge offline).

        This is a M14 activation: wire it now so M14 only needs to pass
        a real bridge_command_port instead of the sink adapter.

        Schema URI: "k1.memory.seed.v1" (define as a constant below)
        """
        SEED_SCHEMA_URI = "k1.memory.seed.v1"

        if bridge_command_port is None:
            return 0

        # Check bridge availability
        is_available = False
        if hasattr(bridge_command_port, "is_available"):
            is_available = bridge_command_port.is_available()
        elif hasattr(bridge_command_port, "_bridge"):
            is_available = getattr(bridge_command_port._bridge, "is_available", lambda: False)()

        if not is_available:
            logger.debug("seed_k0_memories: bridge offline, skipping %d memories", len(profile.memories))
            return 0

        # Filter to requested memory types
        eligible = [m for m in profile.memories if m.memory_type in memory_types]
        if not eligible:
            return 0

        envelopes = [
            {
                "topic": f"k1.memory.seed.{m.memory_type}.v1",
                "schema_uri": SEED_SCHEMA_URI,
                "body": m.to_seed_dict(),
            }
            for m in eligible
        ]

        await bridge_command_port.submit_batch(envelopes)
        logger.info(
            "seed_k0_memories: submitted %d memories to K0 for family=%s",
            len(envelopes), profile.family_name,
        )
        return len(envelopes)
```

---

### E13.4 — Integration with M12 `UiCoordinator`

**File to edit**: `ui/web/coordinator.py` (created in M12)

#### Issue E13.4.1 — Update `_phase1_web_data()` to use `FamilyProfile`

Replace the POC import with the production `verticals.family.smith.SMITH_PROFILE`:

```python
async def _phase1_web_data(self) -> None:
    """Phase 1: Load family profile. (<1s budget)"""
    family_config_path = getattr(self, "_family_config_path", None)
    if family_config_path:
        from verticals.family.profile import FamilyProfile
        self.family_profile_obj = FamilyProfile.from_json(family_config_path)
    else:
        # M13: production family data, no poc.* dependency
        from verticals.family.smith import SMITH_PROFILE
        self.family_profile_obj = SMITH_PROFILE

    # Keep self.family_profile as a dict for backwards compat with app.py /api/family route
    self.family_profile = self._profile_to_web_dict(self.family_profile_obj)
    self.session_config = self.family_profile_obj.session_config
    self.device_registry = self.family_profile_obj.devices
    logger.info("Phase 1: family=%s members=%d",
        self.family_profile_obj.family_name, len(self.family_profile_obj.members))


def _profile_to_web_dict(self, profile: Any) -> dict:
    """Convert FamilyProfile to the dict format expected by /api/family and app.js."""
    return {
        "family_name": profile.family_name,
        "location": profile.location,
        "timezone": profile.timezone,
        "members": [
            {
                "name": m.name,
                "relation": m.relation,
                "age": m.age,
                "actor_id": m.actor_id,
                "access_level": m.access_level,
                "preferences": m.preferences,
                "device_ids": m.device_ids,
                "occupation": m.occupation,
            }
            for m in profile.members
        ],
        "devices": profile.devices,
        "session_config": profile.session_config,
        "dietary_restrictions": profile.dietary_restrictions,
        "accessibility_needs": profile.accessibility_needs,
    }
```

#### Issue E13.4.2 — Update `_phase2_kernel_startup()` to inject seed_memories

**This is the key M13 change.** Replace the bare `KernelConfig(...)` in `_phase2_kernel_startup()`
with a seeder-driven version:

```python
async def _phase2_kernel_startup(self) -> None:
    """Phase 2: Start production K1 kernel with family data seeded. (<5s budget)"""
    phase_start = time.time()
    from k1.kernel.bootstrap import start_kernel
    from k1.concierge.config.kernel import KernelConfig

    # M13: build seed_memories BEFORE KernelConfig is created
    from verticals.family.seeder import SpaceDataSeeder
    seeder = SpaceDataSeeder()
    seed_mems = seeder.build_seed_memories(
        self.family_profile_obj,
        device_id=self._current_device,   # "alex_phone" by default
    )
    logger.info("Phase 2: built %d seed_memories from FamilyProfile", len(seed_mems))

    config = KernelConfig(
        ordered_bus=True,
        capture_bus=False,
        test_mode=self._test_mode,
        session_mode="testing",
        session_id=f"web-{uuid.uuid4().hex[:8]}",
        enable_experience=True,
        enable_delta=True,
        enable_orchestrator=True,
        auto_start_consumer=False,
        seed_memories=seed_mems,          # <-- M13 injection
        # enable_self_model=True,         # <-- uncomment when selfmodel is stable
    )

    runtime = await start_kernel(config)
    self._kernel = runtime

    # ... (copy all runtime field assignments from M12 E12.2.5) ...

    # M13: self-model seeding (only when enable_self_model=True)
    if config.enable_self_model and runtime._service.self_model_bundle is not None:
        try:
            seeder.seed_space_projection(
                runtime._service.self_model_bundle,
                self.family_profile_obj,
            )
        except Exception as exc:
            logger.warning("seed_space_projection failed (non-fatal): %s", exc)

    logger.info("Phase 2: kernel started in %.3fs", time.time() - phase_start)
```

**Why non-fatal?** Self-model seeding failure must not prevent the web UI from starting. The
Concierge still has L0 session beliefs from `seed_memories`. Self-model projections are a
progressive enhancement.

#### Issue E13.4.3 — Add `family_profile_obj` slot to `__init__()`

In `UiCoordinator.__init__()`, add:

```python
self.family_profile_obj: Any = None   # FamilyProfile instance (M13)
self._current_device: str = "alex_phone"  # default device for seed resolution
```

---

### E13.5 — Pre-flight Checklist Before Coding

```powershell
# 1. Verify seed_memories field exists in KernelConfig
python -c "
from k1.concierge.config.kernel import KernelConfig
import dataclasses
f = next((f for f in dataclasses.fields(KernelConfig) if f.name=='seed_memories'), None)
print('seed_memories default:', f.default_factory() if f else 'NOT FOUND')
"

# 2. Verify SPACE_GRAPH_WRITER_ID constant
python -c "from k1.selfmodel.service.space_graph import SPACE_GRAPH_WRITER_ID; print('writer_id:', SPACE_GRAPH_WRITER_ID)"

# 3. Verify SpaceGraphSnapshot fields
python -c "
from k1.selfmodel.contracts.space_graph import SpaceGraphSnapshot, ActorRef, SpaceEdge
import dataclasses
print([f.name for f in dataclasses.fields(SpaceGraphSnapshot)])
print([f.name for f in dataclasses.fields(ActorRef)])
"

# 4. Verify IProjectionStorePort write_space accepts writer_id
python -c "
from k1.selfmodel.adapters.memory_projection_store import InMemoryProjectionStore
from k1.selfmodel.service.space_graph import SPACE_GRAPH_WRITER_ID
store = InMemoryProjectionStore(allowed_writers=(SPACE_GRAPH_WRITER_ID,))
print('store created OK')
"

# 5. Verify seed_memories flows to ConciergeConfig
python -c "
from k1.concierge.config.concierge import ConciergeConfig
import dataclasses
f = next((f for f in dataclasses.fields(ConciergeConfig) if f.name=='seed_memories'), None)
print('ConciergeConfig.seed_memories:', f)
"

# 6. Verify POC preloaded_memories has the expected structure
python -c "
from poc.k1_poc.demo.preloaded_memories import PRELOADED_MEMORIES
print(f'{len(PRELOADED_MEMORIES)} memories')
print('Keys:', list(PRELOADED_MEMORIES[0].keys()))
print('Types:', list({m[\"type\"] for m in PRELOADED_MEMORIES}))
"

# 7. Verify KernelService.self_model_bundle property
python -c "
from k1.kernel.service import KernelService
import inspect
src = inspect.getsource(KernelService.self_model_bundle.fget)
print(src[:200])
"
```

---

### E13.6 — Tests

#### Issue E13.6.1 — `tests/verticals/family/__init__.py`

Empty file.

#### Issue E13.6.2 — `tests/verticals/family/test_profile.py`

```python
"""Tests for FamilyProfile schema.
Run: python -m pytest tests/verticals/family/test_profile.py -q --no-cov
"""
import json, pytest
from pathlib import Path
from verticals.family.profile import FamilyMember, FamilyMemoryEntry, FamilyProfile
from verticals.family.smith import SMITH_PROFILE


class TestFamilyMember:
    def test_age_band_child(self):
        m = FamilyMember("riley","Riley","child",8,[])
        assert m.age_band() == "child"

    def test_age_band_adult(self):
        m = FamilyMember("alex","Alex","parent",38,[])
        assert m.age_band() == "adult"

    def test_role_parent_maps_to_guardian(self):
        m = FamilyMember("alex","Alex","parent",38,[])
        assert m.role() == "guardian"

    def test_role_child_maps_to_child(self):
        m = FamilyMember("riley","Riley","child",8,[])
        assert m.role() == "child"

    def test_to_seed_dict_has_required_keys(self):
        m = FamilyMember("alex","Alex","parent",38,["alex_phone"])
        d = m.to_seed_dict()
        assert "actor_id" in d
        assert "name" in d
        assert "preferences" in d
        assert "device_ids" in d


class TestFamilyProfile:
    def test_smith_profile_has_4_members(self):
        assert len(SMITH_PROFILE.members) == 4

    def test_smith_profile_has_memories(self):
        assert len(SMITH_PROFILE.memories) >= 19

    def test_member_by_device_alex_phone(self):
        m = SMITH_PROFILE.member_by_device("alex_phone")
        assert m is not None
        assert m.actor_id == "alex"

    def test_member_by_device_jordan_phone(self):
        m = SMITH_PROFILE.member_by_device("jordan_phone")
        assert m is not None
        assert m.actor_id == "jordan"

    def test_member_by_device_unknown_returns_none(self):
        m = SMITH_PROFILE.member_by_device("unknown_device")
        assert m is None

    def test_member_by_actor_id(self):
        m = SMITH_PROFILE.member_by_actor("riley")
        assert m is not None
        assert m.name == "Riley"

    def test_memories_for_actor_alex(self):
        mems = SMITH_PROFILE.memories_for_actor("alex")
        assert len(mems) > 0
        # Every returned memory must be tagged alex or be family-level
        for mem in mems:
            assert (mem.actor_id is None or "alex" in (mem.actor_id or "").lower()
                    or "alex" in [t.lower() for t in mem.tags]), (
                f"Memory not tagged alex or family-level: {mem.content[:60]}"
            )

    def test_primary_device_alex(self):
        d = SMITH_PROFILE.primary_device("alex")
        assert d in ("alex_phone", "alex_laptop")

    def test_primary_device_riley_empty(self):
        # Riley has no device
        d = SMITH_PROFILE.primary_device("riley")
        assert d == ""

    def test_from_json_roundtrip(self, tmp_path):
        """Write JSON, load back, assert member count preserved."""
        output = {
            "family_name": SMITH_PROFILE.family_name,
            "space_id": SMITH_PROFILE.space_id,
            "location": SMITH_PROFILE.location,
            "timezone": SMITH_PROFILE.timezone,
            "preferred_language": SMITH_PROFILE.preferred_language,
            "dietary_restrictions": SMITH_PROFILE.dietary_restrictions,
            "accessibility_needs": SMITH_PROFILE.accessibility_needs,
            "session_config": SMITH_PROFILE.session_config,
            "members": [m.to_seed_dict() for m in SMITH_PROFILE.members],
            "devices": SMITH_PROFILE.devices,
            "memories": [e.to_seed_dict() for e in SMITH_PROFILE.memories],
        }
        p = tmp_path / "test_smith.json"
        p.write_text(json.dumps(output))
        loaded = FamilyProfile.from_json(str(p))
        assert loaded.family_name == SMITH_PROFILE.family_name
        assert len(loaded.members) == len(SMITH_PROFILE.members)
        assert len(loaded.memories) == len(SMITH_PROFILE.memories)

    def test_from_json_invalid_raises(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not valid json}")
        with pytest.raises(Exception):
            FamilyProfile.from_json(str(p))
```

#### Issue E13.6.3 — `tests/verticals/family/test_seeder.py`

```python
"""Tests for SpaceDataSeeder.
Run: python -m pytest tests/verticals/family/test_seeder.py -q --no-cov
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from verticals.family.seeder import SpaceDataSeeder
from verticals.family.smith import SMITH_PROFILE


class TestBuildSeedMemories:
    def test_returns_list_of_dicts(self):
        seeder = SpaceDataSeeder()
        result = seeder.build_seed_memories(SMITH_PROFILE, "alex_phone")
        assert isinstance(result, list)
        assert len(result) > 0
        for item in result:
            assert "type" in item, f"missing 'type' in: {item}"
            assert "content" in item, f"missing 'content' in: {item}"

    def test_includes_19_preloaded_memories(self):
        seeder = SpaceDataSeeder()
        result = seeder.build_seed_memories(SMITH_PROFILE, "alex_phone")
        # 4 synthetic + 19 preloaded = at least 23
        assert len(result) >= 23

    def test_active_member_alex_phone(self):
        seeder = SpaceDataSeeder()
        result = seeder.build_seed_memories(SMITH_PROFILE, "alex_phone")
        active_entries = [e for e in result if "active_member" in e.get("tags", [])]
        assert len(active_entries) == 1
        assert "Alex" in active_entries[0]["content"]
        assert active_entries[0].get("actor_id") == "alex"

    def test_active_member_jordan_phone(self):
        seeder = SpaceDataSeeder()
        result = seeder.build_seed_memories(SMITH_PROFILE, "jordan_phone")
        active_entries = [e for e in result if "active_member" in e.get("tags", [])]
        assert len(active_entries) == 1
        assert "Jordan" in active_entries[0]["content"]

    def test_family_context_entry_present(self):
        seeder = SpaceDataSeeder()
        result = seeder.build_seed_memories(SMITH_PROFILE)
        ctx_entries = [e for e in result if "family_context" in e.get("tags", [])]
        assert len(ctx_entries) == 1
        assert "Smith" in ctx_entries[0]["content"]

    def test_session_config_entry_present(self):
        seeder = SpaceDataSeeder()
        result = seeder.build_seed_memories(SMITH_PROFILE)
        sc_entries = [e for e in result if "session_config" in e.get("tags", [])]
        assert len(sc_entries) == 1
        assert "warm" in sc_entries[0]["content"]  # tone=warm in Smith profile

    def test_dietary_entry_present(self):
        seeder = SpaceDataSeeder()
        result = seeder.build_seed_memories(SMITH_PROFILE)
        diet_entries = [e for e in result if "dietary" in e.get("tags", [])]
        assert len(diet_entries) >= 1
        assert "shellfish" in diet_entries[0]["content"].lower()

    def test_all_entries_have_str_content(self):
        seeder = SpaceDataSeeder()
        result = seeder.build_seed_memories(SMITH_PROFILE, "alex_phone")
        for item in result:
            assert isinstance(item["content"], str)
            assert len(item["content"]) > 0


class TestSeedSpaceProjection:
    def _make_bundle(self, existing=None):
        """Build a minimal mock SelfModelServiceBundle."""
        from k1.selfmodel.adapters.memory_projection_store import InMemoryProjectionStore
        from k1.selfmodel.service.space_graph import SPACE_GRAPH_WRITER_ID

        store = InMemoryProjectionStore(
            allowed_writers=(SPACE_GRAPH_WRITER_ID, "test:fixture")
        )
        if existing is not None:
            from k1.selfmodel.service.space_graph import SPACE_GRAPH_WRITER_ID
            store.write_space(existing, writer_id=SPACE_GRAPH_WRITER_ID)

        bundle = MagicMock()
        bundle.store = store
        bundle.space_id = SMITH_PROFILE.space_id
        return bundle

    def test_writes_space_snapshot(self):
        seeder = SpaceDataSeeder()
        bundle = self._make_bundle()
        seeder.seed_space_projection(bundle, SMITH_PROFILE)

        snap, result = bundle.store.read_space(SMITH_PROFILE.space_id)
        assert snap is not None
        assert len(snap.members) == 4

    def test_member_ids_are_actor_ids(self):
        seeder = SpaceDataSeeder()
        bundle = self._make_bundle()
        seeder.seed_space_projection(bundle, SMITH_PROFILE)

        snap, _ = bundle.store.read_space(SMITH_PROFILE.space_id)
        member_ids = {m.member_id for m in snap.members}
        assert "alex" in member_ids
        assert "jordan" in member_ids
        assert "riley" in member_ids
        assert "nana_liz" in member_ids

    def test_parent_child_relations_seeded(self):
        seeder = SpaceDataSeeder()
        bundle = self._make_bundle()
        seeder.seed_space_projection(bundle, SMITH_PROFILE)

        snap, _ = bundle.store.read_space(SMITH_PROFILE.space_id)
        relations = [(r.from_member, r.to_member, r.kind) for r in snap.relations]
        assert ("alex", "riley", "parent_of") in relations
        assert ("jordan", "riley", "parent_of") in relations

    def test_idempotent_does_not_overwrite(self):
        """Second call must not overwrite existing snapshot."""
        from k1.selfmodel.contracts.space_graph import ActorRef, SpaceGraphSnapshot
        from k1.selfmodel.service.space_graph import SPACE_GRAPH_WRITER_ID

        seeder = SpaceDataSeeder()

        # Pre-seed with a 1-member snapshot
        existing = SpaceGraphSnapshot(
            space_id=SMITH_PROFILE.space_id,
            revision="pre-existing",
            members=(ActorRef(member_id="pre_existing_user", display_name="Pre"),),
        )
        bundle = self._make_bundle(existing=existing)

        # Try to seed again — should be a no-op
        seeder.seed_space_projection(bundle, SMITH_PROFILE)

        snap, _ = bundle.store.read_space(SMITH_PROFILE.space_id)
        # Must still be the pre-existing snapshot
        assert snap.revision == "pre-existing"
        assert len(snap.members) == 1
        assert snap.members[0].member_id == "pre_existing_user"

    def test_none_bundle_is_safe(self):
        seeder = SpaceDataSeeder()
        seeder.seed_space_projection(None, SMITH_PROFILE)  # must not raise


class TestSeedK0Memories:
    @pytest.mark.asyncio
    async def test_bridge_offline_returns_zero(self):
        seeder = SpaceDataSeeder()
        mock_bridge = MagicMock()
        mock_bridge.is_available = MagicMock(return_value=False)
        count = await seeder.seed_k0_memories(mock_bridge, SMITH_PROFILE)
        assert count == 0

    @pytest.mark.asyncio
    async def test_bridge_online_submits_batch(self):
        seeder = SpaceDataSeeder()
        mock_bridge = MagicMock()
        mock_bridge.is_available = MagicMock(return_value=True)
        mock_bridge.submit_batch = AsyncMock(return_value=None)

        count = await seeder.seed_k0_memories(mock_bridge, SMITH_PROFILE)
        assert count > 0
        mock_bridge.submit_batch.assert_called_once()
        envelopes = mock_bridge.submit_batch.call_args[0][0]
        assert len(envelopes) == count
        assert all("topic" in e for e in envelopes)
        assert all("body" in e for e in envelopes)

    @pytest.mark.asyncio
    async def test_none_bridge_returns_zero(self):
        seeder = SpaceDataSeeder()
        count = await seeder.seed_k0_memories(None, SMITH_PROFILE)
        assert count == 0
```

#### Issue E13.6.4 — Integration smoke test `tests/verticals/family/test_seeder_integration.py`

```python
"""Integration test: seed_memories flows into a real KernelConfig.
Run: python -m pytest tests/verticals/family/test_seeder_integration.py -q --no-cov
"""
import pytest
from verticals.family.seeder import SpaceDataSeeder
from verticals.family.smith import SMITH_PROFILE
from k1.concierge.config.kernel import KernelConfig


class TestSeedMemoriesIntegration:
    def test_seed_memories_accepted_by_kernel_config(self):
        """KernelConfig must accept the seed_memories list without error."""
        seeder = SpaceDataSeeder()
        seed_mems = seeder.build_seed_memories(SMITH_PROFILE, "alex_phone")

        config = KernelConfig(
            test_mode=True,
            seed_memories=seed_mems,
        )
        assert config.seed_memories == seed_mems
        assert len(config.seed_memories) >= 23

    def test_seed_memories_all_dicts(self):
        seeder = SpaceDataSeeder()
        seed_mems = seeder.build_seed_memories(SMITH_PROFILE, "alex_phone")

        # KernelConfig validates type — must all be dicts
        assert all(isinstance(m, dict) for m in seed_mems)

    def test_smith_profile_space_id_matches_default_selfmodel_config(self):
        """SMITH_PROFILE.space_id must be compatible with KernelConfig.selfmodel_space_id."""
        default_config = KernelConfig()
        # default is "family:default" — note SMITH_PROFILE uses "family:smith"
        # The coordinator must explicitly set selfmodel_space_id="family:smith"
        assert SMITH_PROFILE.space_id == "family:smith"
        assert default_config.selfmodel_space_id == "family:default"
        # When seeding, ensure coordinator passes selfmodel_space_id=profile.space_id
        config_with_smith = KernelConfig(
            test_mode=True,
            selfmodel_space_id=SMITH_PROFILE.space_id,
        )
        assert config_with_smith.selfmodel_space_id == "family:smith"
```

---

### E13.7 — Implementation Order

```
Step 1:  Run pre-flight checklist (E13.5) — answer all 7 checks
Step 2:  Create verticals/family/__init__.py (E13.1.1)
Step 3:  Create verticals/family/profile.py (E13.1.2)
Step 4:  Create verticals/family/smith.py (E13.1.3)
Step 5:  Create verticals/family/seeder.py (E13.3.1 → E13.3.4)
Step 6:  Run tests: python -m pytest tests/verticals/family/ -q --no-cov
Step 7:  Create data/families/ dir; run python scripts/generate_smith_json.py (E13.2.1)
Step 8:  Update coordinator._phase1_web_data() (E13.4.1)
Step 9:  Update coordinator._phase2_kernel_startup() to inject seed_memories (E13.4.2)
Step 10: Update coordinator.__init__() to add family_profile_obj slot (E13.4.3)
Step 11: Run coordinator tests: python -m pytest tests/ui/web/ -q --no-cov
Step 12: Boot: python -m ui.web --test-mode --port 8765
Step 13: Type "What does Riley need for her homework?" — verify family context in response
```

**Key gotcha**: `KernelConfig.selfmodel_space_id` defaults to `"family:default"` but
`SMITH_PROFILE.space_id` is `"family:smith"`. When enabling self-model seeding, pass
`selfmodel_space_id=self.family_profile_obj.space_id` in `KernelConfig`.

---

## M14 — Pseudo-K0 Kernel

**Goal**: A lightweight local HTTP server that satisfies the K0 HTTP API surface (`/k0/command.submit`,
`/k0/query.recall`, `/k0/obs.emit`, `/k0/sse.subscribe`, `/k0/connector.execute`, `/healthz`)
so that K1's `BridgeConnectionAdapter` switches from `SinkBridgeAdapter` (offline outbox) to live
`HttpBridgeClient` → pseudo-K0 HTTP. Memory recall, memory store, and tool dispatch all work locally
without real K0 infrastructure.

**Read first before coding:**

- [bridge/client.py](bridge/client.py) — `SinkBridgeClient`, `HttpBridgeClient`, `IBridgeClient`,
  `create_sink_bridge_client()`. Key: `HttpBridgeClient` may only be constructed via `BridgeRuntime.from_registry()` (lint-enforced sentinel token). Do NOT call `HttpBridgeClient(...)` directly.
- [bridge/runtime.py](bridge/runtime.py) — `BridgeRuntime.from_registry(contracts_path, role, transport)` — the only legal way to get an `HttpBridgeClient`. Slots: `memory_write_v1`, `recall_request_v1`, `query`, `sse`, `obs`, `gateway`.
- [bridge/core/transport/**init**.py](bridge/core/transport/__init__.py) — `HttpTransport`, `TransportConfig(base_url, connect_timeout_s, read_timeout_s, tls_verify)`. `HttpTransport.COMMAND_PATH = "/k0/command.submit"`. `HttpTransport.HEALTH_PATH = "/healthz"`.
- [k1/kernel/service.py](k1/kernel/service.py) lines 1254–1265 — S4 bridge wiring: `if bridge_enabled → SinkBridgeAdapter(outbox_path=...) else → OfflineBridgeAdapter()`. This is what M14 changes.
- [k1/kernel/adapters/bridge_adapter.py](k1/kernel/adapters/bridge_adapter.py) — `SinkBridgeAdapter`, `OfflineBridgeAdapter`. S4 creates one and stores as `self._bridge`. `get_client()` returns the inner `SinkBridgeClient`.
- [k1/fabric/adapters/bridge_connection.py](k1/fabric/adapters/bridge_connection.py) — `BridgeConnectionAdapter(config, client)`. S3 builds this from `self._bridge.get_client()` as `bridge_client`, wraps it into `BridgeConnectionAdapter(client=bridge_client)` which is passed to `FabricFactory.create_shared(bridge=...)`.
- [k1/concierge/config/kernel.py](k1/concierge/config/kernel.py) — `KernelConfig` fields for bridge: `bridge_enabled: bool = True`, `bridge_offline_ok: bool = True`, `bridge_outbox_path: str = './data/bridge_outbox.db'`. No `k0_endpoint` field exists yet.
- [bridge/connector/gateway.py](bridge/connector/gateway.py) — `ConnectorGateway` with `invoke(adapter_id, action, caller, ...)`. This is the real K0-side connector. Pseudo-K0's `ConnectorHost` is the development-mode equivalent.

**Critical discovery — `HttpBridgeClient` construction path:**

`HttpBridgeClient` is guarded by a CI gate (`bridge_client_construction_via_runtime_only`). The
only correct way to get one is:

```python
from bridge.core.transport import HttpTransport, TransportConfig
from bridge.runtime import BridgeRuntime, Role

transport = HttpTransport(config=TransportConfig(base_url="http://localhost:8090"))
await transport.open()  # opens httpx connection pool
runtime = BridgeRuntime.from_registry(
    contracts_path="bridge/contracts",
    role=Role.K1,
    transport=transport,
)
# runtime.client is now an HttpBridgeClient with active slots:
#   memory_write_v1, recall_request_v1, query, sse, obs
```

This means the S4 bridge wiring in `KernelService` needs a new `LiveBridgeAdapter` class that
wraps `BridgeRuntime.from_registry()` rather than any direct `HttpBridgeClient` construction.

**Critical discovery — endpoint paths for pseudo-K0:**

From `bridge/core/transport/__init__.py`:

```python
HttpTransport.COMMAND_PATH = "/k0/command.submit"   # POST
HttpTransport.HEALTH_PATH  = "/healthz"              # GET
```

Additional paths used by generated clients (confirm via bridge contracts):

```python
"/k0/query.recall"     # POST — recall_request_v1
"/k0/obs.emit"         # POST — obs
"/k0/sse.subscribe"    # GET  — SSE
"/k0/connector.execute"# POST — connector gateway (MS-5 / IFL)
```

**Three-phase architecture:**

| Phase | K1 bridge mode | Memory recall | Tool dispatch |
|---|---|---|---|
| Pre-M14 | `SinkBridgeAdapter` (offline) | Empty result | NotImplementedError |
| M14 (this milestone) | `LiveBridgeAdapter` → pseudo-K0 | SQLite WAL query | `ConnectorHost.dispatch()` |
| MS-3+ | `LiveBridgeAdapter` → real K0 | Real K0 | Real K0 connector gateway |

Key insight: M14 is mostly a **server build** (pseudo-K0) + **one new kernel adapter** (`LiveBridgeAdapter`) + **one new KernelConfig field** (`k0_endpoint`). The existing `BridgeConnectionAdapter` in S3 Fabric needs no changes — it already accepts any `IBridgeClient`.

---

### E14.1 — pseudo-K0 Server Package

**No `scripts/pseudo_k0/` directory exists yet. Create from scratch.**

#### Issue E14.1.1 — Scaffold directory structure

```text
scripts/pseudo_k0/
├── __init__.py         ← package marker
├── __main__.py         ← python -m scripts.pseudo_k0 --port 8090 --db ./data/pseudo_k0.db
├── models.py           ← Pydantic V2 request/response models
├── store.py            ← SQLiteK0Store (WAL table + obs_log table)
├── server.py           ← FastAPI app with 6 endpoints
└── connector_host.py   ← ConnectorHost (adapter registry, M11 prerequisite)
```

Dependencies (add to requirements.txt or pyproject.toml if not present):

```text
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
httpx>=0.27.0          # test client
pydantic>=2.7.0        # already present
```

Run command: `python -m scripts.pseudo_k0 --port 8090 --db data/pseudo_k0.db`

Health check: `GET http://localhost:8090/healthz` → `{"status": "ok", "mode": "K0_LOCAL"}`

#### Issue E14.1.2 — Create `scripts/pseudo_k0/__init__.py`

```python
"""scripts.pseudo_k0 — Pseudo-K0 local server for development/demo.

Satisfies the K0 HTTP API surface so K1 can use HttpBridgeClient
without real K0 infrastructure. Not for production use.

Usage:
    python -m scripts.pseudo_k0 --port 8090 --db data/pseudo_k0.db

Endpoints:
    GET  /healthz
    POST /k0/command.submit     (body: Envelope)
    POST /k0/query.recall       (body: RecallRequest)
    POST /k0/obs.emit           (body: ObsPayload)
    GET  /k0/sse.subscribe      (text/event-stream)
    POST /k0/connector.execute  (body: ConnectorRequest)
"""
```

---

### E14.2 — `models.py` — Pydantic Request/Response Models

#### Issue E14.2.1 — Create `scripts/pseudo_k0/models.py`

Read the actual bridge envelope format from [bridge/core/envelope_builder.py](bridge/core/envelope_builder.py)
before coding — the `topic`, `space_id`, `actor`, `band`, and `payload` field names must match
exactly what `HttpTransport.publish()` sends.

```python
"""scripts.pseudo_k0.models — Pydantic V2 models for pseudo-K0 HTTP API.

All models use extra="ignore" so unknown bridge envelope fields are dropped
without validation errors. This is the key simplification vs real K0
(which validates against the contract schema registry).
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Envelope(BaseModel):
    """Incoming envelope from K1 via HttpTransport.publish() → /k0/command.submit.

    Field names match bridge/core/envelope_builder.py CommandEnvelope output.
    All fields optional except topic.
    """
    model_config = ConfigDict(extra="ignore")

    topic: str                              # e.g. "memory.write.v1"
    schema_uri: str | None = None           # e.g. "k1.memory.seed.v1"
    cognitive_trace_id: str | None = None
    tenant_id: str = ""
    space_id: str = ""
    actor: str = ""                         # actor_id (e.g. "alex")
    device_id: str = ""
    band: str = "GREEN"                     # "GREEN" | "AMBER" | "RED"
    payload: dict = Field(default_factory=dict)  # decoded body dict


class RecallSelector(BaseModel):
    """Single filter clause for a RecallRequest. All fields optional."""
    model_config = ConfigDict(extra="ignore")

    space_id: str | None = None
    tenant_id: str | None = None
    actor_id: str | None = None
    memory_type: str | None = None          # "episodic" | "semantic" | "procedural"
    topic: str | None = None               # filter by exact topic
    after: int | None = None               # WAL id exclusive lower bound (pagination)
    cursor: int | None = None              # WAL id exclusive upper bound (pagination)
    query: str | None = None               # free-text substring match on content field
    limit: int = Field(default=20, ge=1, le=256)


class RecallRequest(BaseModel):
    """Body for POST /k0/query.recall."""
    model_config = ConfigDict(extra="ignore")

    space_id: str                           # primary filter — always required
    selectors: list[RecallSelector] = Field(default_factory=list)
    tenant_id: str | None = None
    max_latency_ms: int | None = None       # not enforced in pseudo-K0 (no latency budget)
    fail_fast: bool = False


class ObsPayload(BaseModel):
    """Body for POST /k0/obs.emit."""
    model_config = ConfigDict(extra="ignore")

    kind: str                               # "metrics" | "logs" | "feedback" | "audit"
    body: dict = Field(default_factory=dict)
    priority: str = "NORMAL"               # "LOW" | "NORMAL" | "HIGH"
    trace_id: str | None = None


class ConnectorRequest(BaseModel):
    """Body for POST /k0/connector.execute."""
    model_config = ConfigDict(extra="ignore")

    adapter_id: str                         # "calendar" | "tasks" | "reminders" etc.
    action: str                             # tool name e.g. "list_events"
    params: dict = Field(default_factory=dict)
    trace_id: str | None = None
    caller_actor_id: str | None = None
    timeout_ms: int = 30_000


class ConnectorResult(BaseModel):
    """Response for POST /k0/connector.execute."""

    success: bool
    result: dict | None = None
    error: str | None = None
    adapter_id: str = ""
    action: str = ""
    trace_id: str | None = None
```

File: `scripts/pseudo_k0/models.py`

---

### E14.3 — `store.py` — `SQLiteK0Store`

#### Issue E14.3.1 — Create `scripts/pseudo_k0/store.py`

**Read before coding**: The `space_id` on envelopes comes from the K1 `KernelConfig.selfmodel_space_id`
(default `"family:default"`) or the session's `space_id`. The `actor` field maps to `actor_id`
in the WAL row. Content extraction: try `payload["content"]` first, then `payload["body"]` if
missing, then `str(payload)` as fallback.

```python
"""scripts.pseudo_k0.store — SQLiteK0Store: append-only WAL + obs_log.

Tables:
    wal        — memory writes (command.submit)
    obs_log    — telemetry writes (obs.emit)

Thread-safety: uses threading.Lock + WAL journal mode (concurrent reads OK).
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from scripts.pseudo_k0.models import Envelope, RecallRequest


_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS wal (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    space_id     TEXT    NOT NULL DEFAULT '',
    tenant_id    TEXT,
    actor_id     TEXT,
    topic        TEXT    NOT NULL DEFAULT '',
    memory_type  TEXT,
    content      TEXT,
    tags         TEXT,
    trace_id     TEXT,
    payload      TEXT    NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_wal_space       ON wal(space_id);
CREATE INDEX IF NOT EXISTS idx_wal_topic       ON wal(topic);
CREATE INDEX IF NOT EXISTS idx_wal_actor       ON wal(actor_id);
CREATE INDEX IF NOT EXISTS idx_wal_memory_type ON wal(memory_type);

CREATE TABLE IF NOT EXISTS obs_log (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    ts    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    kind  TEXT NOT NULL,
    body  TEXT NOT NULL DEFAULT '{}'
);
"""

_RECALL_SQL = """
SELECT id, ts, topic, memory_type, content, tags, trace_id, space_id, actor_id, payload
FROM wal
WHERE space_id = :space_id
  AND (:tenant_id  IS NULL OR tenant_id   = :tenant_id)
  AND (:actor_id   IS NULL OR actor_id    = :actor_id)
  AND (:memory_type IS NULL OR memory_type = :memory_type)
  AND (:topic      IS NULL OR topic        = :topic)
  AND (:after      IS NULL OR id > :after)
  AND (:cursor     IS NULL OR id < :cursor)
  AND (:query_like IS NULL OR content LIKE :query_like)
ORDER BY id DESC
LIMIT :limit
"""


class SQLiteK0Store:
    """Thread-safe SQLite store for pseudo-K0 WAL and obs_log."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        self._lock = threading.Lock()
        if self._db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            self._db_path,
            check_same_thread=False,  # protected by _lock
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_DDL)
        self._conn.commit()

    # -- Write ---------------------------------------------------------------

    def write_envelope(self, env: Envelope) -> int:
        """Persist an envelope to the WAL table. Returns the new row id."""
        content = self._extract_content(env.payload)
        tags = json.dumps(env.payload.get("tags", []))
        memory_type = (
            env.payload.get("type")
            or env.payload.get("memory_type")
            or _infer_memory_type(env.topic)
        )
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO wal
                   (space_id, tenant_id, actor_id, topic, memory_type, content, tags,
                    trace_id, payload)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    env.space_id or "",
                    env.tenant_id or None,
                    env.actor or None,
                    env.topic,
                    memory_type,
                    content,
                    tags,
                    env.cognitive_trace_id,
                    json.dumps(env.payload, ensure_ascii=False),
                ),
            )
            self._conn.commit()
            return cur.lastrowid  # type: ignore[return-value]

    def write_obs(self, kind: str, body: dict[str, Any]) -> None:
        """Append an obs_log row."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO obs_log (kind, body) VALUES (?, ?)",
                (kind, json.dumps(body, ensure_ascii=False)),
            )
            self._conn.commit()

    # -- Read ----------------------------------------------------------------

    def recall(self, req: RecallRequest) -> list[dict[str, Any]]:
        """Run all selectors, merge results, dedup by id, return newest-first."""
        seen: set[int] = set()
        results: list[dict[str, Any]] = []

        selectors = req.selectors or [RecallSelector()]  # default: all rows for space
        for sel in selectors:
            params = {
                "space_id": req.space_id,
                "tenant_id": req.tenant_id or sel.tenant_id,
                "actor_id": sel.actor_id,
                "memory_type": sel.memory_type,
                "topic": sel.topic,
                "after": sel.after,
                "cursor": sel.cursor,
                "query_like": f"%{sel.query}%" if sel.query else None,
                "limit": sel.limit,
            }
            with self._lock:
                rows = self._conn.execute(_RECALL_SQL, params).fetchall()
            for row in rows:
                row_id = row["id"]
                if row_id not in seen:
                    seen.add(row_id)
                    results.append(dict(row))

        # Sort merged results newest-first
        results.sort(key=lambda r: r["id"], reverse=True)
        return results

    def health(self) -> dict[str, Any]:
        """Return health dict for /healthz endpoint."""
        with self._lock:
            row_count = self._conn.execute("SELECT COUNT(*) FROM wal").fetchone()[0]
        return {
            "status": "ok",
            "mode": "K0_LOCAL",
            "db_path": self._db_path,
            "wal_row_count": row_count,
        }

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- Internal helpers ----------------------------------------------------

    @staticmethod
    def _extract_content(payload: dict[str, Any]) -> str | None:
        """Best-effort content extraction from payload dict."""
        for key in ("content", "body", "text", "message", "value"):
            if key in payload and isinstance(payload[key], str):
                return payload[key]
        # Fallback: serialize the whole payload
        return json.dumps(payload, ensure_ascii=False)[:2000]


def _infer_memory_type(topic: str) -> str | None:
    """Infer memory_type from topic string (e.g. 'memory.write.v1' → None)."""
    if "episodic" in topic: return "episodic"
    if "semantic" in topic: return "semantic"
    if "procedural" in topic: return "procedural"
    if "delta" in topic: return "delta"
    return None
```

Note: `RecallSelector` must be imported at module top when used in `recall()`:

```python
from scripts.pseudo_k0.models import Envelope, RecallRequest, RecallSelector
```

File: `scripts/pseudo_k0/store.py`

---

### E14.4 — `connector_host.py` — `ConnectorHost`

#### Issue E14.4.1 — Create `scripts/pseudo_k0/connector_host.py`

`ConnectorHost` is the pseudo-K0 equivalent of `bridge.connector.ConnectorGateway`. It holds a
registry of in-process adapter handlers and dispatches `connector.execute` calls to them. M11
fills this with real tool handlers; M14 only creates the skeleton.

```python
"""scripts.pseudo_k0.connector_host — ConnectorHost: adapter registry.

In M14 this is a skeleton — no handlers registered, all dispatch returns
{"success": False, "error": "unknown adapter: <id>"}.

In M11 each tool (calendar, tasks, reminders, ...) registers a handler here.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class IMCPHandler(Protocol):
    """Interface every pseudo-K0 adapter handler must satisfy."""

    async def call(self, *, action: str, params: dict[str, Any], trace_id: str | None) -> dict[str, Any]:
        """Invoke a tool action. Must return a serializable dict."""
        ...


class ConnectorHost:
    """In-process adapter registry for pseudo-K0 /k0/connector.execute.

    Registration:
        host = ConnectorHost()
        host.register("calendar", CalendarHandler(...))
        host.register("tasks", TasksHandler(...))

    Dispatch:
        result = await host.dispatch("calendar", "list_events", {"date": "2026-05-10"}, trace_id)
        # {"success": True, "result": {...}}
        # {"success": False, "error": "unknown adapter: foo"}
    """

    def __init__(self) -> None:
        self._handlers: dict[str, IMCPHandler] = {}

    def register(self, adapter_id: str, handler: IMCPHandler) -> None:
        """Register a handler for adapter_id. Overwrites if already registered."""
        self._handlers[adapter_id] = handler
        logger.info("ConnectorHost: registered adapter=%s handler=%r", adapter_id, handler)

    def unregister(self, adapter_id: str) -> None:
        """Remove a handler. Idempotent."""
        self._handlers.pop(adapter_id, None)

    @property
    def registered_adapters(self) -> list[str]:
        """Return sorted list of registered adapter_ids."""
        return sorted(self._handlers.keys())

    async def dispatch(
        self,
        adapter_id: str,
        action: str,
        params: dict[str, Any],
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Route a connector.execute call to the registered handler.

        Returns:
            {"success": True,  "result": {...}, "adapter_id": ..., "action": ...}
            {"success": False, "error": "...",  "adapter_id": ..., "action": ...}
        """
        handler = self._handlers.get(adapter_id)
        if handler is None:
            logger.warning("ConnectorHost: no handler for adapter_id=%s", adapter_id)
            return {
                "success": False,
                "error": f"unknown adapter: {adapter_id}",
                "adapter_id": adapter_id,
                "action": action,
                "trace_id": trace_id,
            }
        try:
            result = await handler.call(action=action, params=params, trace_id=trace_id)
            logger.debug(
                "ConnectorHost: dispatched adapter=%s action=%s → success",
                adapter_id, action,
            )
            return {"success": True, "result": result, "adapter_id": adapter_id, "action": action, "trace_id": trace_id}
        except NotImplementedError:
            return {
                "success": False,
                "error": f"{adapter_id}.{action}: not implemented",
                "adapter_id": adapter_id,
                "action": action,
                "trace_id": trace_id,
            }
        except Exception as exc:
            logger.error(
                "ConnectorHost: error in adapter=%s action=%s: %s",
                adapter_id, action, exc,
            )
            return {
                "success": False,
                "error": str(exc),
                "adapter_id": adapter_id,
                "action": action,
                "trace_id": trace_id,
            }
```

File: `scripts/pseudo_k0/connector_host.py`

---

### E14.5 — `server.py` — FastAPI Application

#### Issue E14.5.1 — Create `scripts/pseudo_k0/server.py`

**Pre-read**: Check whether `bridge/core/transport/__init__.py`'s `HttpTransport.COMMAND_PATH`
is `/k0/command.submit` or `/command.submit`. Pseudo-K0's routes must match exactly.

```python
"""scripts.pseudo_k0.server — FastAPI pseudo-K0 HTTP server.

All 6 endpoints that K1's HttpBridgeClient connects to:

  GET  /healthz                     ← HttpTransport.HEALTH_PATH
  POST /k0/command.submit           ← HttpTransport.COMMAND_PATH
  POST /k0/query.recall             ← recall_request_v1 client
  POST /k0/obs.emit                 ← obs emitter
  GET  /k0/sse.subscribe            ← SSE (keepalive-only in Phase 1)
  POST /k0/connector.execute        ← ConnectorGateway (MS-5) / ConnectorHost (pseudo-K0)
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from scripts.pseudo_k0.connector_host import ConnectorHost
from scripts.pseudo_k0.models import (
    ConnectorRequest,
    ConnectorResult,
    Envelope,
    ObsPayload,
    RecallRequest,
)
from scripts.pseudo_k0.store import SQLiteK0Store

logger = logging.getLogger(__name__)


def create_app(store: SQLiteK0Store, connector_host: ConnectorHost) -> FastAPI:
    """Factory so tests can inject a custom store/host without side effects.

    Usage:
        store = SQLiteK0Store(":memory:")
        host  = ConnectorHost()
        app   = create_app(store, host)
        # ASGI: mount directly, or run via uvicorn
    """
    app = FastAPI(
        title="Pseudo-K0",
        version="0.1.0",
        description="Development-mode K0 API surface for FamilyOS K1 bridge.",
    )

    # -- Health ------------------------------------------------------------- #

    @app.get("/healthz", tags=["health"])
    async def healthz() -> dict:
        """GET /healthz — matches HttpTransport.HEALTH_PATH."""
        return store.health()

    # -- Command submit ----------------------------------------------------- #

    @app.post(
        "/k0/command.submit",
        status_code=202,
        tags=["command"],
        summary="Accept a K1 command envelope and persist to WAL.",
    )
    async def command_submit(body: Envelope) -> dict:
        """POST /k0/command.submit — matches HttpTransport.COMMAND_PATH.

        Accepts any bridge envelope. Extracts space_id, actor, topic,
        payload and writes to WAL. Returns wal_id for idempotency checks.
        """
        wal_id = store.write_envelope(body)
        logger.debug("command.submit: topic=%s wal_id=%d", body.topic, wal_id)
        return {
            "accepted": True,
            "wal_id": wal_id,
            "topic": body.topic,
            "space_id": body.space_id,
        }

    # -- Query recall ------------------------------------------------------- #

    @app.post(
        "/k0/query.recall",
        tags=["query"],
        summary="Recall memories from WAL by space_id + optional selectors.",
    )
    async def query_recall(req: RecallRequest) -> dict:
        """POST /k0/query.recall — used by recall_request_v1 K1 client.

        Returns all matching rows across all selectors (deduped by WAL id).
        """
        rows = store.recall(req)
        logger.debug("query.recall: space_id=%s → %d rows", req.space_id, len(rows))
        return {"results": rows, "count": len(rows), "space_id": req.space_id}

    # -- Obs emit ----------------------------------------------------------- #

    @app.post(
        "/k0/obs.emit",
        status_code=204,
        tags=["obs"],
        summary="Accept a telemetry/feedback obs payload.",
    )
    async def obs_emit(payload: ObsPayload) -> None:
        """POST /k0/obs.emit — drops LOW priority, logs the rest."""
        if payload.priority != "LOW":
            store.write_obs(payload.kind, payload.body)
            logger.debug("obs.emit: kind=%s priority=%s", payload.kind, payload.priority)

    # -- SSE subscribe ------------------------------------------------------ #

    @app.get(
        "/k0/sse.subscribe",
        tags=["sse"],
        summary="K0→K1 SSE stream (Phase 1: keepalive only).",
    )
    async def sse_subscribe(request: Request) -> StreamingResponse:
        """GET /k0/sse.subscribe.

        Phase 1 (M14): keepalive ping every 30 seconds.
        Phase 2 (post-M14): real push when WAL write fires an event.
        """
        async def event_stream():
            while True:
                if await request.is_disconnected():
                    break
                yield "data: {}\n\n"
                await asyncio.sleep(30)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # -- Connector execute -------------------------------------------------- #

    @app.post(
        "/k0/connector.execute",
        tags=["connector"],
        summary="Dispatch a tool call to ConnectorHost.",
    )
    async def connector_execute(req: ConnectorRequest) -> ConnectorResult:
        """POST /k0/connector.execute — routes to ConnectorHost.dispatch().

        In M14: skeleton returns unknown adapter error for all adapters.
        In M11: calendar, tasks, reminders, chores, budget, school, health registered.
        """
        result = await connector_host.dispatch(
            req.adapter_id, req.action, req.params, req.trace_id
        )
        return ConnectorResult(**result)

    return app
```

File: `scripts/pseudo_k0/server.py`

#### Issue E14.5.2 — Create `scripts/pseudo_k0/__main__.py`

```python
"""scripts.pseudo_k0.__main__ — CLI entrypoint for pseudo-K0 server.

Usage:
    python -m scripts.pseudo_k0
    python -m scripts.pseudo_k0 --port 8090 --db data/pseudo_k0.db --host 127.0.0.1
    python -m scripts.pseudo_k0 --reload  (dev mode, requires uvicorn[standard])

Environment variables (override CLI flags):
    PSEUDO_K0_PORT  default 8090
    PSEUDO_K0_DB    default data/pseudo_k0.db
    PSEUDO_K0_HOST  default 127.0.0.1
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("pseudo_k0")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Pseudo-K0 local HTTP server")
    p.add_argument("--port", type=int, default=int(os.environ.get("PSEUDO_K0_PORT", 8090)))
    p.add_argument("--host", default=os.environ.get("PSEUDO_K0_HOST", "127.0.0.1"))
    p.add_argument("--db", default=os.environ.get("PSEUDO_K0_DB", "data/pseudo_k0.db"))
    p.add_argument("--reload", action="store_true", help="Enable uvicorn auto-reload (dev mode)")
    p.add_argument("--log-level", default="info", choices=["debug", "info", "warning", "error"])
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    logger.info("Starting pseudo-K0 on http://%s:%d (db=%s)", args.host, args.port, args.db)

    import uvicorn
    from scripts.pseudo_k0.connector_host import ConnectorHost
    from scripts.pseudo_k0.server import create_app
    from scripts.pseudo_k0.store import SQLiteK0Store

    store = SQLiteK0Store(db_path=args.db)
    host = ConnectorHost()
    # M11: register tool handlers here
    # host.register("calendar",  CalendarHandler(args.db))
    # host.register("tasks",     TasksHandler(args.db))

    app = create_app(store=store, connector_host=host)

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main(sys.argv[1:])
```

File: `scripts/pseudo_k0/__main__.py`

---

### E14.6 — Wire K1 to Pseudo-K0

#### Issue E14.6.1 — Add `k0_endpoint` field to `KernelConfig`

**File**: `k1/concierge/config/kernel.py`

Current bridge fields (verified):

```python
bridge_enabled: bool = True
bridge_offline_ok: bool = True
bridge_outbox_path: str = './data/bridge_outbox.db'
```

Add after `bridge_outbox_path`:

```python
k0_endpoint: str = ""
# If non-empty, K1 kernel S4 wires a LiveBridgeAdapter pointed at this URL.
# Example: "http://localhost:8090"
# When empty (default), S4 uses SinkBridgeAdapter (offline outbox mode).
# Set via env var K0_ENDPOINT in ui/web/__main__.py.
```

Touch point: EDIT `k1/concierge/config/kernel.py` — add one field after `bridge_outbox_path`

#### Issue E14.6.2 — Create `k1/kernel/adapters/live_bridge_adapter.py`

**This is the most critical wiring file.** `HttpBridgeClient` can only be built via
`BridgeRuntime.from_registry()` — this class encapsulates that pattern behind the same interface
as `SinkBridgeAdapter` and `OfflineBridgeAdapter`.

```python
"""k1.kernel.adapters.live_bridge_adapter — LiveBridgeAdapter for real/pseudo K0.

Wraps BridgeRuntime.from_registry() to produce a valid HttpBridgeClient
without violating the bridge_client_construction_via_runtime_only CI gate.

This is the S4 bridge adapter used when KernelConfig.k0_endpoint is set.

Implements the same duck-typed interface as SinkBridgeAdapter:
    is_connected() -> bool
    get_client()   -> IBridgeClient | SinkBridgeClient
    connect()      -> None (async)
    disconnect()   -> None (async)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Bridge contracts directory — relative to workspace root
_CONTRACTS_PATH = Path("bridge/contracts")


class LiveBridgeAdapter:
    """Real-HTTP bridge adapter using BridgeRuntime → HttpBridgeClient.

    Used at S4 when KernelConfig.k0_endpoint is non-empty.

    Parameters
    ----------
    endpoint : str
        Base URL for pseudo-K0 or real K0. E.g. "http://localhost:8090".
    contracts_path : Path
        Path to bridge contracts directory (default: "bridge/contracts").
    connect_timeout_s : float
        HTTP connect timeout (default: 5.0s).
    tls_verify : bool
        Whether to verify TLS certificates (default: False for local dev).
    """

    def __init__(
        self,
        *,
        endpoint: str,
        contracts_path: Path | str = _CONTRACTS_PATH,
        connect_timeout_s: float = 5.0,
        tls_verify: bool = False,
    ) -> None:
        self._endpoint = endpoint
        self._contracts_path = Path(contracts_path)
        self._connect_timeout_s = connect_timeout_s
        self._tls_verify = tls_verify
        self._transport: Any = None   # bridge.core.transport.HttpTransport
        self._runtime: Any = None     # bridge.BridgeRuntime
        self._client: Any = None      # bridge.client.HttpBridgeClient
        self._connected = False

    async def connect(self) -> None:
        """Open HTTP transport and build HttpBridgeClient via BridgeRuntime."""
        if self._connected:
            return

        from bridge.core.transport import HttpTransport, TransportConfig
        from bridge.runtime import BridgeRuntime, Role

        config = TransportConfig(
            base_url=self._endpoint,
            connect_timeout_s=self._connect_timeout_s,
            tls_verify=self._tls_verify,
        )
        transport = HttpTransport(config=config)
        await transport.open()
        self._transport = transport

        runtime = BridgeRuntime.from_registry(
            contracts_path=self._contracts_path,
            role=Role.K1,
            transport=transport,
        )
        await runtime.start()
        self._runtime = runtime
        self._client = runtime.client   # HttpBridgeClient with active slots
        self._connected = True
        logger.info(
            "LiveBridgeAdapter: connected to %s (slots=%r)",
            self._endpoint,
            [s for s in ("memory_write_v1", "recall_request_v1", "query", "sse", "obs")
             if getattr(self._client, s, None) is not None],
        )

    async def disconnect(self) -> None:
        """Tear down runtime and transport."""
        if self._runtime is not None:
            await self._runtime.stop()
            self._runtime = None
        if self._transport is not None:
            close = getattr(self._transport, "close", None) or getattr(self._transport, "aclose", None)
            if close is not None:
                await close()
            self._transport = None
        self._client = None
        self._connected = False
        logger.info("LiveBridgeAdapter: disconnected from %s", self._endpoint)

    def is_connected(self) -> bool:
        """True only after successful connect()."""
        return self._connected

    def get_client(self) -> Any:
        """Return the HttpBridgeClient (or None if not connected)."""
        return self._client
```

File: `k1/kernel/adapters/live_bridge_adapter.py`

Touch point: NEW file only. S4 wiring is the next step.

#### Issue E14.6.3 — Update S4 in `KernelService._startup_tier1()` to use `LiveBridgeAdapter`

**File**: `k1/kernel/service.py` — the S4 bridge section (currently lines ~1254–1265).

Current S4 code:

```python
# ── S4: Bridge (kernel-level IBridgePort) ─────────
try:
    if self._config.bridge_enabled:
        self._bridge = SinkBridgeAdapter(
            outbox_path=self._config.bridge_outbox_path,
        )
        logger.info(
            "K1 Kernel S4: bridge=OFFLINE (SinkBridgeClient / outbox mode). "
            "K0 ops will queue to %s. Live K0 requires HttpBridgeClient.",
            self._config.bridge_outbox_path,
        )
    else:
        self._bridge = OfflineBridgeAdapter()
        logger.info("K1 Kernel S4: bridge=DISABLED (OfflineBridgeAdapter).")
except Exception:
    self._bus.close()
    self._router.close()
    raise
```

Replace with:

```python
# ── S4: Bridge (kernel-level IBridgePort) ─────────
# Three modes:
#   k0_endpoint set    → LiveBridgeAdapter (HttpBridgeClient via BridgeRuntime)
#   bridge_enabled     → SinkBridgeAdapter (offline outbox, default)
#   neither            → OfflineBridgeAdapter (null object)
try:
    if self._config.k0_endpoint:
        from k1.kernel.adapters.live_bridge_adapter import LiveBridgeAdapter
        live_adapter = LiveBridgeAdapter(endpoint=self._config.k0_endpoint)
        await live_adapter.connect()
        self._bridge = live_adapter
        logger.info(
            "K1 Kernel S4: bridge=LIVE (HttpBridgeClient → %s).",
            self._config.k0_endpoint,
        )
    elif self._config.bridge_enabled:
        self._bridge = SinkBridgeAdapter(
            outbox_path=self._config.bridge_outbox_path,
        )
        logger.info(
            "K1 Kernel S4: bridge=OFFLINE (SinkBridgeClient / outbox mode). "
            "K0 ops will queue to %s. Live K0 requires HttpBridgeClient.",
            self._config.bridge_outbox_path,
        )
    else:
        self._bridge = OfflineBridgeAdapter()
        logger.info("K1 Kernel S4: bridge=DISABLED (OfflineBridgeAdapter).")
except Exception:
    self._bus.close()
    self._router.close()
    raise
```

**Note**: S4 is called inside `async def _startup_tier1()` so `await live_adapter.connect()` is
legal. Verify in [k1/kernel/service.py](k1/kernel/service.py) that `_startup_tier1` is indeed
async before adding the await.

Touch point: EDIT `k1/kernel/service.py` — S4 block only (the ~12 lines shown above)

#### Issue E14.6.4 — Read `K0_ENDPOINT` env var in `ui/web/__main__.py`

**File**: `ui/web/__main__.py`

Add before `KernelConfig(...)` is built:

```python
import os
k0_endpoint = os.environ.get("K0_ENDPOINT", "")
if k0_endpoint:
    logger.info("K0_ENDPOINT=%s → LiveBridgeAdapter will be used at S4", k0_endpoint)
```

And pass to `KernelConfig`:

```python
config = KernelConfig(
    ...
    k0_endpoint=k0_endpoint,
)
```

Touch point: EDIT `ui/web/__main__.py` — read env var and pass to config

#### Issue E14.6.5 — Update `UiCoordinator._phase2_kernel_startup()` for live bridge

**File**: `ui/web/coordinator.py` (M12 file)

After the `config = KernelConfig(...)` call in `_phase2_kernel_startup()`, pass `k0_endpoint`
from the coordinator's config/env:

```python
# M14: live bridge support
k0_endpoint = os.environ.get("K0_ENDPOINT", "")
config = KernelConfig(
    ...
    k0_endpoint=k0_endpoint,
    seed_memories=seed_mems,      # from M13
)
```

Also: after `start_kernel()` returns, log bridge mode:

```python
runtime = await start_kernel(config)
if k0_endpoint:
    logger.info("Phase 2: kernel connected to K0 at %s", k0_endpoint)
else:
    logger.info("Phase 2: kernel in offline bridge mode (outbox)")
```

Touch point: EDIT `ui/web/coordinator.py` — `_phase2_kernel_startup()` only

---

### E14.7 — Pre-flight Checklist Before Coding

```powershell
# 1. Verify SinkBridgeAdapter and OfflineBridgeAdapter exist
python -c "
from k1.kernel.adapters.bridge_adapter import SinkBridgeAdapter, OfflineBridgeAdapter
print('SinkBridgeAdapter:', SinkBridgeAdapter)
print('OfflineBridgeAdapter:', OfflineBridgeAdapter)
"

# 2. Verify KernelConfig bridge fields
python -c "
import dataclasses
from k1.concierge.config.kernel import KernelConfig
bridge_fields = [(f.name, repr(f.default)) for f in dataclasses.fields(KernelConfig) if 'bridge' in f.name or 'k0' in f.name]
for n, d in bridge_fields: print(f'{n} = {d}')
"

# 3. Verify BridgeRuntime.from_registry signature
python -c "
import inspect
from bridge.runtime import BridgeRuntime
print(inspect.signature(BridgeRuntime.from_registry))
"

# 4. Verify HttpTransport.COMMAND_PATH and HEALTH_PATH
python -c "
from bridge.core.transport import HttpTransport
print('COMMAND_PATH:', HttpTransport.COMMAND_PATH)
print('HEALTH_PATH:', HttpTransport.HEALTH_PATH)
"

# 5. Verify TransportConfig fields
python -c "
import dataclasses
from bridge.core.transport import TransportConfig
for f in dataclasses.fields(TransportConfig): print(f.name, '=', repr(f.default))
"

# 6. Verify BridgeConnectionAdapter accepts any client
python -c "
import inspect
from k1.fabric.adapters.bridge_connection import BridgeConnectionAdapter
print(inspect.signature(BridgeConnectionAdapter.__init__))
"

# 7. Verify FastAPI available for pseudo-K0 server
python -c "import fastapi, uvicorn; print('fastapi:', fastapi.__version__, 'uvicorn:', uvicorn.__version__)"

# 8. Verify KernelService._startup_tier1 is async
python -c "
import inspect, asyncio
from k1.kernel.service import KernelService
fn = getattr(KernelService, '_startup_tier1', None)
print('is coroutinefunction:', asyncio.iscoroutinefunction(fn))
" 2>/dev/null || echo "Import error — check source directly at k1/kernel/service.py"
```

---

### E14.8 — Tests

#### Issue E14.8.1 — Create `tests/scripts/pseudo_k0/__init__.py` + `test_store.py`

```python
"""Tests for SQLiteK0Store.
Run: python -m pytest tests/scripts/pseudo_k0/test_store.py -q --no-cov
"""
import json
import pytest
from scripts.pseudo_k0.models import Envelope, RecallRequest, RecallSelector
from scripts.pseudo_k0.store import SQLiteK0Store


@pytest.fixture
def store(tmp_path):
    s = SQLiteK0Store(db_path=tmp_path / "test.db")
    yield s
    s.close()


@pytest.fixture
def mem_store():
    s = SQLiteK0Store(db_path=":memory:")
    yield s
    s.close()


def _env(topic="memory.write.v1", space_id="family:smith", actor="alex",
         content="test memory", memory_type="semantic", tags=None) -> Envelope:
    return Envelope(
        topic=topic,
        space_id=space_id,
        actor=actor,
        payload={"type": memory_type, "content": content, "tags": tags or []},
    )


class TestWriteAndRecall:
    def test_write_returns_positive_int(self, mem_store):
        row_id = mem_store.write_envelope(_env())
        assert isinstance(row_id, int)
        assert row_id > 0

    def test_recall_by_space_returns_written_row(self, mem_store):
        mem_store.write_envelope(_env(space_id="family:smith"))
        req = RecallRequest(space_id="family:smith")
        rows = mem_store.recall(req)
        assert len(rows) >= 1
        assert rows[0]["space_id"] == "family:smith"

    def test_recall_different_space_returns_empty(self, mem_store):
        mem_store.write_envelope(_env(space_id="family:smith"))
        req = RecallRequest(space_id="family:jones")
        rows = mem_store.recall(req)
        assert rows == []

    def test_write_three_same_space(self, mem_store):
        for i in range(3):
            mem_store.write_envelope(_env(content=f"memory {i}"))
        req = RecallRequest(space_id="family:smith")
        rows = mem_store.recall(req)
        assert len(rows) == 3

    def test_recall_by_memory_type(self, mem_store):
        mem_store.write_envelope(_env(memory_type="episodic", content="episodic memory"))
        mem_store.write_envelope(_env(memory_type="semantic",  content="semantic memory"))
        req = RecallRequest(
            space_id="family:smith",
            selectors=[RecallSelector(memory_type="episodic")],
        )
        rows = mem_store.recall(req)
        assert len(rows) == 1
        assert rows[0]["memory_type"] == "episodic"

    def test_recall_by_actor(self, mem_store):
        mem_store.write_envelope(_env(actor="alex",   content="alex memory"))
        mem_store.write_envelope(_env(actor="jordan", content="jordan memory"))
        req = RecallRequest(
            space_id="family:smith",
            selectors=[RecallSelector(actor_id="alex")],
        )
        rows = mem_store.recall(req)
        assert len(rows) == 1
        assert rows[0]["actor_id"] == "alex"

    def test_recall_limit(self, mem_store):
        for i in range(10):
            mem_store.write_envelope(_env(content=f"memory {i}"))
        req = RecallRequest(
            space_id="family:smith",
            selectors=[RecallSelector(limit=3)],
        )
        rows = mem_store.recall(req)
        assert len(rows) == 3

    def test_recall_after_pagination(self, mem_store):
        ids = [mem_store.write_envelope(_env(content=f"mem {i}")) for i in range(5)]
        # recall only rows after id[1]
        req = RecallRequest(
            space_id="family:smith",
            selectors=[RecallSelector(after=ids[1])],
        )
        rows = mem_store.recall(req)
        assert all(r["id"] > ids[1] for r in rows)
        assert len(rows) == 3  # ids[2], ids[3], ids[4]

    def test_recall_free_text_query(self, mem_store):
        mem_store.write_envelope(_env(content="Riley loves swimming"))
        mem_store.write_envelope(_env(content="Alex drinks coffee"))
        req = RecallRequest(
            space_id="family:smith",
            selectors=[RecallSelector(query="swim")],
        )
        rows = mem_store.recall(req)
        assert len(rows) == 1
        assert "swim" in rows[0]["content"].lower()

    def test_recall_multiple_selectors_dedup(self, mem_store):
        """Two selectors that match the same row should only return it once."""
        mem_store.write_envelope(_env(memory_type="semantic", content="shared memory"))
        req = RecallRequest(
            space_id="family:smith",
            selectors=[
                RecallSelector(memory_type="semantic"),
                RecallSelector(query="shared"),
            ],
        )
        rows = mem_store.recall(req)
        assert len(rows) == 1  # deduped

    def test_recall_results_newest_first(self, mem_store):
        for i in range(5):
            mem_store.write_envelope(_env(content=f"memory {i}"))
        req = RecallRequest(space_id="family:smith")
        rows = mem_store.recall(req)
        ids = [r["id"] for r in rows]
        assert ids == sorted(ids, reverse=True)


class TestObs:
    def test_write_obs_does_not_raise(self, mem_store):
        mem_store.write_obs("metrics", {"latency_ms": 42})

    def test_health_returns_row_count(self, mem_store):
        for i in range(3):
            mem_store.write_envelope(_env(content=f"mem {i}"))
        h = mem_store.health()
        assert h["wal_row_count"] == 3
        assert h["status"] == "ok"
        assert h["mode"] == "K0_LOCAL"


class TestStore:
    def test_persistent_db_survives_reopen(self, tmp_path):
        db = tmp_path / "test.db"
        s1 = SQLiteK0Store(db_path=db)
        s1.write_envelope(_env(content="persisted"))
        s1.close()

        s2 = SQLiteK0Store(db_path=db)
        rows = s2.recall(RecallRequest(space_id="family:smith"))
        s2.close()
        assert len(rows) == 1
        assert "persisted" in rows[0]["content"]
```

#### Issue E14.8.2 — Create `tests/scripts/pseudo_k0/test_server.py`

```python
"""Tests for pseudo-K0 FastAPI server.
Run: python -m pytest tests/scripts/pseudo_k0/test_server.py -q --no-cov
Requires: httpx (pip install httpx)
"""
import pytest
import httpx
from scripts.pseudo_k0.connector_host import ConnectorHost
from scripts.pseudo_k0.server import create_app
from scripts.pseudo_k0.store import SQLiteK0Store


@pytest.fixture
def app():
    store = SQLiteK0Store(":memory:")
    host = ConnectorHost()
    return create_app(store=store, connector_host=host), store, host


@pytest.fixture
def client(app):
    app_obj, store, host = app
    with httpx.Client(app=app_obj, base_url="http://test") as c:
        yield c, store, host


class TestHealth:
    def test_healthz_200(self, client):
        c, _, _ = client
        r = c.get("/healthz")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["mode"] == "K0_LOCAL"


class TestCommandSubmit:
    def test_valid_envelope_202(self, client):
        c, _, _ = client
        r = c.post("/k0/command.submit", json={
            "topic": "memory.write.v1",
            "space_id": "family:smith",
            "actor": "alex",
            "payload": {"type": "semantic", "content": "test memory"},
        })
        assert r.status_code == 202
        assert r.json()["accepted"] is True
        assert "wal_id" in r.json()

    def test_envelope_written_to_store(self, client):
        c, store, _ = client
        c.post("/k0/command.submit", json={
            "topic": "memory.write.v1",
            "space_id": "family:test",
            "payload": {"content": "uniqueword99"},
        })
        from scripts.pseudo_k0.models import RecallRequest, RecallSelector
        rows = store.recall(RecallRequest(
            space_id="family:test",
            selectors=[RecallSelector(query="uniqueword99")],
        ))
        assert len(rows) == 1

    def test_missing_topic_422(self, client):
        c, _, _ = client
        r = c.post("/k0/command.submit", json={"space_id": "x", "payload": {}})
        assert r.status_code == 422  # Pydantic validation error


class TestQueryRecall:
    def test_empty_recall(self, client):
        c, _, _ = client
        r = c.post("/k0/query.recall", json={"space_id": "family:empty"})
        assert r.status_code == 200
        assert r.json()["count"] == 0
        assert r.json()["results"] == []

    def test_recall_after_submit(self, client):
        c, _, _ = client
        c.post("/k0/command.submit", json={
            "topic": "memory.write.v1",
            "space_id": "family:recall_test",
            "payload": {"content": "hello recall"},
        })
        r = c.post("/k0/query.recall", json={"space_id": "family:recall_test"})
        assert r.status_code == 200
        assert r.json()["count"] >= 1


class TestObsEmit:
    def test_obs_204(self, client):
        c, _, _ = client
        r = c.post("/k0/obs.emit", json={"kind": "metrics", "body": {"k": "v"}})
        assert r.status_code == 204


class TestConnectorExecute:
    def test_unknown_adapter_returns_error(self, client):
        c, _, _ = client
        r = c.post("/k0/connector.execute", json={
            "adapter_id": "does_not_exist",
            "action": "list",
            "params": {},
        })
        assert r.status_code == 200
        assert r.json()["success"] is False
        assert "unknown adapter" in r.json()["error"]

    def test_registered_adapter_dispatched(self, client):
        c, store, host = client

        class PingHandler:
            async def call(self, *, action, params, trace_id):
                return {"pong": True}

        host.register("ping", PingHandler())
        r = c.post("/k0/connector.execute", json={
            "adapter_id": "ping",
            "action": "ping",
            "params": {},
        })
        assert r.status_code == 200
        assert r.json()["success"] is True
        assert r.json()["result"]["pong"] is True
```

#### Issue E14.8.3 — Create `tests/scripts/pseudo_k0/test_connector_host.py`

```python
"""Tests for ConnectorHost.
Run: python -m pytest tests/scripts/pseudo_k0/test_connector_host.py -q --no-cov
"""
import pytest
from scripts.pseudo_k0.connector_host import ConnectorHost, IMCPHandler


class EchoHandler:
    async def call(self, *, action, params, trace_id):
        return {"echo_action": action, "echo_params": params}


class ErrorHandler:
    async def call(self, *, action, params, trace_id):
        raise ValueError("simulated error")


class NotImplementedHandler:
    async def call(self, *, action, params, trace_id):
        raise NotImplementedError


class TestConnectorHost:
    @pytest.mark.asyncio
    async def test_unknown_adapter_returns_error_dict(self):
        host = ConnectorHost()
        result = await host.dispatch("unknown", "action", {})
        assert result["success"] is False
        assert "unknown adapter" in result["error"]

    @pytest.mark.asyncio
    async def test_registered_handler_dispatched(self):
        host = ConnectorHost()
        host.register("echo", EchoHandler())
        result = await host.dispatch("echo", "greet", {"name": "Alex"})
        assert result["success"] is True
        assert result["result"]["echo_action"] == "greet"
        assert result["result"]["echo_params"]["name"] == "Alex"

    @pytest.mark.asyncio
    async def test_handler_exception_returns_error(self):
        host = ConnectorHost()
        host.register("error_tool", ErrorHandler())
        result = await host.dispatch("error_tool", "do_it", {})
        assert result["success"] is False
        assert "simulated error" in result["error"]

    @pytest.mark.asyncio
    async def test_not_implemented_handler(self):
        host = ConnectorHost()
        host.register("stub", NotImplementedHandler())
        result = await host.dispatch("stub", "action", {})
        assert result["success"] is False
        assert "not implemented" in result["error"]

    def test_registered_adapters_list(self):
        host = ConnectorHost()
        host.register("calendar", EchoHandler())
        host.register("tasks", EchoHandler())
        assert host.registered_adapters == ["calendar", "tasks"]

    def test_unregister_removes_handler(self):
        host = ConnectorHost()
        host.register("tmp", EchoHandler())
        host.unregister("tmp")
        assert "tmp" not in host.registered_adapters

    def test_register_overwrites(self):
        host = ConnectorHost()
        host.register("echo", EchoHandler())
        host.register("echo", EchoHandler())  # must not raise
        assert host.registered_adapters == ["echo"]
```

---

### E14.9 — Implementation Order

```text
Step 1:  Run pre-flight checklist (E14.7) — answer all 8 checks
Step 2:  Create scripts/pseudo_k0/__init__.py (E14.1.2)
Step 3:  Create scripts/pseudo_k0/models.py (E14.2.1)
Step 4:  Create scripts/pseudo_k0/store.py (E14.3.1)
Step 5:  Create scripts/pseudo_k0/connector_host.py (E14.4.1)
Step 6:  Create scripts/pseudo_k0/server.py (E14.5.1)
Step 7:  Create scripts/pseudo_k0/__main__.py (E14.5.2)
Step 8:  Run pseudo-K0 tests: python -m pytest tests/scripts/pseudo_k0/ -q --no-cov
Step 9:  Add k0_endpoint field to k1/concierge/config/kernel.py (E14.6.1)
Step 10: Create k1/kernel/adapters/live_bridge_adapter.py (E14.6.2)
Step 11: Edit k1/kernel/service.py S4 block (E14.6.3) — add k0_endpoint branch
Step 12: Edit ui/web/__main__.py to read K0_ENDPOINT env var (E14.6.4)
Step 13: Edit ui/web/coordinator.py _phase2_kernel_startup() (E14.6.5)
Step 14: Smoke test pseudo-K0:
           python -m scripts.pseudo_k0 --port 8090 --db data/pseudo_k0_test.db &
           curl -s http://localhost:8090/healthz
Step 15: Boot K1 with K0:
           $env:K0_ENDPOINT = "http://localhost:8090"
           python -m ui.web --test-mode --port 8765
Step 16: Submit a memory via K1 and verify it appears in pseudo-K0:
           curl -s http://localhost:8090/k0/query.recall \
             -d '{"space_id":"family:smith"}' -H 'content-type: application/json'
Step 17: Check K1 /api/status shows bridge_mode=LIVE (not OFFLINE)
```

**Key gotchas:**

1. `HttpBridgeClient` MUST be built via `BridgeRuntime.from_registry()` — the CI gate
   `bridge_client_construction_via_runtime_only` will fail the build if you call `HttpBridgeClient(...)` directly.
2. `bridge/contracts/` path must exist and contain valid manifests — `BridgeRuntime.from_registry()` loads all YAML files there. Verify with step 3 of pre-flight.
3. Pseudo-K0's `/healthz` path must match `HttpTransport.HEALTH_PATH = "/healthz"` (not `/k0/healthz`).
4. Pseudo-K0's `/k0/command.submit` path must match `HttpTransport.COMMAND_PATH = "/k0/command.submit"`.
5. The `_startup_tier1()` must be async for the `await live_adapter.connect()` call — verify in pre-flight step 8.

---

## M15 — Native Family Apps Foundation (The Moat Layer)

**Design doc**: [docs/whiteboard/whiteboard_family_apps.md](../whiteboard/whiteboard_family_apps.md)
(read this first — it covers the moat thesis, app roster, three-faces architecture, visibility
model, and Q1–Q12 design decisions).

**Goal**: Build the _foundation_ that hosts FamilyOS's native family apps + ship the five
tier-1 apps on top of it (Calendar, Tasks, Reminders, Chores, Shopping List).

**Foundation-first principle**: Every future app — Health, Finance, IoT, Documents, School,
Photos, Location — will plug into the same `BaseToolService` + `ToolDefinition` +
`ManifestRegistry` + `VisibilityPolicy` + `EventEmitter` primitives built here. M15 is
explicitly **infrastructure-shaped**, not "five hand-rolled CRUD apps". The five apps shipped
in M15 are the proof-of-pattern; the moat is the foundation.

**LLM-reasoning-first principle**: Every tool exposes itself to the Concierge LLM through
five primitive surfaces — (1) a typed action signature, (2) semantic `use_when` hints, (3)
canonical few-shot examples, (4) read-before-write affordances (every `*.create_*` has a
paired `*.list_*` and `*.get_*`), (5) cross-tool reference IDs. This makes M15 the substrate
the planner reasons over to decide _which tool to call, when, with what args, and how to verify_.

**Supersedes**: this section replaces the previous M11 plan ("Native Family Tools via Bridge").
M11 the milestone ID is retired — its scope is fully absorbed here.

---

### M15 ARCHITECTURE REVISION (2026-05-11) — K1-hot / K0-optional

> **READ THIS BEFORE ANY OTHER M15 SUBSECTION.** This revision supersedes wiring
> decisions in §E15.0–§E15.10 below. The Pydantic models, ACL, manifest generator,
> visibility policy, and CRUD logic are unchanged. **Hosting kernel and dispatch
> boundary change.**

#### R-1 — Storage tiering pivot

- **K1 is HOT storage.** All app projection tables (`calendar_events`, `task_items`,
  `reminders`, `chores`, `shopping_items`, `family_settings`) live in a K1-resident
  SQLite file (`data/k1_family.db`). All reads and writes happen K1-locally.
- **K0 is COLD storage / sync target — OPTIONAL.** When `K0_ENDPOINT` is set, an
  outbox-style replicator forwards `*.create|update|delete.v1` envelopes to K0's WAL.
  When unset, apps work fully offline. K0 is **never** in the dispatch hot path.
- **Sync is fire-and-forget through the existing M14 bridge.** Apps must not block on
  K0 availability.

#### R-2 — Canonical dispatch path (replaces ADQ-4 from M15 readiness audit)

```
LLM tool_call("calendar.create_event", args)
  → execute_invoke_capability                          [k1/concierge]
  → FabricDispatchAdapter.dispatch_direct
  → CapabilityFabric.execute(CapabilityRequest)
  → NativeToolProvider     (NEW — provider_type="LOCAL", in-process)
  → BaseToolService.dispatch(action, params, ctx)      [K1-resident]
     ├─ band check (step 0)
     ├─ role gate
     ├─ idempotency check
     ├─ pre/post hooks
     ├─ writes to K1 hot SQLite                        [data/k1_family.db]
     ├─ emits SSE locally via k1.sse.publisher
     └─ enqueues sync envelope → bridge outbox → K0 (best-effort)
```

UI/REST face mounts on **K1's existing web app** (`ui/web`), not pseudo-K0, and calls
`service.dispatch()` directly. Voice face goes through Fabric like LLM.

`scripts/pseudo_k0/tools/` is **deleted from this milestone**. Pseudo-K0 (M14) keeps
only its existing surfaces: `/k0/command.submit`, `/k0/query.recall`, `/k0/obs.emit`,
`/k0/healthz`, `/k0/sse.subscribe`. The `/k0/connector.execute` slot stays in M14 for
real-K0 compatibility but is **not exercised by M15 apps**.

#### R-3 — Path translation table

Throughout §E15.0–§E15.10 below, treat every reference as follows:

| Plan text (obsolete)                              | Apply as (canonical)                          |
|---------------------------------------------------|-----------------------------------------------|
| `scripts/pseudo_k0/tools/base.py`                 | `k1/tools/family/base.py`                     |
| `scripts/pseudo_k0/tools/definition.py`           | `k1/tools/family/definition.py`               |
| `scripts/pseudo_k0/tools/registry.py`             | `k1/tools/family/registry.py`                 |
| `scripts/pseudo_k0/tools/manifest.py`             | `k1/tools/family/manifest.py`                 |
| `scripts/pseudo_k0/tools/policy.py`               | `k1/tools/family/policy.py`                   |
| `scripts/pseudo_k0/tools/acl.py`                  | `k1/tools/family/acl.py`                      |
| `scripts/pseudo_k0/tools/events.py`               | `k1/tools/family/events.py`                   |
| `scripts/pseudo_k0/tools/handler.py`              | `k1/tools/family/provider.py` (NativeToolProvider — see R-4) |
| `scripts/pseudo_k0/tools/routes.py`               | `k1/tools/family/routes.py` (mounted on `ui/web`) |
| `scripts/pseudo_k0/tools/idem.py`                 | `k1/tools/family/idem.py`                     |
| `scripts/pseudo_k0/tools/links.py`                | `k1/tools/family/links.py`                    |
| `scripts/pseudo_k0/tools/{app}/...`               | `k1/tools/family/{app}/...`                   |
| `ConnectorHost.register(adapter_id, handler)`     | `fabric.registry.register(CapabilityContract)` per action |
| `_ServiceHandler` (IMCPHandler wrapper)           | `NativeToolProvider` (CapabilityProvider impl)|
| SQLite conn from `SQLiteK0Store._conn`            | `K1FamilyStore(data/k1_family.db)` (NEW; M15 owns it) |
| Pseudo-K0 SSE fan-out (`emitter.subscribe(space)`)| K1 SSE publisher (`k1.sse.publisher.publish`) |

`tests/scripts/pseudo_k0/tools/...` → `tests/k1/tools/family/...`.

#### R-4 — NativeToolProvider (replaces ConnectorProvider/`_ServiceHandler`)

Add a single new module `k1/fabric/providers/native_tool_provider.py`:

```python
"""NativeToolProvider — in-process CapabilityProvider for K1-native tools.

Resolves provider_type="LOCAL" + provider_id="k1_native_tools".
Looks up the BaseToolService by adapter_id from a registry passed at construction,
builds WriteContext from ISessionStateReader, and calls service.dispatch().
NO HTTP, NO bridge round-trip. Pure in-process dispatch.
"""
```

Boot-time wiring (in `KernelService._startup_tier2()` or equivalent, after Fabric is
constructed): instantiate `K1FamilyStore`, `EventEmitter`, `IdempotencyStore`,
`ToolRegistry`, register the 6 service classes, then call
`manifest_translator.register_with_fabric(registry, fabric)`.

#### R-5 — Three blockers + resolutions

1. **`k1/fabric/manifest_translator.py` does not exist.** Was claimed "existing module"
   in old §E15.0 read-list and in whiteboard. **Resolution:** create it as a real file
   in this milestone (see §E15.0.0 below). Its job: iterate `ToolDefinition.actions`,
   register each as a `CapabilityContract(name="{adapter_id}.{action}",
   provider_type="LOCAL", provider_id="k1_native_tools")`.

2. **`ConnectorHost.register()` API mismatch.** Moot under R-1/R-2: ConnectorHost is
   no longer in the dispatch path. The `_ServiceHandler` IMCPHandler wrapper is
   **deleted**. Replaced by `NativeToolProvider` (R-4).

3. **Fabric → `execute_connector` path unproven.** Moot under R-2: we do not route
   through `execute_connector`. The provable path is Fabric → `NativeToolProvider` →
   in-process call. See §E15.-1 below for the proof-of-path step.

#### R-6 — Five plan enhancements (locked in)

| # | Enhancement | Where applied |
|---|---|---|
| E1 | Add §E15.-1 proof-of-path step (Fabric→NativeToolProvider→stub service) | Inserted before §E15.0 below |
| E2 | Create `k1/fabric/manifest_translator.py` as new module (not "existing") | §E15.0.0 (NEW) |
| E3 | Replace `_ServiceHandler` / `ConnectorHost.register` with `NativeToolProvider` + Fabric `CapabilityContract` registration | §E15.0.7 (REVISED) |
| E4 | Tool business logic in `k1/tools/family/`; no `scripts/pseudo_k0/tools/`; REST routes mount on `ui/web` | This R-3 table is the canonical mapping for §E15.0–§E15.10 |
| E5 | Bump dispatch signatures to thread `trace_id` end-to-end; `BaseToolService.dispatch` step 0 is `safety_band` check | §E15.0.6 already takes ctx; ensure `ctx.trace_id` is wired; add band step 0 |

#### R-7 — Additional discipline (from M15 readiness audit)

- **P7** — every `tables_sql` must include a `{adapter_id}_schema_version` table; `BaseToolService.__init__` runs incremental migrations.
- **P9** — every WAL topic (`calendar.create_event.v1`, etc.) gets a contract manifest in `bridge/contracts/manifests/` by end of M15.
- **P10** — `k1/tools/family/` imports only from `k1.fabric.*` and `k1.kernel.ports.*`; **no `bridge.*` imports** (CI gate `bridge_not_imported_from_kernels` enforces this).
- **Observability** — `BaseToolService.dispatch()` emits `k1.tools.{adapter_id}.dispatch.{ok|error}.v1` on the k1 bus; per-action latency histogram via `k1.fabric.metrics`.
- **REST bypass documented** — UI face calls `service.dispatch()` directly (no Fabric round-trip). Both faces hit the same `dispatch()`, which is the **single point** where invariants apply.

#### R-8 — Acceptance criteria addendum

The §E15.16 acceptance list must be re-read with R-3 path translation. In addition:

- **AC-A** — When `K0_ENDPOINT` is unset, all 5 apps still work end-to-end (create/list/update/delete via REST and via Fabric). K0 absence is not a failure.
- **AC-B** — When `K0_ENDPOINT` is set, every successful write produces a sync envelope visible in K0's WAL within 5s (best-effort, no SLA).
- **AC-C** — Concierge LLM `tool_call("calendar.create_event", ...)` routes through `execute_invoke_capability` → `FabricDispatchAdapter.dispatch_direct` → `NativeToolProvider` → `BaseToolService.dispatch`. Verified by integration test in §E15.-1.
- **AC-D** — `k1/tools/family/` contains zero `bridge.*` imports (CI gate green).

---

### E15.-1 — Proof-of-path: Fabric → NativeToolProvider → stub service (PREREQ)

**Do this BEFORE writing any app.** It proves the canonical R-2 path on a 50-LOC stub.

1. Create `k1/fabric/providers/native_tool_provider.py` (NEW) implementing
   `CapabilityProvider` for `provider_type="LOCAL"`, `provider_id="k1_native_tools"`.
   It takes a `registry: ToolRegistryReader` (protocol with `get(adapter_id)`) at
   construction, resolves `capability_name="adapter.action"`, builds `WriteContext`
   from `ISessionStateReader.read_section(session_id, "control")`, calls
   `service.dispatch(action, params, ctx)`, returns result dict.
2. Create a `PingToolService(BaseToolService)` stub with one action `ping` that
   returns `{"pong": True}`. Place it in `tests/k1/tools/family/_stubs.py`.
3. In a pytest fixture: build Fabric, register a `CapabilityContract(name="ping.ping",
   provider_type="LOCAL", provider_id="k1_native_tools")`, wire `NativeToolProvider`
   into `FabricFactory.create_with_ports()`.
4. Test calls `fabric.execute(CapabilityRequest(capability_name="ping.ping",
   session_id=..., params={}, safety_band="GREEN"))` and asserts result `{"pong": True}`.
5. Acceptance: test passes. **Only then proceed to §E15.0.**

File: `k1/fabric/providers/native_tool_provider.py` (NEW)
Test: `tests/k1/fabric/providers/test_native_tool_provider_path.py` (NEW)

---

### E15.0.0 — Create `k1/fabric/manifest_translator.py` (NEW — was incorrectly claimed "existing")

```python
"""k1.fabric.manifest_translator — registers ToolDefinitions with Fabric.

At K1 boot, called by ToolRegistry after all services are registered:

    manifest_translator.register_with_fabric(registry, fabric)

For each service.DEFINITION.actions, emit:

    fabric.registry.register(CapabilityContract(
        name=f"{adapter_id}.{action.name}",
        provider_type="LOCAL",
        provider_id="k1_native_tools",
        input_schema=action.params_schema,
        output_schema=action.result_schema,
        min_safety_band=action.min_band,
        description=action.llm_hints.use_when if action.llm_hints else "",
    ))
"""
```

File: `k1/fabric/manifest_translator.py` (NEW). All references in §E15.0 read-list
and in [whiteboard_family_apps.md:468](../whiteboard/whiteboard_family_apps.md) that
call this "existing" are **incorrect** and superseded by this section.

---

### E15.0 — Foundation Layer (the only part future apps reuse)

All ~700 lines of this section are written once and never touched again when adding new apps
(health, finance, IoT, etc.). Apps in §E15.5+ are _thin_ — each is ~250 LOC because the
foundation does the heavy lifting.

#### Read first before coding

> **Apply R-3 path translation throughout this subsection** (see revision block above).
> Files documented as `scripts/pseudo_k0/tools/X` live at `k1/tools/family/X`.

- [k1/fabric/manifest_translator.py](k1/fabric/manifest_translator.py) — **NEW in this
  milestone (§E15.0.0)**. Translates `ToolDefinition` → Fabric `CapabilityContract`.
  Earlier text calling this "existing module" was incorrect.
- [k1/fabric/providers/native_tool_provider.py](k1/fabric/providers/native_tool_provider.py)
  — **NEW (§E15.-1)**. In-process `CapabilityProvider` for `provider_type="LOCAL"`.
- [k1/fabric/fabric.py](k1/fabric/fabric.py) — `CapabilityRegistryAPI.register(contract)`.
  Each action becomes one `CapabilityContract`.
- [k1/concierge/tools/implementations.py](k1/concierge/tools/implementations.py) — the
  `execute_invoke_capability` entrypoint (≈line 1219) is the LLM ingress.
- [k1/concierge/adapters/fabric_dispatch.py](k1/concierge/adapters/fabric_dispatch.py) —
  `FabricDispatchAdapter.dispatch_direct` routes non-workflow capabilities to Fabric.
- [verticals/family/profile.py](verticals/family/profile.py) (M13) — `FamilyProfile`,
  `FamilyMember`. Source of `member_id`, `role`, `space_id` used by ACL.
- [bridge/connector/](bridge/connector/) — real-K0 `ConnectorGateway`. **Not in M15
  hot path.** Used only by the sync outbox forwarder when `K0_ENDPOINT` is set.
- [scripts/pseudo_k0/](scripts/pseudo_k0/) (M14) — kept as-is for the M14 surfaces
  (`command.submit`, `query.recall`, `obs.emit`, `healthz`, `sse.subscribe`). M15
  apps **do not** register handlers here.

#### Foundation file layout (all NEW)

```text
scripts/pseudo_k0/tools/
├── __init__.py                ← package marker + version
├── base.py                    ← BaseEntity (Pydantic) + BaseToolService
├── definition.py              ← ToolDefinition, ActionSpec, FieldSpec, LLMHints
├── registry.py                ← ToolRegistry: discovery + ConnectorHost wiring + Fabric registration
├── manifest.py                ← ManifestGenerator: per-role UI/LLM/OpenAPI manifests
├── policy.py                  ← VisibilityPolicy (rules) + default rules
├── acl.py                     ← ACL filter functions (read-time)
├── events.py                  ← EventEmitter: WAL + SSE fan-out
├── handler.py                 ← _ServiceHandler: ConnectorHost handler wrapping a ToolService
├── routes.py                  ← _build_tool_router: REST router factory for any ToolService
├── idem.py                    ← IdempotencyStore: dedupe per (adapter, action, idem_key)
└── links.py                   ← CrossToolLink: typed references between app entities

k1/tools/family/
├── __init__.py
├── client.py                  ← FamilyToolClient: generic REST wrapper used by UI shell
├── manifest_cache.py          ← caches role-filtered manifests pulled from pseudo-K0
└── reasoning.py               ← LLMReasoningContext: builds Fabric tool specs from manifest
```

---

### E15.0.1 — `BaseEntity` (universal entity Pydantic base)

Every tool entity (CalendarEvent, TaskItem, Reminder, etc.) inherits from this. The fields
encode provenance, ACL, optimistic concurrency, audit trail, and cross-tool linkage — features
EVERY future app gets for free.

File: `scripts/pseudo_k0/tools/base.py`

```python
"""scripts.pseudo_k0.tools.base — BaseEntity + BaseToolService foundation.

Every native family app entity inherits BaseEntity. Every service inherits
BaseToolService. The hooks (_pre_write, _post_write, _apply_acl) are how future
apps customize behavior without rewriting the CRUD + sync + manifest machinery.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from typing import Any, ClassVar, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

Visibility = Literal["family", "adults", "named", "private"]
SourceKind = Literal[
    "native", "google", "outlook", "teams", "classroom",
    "apple", "manual_import", "system_generated",
]


def _now_ms() -> int:
    return int(time.time() * 1000)


def _new_id() -> str:
    """uuid7-ish — time-sortable, collision-free."""
    return uuid.uuid4().hex


class BaseEntity(BaseModel):
    """Universal entity base — every app's entity inherits this.

    Provenance, ACL, audit, optimistic concurrency, cross-tool linkage are all
    encoded here so apps cannot accidentally skip them.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    # ---------- Identity ----------
    id: str = Field(default_factory=_new_id)
    space_id: str                              # "family:smith"
    tenant_id: str = ""

    # ---------- Audit ----------
    created_by: str                            # member_id
    created_at: int = Field(default_factory=_now_ms)
    updated_by: str = ""                       # filled by service on update
    updated_at: int = Field(default_factory=_now_ms)
    version: int = 1                           # optimistic concurrency

    # ---------- Provenance ----------
    source: SourceKind = "native"
    source_ref: str | None = None              # external id (etag, gcal eventId, etc.)
    source_account: str | None = None          # which member's external account
    source_label: str | None = None            # "work" | "personal" — drives policy

    # ---------- ACL ----------
    visibility: Visibility | None = None       # None → policy assigns
    visible_to: list[str] = Field(default_factory=list)

    # ---------- Extensibility ----------
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    # ---------- Cross-tool linkage ----------
    linked_to: list[dict[str, str]] = Field(default_factory=list)
    # Each link: {"adapter_id": "tasks", "entity_id": "abc123", "rel": "spawned_from"}

    def bump(self, actor_member_id: str) -> None:
        """Increment version and audit on every update."""
        self.version += 1
        self.updated_by = actor_member_id
        self.updated_at = _now_ms()


class WriteContext(BaseModel):
    """Per-call context every action handler receives.

    Encodes WHO is calling and through WHICH face — needed for ACL,
    idempotency, and audit. Built once at ConnectorHost.dispatch() or
    REST route entrypoint; passed through unchanged.
    """
    model_config = ConfigDict(extra="forbid")

    actor_member_id: str                       # "alex" | "jordan" | ...
    actor_role: Literal["parent", "child", "guardian", "elder", "system"]
    space_id: str                              # "family:smith"
    tenant_id: str = ""
    trace_id: str | None = None
    face: Literal["llm", "ui", "voice", "system", "feed"] = "ui"
    idem_key: str | None = None                # if provided, replay-safe
```

---

### E15.0.2 — `ToolDefinition` (declarative tool spec)

This is the **single declarative source** for everything about a tool. Every consumer reads
from here: UI renderer, LLM tool registry, OpenAPI, Fabric, MCP handler. One declaration,
many surfaces.

File: `scripts/pseudo_k0/tools/definition.py`

```python
"""scripts.pseudo_k0.tools.definition — ToolDefinition declarative spec.

A ToolDefinition is the single source of truth for one app. From it we
generate:
    - UI manifest (per role)
    - LLM tool spec (Fabric capability contracts)
    - OpenAPI route specs
    - MCP handler registration
    - DDL for projection tables (via tables_sql field)
    - Authorization rules (per action min_role + per action min_band)

Adding a new app = write ONE ToolDefinition + Pydantic models + service class.
"""
from __future__ import annotations

from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["parent", "child", "guardian", "elder", "system"]
Band = Literal["GREEN", "AMBER", "RED", "BLACK"]
FieldType = Literal[
    "string", "text", "int", "float", "bool", "datetime", "date", "duration",
    "enum", "enum_multi", "member", "member_multi", "entity_ref",
    "money", "location", "json",
]


class FieldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: FieldType
    label: str | None = None
    required: bool = False
    default: Any = None
    options: list[str] | None = None           # for enum/enum_multi
    show_when: str | None = None               # JSON-Logic predicate
    description: str | None = None             # LLM hint for this field
    examples: list[Any] | None = None          # few-shot values
    ref_adapter: str | None = None             # for entity_ref


class LLMHints(BaseModel):
    """LLM reasoning hints attached to each action. Critical for moat — this
    is what makes the Concierge planner *good* at picking the right tool."""
    model_config = ConfigDict(extra="forbid")

    use_when: list[str] = Field(default_factory=list)
    do_not_use_when: list[str] = Field(default_factory=list)
    examples: list[dict[str, Any]] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    side_effects: list[str] = Field(default_factory=list)
    related_actions: list[str] = Field(default_factory=list)
    typical_followups: list[str] = Field(default_factory=list)
    read_before_write: str | None = None


class ActionSpec(BaseModel):
    """One action on a tool (create_event, update_task, etc.).

    The handler is a coroutine; `min_role`/`min_band` are checked by
    BaseToolService.dispatch() before invocation. `form` drives BOTH the UI
    rendering and the LLM tool argument schema.
    """
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    name: str                                  # "create_event"
    label: str                                 # "New event"
    kind: Literal["read", "write", "delete", "compute"] = "write"
    primary: bool = False                      # UI: show as primary CTA
    context: str | None = None                 # "per_event_gear_icon", "global_fab", etc.
    form: list[FieldSpec] = Field(default_factory=list)
    output_schema: dict[str, Any] | None = None
    min_role: Role | None = None               # None → all roles allowed
    min_band: Band = "AMBER"
    idempotent: bool = False                   # safe to retry with same idem_key
    llm: LLMHints = Field(default_factory=LLMHints)
    handler: Callable | None = None            # bound at registration


class SSESpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    on_write_topic: str = "tool_state.changed.v1"
    extra_keys: list[str] = Field(default_factory=list)


class ToolDefinition(BaseModel):
    """The full declarative spec for one tool.

    Add a new app =
      1. Subclass BaseEntity for each entity type
      2. Write tables_sql (DDL for projection tables)
      3. Construct ToolDefinition(...)
      4. Subclass BaseToolService and implement entity-specific logic
      5. Register with ToolRegistry — everything else (UI, LLM, REST, MCP, SSE)
         flows from this single declaration.
    """
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    adapter_id: str                            # "calendar" | "tasks" | "health.medication"
    version: str = "1.0"
    title: str
    icon: str | None = None
    category: Literal["coordination", "health", "finance", "iot",
                      "knowledge", "system"] = "coordination"
    description: str
    entity_type: str                           # display name "CalendarEvent"
    actions: list[ActionSpec]
    views: dict[str, Any] = Field(default_factory=dict)
    filters: dict[str, Any] = Field(default_factory=dict)
    tables_sql: str                            # DDL for projection tables
    sse: SSESpec = Field(default_factory=SSESpec)
    feature_flags: dict[str, bool] = Field(default_factory=dict)
    # Cross-tool linkage hints — what entities this tool can reference
    can_reference: list[str] = Field(default_factory=list)
```

---

### E15.0.3 — `VisibilityPolicy` + ACL

`VisibilityPolicy` is the pluggable extension point. M15 ships the default rule set described
in the whiteboard. Future apps (health, finance) supply additional rule lists without touching
the core.

File: `scripts/pseudo_k0/tools/policy.py`

```python
"""scripts.pseudo_k0.tools.policy — VisibilityPolicy.

A pluggable rule chain. M15 ships default rules. Health/Finance/IoT apps
add additional rules (e.g. HIPAA: any medication entity → adults).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from scripts.pseudo_k0.tools.base import BaseEntity, Visibility

Rule = Callable[[BaseEntity, str], Visibility | None]
# (entity, creator_role) → visibility or None to fall through


@dataclass
class VisibilityPolicy:
    rules: list[Rule] = field(default_factory=list)
    default: Visibility = "family"

    def apply(self, entity: BaseEntity, creator_role: str) -> Visibility:
        if entity.visibility is not None:
            return entity.visibility           # explicit override wins
        for rule in self.rules:
            v = rule(entity, creator_role)
            if v is not None:
                return v
        return self.default

    def add(self, rule: Rule) -> None:
        self.rules.append(rule)


# ---------- Default rule set (shipped in M15) ----------

_SENSITIVE_KEYWORDS = {"doctor", "therapy", "appointment", "medication",
                       "prescription", "diagnosis", "salary"}


def _native_default(e: BaseEntity, role: str) -> Visibility | None:
    if e.source == "native":
        return "family"
    return None


def _google_work(e: BaseEntity, role: str) -> Visibility | None:
    if e.source == "google" and e.source_label == "work":
        return "adults"
    return None


def _google_personal(e: BaseEntity, role: str) -> Visibility | None:
    if e.source == "google" and e.source_label == "personal":
        return "private"
    return None


def _outlook_default(e: BaseEntity, role: str) -> Visibility | None:
    if e.source in ("outlook", "teams"):
        return "adults"
    return None


def _classroom_default(e: BaseEntity, role: str) -> Visibility | None:
    if e.source == "classroom":
        return "named"
    return None


def _sensitive_keywords(e: BaseEntity, role: str) -> Visibility | None:
    text_blob = " ".join([
        str(getattr(e, "title", "")),
        str(getattr(e, "notes", "")),
        str(getattr(e, "name", "")),
    ]).lower()
    if any(kw in text_blob for kw in _SENSITIVE_KEYWORDS):
        return "adults"
    return None


def default_policy() -> VisibilityPolicy:
    return VisibilityPolicy(
        rules=[
            _sensitive_keywords,               # most restrictive first
            _google_work,
            _google_personal,
            _outlook_default,
            _classroom_default,
            _native_default,
        ],
        default="family",
    )
```

File: `scripts/pseudo_k0/tools/acl.py`

```python
"""scripts.pseudo_k0.tools.acl — Read-time visibility filter."""
from __future__ import annotations

from typing import Any, Iterable

from scripts.pseudo_k0.tools.base import WriteContext


def filter_rows(
    rows: Iterable[dict[str, Any]],
    ctx: WriteContext,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if row.get("created_by") == ctx.actor_member_id:
            out.append(row)                    # always see own
            continue
        vis = row.get("visibility") or "family"
        if vis == "family":
            out.append(row)
        elif vis == "adults" and ctx.actor_role in ("parent", "guardian"):
            out.append(row)
        elif vis in ("named", "private"):
            visible_to = row.get("visible_to") or []
            if isinstance(visible_to, str):
                import json
                try:
                    visible_to = json.loads(visible_to)
                except Exception:
                    visible_to = []
            if ctx.actor_member_id in visible_to:
                out.append(row)
    return out
```

---

### E15.0.4 — `EventEmitter` (WAL + SSE fan-out)

Every write goes through this. Ensures the durable audit log + cross-family fan-out cannot
be accidentally skipped by an app author.

File: `scripts/pseudo_k0/tools/events.py`

```python
"""scripts.pseudo_k0.tools.events — uniform WAL + SSE emit.

Every write through BaseToolService routes here. App authors cannot
write directly to projection tables — they go through this emitter so
the WAL + SSE invariants always hold.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from scripts.pseudo_k0.models import Envelope
from scripts.pseudo_k0.store import SQLiteK0Store
from scripts.pseudo_k0.tools.base import BaseEntity, WriteContext

logger = logging.getLogger(__name__)


class EventEmitter:
    """WAL + SSE emitter shared by all tool services.

    SSE fan-out is a list of subscribed asyncio.Queue's, populated by the
    /k0/sse.subscribe route in pseudo_k0/server.py. M15 wires that.
    """

    def __init__(self, store: SQLiteK0Store) -> None:
        self._store = store
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        # space_id → [queue, queue, ...]

    # ---------- SSE subscription wiring (used by server.py) ----------

    def subscribe(self, space_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.setdefault(space_id, []).append(q)
        return q

    def unsubscribe(self, space_id: str, q: asyncio.Queue) -> None:
        try:
            self._subscribers.get(space_id, []).remove(q)
        except ValueError:
            pass

    # ---------- Emit (called by BaseToolService) ----------

    async def emit_write(
        self,
        adapter_id: str,
        op: str,                # "create_event" | "update_task" | etc.
        entity: BaseEntity,
        ctx: WriteContext,
    ) -> int:
        """Write to WAL, then fan out tool_state.changed.v1 SSE event."""
        # 1. WAL (durable audit) — via existing SQLiteK0Store.write_envelope()
        env = Envelope(
            topic=f"{adapter_id}.{op}.v1",
            space_id=entity.space_id,
            tenant_id=entity.tenant_id,
            actor=ctx.actor_member_id,
            cognitive_trace_id=ctx.trace_id,
            payload=entity.model_dump(mode="json"),
        )
        wal_id = self._store.write_envelope(env)

        # 2. SSE fan-out — tool_state.changed.v1
        payload = {
            "type": "tool_state.changed.v1",
            "wal_id": wal_id,
            "tool": adapter_id,
            "op": op,
            "entity_id": entity.id,
            "entity_type": entity.__class__.__name__,
            "version": entity.version,
            "space_id": entity.space_id,
            "actor": ctx.actor_member_id,
            "visibility_hint": entity.visibility or "family",
        }
        for q in list(self._subscribers.get(entity.space_id, [])):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning("SSE queue full for space=%s — dropping event", entity.space_id)
        return wal_id
```

---

### E15.0.5 — `IdempotencyStore` (replay-safe writes)

LLM may retry a tool call. Reliability requires idempotency. The store dedupes by
`(adapter_id, action, idem_key)` and returns the cached result on replay.

File: `scripts/pseudo_k0/tools/idem.py`

```python
"""scripts.pseudo_k0.tools.idem — replay-safe idempotency cache."""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

_DDL = """
CREATE TABLE IF NOT EXISTS tool_idem (
    adapter_id TEXT NOT NULL,
    action     TEXT NOT NULL,
    idem_key   TEXT NOT NULL,
    space_id   TEXT NOT NULL,
    result     TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (adapter_id, action, idem_key, space_id)
);
"""

_TTL_S = 24 * 3600        # 24h


class IdempotencyStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.executescript(_DDL)
        self._conn.commit()

    def lookup(self, adapter_id: str, action: str, idem_key: str, space_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT result, created_at FROM tool_idem "
            "WHERE adapter_id=? AND action=? AND idem_key=? AND space_id=?",
            (adapter_id, action, idem_key, space_id),
        ).fetchone()
        if row is None:
            return None
        if int(time.time()) - row[1] > _TTL_S:
            return None
        return json.loads(row[0])

    def record(self, adapter_id: str, action: str, idem_key: str, space_id: str, result: dict) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO tool_idem VALUES (?,?,?,?,?,?)",
            (adapter_id, action, idem_key, space_id,
             json.dumps(result, default=str), int(time.time())),
        )
        self._conn.commit()
```

---

### E15.0.6 — `BaseToolService` (the core of the foundation)

File: `scripts/pseudo_k0/tools/base.py` (append to the BaseEntity file)

```python
class BaseToolService:
    """Foundation class every app's service inherits.

    Subclasses override:
        DEFINITION:        ClassVar[ToolDefinition] — declarative spec
        ENTITY_CLASSES:    ClassVar[dict[str, type[BaseEntity]]] — type registry
        _upsert(entity, ctx):    persist to projection table
        _delete(entity_id, ctx): remove from projection table
        _select(query, ctx):     query projection table (returns raw rows)

    The foundation handles:
        - action dispatch with role/band gates
        - visibility policy application
        - WAL + SSE emit on every write
        - ACL filter on every read
        - idempotency replay
        - audit log
        - manifest generation
        - Fabric capability registration
        - SSE subscription wiring
    """

    DEFINITION: ClassVar["ToolDefinition"]
    ENTITY_CLASSES: ClassVar[dict[str, type[BaseEntity]]] = {}

    def __init__(
        self,
        conn: sqlite3.Connection,
        emitter: "EventEmitter",
        policy: "VisibilityPolicy",
        idem: "IdempotencyStore",
    ) -> None:
        self.conn = conn
        self.emitter = emitter
        self.policy = policy
        self.idem = idem
        self._actions: dict[str, "ActionSpec"] = {a.name: a for a in self.DEFINITION.actions}
        # Ensure projection tables exist
        self.conn.executescript(self.DEFINITION.tables_sql)
        self.conn.commit()

    # ---------- Public API (called by ConnectorHost handler + REST routes) ----------

    async def dispatch(self, action: str, params: dict[str, Any], ctx: "WriteContext") -> dict[str, Any]:
        """The single entrypoint every face (LLM/UI/voice) calls."""
        spec = self._actions.get(action)
        if spec is None:
            return {"success": False, "error": f"unknown action: {action}"}

        # 1. Role gate
        if spec.min_role is not None:
            if not self._role_satisfies(ctx.actor_role, spec.min_role):
                return {"success": False, "error": f"role {ctx.actor_role} cannot {action}"}

        # 2. Idempotency replay
        if spec.idempotent and ctx.idem_key:
            cached = self.idem.lookup(self.DEFINITION.adapter_id, action, ctx.idem_key, ctx.space_id)
            if cached is not None:
                return {"success": True, "result": cached, "replayed": True}

        # 3. Invoke handler
        try:
            handler = spec.handler or getattr(self, action, None)
            if handler is None:
                return {"success": False, "error": f"no handler bound: {action}"}
            result = await handler(params=params, ctx=ctx)
        except PermissionError as e:
            return {"success": False, "error": f"permission: {e}"}
        except ValueError as e:
            return {"success": False, "error": f"validation: {e}"}
        except Exception as e:
            logger.exception("dispatch %s.%s failed", self.DEFINITION.adapter_id, action)
            return {"success": False, "error": str(e)}

        # 4. Cache idempotent results
        if spec.idempotent and ctx.idem_key and isinstance(result, dict):
            self.idem.record(self.DEFINITION.adapter_id, action, ctx.idem_key, ctx.space_id, result)

        return {"success": True, "result": result}

    # ---------- Helpers for subclasses ----------

    async def write_entity(self, op: str, entity: BaseEntity, ctx: WriteContext) -> int:
        """Helper: apply policy, persist, emit. Subclasses call this from write actions."""
        # Apply default visibility
        entity.visibility = self.policy.apply(entity, ctx.actor_role)
        # Persist to projection table (subclass implements)
        self._upsert(entity, ctx)
        # WAL + SSE
        wal_id = await self.emitter.emit_write(self.DEFINITION.adapter_id, op, entity, ctx)
        return wal_id

    async def read_entities(self, query: dict, ctx: WriteContext) -> list[dict]:
        """Helper: query projection, apply ACL. Subclasses call from list_* / get_*."""
        from scripts.pseudo_k0.tools.acl import filter_rows
        rows = self._select(query, ctx)
        return filter_rows(rows, ctx)

    async def delete_entity(self, entity_id: str, ctx: WriteContext, snapshot: BaseEntity) -> int:
        """Helper: tombstone + WAL + SSE. Subclasses call from delete_*."""
        self._delete(entity_id, ctx)
        snapshot.bump(ctx.actor_member_id)
        wal_id = await self.emitter.emit_write(
            self.DEFINITION.adapter_id, "delete", snapshot, ctx,
        )
        return wal_id

    # ---------- Subclass overrides ----------

    def _upsert(self, entity: BaseEntity, ctx: WriteContext) -> None:  # pragma: no cover
        raise NotImplementedError

    def _delete(self, entity_id: str, ctx: WriteContext) -> None:  # pragma: no cover
        raise NotImplementedError

    def _select(self, query: dict, ctx: WriteContext) -> list[dict]:  # pragma: no cover
        raise NotImplementedError

    # ---------- Role / band helpers ----------

    _ROLE_ORDER = {"system": 4, "parent": 3, "guardian": 2, "elder": 1, "child": 0}

    @classmethod
    def _role_satisfies(cls, actor: str, required: str) -> bool:
        return cls._ROLE_ORDER.get(actor, -1) >= cls._ROLE_ORDER.get(required, 0)
```

---

### E15.0.7 — `NativeToolProvider` + `ToolRegistry` (REVISED per R-3/R-4)

> **This subsection is REVISED.** Original text registered a `_ServiceHandler` against
> `ConnectorHost.register(adapter_id, handler)` — that API took only one argument and
> the handler did not implement `IMCPHandler`. Both issues are moot under R-2: dispatch
> is in-process via Fabric, no `ConnectorHost` involvement. Use the canonical wiring
> below.

#### `NativeToolProvider` — the in-process dispatch provider

File: `k1/fabric/providers/native_tool_provider.py` (NEW — created in §E15.-1)

```python
"""k1.fabric.providers.native_tool_provider — in-process tool dispatch.

Resolves Fabric capabilities of provider_type="LOCAL", provider_id="k1_native_tools".
Looks up the BaseToolService by adapter_id, builds WriteContext from session state
via ISessionStateReader, and calls service.dispatch(action, params, ctx).

NO HTTP. NO bridge. Pure in-process. K0_ENDPOINT does not need to be set.
"""
from __future__ import annotations

from typing import Any, Protocol

from k1.fabric.types import CapabilityRequest, CapabilityResult
from k1.kernel.ports import ISessionStateReader


class ToolRegistryReader(Protocol):
    def get(self, adapter_id: str) -> Any | None: ...  # returns BaseToolService


class NativeToolProvider:
    """CapabilityProvider impl for K1-native family tools."""

    PROVIDER_ID = "k1_native_tools"

    def __init__(
        self,
        registry: ToolRegistryReader,
        session_reader: ISessionStateReader,
    ) -> None:
        self._registry = registry
        self._session_reader = session_reader

    async def execute(self, request: CapabilityRequest) -> CapabilityResult:
        # capability_name is "{adapter_id}.{action}"
        adapter_id, _, action = request.capability_name.partition(".")
        svc = self._registry.get(adapter_id)
        if svc is None:
            return CapabilityResult.error(f"unknown adapter: {adapter_id}")

        # Resolve actor from session state (single authoritative point)
        ctrl = await self._session_reader.read_section(request.session_id, "control") or {}
        ctx = _build_write_context(ctrl, request)
        result = await svc.dispatch(action, dict(request.params), ctx)
        return (
            CapabilityResult.ok(result.get("result") or {})
            if result.get("success")
            else CapabilityResult.error(result.get("error", "tool failed"))
        )
```

#### `ToolRegistry` — owns service lifecycle and Fabric registration

File: `k1/tools/family/registry.py` (NEW — replaces `scripts/pseudo_k0/tools/registry.py`)

```python
"""k1.tools.family.registry — discovery + Fabric wiring.

NO ConnectorHost dependency. Apps live entirely in K1.
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Iterable, Optional

from k1.fabric.fabric import CapabilityFabric
from k1.fabric.manifest_translator import register_with_fabric
from k1.tools.family.base import BaseToolService
from k1.tools.family.events import EventEmitter
from k1.tools.family.idem import IdempotencyStore
from k1.tools.family.policy import VisibilityPolicy, default_policy

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Owns the lifecycle of all BaseToolService instances + Fabric registration."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        emitter: EventEmitter,
        fabric: Optional[CapabilityFabric] = None,
        policy: VisibilityPolicy | None = None,
    ) -> None:
        self._conn = conn
        self._emitter = emitter
        self._fabric = fabric
        self._policy = policy or default_policy()
        self._idem = IdempotencyStore(conn)
        self._services: dict[str, BaseToolService] = {}

    def register_class(self, service_cls: type[BaseToolService]) -> BaseToolService:
        svc = service_cls(self._conn, self._emitter, self._policy, self._idem)
        adapter_id = svc.DEFINITION.adapter_id
        if adapter_id in self._services:
            raise ValueError(f"tool already registered: {adapter_id}")
        self._services[adapter_id] = svc
        if self._fabric is not None:
            # E3 enhancement: every action becomes one CapabilityContract
            register_with_fabric(svc.DEFINITION, self._fabric)
        logger.info("ToolRegistry: registered %s", adapter_id)
        return svc

    def register_all(self, classes: Iterable[type[BaseToolService]]) -> None:
        for cls in classes:
            self.register_class(cls)

    def get(self, adapter_id: str) -> BaseToolService | None:
        return self._services.get(adapter_id)

    @property
    def services(self) -> dict[str, BaseToolService]:
        return dict(self._services)
```

**`_ServiceHandler` is DELETED.** It existed only to bridge `ConnectorHost` → `BaseToolService`.
Under R-2, dispatch goes Fabric → `NativeToolProvider` → `BaseToolService` directly.

---

### E15.0.8 — `ManifestGenerator` (one declaration → three manifests)

File: `scripts/pseudo_k0/tools/manifest.py`

```python
"""scripts.pseudo_k0.tools.manifest — generates UI + LLM + OpenAPI manifests.

One ToolDefinition produces:
    - UI manifest (per role) — for the generic K1 renderer
    - LLM tool spec — for Concierge planner / Fabric capability registry
    - OpenAPI fragment — for /k1/tools/* REST docs
"""
from __future__ import annotations

from typing import Any, Literal

from scripts.pseudo_k0.tools.definition import ActionSpec, ToolDefinition, FieldSpec

Role = Literal["parent", "child", "guardian", "elder"]


def _field_to_ui(f: FieldSpec) -> dict:
    out: dict = {"name": f.name, "type": f.type, "required": f.required}
    if f.label: out["label"] = f.label
    if f.default is not None: out["default"] = f.default
    if f.options: out["options"] = f.options
    if f.show_when: out["show_when"] = f.show_when
    if f.description: out["description"] = f.description
    if f.examples: out["examples"] = f.examples
    if f.ref_adapter: out["ref_adapter"] = f.ref_adapter
    return out


def _action_visible_to_role(spec: ActionSpec, role: Role) -> bool:
    if spec.min_role is None:
        return True
    order = {"system": 4, "parent": 3, "guardian": 2, "elder": 1, "child": 0}
    return order.get(role, -1) >= order.get(spec.min_role, 0)


def ui_manifest(defn: ToolDefinition, role: Role) -> dict[str, Any]:
    """Role-filtered UI manifest for the generic K1 renderer."""
    actions = {}
    for spec in defn.actions:
        if not _action_visible_to_role(spec, role):
            continue
        actions[spec.name] = {
            "label": spec.label,
            "kind": spec.kind,
            "primary": spec.primary,
            "context": spec.context,
            "form": {"fields": [_field_to_ui(f) for f in spec.form]},
            "output_schema": spec.output_schema or {},
            "idempotent": spec.idempotent,
        }
    return {
        "adapter_id": defn.adapter_id,
        "version": defn.version,
        "title": defn.title,
        "icon": defn.icon,
        "category": defn.category,
        "description": defn.description,
        "role": role,
        "entity_type": defn.entity_type,
        "actions": actions,
        "views": defn.views,
        "filters": defn.filters,
        "can_reference": defn.can_reference,
        "feature_flags": defn.feature_flags,
    }


def llm_tool_specs(defn: ToolDefinition) -> list[dict[str, Any]]:
    """Per-action LLM tool specs. Concierge LLM sees these as tool definitions.

    Includes the LLMHints (use_when, examples, preconditions, side_effects) so
    the planner can reason about WHICH tool to pick.
    """
    specs = []
    for spec in defn.actions:
        properties = {}
        required = []
        for f in spec.form:
            properties[f.name] = _field_to_json_schema(f)
            if f.required:
                required.append(f.name)
        specs.append({
            "name": f"{defn.adapter_id}.{spec.name}",
            "description": (spec.label + ". " + (spec.llm.use_when[0] if spec.llm.use_when else "")).strip(),
            "kind": spec.kind,
            "min_role": spec.min_role,
            "min_band": spec.min_band,
            "idempotent": spec.idempotent,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
            "output_schema": spec.output_schema or {},
            "llm_hints": spec.llm.model_dump(),
            "category": defn.category,
        })
    return specs


def _field_to_json_schema(f: FieldSpec) -> dict[str, Any]:
    py = {
        "string": "string", "text": "string", "int": "integer", "float": "number",
        "bool": "boolean", "datetime": "string", "date": "string", "duration": "string",
        "enum": "string", "enum_multi": "array", "member": "string", "member_multi": "array",
        "entity_ref": "string", "money": "number", "location": "object", "json": "object",
    }.get(f.type, "string")
    out: dict[str, Any] = {"type": py}
    if f.description: out["description"] = f.description
    if f.options: out["enum"] = f.options
    if f.type in ("enum_multi", "member_multi"): out["items"] = {"type": "string"}
    if f.examples: out["examples"] = f.examples
    return out


def openapi_paths(defn: ToolDefinition) -> dict[str, Any]:
    """OpenAPI 3.1 path fragments for /k1/tools/{adapter}/{action} routes."""
    paths = {}
    for spec in defn.actions:
        path = f"/k1/tools/{defn.adapter_id}/{spec.name}"
        method = "get" if spec.kind == "read" else "post"
        paths[path] = {
            method: {
                "summary": spec.label,
                "tags": [defn.adapter_id],
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    f.name: _field_to_json_schema(f) for f in spec.form
                                },
                            }
                        }
                    }
                } if method == "post" else None,
                "responses": {
                    "200": {"description": "OK"},
                    "403": {"description": "role/band gate denied"},
                    "404": {"description": "entity not found"},
                },
            }
        }
    return paths
```

---

### E15.0.9 — Generic REST router factory

One factory builds the `/k1/tools/{adapter_id}/{action}` REST routes for any `BaseToolService`.
No per-tool boilerplate.

File: `scripts/pseudo_k0/tools/routes.py`

```python
"""scripts.pseudo_k0.tools.routes — generic REST router factory.

Mounts /k1/tools/{adapter_id}/{action} → service.dispatch(action, params, ctx)
plus /k1/tools/{adapter_id}/manifest?role=... for UI.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request

from scripts.pseudo_k0.tools.base import BaseToolService, WriteContext
from scripts.pseudo_k0.tools.manifest import ui_manifest, llm_tool_specs


def build_router(service: BaseToolService) -> APIRouter:
    defn = service.DEFINITION
    router = APIRouter(prefix=f"/k1/tools/{defn.adapter_id}", tags=[defn.adapter_id])

    @router.get("/manifest")
    async def manifest(role: str = Query("parent")) -> dict[str, Any]:
        return ui_manifest(defn, role)  # type: ignore[arg-type]

    @router.get("/llm_specs")
    async def llm_specs() -> list[dict[str, Any]]:
        return llm_tool_specs(defn)

    # Per-action route
    for spec in defn.actions:
        _attach_action(router, service, spec)

    return router


def _attach_action(router: APIRouter, service: BaseToolService, spec) -> None:
    method = "GET" if spec.kind == "read" else "POST"

    if method == "POST":
        async def endpoint(
            payload: dict[str, Any],
            x_actor_member_id: str = Header(...),
            x_actor_role: str = Header("parent"),
            x_space_id: str = Header(...),
            x_trace_id: str | None = Header(None),
            x_idem_key: str | None = Header(None),
        ) -> dict[str, Any]:
            ctx = WriteContext(
                actor_member_id=x_actor_member_id,
                actor_role=x_actor_role,  # type: ignore[arg-type]
                space_id=x_space_id,
                trace_id=x_trace_id,
                face="ui",
                idem_key=x_idem_key,
            )
            result = await service.dispatch(spec.name, payload, ctx)
            if not result.get("success"):
                raise HTTPException(status_code=400, detail=result.get("error"))
            return result
    else:
        async def endpoint(
            request: Request,
            x_actor_member_id: str = Header(...),
            x_actor_role: str = Header("parent"),
            x_space_id: str = Header(...),
            x_trace_id: str | None = Header(None),
        ) -> dict[str, Any]:
            ctx = WriteContext(
                actor_member_id=x_actor_member_id,
                actor_role=x_actor_role,  # type: ignore[arg-type]
                space_id=x_space_id,
                trace_id=x_trace_id,
                face="ui",
            )
            params = dict(request.query_params)
            result = await service.dispatch(spec.name, params, ctx)
            if not result.get("success"):
                raise HTTPException(status_code=400, detail=result.get("error"))
            return result

    router.add_api_route(
        f"/{spec.name}",
        endpoint,
        methods=[method],
        name=f"{service.DEFINITION.adapter_id}.{spec.name}",
        summary=spec.label,
    )
```

---

### E15.0.10 — Wire into K1 kernel startup (REVISED per R-2)

> **This subsection is REVISED.** Original text mounted tool routers + SSE on
> pseudo-K0's `create_app()`. Under R-1/R-2, apps live in K1; pseudo-K0 keeps only
> M14 surfaces. Wire instead at K1 boot.

#### Step A — K1 family store (hot SQLite)

Create `k1/tools/family/storage.py`:

```python
"""k1.tools.family.storage — K1 hot SQLite store for native apps.

Lives at data/k1_family.db. Separate from pseudo-K0's WAL. K1-resident, never
depends on K0_ENDPOINT being set.
"""
class K1FamilyStore:
    def __init__(self, db_path: str = "data/k1_family.db") -> None: ...
    @property
    def conn(self) -> sqlite3.Connection: ...
    def close(self) -> None: ...
```

#### Step B — Wire at K1 startup

Add to `KernelService._startup_tier2()` (or the tier where Fabric is constructed), after
the Fabric instance exists:

```python
# M15: K1-native family apps foundation
from k1.tools.family.storage import K1FamilyStore
from k1.tools.family.events import EventEmitter
from k1.tools.family.registry import ToolRegistry
from k1.tools.family.calendar.service import CalendarToolService
from k1.tools.family.tasks.service import TasksToolService
from k1.tools.family.reminders.service import RemindersToolService
from k1.tools.family.chores.service import ChoresToolService
from k1.tools.family.shopping.service import ShoppingToolService
from k1.tools.family.family_settings.service import FamilySettingsService
from k1.fabric.providers.native_tool_provider import NativeToolProvider

DEFAULT_TOOL_CLASSES = [
    CalendarToolService, TasksToolService, RemindersToolService,
    ChoresToolService, ShoppingToolService, FamilySettingsService,
]

self._family_store = K1FamilyStore("data/k1_family.db")
emitter = EventEmitter(
    sse_publisher=self._sse_publisher,           # K1's existing SSE publisher
    bridge_outbox=self._bridge,                  # M14 bridge for cold-sync (best-effort)
)
self._tool_registry = ToolRegistry(
    conn=self._family_store.conn,
    emitter=emitter,
    fabric=self._fabric,                         # registers CapabilityContracts at boot
)
self._tool_registry.register_all(DEFAULT_TOOL_CLASSES)

# Register the in-process provider so Fabric can dispatch LOCAL capabilities
self._fabric.providers.register(
    "k1_native_tools",
    NativeToolProvider(self._tool_registry, self._session_state_reader),
)
```

#### Step C — Mount REST routes on K1's web app (ui/web)

In `ui/web/app.py` (or wherever the FastAPI app is built), after `kernel_service` is
available:

```python
from k1.tools.family.routes import build_router

for svc in kernel_service.tool_registry.services.values():
    app.include_router(build_router(svc), prefix="/k1/tools")
```

REST routes mount on **K1's web app**, not pseudo-K0. UI face hits
`POST /k1/tools/calendar/create_event` and that goes K1-local through
`BaseToolService.dispatch()`.

#### Step D — Cold-sync to K0 (optional)

`EventEmitter` enqueues a sync envelope on every successful write. If
`KernelConfig.k0_endpoint` is set, the existing M14 bridge outbox forwards them via
`command.submit`. If unset, envelopes accumulate in the outbox (or are dropped per
policy) — apps still work fully. **No app behavior depends on K0 reachability.**

#### Pseudo-K0 server is UNCHANGED

`scripts/pseudo_k0/server.py` keeps only its M14 surfaces. No tool routers, no
EventEmitter, no ToolRegistry. The `/k0/connector.execute` slot stays for real-K0
compatibility but receives no M15 traffic.

---

### E15.1 — Calendar App (the flagship; pattern template)

File: `scripts/pseudo_k0/tools/calendar/schema.py`

```python
"""scripts.pseudo_k0.tools.calendar.schema — Pydantic entity types."""
from __future__ import annotations

from typing import Literal
from pydantic import Field

from scripts.pseudo_k0.tools.base import BaseEntity


class CalendarEvent(BaseEntity):
    title: str
    start: str               # ISO 8601 datetime
    end: str
    location: str = ""
    notes: str = ""
    attendees: list[str] = Field(default_factory=list)   # member_ids
    rrule: str | None = None                             # iCal RRULE
    response: Literal["yes", "no", "maybe", "tentative"] | None = None


class ExternalFeed(BaseEntity):
    member_id: str
    source: Literal["google", "outlook", "teams", "classroom", "apple"]
    account: str
    sync_token: str | None = None
    enabled: bool = False                                # disabled in M15
```

File: `scripts/pseudo_k0/tools/calendar/tables.sql`

```sql
CREATE TABLE IF NOT EXISTS calendar_events (
    id TEXT PRIMARY KEY,
    space_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_by TEXT NOT NULL DEFAULT '',
    updated_at INTEGER NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    source TEXT NOT NULL DEFAULT 'native',
    source_ref TEXT,
    source_account TEXT,
    source_label TEXT,
    visibility TEXT,
    visible_to TEXT NOT NULL DEFAULT '[]',
    tags TEXT NOT NULL DEFAULT '[]',
    metadata TEXT NOT NULL DEFAULT '{}',
    linked_to TEXT NOT NULL DEFAULT '[]',
    -- entity-specific
    title TEXT NOT NULL,
    start TEXT NOT NULL,
    end TEXT NOT NULL,
    location TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    attendees TEXT NOT NULL DEFAULT '[]',
    rrule TEXT,
    response TEXT,
    deleted_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_cal_space  ON calendar_events(space_id);
CREATE INDEX IF NOT EXISTS idx_cal_start  ON calendar_events(start);
CREATE INDEX IF NOT EXISTS idx_cal_source ON calendar_events(source);

CREATE TABLE IF NOT EXISTS calendar_feeds (
    id TEXT PRIMARY KEY,
    space_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_by TEXT NOT NULL DEFAULT '',
    updated_at INTEGER NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    member_id TEXT NOT NULL,
    source TEXT NOT NULL,
    account TEXT NOT NULL,
    sync_token TEXT,
    enabled INTEGER NOT NULL DEFAULT 0,
    metadata TEXT NOT NULL DEFAULT '{}'
);
```

File: `scripts/pseudo_k0/tools/calendar/service.py`

```python
"""scripts.pseudo_k0.tools.calendar.service — CalendarToolService."""
from __future__ import annotations

import json
import sqlite3
from typing import Any, ClassVar

from scripts.pseudo_k0.tools.base import BaseEntity, BaseToolService, WriteContext
from scripts.pseudo_k0.tools.calendar.schema import CalendarEvent, ExternalFeed
from scripts.pseudo_k0.tools.calendar.definition import CALENDAR_DEFINITION

with open(__file__.replace("service.py", "tables.sql")) as _f:
    _DDL = _f.read()


class CalendarToolService(BaseToolService):
    DEFINITION: ClassVar = CALENDAR_DEFINITION
    ENTITY_CLASSES = {"CalendarEvent": CalendarEvent, "ExternalFeed": ExternalFeed}

    # ---------- Actions ----------

    async def create_event(self, params: dict, ctx: WriteContext) -> dict:
        ev = CalendarEvent(
            space_id=ctx.space_id,
            tenant_id=ctx.tenant_id,
            created_by=ctx.actor_member_id,
            **params,
        )
        await self.write_entity("create_event", ev, ctx)
        return ev.model_dump(mode="json")

    async def update_event(self, params: dict, ctx: WriteContext) -> dict:
        event_id = params.pop("event_id")
        expected_version = params.pop("expected_version", None)
        rows = self._select({"id": event_id}, ctx)
        if not rows:
            raise ValueError(f"event not found: {event_id}")
        ev = CalendarEvent(**self._row_to_entity_dict(rows[0]))
        if expected_version is not None and ev.version != expected_version:
            raise ValueError(f"stale version: have {ev.version}, expected {expected_version}")
        for k, v in params.items():
            if hasattr(ev, k):
                setattr(ev, k, v)
        ev.bump(ctx.actor_member_id)
        await self.write_entity("update_event", ev, ctx)
        return ev.model_dump(mode="json")

    async def delete_event(self, params: dict, ctx: WriteContext) -> dict:
        event_id = params["event_id"]
        rows = self._select({"id": event_id}, ctx)
        if not rows:
            raise ValueError(f"event not found: {event_id}")
        ev = CalendarEvent(**self._row_to_entity_dict(rows[0]))
        await self.delete_entity(event_id, ctx, ev)
        return {"deleted": event_id}

    async def list_events(self, params: dict, ctx: WriteContext) -> dict:
        query = {
            "start_after": params.get("start"),
            "start_before": params.get("end"),
            "member_filter": params.get("member_filter"),
            "source_filter": params.get("source_filter"),
        }
        rows = await self.read_entities(query, ctx)
        return {"events": rows, "count": len(rows)}

    async def get_event(self, params: dict, ctx: WriteContext) -> dict:
        rows = await self.read_entities({"id": params["event_id"]}, ctx)
        if not rows:
            raise ValueError(f"event not found: {params['event_id']}")
        return rows[0]

    async def set_visibility(self, params: dict, ctx: WriteContext) -> dict:
        rows = self._select({"id": params["event_id"]}, ctx)
        if not rows:
            raise ValueError("event not found")
        ev = CalendarEvent(**self._row_to_entity_dict(rows[0]))
        ev.visibility = params["visibility"]
        ev.visible_to = params.get("visible_to", [])
        ev.bump(ctx.actor_member_id)
        await self.write_entity("set_visibility", ev, ctx)
        return ev.model_dump(mode="json")

    async def connect_feed(self, params: dict, ctx: WriteContext) -> dict:
        feed = ExternalFeed(
            space_id=ctx.space_id,
            tenant_id=ctx.tenant_id,
            created_by=ctx.actor_member_id,
            member_id=params.get("member_id", ctx.actor_member_id),
            source=params["source"],
            account=params["account"],
            enabled=False,                       # disabled in M15
        )
        await self.write_entity("connect_feed", feed, ctx)
        return feed.model_dump(mode="json")

    async def list_feeds(self, params: dict, ctx: WriteContext) -> dict:
        rows = await self.read_entities({"entity_kind": "feed"}, ctx)
        return {"feeds": rows, "count": len(rows)}

    # ---------- Subclass hooks ----------

    def _upsert(self, entity: BaseEntity, ctx: WriteContext) -> None:
        if isinstance(entity, CalendarEvent):
            self._upsert_event(entity)
        elif isinstance(entity, ExternalFeed):
            self._upsert_feed(entity)
        else:
            raise TypeError(f"unknown entity: {type(entity)}")

    def _upsert_event(self, e: CalendarEvent) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO calendar_events
               (id, space_id, tenant_id, created_by, created_at, updated_by, updated_at,
                version, source, source_ref, source_account, source_label,
                visibility, visible_to, tags, metadata, linked_to,
                title, start, end, location, notes, attendees, rrule, response, deleted_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                e.id, e.space_id, e.tenant_id, e.created_by, e.created_at,
                e.updated_by, e.updated_at, e.version, e.source, e.source_ref,
                e.source_account, e.source_label, e.visibility,
                json.dumps(e.visible_to), json.dumps(e.tags),
                json.dumps(e.metadata), json.dumps(e.linked_to),
                e.title, e.start, e.end, e.location, e.notes,
                json.dumps(e.attendees), e.rrule, e.response, None,
            ),
        )
        self.conn.commit()

    def _upsert_feed(self, f: ExternalFeed) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO calendar_feeds
               (id, space_id, tenant_id, created_by, created_at, updated_by, updated_at,
                version, member_id, source, account, sync_token, enabled, metadata)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                f.id, f.space_id, f.tenant_id, f.created_by, f.created_at,
                f.updated_by, f.updated_at, f.version, f.member_id,
                f.source, f.account, f.sync_token, int(f.enabled),
                json.dumps(f.metadata),
            ),
        )
        self.conn.commit()

    def _delete(self, entity_id: str, ctx: WriteContext) -> None:
        import time as _t
        self.conn.execute(
            "UPDATE calendar_events SET deleted_at=? WHERE id=? AND space_id=?",
            (int(_t.time() * 1000), entity_id, ctx.space_id),
        )
        self.conn.commit()

    def _select(self, query: dict, ctx: WriteContext) -> list[dict]:
        kind = query.get("entity_kind")
        if kind == "feed":
            cur = self.conn.execute(
                "SELECT * FROM calendar_feeds WHERE space_id=?",
                (ctx.space_id,),
            )
        elif "id" in query:
            cur = self.conn.execute(
                "SELECT * FROM calendar_events WHERE id=? AND space_id=? AND deleted_at IS NULL",
                (query["id"], ctx.space_id),
            )
        else:
            sql = "SELECT * FROM calendar_events WHERE space_id=? AND deleted_at IS NULL"
            args: list[Any] = [ctx.space_id]
            if query.get("start_after"):
                sql += " AND end >= ?"; args.append(query["start_after"])
            if query.get("start_before"):
                sql += " AND start <= ?"; args.append(query["start_before"])
            sql += " ORDER BY start ASC LIMIT 500"
            cur = self.conn.execute(sql, args)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    @staticmethod
    def _row_to_entity_dict(row: dict) -> dict:
        d = dict(row)
        for k in ("visible_to", "tags", "metadata", "linked_to", "attendees"):
            if isinstance(d.get(k), str):
                d[k] = json.loads(d[k])
        return d
```

File: `scripts/pseudo_k0/tools/calendar/definition.py`

```python
"""scripts.pseudo_k0.tools.calendar.definition — Calendar declarative spec."""
from scripts.pseudo_k0.tools.definition import (
    ActionSpec, FieldSpec, LLMHints, SSESpec, ToolDefinition,
)

# Read tables.sql at import time
import os
_HERE = os.path.dirname(__file__)
with open(os.path.join(_HERE, "tables.sql")) as _f:
    _DDL = _f.read()


CALENDAR_DEFINITION = ToolDefinition(
    adapter_id="calendar",
    title="Family Calendar",
    icon="calendar",
    category="coordination",
    description="Family-shared calendar with per-event visibility, member attendance, "
                "external feed imports, and cross-family live sync.",
    entity_type="CalendarEvent",
    tables_sql=_DDL,
    can_reference=["tasks", "reminders", "shopping"],
    actions=[
        ActionSpec(
            name="create_event",
            label="New event",
            kind="write",
            primary=True,
            min_band="AMBER",
            idempotent=True,
            form=[
                FieldSpec(name="title", type="string", required=True,
                          description="Short event name",
                          examples=["Riley soccer", "Dentist", "Family dinner"]),
                FieldSpec(name="start", type="datetime", required=True),
                FieldSpec(name="end", type="datetime", required=True),
                FieldSpec(name="attendees", type="member_multi",
                          description="member_ids of family members attending"),
                FieldSpec(name="location", type="string"),
                FieldSpec(name="notes", type="text"),
                FieldSpec(name="visibility", type="enum",
                          options=["family", "adults", "named", "private"],
                          default="family",
                          description="Who can see this event"),
                FieldSpec(name="visible_to", type="member_multi",
                          show_when="visibility in ['named','private']"),
            ],
            llm=LLMHints(
                use_when=[
                    "user wants to add an event, appointment, or meeting to the family calendar",
                    "user mentions a scheduled activity with a date and time",
                    "user wants to remember something happening at a specific time",
                ],
                do_not_use_when=[
                    "user wants a recurring chore (use chores.create_chore)",
                    "user wants a to-do without a fixed time (use tasks.create_task)",
                    "user wants a time-or-location reminder (use reminders.create_reminder)",
                ],
                examples=[
                    {"title": "Riley soccer game", "start": "2026-05-15T10:00",
                     "end": "2026-05-15T11:30", "attendees": ["riley", "alex"],
                     "location": "Field 3", "visibility": "family"},
                    {"title": "Dentist for Jordan", "start": "2026-05-20T14:00",
                     "end": "2026-05-20T15:00", "attendees": ["jordan"],
                     "visibility": "adults"},
                ],
                preconditions=[
                    "start < end",
                    "all attendee member_ids exist in the family profile",
                ],
                side_effects=[
                    "WAL entry on calendar.create_event.v1",
                    "SSE tool_state.changed.v1 fan-out to all family devices",
                    "may auto-create related reminders if user opted in",
                ],
                related_actions=["calendar.update_event", "calendar.list_events"],
                typical_followups=["calendar.list_events", "reminders.create_reminder"],
                read_before_write="calendar.list_events for the same day to avoid double-booking",
            ),
        ),
        ActionSpec(
            name="update_event", label="Update event", kind="write", min_band="AMBER",
            form=[
                FieldSpec(name="event_id", type="entity_ref", ref_adapter="calendar", required=True),
                FieldSpec(name="expected_version", type="int",
                          description="Pass the version you read to detect stale overwrites"),
                FieldSpec(name="title", type="string"),
                FieldSpec(name="start", type="datetime"),
                FieldSpec(name="end", type="datetime"),
                FieldSpec(name="location", type="string"),
                FieldSpec(name="notes", type="text"),
                FieldSpec(name="attendees", type="member_multi"),
            ],
            llm=LLMHints(
                use_when=["user wants to reschedule, edit, or change details of an event"],
                read_before_write="calendar.get_event to fetch current version",
                preconditions=["event must exist", "expected_version must match current"],
            ),
        ),
        ActionSpec(
            name="delete_event", label="Delete event", kind="delete", min_band="AMBER",
            form=[FieldSpec(name="event_id", type="entity_ref", ref_adapter="calendar", required=True)],
            llm=LLMHints(use_when=["user wants to cancel or remove an event"]),
        ),
        ActionSpec(
            name="list_events", label="List events", kind="read", min_band="GREEN",
            form=[
                FieldSpec(name="start", type="datetime", description="Filter start window"),
                FieldSpec(name="end", type="datetime"),
                FieldSpec(name="member_filter", type="member_multi"),
                FieldSpec(name="source_filter", type="enum_multi",
                          options=["native", "google", "outlook", "classroom", "apple"]),
            ],
            llm=LLMHints(
                use_when=[
                    "user asks 'what's on the calendar', 'what do we have this week'",
                    "planner wants to check existing events before scheduling",
                ],
                examples=[{"start": "2026-05-15T00:00", "end": "2026-05-15T23:59"}],
                typical_followups=["calendar.create_event"],
            ),
        ),
        ActionSpec(
            name="get_event", label="Get event", kind="read", min_band="GREEN",
            form=[FieldSpec(name="event_id", type="entity_ref", ref_adapter="calendar", required=True)],
        ),
        ActionSpec(
            name="set_visibility", label="Change visibility", kind="write",
            min_role="parent", min_band="AMBER", context="per_event_gear_icon",
            form=[
                FieldSpec(name="event_id", type="entity_ref", ref_adapter="calendar", required=True),
                FieldSpec(name="visibility", type="enum",
                          options=["family", "adults", "named", "private"], required=True),
                FieldSpec(name="visible_to", type="member_multi",
                          show_when="visibility in ['named','private']"),
            ],
            llm=LLMHints(
                use_when=["parent wants to hide or restrict who sees an event"],
                do_not_use_when=["caller is a child (will fail role gate)"],
            ),
        ),
        ActionSpec(
            name="connect_feed", label="Connect external calendar", kind="write",
            min_role="parent", min_band="AMBER",
            form=[
                FieldSpec(name="source", type="enum",
                          options=["google", "outlook", "teams", "classroom", "apple"],
                          required=True),
                FieldSpec(name="account", type="string", required=True),
                FieldSpec(name="member_id", type="member"),
            ],
            llm=LLMHints(
                use_when=["user wants to import Google/Outlook/Classroom events"],
                side_effects=["feed bound but DISABLED in M15 (real sync in M17)"],
            ),
        ),
        ActionSpec(
            name="list_feeds", label="List feeds", kind="read", min_band="GREEN",
            form=[FieldSpec(name="member_id", type="member")],
        ),
    ],
    views={
        "month": {"layout": "calendar_month"},
        "week":  {"layout": "calendar_week"},
        "day":   {"layout": "calendar_day"},
        "list":  {"layout": "event_list"},
    },
    filters={
        "by_member":   {"type": "member_multi"},
        "by_source":   {"type": "enum_multi",
                        "options": ["native", "google", "outlook", "classroom", "apple"]},
        "by_visibility": {"type": "enum_multi",
                          "options": ["family", "adults", "named", "private"]},
    },
    sse=SSESpec(on_write_topic="tool_state.changed.v1"),
)
```

---

### E15.2 — Tasks App (~250 LOC; same shape)

The remaining four apps follow the exact same shape as Calendar. Below is the per-app spec
in condensed form (full implementation matches Calendar's pattern: schema.py + tables.sql +
service.py + definition.py).

**Entities** (`schema.py`):

```python
class TaskList(BaseEntity):
    name: str
    color: str | None = None

class TaskItem(BaseEntity):
    title: str
    list_id: str | None = None
    assigned_to: str | None = None         # member_id
    due_at: str | None = None              # ISO datetime
    priority: Literal["low", "medium", "high"] = "medium"
    status: Literal["open", "in_progress", "done", "cancelled"] = "open"
    completed_at: str | None = None
    linked_event_id: str | None = None     # cross-tool link to calendar
```

**Tables**: `task_items`, `task_lists` (identical column shape to `calendar_events` for the
universal `BaseEntity` columns; entity-specific columns appended).

**Actions** (`definition.py`):

- `create_task` (write, idempotent, AMBER)
- `update_task` (write, AMBER)
- `complete_task` (write, AMBER, marks done + sets completed_at)
- `reassign_task` (write, AMBER; if new assignee ≠ self, min_role=parent)
- `delete_task` (delete, AMBER)
- `list_tasks` (read, GREEN; filters: assigned_to, status, due_before)
- `get_task` (read, GREEN)

**LLM Hints** that distinguish tasks from chores/reminders/calendar:

```python
use_when=[
    "user wants a one-off to-do item",
    "user wants something done by a specific deadline (not at a specific time)",
]
do_not_use_when=[
    "user wants a recurring family chore → chores.create_chore",
    "user wants a time-triggered reminder → reminders.create_reminder",
    "user wants a calendar event with start+end time → calendar.create_event",
]
```

Touch points: NEW `scripts/pseudo_k0/tools/tasks/{__init__.py, schema.py, tables.sql, service.py, definition.py}`

---

### E15.3 — Reminders App (~250 LOC)

**Entities**:

```python
class ReminderTrigger(BaseModel):
    kind: Literal["time", "location_enter", "location_leave", "event_offset"]
    fire_at: str | None = None                    # for kind="time"
    location: dict | None = None                  # {"lat","lon","radius_m"} for location_*
    event_id: str | None = None                   # for kind="event_offset"
    offset_minutes: int | None = None             # for kind="event_offset"

class Reminder(BaseEntity):
    title: str
    recipient: str                                # member_id (may differ from created_by)
    trigger: ReminderTrigger
    message: str = ""
    status: Literal["scheduled", "fired", "dismissed", "snoozed"] = "scheduled"
    snoozed_until: str | None = None
    fired_at: str | None = None
```

**Actions**: `create_reminder`, `update_reminder`, `snooze_reminder`, `dismiss_reminder`,
`list_reminders`, `get_reminder`.

**Permission rule that lives inside `create_reminder` handler**:

```python
async def create_reminder(self, params, ctx):
    recipient = params["recipient"]
    if recipient != ctx.actor_member_id and ctx.actor_role not in ("parent", "guardian", "system"):
        raise PermissionError("only parents may set reminders for other members")
    # ... persist
```

**LLM Hints** — these make the killer feature ("remind dad to grab milk") work well:

```python
use_when=[
    "user wants to remind themselves or another family member at a specific time",
    "user wants a location-triggered alert (e.g. 'when dad gets home')",
    "user says 'remind X to...' — X is the recipient",
]
examples=[
    {"title": "Pick up milk", "recipient": "alex",
     "trigger": {"kind": "location_leave", "location": {"name": "work"}}},
    {"title": "Take medication", "recipient": "nana",
     "trigger": {"kind": "time", "fire_at": "2026-05-12T20:00"}},
]
```

Touch points: NEW `scripts/pseudo_k0/tools/reminders/{__init__.py, schema.py, tables.sql, service.py, definition.py}`

---

### E15.4 — Chores App (~300 LOC; native-only, no external import)

**Entities**:

```python
class Chore(BaseEntity):
    title: str
    recurrence: str | None = None                 # RRULE — e.g. "FREQ=WEEKLY;BYDAY=SU"
    default_assignee: str | None = None
    reward_amount: float | None = None
    reward_currency: str = "USD"
    requires_verification: bool = False           # parent must confirm

class ChoreAssignment(BaseEntity):
    chore_id: str
    assigned_to: str
    due_at: str | None = None
    status: Literal["pending", "in_progress", "completed", "verified", "skipped"] = "pending"
    completed_at: str | None = None
    completed_by: str | None = None
    verified_at: str | None = None
    verified_by: str | None = None
    evidence_url: str | None = None
    reward_unlocked: bool = False

class RewardLedger(BaseEntity):
    member_id: str
    delta: float                                  # + earn / - spend
    reason: str
    chore_assignment_id: str | None = None
```

**Actions**: `create_chore` (parent), `assign_chore` (parent), `complete_chore` (any),
`verify_chore` (parent), `redeem_reward` (parent unless `kids_can_redeem` flag),
`list_chores`, `get_reward_balance`, `list_ledger`.

**LLM hints** that reflect family-coordination value:

```python
use_when=[
    "user wants to add a recurring family chore",
    "user wants to track who did what household task",
    "user wants to give a kid a chore that earns allowance",
]
side_effects=[
    "create_chore generates ChoreAssignment instances per recurrence",
    "complete_chore + verify_chore → RewardLedger credit if reward set",
]
```

Touch points: NEW `scripts/pseudo_k0/tools/chores/{__init__.py, schema.py, tables.sql, service.py, definition.py}`

---

### E15.5 — Shopping List App (~250 LOC)

**Entities**:

```python
class ShoppingList(BaseEntity):
    name: str                                     # "Groceries" | "Costco run"
    color: str | None = None

class ShoppingItem(BaseEntity):
    list_id: str
    name: str
    qty: float = 1
    unit: str = ""                                # "lb", "ea", "gal", ""
    category: str = ""                            # "produce", "dairy", ...
    requested_by: str
    checked_off: bool = False
    checked_by: str | None = None
    checked_at: str | None = None
    linked_meal_id: str | None = None             # cross-tool link
```

**Actions**: `create_list`, `add_item` (idempotent on idem_key), `update_item`,
`check_off_item`, `uncheck_item`, `delete_item`, `list_items`, `list_lists`,
`suggest_from_meals` (compute kind — uses LLM internally via `model_hub`).

**LLM hints**:

```python
use_when=[
    "user wants to add an item to the shopping list",
    "user wants to see the shopping list",
    "user mentions needing to buy something",
]
typical_followups=["shopping.list_items"]
read_before_write="shopping.list_items to check for duplicates"
```

Touch points: NEW `scripts/pseudo_k0/tools/shopping/{__init__.py, schema.py, tables.sql, service.py, definition.py}`

---

### E15.6 — Family Settings App (the visibility policy editor)

The parent-only adapter that backs the Family Settings UI.

**Entities**:

```python
class VisibilityPolicyDoc(BaseEntity):
    # singleton per space_id — only one VisibilityPolicyDoc per family
    rules: dict[str, str]                         # e.g. {"google_work": "adults"}
    sensitive_keywords: list[str]
    kid_capabilities: dict[str, bool]             # see whiteboard §6.3

class FamilyFeatureFlag(BaseEntity):
    flag_name: str
    enabled: bool
```

**Actions** (all `min_role="parent"`):

- `get_visibility_policy` (read, GREEN)
- `update_visibility_policy` (write, AMBER)
- `list_feature_flags` (read, GREEN)
- `set_feature_flag` (write, AMBER)

On `update_visibility_policy` the service rebuilds the live `VisibilityPolicy` rules (uses
the registry to invalidate caches; the registry holds a single `VisibilityPolicy` instance
shared by all tool services).

Touch points: NEW `scripts/pseudo_k0/tools/family_settings/{__init__.py, schema.py, tables.sql, service.py, definition.py}`

---

### E15.7 — K1-side Client + Manifest Cache

File: `k1/tools/family/client.py`

```python
"""k1.tools.family.client — FamilyToolClient: thin REST wrapper for UI shell."""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class FamilyToolClient:
    """One client serves all family apps. UI shell uses this directly."""

    def __init__(self, base_url: str, member_id: str, role: str, space_id: str) -> None:
        self._base = base_url.rstrip("/")
        self._member = member_id
        self._role = role
        self._space = space_id
        self._http = httpx.AsyncClient(timeout=10.0)

    async def manifest(self, adapter_id: str) -> dict[str, Any]:
        r = await self._http.get(
            f"{self._base}/k1/tools/{adapter_id}/manifest",
            params={"role": self._role},
        )
        r.raise_for_status()
        return r.json()

    async def call(self, adapter_id: str, action: str, params: dict, idem_key: str | None = None) -> dict[str, Any]:
        headers = {
            "x-actor-member-id": self._member,
            "x-actor-role": self._role,
            "x-space-id": self._space,
        }
        if idem_key:
            headers["x-idem-key"] = idem_key
        r = await self._http.post(
            f"{self._base}/k1/tools/{adapter_id}/{action}",
            json=params, headers=headers,
        )
        r.raise_for_status()
        return r.json()

    async def list_read(self, adapter_id: str, action: str, params: dict) -> dict[str, Any]:
        headers = {
            "x-actor-member-id": self._member,
            "x-actor-role": self._role,
            "x-space-id": self._space,
        }
        r = await self._http.get(
            f"{self._base}/k1/tools/{adapter_id}/{action}",
            params=params, headers=headers,
        )
        r.raise_for_status()
        return r.json()

    async def close(self) -> None:
        await self._http.aclose()
```

File: `k1/tools/family/reasoning.py`

```python
"""k1.tools.family.reasoning — LLM reasoning context builder.

Pulls llm_specs from each registered tool and converts them into the format
the Concierge planner / Fabric capability registry expects. Wires hints
(use_when, do_not_use_when, examples) into the system prompt so the LLM
picks the right tool.
"""
from __future__ import annotations

import httpx
from typing import Any


async def build_fabric_contracts(pseudo_k0_url: str, adapter_ids: list[str]) -> list[dict]:
    """Pull llm_specs from each tool and convert to Fabric contract shape."""
    out = []
    async with httpx.AsyncClient(timeout=5.0) as c:
        for adapter_id in adapter_ids:
            r = await c.get(f"{pseudo_k0_url}/k1/tools/{adapter_id}/llm_specs")
            r.raise_for_status()
            for spec in r.json():
                out.append(_to_fabric_contract(spec))
    return out


def _to_fabric_contract(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": spec["name"],                                 # "calendar.create_event"
        "description": _build_description(spec),
        "provider_type": "BRIDGE",
        "safety_band_min": spec["min_band"],
        "required_inputs": [
            {"name": k, "type": v.get("type"), "required": k in spec["parameters"].get("required", [])}
            for k, v in spec["parameters"]["properties"].items()
        ],
        "output_schema": spec.get("output_schema") or {},
        "metadata": {
            "category": spec["category"],
            "kind": spec["kind"],
            "idempotent": spec.get("idempotent", False),
            "llm_hints": spec.get("llm_hints", {}),
        },
    }


def _build_description(spec: dict[str, Any]) -> str:
    hints = spec.get("llm_hints", {})
    bits = [spec["description"]]
    if hints.get("use_when"):
        bits.append("Use when: " + "; ".join(hints["use_when"]))
    if hints.get("do_not_use_when"):
        bits.append("Do not use when: " + "; ".join(hints["do_not_use_when"]))
    return ". ".join(bits)
```

---

### E15.8 — K1 web routes (UI face)

File: `ui/web/routes/family_tools.py`

```python
"""ui.web.routes.family_tools — proxies /k1/tools/* to pseudo-K0.

In M15, the K1 web server proxies tool routes 1:1 to pseudo-K0. Later
milestones may add caching / response shaping here, but the proxy keeps
the dependency direction clean (UI never talks to pseudo-K0 directly).
"""
from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, Header, HTTPException, Request


def build_family_tools_router(pseudo_k0_url: str | None = None) -> APIRouter:
    pseudo_k0_url = pseudo_k0_url or os.environ.get("K0_ENDPOINT", "")
    router = APIRouter(prefix="/k1/tools", tags=["family_tools"])

    @router.api_route("/{adapter_id}/{action}", methods=["GET", "POST"])
    async def proxy(adapter_id: str, action: str, request: Request) -> dict:
        if not pseudo_k0_url:
            raise HTTPException(status_code=503, detail="K0_ENDPOINT not configured")
        url = f"{pseudo_k0_url}/k1/tools/{adapter_id}/{action}"
        headers = {k: v for k, v in request.headers.items()
                   if k.lower() in {"x-actor-member-id", "x-actor-role",
                                    "x-space-id", "x-trace-id", "x-idem-key",
                                    "content-type"}}
        body = await request.body()
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.request(
                request.method, url, content=body, headers=headers,
                params=request.query_params,
            )
        if r.status_code >= 400:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        return r.json()

    return router
```

Mount in `ui/web/app.py`:

```python
from ui.web.routes.family_tools import build_family_tools_router
app.include_router(build_family_tools_router())
```

---

### E15.9 — Fabric Auto-Registration at K1 Startup

Add to `UiCoordinator._phase2_kernel_startup()` (M12), after `start_kernel()` returns:

```python
# M15: pull tool specs from pseudo-K0 and register as Fabric capabilities
if k0_endpoint:
    from k1.tools.family.reasoning import build_fabric_contracts
    contracts = await build_fabric_contracts(
        pseudo_k0_url=k0_endpoint,
        adapter_ids=["calendar", "tasks", "reminders", "chores", "shopping", "family_settings"],
    )
    runtime.kernel_service.fabric.register_contracts(contracts)
    logger.info("Phase 2: registered %d family tool actions in Fabric", len(contracts))
```

This means the Concierge LLM at planning time sees:

```text
Available capabilities (subset):
  calendar.create_event(title, start, end, attendees, ...)
    Use when: user wants to add an event...
    Do not use when: user wants a recurring chore (use chores.create_chore)...
  calendar.list_events(start?, end?, member_filter?)
  tasks.create_task(title, assigned_to, due?, priority?, ...)
  reminders.create_reminder(title, recipient, trigger, ...)
  chores.complete_chore(assignment_id, evidence?)
  shopping.add_item(list_id, name, qty?, ...)
  ...
```

---

### E15.10 — SSE Subscription in K1

Add to `KernelService._startup_tier1()` (M14, after `LiveBridgeAdapter.connect()`):

```python
if isinstance(self._bridge, LiveBridgeAdapter):
    # Subscribe to tool_state.changed.v1 for our space
    asyncio.create_task(self._consume_tool_sse())

async def _consume_tool_sse(self) -> None:
    """Listen for tool_state.changed.v1 and invalidate UI projections."""
    async for event in self._bridge.subscribe_sse(
        topics=["tool_state.changed.v1"],
        space_id=self._config.selfmodel_space_id,
    ):
        await self._bus.publish("k1.tool_state.changed.v1", event)
```

K1 web shell subscribes via the existing SSE pipeline (`k1/sse/`) and pushes a
`tool-refresh` event to the browser, which calls `FamilyToolClient.list_*()` to redraw.

---

### E15.11 — Pre-flight Checklist

```powershell
# 1. M14 ConnectorHost exists
python -c "from scripts.pseudo_k0.connector_host import ConnectorHost, IMCPHandler; print('OK')"

# 2. M14 SQLiteK0Store exists
python -c "from scripts.pseudo_k0.store import SQLiteK0Store; print('OK')"

# 3. M13 FamilyProfile exists with role field
python -c "
from verticals.family.profile import FamilyMember
import dataclasses
print([f.name for f in dataclasses.fields(FamilyMember)])
"

# 4. Pydantic V2 + FastAPI versions
python -c "import pydantic, fastapi; print('pydantic', pydantic.__version__, 'fastapi', fastapi.__version__)"

# 5. Fabric register_contracts entry point
python -c "
from k1.fabric import manifest_translator
print('translator:', manifest_translator)
" 2>/dev/null || echo "verify k1/fabric/manifest_translator.py"

# 6. K1 SSE pipeline can receive new event type
python -c "
from k1.sse import topics
print('topics module:', topics)
" 2>/dev/null || echo "verify k1/sse/topics.py and add tool_state.changed.v1"

# 7. UiCoordinator._phase2_kernel_startup is async
python -c "
import inspect, asyncio
from ui.web.coordinator import UiCoordinator
fn = getattr(UiCoordinator, '_phase2_kernel_startup', None)
print('async:', asyncio.iscoroutinefunction(fn))
"

# 8. No file naming collisions
Test-Path d:\familyos\scripts\pseudo_k0\tools  # should be False before M15 starts
Test-Path d:\familyos\k1\tools\family          # should be False before M15 starts
```

---

### E15.12 — Tests

#### Issue E15.12.1 — Foundation tests

File: `tests/scripts/pseudo_k0/tools/test_base.py`

```python
"""Foundation tests — BaseToolService dispatch, ACL, idempotency."""
import pytest
from scripts.pseudo_k0.tools.base import BaseEntity, BaseToolService, WriteContext
from scripts.pseudo_k0.tools.policy import default_policy
from scripts.pseudo_k0.tools.acl import filter_rows


class TestBaseEntity:
    def test_new_entity_gets_id_and_timestamps(self):
        class E(BaseEntity):
            title: str
        e = E(space_id="family:test", created_by="alex", title="t")
        assert e.id
        assert e.version == 1
        assert e.created_at > 0
        assert e.source == "native"

    def test_bump_increments_version_and_audit(self):
        class E(BaseEntity):
            title: str
        e = E(space_id="s", created_by="alex", title="t")
        v0, t0 = e.version, e.updated_at
        import time; time.sleep(0.002)
        e.bump("jordan")
        assert e.version == v0 + 1
        assert e.updated_by == "jordan"
        assert e.updated_at > t0


class TestACL:
    def _ctx(self, member, role):
        return WriteContext(actor_member_id=member, actor_role=role, space_id="s")

    def test_creator_sees_own_private_event(self):
        rows = [{"created_by": "alex", "visibility": "private", "visible_to": []}]
        out = filter_rows(rows, self._ctx("alex", "parent"))
        assert len(out) == 1

    def test_child_does_not_see_adults_event(self):
        rows = [{"created_by": "alex", "visibility": "adults", "visible_to": []}]
        out = filter_rows(rows, self._ctx("riley", "child"))
        assert out == []

    def test_parent_sees_adults_event(self):
        rows = [{"created_by": "alex", "visibility": "adults", "visible_to": []}]
        out = filter_rows(rows, self._ctx("jordan", "parent"))
        assert len(out) == 1

    def test_named_acl_includes_listed_members(self):
        rows = [{"created_by": "alex", "visibility": "named",
                 "visible_to": ["riley", "jordan"]}]
        assert len(filter_rows(rows, self._ctx("riley",  "child"))) == 1
        assert len(filter_rows(rows, self._ctx("jordan", "parent"))) == 1
        assert filter_rows(rows, self._ctx("nana", "elder")) == []

    def test_family_event_visible_to_all(self):
        rows = [{"created_by": "alex", "visibility": "family", "visible_to": []}]
        for member, role in [("riley", "child"), ("nana", "elder"), ("jordan", "parent")]:
            assert len(filter_rows(rows, self._ctx(member, role))) == 1


class TestVisibilityPolicy:
    def test_default_native_is_family(self):
        class E(BaseEntity):
            title: str = ""
        pol = default_policy()
        e = E(space_id="s", created_by="a", source="native")
        assert pol.apply(e, "parent") == "family"

    def test_google_work_is_adults(self):
        class E(BaseEntity):
            title: str = ""
        pol = default_policy()
        e = E(space_id="s", created_by="a", source="google", source_label="work")
        assert pol.apply(e, "parent") == "adults"

    def test_sensitive_keyword_overrides_to_adults(self):
        class E(BaseEntity):
            title: str = ""
        pol = default_policy()
        e = E(space_id="s", created_by="a", title="doctor appointment", source="native")
        assert pol.apply(e, "parent") == "adults"

    def test_explicit_visibility_wins(self):
        class E(BaseEntity):
            title: str = ""
        pol = default_policy()
        e = E(space_id="s", created_by="a", visibility="private", title="doctor")
        assert pol.apply(e, "parent") == "private"
```

#### Issue E15.12.2 — Per-app CRUD + ACL tests (12+ each)

`tests/scripts/pseudo_k0/tools/test_calendar.py` — 18 tests:

- `test_create_event_persists`
- `test_create_event_emits_sse`
- `test_create_event_writes_wal`
- `test_update_event_bumps_version`
- `test_update_event_stale_version_rejected`
- `test_delete_event_marks_deleted_at`
- `test_list_events_filters_by_space`
- `test_list_events_filters_by_window`
- `test_list_events_applies_acl_for_child`
- `test_get_event_404_when_missing`
- `test_set_visibility_parent_only`
- `test_set_visibility_child_rejected`
- `test_connect_feed_creates_disabled`
- `test_idempotent_create_event_replays`
- `test_external_google_work_event_default_adults`
- `test_native_event_default_family`
- `test_cross_tool_linked_to_task`
- `test_attendees_validated_against_profile`

Repeat similar pattern for: `test_tasks.py`, `test_reminders.py`, `test_chores.py`,
`test_shopping.py`, `test_family_settings.py` — each ~12–15 tests.

#### Issue E15.12.3 — Manifest + LLM spec tests

File: `tests/scripts/pseudo_k0/tools/test_manifest.py`

```python
"""Manifest generation tests."""
from scripts.pseudo_k0.tools.calendar.definition import CALENDAR_DEFINITION
from scripts.pseudo_k0.tools.manifest import (
    ui_manifest, llm_tool_specs, openapi_paths,
)


def test_parent_manifest_includes_set_visibility():
    m = ui_manifest(CALENDAR_DEFINITION, "parent")
    assert "set_visibility" in m["actions"]


def test_child_manifest_excludes_set_visibility():
    m = ui_manifest(CALENDAR_DEFINITION, "child")
    assert "set_visibility" not in m["actions"]


def test_llm_specs_include_use_when_hints():
    specs = llm_tool_specs(CALENDAR_DEFINITION)
    create = next(s for s in specs if s["name"] == "calendar.create_event")
    assert create["llm_hints"]["use_when"]
    assert any("event" in u.lower() for u in create["llm_hints"]["use_when"])


def test_llm_specs_include_do_not_use_for_disambiguation():
    specs = llm_tool_specs(CALENDAR_DEFINITION)
    create = next(s for s in specs if s["name"] == "calendar.create_event")
    assert any("chore" in d.lower() for d in create["llm_hints"]["do_not_use_when"])


def test_openapi_paths_built_for_all_actions():
    paths = openapi_paths(CALENDAR_DEFINITION)
    assert "/k1/tools/calendar/create_event" in paths
    assert "/k1/tools/calendar/list_events" in paths
```

#### Issue E15.12.4 — Cross-family SSE end-to-end

File: `tests/scripts/pseudo_k0/test_sse_fanout.py`

```python
"""Cross-family SSE fan-out test."""
import asyncio
import pytest
from scripts.pseudo_k0.tools.events import EventEmitter
from scripts.pseudo_k0.store import SQLiteK0Store


@pytest.mark.asyncio
async def test_two_subscribers_both_receive_event():
    store = SQLiteK0Store(":memory:")
    emitter = EventEmitter(store)
    q_dad = emitter.subscribe("family:smith")
    q_riley = emitter.subscribe("family:smith")
    q_other = emitter.subscribe("family:jones")

    # Simulate calendar service writing
    from scripts.pseudo_k0.tools.base import WriteContext
    from scripts.pseudo_k0.tools.calendar.schema import CalendarEvent
    ev = CalendarEvent(
        space_id="family:smith", created_by="alex",
        title="t", start="2026-05-15T10:00", end="2026-05-15T11:00",
    )
    ctx = WriteContext(actor_member_id="alex", actor_role="parent", space_id="family:smith")
    await emitter.emit_write("calendar", "create_event", ev, ctx)

    dad_msg = await asyncio.wait_for(q_dad.get(), timeout=1.0)
    riley_msg = await asyncio.wait_for(q_riley.get(), timeout=1.0)
    assert dad_msg["tool"] == "calendar"
    assert riley_msg["entity_id"] == ev.id
    assert q_other.empty()  # other family doesn't get the event
```

#### Issue E15.12.5 — Three-faces parity

File: `tests/scripts/pseudo_k0/test_three_faces_parity.py`

```python
"""LLM, UI, voice all hit the same path → same result."""
import asyncio
import pytest


@pytest.mark.asyncio
async def test_llm_and_ui_face_produce_identical_writes(registry, async_client):
    # FACE 1: LLM via ConnectorHost
    llm_result = await registry._connector_host.dispatch(
        "calendar", "create_event",
        params={"title": "via-llm", "start": "2026-05-15T10:00", "end": "2026-05-15T11:00",
                "_ctx": {"actor_member_id": "alex", "actor_role": "parent", "space_id": "family:t"}},
        trace_id="llm-trace",
    )
    # FACE 2: UI via REST
    ui_result = await async_client.post(
        "/k1/tools/calendar/create_event",
        json={"title": "via-ui", "start": "2026-05-15T12:00", "end": "2026-05-15T13:00"},
        headers={
            "x-actor-member-id": "alex",
            "x-actor-role": "parent",
            "x-space-id": "family:t",
        },
    )
    assert llm_result["success"]
    assert ui_result.status_code == 200
    # Both events queryable via list_events
    listing = await async_client.get(
        "/k1/tools/calendar/list_events",
        headers={"x-actor-member-id": "alex", "x-actor-role": "parent", "x-space-id": "family:t"},
    )
    titles = {e["title"] for e in listing.json()["result"]["events"]}
    assert {"via-llm", "via-ui"} <= titles
```

**Test counts target**: ~80 tests across foundation + 6 apps + manifest + SSE + parity.

---

### E15.13 — Implementation Order (20 steps)

```text
Step 1:  Create scripts/pseudo_k0/tools/__init__.py
Step 2:  Create base.py (BaseEntity + WriteContext)
Step 3:  Create definition.py (ToolDefinition + ActionSpec + LLMHints + FieldSpec + SSESpec)
Step 4:  Create policy.py (VisibilityPolicy + default rules)
Step 5:  Create acl.py (filter_rows)
Step 6:  Create events.py (EventEmitter)
Step 7:  Create idem.py (IdempotencyStore)
Step 8:  Append BaseToolService class to base.py
Step 9:  Create handler.py (_ServiceHandler) + registry.py (ToolRegistry)
Step 10: Create manifest.py (ui_manifest + llm_tool_specs + openapi_paths)
Step 11: Create routes.py (build_router factory)
Step 12: Run foundation tests: pytest tests/scripts/pseudo_k0/tools/test_base.py
                                       tests/scripts/pseudo_k0/tools/test_manifest.py
Step 13: Create calendar/ app (schema, tables.sql, service, definition)
Step 14: Update pseudo_k0/server.py create_app() to mount tool registry + SSE fan-out
Step 15: Smoke test: python -m scripts.pseudo_k0 ; curl GET /k1/tools/calendar/manifest
Step 16: Create tasks/, reminders/, chores/, shopping/, family_settings/ apps
Step 17: Create k1/tools/family/{client.py, manifest_cache.py, reasoning.py}
Step 18: Create ui/web/routes/family_tools.py + mount in app
Step 19: Wire Fabric auto-registration in UiCoordinator._phase2_kernel_startup()
Step 20: Wire SSE subscription in KernelService._startup_tier1() for tool_state.changed.v1
Step 21: End-to-end smoke test:
           a. boot_web.ps1 -WithK0
           b. mom's browser: create calendar event via UI form
           c. dad's browser: receives tool_state.changed.v1 within 2s
           d. dad's browser: list_events shows mom's event
           e. ask Concierge "what's on the calendar this week?"
           f. Concierge calls calendar.list_events → answers correctly
           g. ask Concierge "add Riley's soccer game Saturday 10am"
           h. Concierge calls calendar.create_event → SSE fan-out
```

**Key gotchas:**

1. **Single VisibilityPolicy instance** — `ToolRegistry` holds one `VisibilityPolicy`; all
   tool services share it. Hot-reloading from `family_settings.update_visibility_policy`
   requires `policy.rules[:] = new_rules` (mutate in place, don't reassign).
2. **`linked_to` is a JSON column** — cross-tool refs serialize via `json.dumps`. Always
   `json.loads` in `_row_to_entity_dict`.
3. **`tool_state.changed.v1` is global** — every tool emits to the same topic. K1
   consumers must dispatch on `payload["tool"]` to know which projection to refresh.
4. **Idempotency keys are scoped per-space** — same `idem_key` in two families must NOT
   collide. The `tool_idem` PK includes `space_id`.
5. **ACL is read-time only** — the WAL contains everything. A child reading the WAL
   directly would see adults-only rows. This is acceptable because WAL access is bridge-
   only (not UI). Defense in depth: pseudo-K0 `query.recall` route also applies the ACL
   filter when `caller_member_id` is passed in.
6. **`_ServiceHandler.call` removes `_ctx` from params** — clients pass the WriteContext as
   `params["_ctx"]`. The handler pops it before forwarding to `service.dispatch`. UI face
   uses HTTP headers instead.

---

### E15.14 — Why this is the moat (the LLM-reasoning angle)

The Concierge LLM at planning time sees not just _what tools exist_ but _when to use each
one_ via the `LLMHints` carried in every action spec. This is the difference between:

> Bad: "I have a tool called `calendar.create_event(title, start, end)`. The user said
> 'remind me to call mom Saturday'. I'll call `calendar.create_event(title='call mom',
> start='2026-05-16T00:00', end='2026-05-16T00:00')`."

vs

> Good: "I see `calendar.create_event` (Use when: scheduled activity with date and time;
> Do not use when: user wants a time-or-location reminder → reminders.create_reminder).
> The user said 'remind me' → reminders.create_reminder is the right choice."

Plus:

- **read_before_write hints** drive the planner to call `list_events` before `create_event`
  on overlapping windows
- **examples** train few-shot prompts for arg generation
- **preconditions** let the planner validate before invoking (avoid wasted band)
- **side_effects** + **typical_followups** drive proactive suggestions
- **cross-tool links** (`can_reference`) let the LLM connect: "this calendar event has a
  task linked to it" → updates both

Future apps (health, finance, IoT) inherit this whole reasoning surface for free by
filling in `LLMHints` per action. **That's the foundation, not the apps**.

---

### E15.15 — How future apps (Health, Finance, IoT) plug in

When you add Health/Medication (M18 say), you write:

```text
scripts/pseudo_k0/tools/health_medication/
├── schema.py       ← Medication, MedicationDose, MedicationSchedule (extends BaseEntity)
├── tables.sql      ← DDL for projection tables
├── service.py      ← HealthMedicationService(BaseToolService) — ~250 LOC
└── definition.py   ← ToolDefinition + ActionSpec with HIPAA-grade LLMHints
```

You DO NOT write:

- UI manifest generator (foundation does it)
- LLM tool spec generator (foundation does it)
- REST routes (foundation does it via `build_router`)
- WAL write logic (foundation does it via `EventEmitter`)
- SSE fan-out (foundation does it)
- ACL filter (foundation does it)
- Idempotency (foundation does it)
- Audit log (foundation does it via `BaseEntity.bump()` + WAL)
- Optimistic concurrency (foundation does it via `version`)
- Fabric registration (foundation does it via `llm_tool_specs` → `build_fabric_contracts`)

You optionally add:

- A new `VisibilityPolicy` rule (e.g. `_health_default → "adults"`)
- A new feature flag in `FamilyFeatureFlag` (e.g. `health.dose_log_visible_to_kids`)
- A new safety band (e.g. `RED` for medication writes — requires PIN)

That's the moat. The foundation compounds.

---

### E15.16 — Acceptance Criteria

M15 is complete when **all** of these pass:

> **Apply R-3 path translation** when reading the criteria below. REST endpoints are
> on K1's web app (`http://localhost:<K1_PORT>/k1/tools/...`), not pseudo-K0.

1. K1 boot wires `ToolRegistry`, registers 6 services (5 apps + family_settings),
   creates `data/k1_family.db`, and registers ~30 `CapabilityContract`s in Fabric —
   **without requiring `K0_ENDPOINT`**.
2. `GET /k1/tools/calendar/manifest?role=parent` (on K1) returns full manifest with `set_visibility`
3. `GET /k1/tools/calendar/manifest?role=child` returns filtered manifest (no set_visibility)
4. `GET /k1/tools/calendar/llm_specs` returns array of LLM tool specs with `llm_hints`
5. `POST /k1/tools/calendar/create_event` (UI face) → `service.dispatch()` directly →
   writes projection to `data/k1_family.db` + emits SSE on K1 bus + (if K0 reachable) enqueues sync envelope.
6. **Concierge LLM `tool_call("calendar.create_event", ...)` routes through
   `execute_invoke_capability` → `FabricDispatchAdapter.dispatch_direct` →
   `CapabilityFabric.execute` → `NativeToolProvider` → `BaseToolService.dispatch` →
   identical projection + SSE.** Verified by integration test (§E15.-1 pattern, full
   service). Both faces hit the same `dispatch()`; results are byte-identical except `face` tag.
7. Mom's K1 creates event → dad's K1 receives SSE within 2s (via shared K0 sync when K0 is up)
8. Visibility ACL: parent sees `adults` events; child does not
9. Per-event override: parent calls `set_visibility` → child stops seeing event
10. `update_visibility_policy` from family_settings invalidates default rules live
11. K1 boot registers ~30 Fabric contracts (one per action across the 6 services)
12. Concierge LLM with all family tools available reliably picks `reminders.create_reminder`
    for "remind dad about milk" and `calendar.create_event` for "soccer Saturday 10am"
    (qualitative — verified manually with 5 test prompts)
13. All M15 tests pass: `pytest tests/k1/tools/family/ tests/k1/fabric/providers/test_native_tool_provider_path.py -q --no-cov`
14. `boot_web.ps1` end-to-end smoke succeeds **both** with and without `K0_ENDPOINT` set.
15. M13 seeded family appears: Calendar shows Riley's soccer game, Chores shows Riley's vacuum
16. **AC-A (K0-optional)** — full E2E happy path passes with `K0_ENDPOINT` unset.
17. **AC-B (K0-sync)** — when `K0_ENDPOINT` is set, every successful write produces a
    sync envelope visible in K0's WAL within 5s (best-effort).
18. **AC-D (no bridge leak)** — CI gate `bridge_not_imported_from_kernels` green;
    `k1/tools/family/` has zero `bridge.*` imports.

---

### E11.0 — Bridge-Routed MCP Transport Layer

**Goal**: Wire MCP capability requests from K1 Fabric through the bridge to pseudo-K0's
`/k0/connector.execute` endpoint.

#### Issue E11.0.1 — Implement `ConnectorHost` in `scripts/pseudo_k0/connector_host.py`

`ConnectorHost` is the pseudo-K0-side registry of all local MCP servers:

```python
class ConnectorHost:
    """
    Hosts all local MCP servers inside pseudo-K0 process.
    Dispatches connector.execute requests to the appropriate server handler.
    """
    def __init__(self) -> None:
        self._adapters: dict[str, IMCPHandler] = {}

    def register(self, adapter_id: str, handler: IMCPHandler) -> None: ...

    async def dispatch(
        self,
        adapter_id: str,
        action: str,
        params: dict,
        trace_id: str | None,
    ) -> dict: ...
    # Returns: {"success": bool, "result": dict | None, "error": str | None}
```

At pseudo-K0 startup, all MCP servers register themselves:

```python
host = ConnectorHost()
host.register("calendar",  CalendarMCPHandler(db_path))
host.register("tasks",     TasksMCPHandler(db_path))
host.register("reminders", RemindersMCPHandler(db_path))
host.register("chores",    ChoresMCPHandler(db_path))
host.register("messaging", MessagingMCPHandler(db_path))
host.register("budget",    BudgetMCPHandler(db_path))
host.register("school",    SchoolMCPHandler(db_path))
host.register("health",    HealthMCPHandler(db_path))
```

Touch point: NEW `scripts/pseudo_k0/connector_host.py`

#### Issue E11.0.2 — Add `BridgeConnectorMCPTransport` to K1 Fabric

A new transport class that routes MCP tool calls through the bridge instead of stdio:

```python
class BridgeConnectorMCPTransport(IMCPTransport):
    """
    Routes MCP tool calls to pseudo-K0 /k0/connector.execute via bridge.
    Used when K0_ENDPOINT is set. Falls back to stdio transport when not.
    """
    def __init__(self, bridge_port: IFabricK0Port, adapter_id: str) -> None: ...

    async def call_tool(self, tool_name: str, arguments: dict, trace_id: str) -> dict:
        result = await self._bridge.send_command(
            operation="connector.execute",
            payload={"adapter_id": self._adapter_id, "action": tool_name, "params": arguments},
            trace_id=trace_id,
        )
        return result.data
```

Touch point: NEW `k1/fabric/transports/bridge_connector_transport.py`

#### Issue E11.0.3 — Auto-select transport in `MCPProviderFactory`

When `KernelConfig.k0_endpoint` is set, `MCPProviderFactory` uses `BridgeConnectorMCPTransport`.
When it is empty, falls back to existing `AutoDiscoveryMCPTransport` (stdio — for local dev
without pseudo-K0).

Touch point: EDIT `k1/fabric/providers/mcp_provider.py` (or relevant factory) — transport selector

#### Issue E11.0.4 — Add `connector.execute` to K1 `BridgeProvider`

Currently `BridgeProvider` handles: `memory.store`, `memory.delta`, `memory.recall`, `checkpoint`,
`feedback.signal`, `tool.execute.home.*`, `tool.execute.device.*` via `route_ifl`.

Add: `connector.execute` as a new operation routed via `send_command`:

```python
# In BridgeProvider._execute():
if request.capability_name.startswith("tool.execute.family."):
    # Route through connector.execute
    adapter_id = request.capability_name.split(".")[3]  # "calendar", "tasks", etc.
    action = request.capability_name.split(".")[4]       # "list_events", "create_task", etc.
    result = await bridge.send_command(
        operation="connector.execute",
        payload={"adapter_id": adapter_id, "action": action, "params": dict(request.params)},
        trace_id=trace_id,
    )
```

Touch point: EDIT `k1/fabric/providers/bridge_provider.py` — add `connector.execute` branch

---

### E11.1 — Calendar Enhancement (Tier 1)

_(Same as `POC_MIGRATION_PLAN.md` E11.1 but handlers live in pseudo-K0 `connector_host`, not
directly in K1 Fabric MCP server subprocess.)_

**Existing**: `k1/tools/mcp_servers/calendar/` — models, storage, handlers, server.
**Change**: handlers also registered with `ConnectorHost` in pseudo-K0.

#### Issue E11.1.1 — Register Calendar handler in `ConnectorHost`

Create `scripts/pseudo_k0/adapters/calendar_handler.py` that wraps the existing
`k1/tools/mcp_servers/calendar/handlers.py` `CalendarToolHandlers` class as an `IMCPHandler`.
Register as `host.register("calendar", CalendarHandler(...))`.

Touch points:

- NEW `scripts/pseudo_k0/adapters/calendar_handler.py`
- EDIT `scripts/pseudo_k0/server.py` — register at startup

#### Issue E11.1.2 — Add `tool.write.calendar_update_event` contract + handler

Same as `POC_MIGRATION_PLAN.md` E11.1.1. The handler addition goes into
`k1/tools/mcp_servers/calendar/handlers.py`; the registration propagates to pseudo-K0 via the
adapter wrapper.

Touch points:

- NEW `k1/contracts/tools/calendar_update_event.yaml`
- EDIT `k1/tools/mcp_servers/calendar/storage.py` — `update_event()`
- EDIT `k1/tools/mcp_servers/calendar/handlers.py` — `update_event()` handler

#### Issue E11.1.3 — Recurring events, multi-member views, conflict detection

Same as `POC_MIGRATION_PLAN.md` E11.1.2 – E11.1.4. No routing change — these are internal
handler enhancements.

Touch points: Same as `POC_MIGRATION_PLAN.md` E11.1.2 – E11.1.4

#### Issue E11.1.4 — Calendar E2E tests via bridge path

Add bridge-routed tests alongside existing stdio tests:

- Same test scenarios but call through `BridgeConnectorMCPTransport` pointing at a test
  `ConnectorHost` (in-process, no HTTP)
- Assert identical results

Touch point: NEW `tests/k1/fabric/tools/test_calendar_bridge_e2e.py` (~30 tests)

---

### E11.2 — Tasks & Lists (Tier 1)

#### Issue E11.2.1 — Scaffold `k1/tools/mcp_servers/tasks/`

```
k1/tools/mcp_servers/tasks/
├── __init__.py
├── models.py      ← Task, TaskList dataclasses
├── storage.py     ← SQLiteTaskStorage
├── handlers.py    ← TaskToolHandlers
└── server.py      ← MCP server (FastMCP style)
```

`Task` model:

```python
@dataclass
class Task:
    task_id: str
    title: str
    list_name: str        # "groceries" | "todo" | "school" | custom
    owner: str            # actor_id
    assigned_to: str      # actor_id or ""
    due_date: str | None  # ISO date
    priority: str         # "low" | "medium" | "high"
    status: str           # "open" | "in_progress" | "done"
    tags: list[str]
    created_at: str
    updated_at: str
```

Touch point: NEW `k1/tools/mcp_servers/tasks/` (4 files)

#### Issue E11.2.2 — Define 6 contracts for Tasks

```
k1/contracts/tools/
├── tasks_list.yaml          — tool.read.tasks_list        GREEN
├── tasks_create.yaml        — tool.write.tasks_create     AMBER
├── tasks_update.yaml        — tool.write.tasks_update     AMBER
├── tasks_complete.yaml      — tool.write.tasks_complete   AMBER
├── tasks_delete.yaml        — tool.delete.tasks_delete    AMBER
└── tasks_search.yaml        — tool.read.tasks_search      GREEN
```

Touch points: NEW 6 YAML contract files in `k1/contracts/tools/`

#### Issue E11.2.3 — Register Tasks handler in `ConnectorHost`

Touch points:

- NEW `scripts/pseudo_k0/adapters/tasks_handler.py`
- EDIT `scripts/pseudo_k0/server.py` — register `"tasks"`

#### Issue E11.2.4 — Tasks E2E tests

Touch point: NEW `tests/k1/fabric/tools/test_tasks_bridge_e2e.py` (~25 tests)

---

### E11.3 — Family Messaging (Tier 1)

#### Issue E11.3.1 — Scaffold `k1/tools/mcp_servers/messaging/`

`Message` model: `message_id`, `from_actor`, `to_actor` (or `"family"`), `subject`, `body`,
`thread_id`, `read_by: list[str]`, `priority`, `created_at`.

Touch point: NEW `k1/tools/mcp_servers/messaging/` (4 files)

#### Issue E11.3.2 — Define 4 contracts for Messaging

```
messaging_send.yaml          — tool.write.messaging_send      AMBER
messaging_list.yaml          — tool.read.messaging_list       GREEN
messaging_mark_read.yaml     — tool.write.messaging_mark_read AMBER
messaging_search.yaml        — tool.read.messaging_search     GREEN
```

Touch points: NEW 4 YAML contract files

#### Issue E11.3.3 — Register Messaging handler + E2E tests

Touch points:

- NEW `scripts/pseudo_k0/adapters/messaging_handler.py`
- NEW `tests/k1/fabric/tools/test_messaging_bridge_e2e.py` (~20 tests)

---

### E11.4 — Reminders & Timers (Tier 1)

#### Issue E11.4.1 — Scaffold `k1/tools/mcp_servers/reminders/`

`Reminder` model: `reminder_id`, `title`, `actor_id`, `trigger_at` (ISO datetime),
`recurrence` (none/daily/weekly), `status` (pending/fired/cancelled), `notify_via` (app/bus).

Touch point: NEW `k1/tools/mcp_servers/reminders/` (4 files)

#### Issue E11.4.2 — Define 5 contracts for Reminders

```
reminders_create.yaml    — tool.write.reminders_create     AMBER
reminders_list.yaml      — tool.read.reminders_list        GREEN
reminders_update.yaml    — tool.write.reminders_update     AMBER
reminders_cancel.yaml    — tool.write.reminders_cancel     AMBER
reminders_list_due.yaml  — tool.read.reminders_list_due    GREEN
```

Touch points: NEW 5 YAML contract files

#### Issue E11.4.3 — Register Reminders handler + E2E tests

Touch points:

- NEW `scripts/pseudo_k0/adapters/reminders_handler.py`
- NEW `tests/k1/fabric/tools/test_reminders_bridge_e2e.py` (~20 tests)

---

### E11.5 — Chore Manager (Tier 1)

#### Issue E11.5.1 — Scaffold `k1/tools/mcp_servers/chores/`

`Chore` model: `chore_id`, `title`, `assigned_to` (actor_id), `frequency`
(daily/weekly/monthly/once), `last_completed_at`, `next_due_at`, `points` (gamification),
`status` (pending/done/skipped).

Touch point: NEW `k1/tools/mcp_servers/chores/` (4 files)

#### Issue E11.5.2 — Define 5 contracts for Chores

```
chores_list.yaml        — tool.read.chores_list         GREEN
chores_assign.yaml      — tool.write.chores_assign      AMBER
chores_complete.yaml    — tool.write.chores_complete    AMBER
chores_skip.yaml        — tool.write.chores_skip        AMBER
chores_summary.yaml     — tool.read.chores_summary      GREEN
```

Touch points: NEW 5 YAML contract files

#### Issue E11.5.3 — Register Chores handler + E2E tests

Touch points:

- NEW `scripts/pseudo_k0/adapters/chores_handler.py`
- NEW `tests/k1/fabric/tools/test_chores_bridge_e2e.py` (~20 tests)

---

### E11.6 — Meal Planner Enhancement (Tier 2)

_(Extends existing `k1/tools/mcp_servers/recipes/` — same bridge-registration pattern)_

#### Issue E11.6.1 — Add `tool.write.mealplan_assign` and `tool.read.mealplan_week` contracts

`MealPlan` model: `plan_id`, `week_of` (ISO date of Monday), `days: dict[str, list[str]]` (day →
list of recipe_ids), `shopping_list_generated: bool`.

Touch points:

- NEW `k1/contracts/tools/mealplan_assign.yaml` + `mealplan_week.yaml`
- EDIT `k1/tools/mcp_servers/recipes/storage.py` — add `MealPlanStorage`
- EDIT `k1/tools/mcp_servers/recipes/handlers.py` — add meal plan handlers
- NEW `scripts/pseudo_k0/adapters/recipes_handler.py`

---

### E11.7 — Family Budget (Tier 2)

#### Issue E11.7.1 — Scaffold `k1/tools/mcp_servers/budget/`

`Transaction` model: `tx_id`, `amount_cents`, `category`, `description`, `actor_id`,
`date`, `payment_method`, `recurring`: bool.
`Budget` model: `budget_id`, `category`, `limit_cents`, `period` (monthly/weekly), `space_id`.

Touch point: NEW `k1/tools/mcp_servers/budget/` (4 files)

#### Issue E11.7.2 — Define 5 contracts for Budget

```
budget_log_expense.yaml      — tool.write.budget_log_expense   AMBER
budget_list_expenses.yaml    — tool.read.budget_list_expenses  GREEN
budget_summary.yaml          — tool.read.budget_summary        GREEN
budget_set_limit.yaml        — tool.write.budget_set_limit     RED   ← family financial setting
budget_check_limit.yaml      — tool.read.budget_check_limit    GREEN
```

Touch points: NEW 5 YAML contract files

#### Issue E11.7.3 — Register Budget handler + E2E tests

Touch points:

- NEW `scripts/pseudo_k0/adapters/budget_handler.py`
- NEW `tests/k1/fabric/tools/test_budget_bridge_e2e.py` (~20 tests)

---

### E11.8 — School Hub (Tier 2)

#### Issue E11.8.1 — Scaffold `k1/tools/mcp_servers/school/`

`SchoolEvent` model: `event_id`, `student_actor_id`, `title`, `event_type`
(homework/exam/activity/meeting), `due_date`, `subject`, `status`, `grade_received`.

Touch point: NEW `k1/tools/mcp_servers/school/` (4 files)

#### Issue E11.8.2 — Define 5 contracts for School

```
school_list_events.yaml     — tool.read.school_list_events    GREEN
school_add_event.yaml       — tool.write.school_add_event     AMBER
school_mark_done.yaml       — tool.write.school_mark_done     AMBER
school_grade_record.yaml    — tool.write.school_grade_record  AMBER
school_summary.yaml         — tool.read.school_summary        GREEN
```

Touch points: NEW 5 YAML contract files

#### Issue E11.8.3 — Register School handler + E2E tests

Touch points:

- NEW `scripts/pseudo_k0/adapters/school_handler.py`
- NEW `tests/k1/fabric/tools/test_school_bridge_e2e.py` (~20 tests)

---

### E11.9 — Health & Medication (Tier 3)

#### Issue E11.9.1 — Scaffold `k1/tools/mcp_servers/health/`

`MedRecord` model: `record_id`, `actor_id`, `medication_name`, `dose`, `frequency`,
`last_taken_at`, `next_due_at`, `prescribed_by`, `notes`.

Touch point: NEW `k1/tools/mcp_servers/health/` (4 files)

#### Issue E11.9.2 — Define 6 contracts for Health (RED band for medication writes)

```
health_list_medications.yaml   — tool.read.health_list_medications   GREEN
health_log_taken.yaml          — tool.write.health_log_taken         AMBER
health_update_medication.yaml  — tool.write.health_update_medication RED  ← dose change
health_missed_dose.yaml        — tool.read.health_missed_dose        GREEN
health_add_medication.yaml     — tool.write.health_add_medication    RED
health_summary.yaml            — tool.read.health_summary            GREEN
```

Touch points: NEW 6 YAML contract files

#### Issue E11.9.3 — Register Health handler + E2E tests

Touch points:

- NEW `scripts/pseudo_k0/adapters/health_handler.py`
- NEW `tests/k1/fabric/tools/test_health_bridge_e2e.py` (~25 tests)

---

### E11.10 — Transport & Pickup (Tier 3)

#### Issue E11.10.1 — Scaffold `k1/tools/mcp_servers/transport/`

`PickupRecord` model: `pickup_id`, `child_actor_id`, `pickup_by_actor_id`, `location`,
`scheduled_at`, `actual_at`, `status` (scheduled/completed/cancelled), `notes`.

Touch point: NEW `k1/tools/mcp_servers/transport/` (4 files)

#### Issue E11.10.2 — Define 4 contracts for Transport

```
transport_schedule_pickup.yaml  — tool.write.transport_schedule_pickup  AMBER
transport_list_pickups.yaml     — tool.read.transport_list_pickups      GREEN
transport_confirm_pickup.yaml   — tool.write.transport_confirm_pickup   AMBER
transport_cancel_pickup.yaml    — tool.write.transport_cancel_pickup    AMBER
```

Touch points: NEW 4 YAML contract files

#### Issue E11.10.3 — Register Transport handler + E2E tests

Touch points:

- NEW `scripts/pseudo_k0/adapters/transport_handler.py`
- NEW `tests/k1/fabric/tools/test_transport_bridge_e2e.py` (~15 tests)

---

### E11.11 — Integration: All Tools Reachable via K1 Chat

#### Issue E11.11.1 — Integration smoke test: all 8 tool domains accessible via bridge

With pseudo-K0 running + K1 booted via `boot_web.ps1 -WithK0`:

Test each domain with one round-trip (create then list):

- `calendar`: create event → list events → event appears
- `tasks`: create task → list tasks → task appears
- `messaging`: send message → list messages → message appears
- `reminders`: create reminder → list due → reminder appears
- `chores`: assign chore → list chores → chore appears
- `budget`: log expense → summary → expense reflected
- `school`: add event → list → event appears
- `health`: log taken → missed dose check → works

Touch point: NEW `tests/k1/kernel/test_e2e_tools_via_bridge.py` (~16 tests, 2 per domain)

#### Issue E11.11.2 — Verify tool calls appear in Timeline panel

Manual verification: boot web UI, send "What's on the calendar this week?" → Timeline panel
shows `tool_event` entries for `tool.read.calendar_list_events` dispatched → completed.

Touch point: MANUAL TEST (no automated file)

---

## Dependency Graph

```
M12 (Web UI)         M13 (Family Data)      M14 (Pseudo-K0)      M11 (Tools via Bridge)
─────────────────    ─────────────────      ─────────────────    ──────────────────────
E12.1 scaffold       E13.1 FamilyProfile    E14.1 server pkg     E11.0 bridge transport
E12.2 coordinator ─► E13.2 Layer A seeder   E14.2 SQLiteStore    E11.1 Calendar
E12.3 app.py         E13.3 Layer B seeder   E14.3 HTTP endpoints E11.2 Tasks
E12.4 boot script    E13.4 seeder tests     E14.4 K1 wiring  ──► E11.3 Messaging
E12.5 tests          │                      E14.5 tests          E11.4 Reminders
│                    │                      │                    E11.5 Chores
▼                    ▼                      ▼                    E11.6 Meals
E12 works            E13 works alone        E14 enables K0       E11.7 Budget
K0_OFFLINE           (beliefs in session)   memory recall        E11.8 School
(chat works)         (no K0 needed)         + tool dispatch      E11.9 Health
                                                                 E11.10 Transport
                                                                 E11.11 Integration
```

---

## End-to-End Boot Sequence (all milestones complete)

```powershell
# One command to boot everything:
.\scripts\boot_web.ps1 -FamilyConfig .\data\families\smith.json -WithK0 -Port 8765
```

Internal sequence:

```
1.  [boot_web.ps1]   Load .env (GOOGLE_API_KEY etc.)
2.  [boot_web.ps1]   Start: python -m scripts.pseudo_k0 --port 8090 --db ./data/pseudo_k0.db
3.  [pseudo_k0]      SQLiteK0Store initialized
4.  [pseudo_k0]      ConnectorHost registers: calendar, tasks, reminders, chores,
                       messaging, budget, school, health, transport
5.  [pseudo_k0]      FastAPI listening on :8090
6.  [boot_web.ps1]   Poll GET /k0/health → {available: true}  ✓
7.  [boot_web.ps1]   Set K0_ENDPOINT=http://localhost:8090
8.  [boot_web.ps1]   Start: python -m ui.web --port 8765 --family-config smith.json
9.  [ui.web]  KernelService._startup_tier1():
     S1  LocalBus + AsyncBusBridge + MailboxRouter
     S2  ModelHub (hub or test mode)
     S2.5 HumanInTheLoopService
     S2.6 SelfModelServiceBundle
     S2.6.5 SpaceDataSeeder.seed_self_model(bundle, smith_profile)  ← M13 L2
     S4  HttpBridgeClient(endpoint="http://localhost:8090")  ← M14
     S3  SharedFabric (with BridgeConnectorMCPTransport)  ← M11.E11.0
     S5  OrchestratorService
     S6  PlannerAgent
     S6b Cross-wire
     S7  Planner task
10. [ui.web]  KernelService.create_session("web-session-0"):
     P2  SessionStateManager
     P2.5 SpaceDataSeeder.seed_session(ssm, smith_profile, "alex_phone")  ← M13 L1
     P4  ConciergeRuntime
     P5  MemoryWriterService
11. [ui.web]  FastAPI + uvicorn listening on :8765
12. [Browser]        Open http://localhost:8765
13. [Browser]        WebSocket /ws connects → receives init message
14. [Browser]        Family sidebar shows: Alex ✓ Jordan ✓ Riley ✓ Nana Liz ✓
15. [User]           Types "What's on the calendar this week?"
16. [K1 Bus]         ConciergeRuntime → BridgeProvider → bridge.send_command("connector.execute")
17. [pseudo_k0]      POST /k0/connector.execute → CalendarHandler.list_events()
18. [K1 Bus]         Result flows back → response rendered in browser
19. [Browser]        Timeline panel shows tool_event: calendar_list_events dispatched → completed
```

---

## Scope Boundaries

**In scope for this plan:**

- Browser UI on production K1 kernel
- Smith family data seeding (extensible to any family via JSON)
- Pseudo-K0 with memory store + tool dispatch
- 8 native family tool domains, all routed via bridge
- `scripts/boot_web.ps1` as single entry point

**Out of scope:**

- Real K0 (`k0/`) distributed system — signature verification, WAL replication, SSE fan-out
- `HttpBridgeClient` retry/backoff reconnect (pseudo-K0 is always-up, local)
- HIL suspension manager (separate Epic 4.x)
- `_NullSSMShim` fix on ModelHub (separate K8 issue)
- UltraBERT model weights (use `--test-mode` without them)
- Multi-user session management (single session per server process; extend post-M14)
- External IFL adapters (Google Calendar import, Instacart — separate milestone)
- Real K0 ECDSA signature generation from K1 (pseudo-K0 skips verification)

---

## Summary Metrics

| Milestone | New Files | New Tests | Gate |
|---|---|---|---|
| M12 Web UI | ~12 | ~35 | Browser renders chat with FSM badge |
| M13 Family Data | ~5 | ~35 | Smith family in session beliefs + self-model |
| M14 Pseudo-K0 | ~8 | ~55 | memory.recall returns real data; `/k0/health` healthy |
| M15 Native Family Apps Foundation | ~45 | ~80 | 5 apps + foundation + LLM reasoning; SSE fan-out under 2s |
| **Total** | **~70** | **~205** | |

---

## Architecture Decision Records

### ADR-1 — UI Layer Lives Outside `k1/` (decided May 2026)

**Decision**: The entire web UI layer (M12 content: `app.py`, `coordinator.py`, `renderer.py`,
`static/`, `__main__.py`) moves from `k1/kernel/web/` to `ui/web/`. K1 is a pure runtime kernel
with no knowledge of FastAPI, WebSockets, or browser clients.

**Problem with current plan**: `k1/kernel/web/` creates a circular-concern boundary violation.
The kernel "contains" its own UI client. If a CLI client or mobile client is added later, they
would also have to live inside `k1/kernel/` — which is clearly wrong.

**New directory layout**:

```
familyos/           (workspace root)
├── k1/             ← pure kernel — no HTTP, no UI, no browser assets
│   ├── kernel/     ← bootstrap.py, service.py, session.py, adapters/
│   ├── concierge/  ← config, bus, builders
│   ├── selfmodel/  ← SpaceGraph layer (see ADR-2)
│   └── ...
├── ui/             ← ALL presentation layers
│   ├── web/        ← FastAPI + WebSocket + static assets (was k1/kernel/web/)
│   │   ├── __init__.py
│   │   ├── __main__.py      ← python -m ui.web [--port 8765]
│   │   ├── app.py           ← FastAPI application
│   │   ├── coordinator.py   ← UiCoordinator: wraps k1.kernel (uses k1 as library)
│   │   ├── renderer.py      ← WebSocketRenderer
│   │   └── static/          ← index.html, app.js, styles.css
│   ├── cli/                 ← future terminal client (python -m ui.cli)
│   └── voice/               ← future voice shell
├── verticals/
│   └── family/              ← FamilyProfile, SMITH_PROFILE, SpaceDataSeeder
│                               (was k1/family/ — see ADR-3)
└── scripts/
    └── pseudo_k0/           ← dev infrastructure, unchanged
```

**Boot command change**:

```powershell
# Before (wrong — UI inside kernel):
python -m k1.kernel.web --test-mode --port 8765

# After (correct — UI as separate package that uses k1):
python -m ui.web --test-mode --port 8765
```

**Coordinator rename**: `K1WebCoordinator` → `UiCoordinator`. The coordinator lives in `ui/web/`
and imports `k1.kernel.bootstrap.start_kernel` as an external library call. K1 has no import
back into `ui/`.

**K1 kernel contract**: `k1/kernel/bootstrap.py::start_kernel()` and `stop_kernel()` are the
only public API surface of the kernel. `ui/web/coordinator.py` calls these and nothing else.

**Impact on plan milestones**:

- M12 files move: `k1/kernel/web/` → `ui/web/`
- M12 imports update: `from k1.kernel.web.*` → `from ui.web.*`
- Test paths update: `tests/k1/kernel/web/` → `tests/ui/web/`
- `scripts/boot_web.ps1` launch command: `python -m k1.kernel.web` → `python -m ui.web`
- All other milestones (M13/M14/M15) are unaffected

**SchoolOS/HealthOS implication**: A SchoolOS deployment would have its own `ui/school_web/`
or `ui/school_mobile/` that also imports `k1.kernel.bootstrap.start_kernel` with a
`SchoolSpaceContext`. The kernel itself (k1) is reused unchanged.

---

### ADR-2 — Self-Model Is Domain-Agnostic: `FamilySelfModelSnapshot` → `SpaceGraphSnapshot` (decided May 2026)

**Decision**: The K1 self-model layer (projection store, ports, service) uses generic
`SpaceGraphSnapshot` / `ActorRef` / `ISelfSpacePort` terminology. Family-specific names live
only in `verticals/family/`.

**Problem with current code**:

```
k1/selfmodel/
  contracts/family_model.py   ← FamilyMemberRef, FamilySelfModelSnapshot
  ports/selffamily.py         ← ISelfFamilyPort.get_family_view()
  service/family_model.py     ← FamilyModelService, FAMILY_MODEL_WRITER_ID
  ports/projection_store.py   ← read_family(), write_family()
```

All of these have "family" in their name but the underlying concept is a **social graph for a
space** — universally applicable. A HealthOS would need `PatientCareTeamSnapshot` but the data
structure is identical: `(space_id, actors, directed_edges, routines)`.

**Rename map** (behaviour unchanged, only names change):

| Current (family-locked) | New (domain-neutral) |
|---|---|
| `FamilyMemberRef` | `ActorRef` |
| `RelationshipEdge` | `SpaceEdge` (fields unchanged: from_member, to_member, kind, weight) |
| `RoutineRef` | `RoutineRef` (no change needed — already neutral) |
| `FamilySelfModelSnapshot` | `SpaceGraphSnapshot` (field: `family_space_id` → `space_id`) |
| `ISelfFamilyPort` | `ISelfSpacePort` |
| `ISelfFamilyPort.get_family_view()` | `ISelfSpacePort.get_space_view()` |
| `IProjectionStorePort.read_family()` | `IProjectionStorePort.read_space()` |
| `IProjectionStorePort.write_family()` | `IProjectionStorePort.write_space()` |
| `FamilyModelService` | `SpaceGraphService` |
| `FAMILY_MODEL_WRITER_ID` | `SPACE_GRAPH_WRITER_ID` |
| `k1.concierge.config.kernel.selfmodel_family_space_id` | `selfmodel_space_id` |

**The five-layer actor model (`K1SelfModelSnapshot`) is already correct and unchanged**:

```python
class K1SelfModelSnapshot:
    actor_id: str       # "alex" | "patient_7" | "student_3" | "user_42"
    L1_core: dict       # identity facts — any human
    L2_identity: dict   # roles, credentials — any actor
    L3_pattern: dict    # preferences, habits, goals — any actor
    L4_context: dict    # RAM-only situational — any domain
    L5_state: dict      # RAM-only ephemeral — any domain
```

`GroundingCapsule` blocks (`self_block`, `preferences_block`, etc.) are also already neutral.
`ConstitutionSnapshot` + `AmendmentProposal` are already neutral (governance works for any domain).
No changes needed to these.

**What remains family-specific (correctly, in `verticals/family/`):**

```
verticals/family/
  profile.py           ← FamilyProfile — role taxonomy (parent/child/guardian/elder)
  smith.py             ← SMITH_PROFILE — default demo data
  seeder.py            ← SpaceDataSeeder — builds seed_memories from FamilyProfile
  acl_rules.py         ← family-specific VisibilityPolicy rules (dinner DND, work calendar, etc.)
```

**Domain comparison — all use the same `SpaceGraphSnapshot`**:

| Vertical | space_id | actor roles | edge kinds |
|---|---|---|---|
| FamilyOS | `family:smith` | parent/child/guardian/elder | parent_of, sibling_of, guardian_of |
| HealthOS | `clinic:mayo:ward_3` | patient/clinician/caregiver/admin | treating, caring_for, supervises |
| SchoolOS | `school:lincoln:class_5b` | student/teacher/parent/admin | enrolled_in, teaches, guardian_of |
| FinanceOS | `fund:blackrock:portfolio_x` | investor/manager/advisor/analyst | manages, advises, reviews |
| GovOS | `city:austin:district_7` | citizen/officer/official/auditor | represents, governs, audits |
| AgriOS | `farm:johnson:field_n40` | farmer/agronomist/supplier/buyer | operates, consults, supplies |

Each vertical writes its own `SpaceProfile` → `SpaceGraphSnapshot` seeder, its own
`VisibilityPolicy` rules, and its own `ConstitutionSnapshot` (consent model). The kernel
consumes only `SpaceGraphSnapshot`.

**`GroundingCapsule` domain extension**: The `household_block` in `GroundingCapsule.as_prompt_text()`
should be renamed to `space_graph_block` and populated from `SpaceGraphSnapshot`. For FamilyOS
it renders as a household summary; for HealthOS it renders as a care team summary. Same
machinery, different content.

**Impact on plan milestones**:

- M13: `SpaceDataSeeder.seed_space_projection()` now calls `store.write_space()` instead of
  `store.write_family()`, passes `SpaceGraphSnapshot` instead of `FamilySelfModelSnapshot`
- M13 tests: update import paths
- M14/M15: `KernelConfig.selfmodel_family_space_id` → `selfmodel_space_id`
- All `k1.selfmodel.*` internal files: rename only — zero logic changes

**Implementation order for this ADR**:

```
Step 1: Rename k1/selfmodel/contracts/family_model.py → space_graph.py
        — FamilyMemberRef → ActorRef
        — FamilySelfModelSnapshot → SpaceGraphSnapshot (field family_space_id → space_id)
Step 2: Rename k1/selfmodel/ports/selffamily.py → selfspace.py
        — ISelfFamilyPort → ISelfSpacePort
        — get_family_view() → get_space_view()
Step 3: Edit k1/selfmodel/ports/projection_store.py
        — read_family() → read_space()
        — write_family() → write_space()
Step 4: Rename k1/selfmodel/service/family_model.py → space_graph.py
        — FamilyModelService → SpaceGraphService
        — FAMILY_MODEL_WRITER_ID → SPACE_GRAPH_WRITER_ID
Step 5: Edit k1/concierge/config/kernel.py
        — selfmodel_family_space_id → selfmodel_space_id
Step 6: Edit k1/selfmodel/adapters/memory_projection_store.py
        — read_family → read_space, write_family → write_space
Step 7: Edit k1/selfmodel/adapters/sqlite_projection_store.py (same renames)
Step 8: Move k1/family/ → verticals/family/
        — Update imports in verticals/family/seeder.py to use SpaceGraphSnapshot
Step 9: Update all plan references in M13/M14/M15 sections to use new names
Step 10: Run tests: python -m pytest tests/k1/selfmodel/ -q --no-cov
```

---

### ADR-3 — Vertical Domain Data Belongs in `verticals/`, Not in `k1/` (decided May 2026)

**Decision**: `k1/family/` moves to `verticals/family/`. Any future vertical
(HealthOS, SchoolOS, FinanceOS) creates `verticals/health/`, `verticals/school/`, etc.
The `k1/` namespace is reserved for kernel infrastructure.

**Directory contract**:

```
k1/             ← kernel only — no domain knowledge, no family/health/school specifics
verticals/
  family/       ← FamilyProfile, SMITH_PROFILE, SpaceDataSeeder, family ACL rules
  health/       ← (future) PatientProfile, CareTeamSeeder, HIPAA ACL rules
  school/       ← (future) ClassroomProfile, ClassroomSeeder, FERPA ACL rules
  finance/      ← (future) OrgProfile, OrgSeeder, SEC-visibility ACL rules
```

**The single Protocol the kernel understands** (one new file, ~30 lines):

```python
# k1/kernel/contracts/space_context.py
from typing import Protocol, runtime_checkable, Any

@runtime_checkable
class SpaceContext(Protocol):
    """The only type the kernel accepts from any vertical."""
    space_id: str           # "family:smith" | "school:lincoln:5b" | "clinic:mayo:3"
    tenant_id: str
    actors: list[Any]       # list of objects with actor_id, role, display_name
    seed_memories: list[dict]
    session_config: dict
    preferred_language: str
```

`verticals/family/profile.FamilyProfile` implements `SpaceContext`.
`verticals/health/profile.CareTeamProfile` implements `SpaceContext`.
The kernel's `K1WebCoordinator` → `UiCoordinator` accepts `SpaceContext`, not `FamilyProfile`.

**Impact on plan milestones**:

- M12: `coordinator.py` slot `self.family_profile_obj: FamilyProfile` → `self.space_context: SpaceContext`
- M13: Move files `k1/family/*.py` → `verticals/family/*.py` (content unchanged)
- Import updates: `from k1.family.smith import SMITH_PROFILE` → `from verticals.family.smith import SMITH_PROFILE`
- All tests in `tests/k1/family/` → `tests/verticals/family/`
