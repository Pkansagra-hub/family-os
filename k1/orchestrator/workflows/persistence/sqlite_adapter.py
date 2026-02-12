"""
k1.orchestrator.workflows.persistence.sqlite_adapter -- SQLiteWorkflowAdapter (4.1.5).

Production persistence backend for IWorkflowStoragePort.

Design:
  - Uses SQLite in WAL mode (ADR-1.1.9) for edge-first local persistence.
  - Async port methods implemented via ``asyncio.to_thread`` to keep the
    Orchestrator event loop responsive.
  - Stores JSON blobs for WorkflowSpec and run/gap payloads.
  - All timestamps are floats (time.time()) -- timezone-agnostic.

Schema (V1 = version 1):
  workflows, triggers, runs, gaps (+ schema_version).

Exports:
  SQLiteWorkflowAdapter
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, is_dataclass, replace
from typing import Any, Dict, List, Optional, Tuple

from k1.orchestrator.ports.workflow_storage_port import IWorkflowStoragePort
from k1.orchestrator.types import (
    PlanStep,
    ProactiveGap,
    ProactiveGapStatus,
    TriggerSpec,
    TriggerType,
)
from k1.orchestrator.workflows.workflow_types import WorkflowSpec

_SCHEMA_VERSION = 1
_MAX_FLOAT = 1.0e30


class SQLiteWorkflowAdapter(IWorkflowStoragePort):
    """SQLite-backed implementation of IWorkflowStoragePort."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        # One connection, used behind a lock. Calls run in a background thread.
        self._conn = sqlite3.connect(
            db_path,
            isolation_level=None,  # autocommit; we use explicit transactions
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row

        self._init_db()

    def close(self) -> None:
        """Close the underlying SQLite connection.

        Not part of IWorkflowStoragePort; provided for test cleanup.
        """
        with self._lock:
            self._conn.close()

    # ---------------------------------------------------------------------
    # Public port methods (async)
    # ---------------------------------------------------------------------

    async def save_workflow(self, spec: WorkflowSpec) -> None:
        payload = self._serialize_workflow_spec(spec)
        await asyncio.to_thread(self._save_workflow_sync, spec, payload)

    async def get_workflow(self, workflow_id: str) -> Optional[WorkflowSpec]:
        row = await asyncio.to_thread(self._get_workflow_row_sync, workflow_id)
        if row is None:
            return None
        return self._deserialize_workflow_spec(row["spec_json"])

    async def list_workflows(self, active_only: bool = True) -> List[WorkflowSpec]:
        rows = await asyncio.to_thread(self._list_workflow_rows_sync, active_only)
        return [self._deserialize_workflow_spec(r["spec_json"]) for r in rows]

    async def delete_workflow(self, workflow_id: str) -> None:
        await asyncio.to_thread(self._soft_delete_workflow_sync, workflow_id)

    async def purge_workflow(self, workflow_id: str) -> None:
        await asyncio.to_thread(self._purge_workflow_sync, workflow_id)

    async def save_trigger(self, workflow_id: str, trigger: TriggerSpec) -> None:
        await asyncio.to_thread(self._save_trigger_sync, workflow_id, trigger)

    async def get_due_triggers(self, now: float) -> List[Tuple[str, TriggerSpec]]:
        rows = await asyncio.to_thread(self._get_due_triggers_rows_sync, now)
        result: List[Tuple[str, TriggerSpec]] = []
        for r in rows:
            result.append((r["workflow_id"], self._deserialize_trigger_spec(r)))
        return result

    async def update_trigger_state(
        self, workflow_id: str, next_fire: float, last_fire: float
    ) -> None:
        await asyncio.to_thread(
            self._update_trigger_state_sync,
            workflow_id,
            float(next_fire),
            float(last_fire),
        )

    async def save_run(self, manifest: object) -> None:
        await asyncio.to_thread(self._save_run_sync, manifest)

    async def get_runs(self, workflow_id: str, limit: int = 10) -> list:
        rows = await asyncio.to_thread(self._get_runs_rows_sync, workflow_id, limit)
        # V1: return raw dicts (RunManifest type lands in 4.2.4).
        return [json.loads(r["manifest_json"]) for r in rows]

    async def save_gap(self, gap: ProactiveGap) -> None:
        await asyncio.to_thread(self._save_gap_sync, gap)

    async def get_pending_gaps(self) -> List[ProactiveGap]:
        rows = await asyncio.to_thread(self._get_pending_gaps_rows_sync)
        return [self._deserialize_gap(r) for r in rows]

    # ---------------------------------------------------------------------
    # Initialization / migrations
    # ---------------------------------------------------------------------

    def _init_db(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")

            cur.execute(
                "CREATE TABLE IF NOT EXISTS schema_version (schema_version INTEGER NOT NULL)"
            )
            row = cur.execute("SELECT schema_version FROM schema_version").fetchone()
            if row is None:
                cur.execute("DELETE FROM schema_version")
                cur.execute(
                    "INSERT INTO schema_version(schema_version) VALUES (?)", (_SCHEMA_VERSION,)
                )
                self._apply_schema_v1(cur)
            else:
                current = int(row[0])
                if current < 1:
                    self._apply_schema_v1(cur)
                    cur.execute("UPDATE schema_version SET schema_version=?", (_SCHEMA_VERSION,))
                elif current > _SCHEMA_VERSION:
                    raise RuntimeError(
                        f"SQLiteWorkflowAdapter: DB schema_version {current} newer than supported {_SCHEMA_VERSION}"
                    )

            cur.close()

    @staticmethod
    def _apply_schema_v1(cur: sqlite3.Cursor) -> None:
        # Workflows
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS workflows (
                workflow_id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                spec_json TEXT NOT NULL,
                active INTEGER DEFAULT 1,
                version TEXT NOT NULL,
                created_at REAL,
                updated_at REAL
            )
            """
        )

        # Triggers
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS triggers (
                trigger_id TEXT PRIMARY KEY,
                workflow_id TEXT REFERENCES workflows(workflow_id) ON DELETE CASCADE,
                type TEXT NOT NULL,
                schedule TEXT,
                timezone TEXT DEFAULT 'UTC',
                event_topic TEXT,
                enabled INTEGER DEFAULT 1,
                next_fire_time REAL,
                last_fire_time REAL
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_triggers_next_fire_time ON triggers(next_fire_time)"
        )

        # Runs
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                workflow_id TEXT REFERENCES workflows(workflow_id) ON DELETE CASCADE,
                version TEXT,
                compiled_hash TEXT,
                trigger_type TEXT,
                status TEXT,
                started_at REAL,
                completed_at REAL,
                manifest_json TEXT
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_runs_workflow_started ON runs(workflow_id, started_at DESC)"
        )

        # Gaps
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS gaps (
                gap_id TEXT PRIMARY KEY,
                workflow_id TEXT REFERENCES workflows(workflow_id) ON DELETE CASCADE,
                capability TEXT,
                gap_type TEXT,
                description TEXT,
                status TEXT DEFAULT 'PENDING',
                detected_at REAL,
                resolved_at REAL,
                gap_json TEXT
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_gaps_status ON gaps(status)")

    # ---------------------------------------------------------------------
    # Workflow CRUD (sync)
    # ---------------------------------------------------------------------

    def _save_workflow_sync(self, spec: WorkflowSpec, spec_json: str) -> None:
        with self._lock:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO workflows(
                        workflow_id, name, spec_json, active, version, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(workflow_id) DO UPDATE SET
                        name=excluded.name,
                        spec_json=excluded.spec_json,
                        active=excluded.active,
                        version=excluded.version,
                        created_at=excluded.created_at,
                        updated_at=excluded.updated_at
                    """,
                    (
                        spec.workflow_id,
                        spec.name,
                        spec_json,
                        1 if spec.active else 0,
                        spec.version,
                        float(spec.created_at),
                        float(spec.updated_at),
                    ),
                )

    def _get_workflow_row_sync(self, workflow_id: str) -> Optional[sqlite3.Row]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT spec_json FROM workflows WHERE workflow_id=?", (workflow_id,)
            )
            row = cur.fetchone()
            return row

    def _list_workflow_rows_sync(self, active_only: bool) -> List[sqlite3.Row]:
        with self._lock:
            if active_only:
                cur = self._conn.execute(
                    "SELECT spec_json FROM workflows WHERE active=1 ORDER BY name"
                )
            else:
                cur = self._conn.execute("SELECT spec_json FROM workflows ORDER BY name")
            return list(cur.fetchall())

    def _soft_delete_workflow_sync(self, workflow_id: str) -> None:
        with self._lock:
            row = self._conn.execute(
                "SELECT spec_json FROM workflows WHERE workflow_id=?", (workflow_id,)
            ).fetchone()
            if row is None:
                return
            spec = self._deserialize_workflow_spec(row["spec_json"])
            updated = replace(spec, active=False, updated_at=time.time())
            payload = self._serialize_workflow_spec(updated)
            with self._conn:
                self._conn.execute(
                    "UPDATE workflows SET active=0, spec_json=?, updated_at=? WHERE workflow_id=?",
                    (payload, float(updated.updated_at), workflow_id),
                )

    def _purge_workflow_sync(self, workflow_id: str) -> None:
        with self._lock:
            with self._conn:
                self._conn.execute("DELETE FROM workflows WHERE workflow_id=?", (workflow_id,))
                # ON DELETE CASCADE handles triggers/runs/gaps

    # ---------------------------------------------------------------------
    # Trigger state (sync)
    # ---------------------------------------------------------------------

    @staticmethod
    def _parse_enum_value(raw: object) -> str:
        """Normalize enum-like string values.

        Accepts either:
          - "CRON" (preferred persisted form)
          - "TriggerType.CRON" (legacy string(EnumMember) form)
        """
        s = "" if raw is None else str(raw)
        if "." in s:
            # e.g. "TriggerType.CRON" -> "CRON"
            s = s.split(".", 1)[1]
        return s

    def _save_trigger_sync(self, workflow_id: str, trigger: TriggerSpec) -> None:
        trigger_id = f"trg-{workflow_id}"
        next_fire = self._initial_next_fire_time(trigger)
        last_fire = None
        with self._lock:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO triggers(
                        trigger_id, workflow_id, type, schedule, timezone, event_topic,
                        enabled, next_fire_time, last_fire_time
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(trigger_id) DO UPDATE SET
                        type=excluded.type,
                        schedule=excluded.schedule,
                        timezone=excluded.timezone,
                        event_topic=excluded.event_topic,
                        enabled=excluded.enabled
                    """,
                    (
                        trigger_id,
                        workflow_id,
                        trigger.type.value,
                        trigger.schedule,
                        trigger.timezone,
                        trigger.event_topic,
                        1 if trigger.enabled else 0,
                        float(next_fire),
                        last_fire,
                    ),
                )

    @staticmethod
    def _initial_next_fire_time(trigger: TriggerSpec) -> float:
        if not trigger.enabled:
            return _MAX_FLOAT
        if trigger.type == TriggerType.CRON:
            # Let the scheduler compute the real next fire; make it "due" on startup.
            return 0.0
        # EVENT and MANUAL are not time-driven.
        return _MAX_FLOAT

    def _get_due_triggers_rows_sync(self, now: float) -> List[sqlite3.Row]:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT workflow_id, type, schedule, timezone, event_topic, enabled,
                       next_fire_time, last_fire_time
                FROM triggers
                WHERE enabled=1 AND next_fire_time <= ?
                ORDER BY next_fire_time ASC
                """,
                (float(now),),
            )
            return list(cur.fetchall())

    def _update_trigger_state_sync(
        self, workflow_id: str, next_fire: float, last_fire: float
    ) -> None:
        trigger_id = f"trg-{workflow_id}"
        with self._lock:
            with self._conn:
                self._conn.execute(
                    """
                    UPDATE triggers
                    SET next_fire_time=?, last_fire_time=?
                    WHERE trigger_id=?
                    """,
                    (float(next_fire), float(last_fire), trigger_id),
                )

    @staticmethod
    def _deserialize_trigger_spec(row: sqlite3.Row) -> TriggerSpec:
        return TriggerSpec(
            type=TriggerType(SQLiteWorkflowAdapter._parse_enum_value(row["type"])),
            schedule=row["schedule"],
            timezone=row["timezone"] or "UTC",
            event_topic=row["event_topic"],
            enabled=bool(row["enabled"]),
        )

    # ---------------------------------------------------------------------
    # Runs (sync)
    # ---------------------------------------------------------------------

    def _save_run_sync(self, manifest: object) -> None:
        run_id = getattr(manifest, "run_id", None) or str(uuid.uuid4())
        workflow_id = getattr(manifest, "workflow_id", "")
        version = getattr(manifest, "version", None)
        compiled_hash = getattr(manifest, "compiled_hash", None)
        trigger_type = getattr(manifest, "trigger_type", None)
        status = getattr(manifest, "status", None)
        started_at = getattr(manifest, "started_at", None)
        completed_at = getattr(manifest, "completed_at", None)

        manifest_json = json.dumps(self._jsonable(manifest), sort_keys=True, default=str)

        with self._lock:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO runs(
                        run_id, workflow_id, version, compiled_hash, trigger_type,
                        status, started_at, completed_at, manifest_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id) DO UPDATE SET
                        workflow_id=excluded.workflow_id,
                        version=excluded.version,
                        compiled_hash=excluded.compiled_hash,
                        trigger_type=excluded.trigger_type,
                        status=excluded.status,
                        started_at=excluded.started_at,
                        completed_at=excluded.completed_at,
                        manifest_json=excluded.manifest_json
                    """,
                    (
                        str(run_id),
                        workflow_id,
                        version,
                        compiled_hash,
                        str(trigger_type) if trigger_type is not None else None,
                        str(status) if status is not None else None,
                        float(started_at) if started_at is not None else None,
                        float(completed_at) if completed_at is not None else None,
                        manifest_json,
                    ),
                )

    def _get_runs_rows_sync(self, workflow_id: str, limit: int) -> List[sqlite3.Row]:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT manifest_json
                FROM runs
                WHERE workflow_id=?
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (workflow_id, int(limit)),
            )
            return list(cur.fetchall())

    # ---------------------------------------------------------------------
    # Gaps (sync)
    # ---------------------------------------------------------------------

    def _save_gap_sync(self, gap: ProactiveGap) -> None:
        gap_json = json.dumps(self._jsonable(gap), sort_keys=True, default=str)
        with self._lock:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO gaps(
                        gap_id, workflow_id, capability, gap_type, description,
                        status, detected_at, resolved_at, gap_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(gap_id) DO UPDATE SET
                        workflow_id=excluded.workflow_id,
                        capability=excluded.capability,
                        gap_type=excluded.gap_type,
                        description=excluded.description,
                        status=excluded.status,
                        detected_at=excluded.detected_at,
                        resolved_at=excluded.resolved_at,
                        gap_json=excluded.gap_json
                    """,
                    (
                        gap.gap_id,
                        gap.workflow_id,
                        gap.capability_name,
                        gap.gap_type,
                        gap.description,
                        gap.status.value,
                        float(gap.detected_at),
                        None,
                        gap_json,
                    ),
                )

    def _get_pending_gaps_rows_sync(self) -> List[sqlite3.Row]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT gap_json FROM gaps WHERE status=? ORDER BY detected_at ASC",
                (ProactiveGapStatus.PENDING.value,),
            )
            return list(cur.fetchall())

    @staticmethod
    def _deserialize_gap(row: sqlite3.Row) -> ProactiveGap:
        data = json.loads(row["gap_json"])
        status_val = data.get("status", ProactiveGapStatus.PENDING.value)
        return ProactiveGap(
            workflow_id=data["workflow_id"],
            gap_type=data["gap_type"],
            affected_step_id=data.get("affected_step_id", ""),
            capability_name=data.get("capability_name", data.get("capability", "")),
            old_contract_version=data.get("old_contract_version", ""),
            new_contract_version=data.get("new_contract_version", ""),
            description=data.get("description", ""),
            justification=data.get("justification", ""),
            gap_id=data.get("gap_id", str(uuid.uuid4())),
            detected_at=float(data.get("detected_at", time.time())),
            question=data.get("question"),
            status=ProactiveGapStatus(SQLiteWorkflowAdapter._parse_enum_value(status_val)),
            resolved_value=data.get("resolved_value"),
        )

    # ---------------------------------------------------------------------
    # Serialization helpers
    # ---------------------------------------------------------------------

    @staticmethod
    def _jsonable(obj: object) -> object:
        if is_dataclass(obj) and not isinstance(obj, type):
            return asdict(obj)
        if hasattr(obj, "to_dict") and callable(getattr(obj, "to_dict")):
            return obj.to_dict()  # type: ignore[no-any-return]
        if hasattr(obj, "__dict__"):
            return dict(obj.__dict__)
        return str(obj)

    @staticmethod
    def _serialize_workflow_spec(spec: WorkflowSpec) -> str:
        trigger = spec.trigger
        steps = [s.to_dict() for s in spec.steps]
        payload: Dict[str, Any] = {
            "workflow_id": spec.workflow_id,
            "name": spec.name,
            "source_plan_id": spec.source_plan_id,
            "version": spec.version,
            "trigger": {
                "type": trigger.type.value,
                "schedule": trigger.schedule,
                "timezone": trigger.timezone,
                "event_topic": trigger.event_topic,
                "enabled": trigger.enabled,
            },
            "steps": steps,
            "dependencies": spec.dependencies,
            "active": spec.active,
            "created_at": float(spec.created_at),
            "updated_at": float(spec.updated_at),
            "created_by": spec.created_by,
        }
        return json.dumps(payload, sort_keys=True, default=str)

    @staticmethod
    def _deserialize_workflow_spec(spec_json: str) -> WorkflowSpec:
        data = json.loads(spec_json)
        t = data["trigger"]
        trigger = TriggerSpec(
            type=TriggerType(SQLiteWorkflowAdapter._parse_enum_value(t["type"])),
            schedule=t.get("schedule"),
            timezone=t.get("timezone", "UTC"),
            event_topic=t.get("event_topic"),
            enabled=bool(t.get("enabled", True)),
        )
        steps = [PlanStep(**s) for s in data.get("steps", [])]
        return WorkflowSpec(
            workflow_id=data["workflow_id"],
            name=data["name"],
            source_plan_id=data["source_plan_id"],
            version=data["version"],
            trigger=trigger,
            steps=steps,
            dependencies=data.get("dependencies", {}),
            active=bool(data.get("active", True)),
            created_at=float(data.get("created_at", 0.0)),
            updated_at=float(data.get("updated_at", 0.0)),
            created_by=data.get("created_by", "system"),
        )
