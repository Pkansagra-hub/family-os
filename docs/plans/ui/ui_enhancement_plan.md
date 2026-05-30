I read the current UI code path end to end with three read-only explorers and then checked the live sections myself: index.html, app.js, and styles.css. The important architectural fact is this: FamilyOS now has the right base primitive for this next phase because app.js already writes `data-view` and `data-household-weather` onto `html/body`, and the CSS already has per-view room variables plus weather variables.

I would treat **Chat as the cognition layer/shell**, and the **seven product rooms** as: Home, Calendar, Tasks, Shopping, Reminders, Chores, Family Settings. Every milestone below must cover those seven rooms, with Chat providing the cross-room atmospheric language.

**North Star**
Build an environmental behavior system, not more UI.

No new widgets. No particle nonsense. No heavy glassmorphism. No dashboards. The work should make the same components feel governed by shared invisible physics:

- weather pressure
- room memory
- time of day
- cognitive mode
- urgency gravity
- edge dissolution
- quiet visual acoustics

The implementation center should be:

```text
app.js derives environmental state
  -> writes data-* + CSS variables
  -> styles.css maps that state into atmospheric behavior
  -> every room consumes the same environmental contract
```

**Milestone 1: Environmental State Contract**
Goal: create the one stable “physics model” before touching visuals.

Add a small environmental model in app.js, likely around the existing `state.householdWeather`, `applyShellState()`, and `_homeHouseholdWeather()`.

New state shape:

```js
state.environment = {
  view,
  weather,
  timePhase,
  cognitionMode,
  pressure,
  motion,
  clarity,
  warmth,
  density,
  lastVisitedByView
}
```

CSS output should stay simple:

```html
<body
  data-view="tasks"
  data-household-weather="moving"
  data-time-phase="evening"
  data-cognition-mode="execution"
  data-environment-motion="slow"
>
```

And CSS variables:

```css
--env-drift-x
--env-drift-y
--env-drift-duration
--env-clarity
--env-density
--env-warmth
--env-edge-dissolve
--env-gravity-x
--env-gravity-y
--env-breath-opacity
```

Coverage across seven rooms:

- Home: derives household pressure and global weather.
- Calendar: contributes time conflict pressure.
- Tasks: contributes execution pressure.
- Shopping: contributes supply/approval pressure.
- Reminders: contributes nudge/attention pressure.
- Chores: contributes household rhythm pressure.
- Family Settings: contributes safety/policy pressure.

Acceptance gate: changing room/weather/time changes CSS variables, but no visual drama yet.

**Milestone 2: Atmospheric Drift Engine**
Goal: make the shared shell breathe over 6-12 minute cycles.

Implement this mostly in styles.css at the bottom product-shell layer. The `app-shell` should remain the only painted shell surface. Do not reintroduce panel backgrounds on sidebar/header/composer.

Add ultra-slow keyframes:

```css
@keyframes envDrift {
  0%, 100% { background-position: 48% 48%, 50% 50%, 52% 52%; }
  50% { background-position: 52% 50%, 48% 52%, 50% 48%; }
}
```

Use variables to tune per condition:

- quiet: almost still
- calm: slow open drift
- moving: slightly broader drift
- decision: drift narrows toward action zones
- overload: denser, slower compression

Coverage:

- Home: global household drift.
- Calendar: cooler lateral drift, time-axis feeling.
- Tasks: forward/diagonal drift.
- Shopping: soft distributed green/teal drift.
- Reminders: warmer small nudge drift.
- Chores: rhythmic warm/green drift.
- Settings: cooler, stable, less motion.

Acceptance gate: drift must be almost invisible in a 10-second glance. It should be noticeable only when comparing screenshots minutes apart.

**Milestone 3: Cognitive Gravity**
Goal: important regions should attract the eye without borders or louder cards.

Add a normalized “focus gravity” contract. In app.js, each screen already computes priority-ish data:

- Home: `primaryMove`, `attentionCount`
- Calendar: conflicts / selected event
- Tasks: overdue/today/high-priority task
- Shopping: approvals / needed items
- Reminders: fired/overdue/due today
- Chores: due now / skipped / pending
- Settings: locked/private/review policy states

For each room, mark the current focus root with one shared attribute:

```html
data-gravity="primary|secondary|quiet"
```

or class:

```css
.env-gravity-primary
```

CSS behavior:

- primary region gets slight clarity increase
- nearby background fog thins by a tiny amount
- non-primary repeated rows diffuse slightly only when safe
- no scale jumps, no card glow blasts

Coverage:

- Home: current turn / day thread.
- Calendar: first conflict or selected next event.
- Tasks: next task / overdue lane.
- Shopping: pending approval or needed aisle.
- Reminders: fired/overdue reminder.
- Chores: due-now chore or assignee imbalance.
- Settings: policy review / sensitive controls.

Acceptance gate: user’s eye lands correctly, but screenshots still look restrained.

**Milestone 4: Presence Breathing**
Goal: the OS feels awake, not animated.

This belongs in existing living elements:

- sidebar orb
- chat concierge orb
- runtime pill orb
- composer horizon
- activity rail dot
- active nav dot
- Home pulse state

Add one shared breathing animation:

```css
@keyframes presenceBreath {
  0%, 100% { opacity: var(--breath-low); filter: blur(var(--breath-blur-low)); }
  50% { opacity: var(--breath-high); filter: blur(var(--breath-blur-high)); }
}
```

Cycle should be slow, around 8-14 seconds. Respect `prefers-reduced-motion`.

Coverage:

- Home: pulse pill and current-turn horizon.
- Calendar: today/now indicator breath.
- Tasks: due-now/active task indicator breath.
- Shopping: pending approval/needed indicator breath.
- Reminders: fired reminder indicator breath.
- Chores: due-now rhythm indicator breath.
- Settings: safety/status indicator breath.

Acceptance gate: no spinner feeling. No “AI is doing magic” animation. It should feel metabolic.

**Milestone 5: Memory Echoes**
Goal: rooms remember how they felt, without storing anything creepy or heavy.

Use local client memory only at first. On navigation, record:

```js
state.environment.lastVisitedByView[viewId] = {
  weather,
  timePhase,
  warmth,
  density,
  visitedAt
}
```

Optionally persist a tiny version in `localStorage`:

```text
familyos.roomMemory.v1
```

Do not store user content. Store only environmental summaries.

On revisit:

- room starts with a faint echo of its previous warmth/density
- then blends into current state over ~2-4 seconds
- if last visit was overload, keep only a tiny trace, not anxiety residue

Coverage:

- Home: remembers last household pressure.
- Calendar: remembers conflict/calm temporal tone.
- Tasks: remembers execution density.
- Shopping: remembers supply/approval state.
- Reminders: remembers nudge intensity.
- Chores: remembers household rhythm.
- Settings: remembers safety/privacy posture.

Acceptance gate: the room feels familiar, not haunted. No visible “history” UI.

**Milestone 6: Semantic Light Routing**
Goal: cognition mode changes lighting topology.

Add a derived `cognitionMode`:

```text
planning
reflection
execution
coordination
review
idle
```

Possible sources:

- Chat streaming/runtime phase via `_runtimePillState()`
- current view
- selected action type
- Home primary move
- activity rail running state
- settings safety state

CSS mappings:

- planning: wider horizontal washes
- reflection: softer center fog, lower edge contrast
- execution: clearer action horizon, composer gravity
- coordination: distributed warm nodes
- review: cooler, more structured, slightly higher clarity
- idle: open, quiet, slow

Coverage:

- Home: mode from primary household move.
- Calendar: planning/review.
- Tasks: execution.
- Shopping: coordination/execution.
- Reminders: review/coordination.
- Chores: coordination.
- Settings: review.

Acceptance gate: mode shift should be felt most in global atmosphere, not by repainting cards.

**Milestone 7: Edge Dissolution**
Goal: components stop ending like boxes.

Do this carefully. The current app has many useful panels and cards; do not delete their affordance. Instead add reusable dissolution layers:

```css
.env-condensation {
  mask-image: radial-gradient(...);
}

.env-edge-dissolve {
  box-shadow: none;
  border-color: transparent;
}
```

Apply mostly to large surfaces:

- page headers
- hero panels
- focus surfaces
- support rails
- detail rails
- chat welcome starter area
- composer horizon

Avoid applying it to dense rows where boundaries carry scanning value.

Coverage:

- Home: ambient stage edges dissolve.
- Calendar: focus surface and side rail.
- Tasks: workbench, inspector.
- Shopping: aisle/approval lanes.
- Reminders: timeline/focus surfaces.
- Chores: today/board lanes.
- Settings: safety stage and overview surface.

Acceptance gate: information remains scannable. Big surfaces feel like condensations; rows remain usable.

**Milestone 8: Temporal Light / Circadian Mode**
Goal: time of day changes emotional pacing without dark mode.

Use existing helpers like `_displayTimeZone()`, `_familyTimeZone()`, `_localDateIso()`, and browser device context.

Add:

```js
getTimePhase(date, timezone) =>
  dawn | morning | midday | afternoon | evening | late | night
```

Then set:

```html
data-time-phase="evening"
```

Behavior:

- morning: cooler eastward bloom
- midday: clearer, flatter, higher legibility
- afternoon: balanced
- evening: warmer lavender decay
- late/night: slower, quieter, lower contrast, less sharp motion
- weekend/holiday later: lower pressure, softer rhythm

Coverage:

- Home: global day rhythm.
- Calendar: strongest temporal axis.
- Tasks: late-night softening of work pressure.
- Shopping: evening warmth.
- Reminders: late-night quieting.
- Chores: weekend/routine tone.
- Settings: stable, low-motion at night.

Acceptance gate: no dark mode. Same UI, different emotional light.

**Milestone 9: Intelligent Blur Hierarchy**
Goal: blur means state, not decoration.

Define blur classes by semantic certainty:

```text
resolved -> clearer
in_progress -> softer edges
uncertain -> diffused
delegated -> background-soft
blocked -> denser, still
```

Sources already exist:

- activity `item.status`
- chat runtime phase
- task/reminder/chore statuses
- settings locked/private states
- calendar conflicts
- shopping approval states

Coverage:

- Home: unresolved household pressure diffuses non-primary background.
- Calendar: conflicts sharpen; tentative/secondary events soften.
- Tasks: active task clearer; backlog softer.
- Shopping: approvals clearer; pantry/background softer.
- Reminders: fired clearer; later reminders softer.
- Chores: due-now clearer; completed resolved/crystalline.
- Settings: locked/review states clearer, safe defaults quiet.

Acceptance gate: users can intuit “done vs in progress vs uncertain” before reading labels.

**Milestone 10: Visual Acoustic Pass**
Goal: make the UI sound quiet visually.

This is not a new engine. It is a restraint audit after the behavior systems exist.

Audit:

- icon stroke aggression
- row divider contrast
- uppercase labels
- micro-grid noise
- border leftovers
- too-many glows
- overactive hover states
- text rhythm and line-height
- animated elements count per viewport

Coverage:

- Home: fewer competing signals around hero/current turn.
- Calendar: preserve dense scan but lower noise.
- Tasks: reduce lane/card shout.
- Shopping: keep approval visible, reduce list chatter.
- Reminders: prevent nudge UI from feeling alarmist.
- Chores: avoid gamification visual noise.
- Settings: make safety feel calm, not security-console harsh.

Acceptance gate: screenshot should feel quieter than before even though more intelligence is running underneath.

**Milestone 11: Emotional Refraction**
Goal: household emotional load modulates the environment, not theme colors.

This should be the last milestone because it depends on the earlier contract.

Input sources:

- `state.currentAffect`
- household weather
- Home pressure
- activity status
- settings safety
- time phase
- cognition mode

Output dimensions:

```text
density
openness
diffusion
warmth
tension
clarity
motion
```

Do not create “happy/sad themes.” Do not map emotions to obvious colors. Refraction should be environmental:

- anxious/urgent: slightly denser, slower, more grounded
- warm/empathetic: softer distributed warmth
- calm: open, clearer
- playful: barely more buoyant, not silly
- neutral: baseline

Coverage:

- Home: strongest global refraction.
- Calendar: tension only when conflicts exist.
- Tasks: pressure without alarm.
- Shopping: coordination warmth.
- Reminders: nudge softness.
- Chores: rhythm warmth.
- Settings: safety steadiness.

Acceptance gate: nobody should say “the UI changed color because mood.” They should say “it feels calmer/tenser/open.”

**Implementation Order**
1. **State Contract First**
   Add `state.environment`, `deriveEnvironmentState()`, `applyEnvironmentState()`, and `data-*` attributes. No major visuals.

2. **CSS Variable Plumbing**
   Add tokens only. Wire `data-time-phase`, `data-cognition-mode`, `data-environment-motion`, and `data-environment-density`.

3. **Atmospheric Drift**
   One shared shell animation, weather/time/view controlled. Browser smoke for overflow.

4. **Cognitive Gravity**
   Add shared `data-gravity`/classes and apply to all seven rooms.

5. **Presence Breathing**
   One shared subtle rhythm across orb/dot/horizon elements.

6. **Temporal Light**
   Add circadian phase and per-phase CSS modulation.

7. **Memory Echoes**
   Local, tiny, non-content environmental memory.

8. **Blur Hierarchy**
   State-driven blur/clarity semantics.

9. **Edge Dissolution**
   Large-surface condensation pass across all seven rooms.

10. **Emotional Refraction**
   Combine affect + weather + cognition into final environmental modulation.

11. **Visual Acoustic Audit**
   Final restraint pass, removing noise introduced along the way.

**Validation Gates**
Every milestone should pass:

```powershell
node --check ui/web/static/app.js
git diff --check -- ui/web/static/app.js ui/web/static/styles.css ui/web/static/index.html
```

Browser probes must check:

- asset version bumped
- `body[data-view]`
- `body[data-household-weather]`
- new environment data attributes
- no body horizontal/vertical overflow
- no chat overflow
- all seven rooms open without layout shift
- reduced motion disables environmental animation
- mobile sidebar still works at <=900px

For screenshot smoke, check:

- Home
- Chat
- Calendar
- Tasks
- Shopping
- Reminders
- Chores
- Family Settings

**Key Rule**
This plan should never add a new visible feature to prove itself.

If a change requires adding a widget, it is probably wrong. The system should feel more intelligent because the air, clarity, gravity, and rhythm changed around the existing work.
