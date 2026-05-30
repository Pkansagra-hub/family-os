# Reminders activity profile v1

Use this profile as procedural guidance only. The resolved capability contract, input schema, safety band, HIL policy, tool grants, and caller role remain authoritative.

## Chain of thought — always follow this order

1. **Discover** — Call `discover_capabilities` with `intent=<what the task requires>` and `domain=["reminders"]` before any write. If the capability name is already in the dispatch params, skip discovery.
2. **Read first** — Before any create/update/delete/snooze/dismiss, call `tool.read.reminders.list_reminders` (filtered by recipient and/or status) or `tool.read.reminders.get_reminder` (by id) to confirm the target exists and retrieve current state. Never skip this step for mutations.
3. **Resolve ambiguity** — If the recipient, trigger kind, trigger time or location, timezone, or title are missing or ambiguous, use `submit_result` with `result_type=needs_clarification` — do NOT invent values.
4. **Write** — Only after confirming the target and having all required inputs, invoke the write capability (`tool.execute.reminders.create_reminder`, `tool.execute.reminders.update_reminder`, `tool.execute.reminders.snooze_reminder`, `tool.execute.reminders.dismiss_reminder`, or `tool.execute.reminders.delete_reminder`).
5. **Confirm** — After any write, call `tool.read.reminders.get_reminder` with the returned reminder_id to verify the change landed. Include the confirmation in `final_answer`.

## Tool usage rules

- `tool.read.reminders.list_reminders` — required inputs: none (filter by `recipient` and/or `status`). Use to check for duplicates before creates and to fetch reminder ids before mutations.
- `tool.read.reminders.get_reminder` — required input: `reminder_id`. Use to read current state before any mutation and to verify after writes.
- `tool.execute.reminders.create_reminder` — AMBER band. Required: `title`, `recipient`, `trigger`. `trigger` keys depend on kind: `time` → `{kind, fire_at}`; `location_enter|leave` → `{kind, location:{lat,lon,radius_m}}`; `event_offset` → `{kind, event_id, offset_minutes?}`. Run `list_reminders` for the same recipient first to detect duplicates.
- `tool.execute.reminders.update_reminder` — AMBER band. Required: `reminder_id` plus the fields to change. Blocked if reminder has already fired — use `snooze_reminder` instead. Never invent a `reminder_id`; always retrieve it via `list_reminders` or `get_reminder` first.
- `tool.execute.reminders.snooze_reminder` — AMBER band. Required: `reminder_id`, `snooze_until`. Use only for reminders that have already fired. Use `update_reminder` if the reminder has not fired yet.
- `tool.execute.reminders.dismiss_reminder` — AMBER band. Required: `reminder_id`. Use when recipient acknowledged the alert and no further action is needed.
- `tool.execute.reminders.delete_reminder` — AMBER band. Required: `reminder_id`. Use to cancel a scheduled (not yet fired) reminder. If already fired, use `dismiss_reminder` instead.
- `tool.execute.reminders.fire_reminder` — **SYSTEM ONLY** — the scheduler calls this automatically. Never invoke it from LLM-initiated tasks.

## Duplicate-check rule

Before `create_reminder`: call `list_reminders` filtered by `recipient` and `status=scheduled`. If a reminder with the same title and overlapping trigger time already exists for that recipient, return `needs_clarification` instead of creating a duplicate.

## Cross-member guard

If `recipient` differs from the task's acting member, the caller must be `guardian` or higher. If the task dispatch does not confirm the caller role satisfies this, return `needs_clarification` before writing.

## What NOT to do

- Do not use reminder tools for calendar appointments, recurring chores, or task to-dos — a reminder fires an alert, it does not reserve time or assign work.
- Do not invoke `fire_reminder` from any LLM-initiated task context — it is scheduler-only.
- Do not put reasoning notes or provenance in the `title` or `message` fields — only in approved metadata fields exposed by the contract schema.
- Do not snooze a reminder that has not yet fired — use `update_reminder` to shift its trigger instead.
