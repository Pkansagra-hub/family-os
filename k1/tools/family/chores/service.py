"""k1.tools.family.chores.service -- ``ChoresToolService``.

Implements the 9 Chores adapter actions declared in :data:`CHORES_DEFINITION`.

Permission guards
-----------------
1. ``create_template`` / ``update_template`` / ``delete_template`` / ``reopen_chore``:
   parent+ only.
2. ``assign_chore``:
   guardian+ (a guardian may assign chores to any member; a child cannot
   reassign another member's chore — but can create an occurrence for themselves
   if the template is assigned to them by default).
3. ``complete_chore`` / ``skip_chore``:
   actor gate — caller must be the occurrence assignee OR parent+.
   Children can self-complete/skip; they cannot touch another member's chores.
4. ``points_override`` on ``complete_chore``:
   only effective if caller is parent+; silently ignored for child callers.

Design notes
------------
* Templates and occurrences are stored in separate tables; the service
    manages both. ``create_template`` creates the first pending occurrence
    immediately so list/board surfaces reflect the new chore. ``assign_chore``
    claims that initial unassigned occurrence when available; otherwise it
    creates a new occurrence.
* ``complete_chore`` is idempotent: calling it on an already-done
  occurrence returns success with the existing ``completed_at`` timestamp.
* ``chore_summary`` is a pure read aggregation — no writes, no SSE.
* SSE fan-out on every mutating action keeps all household devices in sync.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, ClassVar, Optional

from k1.tools.family.acl import filter_rows
from k1.tools.family.base import BaseEntity, WriteContext, role_satisfies
from k1.tools.family.base_service import BaseToolService
from k1.tools.family.chores.definition import CHORES_DEFINITION
from k1.tools.family.chores.schema import ChoreOccurrence, ChoreTemplate

logger = logging.getLogger(__name__)

_JSON_COLS = ("named_visible", "tags", "metadata")


def _new_id() -> str:
    return uuid.uuid4().hex


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_frequency(value: Any) -> tuple[str, dict[str, Any]]:
    raw = str(value or "weekly").strip()
    normalized = raw.lower().replace("_", "-")
    compact = re.sub(r"\s+", " ", normalized)

    exact: dict[str, str] = {
        "daily": "daily",
        "day": "daily",
        "every day": "daily",
        "each day": "daily",
        "everyday": "daily",
        "weekly": "weekly",
        "week": "weekly",
        "every week": "weekly",
        "each week": "weekly",
        "once a week": "weekly",
        "monthly": "monthly",
        "month": "monthly",
        "every month": "monthly",
        "each month": "monthly",
        "once a month": "monthly",
        "once": "once",
        "one time": "once",
        "one-time": "once",
        "one off": "once",
        "one-off": "once",
        "custom": "custom",
    }
    if compact in exact:
        return exact[compact], {}

    match = re.fullmatch(r"every (\d+) (day|days|week|weeks|month|months)", compact)
    if match:
        count = int(match.group(1))
        unit = match.group(2).rstrip("s")
        if count == 1:
            return {"day": "daily", "week": "weekly", "month": "monthly"}[unit], {}
        return "custom", {"raw": raw, "interval_count": count, "interval_unit": unit}

    return "custom", {"raw": raw}


class ChoresToolService(BaseToolService):
    """Family Chores adapter service."""

    DEFINITION: ClassVar = CHORES_DEFINITION
    ENTITY_CLASSES: ClassVar[dict[str, type[BaseEntity]]] = {
        "chore_template": ChoreTemplate,
        "chore_occurrence": ChoreOccurrence,
    }

    # ------------------------------------------------------------------ #
    # Action handlers — templates
    # ------------------------------------------------------------------ #

    async def create_template(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("create_template")
        if not role_satisfies(ctx.role, "parent"):
            raise PermissionError("only a parent or system may create chore templates")

        frequency, recurrence_metadata = _normalize_frequency(params.get("frequency", "weekly"))
        metadata = dict(params.get("metadata") or {}) if isinstance(params.get("metadata"), dict) else {}
        if recurrence_metadata:
            metadata["recurrence"] = recurrence_metadata

        template = ChoreTemplate(
            id=_new_id(),
            space_id=ctx.space_id,
            actor=ctx.user_id,
            visibility=params.get("visibility", "family"),
            metadata=metadata,
            title=params["title"],
            description=params.get("description"),
            assigned_to=params.get("assigned_to"),
            frequency=frequency,
            base_points=params.get("base_points", 0),
        )
        occurrence = ChoreOccurrence(
            id=_new_id(),
            space_id=ctx.space_id,
            actor=ctx.user_id,
            visibility=template.visibility,
            template_id=template.id,
            title=template.title,
            assigned_to=template.assigned_to,
            due_at=params.get("due_at"),
            points_awarded=template.base_points,
        )
        self._upsert_template(template)
        self._upsert_occurrence(occurrence)
        self.emit_entity_write("create", template, ctx, action=action)
        self.emit_entity_write("create", occurrence, ctx, action=action)
        return {
            "success": True,
            "template_id": template.id,
            "occurrence_id": occurrence.id,
            "version": template.version,
        }

    async def update_template(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("update_template")
        if not role_satisfies(ctx.role, "parent"):
            raise PermissionError("only a parent or system may update chore templates")

        template_id = params.get("template_id")
        if not template_id:
            raise ValueError("update_template requires template_id")
        existing = self._select_template(template_id, ctx.space_id)
        if existing is None:
            raise ValueError(f"template not found: {template_id}")

        updates: dict[str, Any] = {}
        for field in ("title", "description", "assigned_to", "base_points"):
            if field in params and params[field] is not None:
                updates[field] = params[field]
        if "frequency" in params and params["frequency"] is not None:
            frequency, recurrence_metadata = _normalize_frequency(params["frequency"])
            metadata = dict(existing.metadata)
            metadata.pop("recurrence", None)
            if recurrence_metadata:
                metadata["recurrence"] = recurrence_metadata
            updates["frequency"] = frequency
            updates["metadata"] = metadata
        if "is_active" in params and params["is_active"] is not None:
            updates["is_active"] = bool(params["is_active"])
        if "visibility" in params and params["visibility"] is not None:
            updates["visibility"] = params["visibility"]

        if updates:
            existing = existing.model_copy(update=updates)
        template = existing.bump(ctx.user_id)
        self._upsert_template(template)
        self.emit_entity_write("update", template, ctx, action=action)
        return {"success": True, "template_id": template.id, "version": template.version}

    async def delete_template(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("delete_template")
        if not role_satisfies(ctx.role, "parent"):
            raise PermissionError("only a parent or system may delete chore templates")

        template_id = params.get("template_id")
        if not template_id:
            raise ValueError("delete_template requires template_id")
        existing = self._select_template(template_id, ctx.space_id)
        if existing is None:
            raise ValueError(f"template not found: {template_id}")

        deleted = existing.model_copy(
            update={
                "deleted_at": datetime.now(timezone.utc),
                "version": existing.version + 1,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self._upsert_template(deleted)
        self._soft_delete_pending_occurrences(template_id, ctx.space_id)
        self.emit_entity_write("delete", deleted, ctx, action=action)
        return {"success": True, "template_id": template_id}

    # ------------------------------------------------------------------ #
    # Action handlers — occurrences
    # ------------------------------------------------------------------ #

    async def assign_chore(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("assign_chore")
        if not role_satisfies(ctx.role, "guardian"):
            raise PermissionError("only guardian or parent may assign chore occurrences")

        template_id = params.get("template_id")
        assigned_to = params.get("assigned_to")
        if not template_id or not assigned_to:
            raise ValueError("assign_chore requires template_id and assigned_to")

        # Load template to get title + base_points.
        template = self._select_template(template_id, ctx.space_id)
        if template is None:
            raise ValueError(f"template not found: {template_id}")

        points = params.get("points_awarded", template.base_points)
        existing_pool_occ = self._select_pending_pool_occurrence(template_id, ctx.space_id)
        if existing_pool_occ is not None:
            occ = existing_pool_occ.model_copy(
                update={
                    "title": template.title,
                    "assigned_to": assigned_to,
                    "due_at": params.get("due_at"),
                    "points_awarded": points,
                    "visibility": params.get("visibility", existing_pool_occ.visibility),
                }
            ).bump(ctx.user_id)
        else:
            occ = ChoreOccurrence(
                id=_new_id(),
                space_id=ctx.space_id,
                actor=ctx.user_id,
                visibility=params.get("visibility", "family"),
                template_id=template_id,
                title=template.title,
                assigned_to=assigned_to,
                due_at=params.get("due_at"),
                points_awarded=points,
            )
        self._upsert_occurrence(occ)
        self.emit_entity_write("create", occ, ctx, action=action)
        return {"success": True, "occurrence_id": occ.id, "version": occ.version}

    async def complete_chore(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("complete_chore")
        occurrence_id = params.get("occurrence_id")
        if not occurrence_id:
            raise ValueError("complete_chore requires occurrence_id")
        existing = self._select_occurrence(occurrence_id, ctx.space_id)
        if existing is None:
            raise ValueError(f"occurrence not found: {occurrence_id}")

        # Actor gate: assignee or parent+.
        self._assert_occurrence_gate(existing, ctx, action_name="complete")

        # Idempotent if already done.
        if existing.status == "done":
            return {
                "success": True,
                "occurrence_id": occurrence_id,
                "completed_at": existing.completed_at,
                "points_awarded": existing.points_awarded,
            }

        completed_by = params.get("completed_by") or ctx.user_id
        now = _now_iso()

        # Points override: only effective for parent+.
        points = existing.points_awarded
        if "points_override" in params and params["points_override"] is not None:
            if role_satisfies(ctx.role, "parent"):
                points = int(params["points_override"])

        occ = existing.model_copy(
            update={
                "status": "done",
                "completed_at": now,
                "completed_by": completed_by,
                "points_awarded": points,
                "skipped_at": None,
                "skip_reason": None,
            }
        ).bump(ctx.user_id)
        self._upsert_occurrence(occ)
        self.emit_entity_write("update", occ, ctx, action=action)
        return {
            "success": True,
            "occurrence_id": occ.id,
            "completed_at": now,
            "points_awarded": points,
        }

    async def skip_chore(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("skip_chore")
        occurrence_id = params.get("occurrence_id")
        if not occurrence_id:
            raise ValueError("skip_chore requires occurrence_id")
        existing = self._select_occurrence(occurrence_id, ctx.space_id)
        if existing is None:
            raise ValueError(f"occurrence not found: {occurrence_id}")

        # Actor gate: assignee or parent+.
        self._assert_occurrence_gate(existing, ctx, action_name="skip")

        if existing.status == "skipped":
            return {"success": True, "occurrence_id": occurrence_id}

        now = _now_iso()
        occ = existing.model_copy(
            update={
                "status": "skipped",
                "skipped_at": now,
                "skip_reason": params.get("skip_reason"),
                "completed_at": None,
                "completed_by": None,
            }
        ).bump(ctx.user_id)
        self._upsert_occurrence(occ)
        self.emit_entity_write("update", occ, ctx, action=action)
        return {"success": True, "occurrence_id": occ.id}

    async def reopen_chore(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("reopen_chore")
        if not role_satisfies(ctx.role, "parent"):
            raise PermissionError("only a parent or system may reopen chore occurrences")

        occurrence_id = params.get("occurrence_id")
        if not occurrence_id:
            raise ValueError("reopen_chore requires occurrence_id")
        existing = self._select_occurrence(occurrence_id, ctx.space_id)
        if existing is None:
            raise ValueError(f"occurrence not found: {occurrence_id}")

        if existing.status == "pending":
            return {"success": True, "occurrence_id": occurrence_id}

        occ = existing.model_copy(
            update={
                "status": "pending",
                "completed_at": None,
                "completed_by": None,
                "skipped_at": None,
                "skip_reason": None,
            }
        ).bump(ctx.user_id)
        self._upsert_occurrence(occ)
        self.emit_entity_write("update", occ, ctx, action=action)
        return {"success": True, "occurrence_id": occ.id}

    async def list_chores(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        rows = self._scan_occurrences(
            space_id=ctx.space_id,
            assigned_to=params.get("assigned_to"),
            status=params.get("status"),
            template_id=params.get("template_id"),
        )
        due_before = params.get("due_before")
        if due_before:
            rows = [r for r in rows if r.get("due_at") is None or r["due_at"] <= due_before]
        visible = filter_rows(rows, ctx, self._policy)
        return {"success": True, "chores": visible, "count": len(visible)}

    async def chore_summary(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        since = params.get("since")
        sql = """
            SELECT assigned_to, status,
                   COUNT(*) AS total,
                   SUM(CASE WHEN status='done' THEN points_awarded ELSE 0 END) AS points
            FROM chore_occurrences
            WHERE space_id=? AND deleted_at IS NULL
        """
        args: list[Any] = [ctx.space_id]
        if since:
            sql += " AND (completed_at >= ? OR skipped_at >= ? OR created_at >= ?)"
            args += [since, since, since]
        sql += " GROUP BY assigned_to, status"

        cur = self._conn.execute(sql, args)
        rows = cur.fetchall()

        # Aggregate into per-member totals.
        members: dict[str, dict[str, Any]] = {}
        for row in rows:
            member_id = row["assigned_to"] or "__unassigned__"
            if member_id not in members:
                members[member_id] = {
                    "member_id": member_id,
                    "pending": 0,
                    "done": 0,
                    "skipped": 0,
                    "total_points": 0,
                }
            members[member_id][row["status"]] = row["total"]
            if row["status"] == "done":
                members[member_id]["total_points"] += row["points"] or 0

        return {
            "success": True,
            "summary": list(members.values()),
            "since": since,
        }

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _assert_occurrence_gate(
        self, occ: ChoreOccurrence, ctx: WriteContext, *, action_name: str
    ) -> None:
        """Raise PermissionError unless caller is assignee or parent+."""
        if (
            ctx.user_id != occ.assigned_to
            and ctx.user_id != occ.actor
            and not role_satisfies(ctx.role, "parent")
        ):
            raise PermissionError(
                f"only the chore assignee or a parent may {action_name} this occurrence"
            )

    def _spec(self, name: str):
        spec = self.DEFINITION.find_action(name)
        if spec is None:  # pragma: no cover
            raise RuntimeError(f"ChoresToolService missing ActionSpec {name!r}")
        return spec

    # ---- templates I/O ------------------------------------------------- #

    def _upsert_template(self, template: ChoreTemplate) -> None:
        data = template.model_dump(mode="json")
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
            "description",
            "assigned_to",
            "frequency",
            "base_points",
            "is_active",
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
            data["description"],
            data["assigned_to"],
            data["frequency"],
            data["base_points"],
            1 if data.get("is_active", True) else 0,
        ]
        ph = ",".join("?" for _ in cols)
        sql = f"INSERT OR REPLACE INTO chore_templates ({','.join(cols)}) VALUES ({ph})"
        with self._conn:
            self._conn.execute(sql, values)

    def _select_template(self, template_id: str, space_id: str) -> Optional[ChoreTemplate]:
        cur = self._conn.execute(
            "SELECT * FROM chore_templates WHERE id=? AND space_id=?",
            (template_id, space_id),
        )
        raw = cur.fetchone()
        if raw is None:
            return None
        row = _decode_cols(_row_to_dict(raw))
        row["is_active"] = bool(row.get("is_active", 1))
        return ChoreTemplate(**row)

    # ---- occurrences I/O ----------------------------------------------- #

    def _upsert_occurrence(self, occ: ChoreOccurrence) -> None:
        data = occ.model_dump(mode="json")
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
            "template_id",
            "title",
            "assigned_to",
            "due_at",
            "completed_at",
            "completed_by",
            "skipped_at",
            "skip_reason",
            "points_awarded",
            "status",
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
            data["template_id"],
            data["title"],
            data["assigned_to"],
            data["due_at"],
            data["completed_at"],
            data["completed_by"],
            data["skipped_at"],
            data["skip_reason"],
            data["points_awarded"],
            data["status"],
        ]
        ph = ",".join("?" for _ in cols)
        sql = f"INSERT OR REPLACE INTO chore_occurrences ({','.join(cols)}) VALUES ({ph})"
        with self._conn:
            self._conn.execute(sql, values)

    def _select_occurrence(self, occurrence_id: str, space_id: str) -> Optional[ChoreOccurrence]:
        cur = self._conn.execute(
            "SELECT * FROM chore_occurrences WHERE id=? AND space_id=?",
            (occurrence_id, space_id),
        )
        raw = cur.fetchone()
        if raw is None:
            return None
        row = _decode_cols(_row_to_dict(raw))
        return ChoreOccurrence(**row)

    def _select_pending_pool_occurrence(
        self,
        template_id: str,
        space_id: str,
    ) -> Optional[ChoreOccurrence]:
        cur = self._conn.execute(
            """
            SELECT * FROM chore_occurrences
            WHERE template_id=?
              AND space_id=?
              AND assigned_to IS NULL
              AND status='pending'
              AND deleted_at IS NULL
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (template_id, space_id),
        )
        raw = cur.fetchone()
        if raw is None:
            return None
        row = _decode_cols(_row_to_dict(raw))
        return ChoreOccurrence(**row)

    def _soft_delete_pending_occurrences(self, template_id: str, space_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn:
            self._conn.execute(
                """
                UPDATE chore_occurrences
                SET deleted_at=?, updated_at=?, version=version+1
                WHERE template_id=?
                  AND space_id=?
                  AND status='pending'
                  AND deleted_at IS NULL
                """,
                (now, now, template_id, space_id),
            )

    def _scan_occurrences(
        self,
        *,
        space_id: str,
        assigned_to: Optional[str],
        status: Optional[str],
        template_id: Optional[str],
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM chore_occurrences WHERE space_id=? AND deleted_at IS NULL"
        args: list[Any] = [space_id]
        if assigned_to:
            sql += " AND assigned_to=?"
            args.append(assigned_to)
        if status:
            sql += " AND status=?"
            args.append(status)
        if template_id:
            sql += " AND template_id=?"
            args.append(template_id)
        sql += " ORDER BY due_at ASC NULLS LAST LIMIT 500"
        cur = self._conn.execute(sql, args)
        return [_decode_cols(_row_to_dict(r)) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Module-private row helpers
# ---------------------------------------------------------------------------


def _row_to_dict(raw: Any) -> dict[str, Any]:
    if hasattr(raw, "keys"):
        return {k: raw[k] for k in raw.keys()}
    return dict(raw)


def _decode_cols(row: dict[str, Any]) -> dict[str, Any]:
    for col in _JSON_COLS:
        val = row.get(col)
        if isinstance(val, str):
            try:
                row[col] = json.loads(val)
            except json.JSONDecodeError:
                logger.warning("chores: failed to decode JSON column %r", col)
    return row
