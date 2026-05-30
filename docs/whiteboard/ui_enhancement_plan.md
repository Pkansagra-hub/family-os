# FamilyOS UI Enhancement Plan

## Direction

The current UI is attractive and information-rich, but many screens expose every control, filter, count, and detail at once. The next design direction is not to remove power. It is to make power progressive.

Default screens should feel calm and immediately useful. Deeper operational detail should be available through intentional drill-down: expanders, drawers, focused modes, advanced toggles, and detail panels that appear only when the user asks for them.

## Product Principle

Each app should support four layers:

1. Glance layer: what matters now, in one scan.
2. Action layer: the one or two actions the user is most likely to take next.
3. Work layer: lists, boards, calendars, filters, and editing controls.
4. Audit layer: metadata, policy, traces, IDs, histories, and system detail.

The default view should show layers 1 and 2. Layer 3 should be one click away. Layer 4 should be intentionally tucked behind advanced/detail surfaces.

## Shared Design Rules

- Use a 1.618-based layout rhythm where it helps: primary work area plus smaller supporting area.
- Do not show every stat card if a single meaningful summary would do.
- Replace always-visible side panels with contextual drawers on smaller or calmer default screens.
- Keep filters collapsed into concise filter chips or a `More filters` control unless they are central to the task.
- Use empty space deliberately. A screen can feel premium because it chooses not to shout.
- Preserve expert workflows through focused modes, not through permanently dense defaults.
- Keep system/debug language secondary: `Behind the scenes`, `Advanced`, or `Details`, not primary UI.

## Milestone 0: Shared Progressive Disclosure Foundation

Goal: Create reusable UI patterns that every app can use consistently.

Status: Foundation implemented. App-specific milestones can now migrate existing one-off sidebars, detail panels, filters, and empty states onto the shared progressive-disclosure classes.

Scope:

- Add shared CSS tokens for calm density, compact density, detail drawers, quiet summary cards, and advanced panels.
- Standardize app page structure: header, summary strip, primary workspace, optional support rail/drawer.
- Define shared classes for `app-focus-card`, `app-detail-drawer`, `app-advanced-section`, `app-filter-row`, and `app-empty-state`.
- Keep the current visual language, but reduce default surface area and control noise.

Acceptance criteria:

- Every app can express overview, focused work, and detail states using shared patterns.
- No app needs one-off card nesting to achieve progressive disclosure.
- Existing urgent/selected state tints remain intact.

Implementation notes:

- Added shared density, summary, workspace, support-rail, drawer, filter, advanced-section, and empty-state CSS primitives in `ui/web/static/styles.css`.
- Added generic drawer open/close and filter-row expansion hooks in `ui/web/static/app.js` using `data-app-*` attributes.
- Bumped static assets in `ui/web/static/index.html` so the foundation loads as `v=37`.

## Milestone 1: Home

Goal: Make Home feel like a family cockpit, not a dashboard dump.

Status: Implemented. Home now leads with a `Today at a glance` focus card, keeps full metrics behind `Show more family status`, shows one latest activity event, and prioritizes natural quick actions.

Current issue:

- Home now has good proportions, but still defaults to stats plus activity plus actions as separate blocks.

Plan:

- Keep the golden-ratio structure from the current pass.
- Replace the four equal stat cards with a calmer `Today at a glance` strip: one primary summary plus three compact signals.
- Make `Recent Activity` show only the latest meaningful family event by default, with `View timeline` for depth.
- Keep Quick Actions in the minor column, but prioritize natural outcomes: `Plan today`, `Add task`, `Schedule`, `Ask Concierge`.
- Add a `Show more family status` affordance for expanded metrics.

Acceptance criteria:

- User can understand the day in under five seconds.
- No more than one large card competes for attention.
- Full stats remain reachable without crowding the first view.

## Milestone 2: Chat

Goal: Make Chat feel like a human concierge workspace, not a chatbot plus debug surface.

Status: Implemented. Chat now defaults to two outcome-focused starters, keeps extra ideas behind `More ideas`, fades the welcome into conversation history, keeps system details quiet unless opened or active, and preserves reasoning as secondary detail under the useful response.

Current issue:

- The new chat surface is calmer, but the starter panel can still feel like a control panel if it grows.

Plan:

- Keep the shared golden conversation column for welcome, messages, and composer.
- Make conversation starters adaptive and fewer by default: show two primary starters and a `More ideas` expander.
- Keep `Behind the scenes` collapsed unless work is active or the user opens it.
- Final answers should lead with the useful response; reasoning and trace details stay secondary.
- Add a subtle state transition from empty welcome to conversation history so the UI feels alive instead of swapping abruptly.

Acceptance criteria:

- Empty chat feels like an invitation, not a menu.
- System details never dominate unless explicitly opened.
- The composer remains visually connected to the conversation column.

## Milestone 3: Calendar

Status: Implemented in `ui/web/static` as the default `Today and next` scheduling surface, then refined with a stronger golden-ratio opening composition, richer next-event hero, preserved Month/Week/Day power modes, and day/event details in the shared drawer.

Goal: Make Calendar default to the user's next scheduling decisions, while keeping dense week/day power available.

Current issue:

- Week/day calendar views and selected-day lists expose a lot at once.

Plan:

- Default to a calm `Today and next` view: next event, conflicts, and upcoming family blocks.
- Keep Month/Week/Day as explicit modes, but do not make dense grids the first mental load.
- Move selected-day event details into a drawer that opens from a day or event click.
- Use `Show full week grid` as the deeper mode for power scheduling.
- Keep color-coded events, but reduce chrome around secondary metadata.

Acceptance criteria:

- User sees today's most important schedule information first.
- Dense time-grid complexity is available but not the default cognitive burden.
- Clicking a day or event reveals detail without crowding the base screen.

## Milestone 4: Tasks

Status: Implemented in `ui/web/static` as a next-move task surface with Today/Overdue/Needs decision signals, compact list selection, quiet secondary filters, preserved List/Board/Focus modes, and selected-only task detail.

Goal: Make Tasks about what needs doing next, not every task dimension at once.

Current issue:

- Stats, lists, filters, search, task rows, and details can all appear simultaneously.

Plan:

- Default to `Today`, `Overdue`, and `Needs decision` as the primary task focus.
- Collapse list selection into a compact dropdown or side drawer unless the user is managing lists.
- Show filters as a quiet summary row with `More filters` for secondary facets.
- Detail panel appears only after a task is selected; otherwise show a helpful empty detail state or hide it.
- Keep board/focus modes, but make `List` the calm default for broad task review.

Acceptance criteria:

- Default view answers: what should I handle now?
- List and filter complexity is discoverable but not permanently visible.
- Detail panel does not occupy space when no task is selected.

## Milestone 5: Shopping

Goal: Make Shopping feel like an active list first, with approvals and list management as deeper layers.

Current issue:

- List navigation, filters, item details, search, and status counts compete even for a tiny shopping list.

Plan:

- Default to the active list and needed items.
- Hide empty status counts unless they indicate a problem, approval, or high-priority item.
- Make aisles, approvals, rejected items, and list metadata secondary modes.
- Detail panel opens only when an item is selected.
- Add a compact `Add quickly` path for common items.

Acceptance criteria:

- A small shopping list looks small and calm, not like a database screen.
- Approval and list-management power remains one click away.
- Item details do not consume permanent space when nothing is selected.

Status: Implemented. Shopping now opens to the active list and needed items, with a compact add-quickly path, quiet signal cards, list selection and filters behind compact controls, aisle/approval modes one click away, and item details only after selection.

## Milestone 6: Reminders

Goal: Make Reminders feel like a nudge system, not a full event log by default.

Current issue:

- Reminder counts, recipients, filters, timeline rows, search, and detail cards are all visible together.

Plan:

- Default to grouped reminders: `Due now`, `Today`, `Later`, with collapsed historical/dismissed groups.
- Keep recipient filtering, but move the recipient list into a compact selector or drawer.
- Show only attention-worthy counts in the summary strip.
- Detail panel appears after selecting a reminder; otherwise it should be hidden or show one calm snapshot.
- Advanced scheduling metadata remains in the detail drawer.

Acceptance criteria:

- User can quickly see what reminders need action.
- Long reminder lists remain navigable without overwhelming the top-level screen.
- Recipient and status filters are available but not visually dominant.

Status: Implemented. Reminders now opens as a nudge-first surface with due-now/today/later signals, a compact recipient selector, quieter filters/search, collapsed dismissed history, board/focus modes preserved, and details only after selecting a reminder.

## Milestone 7: Chores

Goal: Make Chores about household rhythm and responsibility, while preserving board/reward depth.

Current issue:

- Assignees, board columns, filters, reward states, selected chore details, and stats appear together.

Plan:

- Default to `Today in chores`: due now, upcoming, and done summary.
- Make assignee selection a compact row or drawer instead of a persistent wide sidebar.
- Keep board/list/rewards modes, but make the default view lighter when chore count is low.
- Detail panel appears only after selecting a chore.
- Points and rewards are summarized, with deeper reward mechanics behind the `Rewards` mode.

Acceptance criteria:

- With one chore, the screen should not feel like a full kanban system.
- Parents can still manage templates, assignments, and rewards when needed.
- Child/family-facing progress stays easy to scan.

Status: Implemented. Chores now opens as a `Today in chores` rhythm surface with due-now/upcoming/done signals, compact assignee selection, quiet filters/search, preserved Today/Board/List/Rewards modes, deduped assignees, and details only after selecting a chore.

## Milestone 8: Family Settings

Goal: Make Settings feel safe and understandable before showing policy mechanics.

Current issue:

- Privacy rules, sensitive terms, policy snapshot, IDs, counts, and capabilities are visible as technical controls.

Plan:

- Default to a `Family safety overview`: privacy posture, kid locks, feature availability, and items needing review.
- Move raw policy IDs, rule counts, and advanced visibility matrices behind `Advanced policy details`.
- Group settings by user intent: `Privacy`, `Kid permissions`, `Feature access`, `Sensitive terms`.
- Use disclosure sections so parents can review one category at a time.
- Keep admin controls explicit and protected from accidental edits.

Acceptance criteria:

- Parent can understand safety posture without reading policy internals.
- Advanced details remain available for debugging and audits.
- Dangerous or sensitive controls require deliberate interaction.

Status: Implemented. Family Settings now opens as a golden-ratio `Family safety overview` with parent-first posture signals, separate Privacy/Kid permissions/Sensitive terms/Feature access categories, raw policy IDs/counts behind `Advanced policy details`, and admin update controls kept inside that deliberate disclosure.

## Milestone 9: System Views

Goal: Keep Timeline, Dashboard, and Session State powerful but clearly technical.

Current issue:

- System surfaces can leak into the family-product mental model.

Plan:

- Label these as `Technical` or keep them under the existing System nav.
- Default each system page to a calm health summary.
- Move raw logs, session sections, latency, bytes, and traces into expandable advanced panels.
- Keep links from family apps into specific system details only when helpful.

Acceptance criteria:

- Family-facing apps do not feel like system consoles.
- Debug information remains reachable for development and support.
- Technical views are useful without competing with core family workflows.

## Milestone 10: Cross-App Validation

Goal: Prove the lighter design works across real app states.

Validation checklist:

- Empty state, low-data state, and high-data state for every app.
- Desktop and mobile screenshots for each app.
- No horizontal overflow.
- Text does not overlap or truncate awkwardly.
- Detail drawers and expanders are keyboard accessible.
- Primary action is visible without exposing all secondary actions.
- Existing app workflows still work: create, edit, filter, select, and remove.

Implementation checks:

- Run `node --check ui/web/static/app.js` after JS edits.
- Run editor diagnostics for changed files.
- Run `git diff --check -- ui/web/static/app.js ui/web/static/styles.css ui/web/static/index.html`.
- Bump static asset versions in `ui/web/static/index.html` after JS/CSS changes.
- Use browser smoke tests to verify each milestone's default and expanded states.

## Suggested Execution Order

1. Milestone 0: shared progressive disclosure foundation.
2. Milestone 1: Home, because it sets the overall product rhythm.
3. Milestone 2: Chat, because it is the emotional face of FamilyOS.
4. Milestone 4: Tasks, then Milestone 6: Reminders, because both are high-frequency action screens.
5. Milestone 3: Calendar, because it has the most complex visual density.
6. Milestone 5: Shopping and Milestone 7: Chores, because both need low-data calm states.
7. Milestone 8: Family Settings, because it needs careful safety wording.
8. Milestone 9: System Views.
9. Milestone 10: cross-app validation and polish.

## Definition Of Done For Each App Milestone

- The default view shows only what a normal family user needs first.
- The user has an obvious path to deeper detail.
- Advanced/system information is available but not front-loaded.
- The screen still works for power users.
- The design uses shared patterns rather than one-off layout hacks.
- Browser screenshots confirm the screen feels calmer, not emptier.
