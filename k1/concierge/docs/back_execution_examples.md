# Back Execution: How It Works (With Examples)

**Status:** Living reference. Plain-language companion to `back_tool_contract_whiteboard.md`.
**Audience:** Anyone who wants to understand what changes in Fabric and how Back's ReAct loop will work.
**Date:** 2026-06-02

---

## 1. What Changes in Fabric

**Today,** Fabric is a toolbox catalog. Back searches for tools by typing keywords, gets a top-10 list, picks one that looks right, and calls it. Fabric runs the tool and says "done." That's it. No guardrails.

**Tomorrow,** Fabric becomes a **situated execution authority.** Instead of "here's a catalog, pick something," it says "given who you are, what household you're in, what resources are connected, and what the rules say — here's exactly what you're allowed to do right now, in what order, with what checks."

### The 10 New Pieces

| What's new | What it does in human terms |
|---|---|
| **GlobalProjectionStore** | The master list of every tool and connector that exists in the universe. SQLite, searchable. |
| **LocalProjectionStore** | What THIS household actually has connected — Riley's calendar, the family chore list, the shared shopping list. |
| **IdempotencyStore** | Prevents double-booking. If Back accidentally tries to create the same dentist appointment twice, the second call is blocked. |
| **SituatedResolver** | The brain. Takes a task ("add dentist for Riley Monday 3pm") and returns a verdict: CAN you do this? What checks must happen first? What tools are you allowed to use? |
| **PolicySelector** | The rulebook. "Parents can schedule for kids. Guests can't write to the calendar. AMBER-band sessions can't touch RED-band tools." |
| **VerificationPlanRunner** | The proof-checker. After Back says "I created the event," it reads it back from the calendar to confirm it actually exists. No trust — verify. |
| **ConnectorConstitution** | The instruction manual that ships WITH each connector. "Before you create a calendar event, you MUST list existing events to check for conflicts. Also check the person's chores and tasks." |
| **PromptPackBuilder** | The briefing packet. Takes all the resolution results and packages them into a compact, clean summary for Back to read. No raw database dumps. |
| **CapabilityNameParser** | Ensures tool names follow the rules: `tool.read.calendar.list_events`. Catches typos. |
| **ConnectorAliasNormalizer** | Translates human names to machine names. "Riley's calendar" → `calendar`. "Google Calendar" → `google_calendar_read`. |

---

## 2. New Meta-Tools Back Will Use

Back currently has: `discover_capabilities`, `invoke_capability`, `submit_result`, `recall_memory`.

The new surface:

| Meta-tool | What Back uses it for | Replaces what? |
|---|---|---|
| **`resolve_situation`** | "Here's my task. What am I allowed to do?" Returns a resolution envelope with: verdict, allowed actions, a briefing packet (PromptPack), and the exact tools Back can call. | Replaces `discover_capabilities` for execution. |
| **`invoke_capability`** | "Run this specific bound tool with these exact params." Now called by **binding_id** (a reference the resolver gave Back), not by Back copying a tool name from search results. | Same name, different contract. |
| **`submit_result`** | "I'm done. Here's what happened and here's the verification proof." Now **gated** — Back cannot say "completed" unless verification passed (or policy explicitly allows degraded completion). | Same name, enforcement added. |
| **`discover_capabilities`** | Demoted to catalog-browsing only. "What tools exist for weather?" Returns a list but with `allowed_next_actions=[]` — Back can browse but CANNOT invoke from this. | Demoted, not removed. |

---

## 3. How Back's ReAct Loop Will Work

**Today's flow** (the old way):

```
1. Back gets a task: "add dentist for Riley Monday 3pm"
2. Back searches: discover_capabilities("calendar", "create")
3. Fabric returns top-10 matches, scored
4. Back reads the list, picks "tool.execute.calendar.create_event"
5. Back copies the name, fills in params, calls invoke_capability
6. Fabric runs it, says "ok"
7. Back calls submit_result("completed")
8. Done. Nobody verified the event actually exists.
```

**Tomorrow's flow** (the new way):

```
1. Back gets a task: "add dentist for Riley Monday 3pm"
2. Back builds a RequestFrame:
   - Who: Riley
   - What: create calendar event
   - When: Monday 3pm
   - Where: (household context)

3. Back calls resolve_situation(RequestFrame, phase="connector_summary")

4. Fabric does a LOT of work behind the scenes:
   a. Resolves "Riley" → person_riley_001 (LocalProjectionStore)
   b. Finds Riley's connected calendar → connector_id="calendar"
   c. Loads the calendar constitution:
      "BEFORE creating an event, you MUST list existing events to check for
       conflicts. Also check Riley's chores and tasks at that time."
   d. Checks policy: is Back's actor (parent) allowed to write to Riley's calendar? → yes
   e. Checks safety band: is GREEN-band session OK for GREEN-band tool? → yes
   f. Finds the right capability bindings:
      - prerequisite_read: tool.read.calendar.list_events
      - primary_write: tool.execute.calendar.create_event
      - verifier: tool.read.calendar.get_event
   g. Determines verdict: can_execute_with_gate
      (you CAN do this, but you must run the prerequisite read first)

5. Back receives a PromptPack (the briefing):
   ┌────────────────────────────────────────────┐
   │ Verdict: can_execute_with_gate             │
   │                                            │
   │ Connector: Family Calendar                 │
   │ Before create: list events to check        │
   │   duplicates and time conflicts            │
   │ Check: Riley's chores and tasks            │
   │ After create: read back event to confirm   │
   │                                            │
   │ Allowed next action:                       │
   │   ✓ Run prerequisite: list_events          │
   │                                            │
   │ DO NOT call create_event yet               │
   │ (blocked until prerequisite completes)     │
   └────────────────────────────────────────────┘

6. Back reads the briefing and acts:
   "OK, I need to list events first. Then I can create."
   → Calls invoke_capability(binding_id="bind_list_riley_001")
   → Gets back: 3 events that week, no conflicts at Monday 3pm

7. Back calls resolve_situation again:
   "I completed the prerequisite read. Now what?"
   → Verdict changes to: can_execute
   → Allowed next action: create_event

8. Back invokes the write:
   → Calls invoke_capability(binding_id="bind_create_riley_001")
   → Fabric runs create_event
   → Fabric automatically runs verification: reads back the event
   → Confirms: event exists, title matches, time matches
   → Returns: InvocationObservation + VerificationObservation

9. Back calls submit_result("completed", evidence=[verification_observation])
   → Gate checks: verification passed? ✓
   → submit_result accepted
   → Done.
```

**The big shift in one sentence:** Back stops being a search-and-guess operator and becomes a contract-following executor. It doesn't decide WHAT to do — the constitution and resolver tell it. It decides HOW to do it within the guardrails they set.

**What Back NEVER does anymore:**

- Never invents tool names from scratch
- Never skips prerequisite reads ("I'll just create the event without checking")
- Never calls `submit_result(completed)` without verification proof
- Never invokes tools from raw catalog search results
- Never invokes tools that aren't in `allowed_next_actions[]`

---

## 4. Worked Examples

### Example 1 — Simple Read (no writes, no gates)

```
User: "What's on Riley's calendar this week?"
```

**Old way:** Back searches `discover_capabilities("calendar", "list")`, picks a name, calls it. Done.

**New way:**

```
1. Back builds RequestFrame:
   who: Riley
   what: list calendar events (read only)
   when: this week (Monday-Sunday)

2. Back calls resolve_situation(phase="connector_summary")

3. Fabric resolves:
   - Riley → person_riley_001
   - Her calendar → calendar connector, freshness: fresh
   - Constitution says: no prerequisites for reads
   - Policy says: parent reading child's calendar → allowed
   - Verdict: can_execute  ← NO gate this time! Pure read.

4. Back gets PromptPack:
   ┌───────────────────────────────────────────┐
   │ Verdict: can_execute                       │
   │ Allowed: tool.read.calendar.list_events    │
   │ Params needed: resource_id, time_window    │
   │ Go ahead — no prerequisites required.     │
   └───────────────────────────────────────────┘

5. Back calls invoke_capability(binding_id="bind_list_riley_001")
   → Returns: 5 events this week

6. Back calls submit_result("completed")
   → No verification needed (it was a read, not a write)
   → Done.
```

Key difference: Back didn't search a catalog. It asked the resolver "what am I allowed to do for this specific task" and got exactly one answer. No guesswork.

---

### Example 2 — Policy Denial (child actor, parent-only action)

```
User (Riley, age 8): "Move my dentist to Friday"
```

```
1. Back builds RequestFrame:
   who: Riley (self)
   what: update calendar event
   actor_role: child
   safety_band: GREEN

2. Back calls resolve_situation(phase="connector_summary")

3. Fabric resolves:
   - Riley → person_riley_001 ✓
   - Her calendar → connector=calendar, actor_permission=read_only

4. PolicySelector checks:
   - Calendar constitution says: update events → write operation
   - Riley's permission on her own calendar: read_only
   - Policy: child actors can read their own calendar but cannot write
   - Policy verdict: deny

5. Verdict: blocked_by_policy

6. Back gets PromptPack:
   ┌───────────────────────────────────────────┐
   │ Verdict: blocked_by_policy                │
   │ Reason: Child actors cannot modify        │
   │   calendar events directly.               │
   │                                           │
   │ Allowed next actions: [] (none)           │
   │                                           │
   │ Recovery: Ask a parent or guardian to     │
   │   make this change, or request permission │
   │   through HIL.                            │
   └───────────────────────────────────────────┘

7. Back calls submit_result("blocked",
     reason="child_actor_cannot_write_calendar")
   → Front tells Riley: "I can't move that appointment myself,
     but I can ask your dad to do it."
```

Back never even got to see the tool names. The policy gate blocked it before binding happened.

---

### Example 3 — Ambiguous Person (needs disambiguation)

```
User: "Add Aunt Sarah to the Saturday picnic"
```

```
1. Back builds RequestFrame:
   who: Aunt Sarah
   what: (inferred) add person to event
   person_refs: [{raw: "Aunt Sarah"}]

2. Back calls resolve_situation(phase="connector_summary")

3. Fabric resolves:
   - LocalProjectionStore.resolve_alias("Aunt Sarah") → 0 matches
   - Fuzzy search: "sarah" finds:
     - Sarah Johnson (contact, not a household member)
     - Sarah Williams (household guest, visited once)
   - 2 candidates → ambiguous

4. Verdict: needs_disambiguation

5. Back gets PromptPack:
   ┌───────────────────────────────────────────┐
   │ Verdict: needs_disambiguation             │
   │                                           │
   │ Could not resolve "Aunt Sarah" to a       │
   │ known household member.                   │
   │                                           │
   │ Candidates found:                         │
   │   1. Sarah Johnson (contact)              │
   │   2. Sarah Williams (household guest)     │
   │   3. None of these — add new person       │
   │                                           │
   │ Allowed next actions: []                  │
   │ Recovery: Ask user which Sarah           │
   └───────────────────────────────────────────┘

6. Back triggers HIL:
   "Which Sarah did you mean? I found Sarah Johnson
    from your contacts and Sarah Williams who visited before."

   User: "Sarah Johnson"

7. HIL response comes back. Back calls resolve_situation again:
   person_refs: [{raw: "Aunt Sarah", resolved_id: "contact_sarah_johnson"}]

8. Now resolves cleanly. Proceeds with event creation flow.
```

The key: the resolver doesn't guess. It surfaces the ambiguity and hands it to HIL.

---

### Example 4 — Missing Required Params (HIL for time)

```
User: "Schedule Riley's dentist"
```

```
1. Back builds RequestFrame:
   who: Riley
   what: create calendar event
   when: ??? (missing!)
   subject: dentist

2. Back calls resolve_situation(phase="connector_summary")

3. Fabric resolves:
   - Riley → person_riley_001 ✓
   - Calendar → connector=calendar, freshness=fresh ✓
   - But: calendar.create_event REQUIRES time_window
   - RequestFrame has NO time_window

4. Verdict: missing_required_params
   Sub-reason: missing_time_window

5. Back gets PromptPack:
   ┌───────────────────────────────────────────┐
   │ Verdict: missing_required_params          │
   │ Missing: time_window                      │
   │                                           │
   │ Calendar write requires:                  │
   │   - subject (have: "dentist") ✓           │
   │   - time_window (missing) ✗               │
   │                                           │
   │ Allowed next actions: []                  │
   │ Recovery: Ask user for date/time          │
   │                                           │
   │ HIL trigger: time_missing → ask_for_time  │
   └───────────────────────────────────────────┘

6. Back triggers HIL:
   "What day and time is Riley's dentist appointment?"

   User: "Monday at 3pm"

7. Back calls resolve_situation again:
   time_window: {start: "2026-06-08T15:00:00", end: "2026-06-08T16:00:00"}

8. Now: verdict = can_execute_with_gate → proceed with prerequisite reads.
```

The HIL question came from the constitution (the calendar connector declared `time_missing → ask_for_time`), not from Back guessing what to ask.

---

### Example 5 — Stale Projection (resource out of date)

```
User: "Add Jordan's dentist to his calendar"
Last sync of Jordan's Google Calendar: 6 hours ago
```

```
1. Back builds RequestFrame:
   who: Jordan
   what: create calendar event
   connector_hint: google_calendar_read

2. Back calls resolve_situation(phase="connector_summary")

3. Fabric resolves:
   - Jordan → person_jordan_001 ✓
   - His calendar resource: google_calendar_read
   - Freshness check: last_synced_at = 6 hours ago
   - Freshness threshold: 5 minutes
   - Freshness state: STALE

4. Verdict: stale_projection
   Sub-reason: stale_write_candidate

5. Back gets PromptPack:
   ┌───────────────────────────────────────────┐
   │ Verdict: stale_projection                 │
   │                                           │
   │ Jordan's Google Calendar was last synced  │
   │ 6 hours ago. The calendar data may be     │
   │ out of date — creating an event on stale  │
   │ data risks double-booking.               │
   │                                           │
   │ Allowed next actions: []                  │
   │ Recovery: Refresh the calendar first,     │
   │   or confirm with user                   │
   └───────────────────────────────────────────┘

6. Back triggers HIL:
   "Jordan's Google Calendar hasn't been refreshed in 6 hours.
    I should sync it first to check for conflicts. Refresh now?"

   User: "Yes, refresh it"

7. System refreshes the calendar → freshness becomes fresh
8. Back calls resolve_situation again → now verdict = can_execute_with_gate
9. Proceeds normally.
```

---

### Example 6 — Cross-Connector Task (promotes to Tier 3)

```
User: "Plan Riley's birthday party Saturday. Invite her soccer team.
       Make sure dad is free and check if we need to buy anything."
```

```
1. Back builds RequestFrame:
   who: Riley + soccer team members + dad (Jordan)
   what: create event + check availability + check shopping

2. Back calls resolve_situation(phase="connector_summary")

3. Fabric resolves:
   - Person refs: Riley, 8 soccer teammates, Jordan → resolved ✓
   - Resource refs detected:
     - calendar (for scheduling)
     - contacts (for team members)
     - shopping (for supplies check)
   - CapabilityNameParser.connectors_in_scope() → {"calendar", "contacts", "shopping"}
   - Multiple connector families detected → cross_connector

4. Verdict: promote_to_tier3
   Sub-reason: cross_connector

5. Back gets PromptPack:
   ┌───────────────────────────────────────────┐
   │ Verdict: promote_to_tier3                 │
   │                                           │
   │ This task spans 3 connector families:     │
   │   - calendar (scheduling)                │
   │   - contacts (team roster)               │
   │   - shopping (supply check)              │
   │                                           │
   │ Multi-connector tasks require the         │
   │ Planner and Orchestrator (Tier 3).        │
   │                                           │
   │ Escalation reason: cross_connector        │
   │ Companion resource roles:                 │
   │   - participants: 9 people to check       │
   │   - conflict_subjects: chores, tasks      │
   │                                           │
   │ Allowed next actions: []                  │
   │ Recovery: Task has been escalated         │
   └───────────────────────────────────────────┘

6. Back emits BackPromotionOutcome → FSM routes to Orchestrator

7. Orchestrator builds a PlanRequest, Planner runs SKETCH→EXPAND→VALIDATE→COMMIT:

   Sketch: "plan birthday party for Riley"

   Expand: reads all 3 connector constitutions:
     - Calendar: before create, list events for all 9 participants
     - Calendar: check chore conflicts for each child at party time
     - Contacts: read contact info for soccer team
     - Shopping: check if "party supplies" list exists

   Plan DAG:
     Wave 1 (parallel reads):
       ├── list_events(Riley)
       ├── list_events(Jordan)
       ├── list_events(teammate_1)
       ├── ... (8 more teammates)
       ├── list_chores(each child)
       └── check_shopping_list("party supplies")

     Wave 2 (conflict analysis):
       └── evaluate: any overlaps? any missing supplies?

     Wave 3 (conditional):
       ├── if no conflicts → create_event("Riley's party", Saturday)
       ├── if supplies needed → create_shopping_items([...])
       └── if conflicts → HIL with alternatives

     Wave 4 (verification):
       ├── read_after_write: get_event(party)
       └── read_after_write: get_shopping_list

8. Orchestrator executes the DAG deterministically — no LLM in the loop
   during execution. Reads happen in parallel where possible. Writes are
   sequenced after conflict analysis passes.

9. Result: party scheduled OR conflicts surfaced to user with alternatives.
```

Back's job here was SIMPLE: recognize this is too complex for one connector, build the frame, get the `promote_to_tier3` verdict, and escalate. It never tried to plan 15 steps. That's Tier 3's job.

---

### Example 7 — Verification Fails (write didn't persist)

```
User: "Add dentist for Riley Monday 3pm"
Back creates the event. Provider says "ok" (HTTP 200).
But the calendar adapter silently failed — the event doesn't actually exist.
```

```
1-7. (Same flow as the main dentist example)
     Back resolves → prerequisite list_events → no conflicts → creates event.

8. invoke_capability returns: {status: "success", event_id: "evt_abc123"}

9. Fabric's VerificationPlanRunner kicks in automatically:
   - Constitution says: "after create, read_after_write via get_event"
   - Runner builds a readback plan
   - Runner calls: get_event(event_id="evt_abc123")
   - Calendar responds: {found: false}

10. VerificationObservation:
    status: failed
    mismatch_summary: "Readback found no event for id evt_abc123.
                       Provider reported success but event does not
                       exist in calendar."

11. CapabilityFabric overrides the result:
    Instead of "success", returns:
    {status: "verification_failed",
     data: {verification_observation: {...}}}

12. Back receives the failure. PromptPack updates:
    ┌───────────────────────────────────────────┐
    │ Previous action: create_event            │
    │ Result: verification_failed              │
    │                                           │
    │ The event was reported as created but     │
    │ could not be found on readback.           │
    │                                           │
    │ Allowed next actions:                     │
    │   - Retry create_event                   │
    │   - Submit partial evidence              │
    │                                           │
    │ DO NOT submit completed                  │
    └───────────────────────────────────────────┘

13. Back CANNOT call submit_result("completed") — the gate blocks it.
    Back either retries or calls submit_result("partial") with the
    verification failure as evidence.
```

The critical point: provider said "200 OK" but the verifier proved the write didn't land. Without the verifier, Back would have called `submit_result(completed)` and the user would believe the appointment was booked — but it wasn't.

---

### Example 8 — Discovery Mode (just browsing, no execution)

```
User: "What weather tools do we have?"
```

```
1. Back builds RequestFrame:
   what: discover weather capabilities
   resolution_mode: catalog  ← key difference

2. Back calls resolve_situation(
     resolution_mode="catalog",
     phase="connector_summary"
   )

3. Fabric resolves:
   - FTS5 search: "weather" → finds weather connector
   - But resolution_mode=catalog → no execution authority
   - No resource resolution needed (not trying to do anything)
   - No policy check (not executing)
   - No binding (can't invoke from catalog results)

4. Verdict: can_execute  ← allowed to browse, not execute

5. Back gets PromptPack:
   ┌───────────────────────────────────────────┐
   │ Verdict: can_execute                      │
   │ Mode: CATALOG (browse only)               │
   │                                           │
   │ Found connector: Weather                  │
   │   Tools available:                        │
   │     - get_current_weather                 │
   │     - get_forecast                        │
   │                                           │
   │ ⚠ CATALOG ONLY — cannot invoke tools     │
   │   from catalog results. To use weather    │
   │   tools, build a RequestFrame with an     │
   │   execution intent and call               │
   │   resolve_situation in execution mode.    │
   │                                           │
   │ Allowed next actions: []                  │
   └───────────────────────────────────────────┘

6. Back tells Front: "We have a weather connector with current
   conditions and forecast tools."

7. If Back tries to invoke get_current_weather from this result:
   → Dispatcher blocks it. allowed_next_actions=[].
   → Back must go through resolve_situation in execution mode first.
```

Back can browse the catalog but can't fire tools from it. Same as you can window-shop but can't take merchandise without going through checkout.

---

## 5. The Pattern Across All Examples

```text
┌──────────────────────────────────────────────────┐
│ Every Back task follows the same spine:           │
│                                                  │
│ 1. Build RequestFrame                            │
│    (who, what, when — in structured form)        │
│                                                  │
│ 2. Call resolve_situation                        │
│    (Fabric figures out what's possible)          │
│                                                  │
│ 3. Read the PromptPack                           │
│    (verdict + allowed actions + guidance)        │
│                                                  │
│ 4. Act ONLY through allowed_next_actions         │
│    (prerequisite reads → writes → verify)        │
│                                                  │
│ 5. Submit result with evidence                   │
│    (completed needs verification proof)          │
└──────────────────────────────────────────────────┘
```

**What CHANGES per scenario is the VERDICT:**

| Verdict | Meaning | Back's response |
|---|---|---|
| `can_execute` | Go ahead, no gates | Invoke the bound tool |
| `can_execute_with_gate` | Do prerequisite reads first | Run prerequisite reads, then re-resolve |
| `needs_disambiguation` | Ask user to clarify | Trigger HIL with candidates |
| `missing_required_params` | Ask user for missing info | Trigger HIL for the missing field |
| `stale_projection` | Refresh data first | Trigger HIL or refresh, then re-resolve |
| `blocked_by_policy` | Stop, not allowed | Submit blocked with reason |
| `promote_to_tier3` | Too complex, escalate | Emit promotion outcome to Orchestrator |
| `cannot_execute` | Budget exhausted or duplicate | Submit cannot_execute |

---

## 6. Why This Scales to 500K+ Tools

### The Core Problem With Current AI Startups

Every AI startup right now is building the same thing: an LLM with a function-calling catalog. The model gets a list of tools, picks one, and calls it.

```text
Current approach:
  LLM receives: ALL tool schemas → picks one → calls it

  At 10 tools:     LLM sees 10 schemas. Fine.
  At 100 tools:    LLM sees 100 schemas. Context window filling up.
                   Model gets confused between similar tools.
  At 1,000 tools:  Impossible. Can't fit in context. Even if you
                   could, the LLM can't reliably pick the right one.
  At 100,000 tools: Not even theoretically possible. Tool discovery
                   becomes a search engine problem, not an execution problem.
```

Startups paper over this with "semantic search" — the LLM types a query, a vector database returns the top 10 matches, and the LLM picks from those. This is what we do TODAY in FamilyOS with `discover_capabilities`. It seems to work until you hit the fundamental limits.

### Why Semantic Search + LLM Choice Fails at Scale

**Problem 1: The LLM doesn't know what it doesn't know.**

The vector search returns the top 10 "calendar create" tools. But the LLM has no way to know that the 11th result — a `family_calendar_with_conflict_check` tool — is the one it actually needed. The LLM picks from what it's shown, not from what exists.

At 500K tools with 50 different calendar connectors (Google, Apple, Outlook, school calendars, doctor portals, sports team schedulers...), the top-10 list is a lottery. The right tool for THIS family's situation might be result #47, and the LLM never sees it.

**Problem 2: Tool knowledge rots in the prompt.**

Every startup writes prompt instructions like:

```
"When creating a calendar event, first check for conflicts by calling
list_events. Then verify the event was created by calling get_event."
```

This works for 5 tools. At 500,000 tools, you cannot hand-write instructions for every combination. And when a connector updates (Google Calendar API v4 → v5), your prompt instructions are now wrong but nobody noticed.

**Problem 3: Permission and conflict logic explodes combinatorially.**

```
Can child actor modify parent's calendar? → Depends on family rules
Can guest user see household member list? → Depends on privacy settings
Does this bank transaction need verification? → Depends on amount, actor, bank policy
Can this tool be used alongside that tool? → Depends on both tool contracts
```

Prompts can't encode this. Prompt engineering collapses under combinatorial complexity.

**Problem 4: Every execution is a fresh decision.**

The LLM decides what to do EVERY time. If the user says "book dentist for Riley," the LLM must remember (or be told) to check for conflicts, check chores, check guardians, verify the write... every single time. The plan is re-derived from scratch per invocation. This is slow, expensive, and unreliable.

### How Our Architecture Solves Each Problem

**Solution 1: Situated Projection Instead of Global Search**

```text
Current startups:  Search 500K tools → top-10 → LLM picks
Our approach:      Which 3 connectors does THIS household use?
                   → load ONLY those → resolve
```

`LocalProjectionStore` filters the universe before the LLM ever sees anything. A family of 4 with 5 connected apps has maybe 50 relevant tools, not 500,000. The resolver works with the household's actual world, not the global catalog.

How this scales: Adding 100 new connectors to the global catalog doesn't change what THIS household sees. Their local projection stays at 5 connectors until they explicitly connect more.

**Solution 2: Constitutions Ship With Connectors, Not Prompts**

```text
Current startups:  "Here's a tool schema. Good luck figuring out how to use it safely."

Our approach:      Every connector ships with a CONSTITUTION that declares:
                   - What prerequisite reads must happen
                   - What conflicts to check
                   - When to stop and ask a human (HIL gates)
                   - How to verify the write actually happened
                   - Who else is impacted (companion resources)
```

A new connector author doesn't need to update the Back prompt or the Planner prompt or any prompt. They write ONE constitution file alongside their connector manifest. The resolver reads it at runtime. The knowledge lives WITH the tool, versioned WITH the tool, proven WITH the tool.

How this scales: 500 connectors = 500 constitutions. Each is authored once by the connector developer. No central prompt needs updating. When Google Calendar v5 ships, the new constitution ships with it. The resolver loads the new version automatically.

**Solution 3: Policy Is Declared, Not Prompted**

```text
Current startups:  System prompt says "don't let children delete things"
                   LLM interprets this... sometimes correctly, sometimes not

Our approach:      PolicySelector evaluates hard rules BEFORE the LLM sees anything:
                   - Is this actor's role allowed for this operation? → YES/NO
                   - Is the safety band sufficient? → YES/NO
                   - Does the constitution require HIL? → YES/NO

                   If NO to any: verdict = blocked_by_policy
                   The LLM never even sees the tool as an option.
```

The LLM can't "forget" a policy rule because it never had the authority to decide. The policy gate is upstream of the LLM.

How this scales: Policy rules are per-connector, per-operation, per-role. You add a new connector, you declare its policy in its manifest. The PolicySelector evaluates it the same way as every other connector. No prompt changes.

**Solution 4: The LLM Follows Contracts, Doesn't Invent Plans**

```text
Current startups:  LLM sees task → LLM invents plan → LLM executes steps
                   Problem: LLM forgets steps, hallucinates tools, skips checks

Our approach:      LLM sees task → builds RequestFrame → resolver returns:
                   "Here's EXACTLY what you can do, in EXACTLY this order,
                    with EXACTLY these tools, and here's EXACTLY what to check."

                   The LLM's job shrinks from "figure out the plan" to
                   "execute these specific steps with these specific tools."
```

The constitution carries the plan. The LLM carries out the plan. This is the Dumb-LLM Principle: the model doesn't need to be smart about what to do — the contracts tell it.

How this scales: A connector for "doctor appointment booking" carries a constitution that says "before booking, list existing appointments, check insurance eligibility, verify patient identity." An LLM that has never seen a doctor booking tool before can still execute it correctly because the constitution tells it how.

**Solution 5: Verification Is Automatic, Not Hoped-For**

```text
Current startups:  Tool returns 200 OK → "done!" → submit completed
                   Nobody checks if the database actually has the data.

Our approach:      Tool returns 200 OK → VerificationPlanRunner reads it back
                   → confirms data exists → THEN submit completed is legal

                   If readback fails: submit completed is BLOCKED.
                   Even if the provider said "success."
```

This is the difference between "the API said ok" and "we proved the write landed." At 500K tools across banking, healthcare, scheduling — you cannot afford silent write failures.

**Solution 6: Tiered Routing Prevents the LLM From Drowning**

```text
Current startups:  Everything goes to the LLM. Complex multi-step task?
                   LLM tries to figure it out. Usually fails or hallucinates.

Our approach:      Tier 2 (Back, single connector, simple task):
                     LLM follows constitution, does 2-3 steps, done.

                   Tier 3 (Planner + Orchestrator, multi-connector):
                     No LLM in the execution loop. Planner builds a DAG.
                     Orchestrator executes deterministically.
                     Reads parallelize. Writes sequence. Conflicts gate.
```

The LLM handles simple, single-connector tasks. Cross-connector coordination ("plan the birthday party across calendar + chores + shopping") goes to deterministic execution — a DAG, not a ReAct loop.

---

## 7. The Difference From Current AI Startups, Summarized

| Dimension | Current AI Startups | Our Architecture |
|---|---|---|
| **Tool discovery** | Semantic search → top-K → LLM chooses | Situated projection: what does THIS household have connected? |
| **Knowledge location** | Prompt text (rots, doesn't version) | Connector constitution (ships with tool, versioned) |
| **Permission model** | Prompt nudges ("don't do bad things") | PolicySelector hard-gates BEFORE LLM sees tools |
| **LLM's job** | Figure out what to do AND how to do it | Execute specific bound steps from the resolver |
| **Verification** | Trust the API response | Read back and confirm — or submit is blocked |
| **Multi-step tasks** | LLM invents the plan each time | Constitution declares the plan; Orchestrator DAG executes |
| **Scaling model** | Better prompts, bigger context windows | More connectors with their own constitutions — no central bottleneck |
| **Failure mode at scale** | LLM hallucinates tools, skips checks, invents params | Hard gates block before execution. Can't skip prerequisite reads. Can't call submit completed without proof. |

**The one-sentence version:** Startups are making LLMs smarter so they can handle more tools. We're making the system dumber — in the good way — so the LLM doesn't need to be smart. The knowledge isn't in the model. It's in the contracts.

---

## 8. Verdict Reference Card

```
Back's job: Build the frame → call resolve_situation → read the verdict → act.

┌─────────────────────────┬──────────────────────────────────────────────┐
│ VERDICT                 │ WHAT BACK SHOULD DO                          │
├─────────────────────────┼──────────────────────────────────────────────┤
│ can_execute             │ Invoke the bound tool(s). Go ahead.          │
│ can_execute_with_gate   │ Run prerequisite reads first, then re-resolve│
│ needs_disambiguation    │ Ask user to pick from candidates (HIL)       │
│ missing_required_params │ Ask user for the missing field (HIL)         │
│ stale_projection        │ Refresh the resource or ask user (HIL)       │
│ blocked_by_policy       │ Stop. Submit blocked with the deny reason.   │
│ promote_to_tier3        │ Escalate to Planner/Orchestrator. Back's done│
│ cannot_execute          │ Submit cannot_execute with reason.           │
└─────────────────────────┴──────────────────────────────────────────────┘

RULES BACK MUST NEVER BREAK:
  ✗ Never invoke a tool not in allowed_next_actions[]
  ✗ Never skip a prerequisite read declared by the constitution
  ✗ Never call submit_result(completed) without verification proof
  ✗ Never invoke from catalog/discovery results
  ✗ Never invent capability names
```
