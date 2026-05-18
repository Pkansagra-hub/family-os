"""k1.tools.family.shopping.service -- Shopping native app service."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, ClassVar, Optional

from k1.tools.family.acl import filter_rows
from k1.tools.family.base import BaseEntity, WriteContext, role_satisfies
from k1.tools.family.base_service import BaseToolService
from k1.tools.family.shopping.definition import SHOPPING_DEFINITION
from k1.tools.family.shopping.schema import ShoppingItem, ShoppingList

logger = logging.getLogger(__name__)

_JSON_COLS = ("named_visible", "tags", "metadata")


def _new_id() -> str:
    return uuid.uuid4().hex


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ShoppingToolService(BaseToolService):
    """Family Shopping adapter service."""

    DEFINITION: ClassVar = SHOPPING_DEFINITION
    ENTITY_CLASSES: ClassVar[dict[str, type[BaseEntity]]] = {
        "shopping_list": ShoppingList,
        "shopping_item": ShoppingItem,
    }

    # ------------------------------------------------------------------ #
    # List actions
    # ------------------------------------------------------------------ #

    async def create_list(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("create_list")
        self._assert_approver(ctx, "create shopping lists")

        try:
            shopping_list = ShoppingList(
                id=_new_id(),
                space_id=ctx.space_id,
                actor=ctx.user_id,
                visibility=params.get("visibility", "family"),
                named_visible=list(params.get("visible_to") or []),
                name=params["name"],
                category=params.get("category", "groceries"),
            )
        except KeyError as exc:
            raise ValueError(f"create_list missing required field: {exc.args[0]}") from exc

        shopping_list = self._apply_visibility_list(shopping_list, ctx)
        self._upsert_list(shopping_list)
        self.emit_entity_write("create", shopping_list, ctx, action=action)
        return {"success": True, "list_id": shopping_list.id, "version": shopping_list.version}

    async def delete_list(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("delete_list")
        self._assert_approver(ctx, "delete shopping lists")
        list_id = params.get("list_id")
        if not list_id:
            raise ValueError("delete_list requires list_id")
        existing = self._select_list(list_id, ctx.space_id)
        if existing is None:
            raise ValueError(f"shopping list not found: {list_id}")

        deleted = existing.model_copy(
            update={
                "deleted_at": datetime.now(timezone.utc),
                "version": existing.version + 1,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self._upsert_list(deleted)
        self.emit_entity_write("delete", deleted, ctx, action=action)
        return {"success": True, "list_id": list_id}

    async def list_lists(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        rows = self._scan_lists(space_id=ctx.space_id, category=params.get("category"))
        visible = filter_rows(rows, ctx, self._policy)
        return {"success": True, "lists": visible, "count": len(visible)}

    # ------------------------------------------------------------------ #
    # Item actions
    # ------------------------------------------------------------------ #

    async def add_item(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("add_item")
        list_id = params.get("list_id")
        if not list_id:
            raise ValueError("add_item requires list_id")
        shopping_list = self._select_visible_list(list_id, ctx)

        is_child_request = ctx.role == "child"
        approval_status = "pending_parent_approval" if is_child_request else "approved"
        requested_by = (
            ctx.user_id if is_child_request else params.get("requested_by") or ctx.user_id
        )

        try:
            item = ShoppingItem(
                id=_new_id(),
                space_id=ctx.space_id,
                actor=ctx.user_id,
                visibility=params.get("visibility", shopping_list.visibility),
                named_visible=list(params.get("visible_to") or shopping_list.named_visible),
                list_id=list_id,
                name=params["name"],
                quantity=params.get("quantity"),
                unit=params.get("unit"),
                category=params.get("category") or shopping_list.category,
                requested_by=requested_by,
                notes=params.get("notes"),
                priority=params.get("priority", "medium"),
                approval_status=approval_status,
                approved_by=None if is_child_request else ctx.user_id,
                approved_at=None if is_child_request else _now_iso(),
            )
        except KeyError as exc:
            raise ValueError(f"add_item missing required field: {exc.args[0]}") from exc

        item = self._apply_visibility_item(item, ctx)
        self._upsert_item(item)
        self.emit_entity_write("create", item, ctx, action=action)
        return {
            "success": True,
            "item_id": item.id,
            "version": item.version,
            "approval_status": item.approval_status,
        }

    async def update_item(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("update_item")
        self._assert_approver(ctx, "update shopping items")
        item_id = params.get("item_id")
        if not item_id:
            raise ValueError("update_item requires item_id")
        existing = self._select_item(item_id, ctx.space_id)
        if existing is None:
            raise ValueError(f"shopping item not found: {item_id}")

        updates: dict[str, Any] = {}
        for field in ("name", "quantity", "unit", "category", "notes", "priority"):
            if field in params and params[field] is not None:
                updates[field] = params[field]
        if updates:
            existing = existing.model_copy(update=updates)
        item = existing.bump(ctx.user_id)
        self._upsert_item(item)
        self.emit_entity_write("update", item, ctx, action=action)
        return {"success": True, "item_id": item.id, "version": item.version}

    async def approve_item(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("approve_item")
        self._assert_approver(ctx, "approve shopping items")
        existing = self._require_item(params.get("item_id"), ctx.space_id, "approve_item")

        item = existing.model_copy(
            update={
                "approval_status": "approved",
                "approved_by": ctx.user_id,
                "approved_at": _now_iso(),
                "rejected_by": None,
                "rejected_at": None,
                "rejection_reason": None,
            }
        ).bump(ctx.user_id)
        if params.get("approval_note"):
            metadata = dict(item.metadata)
            metadata["approval_note"] = params["approval_note"]
            item = item.model_copy(update={"metadata": metadata})
        self._upsert_item(item)
        self.emit_entity_write("update", item, ctx, action=action)
        return {"success": True, "item_id": item.id, "approval_status": item.approval_status}

    async def reject_item(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("reject_item")
        self._assert_approver(ctx, "reject shopping items")
        existing = self._require_item(params.get("item_id"), ctx.space_id, "reject_item")

        item = existing.model_copy(
            update={
                "approval_status": "rejected",
                "rejected_by": ctx.user_id,
                "rejected_at": _now_iso(),
                "rejection_reason": params.get("rejection_reason"),
                "approved_by": None,
                "approved_at": None,
                "status": "needed",
                "checked_by": None,
                "checked_at": None,
            }
        ).bump(ctx.user_id)
        self._upsert_item(item)
        self.emit_entity_write("update", item, ctx, action=action)
        return {"success": True, "item_id": item.id, "approval_status": item.approval_status}

    async def check_off_item(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("check_off_item")
        self._assert_approver(ctx, "check off shopping items")
        existing = self._require_item(params.get("item_id"), ctx.space_id, "check_off_item")

        if existing.approval_status != "approved":
            raise PermissionError("shopping item must be parent-approved before check_off_item")
        if existing.status == "checked":
            return {
                "success": True,
                "item_id": existing.id,
                "checked_at": existing.checked_at or _now_iso(),
            }

        checked_at = _now_iso()
        item = existing.model_copy(
            update={
                "status": "checked",
                "checked_by": params.get("checked_by") or ctx.user_id,
                "checked_at": checked_at,
            }
        ).bump(ctx.user_id)
        self._upsert_item(item)
        self.emit_entity_write("update", item, ctx, action=action)
        return {"success": True, "item_id": item.id, "checked_at": checked_at}

    async def delete_item(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("delete_item")
        self._assert_approver(ctx, "delete shopping items")
        existing = self._require_item(params.get("item_id"), ctx.space_id, "delete_item")

        deleted = existing.model_copy(
            update={
                "deleted_at": datetime.now(timezone.utc),
                "version": existing.version + 1,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self._upsert_item(deleted)
        self.emit_entity_write("delete", deleted, ctx, action=action)
        return {"success": True, "item_id": existing.id}

    async def list_items(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        rows = self._scan_items(
            space_id=ctx.space_id,
            list_id=params.get("list_id"),
            category=params.get("category"),
            status=params.get("status"),
            requested_by=params.get("requested_by"),
            approval_status=params.get("approval_status"),
        )
        visible = filter_rows(rows, ctx, self._policy)
        return {"success": True, "items": visible, "count": len(visible)}

    async def get_item(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        item_id = params.get("item_id")
        if not item_id:
            raise ValueError("get_item requires item_id")
        row = self._row_item(item_id, ctx.space_id)
        if row is None:
            raise ValueError(f"shopping item not found: {item_id}")
        visible = filter_rows([row], ctx, self._policy)
        if not visible:
            raise ValueError(f"shopping item not visible: {item_id}")
        return {"success": True, "item": visible[0]}

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _assert_approver(self, ctx: WriteContext, action_name: str) -> None:
        if not role_satisfies(ctx.role, "guardian"):
            raise PermissionError(f"only a parent or guardian may {action_name}")

    def _require_item(self, item_id: Any, space_id: str, action_name: str) -> ShoppingItem:
        if not item_id:
            raise ValueError(f"{action_name} requires item_id")
        existing = self._select_item(str(item_id), space_id)
        if existing is None:
            raise ValueError(f"shopping item not found: {item_id}")
        return existing

    def _select_visible_list(self, list_id: str, ctx: WriteContext) -> ShoppingList:
        row = self._row_list(list_id, ctx.space_id)
        if row is None:
            raise ValueError(f"shopping list not found: {list_id}")
        visible = filter_rows([row], ctx, self._policy)
        if not visible:
            raise ValueError(f"shopping list not visible: {list_id}")
        return ShoppingList(**visible[0])

    def _apply_visibility_list(
        self, shopping_list: ShoppingList, ctx: WriteContext
    ) -> ShoppingList:
        effective = self._policy.apply(shopping_list, ctx.role)
        if effective != shopping_list.visibility:
            return shopping_list.model_copy(update={"visibility": effective})
        return shopping_list

    def _apply_visibility_item(self, item: ShoppingItem, ctx: WriteContext) -> ShoppingItem:
        effective = self._policy.apply(item, ctx.role)
        if effective != item.visibility:
            return item.model_copy(update={"visibility": effective})
        return item

    def _spec(self, name: str):
        spec = self.DEFINITION.find_action(name)
        if spec is None:  # pragma: no cover
            raise RuntimeError(f"ShoppingToolService missing ActionSpec {name!r}")
        return spec

    # ---- shopping_lists I/O ------------------------------------------ #

    def _upsert_list(self, shopping_list: ShoppingList) -> None:
        data = shopping_list.model_dump(mode="json")
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
            "category",
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
            data["category"],
        ]
        placeholders = ",".join("?" for _ in cols)
        sql = f"INSERT OR REPLACE INTO shopping_lists ({','.join(cols)}) VALUES ({placeholders})"
        with self._conn:
            self._conn.execute(sql, values)

    def _select_list(self, list_id: str, space_id: str) -> Optional[ShoppingList]:
        row = self._row_list(list_id, space_id)
        if row is None:
            return None
        return ShoppingList(**row)

    def _row_list(self, list_id: str, space_id: str) -> Optional[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT * FROM shopping_lists WHERE id=? AND space_id=?",
            (list_id, space_id),
        )
        raw = cur.fetchone()
        if raw is None:
            return None
        return _decode_json_cols(_row_to_dict(raw), _JSON_COLS)

    def _scan_lists(self, *, space_id: str, category: Optional[str]) -> list[dict[str, Any]]:
        sql = "SELECT * FROM shopping_lists WHERE space_id=?"
        args: list[Any] = [space_id]
        if category:
            sql += " AND category=?"
            args.append(category)
        sql += " ORDER BY category ASC, name ASC LIMIT 200"
        cur = self._conn.execute(sql, args)
        return [_decode_json_cols(_row_to_dict(r), _JSON_COLS) for r in cur.fetchall()]

    # ---- shopping_items I/O ------------------------------------------ #

    def _upsert_item(self, item: ShoppingItem) -> None:
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
            "list_id",
            "name",
            "quantity",
            "unit",
            "category",
            "requested_by",
            "notes",
            "priority",
            "status",
            "approval_status",
            "approved_by",
            "approved_at",
            "rejected_by",
            "rejected_at",
            "rejection_reason",
            "checked_by",
            "checked_at",
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
            data["list_id"],
            data["name"],
            data["quantity"],
            data["unit"],
            data["category"],
            data["requested_by"],
            data["notes"],
            data["priority"],
            data["status"],
            data["approval_status"],
            data["approved_by"],
            data["approved_at"],
            data["rejected_by"],
            data["rejected_at"],
            data["rejection_reason"],
            data["checked_by"],
            data["checked_at"],
        ]
        placeholders = ",".join("?" for _ in cols)
        sql = f"INSERT OR REPLACE INTO shopping_items ({','.join(cols)}) VALUES ({placeholders})"
        with self._conn:
            self._conn.execute(sql, values)

    def _select_item(self, item_id: str, space_id: str) -> Optional[ShoppingItem]:
        row = self._row_item(item_id, space_id)
        if row is None:
            return None
        return ShoppingItem(**row)

    def _row_item(self, item_id: str, space_id: str) -> Optional[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT * FROM shopping_items WHERE id=? AND space_id=?",
            (item_id, space_id),
        )
        raw = cur.fetchone()
        if raw is None:
            return None
        return _decode_json_cols(_row_to_dict(raw), _JSON_COLS)

    def _scan_items(
        self,
        *,
        space_id: str,
        list_id: Optional[str],
        category: Optional[str],
        status: Optional[str],
        requested_by: Optional[str],
        approval_status: Optional[str],
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM shopping_items WHERE space_id=?"
        args: list[Any] = [space_id]
        if list_id:
            sql += " AND list_id=?"
            args.append(list_id)
        if category:
            sql += " AND category=?"
            args.append(category)
        if status:
            sql += " AND status=?"
            args.append(status)
        if requested_by:
            sql += " AND requested_by=?"
            args.append(requested_by)
        if approval_status:
            sql += " AND approval_status=?"
            args.append(approval_status)
        sql += " ORDER BY category ASC, created_at ASC LIMIT 500"
        cur = self._conn.execute(sql, args)
        return [_decode_json_cols(_row_to_dict(r), _JSON_COLS) for r in cur.fetchall()]


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
                logger.warning("shopping: failed to decode JSON column %r", col)
    return row
