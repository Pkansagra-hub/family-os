# Calendar activity profile v1

Use this profile as procedural guidance only. The resolved capability contract, input schema, safety band, HIL policy, tool grants, and caller role remain authoritative.

## Chain of thought — always follow this order

1. **Discover** — Call `discover_capabilities` with `intent=<what the task requires>` and `domain=["calendar"]` before any write. If the capability name is already in the dispatch params, skip discovery.
2. **Read first** — Before any create/update/delete, call `tool.read.calendar.list_events` (by date range) or `tool.read.calendar.get_event` (by id) to confirm the target exists and retrieve its current state. Never skip this step for updates or deletes.
3. **Resolve ambiguity** — If the event title, start time, end time, timezone, or attendees are missing or ambiguous from the dispatch, use `submit_result` with `result_type=needs_clarification` — do NOT invent values.
4. **Write** — Only after confirming the target and having all required inputs, invoke the write capability (`tool.execute.calendar.create_event`, `tool.execute.calendar.update_event`, or `tool.execute.calendar.delete_event`).
5. **Confirm** — After the write, call `tool.read.calendar.get_event` with the returned event id to verify the change landed correctly. Include the confirmation in `final_answer`.

## Tool usage rules

- `tool.read.calendar.list_events` — required inputs: none (filter by `start`/`end` window and optional `member_filter`). Use to check for duplicates before creates and to fetch event ids before updates/deletes.
- `tool.read.calendar.get_event` — required input: `event_id`. Use to read current state before any mutation and to verify after writes.
- `tool.read.calendar.list_feeds` — required inputs: none (returns all feeds for the caller). Use before `connect_feed` or `disconnect_feed` to confirm the target feed exists.
- `tool.execute.calendar.create_event` — AMBER band. Required: `title`, `start`, `end`. Optional: `attendees`, `location`, `notes`, `visibility`. Run `list_events` over the same window first to detect duplicates.
- `tool.execute.calendar.update_event` — AMBER band. Required: `event_id` plus the fields to change. Never invent an `event_id`; always retrieve it via `list_events` or `get_event` first.
- `tool.execute.calendar.delete_event` — AMBER band. Required: `event_id`. Always confirm with `get_event` before deleting.
- `tool.execute.calendar.respond_to_invite` — AMBER band. Required: `event_id`, `response` (yes/no/maybe/tentative). Read the invite first with `get_event`.
- `tool.execute.calendar.set_visibility` — AMBER band. Required: `event_id`, `visibility`. Caller must be parent or guardian. Preserve parent/guardian role gates; ask if the intended audience is unclear.
- `tool.execute.calendar.connect_feed` / `disconnect_feed` — AMBER band. Required: `feed_source`+`account` / `feed_id`. Call `list_feeds` first to inspect current state. Caller must be parent or guardian.

## Duplicate-check rule

Before `create_event`: call `list_events` with a ±1 day window around the proposed start time. If an event with the same title and overlapping time already exists, return `needs_clarification` instead of creating a second entry.

## What NOT to do

- Do not use calendar tools for alerting reminders, shopping lists, recurring chores, or tasks unless the contract explicitly declares those capabilities.
- Do not put reasoning notes or provenance in event title, body, or attendee fields — only in approved metadata fields exposed by the contract schema.
- Do not act on cross-member or visibility-sensitive events without confirming the intended audience.
