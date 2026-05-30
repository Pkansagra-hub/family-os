# Chores activity profile v1

Use this profile as procedural guidance only. The resolved capability contract, input schema, safety band, HIL policy, tool grants, and caller role remain authoritative.

## Chain of thought - always follow this order

1. **Discover** - Call `discover_capabilities` with `intent=<what the task requires>` and `domain=["chores"]` before any write. If the capability name is already in the dispatch params, skip discovery.
2. **Read first** - Before creating, assigning, completing, skipping, reopening, or deleting chore state, call `tool.read.chores.list_chores` or `tool.read.chores.chore_summary` as appropriate to inspect existing templates, pending occurrences, status, assignee, and points context.
3. **Resolve ambiguity** - If the chore template, occurrence, assignee, due time, recurrence, completion status, or parent/guardian authority is missing or ambiguous, use `submit_result` with `result_type=needs_clarification` - do NOT invent template ids, occurrence ids, member ids, or points.
4. **Write** - Only after confirming the target and having all required inputs, invoke the write capability (`tool.execute.chores.create_template`, `tool.execute.chores.update_template`, `tool.execute.chores.delete_template`, `tool.execute.chores.assign_chore`, `tool.execute.chores.complete_chore`, `tool.execute.chores.skip_chore`, or `tool.execute.chores.reopen_chore`).
5. **Confirm** - After any write, call `tool.read.chores.list_chores` for the affected assignee/template/status or `tool.read.chores.chore_summary` when points changed. Include confirmation in `final_answer`.

## Tool usage rules

- `tool.read.chores.list_chores` - required inputs: none. Use filters (`assigned_to`, `status`, `due_before`, `template_id`) to inspect pending/done/skipped occurrences, avoid duplicate templates/assignments, and find occurrence ids before mutations.
- `tool.read.chores.chore_summary` - required inputs: none. Use for points totals, leaderboards, weekly reports, and verification after completions that change points.
- `tool.execute.chores.create_template` - GREEN band. Parent/system only. Required: `title`. Optional: `description`, `assigned_to`, `frequency`, `base_points`, `visibility`. `frequency` may be `daily`, `weekly`, `monthly`, `once`, or a natural phrase such as `every 3 days`. Use for recurring chores, not one-shot tasks.
- `tool.execute.chores.update_template` - GREEN band. Parent/system only. Required: `template_id` plus fields to change. Use `is_active=false` to pause a chore instead of deleting when the parent asks to pause. `frequency` may be canonical or a natural recurrence phrase.
- `tool.execute.chores.delete_template` - GREEN band. Parent/system only. Required: `template_id`. Use only when the parent wants the chore removed permanently; this soft-deletes the template and pending occurrences.
- `tool.execute.chores.assign_chore` - GREEN band. Guardian/parent/system only. Required: `template_id`, `assigned_to`. Optional: `due_at`, `points_awarded`, `visibility`. Use to create or override a specific occurrence assignment.
- `tool.execute.chores.complete_chore` - GREEN band. Child/elder/guardian/parent/system. Required: `occurrence_id`. Optional: `completed_by`, `points_override`. Use when the assignee or authorized adult says the chore was done.
- `tool.execute.chores.skip_chore` - GREEN band. Child/elder/guardian/parent/system. Required: `occurrence_id`. Optional: `skip_reason`. Use when a chore is explicitly excused or skipped; do not use for completed chores.
- `tool.execute.chores.reopen_chore` - GREEN band. Parent/system only. Required: `occurrence_id`. Optional: `reason`. Use to undo a mistaken completion/skip and return the occurrence to pending.

## Duplicate-check rule

Before `create_template`: call `list_chores` and compare existing chore titles/frequencies for the same assignee or family pool. If a matching active recurring chore already exists, return `needs_clarification` instead of creating another template.

Before `assign_chore`: call `list_chores(template_id=<id>, status="pending")`. If the same assignee already has a pending occurrence in the requested due window, return `needs_clarification` instead of creating a duplicate assignment.

## Role and reward guard

Template creation/update/delete and reopening are parent/system actions. Assignment is guardian/parent/system. Child callers may complete or skip allowed occurrences, but parent-only point overrides and reward-sensitive changes must not be inferred from free text.

## What NOT to do

- Do not use chore tools for one-shot tasks, calendar events, reminders, or shopping items unless the selected contract explicitly supports that operation.
- Do not complete or skip a chore without identifying the occurrence; use `list_chores` first when only the title or assignee is known.
- Do not delete a chore template when the user asks to pause it; use `update_template(is_active=false)`.
- Do not award, override, or redeem rewards unless the selected schema and caller role explicitly permit it.
