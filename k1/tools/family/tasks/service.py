"""k1.tools.family.tasks.service -- ``TasksToolService``.

Subclass of :class:`BaseToolService` implementing the ten Tasks adapter
actions declared in :data:`TASKS_DEFINITION`.

Design choices
--------------
* Tasks are **native-only**: no external feed source, no ``feed_source``
  field.  ``source`` is always ``"native"`` on every row.
* The **cross-member reassign guard** (reassigning to someone other than
  yourself requires ``parent`` or higher) is a runtime check inside the
  handler, not a declarative ``min_role``.  This mirrors the
  ``respond_to_invite`` pattern from the Calendar adapter.
* **Optimistic concurrency** on ``update_task`` via ``expected_version``.
* **Idempotency** on ``create_task`` and ``create_list`` via
  :class:`IdempotencyStore`.
* ACL filtering via :func:`k1.tools.family.acl.filter_rows` on every
  read path.
* Every successful write emits a typed SSE envelope via
  :meth:`BaseToolService.emit_entity_write`.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, ClassVar, Optional

from k1.tools.family.acl import filter_rows
from k1.tools.family.base import BaseEntity, WriteContext, role_satisfies
from k1.tools.family.base_service import BaseToolService
from k1.tools.family.tasks.definition import TASKS_DEFINITION
from k1.tools.family.tasks.schema import TaskItem, TaskList

logger = logging.getLogger(__name__)


_JSON_ITEM_COLS = ("named_visible", "tags", "metadata")
_JSON_LIST_COLS = ("named_visible", "tags", "metadata")


def _new_id() -> str:
    return uuid.uuid4().hex


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ui_interaction_metadata(params: dict[str, Any]) -> dict[str, Any]:
    source = str(params.get("interaction_source") or "").strip()
    kind = str(params.get("interaction_kind") or "").strip()
    if not source and not kind:
        return {}
    stamp: dict[str, Any] = {"at": _now_iso()}
    if source:
        stamp["source"] = source[:80]
    if kind:
        stamp["kind"] = kind[:80]
    return {"_last_ui_interaction": stamp}


def _metadata_updates(params: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if "metadata" in params and params["metadata"] is not None:
        if not isinstance(params["metadata"], dict):
            raise ValueError("task metadata must be an object")
        updates.update(params["metadata"])
    updates.update(_ui_interaction_metadata(params))
    return updates


def _merged_metadata(existing: TaskItem, params: dict[str, Any]) -> dict[str, Any]:
    updates = _metadata_updates(params)
    if not updates:
        return existing.metadata
    return {**existing.metadata, **updates}


class TasksToolService(BaseToolService):
    """The Family Tasks adapter service."""

    DEFINITION: ClassVar = TASKS_DEFINITION
    ENTITY_CLASSES: ClassVar[dict[str, type[BaseEntity]]] = {
        "task_item": TaskItem,
        "task_list": TaskList,
    }

    # ------------------------------------------------------------------ #
    # Action handlers
    # ------------------------------------------------------------------ #

    async def create_task(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("create_task")
        try:
            item = TaskItem(
                id=_new_id(),
                space_id=ctx.space_id,
                actor=ctx.user_id,
                visibility=params.get("visibility", "family"),
                named_visible=list(params.get("visible_to") or []),
                title=params["title"],
                list_id=params.get("list_id"),
                assigned_to=params.get("assigned_to"),
                due_at=params.get("due_at"),
                priority=params.get("priority", "medium"),
                linked_event_id=params.get("linked_event_id"),
            )
        except KeyError as exc:
            raise ValueError(f"create_task missing required field: {exc.args[0]}") from exc

        item = self._apply_visibility(item, ctx)
        self._upsert_item(item)
        self.emit_entity_write("create", item, ctx, action=action)
        return {"success": True, "task_id": item.id, "version": item.version}

    async def update_task(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("update_task")
        task_id = params.get("task_id")
        if not task_id:
            raise ValueError("update_task requires task_id")
        existing = self._select_item(task_id, ctx.space_id)
        if existing is None:
            raise ValueError(f"task not found: {task_id}")

        expected = params.get("expected_version")
        if expected is not None and existing.version != int(expected):
            raise ValueError(
                f"stale update_task: have version {existing.version}, "
                f"caller expected {expected}"
            )

        updates: dict[str, Any] = {}
        for field in ("title", "due_at", "priority", "list_id", "linked_event_id"):
            if field in params and params[field] is not None:
                updates[field] = params[field]
        if "status" in params and params["status"] is not None:
            status = str(params["status"])
            if status not in {"open", "in_progress", "done", "cancelled"}:
                raise ValueError(
                    "update_task status must be one of open, in_progress, done, cancelled"
                )
            updates["status"] = status
            if status == "done":
                updates["completed_at"] = (
                    params.get("completed_at") or existing.completed_at or _now_iso()
                )
            elif status != existing.status:
                updates["completed_at"] = None
        metadata = _merged_metadata(existing, params)
        if metadata is not existing.metadata:
            updates["metadata"] = metadata

        if updates:
            existing = existing.model_copy(update=updates)
        item = existing.bump(ctx.user_id)
        item = self._apply_visibility(item, ctx)
        self._upsert_item(item)
        self.emit_entity_write("update", item, ctx, action=action)
        return {
            "success": True,
            "task_id": item.id,
            "version": item.version,
            "task": item.model_dump(mode="json"),
        }

    async def complete_task(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("complete_task")
        task_id = params.get("task_id")
        if not task_id:
            raise ValueError("complete_task requires task_id")
        existing = self._select_item(task_id, ctx.space_id)
        if existing is None:
            raise ValueError(f"task not found: {task_id}")

        if existing.status == "done":
            # Idempotent: already done — return success without another write.
            return {
                "success": True,
                "task_id": task_id,
                "completed_at": existing.completed_at or _now_iso(),
            }

        now = _now_iso()
        updates = {
            "status": "done",
            "completed_at": now,
            "metadata": _merged_metadata(existing, params),
        }
        item = existing.model_copy(update=updates).bump(ctx.user_id)
        self._upsert_item(item)
        self.emit_entity_write("update", item, ctx, action=action)
        return {
            "success": True,
            "task_id": item.id,
            "completed_at": now,
            "version": item.version,
            "task": item.model_dump(mode="json"),
        }

    async def reopen_task(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("reopen_task")
        task_id = params.get("task_id")
        if not task_id:
            raise ValueError("reopen_task requires task_id")
        existing = self._select_item(task_id, ctx.space_id)
        if existing is None:
            raise ValueError(f"task not found: {task_id}")

        # Cross-member reopen: child can only reopen own tasks; parent can reopen anyone's.
        if existing.actor != ctx.user_id and not role_satisfies(ctx.role, "parent"):
            raise PermissionError("only the task creator or a parent may reopen this task")

        if existing.status == "open":
            return {"success": True, "task_id": task_id, "version": existing.version}

        item = existing.model_copy(
            update={
                "status": "open",
                "completed_at": None,
                "metadata": _merged_metadata(existing, params),
            }
        ).bump(ctx.user_id)
        self._upsert_item(item)
        self.emit_entity_write("update", item, ctx, action=action)
        return {
            "success": True,
            "task_id": item.id,
            "version": item.version,
            "task": item.model_dump(mode="json"),
        }

    async def reassign_task(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("reassign_task")
        task_id = params.get("task_id")
        new_assignee = params.get("new_assignee")
        if not task_id or not new_assignee:
            raise ValueError("reassign_task requires task_id and new_assignee")
        existing = self._select_item(task_id, ctx.space_id)
        if existing is None:
            raise ValueError(f"task not found: {task_id}")

        # Cross-member reassign guard: only parents may reassign to someone else.
        if new_assignee != ctx.user_id and not role_satisfies(ctx.role, "parent"):
            raise PermissionError("only a parent or guardian may reassign a task to another member")

        item = existing.model_copy(
            update={"assigned_to": new_assignee, "metadata": _merged_metadata(existing, params)}
        ).bump(ctx.user_id)
        self._upsert_item(item)
        self.emit_entity_write("update", item, ctx, action=action)
        return {
            "success": True,
            "task_id": item.id,
            "assigned_to": new_assignee,
            "version": item.version,
            "task": item.model_dump(mode="json"),
        }

    async def delete_task(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("delete_task")
        task_id = params.get("task_id")
        if not task_id:
            raise ValueError("delete_task requires task_id")
        existing = self._select_item(task_id, ctx.space_id)
        if existing is None:
            raise ValueError(f"task not found: {task_id}")

        deleted = existing.model_copy(
            update={
                "deleted_at": datetime.now(timezone.utc),
                "version": existing.version + 1,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self._upsert_item(deleted)
        self.emit_entity_write("delete", deleted, ctx, action=action)
        return {"success": True, "task_id": task_id}

    async def list_tasks(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        rows = self._scan_items(
            space_id=ctx.space_id,
            assigned_to=params.get("assigned_to"),
            status=params.get("status"),
            due_before=params.get("due_before"),
            list_id=params.get("list_id"),
            priority=params.get("priority"),
        )
        visible = filter_rows(rows, ctx, self._policy)
        return {"success": True, "tasks": visible, "count": len(visible)}

    async def get_task(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        task_id = params.get("task_id")
        if not task_id:
            raise ValueError("get_task requires task_id")
        row = self._row_item(task_id, ctx.space_id)
        if row is None:
            raise ValueError(f"task not found: {task_id}")
        visible = filter_rows([row], ctx, self._policy)
        if not visible:
            raise ValueError(f"task not visible: {task_id}")
        return {"success": True, "task": visible[0]}

    async def create_list(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("create_list")
        try:
            lst = TaskList(
                id=_new_id(),
                space_id=ctx.space_id,
                actor=ctx.user_id,
                visibility=params.get("visibility", "family"),
                name=params["name"],
                color=params.get("color"),
            )
        except KeyError as exc:
            raise ValueError(f"create_list missing required field: {exc.args[0]}") from exc

        lst = self._apply_visibility_list(lst, ctx)
        self._upsert_list(lst)
        self.emit_entity_write("create", lst, ctx, action=action)
        return {"success": True, "list_id": lst.id}

    async def list_lists(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        rows = self._scan_lists(space_id=ctx.space_id)
        visible = filter_rows(rows, ctx, self._policy)
        return {"success": True, "lists": visible, "count": len(visible)}

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _apply_visibility(self, item: TaskItem, ctx: WriteContext) -> TaskItem:
        effective = self._policy.apply(item, ctx.role)
        if effective != item.visibility:
            return item.model_copy(update={"visibility": effective})
        return item

    def _apply_visibility_list(self, lst: TaskList, ctx: WriteContext) -> TaskList:
        effective = self._policy.apply(lst, ctx.role)
        if effective != lst.visibility:
            return lst.model_copy(update={"visibility": effective})
        return lst

    def _spec(self, name: str):
        spec = self.DEFINITION.find_action(name)
        if spec is None:  # pragma: no cover
            raise RuntimeError(f"TasksToolService missing ActionSpec {name!r}")
        return spec

    # ---- task_items I/O ------------------------------------------------ #

    def _upsert_item(self, item: TaskItem) -> None:
        data = item.model_dump(mode="json")
        cols = [
            "id",
            "space_id",
            "actor",
            "source",
            "source_label",
            "visibility",
            "named_visible",
            "version",
            "created_at",
            "updated_at",
            "deleted_at",
            "tags",
            "metadata",
            "title",
            "list_id",
            "assigned_to",
            "due_at",
            "priority",
            "status",
            "completed_at",
            "linked_event_id",
        ]
        values = [
            data["id"],
            data["space_id"],
            data["actor"],
            data["source"],
            data["source_label"],
            data["visibility"],
            json.dumps(data["named_visible"]),
            data["version"],
            data["created_at"],
            data["updated_at"],
            data["deleted_at"],
            json.dumps(data["tags"]),
            json.dumps(data["metadata"]),
            data["title"],
            data["list_id"],
            data["assigned_to"],
            data["due_at"],
            data["priority"],
            data["status"],
            data["completed_at"],
            data["linked_event_id"],
        ]
        placeholders = ",".join("?" for _ in cols)
        sql = f"INSERT OR REPLACE INTO task_items ({','.join(cols)}) VALUES ({placeholders})"
        with self._conn:
            self._conn.execute(sql, values)

    def _select_item(self, task_id: str, space_id: str) -> Optional[TaskItem]:
        row = self._row_item(task_id, space_id)
        if row is None:
            return None
        return TaskItem(**row)

    def _row_item(self, task_id: str, space_id: str) -> Optional[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT * FROM task_items WHERE id=? AND space_id=?",
            (task_id, space_id),
        )
        raw = cur.fetchone()
        if raw is None:
            return None
        return _decode_json_cols(_row_to_dict(raw), _JSON_ITEM_COLS)

    def _scan_items(
        self,
        *,
        space_id: str,
        assigned_to: Optional[str],
        status: Optional[str],
        due_before: Optional[str],
        list_id: Optional[str],
        priority: Optional[str],
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM task_items WHERE space_id=?"
        args: list[Any] = [space_id]
        if assigned_to:
            sql += " AND assigned_to=?"
            args.append(assigned_to)
        if status:
            sql += " AND status=?"
            args.append(status)
        if due_before:
            sql += " AND due_at IS NOT NULL AND due_at<=?"
            args.append(due_before)
        if list_id:
            sql += " AND list_id=?"
            args.append(list_id)
        if priority:
            sql += " AND priority=?"
            args.append(priority)
        sql += " ORDER BY due_at ASC NULLS LAST, created_at ASC LIMIT 500"
        cur = self._conn.execute(sql, args)
        return [_decode_json_cols(_row_to_dict(r), _JSON_ITEM_COLS) for r in cur.fetchall()]

    # ---- task_lists I/O ------------------------------------------------ #

    def _upsert_list(self, lst: TaskList) -> None:
        data = lst.model_dump(mode="json")
        cols = [
            "id",
            "space_id",
            "actor",
            "source",
            "source_label",
            "visibility",
            "named_visible",
            "version",
            "created_at",
            "updated_at",
            "deleted_at",
            "tags",
            "metadata",
            "name",
            "color",
        ]
        values = [
            data["id"],
            data["space_id"],
            data["actor"],
            data["source"],
            data["source_label"],
            data["visibility"],
            json.dumps(data["named_visible"]),
            data["version"],
            data["created_at"],
            data["updated_at"],
            data["deleted_at"],
            json.dumps(data["tags"]),
            json.dumps(data["metadata"]),
            data["name"],
            data["color"],
        ]
        placeholders = ",".join("?" for _ in cols)
        sql = f"INSERT OR REPLACE INTO task_lists ({','.join(cols)}) VALUES ({placeholders})"
        with self._conn:
            self._conn.execute(sql, values)

    def _scan_lists(self, *, space_id: str) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT * FROM task_lists WHERE space_id=? ORDER BY created_at ASC LIMIT 200",
            (space_id,),
        )
        return [_decode_json_cols(_row_to_dict(r), _JSON_LIST_COLS) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Module-private row helpers  (shared with Calendar service pattern)
# ---------------------------------------------------------------------------


def _row_to_dict(raw: Any) -> dict[str, Any]:
    if hasattr(raw, "keys"):
        return {k: raw[k] for k in raw.keys()}
    return dict(raw)


def _decode_json_cols(row: dict[str, Any], cols: tuple[str, ...]) -> dict[str, Any]:
    for col in cols:
        val = row.get(col)
        if isinstance(val, str):
            try:
                row[col] = json.loads(val)
            except json.JSONDecodeError:
                logger.warning("tasks: failed to decode JSON column %r", col)
    return row
