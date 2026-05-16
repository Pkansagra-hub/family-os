"""k1.tools.family.calendar.service -- ``CalendarToolService``.

Subclass of :class:`BaseToolService` that implements the ten Calendar
actions declared in :data:`CALENDAR_DEFINITION`.

All cross-cutting concerns -- role/band gates, idempotency replay,
audit emission via :class:`EventEmitter`, bus observability -- are
provided by the foundation; this module only owns calendar-specific
persistence (SQLite upserts/selects) and the per-action business
logic.

Reads (``list_events``, ``get_event``, ``list_feeds``) ALWAYS run their
results through :func:`k1.tools.family.acl.filter_rows` so the
visibility band and per-row owner/allow-list gates are applied
uniformly.

Writes (``create_event``, ``update_event``, ``set_visibility`` ...)
ALWAYS:

1. Resolve the effective visibility band via :class:`VisibilityPolicy`,
2. Persist the new revision via ``INSERT OR REPLACE``,
3. Emit a typed audit envelope via
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
from k1.tools.family.calendar.definition import CALENDAR_DEFINITION
from k1.tools.family.calendar.schema import CalendarEvent, ExternalFeed

logger = logging.getLogger(__name__)


# Columns we serialise as JSON in SQLite (mirrors ``BaseEntity`` shape).
_JSON_EVENT_COLS = ("named_visible", "tags", "metadata", "attendees")
_JSON_FEED_COLS = ("named_visible", "tags", "metadata")


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""

    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# CalendarToolService
# ---------------------------------------------------------------------------


class CalendarToolService(BaseToolService):
    """The Family Calendar adapter service."""

    DEFINITION: ClassVar = CALENDAR_DEFINITION
    ENTITY_CLASSES: ClassVar[dict[str, type[BaseEntity]]] = {
        "calendar_event": CalendarEvent,
        "external_feed": ExternalFeed,
    }

    # ------------------------------------------------------------------ #
    # Action handlers -- one per ActionSpec.name in DEFINITION.actions
    # ------------------------------------------------------------------ #

    async def create_event(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("create_event")
        metadata = params.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise ValueError("create_event metadata must be an object")
        try:
            ev = CalendarEvent(
                id=_new_id(),
                space_id=ctx.space_id,
                actor=ctx.user_id,
                visibility=params.get("visibility", "family"),
                named_visible=list(params.get("visible_to") or []),
                title=params["title"],
                start=params["start"],
                end=params["end"],
                location=params.get("location", "") or "",
                notes=params.get("notes", "") or "",
                attendees=list(params.get("attendees") or []),
                rrule=params.get("rrule"),
                metadata=dict(metadata),
            )
        except KeyError as exc:
            raise ValueError(f"create_event missing required field: {exc.args[0]}") from exc

        # Apply visibility policy (may promote ``family`` -> ``adults`` etc.).
        ev = self._apply_visibility(ev, ctx)
        self._upsert_event(ev)
        self.emit_entity_write("create", ev, ctx, action=action)
        return {
            "success": True,
            "event_id": ev.id,
            "version": ev.version,
        }

    async def update_event(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("update_event")
        event_id = params.get("event_id")
        if not event_id:
            raise ValueError("update_event requires event_id")
        existing = self._select_event(event_id, ctx.space_id)
        if existing is None:
            raise ValueError(f"event not found: {event_id}")

        expected = params.get("expected_version")
        if expected is not None and existing.version != int(expected):
            raise ValueError(
                f"stale update_event: have version {existing.version}, "
                f"caller expected {expected}"
            )

        updates: dict[str, Any] = {}
        for field in ("title", "start", "end", "location", "notes", "rrule", "attendees"):
            if field in params and params[field] is not None:
                updates[field] = params[field]
        if "metadata" in params and params["metadata"] is not None:
            if not isinstance(params["metadata"], dict):
                raise ValueError("update_event metadata must be an object")
            updates["metadata"] = {**existing.metadata, **params["metadata"]}

        # ``BaseEntity.bump`` only refreshes the audit columns; apply the
        # business-field updates first, then bump, so the version counter
        # advances exactly once per call.
        if updates:
            existing = existing.model_copy(update=updates)
        ev = existing.bump(ctx.user_id)
        ev = self._apply_visibility(ev, ctx)
        self._upsert_event(ev)
        self.emit_entity_write("update", ev, ctx, action=action)
        return {
            "success": True,
            "event_id": ev.id,
            "version": ev.version,
        }

    async def delete_event(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("delete_event")
        event_id = params.get("event_id")
        if not event_id:
            raise ValueError("delete_event requires event_id")
        existing = self._select_event(event_id, ctx.space_id)
        if existing is None:
            raise ValueError(f"event not found: {event_id}")

        deleted = existing.model_copy(
            update={
                "deleted_at": datetime.now(timezone.utc),
                "version": existing.version + 1,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self._upsert_event(deleted)
        self.emit_entity_write("delete", deleted, ctx, action=action)
        return {"success": True, "event_id": event_id}

    async def list_events(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        rows = self._scan_events(
            space_id=ctx.space_id,
            start=params.get("start"),
            end=params.get("end"),
            source_filter=params.get("source_filter"),
        )
        member_filter = params.get("member_filter")
        if member_filter:
            member_set = set(member_filter)
            rows = [r for r in rows if member_set.intersection(r.get("attendees") or [])]

        visible = filter_rows(rows, ctx, self._policy)
        return {"success": True, "events": visible, "count": len(visible)}

    async def get_event(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        event_id = params.get("event_id")
        if not event_id:
            raise ValueError("get_event requires event_id")
        row = self._row_event(event_id, ctx.space_id)
        if row is None:
            raise ValueError(f"event not found: {event_id}")
        visible = filter_rows([row], ctx, self._policy)
        if not visible:
            raise ValueError(f"event not visible: {event_id}")
        return {"success": True, "event": visible[0]}

    async def respond_to_invite(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("respond_to_invite")
        event_id = params.get("event_id")
        response = params.get("response")
        if not event_id or response not in {"yes", "no", "maybe", "tentative"}:
            raise ValueError(
                "respond_to_invite requires event_id and response in " "{yes,no,maybe,tentative}"
            )
        existing = self._select_event(event_id, ctx.space_id)
        if existing is None:
            raise ValueError(f"event not found: {event_id}")
        if ctx.user_id not in existing.attendees and not role_satisfies(ctx.role, "parent"):
            raise PermissionError("only attendees (or a parent) may RSVP to this event")

        ev = existing.model_copy(update={"response": response}).bump(ctx.user_id)
        self._upsert_event(ev)
        self.emit_entity_write("update", ev, ctx, action=action)
        return {"success": True, "event_id": ev.id, "response": response}

    async def set_visibility(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("set_visibility")
        event_id = params.get("event_id")
        visibility = params.get("visibility")
        if not event_id or visibility not in {"family", "adults", "named", "private"}:
            raise ValueError(
                "set_visibility requires event_id and visibility in "
                "{family,adults,named,private}"
            )
        existing = self._select_event(event_id, ctx.space_id)
        if existing is None:
            raise ValueError(f"event not found: {event_id}")
        ev = existing.model_copy(
            update={
                "visibility": visibility,
                "named_visible": list(params.get("visible_to") or []),
            }
        ).bump(ctx.user_id)
        self._upsert_event(ev)
        self.emit_entity_write("update", ev, ctx, action=action)
        return {"success": True, "event_id": ev.id, "visibility": ev.visibility}

    async def connect_feed(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("connect_feed")
        feed = ExternalFeed(
            id=_new_id(),
            space_id=ctx.space_id,
            actor=ctx.user_id,
            visibility="adults",
            member_id=params.get("member_id") or ctx.user_id,
            feed_source=params["feed_source"],
            account=params["account"],
            enabled=False,
        )
        self._upsert_feed(feed)
        self.emit_entity_write("create", feed, ctx, action=action)
        return {"success": True, "feed_id": feed.id}

    async def disconnect_feed(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        action = self._spec("disconnect_feed")
        feed_id = params.get("feed_id")
        if not feed_id:
            raise ValueError("disconnect_feed requires feed_id")
        feed = self._select_feed(feed_id, ctx.space_id)
        if feed is None:
            raise ValueError(f"feed not found: {feed_id}")
        deleted = feed.model_copy(
            update={
                "deleted_at": datetime.now(timezone.utc),
                "version": feed.version + 1,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self._upsert_feed(deleted)
        self.emit_entity_write("delete", deleted, ctx, action=action)
        return {"success": True, "feed_id": feed_id}

    async def list_feeds(self, params: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
        rows = self._scan_feeds(
            space_id=ctx.space_id,
            member_id=params.get("member_id"),
        )
        visible = filter_rows(rows, ctx, self._policy)
        return {"success": True, "feeds": visible, "count": len(visible)}

    # ------------------------------------------------------------------ #
    # Persistence helpers
    # ------------------------------------------------------------------ #

    def _apply_visibility(self, ev: CalendarEvent, ctx: WriteContext) -> CalendarEvent:
        """Run the configured ``VisibilityPolicy`` on ``ev``."""

        effective = self._policy.apply(ev, ctx.role)
        if effective != ev.visibility:
            return ev.model_copy(update={"visibility": effective})
        return ev

    def _spec(self, name: str):
        spec = self.DEFINITION.find_action(name)
        if spec is None:  # pragma: no cover -- defensive
            raise RuntimeError(f"CalendarToolService missing ActionSpec {name!r}")
        return spec

    # ---- event row I/O ------------------------------------------------- #

    def _upsert_event(self, ev: CalendarEvent) -> None:
        data = ev.model_dump(mode="json")
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
            "start",
            "end",
            "location",
            "notes",
            "attendees",
            "rrule",
            "response",
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
            data["start"],
            data["end"],
            data["location"],
            data["notes"],
            json.dumps(data["attendees"]),
            data["rrule"],
            data["response"],
        ]
        placeholders = ",".join("?" for _ in cols)
        # ``end`` is a SQL reserved keyword; quote it.
        col_sql = ",".join(f'"{c}"' if c == "end" else c for c in cols)
        sql = f"INSERT OR REPLACE INTO calendar_events ({col_sql}) VALUES ({placeholders})"
        with self._conn:
            self._conn.execute(sql, values)

    def _select_event(self, event_id: str, space_id: str) -> Optional[CalendarEvent]:
        row = self._row_event(event_id, space_id)
        if row is None:
            return None
        return CalendarEvent(**self._row_to_event_kwargs(row))

    def _row_event(self, event_id: str, space_id: str) -> Optional[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT * FROM calendar_events WHERE id=? AND space_id=?",
            (event_id, space_id),
        )
        raw = cur.fetchone()
        if raw is None:
            return None
        row = _row_to_dict(raw)
        return _decode_json_cols(row, _JSON_EVENT_COLS)

    def _scan_events(
        self,
        *,
        space_id: str,
        start: Optional[str],
        end: Optional[str],
        source_filter: Optional[list[str]],
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM calendar_events WHERE space_id=?"
        args: list[Any] = [space_id]
        if start:
            sql += ' AND "end" >= ?'
            args.append(start)
        if end:
            sql += " AND start <= ?"
            args.append(end)
        if source_filter:
            placeholders = ",".join("?" for _ in source_filter)
            sql += f" AND source IN ({placeholders})"
            args.extend(source_filter)
        sql += " ORDER BY start ASC LIMIT 500"
        cur = self._conn.execute(sql, args)
        rows = [_decode_json_cols(_row_to_dict(r), _JSON_EVENT_COLS) for r in cur.fetchall()]
        return rows

    @staticmethod
    def _row_to_event_kwargs(row: dict[str, Any]) -> dict[str, Any]:
        # Strip None for optional defaults so Pydantic uses the field default.
        kwargs = dict(row)
        return kwargs

    # ---- feed row I/O -------------------------------------------------- #

    def _upsert_feed(self, feed: ExternalFeed) -> None:
        data = feed.model_dump(mode="json")
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
            "member_id",
            "feed_source",
            "account",
            "sync_token",
            "enabled",
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
            data["member_id"],
            data["feed_source"],
            data["account"],
            data["sync_token"],
            1 if data["enabled"] else 0,
        ]
        placeholders = ",".join("?" for _ in cols)
        sql = f"INSERT OR REPLACE INTO calendar_feeds ({','.join(cols)}) VALUES ({placeholders})"
        with self._conn:
            self._conn.execute(sql, values)

    def _select_feed(self, feed_id: str, space_id: str) -> Optional[ExternalFeed]:
        cur = self._conn.execute(
            "SELECT * FROM calendar_feeds WHERE id=? AND space_id=?",
            (feed_id, space_id),
        )
        raw = cur.fetchone()
        if raw is None:
            return None
        row = _decode_json_cols(_row_to_dict(raw), _JSON_FEED_COLS)
        row["enabled"] = bool(row.get("enabled"))
        return ExternalFeed(**row)

    def _scan_feeds(self, *, space_id: str, member_id: Optional[str]) -> list[dict[str, Any]]:
        sql = "SELECT * FROM calendar_feeds WHERE space_id=?"
        args: list[Any] = [space_id]
        if member_id:
            sql += " AND member_id=?"
            args.append(member_id)
        sql += " ORDER BY created_at ASC LIMIT 500"
        cur = self._conn.execute(sql, args)
        rows = []
        for raw in cur.fetchall():
            row = _decode_json_cols(_row_to_dict(raw), _JSON_FEED_COLS)
            row["enabled"] = bool(row.get("enabled"))
            rows.append(row)
        return rows


# ---------------------------------------------------------------------------
# Module-private row helpers
# ---------------------------------------------------------------------------


def _row_to_dict(raw: Any) -> dict[str, Any]:
    """Coerce a ``sqlite3.Row`` (or tuple from a cursor) into a plain dict."""

    if hasattr(raw, "keys"):
        return {k: raw[k] for k in raw.keys()}
    return dict(raw)


def _decode_json_cols(row: dict[str, Any], cols: tuple[str, ...]) -> dict[str, Any]:
    """Decode the listed JSON-encoded columns back into Python objects."""

    for col in cols:
        val = row.get(col)
        if isinstance(val, str):
            try:
                row[col] = json.loads(val)
            except json.JSONDecodeError:
                logger.warning("calendar: failed to decode JSON column %r", col)
    return row
