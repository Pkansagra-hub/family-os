"""SSE mux implementation for the kernel."""

from __future__ import annotations

import json
import secrets
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, cast

import yaml
from fastapi import HTTPException, status

from k0.obs import ObservabilityEmitter
from k0.qos import QoSContext
from k0.storage.offsets import Offset, OffsetStore
from k0.storage.wal import WalEntry, WriteAheadLog

if TYPE_CHECKING:
    import asyncpg


@dataclass(slots=True)
class CursorState:
    """Represents decoded cursor parameters."""

    last_position: int
    last_ts: datetime
    subscriber_id: str | None = None
    topic: str | None = None
    space_id: str | None = None
    tenant_id: str | None = None


@dataclass(slots=True)
class BackpressureTopicMetrics:
    topic: str
    pending_events: int
    lag_ms: int
    cursor: str | None


@dataclass(slots=True)
class BackpressureMetrics:
    level: str
    lag_ms: int
    pending_events: int
    topics: list[BackpressureTopicMetrics]
    ack_offsets: Mapping[str, int]


@dataclass(slots=True)
class SSEServer:
    """Manage SSE subscriptions and acknowledgements."""

    wal: WriteAheadLog
    offset_store: OffsetStore
    observability: ObservabilityEmitter
    acl_path: Path
    qos: QoSContext
    database_connection: "asyncpg.Connection | None" = None
    max_batch: int = 128

    # Gap 25: Configurable SSE backpressure thresholds
    max_pending_events: int = 1_000
    disconnect_threshold: int = 10_000
    WARNING_LAG_MS: int = 2_000
    WARNING_PENDING: int = 5_000
    THROTTLE_LAG_MS: int = 5_000
    THROTTLE_PENDING: int = 20_000
    SHED_LAG_MS: int = 15_000
    SHED_PENDING: int = 50_000

    async def subscribe(
        self,
        *,
        tenant_id: str,
        space_id: str,
        subscriber_id: str,
        topics: Sequence[str],
        roles: Sequence[str],
        cursor_token: str | None,
        fanout_limit: int | None = None,
    ) -> tuple[list[WalEntry], list[str]]:
        fanout_limit = fanout_limit or self.max_batch
        if fanout_limit <= 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "INVALID_FANOUT_LIMIT")

        permitted_topics = self._load_acl(topics, roles)
        if not permitted_topics:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "TOPIC_ACCESS_DENIED")

        last_position = 0
        if cursor_token:
            cursor_state = self._decode_cursor(cursor_token)
            if cursor_state.subscriber_id and cursor_state.subscriber_id != subscriber_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "CURSOR_SUBSCRIBER_MISMATCH")
            if cursor_state.space_id and cursor_state.space_id != space_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "CURSOR_SCOPE_MISMATCH")
            if cursor_state.tenant_id and cursor_state.tenant_id != tenant_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "CURSOR_SCOPE_MISMATCH")
            last_position = cursor_state.last_position

        rows = await self.wal.read_from(
            last_position,
            min(fanout_limit, self.max_batch),
            connection=self.database_connection,
        )
        filtered_rows: list[WalEntry] = []
        for row in rows:
            if not self._topic_allowed(row.topic, permitted_topics):
                continue
            if row.space_id != space_id or row.tenant_id != tenant_id:
                continue
            filtered_rows.append(row)

        return filtered_rows, permitted_topics

    async def evaluate_backpressure(
        self,
        *,
        subscriber_id: str,
        tenant_id: str,
        space_id: str,
        topics: Sequence[str],
    ) -> BackpressureMetrics:
        total_pending = 0
        max_lag_ms = 0
        topic_metrics: list[BackpressureTopicMetrics] = []
        ack_offsets: dict[str, int] = {}
        now = datetime.now(tz=timezone.utc)

        for topic in topics:
            offset_record = await self.offset_store.fetch(
                subscriber_id,
                topic,
                space_id,
                tenant_id,
                connection=self.database_connection,
            )
            offset_value = int(offset_record.offset) if offset_record else 0
            ack_offsets[topic] = offset_value
            ack_ts_raw = offset_record.updated_ts if offset_record else None
            ack_ts = self._parse_iso8601(ack_ts_raw) if ack_ts_raw else None

            stats = await self.wal.backlog_stats(
                tenant_id=tenant_id,
                space_id=space_id,
                topic=topic,
                offset=offset_value,
                connection=self.database_connection,
            )

            pending = stats.pending_events
            total_pending += pending

            if stats.latest_commit_ts:
                latest_commit_ts = self._parse_iso8601(stats.latest_commit_ts)
                reference = ack_ts or latest_commit_ts
                lag_delta = latest_commit_ts - reference
                lag_ms = max(int(lag_delta.total_seconds() * 1000), 0)
            else:
                lag_ms = 0

            max_lag_ms = max(max_lag_ms, lag_ms)

            cursor_token: str | None = None
            if offset_value > 0:
                cursor_token = self.build_cursor(
                    subscriber_id=subscriber_id,
                    tenant_id=tenant_id,
                    space_id=space_id,
                    topic=topic,
                    offset=offset_value,
                    commit_ts=(ack_ts_raw or now.isoformat().replace("+00:00", "Z")),
                )

            topic_metrics.append(
                BackpressureTopicMetrics(
                    topic=topic,
                    pending_events=pending,
                    lag_ms=lag_ms,
                    cursor=cursor_token,
                )
            )

        level = "normal"
        if max_lag_ms > self.SHED_LAG_MS or total_pending > self.SHED_PENDING:
            level = "shed"
        elif max_lag_ms > self.THROTTLE_LAG_MS or total_pending > self.THROTTLE_PENDING:
            level = "throttle"
        elif max_lag_ms > self.WARNING_LAG_MS or total_pending > self.WARNING_PENDING:
            level = "warning"

        return BackpressureMetrics(
            level=level,
            lag_ms=max_lag_ms,
            pending_events=total_pending,
            topics=topic_metrics,
            ack_offsets=ack_offsets,
        )

    async def acknowledge(
        self,
        *,
        subscriber_id: str,
        tenant_id: str,
        space_id: str,
        topic: str,
        offset: int,
        ack_ts: datetime | None = None,
    ) -> None:
        if offset < 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "NEGATIVE_OFFSET")
        ack_ts = ack_ts or datetime.now(tz=timezone.utc)
        record = Offset(
            subscriber_id=subscriber_id,
            topic=topic,
            space_id=space_id,
            tenant_id=tenant_id,
            offset=offset,
            updated_ts=ack_ts.isoformat(),
        )
        await self.offset_store.upsert(record, connection=self.database_connection)

    def _load_acl(
        self,
        requested_topics: Sequence[str],
        roles: Sequence[str],
    ) -> list[str]:
        try:
            document_obj: Any = yaml.safe_load(self.acl_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "ACL_PARSE_ERROR") from exc

        if not isinstance(document_obj, dict):
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "ACL_INVALID_SHAPE")

        document = cast(dict[str, Any], document_obj)

        roles_map_obj = document.get("roles", {})
        if not isinstance(roles_map_obj, dict):
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "ACL_INVALID_ROLES")
        roles_map = cast(dict[str, Any], roles_map_obj)
        allowed_patterns: set[str] = set()
        for role in roles:
            entries_obj = roles_map.get(role, {})
            if not isinstance(entries_obj, dict):
                continue
            entries = cast(dict[str, Any], entries_obj)
            allow_raw = entries.get("allow", [])
            if not isinstance(allow_raw, list):
                continue
            allow_list = cast(list[Any], allow_raw)
            for pattern in allow_list:
                if isinstance(pattern, str):
                    allowed_patterns.add(pattern)
        permitted = [
            topic for topic in requested_topics if self._topic_allowed(topic, allowed_patterns)
        ]
        return permitted

    def _topic_allowed(self, topic: str, patterns: Iterable[str]) -> bool:
        for pattern in patterns:
            if topic.startswith(pattern.rstrip("*")):
                return True
        return False

    def _decode_cursor(self, token: str) -> CursorState:
        import time

        validation_start = time.perf_counter()

        try:
            payload = json.loads(token)
        except json.JSONDecodeError as exc:
            # Gap 48: Track invalid cursor with MALFORMED reason
            self.observability.emit_metric("sse_invalid_cursor_total", 1.0, reason="MALFORMED")
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "CURSOR_DECODE_ERROR") from exc

        try:
            position = int(payload.get("offset", payload.get("pos")))
            ts_raw = payload["ts"]
            ts = self._parse_iso8601(ts_raw)
        except (KeyError, ValueError, TypeError) as exc:
            # Gap 48: Track invalid cursor with MALFORMED reason
            self.observability.emit_metric("sse_invalid_cursor_total", 1.0, reason="MALFORMED")
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "CURSOR_FIELDS_MISSING") from exc

        if position < 0:
            # Gap 48: Track invalid cursor with NEGATIVE reason
            self.observability.emit_metric("sse_invalid_cursor_total", 1.0, reason="NEGATIVE")
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "CURSOR_NEGATIVE_POSITION")

        # Gap 48: Track successful cursor validation latency
        validation_duration = time.perf_counter() - validation_start
        self.observability.emit_metric("sse_cursor_validation_seconds", validation_duration)

        subscriber_id = payload.get("subscriber_id")
        topic = payload.get("topic")
        space_id = payload.get("space_id")
        tenant_id = payload.get("tenant_id")
        return CursorState(
            last_position=position,
            last_ts=ts,
            subscriber_id=subscriber_id,
            topic=topic,
            space_id=space_id,
            tenant_id=tenant_id,
        )

    def build_cursor(
        self,
        *,
        subscriber_id: str,
        tenant_id: str,
        space_id: str,
        topic: str,
        offset: int,
        commit_ts: str,
    ) -> str:
        cursor_payload: dict[str, str | int] = {
            "subscriber_id": subscriber_id,
            "tenant_id": tenant_id,
            "space_id": space_id,
            "topic": topic,
            "offset": int(offset),
            "ts": commit_ts,
            "nonce": secrets.token_hex(8),
        }
        return json.dumps(cursor_payload)

    @staticmethod
    def _parse_iso8601(value: str) -> datetime:
        candidate = value.strip()
        if candidate.endswith("Z") or candidate.endswith("z"):
            candidate = f"{candidate[:-1]}+00:00"
        parsed = datetime.fromisoformat(candidate)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
