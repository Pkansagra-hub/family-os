# Shopping activity profile v1

Use this profile as procedural guidance only. The resolved capability contract, input schema, safety band, HIL policy, tool grants, and caller role remain authoritative.

## Chain of thought - always follow this order

1. **Discover** - Call `discover_capabilities` with `intent=<what the task requires>` and `domain=["shopping"]` before any write. If the capability name is already in the dispatch params, skip discovery.
2. **Read first** - Before creating, updating, approving, rejecting, checking off, or deleting shopping state, call `tool.read.shopping.list_lists`, `tool.read.shopping.list_items`, or `tool.read.shopping.get_item` to inspect the current list, category, item status, and approval state.
3. **Resolve ambiguity** - If the list, item name, category, quantity, requested member, or approval intent is missing or ambiguous, use `submit_result` with `result_type=needs_clarification` - do NOT invent item ids, list ids, member ids, quantities, or parent approval.
4. **Write** - Only after confirming the target and having all required inputs, invoke the write capability (`tool.execute.shopping.create_list`, `tool.execute.shopping.add_item`, `tool.execute.shopping.update_item`, `tool.execute.shopping.approve_item`, `tool.execute.shopping.reject_item`, `tool.execute.shopping.check_off_item`, `tool.execute.shopping.delete_item`, or `tool.execute.shopping.delete_list`).
5. **Confirm** - After any write, call `tool.read.shopping.get_item` for item writes or `tool.read.shopping.list_lists` for list writes to verify the change. Include confirmation in `final_answer`.

## Tool usage rules

- `tool.read.shopping.list_lists` - required inputs: none. Use to find the correct list id and avoid duplicate list creation. Filter by `category` when the user says groceries, clothes, school, pharmacy, gifts, pets, household, or other.
- `tool.read.shopping.list_items` - required inputs: none. Use filters (`list_id`, `category`, `status`, `requested_by`, `approval_status`) to check for duplicate item requests and find pending child requests.
- `tool.read.shopping.get_item` - required input: `item_id`. Use before updating, approving, rejecting, checking off, or deleting.
- `tool.execute.shopping.create_list` - AMBER band. Parent/guardian/system only. Required: `name`. Optional: `category`, `visibility`, `visible_to`. Use for family-owned buckets such as Groceries, Clothes, School, Pharmacy, Gifts, Pets, Household, or Other.
- `tool.execute.shopping.add_item` - AMBER band. Required: `list_id`, `name`. Optional: `quantity`, `unit`, `category`, `requested_by`, `notes`, `priority`, `visibility`, `visible_to`. Child requests are always created with `approval_status=pending_parent_approval`; do not treat them as approved purchases.
- `tool.execute.shopping.update_item` - AMBER band. Parent/guardian/system only. Required: `item_id` plus fields to change. Use for correcting quantity, notes, priority, or category after reading current state.
- `tool.execute.shopping.approve_item` - AMBER band. Parent/guardian/system only. Required: `item_id`. Use when a parent explicitly approves a child shopping request.
- `tool.execute.shopping.reject_item` - AMBER band. Parent/guardian/system only. Required: `item_id`. Optional: `rejection_reason`. Use when a parent explicitly rejects a child shopping request.
- `tool.execute.shopping.check_off_item` - AMBER band. Parent/guardian/system only. Required: `item_id`. The item must be approved first.
- `tool.execute.shopping.delete_item` - AMBER band. Parent/guardian/system only. Required: `item_id`. Use for removing mistaken or no-longer-needed items.
- `tool.execute.shopping.delete_list` - AMBER band. Parent/guardian/system only. Required: `list_id`. Use only when the parent intends to remove the list bucket.

## Duplicate-check rule

Before `add_item`: call `list_items` filtered by the target `list_id`, normalized `name`, `category`, and `status=needed`. If an approved or pending item with the same name/category already exists, return `needs_clarification` instead of creating a duplicate.

Before `create_list`: call `list_lists`. If a list with the same normalized name or same primary category already exists, use that list or return `needs_clarification` instead of creating another bucket.

## Parent approval rule

Child-originated shopping writes are requests, not purchases. A child `add_item` result with `approval_status=pending_parent_approval` must be followed by an explicit parent/guardian/system `approve_item` before the item can be checked off, purchased, or treated as accepted.

## What NOT to do

- Do not use shopping tools for one-shot tasks, recurring chores, calendar events, or reminders unless the selected contract explicitly supports that operation.
- Do not mark child-requested items as approved without an explicit parent/guardian/system approval action.
- Do not check off or delete an item when the user only asked to review pending requests.
- Do not put reasoning notes or provenance in the item name; use schema-declared notes or metadata fields only.
