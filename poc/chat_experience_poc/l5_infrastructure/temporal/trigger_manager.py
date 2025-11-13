"""
Trigger Manager - CRUD operations for temporal triggers

Purpose:
- Create, read, update, delete triggers
- Validate trigger data before persistence
- Provide high-level API for agents
- Thread-safe for concurrent access

Architecture:
- Wraps TemporalModule database operations
- Validates recurrence patterns
- Ensures fire_time is in the future
- Handles trigger rescheduling

Performance:
- Create trigger: <10ms P95
- Query trigger: <5ms P95
- List triggers: <15ms P95
- Update/delete: <10ms P95

Usage:
    manager = TriggerManager()

    # Create trigger
    trigger_id = manager.create_trigger({
        "trigger_type": "time_based",
        "fire_time": "2025-11-06T08:00:00Z",
        "message": "Take medication",
        "action": {"type": "notification", "target": "user"},
        "user_id": "user_123"
    })

    # List triggers
    triggers = manager.list_triggers("user_123", active_only=True)

    # Update trigger
    manager.update_trigger(trigger_id, {"message": "Take medication (updated)"})

    # Delete trigger
    manager.delete_trigger(trigger_id)
"""

import logging
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from l5_infrastructure.temporal.temporal_module import Trigger, TriggerType, get_temporal_module

logger = logging.getLogger(__name__)


class TriggerManager:
    """
    Trigger Manager - CRUD operations for temporal triggers

    Responsibilities:
    - Create new triggers with validation
    - Fetch triggers by ID or user_id
    - Update trigger fields
    - Delete triggers (soft delete)
    - Manual trigger firing for testing
    - Recurrence rescheduling calculations

    Thread-safe for concurrent agent access.
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize Trigger Manager

        Args:
            db_path: Path to SQLite database (default: config/temporal_triggers.db)
        """
        # Get temporal module instance
        self.temporal_module = get_temporal_module(db_path=db_path)
        self.db_path = self.temporal_module.db_path

        # Thread safety
        self._lock = threading.RLock()

        logger.info(f"[TriggerManager] Initialized with db_path={self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection"""
        return sqlite3.connect(str(self.db_path))

    def create_trigger(self, trigger_data: Dict[str, Any]) -> str:
        """
        Create new trigger

        Args:
            trigger_data: Trigger data dictionary with fields:
                - trigger_type: str ("time_based", "recurring", "pattern", "anomaly")
                - fire_time: str (ISO 8601 datetime)
                - message: str (notification text)
                - action: str or dict (what to do when fired)
                - user_id: str (user this trigger belongs to)
                - recurrence: str (optional - "4h", "daily", "weekly")
                - metadata: dict (optional - additional context)
                - session_id: str (optional - session context)

        Returns:
            trigger_id: Unique trigger identifier (UUID)

        Raises:
            ValueError: If validation fails
        """
        with self._lock:
            # Validate required fields
            required_fields = ["trigger_type", "fire_time", "message", "action", "user_id"]
            for field in required_fields:
                if field not in trigger_data:
                    raise ValueError(f"Missing required field: {field}")

            # Validate trigger_type
            try:
                trigger_type = TriggerType(trigger_data["trigger_type"])
            except ValueError:
                raise ValueError(f"Invalid trigger_type: {trigger_data['trigger_type']}")

            # Validate fire_time
            try:
                fire_time = datetime.fromisoformat(trigger_data["fire_time"].replace("Z", ""))
            except ValueError:
                raise ValueError(f"Invalid fire_time format: {trigger_data['fire_time']}")

            # Check fire_time is in the future
            if fire_time <= datetime.utcnow():
                raise ValueError("fire_time must be in the future")

            # Validate recurrence pattern
            recurrence = trigger_data.get("recurrence")
            if recurrence:
                self._validate_recurrence(recurrence)

            # Validate message and action
            if not trigger_data["message"]:
                raise ValueError("message cannot be empty")
            if not trigger_data["action"]:
                raise ValueError("action cannot be empty")

            # Generate trigger_id
            trigger_id = f"trigger_{uuid.uuid4().hex[:16]}"

            # Prepare action (convert dict to JSON string if needed)
            action = trigger_data["action"]
            if isinstance(action, dict):
                import json

                action = json.dumps(action)

            # Prepare metadata (convert dict to JSON string if needed)
            metadata = trigger_data.get("metadata")
            if metadata and isinstance(metadata, dict):
                import json

                metadata = json.dumps(metadata)

            # Insert into database
            conn = self._get_connection()
            conn.execute(
                """
                INSERT INTO temporal_triggers (
                    trigger_id, trigger_type, fire_time, recurrence, message, action,
                    metadata, user_id, session_id, active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
                (
                    trigger_id,
                    trigger_type.value,
                    fire_time.isoformat() + "Z",
                    recurrence,
                    trigger_data["message"],
                    action,
                    metadata,
                    trigger_data["user_id"],
                    trigger_data.get("session_id"),
                ),
            )
            conn.commit()
            conn.close()

            logger.info(
                f"[TriggerManager] Trigger created: {trigger_id}",
                extra={
                    "trigger_id": trigger_id,
                    "trigger_type": trigger_type.value,
                    "fire_time": fire_time.isoformat() + "Z",
                    "user_id": trigger_data["user_id"],
                },
            )

            return trigger_id

    def _validate_recurrence(self, recurrence: str):
        """
        Validate recurrence pattern format

        Valid patterns:
        - "4h" = every 4 hours
        - "30m" = every 30 minutes
        - "2d" = every 2 days
        - "daily" = every day at same time
        - "weekly" = every week on same day
        - "monthly" = every month on same date

        Args:
            recurrence: Recurrence pattern string

        Raises:
            ValueError: If recurrence pattern is invalid
        """
        recurrence = recurrence.lower()

        if recurrence in ["daily", "weekly", "monthly"]:
            return  # Valid

        if recurrence.endswith("h"):
            hours = int(recurrence[:-1])
            if hours <= 0 or hours > 8760:  # Max 1 year in hours
                raise ValueError(f"Invalid hour recurrence: {recurrence}")
            return

        if recurrence.endswith("m"):
            minutes = int(recurrence[:-1])
            if minutes <= 0 or minutes > 525600:  # Max 1 year in minutes
                raise ValueError(f"Invalid minute recurrence: {recurrence}")
            return

        if recurrence.endswith("d"):
            days = int(recurrence[:-1])
            if days <= 0 or days > 365:
                raise ValueError(f"Invalid day recurrence: {recurrence}")
            return

        raise ValueError(f"Invalid recurrence format: {recurrence}")

    def get_trigger(self, trigger_id: str) -> Optional[Trigger]:
        """
        Fetch trigger by ID

        Args:
            trigger_id: Trigger identifier

        Returns:
            Trigger object, or None if not found
        """
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT trigger_id, trigger_type, fire_time, recurrence, message, action, metadata,
                   user_id, session_id, active, fire_count, last_fired, created_at, updated_at
            FROM temporal_triggers
            WHERE trigger_id = ?
        """,
            (trigger_id,),
        )

        row = cursor.fetchone()
        conn.close()

        if row is None:
            return None

        return Trigger.from_db_row(row)

    def list_triggers(self, user_id: str, active_only: bool = True) -> List[Trigger]:
        """
        List triggers for a user

        Args:
            user_id: User identifier
            active_only: If True, only return active triggers

        Returns:
            List of Trigger objects
        """
        conn = self._get_connection()

        if active_only:
            cursor = conn.execute(
                """
                SELECT trigger_id, trigger_type, fire_time, recurrence, message, action, metadata,
                       user_id, session_id, active, fire_count, last_fired, created_at, updated_at
                FROM temporal_triggers
                WHERE user_id = ? AND active = 1
                ORDER BY fire_time ASC
            """,
                (user_id,),
            )
        else:
            cursor = conn.execute(
                """
                SELECT trigger_id, trigger_type, fire_time, recurrence, message, action, metadata,
                       user_id, session_id, active, fire_count, last_fired, created_at, updated_at
                FROM temporal_triggers
                WHERE user_id = ?
                ORDER BY fire_time ASC
            """,
                (user_id,),
            )

        rows = cursor.fetchall()
        conn.close()

        return [Trigger.from_db_row(row) for row in rows]

    def update_trigger(self, trigger_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update trigger fields

        Args:
            trigger_id: Trigger identifier
            updates: Dictionary of fields to update (supports: fire_time, message, action, metadata, recurrence)

        Returns:
            True if trigger was updated, False if not found

        Raises:
            ValueError: If validation fails
        """
        with self._lock:
            # Check trigger exists
            trigger = self.get_trigger(trigger_id)
            if trigger is None:
                return False

            # Build UPDATE query dynamically
            update_fields = []
            update_values = []

            if "fire_time" in updates:
                fire_time = datetime.fromisoformat(updates["fire_time"].replace("Z", ""))
                if fire_time <= datetime.utcnow():
                    raise ValueError("fire_time must be in the future")
                update_fields.append("fire_time = ?")
                update_values.append(fire_time.isoformat() + "Z")

            if "message" in updates:
                if not updates["message"]:
                    raise ValueError("message cannot be empty")
                update_fields.append("message = ?")
                update_values.append(updates["message"])

            if "action" in updates:
                action = updates["action"]
                if isinstance(action, dict):
                    import json

                    action = json.dumps(action)
                if not action:
                    raise ValueError("action cannot be empty")
                update_fields.append("action = ?")
                update_values.append(action)

            if "metadata" in updates:
                metadata = updates["metadata"]
                if metadata and isinstance(metadata, dict):
                    import json

                    metadata = json.dumps(metadata)
                update_fields.append("metadata = ?")
                update_values.append(metadata)

            if "recurrence" in updates:
                recurrence = updates["recurrence"]
                if recurrence:
                    self._validate_recurrence(recurrence)
                update_fields.append("recurrence = ?")
                update_values.append(recurrence)

            if not update_fields:
                # No valid fields to update
                return True

            # Add trigger_id to values
            update_values.append(trigger_id)

            # Execute UPDATE
            conn = self._get_connection()
            conn.execute(
                f"""
                UPDATE temporal_triggers
                SET {', '.join(update_fields)}, updated_at = datetime('now')
                WHERE trigger_id = ?
            """,
                update_values,
            )
            conn.commit()
            conn.close()

            logger.info(
                f"[TriggerManager] Trigger updated: {trigger_id}",
                extra={"trigger_id": trigger_id, "updates": list(updates.keys())},
            )

            return True

    def delete_trigger(self, trigger_id: str) -> bool:
        """
        Delete trigger (soft delete - sets active=False)

        Args:
            trigger_id: Trigger identifier

        Returns:
            True if trigger was deleted, False if not found
        """
        with self._lock:
            conn = self._get_connection()
            cursor = conn.execute(
                """
                UPDATE temporal_triggers
                SET active = 0, updated_at = datetime('now')
                WHERE trigger_id = ? AND active = 1
            """,
                (trigger_id,),
            )

            rows_affected = cursor.rowcount
            conn.commit()
            conn.close()

            if rows_affected > 0:
                logger.info(f"[TriggerManager] Trigger deleted: {trigger_id}")
                return True
            else:
                return False

    def fire_trigger(self, trigger_id: str) -> bool:
        """
        Manually fire a trigger (for testing)

        Args:
            trigger_id: Trigger identifier

        Returns:
            True if trigger was fired, False if not found
        """
        with self._lock:
            # Get trigger
            trigger = self.get_trigger(trigger_id)
            if trigger is None or not trigger.active:
                return False

            # Fire trigger using temporal module
            import asyncio

            loop = asyncio.get_event_loop()
            loop.run_until_complete(self.temporal_module._fire_trigger(trigger))

            logger.info(f"[TriggerManager] Trigger manually fired: {trigger_id}")

            return True

    def reschedule_recurring(self, trigger_id: str) -> Optional[datetime]:
        """
        Calculate next fire time for a recurring trigger

        Args:
            trigger_id: Trigger identifier

        Returns:
            Next fire time, or None if trigger is not recurring or not found
        """
        # Get trigger
        trigger = self.get_trigger(trigger_id)
        if trigger is None or not trigger.recurrence:
            return None

        # Calculate next fire time
        next_fire_time = self.temporal_module._calculate_next_fire_time(trigger)

        return next_fire_time

    def get_stats(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get trigger statistics

        Args:
            user_id: Optional user_id to filter stats

        Returns:
            Statistics dictionary
        """
        conn = self._get_connection()

        if user_id:
            # User-specific stats
            cursor = conn.execute(
                "SELECT COUNT(*) FROM temporal_triggers WHERE user_id = ? AND active = 1",
                (user_id,),
            )
            active_count = cursor.fetchone()[0]

            cursor = conn.execute(
                "SELECT COUNT(*) FROM temporal_triggers WHERE user_id = ?", (user_id,)
            )
            total_count = cursor.fetchone()[0]

            now = datetime.utcnow().isoformat() + "Z"
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM temporal_triggers
                WHERE user_id = ? AND active = 1 AND fire_time <= ?
            """,
                (user_id, now),
            )
            due_count = cursor.fetchone()[0]
        else:
            # Global stats
            cursor = conn.execute("SELECT COUNT(*) FROM temporal_triggers WHERE active = 1")
            active_count = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM temporal_triggers")
            total_count = cursor.fetchone()[0]

            now = datetime.utcnow().isoformat() + "Z"
            cursor = conn.execute(
                "SELECT COUNT(*) FROM temporal_triggers WHERE active = 1 AND fire_time <= ?", (now,)
            )
            due_count = cursor.fetchone()[0]

        conn.close()

        return {
            "active_triggers": active_count,
            "total_triggers": total_count,
            "due_triggers": due_count,
            "user_id": user_id,
        }
