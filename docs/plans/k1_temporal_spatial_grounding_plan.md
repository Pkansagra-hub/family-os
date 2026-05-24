# K1 Temporal / Spatial / Grounding Plan

Date: 2026-05-18
Owner: Kernel engineering
Branch: `feature/temporal-spatial-grounding` (long-lived)
Source whiteboard: [docs/whiteboard/k1_spatial_temporal_whiteboard.md](../whiteboard/k1_spatial_temporal_whiteboard.md)

## Scope And Non-Scope

In scope:

1. New kernel packages `k1.temporal`, `k1.spatial`, `k1.grounding`.
2. New kernel ports `temporal_port`, `spatial_port`, `grounding_port`, `device_context_port`.
3. New SessionState sections `temporal`, `spatial`, `place_registry`, `grounding`.
4. Concierge / Planner / Orchestrator / Fabric / Agent / Tool wiring.
5. Hard removal of every POC site listed under [Deprecation Inventory](#deprecation-inventory).
6. Domain-agnostic terminology across kernel code.
7. SessionState UI inspector updates for the four new sections.
8. MemoryWriter contract alignment for temporal/spatial metadata fields.
9. Three feature flags `k1.temporal.enabled`, `k1.spatial.enabled`, `k1.grounding.enabled`, default OFF until milestone success criteria pass, then default ON, removed in M6 cleanup epic.

Out of scope (explicit):

1. Vertex 429 / BackPool throttling fixes.
2. `date_calc` WASM runtime fix (mentioned as dependency only).
3. Anything in `poc/` directory — do not read, do not import, do not migrate. POC is dead.
4. Domain layer additions (FamilyOS, SchoolOS, EnterpriseOS). Verticals consume the kernel projections; they are not part of this plan.

## Kernel-Grade Domain-Agnostic Terminology

This is a kernel module. No vertical-specific words appear in code, types, events, section payloads, or prompts produced by these packages.

| Forbidden in kernel | Use instead | Notes |
| --- | --- | --- |
| `family`, `family_*`, `household`, `household_*` | `group_refs`, `group_id`, `group_kind` | Verticals map their group concept to `group_kind` (e.g. `"household"`, `"class"`, `"team"`, `"branch"`). |
| `member`, `Jordan`, `dad`, `mom` | `subject_ref`, `subject_id`, `subject_role` | Verticals map their actor concept. |
| `parent`, `child` | `role_refs` (list of role tags), `relationship_refs` | Roles are opaque tags emitted by the SelfModel/domain. |
| `school`, `home`, `office` (as enum) | `place_kind: str` (opaque tag from registry) | `place_kind` is an open vocabulary. Verticals seed it. |
| `bedtime`, `school day` (as enum) | `routine_id`, `routine_kind` | Routines are registry entries, not enum values. |
| `Denton`, hardcoded city | `place_registry.semantic_place` or unknown | No literal place strings in kernel code. |

The phrase `principal_id` is reserved for the active acting identity (already used by SelfModel). Temporal/spatial/grounding code consumes `principal_id` from SelfModel; it does not introduce a parallel identity model.

## Plan Format And Workflow

1. One long-lived branch: `feature/temporal-spatial-grounding`.
2. One PR per issue. PRs target the long-lived branch, not `main`. The branch merges to `main` only at milestone close after all milestone success criteria pass.
3. Three feature flags wired through `KernelConfig` in `k1/concierge/config/kernel.py`:
   - `k1.temporal.enabled`
   - `k1.spatial.enabled`
   - `k1.grounding.enabled`
   Default OFF until each module's milestone success criteria pass. When a flag is OFF, KernelService skips that Tier 1 bundle and the corresponding Tier 2 install; consumers must handle absence. When all three are stable for one milestone cycle, defaults flip to ON; the flag definitions are removed in M6 cleanup.
4. Per-issue acceptance:
   - All listed files exist with the responsibilities stated.
   - Listed Protocols have the listed methods with the listed signatures.
   - Listed dataclasses are frozen and have the listed fields.
   - Listed tests exist as files (test function naming is the implementer's choice). Implementer runs only the test files listed in the issue plus any direct callers they touched. They do NOT run `tests/k1/kernel/` or the full Fabric suite.
   - `git diff --check` is clean.
   - `pyproject.toml` typing / lint pass for the touched files.
5. Per-issue rollback: revert the PR. Because the long-lived branch is not merged until milestone close, single-PR revert is sufficient. Cross-package issues call out additional reverts.

## Trace Corrections From Code Audit

This plan is constrained by the live K1 kernel, not only by the whiteboard.

1. `KernelConfig` lives at `k1/concierge/config/kernel.py`; `k1/kernel/service.py` consumes it.
2. The live Tier 1 order is S1 Bus, S2 ModelHub, S2.5 HIL, S2.6 SelfModel, S4 Bridge, S3 Shared Fabric, S5 Orchestrator, S6 Planner, S6b Planner binding, S7 Planner task, S8 optional FamilyTools.
3. The canonical final insertion order is S2.7 Temporal, S2.8 Spatial, S2.9 Grounding. During M1.5, Grounding may be installed before Spatial exists by using a NullSpatial adapter, but M3 rewires Grounding after Spatial so the final aggregator consumes both temporal and spatial.
4. The canonical per-session order is P3.5 SelfModel, P3.6 Temporal, P3.7 Spatial, P3.8 Grounding, then P4 Concierge construction, P5 MemoryWriter construction, pre-start handle installs, and P6 `ConciergeRuntime.start()`.
5. Pure payload dataclasses live in package `types.py` files (`k1.temporal.types`, `k1.spatial.types`, `k1.grounding.types`). Kernel port files contain Protocols and import/re-export those types; they do not define duplicate dataclasses.
6. `DeviceContextSnapshot` is defined once in `k1.grounding.types` from M0 onward, even though the Grounding service implementation ships in M1.5.
7. The whiteboard's temporary `control.temporal_anchor` mirror is intentionally overridden by the user's hard-remove policy. The removal still occurs only after callers are migrated; there is no compatibility shim PR.
8. `beliefs_active.mentioned_location` is conversational evidence, not authoritative spatial state. It remains as a candidate source and is not removed from SessionState in this plan.

## Milestones

| ID | Name | Whiteboard phase |
| --- | --- | --- |
| M0 | Design Lock + Scaffolding | Phase 0 |
| M1 | k1.temporal Foundation | Phase 1 |
| M1.5 | k1.grounding Shell + Propagation | Phase 1.5 |
| M2 | Resolve Relative Dates Before Dispatch | Phase 2 |
| M3 | k1.spatial Foundation | Phase 3 |
| M4 | Fabric / Tool Contracts / Agent Leases | Phase 4 |
| M5 | Place Registry + Geofences + K0 Persistence | Phase 5 |
| M6 | K0 Memory + UI + MemoryWriter Schema + Final Cleanup | Phase 6 |

Each milestone has: goal, epics, issues, deprecation epic, success criteria, exit criteria.

## Deprecation Inventory

Every item below is **hard-removed** within the milestone listed. No shim period. Removal is a separate issue inside the milestone's deprecation epic. If callers exist outside this plan, the issue updates them in the same PR.

| ID | File / symbol | What | Removal milestone |
| --- | --- | --- | --- |
| D-01 | `k1/sessionstate/sections/temporal_context.py` | POC module, exports `TemporalAnchor` + `compute_temporal_anchor` | M1 (after `temporal` section ships) |
| D-02 | `k1/sessionstate/public_types.py` lines 27, 71, 91 | Re-exports of `TemporalAnchor`, `compute_temporal_anchor` | M1 |
| D-03 | `k1/sessionstate/sections/control.py` lines 367-370 | `_temporal_anchor: Optional[Dict[str, Any]] = None` field | M1 |
| D-04 | `k1/sessionstate/sections/control.py` lines 803-826 | `set_temporal_anchor()`, `get_temporal_anchor()`, anchor exposure in `get_metadata()` | M1 |
| D-05 | `k1/concierge/prompt/builder.py` lines 644-651 | `SECTION_SOURCE_MAP = {"temporal_context": "control"}` and POC comment | M1 |
| D-06 | `k1/concierge/prompt/builder.py` lines 77-185 | All 10 `SS_READ_CONFIGS` entries that read `temporal_context` (replace with `temporal` + `grounding`) | M1 (entries replaced); old entries removed in M1 deprecation epic |
| D-07 | `k1/concierge/prompt/builder.py` lines 584-620 | `_render_temporal_context_full()` including hardcoded `"Location: Denton, Texas"` line 619 | M1 |
| D-08 | `k1/concierge/prompt/builder.py` lines 622-640 | `_render_temporal_context_slim()` | M1 |
| D-09 | `k1/concierge/prompt/builder.py` ~lines 593, 629 | Lazy `compute_temporal_anchor` fallback inside renderers | M1 |
| D-10 | `k1/concierge/prompt/builder.py` line 664 entry | `SECTION_RENDERERS["temporal_context"]` | M1 |
| D-11 | `k1/concierge/prompt/builder.py` line 1154-1186 | `_build_now_block()` reading `control.get_temporal_anchor()` (M1 temporary typed `TemporalProjection`; M1.5 canonical `GroundingProjection`) | M1/M1.5 |
| D-12 | `k1/concierge/fsm/controller.py` line 140 | `from k1.sessionstate.public_types import compute_temporal_anchor` | M1 |
| D-13 | `k1/concierge/fsm/controller.py` lines 2160, 2170-2183 | `_write_session_context_to_ss()` POC anchor computation + write-elision `"temporal_anchor": True` key | M1 |
| D-14 | `k1/concierge/actors/front.py` lines 565-620 | `_build_family_context()` reading `persona._preferences["family"]["location"]` and `["timezone"]` | M3 (after spatial ships; replaced by grounding projection consumption) |
| D-16 | `k1/concierge/prompt/sections.py` `IDENTITY` block `TIME AWARENESS` paragraph | Hardcoded prompt text about reading current time from session state | M1 (replaced by `GroundingProjection`-rendered block) |
| D-17 | `k1/concierge/concierge_unified.mmd` lines 236-245, 961 | Diagram-only spatial/temporal/place nodes | M3 (replaced by real implementation diagrams in `architecture_diagrams/k1/`) |
| D-18 | `k1/planner/stages/expand_service.py` lines 506, 796-799 | `temporal = request.constraints.get("temporal", {})` ad-hoc string injection | M1.5 (replaced by typed `PlanRequest.grounding` field) |
| D-19 | `k1.temporal.enabled`, `k1.spatial.enabled`, `k1.grounding.enabled` feature flag definitions | Migration-only flags | M6 cleanup |
| D-20 | Three SessionState sections being created without canonical persistence path | Any standalone HOT-only behavior left over after M5 K0 Bridge integration | M6 cleanup |

Non-deprecation note: `k1/sessionstate/sections/beliefs_active.py` `mentioned_location` / `MentionedLocation` is retained. It is conversational evidence and a candidate source for the spatial resolver, not authoritative spatial state and not a removal target.

---

## M0: Design Lock And Scaffolding

Goal: lock canonical names, create the long-lived branch, add kernel-level scaffolding (empty packages, kernel port stub files, feature flag config), so M1+ can land on existing skeletons without touching dozens of import paths.

## M0 Epics

### Epic M0-E1: Repository Scaffolding

#### Issue M0-E1-I1: Create long-lived branch and plan reference

Motivation: keep all temporal/spatial/grounding work on one branch until M6 success.

Scope:

- Create branch `feature/temporal-spatial-grounding` off current `main`.
- Add `docs/plans/k1_temporal_spatial_grounding_plan.md` (this file) to the branch.
- Update `CHANGELOG.md` with a new `[Unreleased]` entry referencing this plan.

Wiring: none.

Acceptance criteria:

- Branch exists on origin.
- `docs/plans/k1_temporal_spatial_grounding_plan.md` exists.
- `CHANGELOG.md` entry exists.

Test files: none.

Rollback: delete branch.

Dependencies: none.

#### Issue M0-E1-I2: Feature flag config

Motivation: every cobbler must be able to gate new code behind a flag.

Scope (CREATE):

- Add `k1/concierge/config/kernel.py` `KernelConfig` fields — read the current `KernelConfig` style first; add three booleans:
  - `enable_temporal: bool = False`
  - `enable_grounding: bool = False`
  - `enable_spatial: bool = False`
- Add env var binding `K1_ENABLE_TEMPORAL`, `K1_ENABLE_GROUNDING`, `K1_ENABLE_SPATIAL`.
- Add log lines on KernelService startup that print each flag's resolved value.

Acceptance criteria:

- `KernelService` reads each flag exactly once at startup.
- Default values are `False`.
- Env var override works.

Test files: `tests/k1/kernel/test_config_temporal_spatial_grounding_flags.py`.

Rollback: revert PR.

Dependencies: M0-E1-I1.

### Epic M0-E2: Empty Kernel Port Files

#### Issue M0-E2-I1: Stub `k1/kernel/ports/temporal_port.py`

Motivation: downstream packages can import the Protocol name even before service code exists, avoiding circular-import refactors later.

Scope (CREATE):

- `k1/kernel/ports/temporal_port.py` containing only:
  - module docstring stating "kernel-visible Protocol for temporal service; see k1.temporal package".
  - `from typing import Protocol, runtime_checkable, Mapping, Any`.
  - Imports/re-exports `TemporalAnchor`, `TemporalWindow`, `ResolvedTemporalExpression`, `TemporalProjection`, and `TemporalTurnSnapshot` from `k1.temporal.types`.
  - `@runtime_checkable class ITemporalPort(Protocol): async def get_anchor(self, session_id: str) -> TemporalAnchor: ...` plus other methods from whiteboard §"Temporal Port" and §"Kernel-Visible Ports".
- Update `k1/kernel/ports/__init__.py` to re-export `ITemporalPort` and the three dataclasses.

Acceptance criteria:

- File imports cleanly with no other dependencies than stdlib.
- No service or adapter import statements.

Test files: `tests/k1/kernel/ports/test_temporal_port_protocol.py` (verifies Protocol shape with `isinstance(..., ITemporalPort)` over a minimal in-test fake).

Rollback: revert PR.

Dependencies: M0-E1-I1.

#### Issue M0-E2-I2: Stub `k1/kernel/ports/spatial_port.py`

Motivation: same as M0-E2-I1 for spatial.

Scope (CREATE):

- `k1/kernel/ports/spatial_port.py` containing imports/re-exports for `PlaceRef`, `LocationFix`, `SpatialContext`, `SpatialProjection`, `SpatialTurnSnapshot` from `k1.spatial.types`, and `@runtime_checkable class ISpatialPort(Protocol)` with methods from whiteboard §"Spatial Port" and §"Kernel-Visible Ports".
- Update `k1/kernel/ports/__init__.py` re-exports.

Acceptance criteria: same shape as M0-E2-I1.

Test files: `tests/k1/kernel/ports/test_spatial_port_protocol.py`.

Rollback: revert PR.

Dependencies: M0-E1-I1.

#### Issue M0-E2-I3: Stub `k1/kernel/ports/grounding_port.py`

Motivation: same as above for grounding.

Scope (CREATE):

- `k1/kernel/ports/grounding_port.py` containing imports/re-exports for `GroundingEnvelope`, `GroundingProjection`, `AgentGroundingLease`, `GroundingFreshness`, `GroundingSource`, `ConsumerScope` from `k1.grounding.types`, and `@runtime_checkable class IGroundingPort(Protocol)` with methods from whiteboard §"Kernel-Visible Ports".
- Update `k1/kernel/ports/__init__.py` re-exports.

Acceptance criteria: same shape.

Test files: `tests/k1/kernel/ports/test_grounding_port_protocol.py`.

Rollback: revert PR.

Dependencies: M0-E1-I1.

#### Issue M0-E2-I4: Stub `k1/kernel/ports/device_context_port.py`

Motivation: producer/reader Protocol for installed-device snapshots. Pure dataclass lives in `k1.grounding.types` from M0 onward; the kernel Protocol imports and re-exports it without creating a duplicate shape.

Scope (CREATE):

- `k1/kernel/ports/device_context_port.py` importing/re-exporting `DeviceContextSnapshot` from `k1.grounding.types`.
- `@runtime_checkable class IDeviceContextPort(Protocol)`: `async def get_snapshot(self, session_id: str, device_id: str, installation_id: str) -> DeviceContextSnapshot`, `async def update_snapshot(self, request: DeviceContextSnapshot) -> DeviceContextSnapshot`.
- Update `k1/kernel/ports/__init__.py` re-exports.

Acceptance criteria: same shape.

Test files: `tests/k1/kernel/ports/test_device_context_port_protocol.py`.

Rollback: revert PR.

Dependencies: M0-E1-I1.

Note: M0 creates only the pure `k1.grounding.types` dataclass. M1.5 creates the Grounding service around it.

### Epic M0-E3: Empty Package Skeletons

Create empty packages so imports compile during M1-M5 work.

#### Issue M0-E3-I1: `k1/temporal/` package skeleton

Scope (CREATE):

- `k1/temporal/__init__.py` (empty, with module docstring).
- `k1/temporal/config.py` (`@dataclass(frozen=True) class TemporalConfig` with default fields stubbed: TTLs, fallback timezone source order, locale defaults).
- `k1/temporal/types.py` with pure frozen dataclass stubs for `TemporalAnchor`, `TemporalWindow`, `ResolvedTemporalExpression`, `TemporalProjection`, and `TemporalTurnSnapshot`.
- `k1/temporal/errors.py` (`class TemporalError(Exception)` plus subclasses `InvalidTimezoneError`, `StaleAnchorError`, `AmbiguousExpressionError`, `UnavailableClockError`, `UnsupportedLocaleError`).
- `k1/temporal/constants.py` (canonical labels for standard windows, time-of-day buckets, weekdays, freshness states, timezone source names).
- Empty subdirs with `__init__.py`: `ports/`, `adapters/`, `service/`, `kernel/`, `tests/`.

Acceptance: package imports cleanly. Types are pure dataclasses only; no service or adapter imports.

Test files: `tests/k1/temporal/test_package_imports.py`.

Rollback: revert PR.

Dependencies: M0-E2-I1.

#### Issue M0-E3-I2: `k1/spatial/` package skeleton

Same shape, with `SpatialConfig`, `SpatialError` hierarchy, spatial constants, and `k1/spatial/types.py` pure dataclasses (`DeviceSurface`, `LocationFix`, `PlaceRef`, `Geofence`, `SpatialContext`, `SpatialProjection`, `PresenceRef`, `SpatialTurnSnapshot`).

Test files: `tests/k1/spatial/test_package_imports.py`.

Dependencies: M0-E2-I2.

#### Issue M0-E3-I3: `k1/grounding/` package skeleton

Same shape, with `GroundingConfig`, `GroundingError` hierarchy, grounding constants, and `k1/grounding/types.py` pure dataclasses (`DeviceContextSnapshot`, `GroundingEnvelope`, `GroundingProjection`, `AgentGroundingLease`, `GroundingFreshness`, `GroundingSource`, `ConsumerScope`).

Test files: `tests/k1/grounding/test_package_imports.py`.

Dependencies: M0-E2-I3, M0-E2-I4.

### Epic M0-E4: Architecture Diagrams Refresh

#### Issue M0-E4-I1: Add real architecture diagrams

Motivation: `concierge_unified.mmd` lines 236-245 contain spatial/temporal/place nodes that are diagram-only and never connected to code. Replace with real architecture diagrams under `architecture_diagrams/k1/`.

Scope (CREATE):

- `architecture_diagrams/k1/temporal_spatial_grounding/overview.mmd` — system overview matching whiteboard Diagram 2.
- `architecture_diagrams/k1/temporal_spatial_grounding/startup_slots.mmd` — Diagram 3 with actual S2.7/S2.8/S2.9 insertion.
- `architecture_diagrams/k1/temporal_spatial_grounding/session_slots.mmd` — Diagram 4 with P3.6/P3.7/P3.8.
- `architecture_diagrams/k1/temporal_spatial_grounding/runtime_turn.mmd` — Diagram 7.
- `architecture_diagrams/k1/temporal_spatial_grounding/agent_lease.mmd` — Diagram 8.

Acceptance: each diagram renders in VS Code Mermaid preview.

Test files: none.

Rollback: revert PR.

Dependencies: M0-E1-I1.

## M0 Success Criteria

1. `feature/temporal-spatial-grounding` branch exists with this plan committed.
2. Feature flag config wired and tested.
3. Four kernel port files exist with full Protocol definitions and dataclass shapes.
4. Three empty packages exist and import cleanly.
5. Architecture diagrams committed.

## M0 Exit Gate

`pytest tests/k1/kernel/ports/ tests/k1/temporal/test_package_imports.py tests/k1/spatial/test_package_imports.py tests/k1/grounding/test_package_imports.py tests/k1/kernel/test_config_temporal_spatial_grounding_flags.py -v` is green.

---

## M1: k1.temporal Foundation

Goal: ship the production-grade temporal kernel service end to end. Front, Back, Planner, and Fabric all consume the new `temporal` SessionState section. POC paths in deprecation IDs D-01..D-13, D-16 are removed.

## M1 Epics

### Epic M1-E1: `k1.temporal` Types And Events

#### Issue M1-E1-I1: `k1/temporal/types.py`

Scope (MODIFY):

- `k1/temporal/types.py` completes the M0 stubs and exports:
  - `TemporalAnchor` (canonical package dataclass; kernel ports import/re-export it and do not define it).
  - `TemporalWindow`, `ResolvedTemporalExpression`, `TemporalProjection`, `TemporalTurnSnapshot`.
  - Enums: `FreshnessState = Literal["live", "stale", "degraded", "unavailable"]`, `TimezoneSource = Literal["device", "spatial", "persona", "utc"]`, `TimeOfDay = Literal["early_morning", "morning", "midday", "afternoon", "evening", "night", "late_night"]`.
  - `TemporalProjection` with fields: `anchor: TemporalAnchor`, `windows: Mapping[str, TemporalWindow]`, `resolved_expressions: tuple[ResolvedTemporalExpression, ...]`, `consumer: str`, `freshness: FreshnessState`, `precision: str`.

Acceptance: all dataclasses `frozen=True`; no port or service imports.

Test files: `tests/k1/temporal/test_types.py`.

Dependencies: M0-E3-I1.

#### Issue M1-E1-I2: `k1/temporal/events.py`

Scope (CREATE):

- Event topic constants `TEMPORAL_ANCHOR_CREATED = "k1.temporal.anchor.created.v1"`, `TEMPORAL_ANCHOR_REFRESHED`, `TEMPORAL_EXPRESSION_RESOLVED`, `TEMPORAL_EXPRESSION_AMBIGUOUS`, `TEMPORAL_ANCHOR_STALE` (whiteboard §"Event Topics").
- Payload dataclasses for each (frozen).

Acceptance: event names match whiteboard exactly.

Test files: `tests/k1/temporal/test_events.py`.

Dependencies: M1-E1-I1.

#### Issue M1-E1-I3: `k1/temporal/serialization.py`

Scope (CREATE):

- `anchor_to_dict()`, `dict_to_anchor()`, `window_to_dict()`, `dict_to_window()`, `resolution_to_dict()`, `dict_to_resolution()`, `projection_to_dict()`, `dict_to_projection()`.
- Round-trip safe.

Acceptance: round-trip tests pass.

Test files: `tests/k1/temporal/test_serialization.py`.

Dependencies: M1-E1-I1.

### Epic M1-E2: `k1/temporal/ports/`

#### Issue M1-E2-I1: All temporal Protocol ports

Scope (CREATE):

- `k1/temporal/ports/clock_port.py` — `IClockPort` (`now_utc() -> str`, `monotonic_ms() -> int`).
- `k1/temporal/ports/device_context_port.py` — `ITemporalDeviceContextPort` wraps kernel `IDeviceContextPort` for temporal subset.
- `k1/temporal/ports/timezone_port.py` — `ITimezonePort` (`candidate_for_principal(principal_id: str) -> str | None`).
- `k1/temporal/ports/routine_port.py` — `IRoutinePort` (`get_window(routine_id: str, anchor: TemporalAnchor) -> TemporalWindow | None`, `list_routines() -> Sequence[RoutineRef]`).
- `k1/temporal/ports/state_port.py` — `ITemporalStatePort` (`write_section(session_id, payload) -> None`, `read_section(session_id) -> dict | None`).
- `k1/temporal/ports/event_port.py` — `ITemporalEventPort` (`publish(topic: str, payload: Mapping) -> None`).
- `k1/temporal/ports/id_port.py` — `ITemporalIdPort` (`new_anchor_id() -> str`, `new_window_id() -> str`, `new_resolution_id() -> str`).
- `k1/temporal/ports/metrics_port.py` — `ITemporalMetricsPort` (counters/timers, all no-op-safe).
- `k1/temporal/ports/policy_port.py` — `ITemporalPolicyPort` (`allow_routine(routine_id: str, consumer: str) -> bool`).
- `ports/__init__.py` re-exports all Protocols.

Acceptance: each Protocol is `@runtime_checkable`; method signatures use only stdlib + `k1.temporal.types`.

Test files: `tests/k1/temporal/ports/test_protocol_shapes.py`.

Dependencies: M1-E1-I1.

### Epic M1-E3: `k1/temporal/adapters/`

#### Issue M1-E3-I1: All temporal adapters

Scope (CREATE):

- `k1/temporal/adapters/system_clock_adapter.py` — `SystemClockAdapter` implements `IClockPort` via `datetime.now(timezone.utc)` and `time.monotonic_ns()/1_000_000`.
- `k1/temporal/adapters/device_context_adapter.py` — adapts kernel `IDeviceContextPort.get_snapshot()` to `ITemporalDeviceContextPort`; extracts timezone, locale, observed_at, clock_skew.
- `k1/temporal/adapters/persona_timezone_adapter.py` — reads `persona.get_all_preferences().get("timezone")` via injected reader. **No** dependency on `family` key — uses `principal_id` against persona record.
- `k1/temporal/adapters/spatial_timezone_adapter.py` — reads `spatial` section if present; returns `None` if `k1.spatial.enabled` is False or section is missing.
- `k1/temporal/adapters/session_state_adapter.py` — `TemporalStateAdapter` writes `temporal` section via `SessionStateManager`. **Does not** write `control.temporal_anchor` (per D-04 removal).
- `k1/temporal/adapters/event_bus_adapter.py` — publishes to session bus.
- `k1/temporal/adapters/null_routine_adapter.py` — returns `None`/empty for every routine call.
- `k1/temporal/adapters/selfmodel_routine_adapter.py` — reads routines via SelfModel handle if available.
- `k1/temporal/adapters/uuid_id_adapter.py` — `uuid.uuid4().hex` based ID generators.
- `k1/temporal/adapters/null_metrics_adapter.py` — no-op metrics.

Acceptance: each adapter file has one class implementing one Protocol.

Test files: `tests/k1/temporal/adapters/test_system_clock_adapter.py`, `tests/k1/temporal/adapters/test_session_state_adapter.py`.

Dependencies: M1-E2-I1.

### Epic M1-E4: `k1/temporal/service/`

#### Issue M1-E4-I1: Core resolvers and builders

Scope (CREATE) — one file per responsibility per whiteboard §"`k1/temporal/` File Map":

- `anchor_builder.py`, `timezone_resolver.py`, `locale_resolver.py`, `clock_skew_checker.py`, `window_builder.py`, `daylight_boundary.py`, `freshness_evaluator.py`.

Key constraints:

- `timezone_resolver.py`: source order is exactly **device → spatial → persona → UTC**. Each fallback recorded as `timezone_source`.
- `window_builder.py`: produces nine standard windows per whiteboard §"Temporal Windows Type" — `yesterday`, `today`, `tomorrow`, `this_week`, `next_week`, `this_weekend`, `next_weekend`, `this_month`, `next_month`. Uses `zoneinfo` (Python 3.9+ stdlib).
- `daylight_boundary.py`: handles DST spring-forward and fall-back. Windows are `[start_inclusive, end_exclusive)`.
- `freshness_evaluator.py`: returns `live` if anchor age < config TTL, `stale` if older but < 2× TTL, `degraded` if > 2× TTL, `unavailable` if clock unreadable.

Acceptance: all five resolver/builder modules deterministic given fixed `IClockPort`.

Test files: `tests/k1/temporal/test_anchor_builder.py`, `test_window_builder.py`, `test_dst_boundaries.py`, `test_freshness_evaluator.py`, `test_timezone_resolver.py`.

Dependencies: M1-E3-I1.

#### Issue M1-E4-I2: Expression resolution (no-regex rule)

Scope (CREATE):

- `expression_candidates.py` — accepts typed candidate spans/phrases. **No prompt scraping.** Inputs come from Front dispatch or task params as structured objects.
- `phrase_catalog.py` — curated phrase catalog by locale: `{locale: {phrase: token_object}}`. English-US starter set: `today`, `tomorrow`, `yesterday`, `tonight`, `this morning`, `this afternoon`, `this evening`, `this weekend`, `next weekend`, `next Monday` (Tue/Wed/Thu/Fri/Sat/Sun), `last Monday`, `by Friday`, `in two days`, `in three weeks`, `next week`, `this week`, `next month`.
- `temporal_tokens.py` — `@dataclass(frozen=True)` token types: `WeekdayToken`, `OffsetToken`, `OrdinalToken`, `DayPartToken`, `DeadlineToken`, `RoutineToken`.
- `relative_day_rules.py` — typed rule classes per whiteboard.
- `weekday_rules.py` — `NextWeekdayRule`, `ByWeekdayRule`, etc.
- `offset_rules.py` — `InNUnitsRule`, `LastNUnitsRule`.
- `routine_window_resolver.py` — looks up routine windows via `IRoutinePort`.
- `ambiguity_resolver.py` — emits `needs_clarification=True` with reason.
- `expression_resolver.py` — orchestrates candidate selection → rule execution → routine lookup → confidence scoring → `ResolvedTemporalExpression`.

**No regular expressions** in any file. If a phrase isn't in the catalog or doesn't tokenize cleanly, the resolver returns `ambiguous`.

Acceptance: every standard phrase resolves; unknown phrases return `ambiguous`.

Test files: `tests/k1/temporal/test_expression_resolver.py`, `test_phrase_catalog.py`, `test_routine_windows.py`.

Dependencies: M1-E4-I1.

#### Issue M1-E4-I3: Projection + renderer + emitter + top-level service

Scope (CREATE):

- `projection_builder.py` — builds `TemporalProjection` variants for `front`, `back`, `planner`, `fabric`, `agent`, `tool`, `memory` consumers.
- `projection_renderer.py` — renders compact prompt blocks from `TemporalProjection` only. Two renderers: `render_now_block(projection)` and `render_execution_block(projection)`.
- `event_emitter.py` — converts service outcomes to events through `ITemporalEventPort`.
- `temporal_service.py` — top-level API: `refresh_turn(session_id)`, `get_anchor(session_id)`, `get_windows(session_id)`, `resolve_expression(session_id, candidate)`, `build_projection(session_id, consumer)`.
- `health.py` — health snapshot per whiteboard §"Health Shape".

Acceptance: `temporal_service.py` exposes the exact methods used by `ITemporalPort`.

Test files: `tests/k1/temporal/test_projection_builder.py`, `test_projection_renderer.py`, `test_temporal_service.py`.

Dependencies: M1-E4-I2.

### Epic M1-E5: Factory and kernel wiring

#### Issue M1-E5-I1: `k1/temporal/factory.py`

Scope (CREATE):

- `class TemporalFactory` with four static methods per whiteboard §"Pattern-Matched Service Design":
  - `create_standalone(config=None) -> TemporalServiceBundle`
  - `create_for_testing(config=None, **overrides) -> tuple[TemporalServiceBundle, dict]`
  - `create_with_ports(*, clock_port, event_port, state_port, device_context_port, timezone_port, routine_port, id_port, metrics_port, policy_port, config=None) -> TemporalServiceBundle`
  - `create_production(*, ...same...) -> TemporalServiceBundle`
- Validates config, validates Protocol satisfaction (`isinstance(..., IXPort)`), rejects duplicate port identities.
- Wiring order matches whiteboard §"Temporal Factory Wiring Order".

Acceptance: each factory entry returns a working bundle; duplicate-port rejection works.

Test files: `tests/k1/temporal/test_factory_wiring.py`.

Dependencies: M1-E4-I3.

#### Issue M1-E5-I2: `k1/temporal/kernel/`

Scope (CREATE):

- `k1/temporal/kernel/bootstrap.py` — `@dataclass(frozen=True) class TemporalServiceBundle` with `service`, `renderer`, `config`, `health`, `shutdown`. `def build_temporal_bundle(...) -> TemporalServiceBundle` calls `TemporalFactory.create_production(...)`.
- `k1/temporal/kernel/handle.py` — `class TemporalHandle` with fields `session_id`, `principal_id`, `device_id`, `installation_id`, `bundle`, `state_adapter`. Methods: `async refresh_turn(user_text_candidates=None) -> TemporalTurnSnapshot`, `async get_projection(consumer: str) -> TemporalProjection`, `install_into_session() -> None`, `uninstall_from_session() -> None`. `def build_temporal_handle(bundle, session_id, principal_id, device_id, installation_id) -> TemporalHandle`.
- `k1/temporal/kernel/session_binding.py` — immutable binding data.

Acceptance: `TemporalHandle` implements `ITemporalPort` structurally.

Test files: `tests/k1/temporal/kernel/test_bundle.py`, `test_handle.py`.

Dependencies: M1-E5-I1.

### Epic M1-E6: SessionState `temporal` section

#### Issue M1-E6-I1: Create `k1/sessionstate/sections/temporal.py`

Scope (CREATE):

- `class TemporalSection` HOT, never-evict during active session.
- Fields: `anchor: dict | None`, `windows: dict[str, dict]`, `resolved_expressions: list[dict]`, `last_turn_id: str | None`, `stale_after_ms: int`, `provenance: list[dict]`.
- Methods: `set_anchor(anchor_dict)`, `get_anchor()`, `set_windows(windows_dict)`, `get_windows()`, `set_resolutions(list)`, `get_resolutions()`, `clear_for_new_turn()`, `get_size_bytes()`.
- Follows existing section patterns from `control.py` (FlatBuffer-ready, JSON for now per project convention).

Scope (MODIFY):

- `k1/sessionstate/sections/__init__.py` — add `TemporalSection` export.
- `k1/sessionstate/tiers/hot.py` — instantiate `TemporalSection` in the HOT `_sections` dict under canonical name `"temporal"`.
- `k1/sessionstate/sizetracker.py` — add `"temporal"` to `HOT_SECTIONS`, `ALL_SECTIONS`, and `SECTION_BUDGETS`.
- `k1/sessionstate/manager.py` / `factory.py` — update only if existing tier composition requires explicit section metadata.

Acceptance: section exists with same API surface as other HOT sections; persists/restores via existing storage adapter.

Test files: `tests/k1/sessionstate/sections/test_temporal_section.py`, `tests/k1/sessionstate/test_temporal_registration.py`.

Dependencies: M1-E5-I2.

### Epic M1-E7: KernelService Tier 1 + Tier 2 install

#### Issue M1-E7-I1: KernelService S2.7 Temporal slot

Scope (MODIFY):

- `k1/kernel/service.py`:
  - Add `self._temporal_bundle: TemporalServiceBundle | None = None`.
  - In `_startup_tier1()` insert S2.7 slot between S2.6 (SelfModel) and S4 (Bridge) — only when `config.enable_temporal` is True:

    ```python
    if config.enable_temporal:
        self._temporal_bundle = build_temporal_bundle(
            clock_port=SystemClockAdapter(),
            event_port=...,
            state_port=...,
            device_context_port=self._device_context_port,
            timezone_port=PersonaTimezoneAdapter(...),
            routine_port=NullRoutineAdapter(),
            id_port=UuidIdAdapter(),
            metrics_port=NullMetricsAdapter(),
            policy_port=SelfModelPolicyAdapter(self._self_model_bundle) if self._self_model_bundle else NullPolicyAdapter(),
            config=TemporalConfig(),
        )
    ```

  - Wire bundle into `_shutdown_tier1()` to call `self._temporal_bundle.shutdown()` after SelfModel teardown.
  - Update `health()` output to include `temporal` key.

Acceptance: KernelService starts cleanly with `enable_temporal=True` and `enable_temporal=False`.

Test files: `tests/k1/kernel/test_service_temporal_tier1.py`.

Dependencies: M1-E6-I1.

#### Issue M1-E7-I2: KernelService P3.6 TemporalHandle install

Scope (MODIFY):

- `k1/kernel/service.py` `_create_session_tier2()`:
  - Insert P3.6 slot between P3.5 (SelfModel handle) and P4 (Concierge) — only when `config.enable_temporal` and `self._temporal_bundle is not None`:

    ```python
    temporal_handle = build_temporal_handle(
        bundle=self._temporal_bundle,
        session_id=session_id,
        principal_id=principal_id,
        device_id=device_id,
        installation_id=installation_id,
    )
    temporal_handle.install_into_session()  # writes initial TemporalSection
    ```

  - Add `temporal_handle` to session record.
  - Pass `temporal_handle` to `ConciergeFactory.create_with_ports(temporal_port=temporal_handle, ...)`.
  - In `_destroy_session()`, call `temporal_handle.uninstall_from_session()` after Concierge stop.

Acceptance: session create succeeds; `TemporalSection` is populated before Concierge starts.

Test files: `tests/k1/kernel/test_service_temporal_tier2.py`.

Dependencies: M1-E7-I1, M1-E6-I1.

### Epic M1-E8: Concierge wiring

#### Issue M1-E8-I1: `ConciergeRuntime.set_temporal(handle)` pre-start guard

Scope (MODIFY):

- `k1/concierge/session.py` — add `_temporal: Any = None` field, `temporal` property, `set_temporal(handle)` method following exact pattern of `set_self_model()` lines 270-285. Pre-start guard `if self._started: raise RuntimeError("set_temporal() must be called before start()")`.
- `k1/concierge/factory.py` — extend `PortBundle` or `create_with_ports(...)` to accept `temporal_port`. Pass into `ConciergeRuntime` before `start()`.
- Mailbox consumer in `session.py` passes `temporal=self._temporal` into `front_handler` and `route_back_envelope`.
- `k1/concierge/CONTRACT.md` updated.

Acceptance: pre-start guard works; setting after start raises; concierge starts cleanly with `temporal=None` (flag off).

Test files: `tests/k1/concierge/test_runtime_set_temporal.py`.

Dependencies: M1-E7-I2.

#### Issue M1-E8-I2: FSM controller — replace POC anchor write with TemporalHandle refresh

Scope (MODIFY):

- `k1/concierge/fsm/controller.py`:
  - **Delete** import `from k1.sessionstate.public_types import compute_temporal_anchor` (line 140) — keep `PrivacyBand` import.
  - **Delete** lines 2170-2183 (POC anchor compute + `control.set_temporal_anchor`).
  - **Delete** line 2160 `"temporal_anchor": True` key from `_write_elision_gate.evaluate(...)` input dict.
  - **Replace** with: `if self._temporal_port is not None: await self._temporal_port.refresh_turn(session_id, user_text_candidates=[])`.
  - Add `_temporal_port` field plumbed via `set_temporal()`.

Scope (DELETE): D-12, D-13.

Acceptance: FSM no longer imports POC utility; controller compiles; turn flow writes `temporal` section via handle.

Test files: `tests/k1/concierge/fsm/test_controller_temporal_refresh.py`.

Dependencies: M1-E8-I1.

#### Issue M1-E8-I3: Prompt builder — remove POC renderers, add temporary TemporalProjection bridge

Scope (MODIFY):

- `k1/concierge/prompt/builder.py`:
  - **Delete** lines 644-651 `SECTION_SOURCE_MAP` (D-05).
  - **Delete** lines 584-620 `_render_temporal_context_full` (D-07).
  - **Delete** lines 622-640 `_render_temporal_context_slim` (D-08).
  - **Delete** lazy `compute_temporal_anchor` calls (~593, ~629) (D-09).
  - **Delete** line 664 `SECTION_RENDERERS["temporal_context"]` entry (D-10).
  - **Replace** all 10 `SS_READ_CONFIGS` entries: swap `SSReadConfig("temporal_context", "full"|"slim")` for `SSReadConfig("temporal", "full"|"slim")`. This is a temporary M1 bridge so the Front is not blind before M1.5 grounding lands.
  - Add `_render_temporal_full(section, cfg)` and `_render_temporal_slim(section, cfg)` that construct a typed `TemporalProjection` through `TemporalHandle`/`TemporalProjectionBuilder`, then render with `k1.temporal.service.projection_renderer`. They must not read raw section dictionaries directly, hardcode city names, or lazily call `compute_temporal_anchor`.
  - **Replace** `_build_now_block(ss)` (line 1154) to use the same temporary typed `TemporalProjection` path. M1.5 deletes this bridge and routes NOW/PLACE/EXECUTION blocks through `k1.grounding.service.prompt_block_renderer`.

Scope (DELETE): D-05, D-06, D-07, D-08, D-09, D-10, D-11.

Acceptance: prompt builds; `Denton` string is gone; `tests/k1/concierge/prompt/test_builder_temporal.py` exercises new renderers.

Test files: `tests/k1/concierge/prompt/test_builder_temporal.py`.

Dependencies: M1-E8-I2, M1-E6-I1.

#### Issue M1-E8-I4: Prompt sections IDENTITY block update

Scope (MODIFY):

- `k1/concierge/prompt/sections.py`:
  - **Delete** the `TIME AWARENESS:` paragraph inside `IDENTITY` (D-16).
  - **Add** a one-line reference: `Current time and place: see GROUNDING blocks rendered by the kernel.` (No machine-readable behavior — purely instructional.)

Acceptance: existing prompt-block tests still pass with updated text.

Test files: `tests/k1/concierge/prompt/test_sections.py`.

Dependencies: M1-E8-I3.

### Epic M1-E9: Planner typed temporal constraint

#### Issue M1-E9-I1: Replace ad-hoc string injection with structured constraint

Scope (MODIFY):

- `k1/planner/stages/expand_service.py`:
  - **Delete** line 796-799 ad-hoc `now = temporal.get("now")` → `"Current time: {now}"` injection (D-18 partial; final removal is M1.5-E4-I2 once typed `PlanRequest.grounding` exists).
  - **Replace** with structured read of `request.constraints.get("temporal", {})` as `dict` containing `anchor_id`, `now_utc`, `timezone`, `today`, `tomorrow`, `resolved_expressions`. Build a multi-line constraint block listing those fields.
  - Update line 506 `query_session_context` tool description: replace `"'beliefs_active', 'persona', 'temporal', 'control', 'history_recent'."` with `"'beliefs_active', 'persona', 'temporal', 'history_recent'."` (drop `control`, since temporal anchor moves out of control).

Acceptance: Planner still works; expanded constraint block contains anchor_id and today/tomorrow ISO ranges.

Test files: `tests/k1/planner/test_expand_service_temporal.py`.

Dependencies: M1-E8-I3.

### Epic M1-E10: Tool contracts (date_calc)

#### Issue M1-E10-I1: `date_calc.yaml` requires temporal

Scope (MODIFY):

- `k1/contracts/tools/date_calc.yaml`:
  - Add `required_context: [temporal]`.

Acceptance: `ContextBuilder` injects `temporal` section into `date_calc` execution context.

Test files: `tests/k1/fabric/test_date_calc_context.py`.

Dependencies: M1-E6-I1.

### Epic M1-E11: M1 Deprecation Epic (hard removal)

#### Issue M1-E11-I1: Remove `temporal_context.py` and POC public_types exports

Scope (DELETE / MODIFY):

- **Delete** file `k1/sessionstate/sections/temporal_context.py` (D-01).
- **Modify** `k1/sessionstate/public_types.py`:
  - Remove line 27 docstring entry "5. Temporal context...".
  - Remove line 71 `from k1.sessionstate.sections.temporal_context import TemporalAnchor, compute_temporal_anchor`.
  - Remove line 91 `"compute_temporal_anchor"` from `__all__`.
  - Remove `TemporalAnchor` from `__all__`.
- Search workspace for any remaining `from k1.sessionstate.public_types import compute_temporal_anchor` or `TemporalAnchor` usages — there must be zero outside `k1.temporal`. If any are found, update or document why.

Acceptance: `git grep "compute_temporal_anchor"` returns only docs and tests under `k1/temporal/`. Whole codebase compiles.

Test files: `tests/k1/sessionstate/test_public_types_no_poc.py`.

Dependencies: M1-E8-I3.

#### Issue M1-E11-I2: Remove `_temporal_anchor` from `control.py`

Scope (MODIFY):

- `k1/sessionstate/sections/control.py`:
  - **Delete** lines 367-370 (`_temporal_anchor` field) (D-03).
  - **Delete** lines 803-826 (`set_temporal_anchor`, `get_temporal_anchor`, `get_metadata` exposure) (D-04).
  - Remove `_temporal_anchor` from `get_size_bytes()` if listed.
  - Update FlatBuffer schema `k1/contracts/flatbuffers/sessionstate/control_section.fbs` to drop the field. Regenerate via `k1/sessionstate/scripts/compile_flatbuffers.py`.
- Search workspace for any caller of `control.set_temporal_anchor` or `control.get_temporal_anchor` — must be zero.

Acceptance: `git grep "temporal_anchor"` returns only references in `k1.temporal`, tests, and historical CHANGELOG.

Test files: `tests/k1/sessionstate/sections/test_control_no_temporal.py`.

Dependencies: M1-E11-I1.

## M1 Success Criteria

1. `k1.temporal` package exists with full file layout per whiteboard §"`k1/temporal/` File Map".
2. `TemporalSection` is a canonical HOT section.
3. KernelService starts the bundle at S2.7 and installs the handle at P3.6.
4. Front prompt builds with `temporal` section; no `Denton` string anywhere.
5. Back prompt receives typed temporal projection through the temporary M1 bridge; M1.5 moves Back to `GroundingProjection`.
6. Planner receives structured temporal constraint dict including ISO `today`/`tomorrow`.
7. All D-01..D-13, D-16 deprecations executed.

## M1 Exit Gate

Run only:

```bash
pytest tests/k1/temporal/ tests/k1/sessionstate/sections/test_temporal_section.py tests/k1/sessionstate/sections/test_control_no_temporal.py tests/k1/sessionstate/test_public_types_no_poc.py tests/k1/sessionstate/test_temporal_registration.py tests/k1/kernel/test_service_temporal_tier1.py tests/k1/kernel/test_service_temporal_tier2.py tests/k1/concierge/test_runtime_set_temporal.py tests/k1/concierge/fsm/test_controller_temporal_refresh.py tests/k1/concierge/prompt/test_builder_temporal.py tests/k1/concierge/prompt/test_sections.py tests/k1/planner/test_expand_service_temporal.py tests/k1/fabric/test_date_calc_context.py -v
```

Flip `k1.temporal.enabled` default to `True` only when this passes.

---

## M1.5: k1.grounding Shell And Propagation

Goal: production grounding envelope path. After M1.5, temporal travels through `GroundingEnvelope` / `GroundingProjection` / `AgentGroundingLease`, not directly through `temporal` section reads. Spatial fields exist on the envelope but always say `unknown` until M3.

## M1.5 Epics

### Epic M1.5-E1: Complete `k1.grounding` runtime types

#### Issue M1.5-E1-I1: Complete `k1/grounding/types.py`

Scope (MODIFY):

- `k1/grounding/types.py` — fill out the M0 stubs for `GroundingEnvelope`, `GroundingProjection`, `GroundingFreshness`, `GroundingSource`, `ConsumerScope`, and `AgentGroundingLease` per whiteboard.
- Keep `DeviceContextSnapshot` in this file as the single canonical definition created in M0.
- Type aliases: `Consumer = Literal["front", "back", "planner", "fabric", "agent", "tool", "memory"]`.

Scope (VERIFY):

- `k1/kernel/ports/device_context_port.py` still imports/re-exports `DeviceContextSnapshot` from `k1.grounding.types` and contains no local dataclass.

Acceptance: only one definition of `DeviceContextSnapshot` in codebase.

Test files: `tests/k1/grounding/test_types.py`.

Dependencies: M1-E5-I2.

#### Issue M1.5-E1-I2: `k1/grounding/events.py` + `errors.py` + `constants.py` + `serialization.py`

Scope (CREATE): per whiteboard §"`k1/grounding/` File Map" — events `k1.grounding.envelope.created.v1`, etc.; errors `ProjectionDeniedError`, `StaleEnvelopeError`, etc.; constants for consumer names, lease statuses, redaction reason codes.

Test files: `tests/k1/grounding/test_events.py`.

Dependencies: M1.5-E1-I1.

### Epic M1.5-E2: `k1/grounding/ports/` + `adapters/`

#### Issue M1.5-E2-I1: All grounding ports

Scope (CREATE): per whiteboard file map — `temporal_port.py` (`IGroundingTemporalPort`), `spatial_port.py` (`IGroundingSpatialPort` — returns unknown until M3), `identity_port.py`, `policy_port.py`, `state_port.py`, `event_port.py`, `id_port.py`, `metrics_port.py`.

Acceptance: Protocols `@runtime_checkable`.

Test files: `tests/k1/grounding/ports/test_protocol_shapes.py`.

Dependencies: M1.5-E1-I2.

#### Issue M1.5-E2-I2: All grounding adapters

Scope (CREATE): `temporal_handle_adapter.py` (wraps `TemporalHandle` → `IGroundingTemporalPort`), `spatial_handle_adapter.py` (stub returning `unknown`/`hidden` until M3), `selfmodel_identity_adapter.py`, `selfmodel_policy_adapter.py`, `session_state_adapter.py` (writes `grounding` section), `event_bus_adapter.py`, `uuid_id_adapter.py`, `null_metrics_adapter.py`.

Acceptance: adapters compile and pass their unit tests.

Test files: `tests/k1/grounding/adapters/test_temporal_handle_adapter.py`, `test_spatial_handle_adapter_stub.py`.

Dependencies: M1.5-E2-I1.

### Epic M1.5-E3: `k1/grounding/service/` + factory + kernel

#### Issue M1.5-E3-I1: Service modules

Scope (CREATE) — one file per responsibility per whiteboard file map:

- `envelope_builder.py`, `projection_policy.py`, `projection_builder.py`, `lease_builder.py`, `context_snapshot_builder.py`, `reference_context_builder.py`, `invocation_metadata.py`, `propagation.py`, `prompt_block_renderer.py`, `stale_envelope_checker.py`, `event_emitter.py`, `grounding_service.py`, `health.py`.

Key constraints:

- `prompt_block_renderer.py` is the only file that renders `== NOW ==`, `== PLACE ==`, `== EXECUTION GROUNDING ==`, `== PLANNING GROUNDING ==` blocks from a `GroundingProjection`. Concierge prompt builder calls this; it does not read raw sections.
- `lease_builder.py` always populates `spatial` field on lease, even when status is `unknown`.
- `propagation.py` defines exact field names: `grounding_envelope_id`, `temporal_anchor_id`, `spatial_context_id`, `resolved_temporal_refs`, `resolved_spatial_refs`.

Test files: `tests/k1/grounding/test_envelope_builder.py`, `test_projection_policy.py`, `test_projection_builder.py`, `test_lease_builder.py`, `test_propagation.py`, `test_prompt_block_renderer.py`, `test_grounding_service.py`.

Dependencies: M1.5-E2-I2.

#### Issue M1.5-E3-I2: Factory + kernel bundle/handle

Scope (CREATE): `factory.py` (four entrypoints same shape as Temporal), `kernel/bootstrap.py` (`GroundingServiceBundle`, `build_grounding_bundle()`), `kernel/handle.py` (`GroundingHandle`, `install_into_session()`/`uninstall_from_session()`), `kernel/session_binding.py`.

Test files: `tests/k1/grounding/test_factory_wiring.py`, `tests/k1/grounding/kernel/test_bundle.py`, `test_handle.py`.

Dependencies: M1.5-E3-I1.

### Epic M1.5-E4: SessionState `grounding` section + kernel wiring + propagation

#### Issue M1.5-E4-I1: `k1/sessionstate/sections/grounding.py`

Scope (CREATE):

- `class GroundingSection` HOT lightweight; fields: `latest_envelope_id`, `latest_projection_ids: dict[consumer, id]`, `source_temporal_section_version`, `source_spatial_section_version`, `redaction_summary: list[str]`.
- **No raw location payload.**
- Methods: `set_envelope_metadata(...)`, `get_envelope_metadata()`, `clear_for_new_turn()`, `get_size_bytes()`.

Scope (MODIFY):

- `k1/sessionstate/sections/__init__.py` export.
- `k1/sessionstate/tiers/hot.py` register as HOT.
- `k1/sessionstate/sizetracker.py` add to `HOT_SECTIONS`, `ALL_SECTIONS`, and `SECTION_BUDGETS`.
- `k1/sessionstate/manager.py` / `factory.py` update only if existing tier composition requires explicit section metadata.

Test files: `tests/k1/sessionstate/sections/test_grounding_section.py`.

Dependencies: M1.5-E3-I2.

#### Issue M1.5-E4-I2: KernelService transitional S2.9 GroundingBundle + P3.8 GroundingHandle

Scope (MODIFY):

- `k1/kernel/service.py`:
  - Add `self._grounding_bundle` field.
  - `_startup_tier1()` insert transitional S2.9 Grounding after S4 Bridge and before S3 Shared Fabric when `config.enable_grounding`. M1.5 uses `NullGroundingSpatialPort` because S2.8 Spatial is reserved but not implemented until M3.
  - `_create_session_tier2()` insert transitional P3.8 Grounding after P3.6 Temporal and before P4 Concierge when `config.enable_grounding`. M1.5 uses a null/unknown spatial view.
  - `ConciergeFactory.create_with_ports(grounding_port=grounding_handle, ...)`.
  - Pass `grounding_handle` into `OrchestratorFactory` and `PlannerFactory` (S5/S6) so they can read `IGroundingPort` for plan requests.

Test files: `tests/k1/kernel/test_service_grounding_tier1.py`, `test_service_grounding_tier2.py`.

Dependencies: M1.5-E4-I1.

#### Issue M1.5-E4-I3: `ConciergeRuntime.set_grounding(handle)` + prompt builder routing

Scope (MODIFY):

- `k1/concierge/session.py`: add `set_grounding(handle)` (mirrors `set_self_model`/`set_temporal` pattern).
- `k1/concierge/factory.py`: extend `create_with_ports(grounding_port=...)`.
- `k1/concierge/prompt/builder.py`:
  - **Replace** `_render_temporal_full/_render_temporal_slim` calls with `await grounding.get_projection(consumer="front")` → `prompt_block_renderer.render_now_block(projection)`.
  - The renderer now reads from `GroundingProjection`, not `TemporalSection` directly.
  - `SS_READ_CONFIGS` no longer needs to read `temporal` directly for prompt construction; instead the builder calls `grounding.get_projection(consumer="front")` once at Stage 9.5 (same place SelfModel capsule is fetched).
  - Keep `SSReadConfig("temporal", ...)` only if Stage 8 inspector UI needs section visibility; otherwise remove.

Test files: `tests/k1/concierge/test_runtime_set_grounding.py`, `tests/k1/concierge/prompt/test_builder_grounding.py`.

Dependencies: M1.5-E4-I2.

#### Issue M1.5-E4-I4: Task dispatch propagation

Scope (MODIFY):

- `k1/concierge/task/dispatch.py`:
  - Add fields on `TaskDispatch`: `grounding_envelope_id: str | None = None`, `temporal_anchor_id: str | None = None`, `spatial_context_id: str | None = None`, `resolved_temporal_refs: dict | None = None`, `resolved_spatial_refs: dict | None = None`.
  - Mirror into `reference_context` for compatibility during M1.5/M2 only.
- `k1/concierge/actors/front.py`: front_handler reads `GroundingProjection` for Front consumer; on dispatch, populates the five new fields from the envelope ID and resolved refs.
- `k1/concierge/actors/back.py`: back actor reads dispatch fields and exposes them to `back_prompt` via execution grounding block (rendered by `prompt_block_renderer.render_execution_block(projection)`).

Test files: `tests/k1/concierge/task/test_dispatch_grounding_fields.py`, `tests/k1/concierge/actors/test_back_execution_grounding.py`.

Dependencies: M1.5-E4-I3.

#### Issue M1.5-E4-I5: Planner typed grounding constraint

Scope (MODIFY):

- `k1/orchestrator/types.py`:
  - Add `grounding: dict | None = None` to `PlanRequest`. (Use `dict` rather than `GroundingEnvelope` import to avoid `k1.grounding` dep on `k1.orchestrator`; serialization in/out via `k1.grounding.serialization`.) Document field shape in docstring.
  - Add `grounding: dict | None = None` to `TaskEnvelope`, or add explicit fields `grounding_envelope_id`, `temporal_anchor_id`, `spatial_context_id`, `resolved_temporal_refs`, and `resolved_spatial_refs` if that matches the existing envelope serializer better. Do not leave grounding only in freeform `context`.
- `k1/orchestrator/orchestration/orchestrator_service.py`: preserves `grounding` field across plan request build.
- `k1/planner/stages/expand_service.py`:
  - **Delete** D-18 line 796-799 ad-hoc string injection.
  - **Replace** with: read `request.grounding` (or `request.constraints["temporal"]` as compat fallback during migration), call `prompt_block_renderer.render_planning_block(...)` against typed projection.
- `k1/planner/stages/sketch_service.py`, `validate_service.py`: same projection access pattern.

Test files: `tests/k1/orchestrator/test_plan_request_grounding.py`, `tests/k1/planner/test_expand_service_grounding.py`.

Dependencies: M1.5-E4-I4.

### Epic M1.5-E5: M1.5 Deprecation Epic

#### Issue M1.5-E5-I1: Remove ad-hoc temporal constraint injection

Scope (MODIFY): finalize D-18 — remove `request.constraints.get("temporal")` fallback path in Planner stages once `request.grounding` is the canonical source.

Test files: `tests/k1/planner/test_no_constraint_temporal_fallback.py`.

Dependencies: M1.5-E4-I5.

## M1.5 Success Criteria

1. `k1.grounding` package exists with full file map.
2. `GroundingSection` registered.
3. KernelService transitional S2.9 + P3.8 grounding wired with null spatial input.
4. Front prompt renders from `GroundingProjection`.
5. Back prompt renders `== EXECUTION GROUNDING ==` from `GroundingProjection`.
6. `TaskDispatch` carries five new grounding fields.
7. `PlanRequest.grounding` is the typed source; old `constraints["temporal"]` path removed.
8. All envelope/projection/lease unit tests green.

## M1.5 Exit Gate

```bash
pytest tests/k1/grounding/ tests/k1/sessionstate/sections/test_grounding_section.py tests/k1/kernel/test_service_grounding_tier1.py tests/k1/kernel/test_service_grounding_tier2.py tests/k1/concierge/test_runtime_set_grounding.py tests/k1/concierge/prompt/test_builder_grounding.py tests/k1/concierge/task/test_dispatch_grounding_fields.py tests/k1/concierge/actors/test_back_execution_grounding.py tests/k1/orchestrator/test_plan_request_grounding.py tests/k1/planner/test_expand_service_grounding.py tests/k1/planner/test_no_constraint_temporal_fallback.py -v
```

Flip `k1.grounding.enabled` default to `True` when green.

---

## M2: Resolve Relative Dates Before Dispatch

Goal: Front resolves common relative-date expressions before Back ever sees them. Back never needs `date_calc` for `today`/`tomorrow`/`next Monday`/etc.

## M2 Epics

### Epic M2-E1: Front candidate extraction

#### Issue M2-E1-I1: Front extracts typed candidates from user turn

Scope (MODIFY):

- `k1/concierge/actors/front.py`: after Front LLM produces a dispatch, before `TaskDispatch` is sent, run `temporal.expression_candidates.extract_from_dispatch(dispatch)` to find candidate phrases in dispatch params and `reference_context`. Each candidate is a typed object (`CandidateSpan` from `k1/temporal/types.py`), **never** a raw regex hit.
- Resolved expressions go into `dispatch.resolved_temporal_refs`.
- If a candidate is ambiguous, Front either asks clarification (via HIL) or marks `dispatch.requires_temporal_clarification = True` (carry through).

Test files: `tests/k1/concierge/actors/test_front_resolve_relative_dates.py`.

Dependencies: M1.5-E4-I5.

### Epic M2-E2: Back consumes resolved refs first

#### Issue M2-E2-I1: Back prefers resolved windows over tool calls

Scope (MODIFY):

- `k1/concierge/actors/back.py`: when building Back tool-call context, expose `dispatch.resolved_temporal_refs` as a typed field consumed by the ReAct prompt template.
- `k1/concierge/prompt/back_prompt.py`: extend `build_back_prompt()` signature to accept `resolved_temporal_refs`. Render them in `== EXECUTION GROUNDING ==`.
- Back tool policy: if a tool requires a date param and `resolved_temporal_refs` contains the answer, Back's ReAct prompt is instructed to use it directly and skip `date_calc`.

Test files: `tests/k1/concierge/actors/test_back_uses_resolved_refs.py`, `tests/k1/concierge/prompt/test_back_prompt_grounding.py`.

Dependencies: M2-E1-I1.

## M2 Success Criteria

1. Golden test: `What does subject_ref have tomorrow?` produces dispatch with `tomorrow` resolved to ISO window.
2. Back does not invoke `date_calc` when resolved window is present.
3. Ambiguous expressions are explicitly marked, not silently guessed.

## M2 Exit Gate

```bash
pytest tests/k1/concierge/actors/test_front_resolve_relative_dates.py tests/k1/concierge/actors/test_back_uses_resolved_refs.py tests/k1/concierge/prompt/test_back_prompt_grounding.py -v
```

## M0-M2 Implementation Context For M3

This section is the handoff snapshot for the uncommitted work completed through
M2. Scope is the temporal/spatial/grounding plan plus the device-context ingress
needed to feed temporal grounding from the browser/runtime. It intentionally does
not describe unrelated HIL, WEAVE, BackPool, UI polish, log, or SQLite sidecar
changes that are also present in the working tree.

### M0 Implemented: Design Lock, Flags, Ports, Scaffolds

Purpose: establish the branch-local architecture contract, guarded flags, kernel
ports, package skeletons, and diagrams before introducing runtime behavior.

- `docs/plans/k1_temporal_spatial_grounding_plan.md` - this milestone plan and
  issue checklist. Current section should be treated as the M3 context anchor.
- `architecture_diagrams/k1/temporal_spatial_grounding/overview.mmd` - end-to-end
  temporal, spatial, grounding overview matching the whiteboard lanes.
- `architecture_diagrams/k1/temporal_spatial_grounding/startup_slots.mmd` -
  documents S2.7/S2.8/S2.9 startup slot placement.
- `architecture_diagrams/k1/temporal_spatial_grounding/session_slots.mmd` -
  documents P3.6/P3.7/P3.8 session handle placement.
- `architecture_diagrams/k1/temporal_spatial_grounding/runtime_turn.mmd` -
  documents per-turn refresh/projection flow.
- `architecture_diagrams/k1/temporal_spatial_grounding/agent_lease.mmd` -
  documents grounding lease ownership and propagation.
- `k1/concierge/config/kernel.py` - adds `enable_temporal`,
  `enable_grounding`, and `enable_spatial` booleans, defaulting OFF.
- `tests/k1/kernel/test_config_temporal_spatial_grounding_flags.py` - verifies
  the three feature flags default OFF and can be overridden from config/env.
- `k1/kernel/ports/temporal_port.py` - defines `ITemporalPort` and re-exports
  temporal public types for kernel consumers.
- `k1/kernel/ports/grounding_port.py` - defines `IGroundingPort` and re-exports
  grounding public types.
- `k1/kernel/ports/spatial_port.py` - defines `ISpatialPort` and re-exports
  spatial public types.
- `k1/kernel/ports/device_context_port.py` - defines `IDeviceContextPort` and
  re-exports the canonical `DeviceContextSnapshot`.
- `k1/kernel/ports/__init__.py` - re-exports the four new kernel Protocols.
- `k1/kernel/adapters/device_context.py` - adds
  `InMemoryDeviceContextPort`, the process-local latest-device snapshot store
  used by temporal timezone resolution.
- `tests/k1/kernel/ports/test_temporal_port_protocol.py` - protocol-shape test
  for `ITemporalPort`.
- `tests/k1/kernel/ports/test_grounding_port_protocol.py` - protocol-shape test
  for `IGroundingPort`.
- `tests/k1/kernel/ports/test_spatial_port_protocol.py` - protocol-shape test
  for `ISpatialPort`.
- `tests/k1/kernel/ports/test_device_context_port_protocol.py` - protocol-shape
  test for `IDeviceContextPort`.
- `k1/temporal/__init__.py`, `k1/temporal/config.py`,
  `k1/temporal/types.py`, `k1/temporal/errors.py`,
  `k1/temporal/constants.py` - temporal package scaffold later completed in M1.
- `k1/grounding/__init__.py`, `k1/grounding/config.py`,
  `k1/grounding/types.py`, `k1/grounding/errors.py`,
  `k1/grounding/constants.py` - grounding package scaffold later completed in
  M1.5; this package owns `DeviceContextSnapshot`.
- `k1/spatial/__init__.py`, `k1/spatial/config.py`, `k1/spatial/types.py`,
  `k1/spatial/errors.py`, `k1/spatial/constants.py` - spatial scaffold only;
  M3 must still complete runtime types, events, ports, adapters, and service.
- `tests/k1/temporal/test_package_imports.py`,
  `tests/k1/grounding/test_package_imports.py`,
  `tests/k1/spatial/test_package_imports.py` - import-cleanliness coverage for
  the three new packages.

### M1 Implemented: k1.temporal Foundation

Purpose: replace the old POC temporal anchor with a kernel-owned temporal
service, turn-scoped anchors/windows, typed expression resolution, projections,
SessionState storage, and Concierge/Planner consumption.

- `k1/temporal/types.py` - completes frozen public dataclasses:
  `TemporalAnchor`, `TemporalWindow`, `ResolvedTemporalExpression`,
  `TemporalProjection`, `TemporalTurnSnapshot`, and candidate/freshness/source
  literals.
- `k1/temporal/events.py` - defines temporal event topics and payload dataclasses
  for anchor creation/refresh/stale, expression resolution, and projection use.
- `k1/temporal/serialization.py` - provides round-trip dict conversion for
  temporal anchors, windows, resolutions, projections, and turn snapshots.
- `tests/k1/temporal/test_types.py`, `tests/k1/temporal/test_events.py`,
  `tests/k1/temporal/test_serialization.py` - cover M1 temporal type/event
  contracts and serialization.
- `k1/temporal/ports/clock_port.py`,
  `k1/temporal/ports/device_context_port.py`,
  `k1/temporal/ports/timezone_port.py`,
  `k1/temporal/ports/routine_port.py`,
  `k1/temporal/ports/state_port.py`,
  `k1/temporal/ports/event_port.py`,
  `k1/temporal/ports/id_port.py`,
  `k1/temporal/ports/metrics_port.py`,
  `k1/temporal/ports/policy_port.py`, `k1/temporal/ports/__init__.py` - nine
  runtime-checkable temporal Protocols and public exports.
- `tests/k1/temporal/ports/test_protocol_shapes.py` - validates the temporal
  port Protocol surface with lightweight fakes.
- `k1/temporal/adapters/system_clock_adapter.py` - production clock adapter.
- `k1/temporal/adapters/device_context_adapter.py` - adapts the kernel device
  context port to temporal timezone/locale inputs.
- `k1/temporal/adapters/persona_timezone_adapter.py` - reads persona/family
  timezone as a fallback source.
- `k1/temporal/adapters/spatial_timezone_adapter.py` - spatial timezone shim;
  returns absent/none until M3 spatial is real.
- `k1/temporal/adapters/session_state_adapter.py` - writes temporal anchors,
  windows, and resolutions into the HOT temporal SessionState section.
- `k1/temporal/adapters/event_bus_adapter.py` - publishes temporal events onto
  the session bus.
- `k1/temporal/adapters/null_routine_adapter.py` - no-op routine source.
- `k1/temporal/adapters/selfmodel_routine_adapter.py` - routine source through
  SelfModel when available.
- `k1/temporal/adapters/uuid_id_adapter.py` - anchor/projection/resolution ID
  generator.
- `k1/temporal/adapters/null_metrics_adapter.py` - no-op temporal metrics port.
- `k1/temporal/adapters/allow_all_policy_adapter.py` - permissive policy adapter
  for initial service wiring.
- `tests/k1/temporal/adapters/test_system_clock_adapter.py`,
  `tests/k1/temporal/adapters/test_session_state_adapter.py`,
  `tests/k1/temporal/adapters/test_event_bus_adapter.py`,
  `tests/k1/temporal/adapters/test_timezone_adapters.py` - adapter coverage.
- `k1/temporal/service/anchor_builder.py` - builds turn anchors from clock,
  timezone, locale, device, and freshness inputs.
- `k1/temporal/service/timezone_resolver.py` - resolves timezone in
  device -> spatial -> persona -> UTC order.
- `k1/temporal/service/locale_resolver.py` - resolves locale for anchor context.
- `k1/temporal/service/clock_skew_checker.py` - detects skew between device and
  kernel clocks.
- `k1/temporal/service/window_builder.py` - builds the standard temporal windows
  using `zoneinfo`.
- `k1/temporal/service/daylight_boundary.py` - handles DST spring-forward and
  fall-back boundary cases.
- `k1/temporal/service/freshness_evaluator.py` - classifies live/stale/degraded
  temporal freshness.
- `k1/temporal/service/expression_candidates.py` - typed candidate extraction
  surface used by M2 dispatch resolution; no regex parsing at the callsite.
- `k1/temporal/service/phrase_catalog.py` - locale-keyed phrase/token catalog.
- `k1/temporal/service/temporal_tokens.py` - token dataclasses for weekday,
  offset, routine, and relative-day rules.
- `k1/temporal/service/relative_day_rules.py`,
  `k1/temporal/service/weekday_rules.py`,
  `k1/temporal/service/offset_rules.py` - deterministic temporal rule engines.
- `k1/temporal/service/routine_window_resolver.py` - resolves routine-named
  windows through `IRoutinePort`.
- `k1/temporal/service/ambiguity_resolver.py` - marks ambiguous expressions for
  clarification rather than guessing.
- `k1/temporal/service/expression_resolver.py` - orchestrates candidate -> rule
  -> routine -> confidence -> `ResolvedTemporalExpression`.
- `k1/temporal/service/projection_builder.py` - builds per-consumer
  `TemporalProjection` objects.
- `k1/temporal/service/projection_renderer.py` - renders temporal prompt blocks
  for direct temporal consumers.
- `k1/temporal/service/event_emitter.py` - emits temporal service lifecycle and
  resolution events.
- `k1/temporal/service/temporal_service.py` - top-level temporal API:
  `refresh_turn`, `get_anchor`, `resolve_expression`, `build_projection`.
- `k1/temporal/service/health.py` - temporal service health snapshot.
- `tests/k1/temporal/service/test_anchor_builder.py`,
  `tests/k1/temporal/service/test_window_builder.py`,
  `tests/k1/temporal/service/test_timezone_resolver.py`,
  `tests/k1/temporal/service/test_expression_resolver.py`,
  `tests/k1/temporal/service/test_projection_builder.py`,
  `tests/k1/temporal/service/test_temporal_service.py` - service coverage.
- `k1/temporal/factory.py` - factory entrypoints for standalone, testing,
  explicit-port, and production temporal service construction.
- `k1/temporal/kernel/bootstrap.py` - `TemporalServiceBundle` and
  `build_temporal_bundle()`.
- `k1/temporal/kernel/handle.py` - `TemporalHandle` implementing the kernel
  temporal port and session install/uninstall lifecycle.
- `k1/temporal/kernel/session_binding.py` - immutable per-session temporal
  binding data.
- `tests/k1/temporal/test_factory_wiring.py`,
  `tests/k1/temporal/kernel/test_bundle.py`,
  `tests/k1/temporal/kernel/test_handle.py` - factory/bundle/handle coverage.
- `k1/sessionstate/sections/temporal.py` - HOT `TemporalSection` storing the
  current anchor, windows, resolutions, provenance, and turn metadata.
- `k1/sessionstate/sections/__init__.py` - exports `TemporalSection`.
- `k1/sessionstate/tiers/hot.py` - registers the HOT `temporal` section.
- `k1/sessionstate/sizetracker.py` - adds temporal to section accounting and
  budgets.
- `tests/k1/sessionstate/sections/test_temporal_section.py`,
  `tests/k1/sessionstate/test_temporal_registration.py` - SessionState temporal
  coverage.
- `k1/kernel/service.py` - adds temporal bundle storage, S2.7 startup bundle
  construction, P3.6 per-session `TemporalHandle` installation, health reporting,
  shutdown cleanup, and device-context port ownership.
- `k1/concierge/session.py` - adds `set_temporal()` pre-start guard and forwards
  the handle into Front and Back actor routing.
- `k1/concierge/factory.py` - accepts `temporal_port` and installs it into the
  Concierge runtime.
- `k1/concierge/fsm/controller.py` - replaces the old inline POC temporal-anchor
  computation path with `temporal_port.refresh_turn(...)` for user turns.
- `k1/concierge/prompt/builder.py` - removes the old POC temporal renderer path
  and routes temporal context through typed projections.
- `k1/concierge/prompt/sections.py` - adds the grounding protocol text used by
  projection-based prompt blocks.
- `tests/k1/concierge/test_runtime_set_temporal.py`,
  `tests/k1/concierge/test_front_temporal_session_id.py`,
  `tests/k1/concierge/test_bus_temporal_topics.py`,
  `tests/k1/concierge/prompt/test_builder_temporal.py` - Concierge temporal
  wiring and prompt coverage.
- `k1/planner/stages/expand_service.py` - migrates planning time context away
  from ad-hoc string injection toward structured temporal/grounding constraints.
- `tests/k1/planner/test_expand_service_temporal.py` - verifies structured
  temporal planning constraint content.
- `k1/contracts/tools/date_calc.yaml` - declares `required_context: [temporal]`.
- `tests/k1/fabric/test_date_calc_context.py` - verifies Fabric context builder
  injects the temporal section for `date_calc`.
- `k1/sessionstate/sections/temporal_context.py` - deleted; old POC anchor module
  is removed.
- `k1/sessionstate/public_types.py` - removes POC temporal anchor re-exports.
- `k1/sessionstate/sections/control.py` - removes control-section temporal anchor
  field/API.
- `tests/k1/sessionstate/test_public_types_no_poc.py`,
  `tests/k1/sessionstate/sections/test_control_no_temporal.py` - regression
  coverage for the POC removal.

### M1.5 Implemented: k1.grounding Shell And Propagation

Purpose: create the canonical grounding layer that composes temporal and spatial
state, even while spatial remains `unknown` until M3, and propagate grounding IDs
and projections across Front, Back, Orchestrator, Planner, and prompts.

- `k1/grounding/types.py` - completes frozen grounding dataclasses:
  `DeviceContextSnapshot`, `GroundingEnvelope`, `GroundingProjection`,
  `AgentGroundingLease`, `GroundingFreshness`, `GroundingSource`, and
  `ConsumerScope`.
- `k1/grounding/events.py` - defines grounding event topics and payloads.
- `k1/grounding/errors.py` - grounding error hierarchy, including projection and
  stale-envelope failures.
- `k1/grounding/constants.py` - consumer names, propagation field names, lease
  status constants, and redaction reason constants.
- `k1/grounding/serialization.py` - round-trip conversion for envelopes,
  projections, leases, and snapshots.
- `k1/grounding/__init__.py` - public package exports.
- `tests/k1/grounding/test_package_imports.py`,
  `tests/k1/grounding/test_m15_runtime.py` - package and M1.5 runtime coverage.
- `k1/grounding/ports/temporal_port.py`,
  `k1/grounding/ports/spatial_port.py`,
  `k1/grounding/ports/identity_port.py`,
  `k1/grounding/ports/policy_port.py`,
  `k1/grounding/ports/state_port.py`,
  `k1/grounding/ports/event_port.py`,
  `k1/grounding/ports/id_port.py`,
  `k1/grounding/ports/metrics_port.py`, `k1/grounding/ports/__init__.py` -
  grounding port layer.
- `k1/grounding/adapters/temporal_handle_adapter.py` - wraps `TemporalHandle` for
  grounding service consumption.
- `k1/grounding/adapters/spatial_handle_adapter.py` - null/unknown spatial
  adapter used until M3 installs real spatial.
- `k1/grounding/adapters/selfmodel_identity_adapter.py` - identity source from
  SelfModel.
- `k1/grounding/adapters/selfmodel_policy_adapter.py` - grounding policy source
  from SelfModel.
- `k1/grounding/adapters/session_state_adapter.py` - persists grounding metadata
  into SessionState.
- `k1/grounding/adapters/event_bus_adapter.py` - publishes grounding events.
- `k1/grounding/adapters/uuid_id_adapter.py` - grounding ID generation.
- `k1/grounding/adapters/null_metrics_adapter.py` - no-op grounding metrics.
- `k1/grounding/service/envelope_builder.py` - builds `GroundingEnvelope` from
  temporal plus current/null spatial state.
- `k1/grounding/service/projection_policy.py` - consumer-scoped projection policy.
- `k1/grounding/service/projection_builder.py` - creates per-consumer
  `GroundingProjection` objects.
- `k1/grounding/service/lease_builder.py` - creates `AgentGroundingLease`, always
  carrying a spatial field even when status is `unknown`.
- `k1/grounding/service/context_snapshot_builder.py` - assembles source context
  snapshots for grounding.
- `k1/grounding/service/reference_context_builder.py` - derives task
  `reference_context["grounding"]` payloads.
- `k1/grounding/service/invocation_metadata.py` - builds tool/model invocation
  grounding metadata.
- `k1/grounding/service/propagation.py` - canonical propagation field builder
  for `grounding_envelope_id`, `temporal_anchor_id`, `spatial_context_id`, and
  resolved refs.
- `k1/grounding/service/prompt_block_renderer.py` - single renderer for
  `== NOW ==`, `== PLACE ==`, `== EXECUTION GROUNDING ==`, and
  `== PLANNING GROUNDING ==` blocks.
- `k1/grounding/service/stale_envelope_checker.py` - detects stale grounding
  envelopes.
- `k1/grounding/service/event_emitter.py` - emits grounding lifecycle events.
- `k1/grounding/service/grounding_service.py` - top-level grounding service API.
- `k1/grounding/service/health.py` - grounding service health snapshot.
- `k1/grounding/factory.py` - factory entrypoints matching temporal.
- `k1/grounding/kernel/bootstrap.py` - `GroundingServiceBundle` and
  `build_grounding_bundle()`.
- `k1/grounding/kernel/handle.py` - `GroundingHandle` with session
  install/uninstall and projection methods.
- `k1/grounding/kernel/session_binding.py` - immutable per-session grounding
  binding data.
- `k1/sessionstate/sections/grounding.py` - HOT `GroundingSection` storing
  envelope/projection IDs, section-version links, and redaction summary only; no
  raw location payload.
- `k1/sessionstate/sections/__init__.py`, `k1/sessionstate/tiers/hot.py`,
  `k1/sessionstate/sizetracker.py` - register grounding in HOT SessionState and
  accounting.
- `tests/k1/sessionstate/sections/test_grounding_section.py` - grounding section
  coverage.
- `k1/kernel/service.py` - adds S2.9 grounding bundle construction using
  `NullGroundingSpatialPort`, P3.8 per-session `GroundingHandle` installation,
  health reporting, and shutdown cleanup.
- `tests/k1/kernel/test_service_grounding_tier1.py`,
  `tests/k1/kernel/test_service_grounding_tier2.py` - kernel tier coverage for
  grounding bundle and handle wiring.
- `k1/concierge/session.py` - adds `set_grounding()` pre-start guard and forwards
  grounding handle into Front and Back processing.
- `k1/concierge/factory.py` - accepts `grounding_port` and installs it into the
  runtime.
- `k1/concierge/prompt/builder.py` - accepts `grounding_projection` and routes
  Front prompt live blocks through `prompt_block_renderer`.
- `tests/k1/concierge/test_runtime_set_grounding.py`,
  `tests/k1/concierge/prompt/test_builder_grounding.py` - runtime guard and
  Front prompt grounding coverage.
- `k1/concierge/task/dispatch.py` - extends `TaskDispatch` with
  `grounding_envelope_id`, `temporal_anchor_id`, `spatial_context_id`,
  `resolved_temporal_refs`, `resolved_spatial_refs`, and
  `requires_temporal_clarification`; serializes/deserializes those fields.
- `tests/k1/concierge/task/test_dispatch_grounding_fields.py`,
  `tests/k1/concierge/test_grounding_dispatch_contract.py` - dispatch contract
  coverage.
- `k1/concierge/actors/front.py` - refreshes/builds Front grounding projections,
  writes propagation metadata into dispatch payloads and `reference_context`, and
  prepares the field path that M2 uses for resolved temporal refs.
- `k1/concierge/actors/back.py` - reads task grounding data, falls back to live
  Back projection if needed, and renders execution grounding through the shared
  grounding renderer.
- `tests/k1/concierge/actors/test_back_execution_grounding.py` - Back execution
  grounding block coverage.
- `k1/concierge/prompt/back_prompt.py` - accepts execution grounding content and
  supports typed resolved refs in the Back prompt.
- `k1/orchestrator/types.py` - adds optional `grounding` payloads to
  `TaskEnvelope` and `PlanRequest` with serialization support.
- `k1/orchestrator/orchestration/orchestrator_service.py` - carries grounding
  from task envelopes into planner requests, with compatibility fallback from
  task context.
- `tests/k1/orchestrator/test_plan_request_grounding.py` - orchestrator grounding
  round-trip/pass-through coverage.
- `k1/planner/stages/expand_service.py` - renders planning grounding from
  `request.grounding` via `dict_to_projection()` and
  `render_planning_grounding_block()`; removes the old temporal-constraint
  fallback path.
- `tests/k1/planner/test_expand_service_grounding.py`,
  `tests/k1/planner/test_planner_grounding_contract.py`,
  `tests/k1/planner/test_no_constraint_temporal_fallback.py` - planner grounding
  contract and fallback-removal coverage.

### M2 Implemented: Resolve Relative Dates Before Dispatch

Purpose: Front resolves relative dates while it still has fresh temporal and
grounding context, then Back consumes those typed windows directly instead of
spending another tool/LLM step to rediscover `tomorrow`, `next Friday`, etc.

- `k1/temporal/types.py` - adds/uses typed candidate span and resolved expression
  shapes needed by dispatch resolution.
- `k1/temporal/service/expression_candidates.py` - provides
  `extract_from_dispatch(dispatch_payload)` to pull typed candidates from dispatch
  params and reference context.
- `k1/concierge/actors/front.py` - after LLM `dispatch_task`, extracts temporal
  candidates, calls `temporal.resolve_expression(...)`, writes
  `resolved_temporal_refs`, and sets `requires_temporal_clarification` for
  ambiguous candidates before publishing the task dispatch.
- `k1/concierge/task/dispatch.py` - carries resolved temporal refs and the
  clarification flag through `TaskDispatch` serialization.
- `k1/concierge/fsm/controller.py` - preserves dispatch grounding/resolved-ref
  metadata while routing task envelopes onward.
- `k1/concierge/orchestrator/routing.py` - includes grounding and resolved-ref
  fields when translating Concierge task dispatch into orchestrator-facing work.
- `k1/concierge/actors/back.py` - exposes `dispatch.resolved_temporal_refs` to
  Back prompt construction and the execution grounding block.
- `k1/concierge/prompt/back_prompt.py` - renders
  `resolved_temporal_refs_typed:` under `== EXECUTION GROUNDING ==` and instructs
  Back to treat those refs as authoritative, skipping `date_calc` for already
  resolved windows.
- `tests/k1/concierge/actors/test_front_resolve_relative_dates.py` - golden
  coverage for resolving `tomorrow` before dispatch and marking ambiguous
  expressions.
- `tests/k1/concierge/actors/test_back_uses_resolved_refs.py` - verifies Back
  prompt receives typed resolved refs.
- `tests/k1/concierge/prompt/test_back_prompt_grounding.py` - verifies Back
  prompt merges resolved refs into execution grounding and carries the
  clarification flag.

### Device Context Ingress Implemented During M0-M2 Work

Purpose: make browser-local timezone/device observations available to the kernel
so temporal anchors are not UTC-only when the user is in a local family context.

- `ui/web/static/app.js` - computes browser/family timezone, locale, observed UTC,
  offset, device surface, and wall-clock metadata via `_browserDeviceContext()`;
  sends it with user messages and uses the display timezone for UI timestamps.
- `ui/web/app.py` - records `device_context` messages and records device context
  before forwarding user messages to the coordinator/runtime.
- `ui/web/coordinator.py` - normalizes browser context, falls back to family
  timezone, builds `DeviceContextSnapshot`, and writes it to
  `service.device_context_port.update_snapshot(...)`.
- `k1/kernel/service.py` - owns the `InMemoryDeviceContextPort` and passes a
  temporal `DeviceContextAdapter` into the temporal bundle.
- `tests/ui/web/test_device_context.py` - verifies coordinator writes browser
  device snapshots and falls back to family timezone.
- `tests/ui/web/test_app.py` - verifies web message handling records device
  context before dispatch.

### Carry-Forward Notes Before Starting M3

- `k1/spatial/` is still a scaffold. M3 must fill spatial runtime types,
  serialization, events, ports, adapters, service, SessionState section, kernel
  handle, and tests. Existing grounding uses the null/unknown spatial adapter.
- M3 should replace `k1/grounding/adapters/spatial_handle_adapter.py` with a real
  spatial handle adapter once P3.7 spatial is installed.
- `k1/concierge/fsm/controller.py` still has a legacy
  `"temporal_anchor": True` control/elision marker. It is not the old
  `compute_temporal_anchor` path, but D-13 cleanup should finish removing the
  misleading marker.
- `k1/concierge/prompt/sections.py` still contains the old `TIME AWARENESS:`
  identity paragraph while typed NOW/grounding blocks also exist. M3 should decide
  whether this text remains policy language or should be removed under D-16.
- The exact files `tests/k1/kernel/test_service_temporal_tier1.py` and
  `tests/k1/kernel/test_service_temporal_tier2.py` are not present; temporal tier
  behavior is covered through temporal factory/kernel/service tests plus Concierge
  wiring tests. Add or rename focused tier tests if M3 requires exact plan-file
  test names.
- `tests/k1/bus/middleware/test_default_registry_temporal.py` exists for temporal
  topic-registry coverage. Before M3 exit, verify default bus topic prefixes cover
  both `k1.temporal.` and `k1.grounding.` event families.

---

## M3: k1.spatial Foundation

Goal: production-grade spatial kernel service. Replace `_build_family_context` location/timezone reads. Hidden/unknown/unavailable are explicit states.

## M3 Epics

### Epic M3-E1: `k1.spatial` types/events/serialization

#### Issue M3-E1-I1: `k1/spatial/types.py`

Scope (MODIFY): complete the M0 `k1/spatial/types.py` stubs for `DeviceSurface`, `LocationFix`, `PlaceRef`, `Geofence`, `SpatialContext`, `SpatialProjection`, `PresenceRef`, `SpatialTurnSnapshot`, and redaction types per whiteboard. Reuses `DeviceContextSnapshot` from `k1.grounding.types` and does not define a duplicate device snapshot.

Dependencies: M1.5-E1-I1, M0-E3-I2.

#### Issue M3-E1-I2: `events.py`, `errors.py`, `constants.py`, `serialization.py`

Scope (CREATE): per whiteboard.

#### M3-E1 Completion Notes (2026-05-23)

Implemented the spatial public contract without adding a duplicate
`DeviceContextSnapshot`:

- `k1/spatial/types.py` now carries the completed frozen payload surface:
  surface kinds, permission/freshness/precision aliases, `DeviceSurface`,
  `LocationFix`, `PlaceRef`, `Geofence`, `PlaceCandidate`, `PresenceRef`,
  `SpatialRedaction`, `SpatialContext`, `SpatialProjection`, and
  `SpatialTurnSnapshot`. It references the shared grounding device snapshot only
  for typing and does not define a second device snapshot.
- `k1/spatial/events.py` adds the whiteboard event topics and payloads:
  context created/refreshed, place resolved, context redacted, and location
  unavailable.
- `k1/spatial/constants.py` now defines precision levels, permission states,
  surface kinds, place kinds, candidate sources, redaction reasons, and default
  consumer precision.
- `k1/spatial/errors.py` now covers missing registry, stale location, invalid
  fix, policy denial, permission denial, unknown place, and unavailable spatial
  source.
- `k1/spatial/serialization.py` adds explicit round-trip helpers for every M3-E1
  spatial payload, including nested device context, places, fixes, projections,
  and turn snapshots.
- `k1/spatial/__init__.py` re-exports the stable public types, events, config,
  and errors for downstream imports.
- `k1/grounding/serialization.py` was updated only at the spatial conversion
  boundary so M1.5 grounding projections still round-trip after the expanded M3
  spatial dataclasses.

Validation added: `tests/k1/spatial/test_types_events_serialization.py` plus the
existing `tests/k1/spatial/test_package_imports.py`.

### Epic M3-E2: `k1/spatial/ports/` + `adapters/`

#### Issue M3-E2-I1: All spatial ports

Per whiteboard file map.

#### Issue M3-E2-I2: All spatial adapters

Per whiteboard file map. `local_place_registry_adapter.py` reads place registry from config/SessionState (no K0 yet — that's M5). `null_*` adapters are first-class.

#### M3-E2 Completion Notes (2026-05-23)

Implemented the spatial port/adapter boundary, keeping core services independent
from production adapters:

- `k1/spatial/ports/device_context_port.py` defines
  `ISpatialDeviceContextPort` over the shared `DeviceContextSnapshot`.
- `k1/spatial/ports/device_location_port.py` defines optional installed-device
  raw/approximate fix input.
- `k1/spatial/ports/place_registry_port.py` defines place, geofence, member
  default, timezone, and registry metadata reads.
- `k1/spatial/ports/geocoder_port.py`, `presence_port.py`, `policy_port.py`,
  `state_port.py`, `event_port.py`, `id_port.py`, and `metrics_port.py` define
  the remaining service boundaries.
- `k1/spatial/ports/__init__.py` re-exports all M3 spatial Protocols for factory
  validation and tests.
- `k1/spatial/adapters/device_context_adapter.py` wraps the kernel
  `IDeviceContextPort` for spatial.
- `k1/spatial/adapters/browser_device_location_adapter.py` reads browser/app
  `location_fix` payloads from `DeviceContextSnapshot`.
- `k1/spatial/adapters/null_device_location_adapter.py`,
  `null_geocoder_adapter.py`, and `null_presence_adapter.py` provide explicit
  unavailable/default behavior.
- `k1/spatial/adapters/local_place_registry_adapter.py` provides local/test
  places, aliases, geofences, defaults, and timezone lookup until M5 Bridge
  persistence.
- `k1/spatial/adapters/bridge_place_registry_adapter.py` is the M5-ready bridge
  adapter shell; it degrades to an unavailable/empty registry when no bridge
  methods exist.
- `k1/spatial/adapters/selfmodel_policy_adapter.py` maps SelfModel policy, when
  present, to allowed spatial precision and redaction reasons; default behavior
  remains private.
- `k1/spatial/adapters/session_state_adapter.py` is the narrow SessionState
  boundary for future `spatial` HOT and `place_registry` WARM sections.
- `k1/spatial/adapters/event_bus_adapter.py`, `uuid_id_adapter.py`, and
  `null_metrics_adapter.py` provide event, ID, and metrics adapters.
- `k1/spatial/adapters/__init__.py` re-exports adapter classes for M3-E4 factory
  wiring.

Validation added: `tests/k1/spatial/test_ports_protocol_shapes.py`,
`tests/k1/spatial/test_device_context.py`, `tests/k1/spatial/test_place_resolver.py`,
and `tests/k1/spatial/test_session_state_adapter.py`.

### Epic M3-E3: `k1/spatial/service/`

#### Issue M3-E3-I1: Core resolvers + privacy

Per whiteboard file map: `device_surface_resolver.py`, `permission_normalizer.py`, `location_normalizer.py`, `place_registry_service.py`, `place_candidate_source.py`, `place_alias_catalog.py`, `place_resolver.py`, `geofence_matcher.py`, `presence_resolver.py`, `precision_selector.py`, `privacy_projector.py`, `projection_builder.py`, `projection_renderer.py`, `event_emitter.py`, `spatial_service.py`, `health.py`.

**Privacy invariant**: `projection_renderer.py` never receives raw coordinates unless `precision_selector.py` explicitly authorized them for that consumer.

Test files: per whiteboard §"Focused Test File Map".

#### M3-E3 Completion Notes (2026-05-23)

Implemented the deterministic spatial service layer without kernel/session wiring
yet. The service takes typed device context, registry, policy, and presence ports
and returns explicit unknown/hidden/unavailable projections when sensors or policy
do not allow more.

- `k1/spatial/service/device_surface_resolver.py` classifies browser, mobile,
  desktop, shared hub, voice, watch, car, and unknown surfaces from the device
  snapshot.
- `k1/spatial/service/permission_normalizer.py` normalizes granted, denied,
  hidden, stale, degraded, unavailable, and unknown permission states.
- `k1/spatial/service/location_normalizer.py` validates coordinates, accuracy,
  permission, confidence, and unavailable fixes.
- `k1/spatial/service/place_alias_catalog.py` provides deterministic alias
  normalization for home/school/work/vehicle-style labels.
- `k1/spatial/service/place_candidate_source.py` extracts typed place candidates
  from `DeviceContextSnapshot` and structured dispatch/reference mappings.
- `k1/spatial/service/place_registry_service.py` loads place/geofence registry
  snapshots through `IPlaceRegistryPort`.
- `k1/spatial/service/place_resolver.py` resolves candidates to `PlaceRef` with
  registry alias matching and explicit unknown fallback.
- `k1/spatial/service/geofence_matcher.py` implements coordinate-availability
  checks, circle matching with accuracy radius, and polygon matching.
- `k1/spatial/service/presence_resolver.py` reads co-presence candidates through
  `IPresencePort` without making presence mandatory.
- `k1/spatial/service/precision_selector.py` centralizes hidden/semantic/
  approximate/place-id/raw precision ordering and policy clamping.
- `k1/spatial/service/privacy_projector.py` applies precision/redaction policy;
  semantic/front-style projections do not carry raw coordinates.
- `k1/spatial/service/projection_builder.py` builds per-consumer
  `SpatialProjection` objects after policy selection.
- `k1/spatial/service/projection_renderer.py` renders prompt-safe PLACE,
  execution place, and planning spatial blocks from `SpatialProjection` only.
- `k1/spatial/service/event_emitter.py` emits spatial lifecycle/redaction events
  through `ISpatialEventPort`.
- `k1/spatial/service/health.py` defines the spatial health snapshot.
- `k1/spatial/service/spatial_service.py` is the top-level API for refresh,
  current context, place resolution, projection building, and health. It writes
  through `ISpatialStatePort` when present but does not yet install kernel handles;
  that remains M3-E4.
- `k1/spatial/service/__init__.py` re-exports the service-layer entrypoints for
  M3-E4 factory wiring.

Validation added: `tests/k1/spatial/test_location_normalizer.py`,
`tests/k1/spatial/test_place_resolver.py`, `tests/k1/spatial/test_geofence_matcher.py`,
`tests/k1/spatial/test_privacy_projector.py`, and
`tests/k1/spatial/test_session_state_adapter.py`.

Targeted validation run:

```bash
pytest tests/k1/spatial/test_package_imports.py tests/k1/spatial/test_types_events_serialization.py tests/k1/spatial/test_ports_protocol_shapes.py tests/k1/spatial/test_device_context.py tests/k1/spatial/test_location_normalizer.py tests/k1/spatial/test_place_resolver.py tests/k1/spatial/test_geofence_matcher.py tests/k1/spatial/test_privacy_projector.py tests/k1/spatial/test_session_state_adapter.py -v
```

Result: 25 passed.

### Epic M3-E4: Factory + kernel + sections

#### Issue M3-E4-I1: `factory.py` + `kernel/bootstrap.py` + `kernel/handle.py`

#### Issue M3-E4-I2: `k1/sessionstate/sections/spatial.py` + `place_registry.py`

Scope (CREATE):

- `SpatialSection` (HOT) per whiteboard.
- `PlaceRegistrySection` (WARM durable) per whiteboard.
- Register `SpatialSection` in `k1/sessionstate/tiers/hot.py` and `PlaceRegistrySection` in `k1/sessionstate/tiers/warm.py`.
- Update `k1/sessionstate/sizetracker.py` (`HOT_SECTIONS`, `WARM_SECTIONS`, `ALL_SECTIONS`, `SECTION_BUDGETS`) and `sections/__init__.py`.

#### Issue M3-E4-I3: KernelService S2.8 + P3.7 and final Grounding rewire

Insert Spatial at S2.8 after S4 Bridge and before S2.9 Grounding, because Spatial may use Bridge/K0-backed place registry. Insert SpatialHandle at P3.7 after P3.6 Temporal and before P3.8 Grounding. Rewire the existing Grounding bundle/handle from M1.5 so S2.9/P3.8 consumes the real Spatial service/handle instead of `NullGroundingSpatialPort`.

#### M3-E4 Completion Notes (2026-05-24)

Implemented Spatial as a real kernel service/bundle/handle without merging it
into grounding:

- Created `k1/spatial/factory.py` with standalone/testing/production entrypoints,
  Protocol validation, and duplicate port identity rejection.
- Created `k1/spatial/kernel/bootstrap.py`, `handle.py`, and
  `session_binding.py`. `SpatialHandle` wraps `SpatialService`, refreshes the
  current turn, builds projections, installs/uninstalls idempotently, and
  refreshes if a projection is requested before context exists.
- Added `SpatialSection` HOT and `PlaceRegistrySection` WARM under
  `k1/sessionstate/sections/`, registered them in HOT/WARM tiers,
  `sections/__init__.py`, and `sizetracker.py`.
- Updated `SpatialEventBusAdapter` to publish K1 `Envelope` objects rather than
  awaiting `bus.publish(topic, payload)`, matching temporal/grounding adapter
  behavior.
- Added Spatial lifecycle wiring in `k1/kernel/service.py`: S2.8 after Bridge and
  before Grounding; P3.7 after Temporal and before Grounding; teardown/reset in
  shutdown, partial cleanup, and session destroy.
- Added `SessionInstance.spatial`, `KernelService.spatial_bundle`, and wiring
  diagnostics in `describe_wiring()`.
- Fixed two old duplicate skeleton footers in `k1/spatial/adapters/__init__.py`
  and `k1/spatial/service/spatial_service.py` that blocked import collection.
- Made new `k1.spatial` factory/kernel package-root exports lazy so
  `k1.grounding.types -> k1.spatial.types` does not circularly import the
  spatial factory.

Validation added: `tests/k1/sessionstate/sections/test_spatial_section.py`,
`tests/k1/sessionstate/sections/test_place_registry_section.py`,
`tests/k1/spatial/test_factory_wiring.py`, `tests/k1/spatial/kernel/test_handle.py`,
`tests/k1/kernel/test_service_spatial_tier1.py`, and
`tests/k1/kernel/test_service_spatial_tier2.py`.

### Epic M3-E5: Concierge spatial wiring

#### Issue M3-E5-I1: `ConciergeRuntime.set_spatial(handle)` + Front spatial consumption

Scope (MODIFY):

- `k1/concierge/session.py`: `set_spatial(handle)`.
- `k1/concierge/factory.py`: `spatial_port` parameter.
- `k1/concierge/actors/front.py`:
  - **Delete** `_build_family_context()` location/timezone reads lines 588-589 (D-14). The active subject block now reads SelfModel capsule + GroundingProjection spatial fields.
  - The grounding spatial projection feeds `== PLACE ==` block via `prompt_block_renderer.render_place_block(projection)`.
- `k1/concierge/fsm/controller.py`: `_temporal_port.refresh_turn(...)` is followed by `_spatial_port.refresh_turn(...)` when enabled.

Test files: `tests/k1/concierge/test_runtime_set_spatial.py`, `tests/k1/concierge/actors/test_front_spatial_projection.py`.

#### M3-E5 Completion Notes (2026-05-24)

Spatial is now a Concierge pre-start port, while Front still consumes current
place through grounding as the projection aggregator:

- `k1/concierge/session.py` now owns `_spatial`, exposes `spatial`, and has
  `set_spatial(handle)` with the same pre-start guard as temporal/grounding.
- `k1/concierge/factory.py` includes `spatial` in `PortBundle`, testing
  adapters, and runtime attachment.
- `k1/kernel/service.py` passes the P3.7 `SpatialHandle` into `PortBundle` before
  `ConciergeRuntime.start()`.
- `k1/concierge/actors/front.py` accepts optional `spatial` for session binding
  symmetry and no longer injects persona `Location:` / `Timezone:` lines into
  family context. Current place is sourced from grounding PLACE blocks.
- `k1/grounding/service/prompt_block_renderer.py` renders a richer PLACE block
  from `GroundingProjection.spatial`, including surface, place refs, and
  redactions when present.
- `k1/concierge/prompt/back_prompt.py` no longer contains the hardcoded Denton
  restaurant example, satisfying the M3 no-hardcoded-place criterion for `k1/`.
- Did not add a blind spatial refresh call to `ConciergeController._route_user_turn`;
  that path is currently synchronous and the live refresh path already runs
  through Front/grounding. This divergence should stay explicit until the FSM
  owns typed async temporal/spatial ports.

Validation added: `tests/k1/concierge/test_runtime_set_spatial.py` and
`tests/k1/concierge/actors/test_front_spatial_projection.py`.

### Epic M3-E6: Grounding spatial adapter upgrade

#### Issue M3-E6-I1: Replace spatial stub with real handle

Scope (MODIFY):

- `k1/grounding/adapters/spatial_handle_adapter.py`: stop returning `unknown` stub; wrap actual `SpatialHandle`.
- `k1/grounding/service/projection_policy.py`: include spatial precision per consumer (per whiteboard table).
- `k1/grounding/service/lease_builder.py`: populate spatial fields from handle, applying redactions.

Test files: `tests/k1/grounding/adapters/test_spatial_handle_adapter_real.py`, `tests/k1/grounding/test_projection_policy_spatial.py`, `tests/k1/grounding/test_lease_spatial.py`.

#### M3-E6 Completion Notes (2026-05-24)

Grounding now consumes the real SpatialHandle and shapes precision by consumer:

- `k1/grounding/adapters/spatial_handle_adapter.py` passes device/installation
  IDs and `requested_precision` through to `SpatialHandle.build_projection()`;
  the unknown fallback remains only for disabled/missing spatial handles.
- `k1/grounding/ports/spatial_port.py` now includes optional
  `requested_precision` so policy can drive spatial projection precision.
- `k1/grounding/service/projection_policy.py` uses
  `k1.spatial.constants.DEFAULT_CONSUMER_PRECISION` (`front/back=semantic`,
  `planner/fabric/tool/memory=place_id`, `agent=semantic`) while preserving the
  explicit raw override gate.
- `k1/grounding/adapters/selfmodel_policy_adapter.py` now uses those defaults
  and accepts optional SelfModel scope overrides via
  `get_grounding_consumer_scope()` / `grounding_consumer_scope()` when present.
- `k1/grounding/service/grounding_service.py` resolves policy before asking
  spatial for a projection, then passes `scope.spatial_precision` into the
  spatial port. Agent leases therefore carry policy-shaped `lease.spatial`.

Validation added: `tests/k1/grounding/adapters/test_spatial_handle_adapter_real.py`,
`tests/k1/grounding/test_projection_policy_spatial.py`, and
`tests/k1/grounding/test_lease_spatial.py`.

### Epic M3-E7: M3 Evidence Integration And Diagram Cleanup

#### Issue M3-E7-I1: Retain `mentioned_location` as conversational place evidence

Scope (MODIFY):

- `k1/sessionstate/sections/beliefs_active.py`:
  - Keep `MentionedLocation` and `set_mentioned_location` / `get_mentioned_location` intact.
  - Document it as conversational evidence only, never authoritative current place.
- `k1/spatial/service/place_candidate_source.py`:
  - Read `beliefs_active.mentioned_location` as one candidate source with provenance `conversation_mention` and lower confidence than device/place-registry signals.
- Concierge FSM and Back snapshot reader: stop treating `mentioned_location` as current place; consume authoritative `spatial`/`grounding` projection for current place and use `mentioned_location` only as a resolver candidate.

Test files: `tests/k1/spatial/test_place_candidate_source.py`, `tests/k1/sessionstate/sections/test_beliefs_active_mentioned_location_candidate.py`.

#### Issue M3-E7-I2: Replace diagram-only spatial nodes

Scope (MODIFY):

- Delete spatial/temporal/place nodes from `k1/concierge/concierge_unified.mmd` lines 236-245, 961 (D-17). Replace with reference link to `architecture_diagrams/k1/temporal_spatial_grounding/` diagrams.

#### M3-E7 Completion Notes (2026-05-24)

Mentioned locations are now explicitly conversational evidence, not current
device place:

- `k1/sessionstate/sections/beliefs_active.py` documentation and method
  docstrings now describe `mentioned_location` as conversational evidence only.
- `k1/spatial/service/place_candidate_source.py` reads
  `beliefs_active.mentioned_location` as a low-confidence
  `conversation_mention` candidate capped below device/registry evidence and
  marks it `authoritative_current_place=False`.
- `k1/concierge/prompt/builder.py` now labels the old HOT-section prompt line as
  `[mentioned location: ...]` rather than `[location: ...]` to avoid confusing it
  with authoritative PLACE grounding.
- `k1/concierge/concierge_unified.mmd` removes diagram-only spatial resolver
  nodes/edges and points to `architecture_diagrams/k1/temporal_spatial_grounding/`
  as the runtime diagram source.

Validation added: `tests/k1/spatial/test_place_candidate_source.py` and
`tests/k1/sessionstate/sections/test_beliefs_active_mentioned_location_candidate.py`.

Targeted validation run for M3-E4 through M3-E7:

```bash
pytest tests/k1/sessionstate/sections/test_spatial_section.py tests/k1/sessionstate/sections/test_place_registry_section.py tests/k1/spatial/test_factory_wiring.py tests/k1/spatial/kernel/test_handle.py tests/k1/kernel/test_service_spatial_tier1.py tests/k1/kernel/test_service_spatial_tier2.py tests/k1/concierge/test_runtime_set_spatial.py tests/k1/concierge/actors/test_front_spatial_projection.py tests/k1/grounding/adapters/test_spatial_handle_adapter_real.py tests/k1/grounding/test_projection_policy_spatial.py tests/k1/grounding/test_lease_spatial.py tests/k1/spatial/test_place_candidate_source.py tests/k1/sessionstate/sections/test_beliefs_active_mentioned_location_candidate.py -v
```

Result: 23 passed.

Targeted nearby regression runs:

```bash
pytest tests/k1/spatial/test_package_imports.py tests/k1/spatial/test_device_context.py tests/k1/spatial/test_session_state_adapter.py tests/k1/kernel/test_service_grounding_tier1.py tests/k1/kernel/test_service_grounding_tier2.py tests/k1/concierge/test_runtime_set_temporal.py tests/k1/concierge/test_runtime_set_grounding.py -v
pytest tests/k1/grounding/test_package_imports.py -v
pytest tests/k1/concierge/prompt/test_back_prompt_capability_names.py tests/k1/concierge/prompt/test_builder_temporal.py -v
```

Result: 14 passed, then 3 passed, then 7 passed. A combined run with both spatial and grounding
`test_package_imports.py` files hits pytest's duplicate-basename import mismatch,
so those package-import files must be run in separate pytest processes unless
the test module names are made unique.

## M3 Success Criteria

1. `k1.spatial` package exists end to end.
2. Front prompt has `== PLACE ==` block sourced from `GroundingProjection`.
3. Hardcoded Denton string is gone (confirmed by `git grep -i denton` returning zero hits in `k1/`).
4. Spawned agents always receive `lease.spatial` even when status is `unknown`.
5. Spatial unit + integration tests green.
6. Final lifecycle order is S2.7 Temporal, S2.8 Spatial, S2.9 Grounding and P3.6 Temporal, P3.7 Spatial, P3.8 Grounding.

## M3 Exit Gate

```bash
pytest tests/k1/spatial/ tests/k1/sessionstate/sections/test_spatial_section.py tests/k1/sessionstate/sections/test_place_registry_section.py tests/k1/kernel/test_service_spatial_tier1.py tests/k1/kernel/test_service_spatial_tier2.py tests/k1/concierge/test_runtime_set_spatial.py tests/k1/concierge/actors/test_front_spatial_projection.py tests/k1/grounding/adapters/test_spatial_handle_adapter_real.py tests/k1/grounding/test_projection_policy_spatial.py tests/k1/grounding/test_lease_spatial.py tests/k1/sessionstate/sections/test_beliefs_active_mentioned_location_candidate.py -v
```

Flip `k1.spatial.enabled` default to `True`.

---

## M4: Fabric / Tool Contracts / Agent Leases

Goal: Fabric `ContextBuilder` honors `temporal`/`spatial`/`grounding` section declarations and baseline invocation grounding. Agents receive `AgentGroundingLease` by default.

## M4 Epics

### Epic M4-E1: Fabric context builder

#### Issue M4-E1-I1: `ContextBuilder` baseline invocation grounding

Scope (MODIFY):

- `k1/fabric/core/context_builder.py`:
  - In `build()`, after reading declared sections, attach a `grounding_invocation` block to `context_override` containing `invoked_at_utc`, `temporal_anchor_id`, `spatial_context_id`, `grounding_envelope_id`. Built via `k1.grounding.service.invocation_metadata.build_invocation_metadata(...)`.
  - Add a typed `grounding_port: IGroundingPort | None` constructor arg. Required when `k1.grounding.enabled`.
  - Update existing call sites in `FabricFactory.create_with_ports()`.
- `k1/fabric/providers/base_provider.py`:
  - Assert provider metadata preserves `context.session_sections["context_override"]["grounding_invocation"]` for all provider classes.
- There is no `k1/fabric/providers/tool_provider.py`. Baseline deterministic-tool grounding flows through `ContextBuilder` plus `BaseProvider` metadata; provider-specific changes are only needed for agent leases.

Test files: `tests/k1/fabric/test_context_builder_grounding_invocation.py`, `tests/k1/fabric/providers/test_base_provider_grounding_metadata.py`.

Dependencies: M3 complete.

#### Issue M4-E1-I2: `context_precision` contract field

Scope (CREATE):

- `k1/fabric/contracts/context_precision.py` — `@dataclass(frozen=True) class ContextPrecision { temporal: Literal["anchor", "windows", "execution"]; spatial: Literal["hidden", "semantic", "approximate", "place_id", "raw"]; }`.

Scope (MODIFY):

- `k1/fabric/contracts/tool_contract.py`, `agent_contract.py`: add optional `context_precision: ContextPrecision | None` field.
- `k1/contracts/schemas/context_precision.schema.json` — JSON schema validation.
- `k1/contracts/schemas/grounding.schema.json` — invocation block schema.

Test files: `tests/k1/fabric/contracts/test_context_precision.py`.

#### M4-E1 Completion Notes (2026-05-24)

Implemented Epic M4-E1 across the live Fabric boundaries, with code reality
taking priority over the original synchronous wording in I1:

- `k1/fabric/core/context_builder.py` now accepts an optional session
  grounding port, exposes `set_grounding_port(...)`, and preserves the
  existing synchronous `build(...)` API. The live Fabric execution path uses
  `build_async(...)` so it can await `IGroundingPort.create_envelope(...)` and
  `build_projection(...)` before attaching `context_override.grounding_invocation`.
- `k1/grounding/service/invocation_metadata.py` now stamps baseline invocation
  metadata with `invoked_at_utc` in addition to envelope/projection/temporal/
  spatial references.
- `k1/fabric/fabric.py` awaits the grounding-aware context build during real
  `execute(...)` while keeping the legacy `_build_context(...)` helper
  synchronous for existing tests and callers.
- `k1/fabric/factory.py` threads an optional `grounding_port` into the shared
  `ContextBuilder`, and `k1/kernel/service.py` binds the per-session
  `GroundingHandle` into the already-created per-session Fabric once P3.8
  grounding exists.
- `k1/fabric/providers/base_provider.py` preserves
  `context_override.grounding_invocation` through the existing shared provider
  metadata helper, so Native/MCP/WASM/Agent provider transports inherit the
  same baseline block without a duplicate or nonexistent `tool_provider.py`.
- `k1/fabric/contracts/context_precision.py` adds the frozen
  `ContextPrecision` value object. `CapabilityContract` and `AgentContract`
  now serialize/deserialize `context_precision`, and both tool/agent parsers
  preserve it from YAML bodies.
- `k1/contracts/schemas/tool_contract.schema.json` and
  `k1/contracts/schemas/agent_contract.schema.json` allow optional
  `context_precision`; `context_precision.schema.json` and
  `grounding.schema.json` document the standalone precision and invocation
  payload shapes.

Validation evidence:

- `python -m pytest tests/k1/fabric/test_context_builder_grounding_invocation.py tests/k1/fabric/providers/test_base_provider_grounding_metadata.py tests/k1/fabric/contracts/test_context_precision.py -v` -> 8 passed.
- Existing boundary regressions via test runner: `tests/k1/fabric/test_context_builder.py`, `tests/k1/fabric/test_capability_contract_prompt_metadata.py`, `tests/k1/fabric/providers/test_native_tool_provider_path.py`, `tests/k1/fabric/test_create_shared.py`, `tests/k1/fabric/test_fabric_factory_hil_port.py`, `tests/k1/fabric/test_fabric_execute_with_gate.py`, `tests/k1/fabric/test_execute_batch.py` -> 230 passed.
- Existing parser/schema/type regressions via test runner: `tests/k1/fabric/test_tool_schema_validation.py`, `tests/k1/fabric/test_agent_schema_validation.py`, `tests/k1/fabric/test_contract_parsers.py`, `tests/k1/fabric/test_types.py` -> 294 passed.

Remaining M4 work starts at M4-E2: agent leases and contract YAML updates are
not implemented by this epic.

### Epic M4-E2: Agent provider lease

#### Issue M4-E2-I1: `AgentProvider` requests lease

Scope (MODIFY):

- `k1/fabric/providers/agent_provider.py`:
  - Before `IAgentFactory.spawn_and_execute()`, call `grounding_port.build_agent_lease(...)` for the contract.
  - Pass `lease` into `ExecutionContext` as a typed field.
  - Lease TTL respected; if lease expires mid-execution, `lease_builder.refresh(...)` is called.

Test files: `tests/k1/fabric/providers/test_agent_provider_lease.py`.

#### Issue M4-E2-I2: `build_agent.yaml` and other contracts updated

Scope (MODIFY):

- `k1/contracts/tools/build_agent.yaml`:

  ```yaml
  required_context: [temporal, spatial, beliefs_active, interaction_history, task_context]
  optional_context: [active_plans, pending_clarifications]
  context_precision:
    temporal: execution
    spatial: semantic
  lease:
    ttl_seconds: 900
    allow_refresh: true
  ```

- `date_calc.yaml`: already updated in M1-E10-I1. Add `context_precision.temporal: anchor`.
- `discover_capabilities.yaml`, `find_prompts.yaml`, `unit_convert.yaml`: declare `context_precision` even if it's just `temporal: anchor, spatial: hidden`.

Test files: `tests/k1/contracts/test_tool_contracts_precision.py`.

### Epic M4-E3: M4 Deprecation Epic

#### Issue M4-E3-I1: Remove ad-hoc context_override grounding paths

Scope (MODIFY): any path that previously injected time/place via `context_override` is replaced by the baseline `grounding_invocation` block from M4-E1-I1.

#### M4-E2 / M4-E3 Completion Notes (2026-05-24)

Implemented Epic M4-E2 and Epic M4-E3 against the live provider and grounding
boundaries:

- `k1/fabric/providers/agent_provider.py` now requests an
  `AgentGroundingLease` before `IAgentFactory.spawn_and_execute(...)` when a
  session grounding port is present, attaches the lease to
  `ExecutionContext.grounding_lease`, and mirrors lease identifiers into
  `context_override.grounding_invocation` plus an `agent_grounding_lease`
  session section for downstream transports and diagnostics.
- `AgentFactory._spawn(...)` preserves provider-issued grounding lease state
  and merges the provider's `context_override.grounding_invocation` through
  the synchronous context rebuild path, so the lease is not lost while building
  the agent's initial context.
- `k1/fabric/factory.py` wires the shared session `grounding_port` into
  `AgentProvider` through the existing `ProviderFactory` port-dependency path;
  no duplicate provider-specific composition path was added.
- `k1/grounding/service/lease_builder.py`,
  `k1/grounding/service/grounding_service.py`, and
  `k1/grounding/kernel/handle.py` now respect explicit `ttl_seconds` when
  issuing agent leases instead of only recording TTL in metadata.
- `ExecutionContext`, `CapabilityContract`, and `AgentContract` now
  serialize/deserialize lease metadata. Tool and agent contract schemas allow
  optional `lease` policies.
- `build_agent.yaml` declares the required/optional context, execution/
  semantic precision, and 900-second refreshable lease policy. `date_calc`,
  `discover_capabilities`, `find_prompts`, and `unit_convert` declare explicit
  precision policies; `date_calc` continues to require the `temporal` section.
- For M4-E3, production search found no remaining production path that injects
  ad-hoc time/place grounding through `context_override`. `ContextBuilder` now
  also drops deprecated top-level grounding override keys (`now`, `time`,
  `place`, `temporal`, `spatial`, `grounding`) while preserving the supported
  `grounding_invocation` block.

Validation evidence:

- Focused new coverage:
  `python -m pytest tests/k1/fabric/providers/test_agent_provider_lease.py tests/k1/contracts/test_tool_contracts_precision.py tests/k1/fabric/test_context_builder_grounding_invocation.py -v` -> 13 passed.
- M4 exit gate:
  `python -m pytest tests/k1/fabric/test_context_builder_grounding_invocation.py tests/k1/fabric/providers/test_base_provider_grounding_metadata.py tests/k1/fabric/contracts/test_context_precision.py tests/k1/fabric/providers/test_agent_provider_lease.py tests/k1/contracts/test_tool_contracts_precision.py tests/k1/fabric/test_date_calc_context.py -v` -> 21 passed.
- Narrow touched-boundary regressions:
  `python -m pytest tests/k1/fabric/test_agent_435.py tests/k1/fabric/test_agent_provider_wiring.py tests/k1/fabric/test_tool_schema_validation.py tests/k1/fabric/test_agent_schema_validation.py tests/k1/fabric/test_contract_parsers.py tests/k1/fabric/test_capability_contract_prompt_metadata.py tests/k1/grounding/test_m15_runtime.py::test_m15_e4_handle_protocol_aliases_preserve_envelope_for_agent_lease tests/k1/grounding/test_lease_spatial.py::test_issue_agent_lease_uses_agent_spatial_precision -v` -> 281 passed.

## M4 Success Criteria

1. Every tool contract declares `context_precision`.
2. Spawned agents always receive `AgentGroundingLease`.
3. `date_calc` receives `temporal` section by contract.
4. `NativeToolProvider`, `WasmProvider`, `McpProvider`, and `AgentProvider` all receive baseline `context_override.grounding_invocation` through shared provider metadata without a nonexistent `tool_provider.py`.
5. Fabric tests green.

## M4 Exit Gate

```bash
pytest tests/k1/fabric/test_context_builder_grounding_invocation.py tests/k1/fabric/providers/test_base_provider_grounding_metadata.py tests/k1/fabric/contracts/test_context_precision.py tests/k1/fabric/providers/test_agent_provider_lease.py tests/k1/contracts/test_tool_contracts_precision.py tests/k1/fabric/test_date_calc_context.py -v
```

---

## M5: Place Registry + Geofences + K0 Persistence

Goal: place registry moves from local/session-only to K0 Bridge-backed durable storage. Geofence matcher reaches production.

## M5 Epics

### Epic M5-E1: K0 Bridge integration for `place_registry`

#### Issue M5-E1-I1: `bridge_place_registry_adapter.py`

Scope (CREATE):

- `k1/spatial/adapters/bridge_place_registry_adapter.py`: implements `IPlaceRegistryPort` against K0 Bridge via existing Bridge adapter (`k0_proxy_client.py` or new K0 op).
- Adapter handles offline mode (`OfflineBridgeAdapter` returns unavailable).

#### Issue M5-E1-I2: K0 schema for place registry

Scope (CREATE):

- `k0/schemas/place_registry.json` — schema for places, geofences, aliases, member-default places.
- `bridge/contracts/place_registry.py` if Bridge adapters require typed surface.

#### Issue M5-E1-I3: Factory switches local→bridge adapter when Bridge online

Scope (MODIFY): `k1/spatial/factory.py` selects `BridgePlaceRegistryAdapter` when bridge_runtime is online and `LocalPlaceRegistryAdapter` otherwise.

### Epic M5-E2: Geofence matcher production

#### Issue M5-E2-I1: `geofence_matcher.py` correctness pass

Scope (MODIFY):

- Add coordinate sanity checks, accuracy radius handling, distance threshold, point-in-polygon for non-circular fences.

Test files: `tests/k1/spatial/test_geofence_matcher_real.py`.

### Epic M5-E3: Travel/proximity helpers for Planner

#### Issue M5-E3-I1: Spatial constraint enriched for planner

Scope (MODIFY): `k1/grounding/service/projection_builder.py` exposes `relevant_place_refs` and `travel_hint` (e.g. coarse distance, not raw coords) in planner projection.

## M5 Success Criteria

1. `place_registry` survives session restarts via K0.
2. Geofence matcher passes correctness tests.
3. Planner spatial constraints include relevant place IDs.

## M5 Exit Gate

```bash
pytest tests/k1/spatial/adapters/test_bridge_place_registry_adapter.py tests/k1/spatial/test_geofence_matcher_real.py tests/k1/grounding/test_projection_builder_planner_spatial.py -v
```

---

## M6: K0 Memory + UI + MemoryWriter Schema + Final Cleanup

Goal: MemoryWriter writes time/place metadata; SessionState UI exposes new sections; MemoryWriter schemas stay aligned with optional grounding fields; feature flags are removed.

## M6 Epics

### Epic M6-E1: Memory write metadata

#### Issue M6-E1-I1: MemoryWriter grounding metadata propagation

Scope (CREATE):

- `k1/memory_writer/grounding_metadata.py` — helper that takes a `GroundingEnvelope`/projection dict and produces memory-write metadata: `temporal.anchor_id`, `event_local_date`, `timezone`, `spatial.place_id`, `spatial.precision`, `transition_from_place`, `transition_mode`.

Scope (MODIFY):

- `k1/memory_writer/extraction/raw_extraction.py` — add optional `transition_from_place` and `transition_mode` fields if absent.
- `k1/memory_writer/extraction/writer_agent.py` — parse those fields from extraction output.
- `k1/memory_writer/extraction/extraction_validator.py` — pass fields into `MemoryAtom`.
- `k1/memory_writer/types.py` — confirm `MemoryAtom` already carries `place_id`, `location_hierarchy`, `transition_from_place`, and `transition_mode`; add only if code drifted.
- `k1/memory_writer/envelope/field_mapper.py` — map grounding metadata into the outgoing `memory.write.v1` body; use `PlaceResolver.resolve_with_geohash()` for transition origin metadata.
- `k1/memory_writer/place_resolver.py` — update only if `resolve_with_geohash()` needs an explicit origin-place code path.

#### Issue M6-E1-I2: `k1/memory_writer/spatial_redaction.py`

Scope (CREATE):

- Enforces raw location is excluded from memory writes by default. Single function `redact_if_disallowed(write_payload, policy)`.
- Applies before `FieldMapper.map_atom_to_body()` emits bridge payloads.

### Epic M6-E2: K0 recall by temporal/spatial facets

#### Issue M6-E2-I1: `k0/memory/time_place_index.py`

Scope (CREATE):

- Indexing helper for K0 recall by local date / time window / place ID / semantic place.

### Epic M6-E3: SessionState UI inspector

#### Issue M6-E3-I1: UI inspector shows new sections

Scope (MODIFY):

- `ui/web/app.py` — ensure `/api/session/state`, `get_session_state()`, and `_serialize_session_section()` surface `temporal`, `spatial`, `place_registry`, and `grounding` section payloads through the existing safe JSON path.
- `ui/web/static/app.js` — update `fetchSessionState()`, `renderSessionState(data)`, `renderSessionInspector(data, sectionName)`, `_ssInspectorStats(value)`, and `_ssStringifyData(value)` to show anchor IDs, windows, resolved expressions, semantic place, precision, redactions, source, envelope IDs, `place_id`, `transition_from_place`, and `temporal_links`.
- `ui/web/static/index.html` — use the existing `#ss-inspector` container; add markup only if the current inspector needs additional fixed regions.
- `tests/ui/web/test_app.py` — assert the inspector renderer still exists and recognizes the new section names.

### Epic M6-E4: MemoryWriter schema contract alignment

#### Issue M6-E4-I1: Align memory writer schema with grounding metadata

Scope (MODIFY):

- `k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json` — keep existing optional fields `place_id`, `location_hierarchy`, `transition_from_place`, `transition_mode`, `temporal`, `temporal_links`, and `conversation_anchor_ms`; add no required fields unless a contract migration is explicitly approved.
- Bridge/K0 memory-write tests remain valid because new grounding fields are optional.
- `beliefs_active.mentioned_location` is not removed; no FlatBuffer migration is required for that field in this plan.

### Epic M6-E5: Final cleanup

#### Issue M6-E5-I1: Remove feature flags (D-19)

Scope (MODIFY):

- `k1/concierge/config/kernel.py`: remove `enable_temporal`, `enable_grounding`, `enable_spatial`. Remove env-var bindings.
- `k1/kernel/service.py`: remove all `if config.enable_*` guards around S2.7/S2.8/S2.9/P3.6/P3.7/P3.8. Modules are always installed in the final order: Temporal, Spatial, Grounding.
- `k1/concierge/factory.py`: same — remove `None` fallback for `temporal_port`/`spatial_port`/`grounding_port`. They are required.
- Test files updated to drop flag-related fixtures.

#### Issue M6-E5-I2: Remove residual HOT-only behavior (D-20)

Scope (MODIFY): once K0 Bridge place_registry persistence is verified, remove any local-only standalone paths.

## M6 Success Criteria

1. Memory writes include temporal+spatial metadata.
2. K0 recall by time/place facets works.
3. UI inspector exposes all four new sections.
4. MemoryWriter contract tests preserve optional temporal/spatial grounding fields without breaking existing payloads.
5. `beliefs_active.mentioned_location` remains available as conversational evidence.
6. Feature flags are removed; modules always on.

## M6 Exit Gate

```bash
pytest tests/k1/memory_writer/test_turn_timestamp_propagation.py tests/k0/gate/test_gate_body_validation.py tests/bridge/test_envelope_builder.py tests/bridge/contracts/test_memory_write_v1.py tests/ui/web/test_app.py tests/k0/memory/test_time_place_index.py tests/k1/kernel/test_no_feature_flags.py -v
```

After M6 exit gate passes, merge `feature/temporal-spatial-grounding` to `main`.

---

## Appendix A: Cross-Cutting Invariants

These must hold at every milestone end. Each milestone's exit gate verifies them by test or grep.

1. `git grep -i denton k1/` returns zero hits in code. (M1.)
2. `git grep "compute_temporal_anchor" k1/` returns hits only inside `k1.temporal` and tests. (M1.)
3. `git grep "from k1.sessionstate.sections.temporal_context" k1/` returns zero hits. (M1.)
4. `git grep "control.set_temporal_anchor\|control.get_temporal_anchor" k1/` returns zero hits. (M1.)
5. No regex import inside `k1/temporal/service/*.py` core resolver files except inside curated leaf helpers (per whiteboard rule). (M1, M2.)
6. `git grep -nE "family|household|Jordan|mom|dad|child(ren)?\b" k1/temporal/ k1/spatial/ k1/grounding/` returns zero hits outside tests/docs. (Domain-agnostic invariant.)
7. Every spawned agent contract executed through Fabric receives an `AgentGroundingLease`. (M4.)
8. Prompt builder renders `== NOW ==` / `== PLACE ==` / `== EXECUTION GROUNDING ==` only via `k1.grounding.service.prompt_block_renderer`. No other path renders these blocks. (M1.5, M3.)
9. `DeviceContextSnapshot` is defined exactly once (`k1.grounding.types`); the kernel port re-exports. (M0.)
10. SessionState sections `temporal`, `spatial`, `place_registry`, `grounding` are registered as HOT (HOT lightweight for `grounding`, WARM durable for `place_registry`). (M1, M1.5, M3.)
11. `beliefs_active.mentioned_location` remains conversational evidence and is never treated as authoritative current location. (M3.)

## Appendix B: Per-Issue Self-Containment Checklist

When implementing any issue above, the implementer ("cobbler") confirms the issue contains all of the following before opening the PR:

- [ ] Files listed under CREATE all created with the responsibilities stated.
- [ ] Files listed under MODIFY changed only as specified.
- [ ] Files listed under DELETE actually deleted (`git rm`).
- [ ] All listed Protocols/dataclasses match signatures.
- [ ] Listed test files exist (implementer names individual tests).
- [ ] Issue's exact pytest command line runs green locally.
- [ ] `git diff --check` clean.
- [ ] No imports from `poc/` anywhere (confirmed by `git grep "from poc\|import poc" $(git diff --name-only main...)`).
- [ ] No `family`/`household`/`Jordan`/etc. domain words in new kernel code (per Appendix A invariant 6).
- [ ] Dependency issues listed in the issue are merged into `feature/temporal-spatial-grounding` first.
- [ ] PR description references the issue ID (e.g. `Closes: M1-E4-I2`).

## Appendix C: Test Discipline

Per user's hard rule:

- **NEVER** run `pytest tests/k1/kernel/` full suite.
- **NEVER** run full Fabric suite unsolicited.
- Run only the exact `pytest <files> -v` command listed in the issue's exit gate or focused test list.
- Targeted regression on directly-touched files only.

## Appendix D: Files To Touch Quick Index

| Area | Path |
| --- | --- |
| New packages | `k1/temporal/`, `k1/spatial/`, `k1/grounding/` |
| Kernel ports | `k1/kernel/ports/temporal_port.py`, `spatial_port.py`, `grounding_port.py`, `device_context_port.py` |
| Kernel service | `k1/kernel/service.py` (S2.7, S2.8, S2.9; P3.6, P3.7, P3.8) |
| Kernel config | `k1/concierge/config/kernel.py` (`KernelConfig`) |
| SessionState sections | `k1/sessionstate/sections/temporal.py`, `spatial.py`, `place_registry.py`, `grounding.py`, `__init__.py`, `control.py`, `beliefs_active.py`, `temporal_context.py` (delete) |
| SessionState public types | `k1/sessionstate/public_types.py` |
| SessionState registration | `k1/sessionstate/tiers/hot.py`, `tiers/warm.py`, `sizetracker.py`, `manager.py`, `factory.py` |
| Concierge | `k1/concierge/session.py`, `factory.py`, `fsm/controller.py`, `actors/front.py`, `actors/back.py`, `prompt/builder.py`, `prompt/sections.py`, `prompt/back_prompt.py`, `task/dispatch.py` |
| Planner | `k1/planner/stages/expand_service.py`, `sketch_service.py`, `validate_service.py` |
| Orchestrator | `k1/orchestrator/types.py`, `orchestration/orchestrator_service.py` |
| Fabric | `k1/fabric/core/context_builder.py`, `contracts/context_precision.py`, `contracts/tool_contract.py`, `contracts/agent_contract.py`, `providers/base_provider.py`, `providers/agent_provider.py`, `providers/native_tool_provider.py`, `providers/wasm_provider.py`, `providers/mcp_provider.py` |
| Tool contracts | `k1/contracts/tools/date_calc.yaml`, `build_agent.yaml`, `discover_capabilities.yaml`, `find_prompts.yaml`, `unit_convert.yaml` |
| Contract schemas | `k1/contracts/schemas/context_precision.schema.json`, `grounding.schema.json` |
| FlatBuffer schemas | `k1/contracts/flatbuffers/sessionstate/control_section.fbs`, `temporal_section.fbs`, `spatial_section.fbs`, `place_registry_section.fbs`, `grounding_section.fbs` |
| MemoryWriter | `k1/memory_writer/grounding_metadata.py`, `spatial_redaction.py`, `extraction/raw_extraction.py`, `extraction/writer_agent.py`, `extraction/extraction_validator.py`, `envelope/field_mapper.py`, `place_resolver.py`, `types.py` |
| K0 | `k0/memory/time_place_index.py`, `k0/schemas/place_registry.json` |
| UI | `ui/web/app.py`, `ui/web/static/app.js`, `ui/web/static/index.html`, `tests/ui/web/test_app.py` |
| Diagrams | `architecture_diagrams/k1/temporal_spatial_grounding/` |

---

## Appendix E: Glossary

- **K0**: memory kernel.
- **K1**: intelligence kernel (this plan's host).
- **Vertical**: tier-2 domain (FamilyOS, SchoolOS, EnterpriseOS, FinanceOS, AgriOS, GovOS) consuming K1.
- **Principal**: active acting identity in a session, sourced from SelfModel.
- **Subject / Group**: domain-agnostic kernel terms for actors and their relational containers; verticals map "member", "household", "student", "class", "employee", "team" to subject/group.
- **Anchor**: typed temporal snapshot for a session at a moment in time.
- **Envelope**: typed grounding object joining temporal, spatial, identity, freshness, provenance, redactions.
- **Projection**: consumer-scoped view of the envelope.
- **Lease**: time-bounded grounding projection issued to a spawned agent.
- **POC**: throwaway prototype code. Hard-removed by this plan.
