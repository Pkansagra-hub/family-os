# Tasks activity profile v1

Use this profile as procedural guidance only. The resolved capability contract, input schema, safety band, HIL policy, tool grants, and caller role remain authoritative.

## Chain of thought - always follow this order

1. **Discover** - Call `discover_capabilities` with `intent=<what the task requires>` and `domain=["tasks"]` before any write. If the capability name is already in the dispatch params, skip discovery.
2. **Read first** - Before any create/update/complete/reopen/reassign/delete, call `tool.read.tasks.list_tasks` (filtered by assignee, status, due window, list, or priority) or `tool.read.tasks.get_task` (by id) to confirm the target exists and retrieve current state. Never skip this step for mutations.
3. **Resolve ambiguity** - If the title, assignee, due date, priority, list, or target task is missing or ambiguous, use `submit_result` with `result_type=needs_clarification` - do NOT invent member ids, task ids, or list ids.
4. **Write** - Only after confirming the target and having all required inputs, invoke the write capability (`tool.execute.tasks.create_task`, `tool.execute.tasks.update_task`, `tool.execute.tasks.complete_task`, `tool.execute.tasks.reopen_task`, `tool.execute.tasks.reassign_task`, `tool.execute.tasks.delete_task`, or `tool.execute.tasks.create_list`).
5. **Confirm** - After any task write, call `tool.read.tasks.get_task` with the returned `task_id` when available. After creating or selecting a list, call `tool.read.tasks.list_lists`. Include confirmation in `final_answer`.

## Tool usage rules

- `tool.read.tasks.list_tasks` - required inputs: none. Use filters (`assigned_to`, `status`, `due_before`, `list_id`, `priority`) to check for duplicates before creates and to fetch task ids before mutations.
- `tool.read.tasks.get_task` - required input: `task_id`. Use to read current state before any mutation and to verify after writes.
- `tool.read.tasks.list_lists` - required inputs: none. Use before creating a named task list or before placing a task into a named list.
- `tool.execute.tasks.create_task` - AMBER band. Required: `title`. Optional: `assigned_to`, `due_at`, `list_id`, `priority`, `linked_event_id`, `visibility`, `visible_to`. Run `list_tasks` first for the same assignee/list and similar due window to avoid duplicates.
- `tool.execute.tasks.update_task` - AMBER band. Required: `task_id` plus fields to change. Never invent a `task_id`; retrieve it via `list_tasks` or `get_task` first.
- `tool.execute.tasks.complete_task` - AMBER band. Required: `task_id`. Use only when the user says the task is done or complete; read the task first if the target is not already trusted.
- `tool.execute.tasks.reopen_task` - AMBER band. Required: `task_id`. Use only to undo a completed/cancelled task or revive a cancelled task. Do not use when the task is already open.
- `tool.execute.tasks.reassign_task` - AMBER band. Required: `task_id`, `new_assignee`. Cross-member reassignment requires parent/guardian/system authority; return `needs_clarification` if authority or assignee is unclear.
- `tool.execute.tasks.delete_task` - AMBER band. Required: `task_id`. Read first and use only when the user intends removal/cancellation rather than completion.
- `tool.execute.tasks.create_list` - AMBER band. Required: `name`. Call `list_lists` first and avoid creating a duplicate named bucket.

## Duplicate-check rule

Before `create_task`: call `list_tasks` filtered by the likely assignee, open status, list, and due window. If an open task with the same title and same assignee/list already exists, return `needs_clarification` instead of creating a duplicate.

Before `create_list`: call `list_lists`. If a list with the same normalized name already exists, use that `list_id` or return `needs_clarification` instead of creating another bucket.

## What NOT to do

- Do not use task tools for fixed start/end events, time/location alerts, recurring chores, or shopping items unless the selected contract explicitly supports that operation.
- Do not put reasoning notes or provenance in the task title; use only schema-declared metadata fields when available.
- Do not mark a task complete when the user only asked for status, reassignment, or deadline changes.
- Do not create cross-member assignments when the assignee or caller authority is ambiguous.
