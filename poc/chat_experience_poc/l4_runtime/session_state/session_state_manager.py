"""
SessionStateManager - Manager for SessionState instances with DeltaBus integration

Manages creation, updates, and lifecycle of SessionState instances.
Publishes delta events to DeltaBus on every update.

References:
- docs/plans/chat_experience_poc_plan.md - Issue 2.2.2
- ADR-0017 - SessionState 6-Section Design
"""

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import structlog

from ..deltabus.deltabus import DeltaBus, DeltaBusEvent, EventType
from .session_state import SessionState

logger = structlog.get_logger(__name__)


class SessionStateManager:
    """
    SessionStateManager - Manage SessionState lifecycle with DeltaBus integration

    Responsibilities:
    - Create/retrieve SessionState instances
    - Update sections and compute deltas
    - Publish delta events to DeltaBus
    - Track session timeouts (600s idle)
    - Observability: log updates, count events

    Fields:
        deltabus: DeltaBus instance for event publishing
        sessions: In-memory session storage
        session_timeout_seconds: Idle timeout before archive (default: 600s)
    """

    def __init__(self, deltabus: DeltaBus, session_timeout_seconds: int = 600):
        """
        Initialize SessionStateManager

        Args:
            deltabus: DeltaBus instance for event publishing
            session_timeout_seconds: Idle timeout (default: 600s = 10 min)
        """
        self.deltabus = deltabus
        self.sessions: Dict[str, SessionState] = {}
        self.session_timeout_seconds = session_timeout_seconds

        # Metrics
        self._updates_per_section: Dict[str, int] = {
            "beliefs": 0,
            "scoreboard": 0,
            "control": 0,
            "persona": 0,
            "multimodal": 0,
            "meta": 0,
        }
        self._delta_events_published = 0
        self._sessions_created = 0
        self._sessions_archived = 0

        # Register with ComponentRegistry
        try:
            from monitoring.component_registry import ComponentRegistry

            reg = ComponentRegistry.inst()
            reg.register("SessionState Manager")
            reg.set("SessionState Manager", "RUNNING")
        except Exception:
            pass  # Registry optional

        logger.info(
            "[SessionStateManager] Initialized",
            timeout_seconds=session_timeout_seconds,
        )

    def create_session(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        cognitive_trace_id: Optional[str] = None,
    ) -> SessionState:
        """
        Create new SessionState

        Args:
            user_id: User ID
            session_id: Optional session ID (auto-generated if None)
            cognitive_trace_id: Optional trace ID (auto-generated if None)

        Returns:
            Created SessionState

        Raises:
            ValueError: If session_id already exists
        """
        if session_id is None:
            session_id = f"session_{uuid.uuid4().hex[:12]}"

        if session_id in self.sessions:
            raise ValueError(f"Session {session_id} already exists")

        if cognitive_trace_id is None:
            cognitive_trace_id = f"trace_{uuid.uuid4().hex[:12]}"

        session = SessionState(
            session_id=session_id,
            user_id=user_id,
            cognitive_trace_id=cognitive_trace_id,
        )

        self.sessions[session_id] = session
        self._sessions_created += 1

        # Publish session.created event
        event = DeltaBusEvent(
            event_type=EventType.SESSION_CREATED.value,
            session_id=session_id,
            payload={
                "user_id": user_id,
                "cognitive_trace_id": cognitive_trace_id,
                "created_at": session.created_at.isoformat(),
            },
            trace_id=cognitive_trace_id,
        )
        self.deltabus.publish(event)  # Sync publish (fast <1ms)

        logger.debug(
            "[SessionStateManager] Session created",
            session_id=session_id,
            user_id=user_id,
            trace_id=cognitive_trace_id,
        )

        return session

    def get_session(self, session_id: str) -> Optional[SessionState]:
        """
        Retrieve SessionState by ID

        Args:
            session_id: Session ID

        Returns:
            SessionState or None if not found
        """
        return self.sessions.get(session_id)

    def get_section(self, session_id: str, section_name: str) -> Optional[Dict[str, Any]]:
        """
        Get section from SessionState

        Args:
            session_id: Session ID
            section_name: Section name

        Returns:
            Section dict or None if session not found
        """
        session = self.get_session(session_id)
        if session is None:
            return None
        return session.get_section(section_name)

    def update_section(
        self,
        session_id: str,
        section_name: str,
        updates: Dict[str, Any],
        origin: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update section and publish delta event

        Args:
            session_id: Session ID
            section_name: Section to update
            updates: Dict of updates to apply
            origin: Optional origin (e.g., "concierge_agent", "planner_agent")

        Returns:
            Dict of changes (old_value, new_value pairs)

        Raises:
            ValueError: If session not found or section invalid
        """
        session = self.get_session(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        # Compute deltas
        changes = session.update_section(section_name, updates)

        # Track metrics
        self._updates_per_section[section_name] += 1

        # Publish session.delta event if there are changes
        if changes:
            event = DeltaBusEvent(
                event_type=EventType.SESSION_DELTA.value,
                session_id=session_id,
                payload={
                    "section": section_name,
                    "deltas": changes,
                    "origin": origin,
                    "updated_at": session.last_updated.isoformat(),
                },
                trace_id=session.cognitive_trace_id,
            )
            self.deltabus.publish(event)  # Sync publish (fast <1ms)
            self._delta_events_published += 1

            logger.debug(
                "[SessionStateManager] Section updated",
                session_id=session_id,
                section=section_name,
                changes_count=len(changes),
                origin=origin,
                trace_id=session.cognitive_trace_id,
            )

        return changes

    def archive_session(self, session_id: str, reason: str = "timeout") -> bool:
        """
        Archive session (remove from memory)

        Args:
            session_id: Session ID
            reason: Archive reason (default: "timeout")

        Returns:
            True if archived, False if not found
        """
        session = self.sessions.pop(session_id, None)
        if session is None:
            return False

        self._sessions_archived += 1

        # Publish session.archived event
        event = DeltaBusEvent(
            event_type=EventType.SESSION_ARCHIVED.value,
            session_id=session_id,
            payload={
                "reason": reason,
                "archived_at": datetime.utcnow().isoformat(),
                "user_id": session.user_id,
            },
            trace_id=session.cognitive_trace_id,
        )
        self.deltabus.publish(event)  # Sync publish (fast <1ms)

        logger.info(
            "[SessionStateManager] Session archived",
            session_id=session_id,
            reason=reason,
            trace_id=session.cognitive_trace_id,
        )

        return True

    def check_session_timeouts(self) -> int:
        """
        Check all sessions for timeout and archive expired ones

        Returns:
            Number of sessions archived
        """
        now = datetime.utcnow()
        timeout_delta = timedelta(seconds=self.session_timeout_seconds)
        archived_count = 0

        session_ids = list(self.sessions.keys())
        for session_id in session_ids:
            session = self.sessions[session_id]
            if now - session.last_updated > timeout_delta:
                self.archive_session(session_id, reason="timeout")
                archived_count += 1

        if archived_count > 0:
            logger.info(
                "[SessionStateManager] Session timeout check",
                archived_count=archived_count,
            )

        return archived_count

    def get_stats(self) -> Dict[str, Any]:
        """
        Get SessionStateManager statistics

        Returns:
            Dict with metrics
        """
        return {
            "active_sessions": len(self.sessions),
            "sessions_created": self._sessions_created,
            "sessions_archived": self._sessions_archived,
            "delta_events_published": self._delta_events_published,
            "updates_per_section": self._updates_per_section.copy(),
            "session_timeout_seconds": self.session_timeout_seconds,
        }
