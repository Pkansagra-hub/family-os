# Future Work: Life Plans, Contextual Intelligence & Proactive Triggers

**Status:** Design Discussion (Not Yet ADR)
**Date:** 2026-02-08
**Context:** Architecture gap analysis after Epic 4.5 completion

---

## Problem Statement

Human lives revolve around time, location, and commitments. The system has a Temporal Resolution Engine but lacks two critical capabilities:

1. **No "Living Plan" entity** — multi-turn conversations that crystallize into persistent, UI-visible life plans
2. **No plan-driven proactive triggering** — contextual nudges based on time + location + schedule + active plans

### Motivating Example

User has a 40-50 turn conversation planning a gym and meal schedule. They settle on:
- Monday: Chest + high-protein meal prep
- Tuesday: Back + recovery meals
- Wednesday: Rest day
- Thursday: Legs + carb-loading
- Friday: Shoulders + lean meals

Today the system has no mechanism to:
1. Crystallize that conversation into a structured plan entity
2. Persist it across sessions (survives app close, device switch)
3. Show it in the UI ("My Gym Plan" — user taps and sees the schedule)
4. Generate proactive triggers ("It's 4:30, you need to leave for gym at 5:00, today is leg day")

---

## Why This Is Extension Work (Not Core Rewrite)

Every integration point already exists as a slot waiting to be filled:

### Life Plan Store

| Existing Slot | What It Provides |
|---|---|
| K0 `st_procedural` table (P20) | Pattern for habit/routine storage with `routine_id`, `cron_pattern`. Life Plans = new `st_life_plans` table, same pattern. |
| `active_plans` in `required_context` | AgentSpecValidator already allows `active_plans` as a valid SessionState section for tool context injection. It is a placeholder name with no backing store yet. |
| K0 P02 Write pipeline | Already handles persistence of structured data from K1 to K0 storage. Life Plans use the same write path. |
| SessionState Hot Core | A new `ACTIVE_PLANS` section (or sub-field of CONTROL) holds the current session's active plan references. |

### Plan Crystallization

| Existing Slot | What It Provides |
|---|---|
| Fabric Tool System | `crystallize_plan` is just another tool. Fabric can create as many tools as needed — this is trivial. |
| Concierge Intent Detection | UltraBERT Intent Head already classifies 8 intent classes. Adding plan-crystallization detection is a training data expansion, not an architecture change. |
| Planner `CommittedPlan` | Planner already outputs frozen execution DAGs. Plan crystallization produces a different kind of committed plan — a user-facing life plan, not an execution graph. But the pattern (conversation -> structured output -> persist) is identical. |
| `plan.confirmed` event | K1 bus already carries typed events. One new event type. |

### Proactive Triggers

| Existing Slot | What It Provides |
|---|---|
| Workflow Scheduler | Already has cron/event/proactive trigger types. Life Plans register their schedules as cron triggers ("weekdays at 4:30pm check gym plan"). |
| `k0.proactive.signal.v1` SSE | K0 already emits proactive signals to K1. Life Plan triggers use the same SSE channel. |
| Proactive Decision Engine | K1 already has `PROACTIVE_DECISION` agent type. It just gets richer context now (spatial + plan sections alongside temporal). |
| Reminder Agent | Already exists (`Reminder Agent — Execute Scheduled Reminder — Temporal Context Aware`). Life Plan reminders are a specialization. |

---

## Life Plan Entity Shape (Draft)

```python
@dataclass(frozen=True)
class LifePlan:
    plan_id: str                          # UUID
    user_id: str                          # Owner
    title: str                            # "My Gym & Meal Schedule"
    status: str                           # draft | confirmed | active | paused | completed | archived
    created_from_session: str             # session_id where crystallized
    created_at_iso: str                   # ISO timestamp
    updated_at_iso: str                   # Last modification

    # Schedule structure
    schedule: LifePlanSchedule            # Weekly/daily/custom recurrence
    items: tuple[LifePlanItem, ...]       # Individual plan items

    # Trigger configuration
    triggers: tuple[PlanTrigger, ...]     # Time/location/event triggers
    lead_time_minutes: int                # How early to nudge (default: 30)

    # Context for proactive agent
    proactive_context: str                # What to tell user ("today is leg day")
    requires_location: bool               # Whether location context enriches triggers

@dataclass(frozen=True)
class LifePlanItem:
    item_id: str
    day_of_week: int | None               # 0=Mon, 6=Sun, None=daily
    time_of_day: str | None               # "17:00" or None for all-day
    activity: str                         # "Legs + carb-loading"
    details: str                          # Extended notes
    duration_minutes: int | None          # Expected duration

@dataclass(frozen=True)
class PlanTrigger:
    trigger_id: str
    trigger_type: str                     # cron | event | location
    cron_expression: str | None           # "30 16 * * 1-5" (4:30pm weekdays)
    location_anchor: str | None           # "home" | "gym" | geo coords
    event_topic: str | None               # bus event that triggers
    message_template: str                 # "It's {time}, you need to leave for {activity}"
```

---

## Life Plan Lifecycle

```
Multi-turn conversation (40-50 turns)
        |
        v
[LLM detects plan-worthy conclusion]
        |
        v
crystallize_plan() tool call
        |
        v
Structured LifePlan (status: draft)
        |
        v
User confirms in UI (or via "yes, save this plan")
        |
        v
LifePlan (status: confirmed -> active)
        |
        v
Triggers registered in Workflow Scheduler
        |
        v
Persisted to K0 st_life_plans via P02
        |
        v
Loaded into SessionState.active_plans per session
        |
        v
Proactive agent fires context-aware nudges
```

---

## UI Contract (What User Sees)

1. **Plan List View** — All active plans with status badges
2. **Plan Detail View** — Full schedule, tap any item for details
3. **Plan Edit** — Pause, modify, archive a plan (triggers LLM re-crystallization)
4. **Proactive Notification** — "It's 4:30, you're at home. Leave in 18 min for leg day at the gym."

The notification is LLM-generated (not templated) using:
- Active plan item for today
- Current time (Temporal Resolution Engine)
- Current location (Spatial Context Engine, see architecture diagrams)
- External data (traffic via connectors, weather)

---

## K0 Storage: `st_life_plans` Table

Follows the `st_procedural` pattern from P20:

| Column | Type | Description |
|---|---|---|
| plan_id | TEXT PK | UUID |
| user_id | TEXT | Owner |
| title | TEXT | Human-readable plan name |
| status | TEXT | draft/confirmed/active/paused/completed/archived |
| schedule_json | TEXT | JSON-encoded LifePlanSchedule |
| items_json | TEXT | JSON-encoded list of LifePlanItem |
| triggers_json | TEXT | JSON-encoded list of PlanTrigger |
| created_from_session | TEXT | Session ID where plan was crystallized |
| created_at | TEXT | ISO timestamp |
| updated_at | TEXT | ISO timestamp |
| archived_at | TEXT | NULL until archived |

---

## Events

| Topic | Direction | Payload |
|---|---|---|
| `k1.plan.crystallized.v1` | K1 bus | `{plan_id, title, status: "draft", item_count}` |
| `k1.plan.confirmed.v1` | K1 bus | `{plan_id, title, trigger_count}` |
| `k1.plan.trigger.fired.v1` | K1 bus | `{plan_id, trigger_id, item, context}` |
| `k0.plan.persisted.v1` | K0 -> K1 SSE | `{plan_id, receipt_id}` |

---

## Absence Detection ("The Dog That Didn't Bark")

The proactive system only triggers on **positive events** — cron fires at 4:30pm, event arrives on bus, location geofence crossed. But humans break routines silently. Nobody triggers "user didn't walk the dog at 7am." Nobody triggers "user hasn't eaten in 8 hours" or "user skipped 3 gym sessions this week."

K0 P20 has `st_procedural` with learned habits and cron patterns. The Workflow Scheduler has cron triggers. But there's **no non-event detector** — something that watches for the absence of expected activity and raises a gentle signal.

### Why It Matters

The Temporal + Spatial + Plan context makes this powerful:

> "It's 7:45am, you're still at home (spatial), usually you've started your morning walk by 7:15 (P20 habit). Everything okay?"

> "You skipped gym 3 times this week (plan tracker). Your sleep has been under 5 hours (health connector). Want to adjust the plan to recover first?"

### How It Works

A **timer-based watcher** per active routine/plan item:
1. Each habit (P20) or Life Plan item has an expected action window (e.g., "walk 7:00-7:30am")
2. When the window closes without a confirming event (step count spike, location change to park, user check-in), the watcher fires a soft proactive signal
3. The signal goes to the Proactive Decision Engine with full context (spatial, temporal, plan, health)
4. The proactive agent decides: nudge, suppress (user is sick), or defer

### Integration Point

Additive — it's another trigger type in the Workflow Scheduler: `cron | event | location | absence`.

| Component | Change |
|---|---|
| Workflow Scheduler | Add `absence` trigger type alongside `cron`, `event`, `location` |
| TriggerSpec | New fields: `expected_window_start`, `expected_window_end`, `confirming_events[]` |
| P20 habits | Each learned habit auto-registers an absence trigger when confidence > 0.8 |
| Life Plan items | Each active plan item registers absence triggers for its schedule |
| Health/Activity connector | Provides confirming signals (step count, GPS movement, heart rate elevation) |

---

## Connector Synthesis Layer ("So What?" Engine)

P09 connectors exist in design: Health (Strava, Apple Health), Finance (Chase, budgets), Calendar (Google Calendar), Weather, etc. K0 schemas define `st_health`, `st_financial`, `st_calendar`, `st_shopping` tables. But raw connector data is just data. There's **no synthesis layer** that turns connector data into actionable context.

### The Problem

The gym meal plan says "high-protein meal prep Monday." Finance connector shows $50 left in grocery budget. Health connector shows 4 hours of sleep last night. Calendar shows meeting until 4pm. Weather shows thunderstorm at 5pm.

Today these are **5 separate data silos**. Nobody fuses them into:

> "Skip the gym today — you slept 4 hours, there's a thunderstorm, and your grocery budget is tight. Swap Monday's workout to Wednesday and do a home bodyweight session instead."

### Architecture

This isn't a new pipeline — it's a **Context Fusion step** that runs when proactive triggers fire, enriching the proactive agent's context with cross-connector signals. It sits between the trigger firing and the agent generating the message.

```
Trigger fires (cron/event/location/absence)
        |
        v
[Context Fusion Engine]  <-- NEW
   |  Reads: st_health (sleep, activity)
   |  Reads: st_financial (budget status)
   |  Reads: st_calendar (upcoming events)
   |  Reads: Weather API (current + forecast)
   |  Reads: active Life Plans (today's items)
   |  Reads: Spatial context (current location)
        |
        v
Enriched trigger context (structured summary)
        |
        v
Proactive Decision Engine (existing)
        |
        v
Proactive Agent generates contextual message
```

### Integration Point

Extension to the existing Proactive Decision Engine in Learning Loop.

| Component | Change |
|---|---|
| Proactive Decision Engine | Before spawning agent, call Context Fusion to enrich trigger payload |
| Context Fusion Engine | New module: reads K0 connector tables, produces structured summary |
| K0 Query Port | Already supports cross-table reads — fusion engine uses existing port |
| Proactive Agent prompt | Template gets enriched context sections (health, finance, calendar, weather) |

### What Context Fusion Produces

```python
@dataclass(frozen=True)
class FusedContext:
    trigger_reason: str               # "gym_plan_reminder"
    sleep_hours_last_night: float     # 4.2
    sleep_quality: str                # "poor"
    budget_remaining: float           # 50.00
    budget_category: str              # "groceries"
    next_calendar_event: str          # "Team standup 4:00pm"
    weather_current: str              # "Thunderstorm warning until 8pm"
    active_plan_item: str             # "Chest day + high-protein meal prep"
    location_context: str             # "at home"
    conflicting_signals: list[str]    # ["poor_sleep", "bad_weather", "tight_budget"]
    recommendation_hint: str          # "suggest_reschedule" | "proceed" | "modify"
```

---

## Family Coordination Mesh

### What ADR-0050 Provides (Foundation)

ADR-0050 (Multi-Device Family Sync Strategy) is purely **data sync infrastructure**:
- **Phase 1:** LAN sync via mDNS + TCP + LWW-CRDT (<50ms)
- **Phase 2:** P2P E2EE Internet sync (<500ms)
- **Presence metadata:** `device_id`, `online_status`, `coarse_location`, `motion_context`, `battery_level`
- **K0 Bridge P07:** Transport layer for device-to-device data
- **`households` table** in K0 PostgreSQL for family membership

ADR-0050 answers: "How do bytes get from Device A to Device B?" It treats the household as a **device group**, not a **coordination group**.

### What's Missing (The Coordination Layer)

This is a **family** OS. The Life Plan examples so far are single-user. But real life:

> "Mom has PT at 3pm (her plan), Dad has gym at 5pm (his plan), kid has soccer practice at 4pm (calendar connector). Who picks up kid? Who drives Mom?"

Today the system **cannot see across family members' plans and calendars** to surface conflicts or coordination needs.

### Required Components

**(a) Cross-User Plan Visibility (Privacy-Gated)**

Each family member opts in to share specific plans with the household. Not blanket sharing — granular:
- "Share my gym schedule with household" (opt-in per plan)
- "Share my calendar availability" (time blocks only, not details)
- "Keep my therapy appointments private" (never shared)

```python
@dataclass(frozen=True)
class PlanSharingPolicy:
    plan_id: str
    owner_user_id: str
    shared_with: str              # "household" | "specific_members" | "private"
    shared_member_ids: tuple[str, ...]  # When specific_members
    visibility_level: str         # "full" | "time_blocks_only" | "title_only"
```

**(b) Family Scheduler (Conflict Detection)**

A background process that cross-references opted-in plans + calendars across household members:

| Conflict Type | Example | Detection |
|---|---|---|
| Time overlap | Mom PT 3pm + kid pickup 3:30pm | Both need transport at same time |
| Resource contention | Only one car, two people need it | Shared resource tracking |
| Dependency chain | Dad gym at 5 depends on Mom being home for kid | One plan blocks another |
| Coverage gap | Both parents away 4-5pm, kid needs supervision | No caregiver available |

**(c) Coordination Nudges**

Proactive triggers that fire when conflicts are detected:

> "Dad, you need to pick up Alex at 4pm because Mom is at PT — this means leaving work 30 min early to make gym at 5."

> "Both your gym plans overlap with Alex's soccer practice today. One of you needs to adjust. Want me to suggest options?"

### Integration Point

Rides on ADR-0050's sync infrastructure. All additive.

| Component | Change |
|---|---|
| K0 `st_life_plans` | Add `sharing_policy` column |
| K0 Bridge P07 | Already syncs data — now also syncs opted-in plan summaries |
| Family Scheduler | New agent type: reads `family_plans` view, detects conflicts |
| `family_plans` view | Aggregated read-only view of opted-in Life Plans per household |
| Proactive Decision Engine | Family conflict triggers alongside individual triggers |
| `households` table | Already exists in K0 PostgreSQL — provides membership |

---

## Life Phase / Macro-Temporal Context

The Temporal Resolution Engine resolves "9" to "9:00 AM" and anchors to "today, this_week." But human life has **macro-temporal phases** that change everything for days/weeks/months:

- **Mom is 3 weeks post-surgery** (recovery phase — changes all plans, priorities, energy)
- **It's winter holiday break** (kids home, schedule disrupted, different meal patterns)
- **Dad has quarterly review next week** (high stress, reduced capacity, skip gym?)
- **Family vacation in 2 weeks** (prep phase — packing, pet care, stop mail)

These aren't events with a timestamp. They're **temporal envelopes** — periods that modify the context of everything else.

### Why It Matters

The proactive system should know "Mom is recovering" and factor that into **every nudge, every plan evaluation, every suggestion** for 6 weeks:

> Without life phase: "Time for your morning run!" (insensitive, Mom had surgery 3 weeks ago)
> With life phase: "Your recovery plan says gentle stretching this week. Want me to suggest a 10-minute routine?"

> Without life phase: "You haven't cooked this week" (guilt-inducing during holiday chaos)
> With life phase: "Holiday break mode — want me to switch to simple meal suggestions this week?"

### How It Works

A **Life Phase Detector** reads K0 beliefs + calendar + health connectors and maintains a `life_phases_active` list:

```python
@dataclass(frozen=True)
class LifePhase:
    phase_id: str
    user_id: str
    phase_type: str               # recovery | holiday | high_stress | travel_prep | grief | celebration
    label: str                    # "Post-surgery recovery"
    started_at: str               # ISO timestamp
    expected_end: str | None      # ISO timestamp or None (open-ended)
    severity: str                 # mild | moderate | significant | major
    affects: tuple[str, ...]      # ["exercise", "meal_plans", "energy", "schedule"]
    source: str                   # "user_stated" | "inferred_from_beliefs" | "calendar_pattern"
    modifications: dict           # {"exercise": "reduce_intensity", "meals": "simplify"}
```

### Detection Sources

| Source | Example | Phase Detected |
|---|---|---|
| User statement | "Mom had surgery Jan 15" | Recovery phase (6-8 weeks) |
| Calendar pattern | No work events for 2 weeks in December | Holiday break |
| Health connector | Sleep < 5hrs for 5 consecutive days | Stress/burnout phase |
| Belief accumulation | 3 mentions of "quarterly review" this week | High-stress period |
| Calendar + Travel | Flight booked + hotel booked + OOO calendar block | Travel/vacation phase |

### Integration Point

Extension to either Concierge's ACKING Core or as a background enrichment in the Learning Loop.

| Component | Change |
|---|---|
| SessionState | New sub-field: `control.life_phases_active: list[LifePhase]` |
| Context Fusion Engine | Reads active life phases, modifies recommendation hints |
| Proactive Agent prompt | Includes active life phases as ambient context |
| Beliefs Section | Life phase facts stored with temporal validity windows |
| Plan evaluation | Active phases modify plan trigger thresholds (gentler during recovery) |

### Lifecycle

```
Belief detected: "Mom had surgery January 15"
        |
        v
Life Phase Detector infers: recovery phase, 6-8 weeks, affects exercise+meals+energy
        |
        v
Stored in SessionState.control.life_phases_active
        |
        v
All proactive triggers check active phases before firing
        |
        v
Phase expires (8 weeks later) or user says "I'm cleared for exercise"
        |
        v
Phase archived, normal triggers resume
```

---

## Dependencies

- **Spatial Context Engine** — Already added to architecture diagrams (see `k1_cognitive_architecture_skeleton.mmd`, `k1/concierge/concierge.mmd`). Enriches proactive triggers with location awareness.
- **Workflow Scheduler** — Already exists. Life Plan triggers register as cron entries. Extended with `absence` and `location` trigger types.
- **Fabric Tool System** — `crystallize_plan` tool. Standard Fabric tool pattern.
- **K0 P02 Write** — Persistence path. Standard write pipeline.
- **K0 P09 Connectors** — Health, Finance, Calendar, Weather data sources feed the Context Fusion Engine.
- **K0 P20 Procedures/Habits** — `st_procedural` table provides learned habits for absence detection.
- **ADR-0050 Sync Infrastructure** — LAN + P2P E2EE sync carries family plan data across devices.
- **Learning Loop** — Proactive Decision Engine is the host for Context Fusion and absence/phase-aware triggering.

---

## Summary: Extension Points

| Concept | Integration Point | Trigger Type | Core Rewrite? |
|---|---|---|---|
| Life Plan Store | K0 `st_life_plans` + SessionState `active_plans` | — | No |
| Plan Crystallization | Fabric tool + Concierge intent detection | `plan.confirmed` event | No |
| Absence Detection | Workflow Scheduler | New: `absence` trigger | No |
| Connector Synthesis | Proactive Decision Engine | Context enrichment step | No |
| Family Coordination | Bridge sync + `households` + Life Plans | New agent type + family plan view | No |
| Life Phase Context | Beliefs + Calendar + Health connectors | SessionState sub-field + detector | No |

All six concepts are additive. Zero core rewrites. Every integration point already exists as a slot in the architecture.

---

## Open Questions

1. **Plan versioning** — When user modifies a plan mid-week, do we version or replace? (Lean: replace with audit trail)
2. **Multi-user plans** — Family gym plans where Mom and Dad have different schedules but share meal prep. Addressed by Family Coordination Mesh above.
3. **Plan conflict detection** — Two plans with overlapping time slots. Should the system warn? (Lean: yes, via Constraint Resolution Engine + Family Scheduler)
4. **Plan completion tracking** — Did user actually go to the gym? Requires activity connector (P09 Health) + Absence Detection working together.
5. **Conversation-to-plan boundary** — How does LLM know when a conversation has crystallized into a plan vs. still exploring? (Lean: explicit user signal "save this plan" + LLM suggestion "Would you like me to save this as a plan?")
6. **Absence sensitivity** — How many missed habits before nudging? Too early = nagging, too late = useless. (Lean: configurable per habit, default after 1 missed window with 30-min grace period)
7. **Life phase inference confidence** — When should the system infer a life phase vs. ask? (Lean: infer from 2+ corroborating signals, always confirmable by user)
8. **Connector data freshness** — How stale can connector data be for Context Fusion? (Lean: health/sleep < 4hrs, finance < 24hrs, calendar real-time, weather < 1hr)
9. **Family coordination privacy** — What happens when a shared plan reveals sensitive information? (Lean: `time_blocks_only` visibility level as default, full sharing requires explicit opt-in per plan)
