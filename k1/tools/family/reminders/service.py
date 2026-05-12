"""k1.tools.family.reminders.service -- ``RemindersToolService``.

Implements the 8 Reminders adapter actions declared in
:data:`REMINDERS_DEFINITION`.

Runtime permission guards
--------------------------
1. ``create_reminder`` cross-member gate:
   ``recipient != ctx.user_id`` → caller must be ``guardian`` or higher.
2. ``update_reminder`` status gate:
   ``reminder.status != 'scheduled'`` → ValueError (immutable after firing).
3. ``snooze_reminder`` / ``dismiss_reminder`` actor gate:
   caller must be ``recipient`` OR ``actor`` (creator) OR ``guardian``+.
4. ``fire_reminder`` system gate:
   ``ctx.role != 'system'`` → PermissionError.
5. ``delete_reminder`` actor gate:
   creator OR ``parent``+.

Design notes
------------
* ``ReminderTrigger`` is serialised to/from a JSON blob in the
  ``trigger`` column.  The ``fire_at`` for time-based triggers is
  duplicated into ... well, extracted in ``list_reminders`` via
  JSON path at query time — not a separate column in M15 (scheduler
  in M16 can add an extracted column via migration).
* SSE fan-out on ``fire_reminder`` carries push-notification payload
  so the UI shell / APNs relay can act without a second round-trip.
* ``create_reminder`` is idempotent via ``idem_key``.
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
from k1.tools.family.reminders.definition import REMINDERS_DEFINITION
from k1.tools.family.reminders.schema import Reminder, ReminderTrigger

logger = logging.getLogger(__name__)

_JSON_REMINDER_COLS = ("named_visible", "tags", "metadata")


def _new_id() -> str:
    return uuid.uuid4().hex


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RemindersToolService(BaseToolService):
    """Family Reminders adapter service."""

    DEFINITION: ClassVar = REMINDERS_DEFINITION
    ENTITY_CLASSES: ClassVar[dict[str, type[BaseEntity]]] = {
        "reminder": Reminder,
    }

    # ------------------------------------------------------------------ #
    # Action handlers
    # ------------------------------------------------------------------ #

    async def create_reminder(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("create_reminder")
        recipient = params.get("recipient")
        if not recipient:
            raise ValueError("create_reminder requires recipient")

        # Cross-member guard: only guardian+ may set reminders for others.
        if recipient != ctx.user_id and not role_satisfies(ctx.role, "guardian"):
            raise PermissionError("only a guardian or parent may set reminders for other members")

        raw_trigger = params.get("trigger")
        if not raw_trigger:
            raise ValueError("create_reminder requires trigger")
        trigger = ReminderTrigger(**raw_trigger) if isinstance(raw_trigger, dict) else raw_trigger

        reminder = Reminder(
            id=_new_id(),
            space_id=ctx.space_id,
            actor=ctx.user_id,
            visibility=params.get("visibility", "family"),
            title=params["title"],
            recipient=recipient,
            trigger=trigger,
            message=params.get("message", ""),
            linked_event_id=params.get("linked_event_id"),
        )
        reminder = self._apply_visibility(reminder, ctx)
        self._upsert_reminder(reminder)
        self.emit_entity_write("create", reminder, ctx, action=action)
        return {"success": True, "reminder_id": reminder.id, "version": reminder.version}

    async def update_reminder(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("update_reminder")
        reminder_id = params.get("reminder_id")
        if not reminder_id:
            raise ValueError("update_reminder requires reminder_id")
        existing = self._select_reminder(reminder_id, ctx.space_id)
        if existing is None:
            raise ValueError(f"reminder not found: {reminder_id}")

        # Status gate: cannot edit after firing.
        if existing.status != "scheduled":
            raise ValueError(
                f"reminder {reminder_id} cannot be updated in status '{existing.status}'; "
                "only 'scheduled' reminders may be edited"
            )

        updates: dict[str, Any] = {}
        if "title" in params and params["title"] is not None:
            updates["title"] = params["title"]
        if "message" in params and params["message"] is not None:
            updates["message"] = params["message"]
        if "trigger" in params and params["trigger"] is not None:
            raw = params["trigger"]
            updates["trigger"] = ReminderTrigger(**raw) if isinstance(raw, dict) else raw

        if updates:
            existing = existing.model_copy(update=updates)
        reminder = existing.bump(ctx.user_id)
        self._upsert_reminder(reminder)
        self.emit_entity_write("update", reminder, ctx, action=action)
        return {"success": True, "reminder_id": reminder.id, "version": reminder.version}

    async def snooze_reminder(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("snooze_reminder")
        reminder_id = params.get("reminder_id")
        snooze_until = params.get("snooze_until")
        if not reminder_id or not snooze_until:
            raise ValueError("snooze_reminder requires reminder_id and snooze_until")
        existing = self._select_reminder(reminder_id, ctx.space_id)
        if existing is None:
            raise ValueError(f"reminder not found: {reminder_id}")

        # Actor gate: recipient, creator, or guardian+.
        self._assert_actor_gate(existing, ctx, action_name="snooze")

        # fired_at may already be set (normal snooze); if not, stamp it now.
        fired_at = existing.fired_at or _now_iso()
        reminder = existing.model_copy(
            update={"status": "snoozed", "snoozed_until": snooze_until, "fired_at": fired_at}
        ).bump(ctx.user_id)
        self._upsert_reminder(reminder)
        self.emit_entity_write("update", reminder, ctx, action=action)
        return {
            "success": True,
            "reminder_id": reminder.id,
            "snoozed_until": snooze_until,
        }

    async def dismiss_reminder(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("dismiss_reminder")
        reminder_id = params.get("reminder_id")
        if not reminder_id:
            raise ValueError("dismiss_reminder requires reminder_id")
        existing = self._select_reminder(reminder_id, ctx.space_id)
        if existing is None:
            raise ValueError(f"reminder not found: {reminder_id}")

        # Idempotent: already dismissed.
        if existing.status == "dismissed":
            return {"success": True, "reminder_id": reminder_id}

        # Actor gate: recipient, creator, or guardian+.
        self._assert_actor_gate(existing, ctx, action_name="dismiss")

        fired_at = existing.fired_at or _now_iso()
        reminder = existing.model_copy(
            update={"status": "dismissed", "fired_at": fired_at, "snoozed_until": None}
        ).bump(ctx.user_id)
        self._upsert_reminder(reminder)
        self.emit_entity_write("update", reminder, ctx, action=action)
        return {"success": True, "reminder_id": reminder.id}

    async def fire_reminder(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        """System-only — called by K1 scheduler when a trigger condition is met.

        Stamps ``status='fired'`` and ``fired_at``, then emits an SSE envelope
        that carries push-notification payload for APNs/FCM relay.
        """
        action = self._spec("fire_reminder")

        # System gate: only the scheduler may fire reminders.
        if ctx.role != "system":
            raise PermissionError("fire_reminder is system-only; LLM must not call this")

        reminder_id = params.get("reminder_id")
        if not reminder_id:
            raise ValueError("fire_reminder requires reminder_id")
        existing = self._select_reminder(reminder_id, ctx.space_id)
        if existing is None:
            raise ValueError(f"reminder not found: {reminder_id}")

        # Idempotent: already fired.
        if existing.status == "fired":
            return {
                "success": True,
                "reminder_id": reminder_id,
                "fired_at": existing.fired_at,
                "push_title": existing.title,
                "push_body": existing.message,
                "push_recipient_ids": [existing.recipient],
            }

        now = _now_iso()
        reminder = existing.model_copy(
            update={"status": "fired", "fired_at": now, "snoozed_until": None}
        ).bump(ctx.user_id)
        self._upsert_reminder(reminder)
        self.emit_entity_write("update", reminder, ctx, action=action)
        return {
            "success": True,
            "reminder_id": reminder.id,
            "fired_at": now,
            "push_title": reminder.title,
            "push_body": reminder.message or reminder.title,
            "push_recipient_ids": [reminder.recipient],
        }

    async def delete_reminder(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("delete_reminder")
        reminder_id = params.get("reminder_id")
        if not reminder_id:
            raise ValueError("delete_reminder requires reminder_id")
        existing = self._select_reminder(reminder_id, ctx.space_id)
        if existing is None:
            raise ValueError(f"reminder not found: {reminder_id}")

        # Delete gate: creator OR parent+.
        if existing.actor != ctx.user_id and not role_satisfies(ctx.role, "parent"):
            raise PermissionError("only the reminder creator or a parent may delete this reminder")

        deleted = existing.model_copy(
            update={
                "deleted_at": datetime.now(timezone.utc),
                "version": existing.version + 1,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self._upsert_reminder(deleted)
        self.emit_entity_write("delete", deleted, ctx, action=action)
        return {"success": True, "reminder_id": reminder_id}

    async def list_reminders(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        rows = self._scan_reminders(
            space_id=ctx.space_id,
            recipient=params.get("recipient"),
            status=params.get("status"),
        )
        # due_before filter: only works for time-based triggers (fire_at in trigger JSON)
        due_before = params.get("due_before")
        if due_before:
            rows = [
                r
                for r in rows
                if _trigger_fire_at(r.get("trigger")) is None
                or _trigger_fire_at(r.get("trigger")) <= due_before
            ]
        visible = filter_rows(rows, ctx, self._policy)
        return {"success": True, "reminders": visible, "count": len(visible)}

    async def get_reminder(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        reminder_id = params.get("reminder_id")
        if not reminder_id:
            raise ValueError("get_reminder requires reminder_id")
        row = self._row_reminder(reminder_id, ctx.space_id)
        if row is None:
            raise ValueError(f"reminder not found: {reminder_id}")
        visible = filter_rows([row], ctx, self._policy)
        if not visible:
            raise ValueError(f"reminder not visible: {reminder_id}")
        return {"success": True, "reminder": visible[0]}

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _assert_actor_gate(
        self, reminder: Reminder, ctx: WriteContext, *, action_name: str
    ) -> None:
        """Raise PermissionError unless caller is recipient, creator, or guardian+."""
        if (
            ctx.user_id != reminder.recipient
            and ctx.user_id != reminder.actor
            and not role_satisfies(ctx.role, "guardian")
        ):
            raise PermissionError(
                f"only the reminder recipient, creator, or a guardian may {action_name} this reminder"
            )

    def _apply_visibility(self, reminder: Reminder, ctx: WriteContext) -> Reminder:
        effective = self._policy.apply(reminder, ctx.role)
        if effective != reminder.visibility:
            return reminder.model_copy(update={"visibility": effective})
        return reminder

    def _spec(self, name: str):
        spec = self.DEFINITION.find_action(name)
        if spec is None:  # pragma: no cover
            raise RuntimeError(f"RemindersToolService missing ActionSpec {name!r}")
        return spec

    # ---- reminders I/O ------------------------------------------------- #

    def _upsert_reminder(self, reminder: Reminder) -> None:
        data = reminder.model_dump(mode="json")
        # Serialise ReminderTrigger to JSON string for storage.
        trigger_raw = data.get("trigger")
        if isinstance(trigger_raw, dict):
            trigger_json = json.dumps(trigger_raw)
        else:
            trigger_json = json.dumps({})

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
            "recipient",
            "trigger",
            "message",
            "status",
            "snoozed_until",
            "fired_at",
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
            data["recipient"],
            trigger_json,
            data["message"],
            data["status"],
            data["snoozed_until"],
            data["fired_at"],
            data["linked_event_id"],
        ]
        placeholders = ",".join("?" for _ in cols)
        sql = f"INSERT OR REPLACE INTO reminders ({','.join(cols)}) " f"VALUES ({placeholders})"
        with self._conn:
            self._conn.execute(sql, values)

    def _select_reminder(self, reminder_id: str, space_id: str) -> Optional[Reminder]:
        row = self._row_reminder(reminder_id, space_id)
        if row is None:
            return None
        # Deserialise trigger back to ReminderTrigger.
        trigger_raw = row.get("trigger")
        if isinstance(trigger_raw, dict):
            row["trigger"] = ReminderTrigger(**trigger_raw)
        return Reminder(**row)

    def _row_reminder(self, reminder_id: str, space_id: str) -> Optional[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT * FROM reminders WHERE id=? AND space_id=?",
            (reminder_id, space_id),
        )
        raw = cur.fetchone()
        if raw is None:
            return None
        return _decode_reminder_cols(_row_to_dict(raw))

    def _scan_reminders(
        self,
        *,
        space_id: str,
        recipient: Optional[str],
        status: Optional[str],
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM reminders WHERE space_id=?"
        args: list[Any] = [space_id]
        if recipient:
            sql += " AND recipient=?"
            args.append(recipient)
        if status:
            sql += " AND status=?"
            args.append(status)
        sql += " ORDER BY created_at ASC LIMIT 500"
        cur = self._conn.execute(sql, args)
        return [_decode_reminder_cols(_row_to_dict(r)) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Module-private row helpers
# ---------------------------------------------------------------------------


def _row_to_dict(raw: Any) -> dict[str, Any]:
    if hasattr(raw, "keys"):
        return {k: raw[k] for k in raw.keys()}
    return dict(raw)


def _decode_reminder_cols(row: dict[str, Any]) -> dict[str, Any]:
    """Decode JSON string columns back to Python objects."""
    for col in _JSON_REMINDER_COLS:
        val = row.get(col)
        if isinstance(val, str):
            try:
                row[col] = json.loads(val)
            except json.JSONDecodeError:
                logger.warning("reminders: failed to decode JSON column %r", col)
    # Decode trigger blob → dict (ReminderTrigger deserialization done in _select_reminder)
    trigger_val = row.get("trigger")
    if isinstance(trigger_val, str):
        try:
            row["trigger"] = json.loads(trigger_val)
        except json.JSONDecodeError:
            logger.warning("reminders: failed to decode trigger JSON")
            row["trigger"] = {}
    return row


def _trigger_fire_at(trigger: Any) -> Optional[str]:
    """Extract fire_at from a trigger dict/object if kind='time'."""
    if isinstance(trigger, dict) and trigger.get("kind") == "time":
        return trigger.get("fire_at")
    return None
