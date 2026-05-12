# Integrating a New Vertical Domain into `k1/selfmodel/`

**Status**: Living document
**Audience**: Engineers adding a new vertical (Health, School, Finance, Gov, Agri, …) on top of K1
**Prerequisite**: M0 (SpaceGraph migration) complete — see `docs/plans/KERNEL_BOOTUP_PLAN.md`

---

## 1. Why `SpaceGraph` is domain-agnostic

The K1 kernel does not know what a "family" is. It only knows about a **space** — a
bounded set of actors with directed relationships, routines, and a constitution.
The same `SpaceGraphSnapshot` shape is reused across every vertical:

```
SpaceGraphSnapshot
├── space_id:        str              # opaque identifier; "family:smith", "clinic:mayo:ward_3", …
├── revision:        str              # monotonic snapshot version
├── members:         tuple[ActorRef]  # actors in this space
├── relations:       tuple[SpaceEdge] # directed edges between members
├── routines:        tuple[RoutineRef]# recurring activities visible in this space
└── composed_at_ms:  int              # render timestamp
```

The kernel composes a `SituationFrame` from this snapshot, filters it against the
viewing actor's visibility, and renders the result as the `space_graph_block` inside
the LLM prompt. **No domain-specific code lives inside `k1/selfmodel/`.**

## 2. Required artifacts for a new vertical

Every vertical lives under `verticals/<name>/` (sibling to `k1/`, never inside it).
At minimum, a vertical ships four files:

```
verticals/<name>/
├── profile.py          # source-of-truth dataclass (e.g. PatientProfile)
├── seeder.py           # SpaceDataSeeder subclass — builds SpaceGraphSnapshot from profile
├── acl_rules.py        # VisibilityPolicy rules for this domain
└── constitution.yaml   # bootstrap constitution body for this vertical
```

### 2.1 `profile.py`

A dataclass that captures the human-readable input data for the vertical. This is
the only file that may contain domain vocabulary (patients, students, classrooms,
funds, citizens, fields).

```python
# verticals/health/profile.py
from dataclasses import dataclass, field

@dataclass(frozen=True)
class CareTeamProfile:
    """Source-of-truth profile for a HealthOS care team. Loaded from JSON/YAML
    or hardcoded for demos."""
    organization: str       # "Mayo Clinic"
    space_id: str           # "clinic:mayo:ward_3"
    members: tuple[...]     # patients, clinicians, caregivers, admins
    routines: tuple[...]    # rounds, medication schedules, shift handoffs
    consent_model: str      # "HIPAA"
```

### 2.2 `seeder.py`

Subclass `SpaceDataSeeder` (lives in `k1.selfmodel.service` or `verticals/_common/`)
and implement `build_snapshot()` which returns a `SpaceGraphSnapshot`.

```python
# verticals/health/seeder.py
from k1.selfmodel.contracts.space_graph import (
    ActorRef, SpaceEdge, SpaceGraphSnapshot, RoutineRef,
)
from k1.selfmodel.service.space_graph import SPACE_GRAPH_WRITER_ID

class CareTeamSeeder:
    """Builds SpaceGraphSnapshot for HealthOS care teams."""

    def seed_space_projection(self, bundle, profile: CareTeamProfile) -> None:
        # Idempotency: skip if a snapshot already exists for this space_id
        existing, _ = bundle.store.read_space(profile.space_id)
        if existing is not None:
            return

        members = tuple(
            ActorRef(
                member_id=m.actor_id,
                display_name=m.name,
                role=m.role,        # "patient" | "clinician" | "caregiver" | "admin"
                age_band=m.age_band,
            )
            for m in profile.members
        )

        relations = tuple(
            SpaceEdge(
                from_member=e.from_actor,
                to_member=e.to_actor,
                kind=e.kind,        # "treating" | "caring_for" | "supervises"
            )
            for e in profile.edges
        )

        routines = tuple(
            RoutineRef(routine_id=r.id, name=r.name, schedule=r.schedule)
            for r in profile.routines
        )

        snapshot = SpaceGraphSnapshot(
            space_id=profile.space_id,
            revision="seed-v1",
            members=members,
            relations=relations,
            routines=routines,
        )
        bundle.store.write_space(snapshot, writer_id=SPACE_GRAPH_WRITER_ID)
```

### 2.3 `acl_rules.py`

Visibility rules are domain-specific. HealthOS enforces HIPAA, SchoolOS enforces
FERPA, FinanceOS enforces SEC disclosure rules. These rules feed the
`VisibilityPolicy` consumed by the situation composer.

```python
# verticals/health/acl_rules.py
from k1.selfmodel.contracts.policy import RiskClass

HEALTH_VISIBILITY_RULES = [
    # Patient PHI is visible only to assigned clinicians + the patient themselves.
    {"actor_role": "clinician", "target_role": "patient",
     "predicate": "is_assigned_to", "risk": RiskClass.SAFETY_SENSITIVE},
    # Admin sees aggregate stats but not individual PHI.
    {"actor_role": "admin", "target_role": "patient",
     "predicate": "deny", "risk": RiskClass.HIGH},
]
```

### 2.4 `constitution.yaml`

Each vertical ships its own bootstrap constitution. The kernel loads it via
`ensure_bootstrap_constitution(body_path="verticals/<name>/constitution.yaml")`.

## 3. `SpaceGraphSnapshot` semantics across verticals

| Vertical | `space_id` example | Actor roles | Edge kinds |
|---|---|---|---|
| FamilyOS | `family:smith` | parent / child / guardian / elder | `parent_of`, `sibling_of`, `guardian_of` |
| HealthOS | `clinic:mayo:ward_3` | patient / clinician / caregiver / admin | `treating`, `caring_for`, `supervises` |
| SchoolOS | `school:lincoln:class_5b` | student / teacher / parent / admin | `enrolled_in`, `teaches`, `guardian_of` |
| FinanceOS | `fund:blackrock:portfolio_x` | investor / manager / advisor / analyst | `manages`, `advises`, `reviews` |
| GovOS | `city:austin:district_7` | citizen / officer / official / auditor | `represents`, `governs`, `audits` |
| AgriOS | `farm:johnson:field_n40` | farmer / agronomist / supplier / buyer | `operates`, `consults`, `supplies` |

The `role` and `kind` fields are free-form strings. The kernel never inspects them.
Domain-specific validation lives in the vertical's `acl_rules.py`.

## 4. Wiring checklist

To bring a new vertical online:

1. Create `verticals/<name>/` with the four files in §2.
2. Set `KernelConfig.selfmodel_space_id = "<vertical>:<instance>"` in the boot config.
3. Set `KernelConfig.enable_self_model = True`.
4. After `start_kernel()` returns the `KernelRuntime`, invoke the vertical's seeder:

   ```python
   from verticals.health.seeder import CareTeamSeeder
   from verticals.health.profile import MAYO_WARD_3_PROFILE
   seeder = CareTeamSeeder()
   seeder.seed_space_projection(runtime.self_model_bundle, MAYO_WARD_3_PROFILE)
   ```

5. Register the vertical's visibility rules with the policy evaluator:

   ```python
   from verticals.health.acl_rules import HEALTH_VISIBILITY_RULES
   runtime.self_model_bundle.evaluator.policy.rules[:] = HEALTH_VISIBILITY_RULES
   ```

6. Load the vertical's constitution at S2.6:

   ```python
   ensure_bootstrap_constitution(
       store=bundle.store,
       body_path="verticals/health/constitution.yaml",
   )
   ```

7. (Optional) Mount the vertical's UI client under `ui/<name>_web/` and tools under
   `verticals/<name>/tools/` (see M11/M15 family-tools reference implementation in
   `KERNEL_BOOTUP_PLAN.md`).

## 5. Anti-patterns

The following violate the layering and **must not** be done:

- **Do not import** from `verticals/<name>/` inside `k1/selfmodel/`. The kernel
  consumes domain data via the `IProjectionStorePort` contract only.
- **Do not add domain-specific fields** to `SpaceGraphSnapshot`, `ActorRef`, or
  `SpaceEdge`. If a vertical needs extra per-actor metadata, use the generic
  `dict[str, object]` payload on `ProjectedSelf.visible_attributes` (set by the
  composer from the snapshot).
- **Do not hardcode** vertical-specific labels (`[household]`, `[care_team]`,
  `[classroom]`) in `k1/concierge/prompt/builder.py`. The capsule renderer is the
  single source of truth for block titles via `space_graph_block`. If a vertical
  wants a custom label, override the capsule renderer's `_render_space_graph()` in
  a subclass and inject it via `KernelConfig`.
- **Do not write** to `bundle.store` from anywhere except a registered seeder or
  service. The `IProjectionStorePort.write_space()` method enforces
  `allowed_writers` — adding a writer means adding a constant like
  `<DOMAIN>_SEEDER_WRITER_ID = "verticals.<name>:seeder"` and registering it.
- **Do not bypass the constitution**. Every vertical declares its forbidden /
  must-ask / soft-warn social acts in its `constitution.yaml`. The
  `ConscienceDigest` is what gates LLM behavior — do not hardcode rules elsewhere.

## 6. Multi-vertical deployments

A single K1 process can serve multiple verticals by running one `KernelService`
session per vertical, each with its own `space_id`. The shared
`SelfModelServiceBundle` holds one `IProjectionStorePort` instance backed by SQLite;
rows are keyed by `space_id`, so the kernel naturally isolates verticals.

Example: a SchoolOS+FamilyOS hybrid running on the same device.

```python
config_family = KernelConfig(enable_self_model=True, selfmodel_space_id="family:smith",   session_id="sess-family")
config_school = KernelConfig(enable_self_model=True, selfmodel_space_id="school:lincoln:5b", session_id="sess-school")
runtime_family = await start_kernel(config_family)
runtime_school = await start_kernel(config_school)
# Two sessions, two space_ids, one selfmodel projection store, two constitutions.
```

Each session loads its own constitution body and its own visibility rules. The
two sessions never see each other's snapshots because `read_space(space_id)` only
returns the row whose `space_id` matches.

## 7. `SpaceContext` Protocol — the kernel's only vertical API boundary

Every vertical exposes itself to the kernel through exactly one Protocol:

```python
# k1/kernel/contracts/space_context.py
from typing import Protocol, runtime_checkable, Any

@runtime_checkable
class SpaceContext(Protocol):
    """The only type the kernel accepts from any vertical.
    Implement this on your vertical's profile dataclass.
    """
    space_id: str           # "family:smith" | "school:lincoln:5b" | "clinic:mayo:3"
    tenant_id: str          # opaque tenant identifier
    actors: list[Any]       # objects with .actor_id, .role, .display_name
    seed_memories: list[dict]
    session_config: dict
    preferred_language: str
```

`verticals/family/profile.FamilyProfile` implements `SpaceContext`.
`verticals/health/profile.CareTeamProfile` implements `SpaceContext`.
The kernel's `K1WebCoordinator` / `UiCoordinator` accepts `SpaceContext`, not a
vertical-specific class.

### 7.1 Why this matters

Prior to ADR-3, `K1WebCoordinator` held a `self.family_profile_obj: FamilyProfile`
slot — a hard dependency on one vertical. After M12, that slot becomes
`self.space_context: SpaceContext`. This is the only interface change that touches
the kernel when a new vertical is introduced.

**Kernel-side contract** (M12 change):

```python
# Before (FamilyOS-only):
self.family_profile_obj: FamilyProfile = family_profile

# After (vertical-agnostic):
self.space_context: SpaceContext = space_context
```

**Vertical-side** — no change needed if the profile dataclass already has the six
`SpaceContext` fields. For example:

```python
# verticals/health/profile.py — implements SpaceContext structurally
@dataclass(frozen=True)
class CareTeamProfile:
    space_id: str                   # required by SpaceContext
    tenant_id: str                  # required by SpaceContext
    actors: list[CareTeamMember]    # required by SpaceContext
    seed_memories: list[dict]       # required by SpaceContext
    session_config: dict            # required by SpaceContext
    preferred_language: str         # required by SpaceContext
    # domain-specific extras:
    organization: str
    consent_model: str              # "HIPAA"
```

### 7.2 Directory contract (ADR-3)

```
k1/                   ← kernel only — no domain knowledge
verticals/
  family/             ← FamilyProfile, SMITH_PROFILE, SpaceDataSeeder, ACL rules
  health/             ← (future) CareTeamProfile, CareTeamSeeder, HIPAA ACL rules
  school/             ← (future) ClassroomProfile, ClassroomSeeder, FERPA ACL rules
  finance/            ← (future) OrgProfile, OrgSeeder, SEC-visibility ACL rules
```

This layout is enforced by `test_module_layout.py` (added in M0): the test asserts
that nothing inside `k1/selfmodel/` imports from a vertical-specific path.

### 7.3 M13 migration — moving `k1/family/` to `verticals/family/`

M13 (planned) moves the existing `k1/family/*.py` to `verticals/family/*.py`.
Content is unchanged; only the import path changes:

```python
# Before (M13):
from k1.family.smith import SMITH_PROFILE

# After (M13):
from verticals.family.smith import SMITH_PROFILE
```

All tests under `tests/k1/family/` migrate to `tests/verticals/family/`.
No kernel code changes — the kernel only ever touches `SpaceContext`.

---

## 8. Quick checklist for code review

When reviewing a PR that adds a new vertical, confirm:

- [ ] No file under `k1/selfmodel/` is modified
- [ ] No file under `k1/concierge/` references the vertical name
- [ ] `verticals/<name>/profile.py` defines a `frozen=True` dataclass
- [ ] `verticals/<name>/seeder.py` is idempotent (re-running does not overwrite)
- [ ] `verticals/<name>/seeder.py` uses `SPACE_GRAPH_WRITER_ID` (or a vertical-specific writer ID registered via `allowed_writers`)
- [ ] `verticals/<name>/constitution.yaml` is signed (in production builds) or stub-signed (in tests)
- [ ] All test paths follow `tests/verticals/<name>/test_*.py`
- [ ] `KernelConfig.selfmodel_space_id` value uses the canonical `<vertical>:<instance>` format

## 9. References

- ADR-2 — Self-Model Is Domain-Agnostic (in `docs/plans/KERNEL_BOOTUP_PLAN.md`)
- ADR-3 — Domain Data Lives Under `verticals/` (in `docs/plans/KERNEL_BOOTUP_PLAN.md`)
- M0 Migration Plan — `docs/plans/KERNEL_BOOTUP_PLAN.md` § M0
- M12 — `K1WebCoordinator` accepts `SpaceContext` instead of `FamilyProfile` (in `KERNEL_BOOTUP_PLAN.md`)
- M13 — Move `k1/family/*.py` → `verticals/family/*.py` (in `KERNEL_BOOTUP_PLAN.md`)
- `k1/selfmodel/contracts/space_graph.py` — canonical data contracts
- `k1/selfmodel/ports/projection_store.py` — read/write API
- `k1/selfmodel/kernel/bootstrap.py` — `SelfModelServiceBundle` definition
- `k1/kernel/contracts/space_context.py` — `SpaceContext` Protocol (to be created in M12)
- `verticals/family/` — reference implementation (the family vertical)
