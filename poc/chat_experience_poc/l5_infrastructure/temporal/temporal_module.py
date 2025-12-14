"""
Temporal Module - Time-based scheduling and trigger execution

Purpose:
- Background scheduler evaluates triggers every 60 seconds
- Fires triggers when fire_time <= now()
- Sends SSE events to ProactiveAgent
- Reschedules recurring triggers automatically

Architecture:
- Singleton pattern for global scheduler
- SQLite storage for trigger persistence
- Async scheduler loop with asyncio
- SSE connection to Mock K0 SSE Server

Performance:
- Scheduler query: <10ms P95
- Trigger fire: <50ms P95
- Scheduler tick: 60s interval (±5s accuracy)

Usage:
    module = get_temporal_module()
    await module.start_scheduler()

    # Scheduler automatically fires triggers and sends SSE events
    # Connects to Mock K0 SSE Server on port 8002
"""

import asyncio
import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class TriggerType(Enum):
    """Trigger type categories"""

    TIME_BASED = "time_based"  # Fire at specific time
    RECURRING = "recurring"  # Fire on schedule
    PATTERN = "pattern"  # Fire based on detected patterns
    ANOMALY = "anomaly"  # Fire on unusual activity


@dataclass
class Trigger:
    """
    Trigger data model

    Fields:
        trigger_id: Unique identifier (UUID)
        trigger_type: Type of trigger (TimeBasedTrigger, RecurringTrigger, etc.)
        fire_time: When to fire trigger (ISO 8601 datetime)
        recurrence: Recurrence pattern ("4h", "daily", "weekly", None)
        message: Notification text for user
        action: What to do when fired (JSON string)
        metadata: Additional context (JSON string)
        user_id: User this trigger belongs to
        session_id: Optional session context
        active: Whether trigger is active (True) or soft deleted (False)
        fire_count: How many times this trigger has fired
        last_fired: Last time trigger fired (ISO 8601 datetime)
        created_at: When trigger was created
        updated_at: When trigger was last updated
    """

    trigger_id: str
    trigger_type: TriggerType
    fire_time: datetime
    message: str
    action: str
    user_id: str
    recurrence: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None
    active: bool = True
    fire_count: int = 0
    last_fired: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "trigger_id": self.trigger_id,
            "trigger_type": self.trigger_type.value,
            "fire_time": self.fire_time.isoformat() + "Z",
            "recurrence": self.recurrence,
            "message": self.message,
            "action": self.action,
            "metadata": json.dumps(self.metadata) if self.metadata else None,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "active": 1 if self.active else 0,
            "fire_count": self.fire_count,
            "last_fired": self.last_fired.isoformat() + "Z" if self.last_fired else None,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
            "updated_at": self.updated_at.isoformat() + "Z" if self.updated_at else None,
        }

    @staticmethod
    def from_db_row(row: tuple) -> "Trigger":
        """Create Trigger from database row"""
        return Trigger(
            trigger_id=row[0],
            trigger_type=TriggerType(row[1]),
            fire_time=datetime.fromisoformat(row[2].replace("Z", "")),
            recurrence=row[3],
            message=row[4],
            action=row[5],
            metadata=json.loads(row[6]) if row[6] else None,
            user_id=row[7],
            session_id=row[8],
            active=bool(row[9]),
            fire_count=row[10],
            last_fired=datetime.fromisoformat(row[11].replace("Z", "")) if row[11] else None,
            created_at=datetime.fromisoformat(row[12].replace("Z", "")) if row[12] else None,
            updated_at=datetime.fromisoformat(row[13].replace("Z", "")) if row[13] else None,
        )


class TemporalModule:
    """
    Temporal Module - Background scheduler and trigger execution

    Responsibilities:
    - Run scheduler loop every 60 seconds
    - Query active triggers where fire_time <= now()
    - Fire triggers and send SSE events to Mock K0 SSE Server
    - Reschedule recurring triggers automatically
    - Log all trigger fires for audit trail

    Singleton pattern for global scheduler coordination.
    """

    _instance: Optional["TemporalModule"] = None

    def __init__(
        self,
        db_path: Optional[Path] = None,
        sse_url: Optional[str] = None,
        k0_backend_url: Optional[str] = None,
    ):
        """
        Initialize Temporal Module

        Args:
            db_path: Path to SQLite database (default: config/temporal_triggers.db)
            sse_url: URL of Mock K0 SSE Server (default: http://localhost:8002)
            k0_backend_url: URL of Mock K0 Backend for P05 queries (default: http://localhost:8001)
        """
        if TemporalModule._instance is not None:
            raise RuntimeError("TemporalModule is a singleton. Use get_temporal_module()")

        # Database path
        if db_path is None:
            config_dir = Path(__file__).parent.parent.parent / "config"
            config_dir.mkdir(exist_ok=True)
            db_path = config_dir / "temporal_triggers.db"

        self.db_path = Path(db_path)

        # SSE server URL
        self.sse_url = sse_url or "http://localhost:8002"

        # K0 Backend URL for P05 queries
        self.k0_backend_url = k0_backend_url or "http://localhost:8001"

        # Scheduler state
        self.scheduler_running = False
        self.scheduler_task: Optional[asyncio.Task] = None
        self.tick_interval = 60  # Check triggers every 60 seconds

        # HTTP client for SSE events and K0 queries
        self.http_client = httpx.AsyncClient(timeout=5.0)

        # Initialize database
        self._init_db()

        logger.info(
            f"[TemporalModule] Initialized: db_path={self.db_path}, "
            f"sse_url={self.sse_url}, k0_backend_url={self.k0_backend_url}, "
            f"tick_interval={self.tick_interval}"
        )

    def _init_db(self):
        """Initialize database schema"""
        schema_path = (
            Path(__file__).parent.parent.parent / "config" / "temporal_triggers_schema.sql"
        )

        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        conn = sqlite3.connect(str(self.db_path))
        with open(schema_path, "r") as f:
            schema_sql = f.read()
            conn.executescript(schema_sql)
        conn.commit()
        conn.close()

        logger.debug(f"[TemporalModule] Database initialized: db_path={self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection"""
        return sqlite3.connect(str(self.db_path))

    async def start_scheduler(self):
        """
        Start background scheduler loop

        Scheduler runs every 60 seconds:
        1. Query all active triggers where fire_time <= now()
        2. Fire each trigger (send SSE event)
        3. Reschedule recurring triggers
        4. Log trigger execution to history
        """
        if self.scheduler_running:
            logger.warning("[TemporalModule] Scheduler already running")
            return

        self.scheduler_running = True
        self.scheduler_task = asyncio.create_task(self._scheduler_loop())

        logger.info(f"[TemporalModule] Scheduler started: tick_interval={self.tick_interval}")

    async def stop_scheduler(self):
        """Stop background scheduler loop"""
        if not self.scheduler_running:
            logger.warning("[TemporalModule] Scheduler not running")
            return

        self.scheduler_running = False

        if self.scheduler_task:
            self.scheduler_task.cancel()
            try:
                await self.scheduler_task
            except asyncio.CancelledError:
                pass

        await self.http_client.aclose()

        logger.info("[TemporalModule] Scheduler stopped")

    async def _scheduler_loop(self):
        """
        Main scheduler loop - UPDATED to include K0 P05 queries

        Runs every 60 seconds (tick_interval):
        - Query local due triggers
        - Query K0 P05 prospectives
        - Merge and deduplicate triggers
        - Fire all due triggers
        - Reschedule recurring triggers
        - Log execution
        """
        logger.info("[TemporalModule] Scheduler loop started")

        while self.scheduler_running:
            try:
                start_time = time.time()

                # Query local triggers (existing)
                local_triggers = self._get_due_triggers()

                # Query K0 P05 prospectives (NEW)
                k0_prospectives = await self._fetch_prospectives_from_k0()

                # Convert K0 prospectives to Trigger objects
                k0_triggers = self._prospectives_to_triggers(k0_prospectives)

                # Merge results (deduplicate)
                all_triggers = self._merge_triggers(local_triggers, k0_triggers)

                logger.debug(
                    f"[TemporalModule] Scheduler tick: local_triggers={len(local_triggers)}, "
                    f"k0_prospectives={len(k0_prospectives)}, total_due={len(all_triggers)}"
                )

                # Fire each trigger
                for trigger in all_triggers:
                    await self._fire_trigger(trigger)

                # Calculate next tick time (align to 60s intervals)
                elapsed = time.time() - start_time
                sleep_time = max(0, self.tick_interval - elapsed)

                logger.debug(
                    f"[TemporalModule] Scheduler tick complete: elapsed_ms={int(elapsed * 1000)}, "
                    f"sleep_time_s={int(sleep_time)}"
                )

                await asyncio.sleep(sleep_time)

            except asyncio.CancelledError:
                logger.info("[TemporalModule] Scheduler loop cancelled")
                break
            except Exception as e:
                logger.error(f"[TemporalModule] Scheduler loop error: {str(e)}", exc_info=True)
                # Sleep briefly before retrying
                await asyncio.sleep(10)

    def _get_due_triggers(self) -> List[Trigger]:
        """
        Query all active triggers where fire_time <= now()

        Returns:
            List of due triggers
        """
        now = datetime.utcnow().isoformat() + "Z"

        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT trigger_id, trigger_type, fire_time, recurrence, message, action, metadata,
                   user_id, session_id, active, fire_count, last_fired, created_at, updated_at
            FROM temporal_triggers
            WHERE active = 1 AND fire_time <= ?
            ORDER BY fire_time ASC
        """,
            (now,),
        )

        rows = cursor.fetchall()
        conn.close()

        return [Trigger.from_db_row(row) for row in rows]

    async def _fetch_prospectives_from_k0(self) -> List[Dict[str, Any]]:
        """
        Fetch active prospectives from Mock K0 P05 endpoint

        Calls: POST http://localhost:8001/k0/query
        Payload: {"query": "P05", "filters": {"active": true, "fire_time_lte": now}}

        Returns:
            List of prospective dicts with:
            - p05_id: str (unique identifier)
            - fire_time: str (ISO 8601)
            - message: str (user-facing text)
            - action: str (what to do)
            - user_id: str (owner)
            - confidence: float (0.0-1.0)
            - writer_id: str (which writer created)
            - metadata: dict (context)

        Performance:
            - Query time: <100ms P95
            - Network overhead: <50ms
            - Timeout: 5s (inherited from http_client)

        Error Handling:
            - Connection error → Log warning, return []
            - Timeout → Log warning, return []
            - Invalid response → Log error, return []
        """
        try:
            now = datetime.utcnow().isoformat() + "Z"
            lookback_days = 30
            lookback_start = (datetime.utcnow() - timedelta(days=lookback_days)).isoformat() + "Z"

            # Query Mock K0 P05 endpoint
            response = await self.http_client.post(
                f"{self.k0_backend_url}/k0/query",
                json={
                    "query": "P05",
                    "filters": {
                        "active": True,
                        "fire_time_lte": now,
                        "fire_time_gte": lookback_start,
                    },
                    "limit": 1000,
                },
                timeout=5.0,
            )

            response.raise_for_status()
            data = await response.json()

            # Extract P05 prospectives
            prospectives = data.get("prospectives", [])

            logger.debug(
                f"[TemporalModule] Fetched prospectives from K0: count={len(prospectives)}, "
                f"query_time_ms={data.get('query_time_ms', 0)}"
            )

            return prospectives

        except Exception as e:
            # DEBUG level since K0 P05 endpoint not yet implemented (Milestone 7)
            logger.debug(
                f"[TemporalModule] K0 prospectives unavailable (expected in PoC): error={str(e)}, "
                f"k0_url={self.k0_backend_url}"
            )
            return []

    def _prospectives_to_triggers(self, prospectives: List[Dict[str, Any]]) -> List[Trigger]:
        """
        Convert K0 P05 prospectives to Trigger objects

        Args:
            prospectives: List of P05 dicts from K0

        Returns:
            List of Trigger objects
        """
        triggers = []

        for p05 in prospectives:
            try:
                trigger = Trigger(
                    trigger_id=f"k0_p05_{p05['p05_id']}",  # Namespace to avoid conflicts
                    trigger_type=TriggerType.TIME_BASED,
                    fire_time=datetime.fromisoformat(p05["fire_time"].replace("Z", "")),
                    message=p05["message"],
                    action=p05["action"],
                    user_id=p05["user_id"],
                    metadata={
                        "source": "k0_p05",
                        "p05_id": p05["p05_id"],
                        "confidence": p05.get("confidence", 0.8),
                        "writer_id": p05.get("writer_id"),
                    },
                )
                triggers.append(trigger)
            except Exception as e:
                logger.warning(
                    f"[TemporalModule] Failed to convert P05 to trigger: p05_id={p05.get('p05_id')}, "
                    f"error={str(e)}"
                )

        return triggers

    def _merge_triggers(self, local: List[Trigger], k0: List[Trigger]) -> List[Trigger]:
        """
        Merge local triggers with K0 prospectives

        Deduplication:
        - If trigger_id matches exactly → Use local (it may have updates)
        - If p05_id exists → Skip duplicate K0 prospective
        - Otherwise → Add K0 prospective

        Args:
            local: Local triggers from SQLite
            k0: K0 prospective triggers

        Returns:
            Merged and deduplicated list of triggers
        """
        # Index local triggers by ID
        local_by_id = {t.trigger_id: t for t in local}

        # Start with all local triggers
        merged = list(local_by_id.values())

        # Add K0 prospectives not already present
        for k0_trigger in k0:
            if k0_trigger.trigger_id not in local_by_id:
                merged.append(k0_trigger)

        return merged

    async def _fire_trigger(self, trigger: Trigger):
        """
        Fire trigger and send SSE event

        Steps:
        1. Send SSE event to Mock K0 SSE Server
        2. Reschedule recurring triggers
        3. Increment fire_count
        4. Log to trigger_history

        Args:
            trigger: Trigger to fire
        """
        start_time = time.time()

        try:
            # Send SSE event
            event_type = self._get_event_type(trigger.trigger_type)
            event_data = {
                "trigger_id": trigger.trigger_id,
                "time": datetime.utcnow().isoformat() + "Z",
                "message": trigger.message,
                "action": trigger.action,
                "user_id": trigger.user_id,
                "session_id": trigger.session_id,
                "metadata": trigger.metadata,
            }

            await self._send_sse_event(event_type, event_data)

            # Update trigger
            fire_time = datetime.utcnow()
            next_fire_time = self._calculate_next_fire_time(trigger)

            conn = self._get_connection()

            if next_fire_time:
                # Reschedule recurring trigger
                conn.execute(
                    """
                    UPDATE temporal_triggers
                    SET fire_count = fire_count + 1,
                        last_fired = ?,
                        fire_time = ?,
                        updated_at = datetime('now')
                    WHERE trigger_id = ?
                """,
                    (
                        fire_time.isoformat() + "Z",
                        next_fire_time.isoformat() + "Z",
                        trigger.trigger_id,
                    ),
                )
            else:
                # Deactivate one-time trigger
                conn.execute(
                    """
                    UPDATE temporal_triggers
                    SET fire_count = fire_count + 1,
                        last_fired = ?,
                        active = 0,
                        updated_at = datetime('now')
                    WHERE trigger_id = ?
                """,
                    (fire_time.isoformat() + "Z", trigger.trigger_id),
                )

            # Log to history
            execution_time_ms = (time.time() - start_time) * 1000
            conn.execute(
                """
                INSERT INTO trigger_history (trigger_id, fire_time, status, execution_time_ms)
                VALUES (?, ?, 'success', ?)
            """,
                (trigger.trigger_id, fire_time.isoformat() + "Z", execution_time_ms),
            )

            conn.commit()
            conn.close()

            next_fire_str = next_fire_time.isoformat() + "Z" if next_fire_time else "None"
            logger.info(
                f"[TemporalModule] Trigger fired: trigger_id={trigger.trigger_id}, "
                f"trigger_type={trigger.trigger_type.value}, message={trigger.message}, "
                f"execution_time_ms={int(execution_time_ms)}, next_fire_time={next_fire_str}"
            )

        except Exception as e:
            # Log error to history
            execution_time_ms = (time.time() - start_time) * 1000

            conn = self._get_connection()
            conn.execute(
                """
                INSERT INTO trigger_history (trigger_id, fire_time, status, error_message, execution_time_ms)
                VALUES (?, ?, 'error', ?, ?)
            """,
                (
                    trigger.trigger_id,
                    datetime.utcnow().isoformat() + "Z",
                    str(e),
                    execution_time_ms,
                ),
            )
            conn.commit()
            conn.close()

            logger.error(
                f"[TemporalModule] Trigger fire error: trigger_id={trigger.trigger_id}, "
                f"error={str(e)}, execution_time_ms={int(execution_time_ms)}",
                exc_info=True,
            )

    def _get_event_type(self, trigger_type: TriggerType) -> str:
        """
        Map trigger type to SSE event type

        Args:
            trigger_type: Trigger type

        Returns:
            SSE event type string
        """
        mapping = {
            TriggerType.TIME_BASED: "prospective.trigger.fired",
            TriggerType.RECURRING: "prospective.trigger.fired",
            TriggerType.PATTERN: "prospective.pattern.detected",
            TriggerType.ANOMALY: "prospective.anomaly.alert",
        }
        return mapping.get(trigger_type, "prospective.trigger.fired")

    async def _send_sse_event(self, event_type: str, event_data: Dict[str, Any]):
        """
        Send SSE event to Mock K0 SSE Server with retry logic

        Retry Strategy:
        - Max 3 retries on failure
        - Backoff: 100ms, 200ms, 400ms
        - Timeout: 5s per attempt
        - Non-blocking: If all retries fail, log error but don't crash scheduler

        Args:
            event_type: Event type (e.g., "prospective.trigger.fired")
            event_data: Event payload (JSON serializable)

        Returns:
            True if sent successfully, False if all retries exhausted
        """
        max_retries = 3
        base_delay_ms = 100
        timeout_s = 5.0

        for attempt in range(max_retries):
            try:
                response = await self.http_client.post(
                    f"{self.sse_url}/fire",
                    json={"event_type": event_type, "data": event_data},
                    timeout=timeout_s,
                )
                response.raise_for_status()

                logger.info(
                    f"[TemporalModule] SSE event sent successfully: event_type={event_type}, "
                    f"trigger_id={event_data.get('trigger_id')}, attempt={attempt + 1}"
                )
                return True

            except httpx.TimeoutException:
                logger.warning(
                    f"[TemporalModule] SSE event send timeout: event_type={event_type}, "
                    f"trigger_id={event_data.get('trigger_id')}, attempt={attempt + 1}/{max_retries}"
                )
                if attempt < max_retries - 1:
                    delay_ms = base_delay_ms * (2**attempt)
                    await asyncio.sleep(delay_ms / 1000.0)

            except httpx.ConnectError:
                logger.warning(
                    f"[TemporalModule] SSE server connection error: event_type={event_type}, "
                    f"trigger_id={event_data.get('trigger_id')}, attempt={attempt + 1}/{max_retries}, "
                    f"sse_url={self.sse_url}"
                )
                if attempt < max_retries - 1:
                    delay_ms = base_delay_ms * (2**attempt)
                    await asyncio.sleep(delay_ms / 1000.0)

            except Exception as e:
                logger.warning(
                    f"[TemporalModule] SSE event send error: event_type={event_type}, "
                    f"trigger_id={event_data.get('trigger_id')}, error={str(e)}, "
                    f"attempt={attempt + 1}/{max_retries}"
                )
                if attempt < max_retries - 1:
                    delay_ms = base_delay_ms * (2**attempt)
                    await asyncio.sleep(delay_ms / 1000.0)

        # All retries exhausted - log error but don't crash scheduler
        logger.error(
            f"[TemporalModule] SSE event send FAILED after all retries: event_type={event_type}, "
            f"trigger_id={event_data.get('trigger_id')}, max_retries={max_retries}, sse_url={self.sse_url}"
        )
        return False

    def _calculate_next_fire_time(self, trigger: Trigger) -> Optional[datetime]:
        """
        Calculate next fire time for recurring triggers

        Args:
            trigger: Trigger to reschedule

        Returns:
            Next fire time, or None if not recurring
        """
        if not trigger.recurrence:
            return None

        recurrence = trigger.recurrence.lower()
        current_fire_time = trigger.fire_time

        try:
            if recurrence.endswith("h"):
                # Hourly recurrence (e.g., "4h")
                hours = int(recurrence[:-1])
                return current_fire_time + timedelta(hours=hours)

            elif recurrence.endswith("m"):
                # Minute recurrence (e.g., "30m")
                minutes = int(recurrence[:-1])
                return current_fire_time + timedelta(minutes=minutes)

            elif recurrence.endswith("d"):
                # Daily recurrence (e.g., "2d")
                days = int(recurrence[:-1])
                return current_fire_time + timedelta(days=days)

            elif recurrence == "daily":
                # Daily at same time
                return current_fire_time + timedelta(days=1)

            elif recurrence == "weekly":
                # Weekly on same day
                return current_fire_time + timedelta(weeks=1)

            elif recurrence == "monthly":
                # Monthly on same date (approximate - 30 days)
                return current_fire_time + timedelta(days=30)

            else:
                logger.warning(
                    f"[TemporalModule] Unknown recurrence format: recurrence={recurrence}, "
                    f"trigger_id={trigger.trigger_id}"
                )
                return None

        except ValueError as e:
            logger.error(
                f"[TemporalModule] Invalid recurrence format: recurrence={recurrence}, "
                f"trigger_id={trigger.trigger_id}, error={str(e)}"
            )
            return None

    def get_stats(self) -> Dict[str, Any]:
        """
        Get temporal module statistics

        Returns:
            Statistics dictionary with counts and status
        """
        conn = self._get_connection()

        # Active triggers count
        cursor = conn.execute("SELECT COUNT(*) FROM temporal_triggers WHERE active = 1")
        active_count = cursor.fetchone()[0]

        # Total triggers count
        cursor = conn.execute("SELECT COUNT(*) FROM temporal_triggers")
        total_count = cursor.fetchone()[0]

        # Due triggers count
        now = datetime.utcnow().isoformat() + "Z"
        cursor = conn.execute(
            "SELECT COUNT(*) FROM temporal_triggers WHERE active = 1 AND fire_time <= ?", (now,)
        )
        due_count = cursor.fetchone()[0]

        # Trigger history count
        cursor = conn.execute("SELECT COUNT(*) FROM trigger_history")
        history_count = cursor.fetchone()[0]

        # Recent fires (last 24 hours)
        yesterday = (datetime.utcnow() - timedelta(days=1)).isoformat() + "Z"
        cursor = conn.execute(
            "SELECT COUNT(*) FROM trigger_history WHERE fire_time >= ?", (yesterday,)
        )
        recent_fires = cursor.fetchone()[0]

        conn.close()

        return {
            "active_triggers": active_count,
            "total_triggers": total_count,
            "due_triggers": due_count,
            "history_count": history_count,
            "recent_fires_24h": recent_fires,
            "scheduler_running": self.scheduler_running,
            "tick_interval": self.tick_interval,
            "db_path": str(self.db_path),
            "sse_url": self.sse_url,
        }


# Singleton factory
def get_temporal_module(
    db_path: Optional[Path] = None,
    sse_url: Optional[str] = None,
    k0_backend_url: Optional[str] = None,
) -> TemporalModule:
    """
    Get or create TemporalModule singleton instance

    Args:
        db_path: Path to SQLite database (only used on first call)
        sse_url: URL of Mock K0 SSE Server (only used on first call)
        k0_backend_url: URL of Mock K0 Backend for P05 queries (only used on first call)

    Returns:
        TemporalModule singleton instance
    """
    if TemporalModule._instance is None:
        TemporalModule._instance = TemporalModule(
            db_path=db_path, sse_url=sse_url, k0_backend_url=k0_backend_url
        )
    return TemporalModule._instance
