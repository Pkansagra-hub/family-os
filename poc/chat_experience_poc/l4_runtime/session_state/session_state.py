"""
SessionState - Working memory for K1 Intelligence Module

6-section structured design for session-scoped working memory.
Ephemeral state (lost on K1 crash, rebuilt from K0 WAL).

Sections:
1. beliefs - User facts, preferences, context (10-20KB)
2. scoreboard - Common ground, referents, QUD (4-8KB)
3. control - Active leases, flow state, agents (8-12KB)
4. persona - Personality model, tone, style (2-4KB)
5. multimodal - Audio/vision state, streaming (4-8KB)
6. meta - Metadata, telemetry, timestamps (2-4KB)

Total: 30-56KB typical, 64KB soft limit

References:
- docs/plans/chat_experience_poc_plan.md - Issue 2.1.3
- ADR-0017 - SessionState 6-Section Design
- ADR-0019a - SessionState FlatBuffers Schema Definition
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict


class AgentState(Enum):
    """Agent lifecycle state machine"""

    WARMING = "warming"  # Just spawned, initializing
    ACTIVE = "active"  # Currently executing task
    IDLE = "idle"  # Waiting for next task (reusable)
    DRAINING = "draining"  # Finishing up, no new tasks
    TERMINATED = "terminated"  # No longer available


@dataclass
class AgentRecord:
    """
    Tracks agent instance lifecycle.

    Attributes:
        agent_id: Unique agent instance ID
        agent_type: Type of agent (e.g., TicketBookingAgent)
        state: Current lifecycle state
        spawned_at_ms: When agent was spawned (epoch millis)
        last_active_ms: When agent last executed task (epoch millis)
        idle_timeout_ms: How long agent waits before expiry (default 5 min = 300000ms)
        assigned_tasks: Total tasks assigned to this agent
        completed_tasks: Total tasks completed successfully
        failed_tasks: Total tasks that failed
    """

    agent_id: str
    agent_type: str
    state: AgentState
    spawned_at_ms: int
    last_active_ms: int
    idle_timeout_ms: int = 300000  # 5 minutes default
    assigned_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0

    def is_reusable(self, current_time_ms: int) -> bool:
        """
        Check if agent is still reusable (not expired).

        Agent is reusable if:
        - State is IDLE
        - Time since last activity < idle_timeout_ms

        Args:
            current_time_ms: Current time in epoch millis

        Returns:
            True if agent can be reused, False if expired
        """
        return (
            self.state == AgentState.IDLE
            and (current_time_ms - self.last_active_ms) <= self.idle_timeout_ms
        )


@dataclass
class SessionState:
    """
    SessionState - 6-section working memory

    Sections (dict-based for PoC, will use FlatBuffers in production):
    - beliefs: User facts, preferences, retrieved context
    - scoreboard: Common ground, referents, agent scores
    - control: Agent leases, active agents, flow state
    - persona: Personality traits, tone, style preferences
    - multimodal: Audio/vision buffers, streaming state
    - meta: Trace IDs, timestamps, performance metrics

    Fields:
        session_id: Unique session identifier (UUID)
        user_id: User this session belongs to
        cognitive_trace_id: Current cognitive trace ID
        created_at: Session creation timestamp
        last_updated: Last update timestamp
        beliefs: Beliefs section (dict)
        scoreboard: Scoreboard section (dict)
        control: Control section (dict)
        persona: Persona section (dict)
        multimodal: Multimodal section (dict)
        meta: Meta section (dict)
    """

    session_id: str
    user_id: str
    cognitive_trace_id: str = field(default_factory=lambda: f"trace_{uuid.uuid4().hex[:12]}")
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_updated: datetime = field(default_factory=datetime.utcnow)

    # 6 sections (dict-based for PoC)
    beliefs: Dict[str, Any] = field(default_factory=dict)
    scoreboard: Dict[str, Any] = field(default_factory=dict)
    control: Dict[str, Any] = field(default_factory=dict)
    persona: Dict[str, Any] = field(default_factory=dict)
    multimodal: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)

    def get_section(self, section_name: str) -> Dict[str, Any]:
        """
        Get section by name

        Args:
            section_name: Section name (beliefs, scoreboard, control, persona, multimodal, meta)

        Returns:
            Section dict

        Raises:
            ValueError: If section_name invalid
        """
        if section_name == "beliefs":
            return self.beliefs
        elif section_name == "scoreboard":
            return self.scoreboard
        elif section_name == "control":
            return self.control
        elif section_name == "persona":
            return self.persona
        elif section_name == "multimodal":
            return self.multimodal
        elif section_name == "meta":
            return self.meta
        else:
            raise ValueError(f"Invalid section name: {section_name}")

    def update_section(self, section_name: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update section with new data

        Args:
            section_name: Section to update
            updates: Dict of updates to apply

        Returns:
            Dict of changes (old_value, new_value pairs)

        Raises:
            ValueError: If section_name invalid
        """
        section = self.get_section(section_name)
        changes = {}

        for key, new_value in updates.items():
            old_value = section.get(key)
            if old_value != new_value:
                changes[key] = {"old": old_value, "new": new_value}
                section[key] = new_value

        self.last_updated = datetime.utcnow()
        return changes

    def add_agent_to_roster(self, agent_record: AgentRecord) -> None:
        """
        Add agent to control.agent_roster.

        Args:
            agent_record: AgentRecord to add
        """
        if "agent_roster" not in self.control:
            self.control["agent_roster"] = {}

        # Serialize AgentRecord to dict for storage
        agent_data = {
            "agent_id": agent_record.agent_id,
            "agent_type": agent_record.agent_type,
            "state": agent_record.state.value,  # Store enum as string
            "spawned_at_ms": agent_record.spawned_at_ms,
            "last_active_ms": agent_record.last_active_ms,
            "idle_timeout_ms": agent_record.idle_timeout_ms,
            "assigned_tasks": agent_record.assigned_tasks,
            "completed_tasks": agent_record.completed_tasks,
            "failed_tasks": agent_record.failed_tasks,
        }
        self.control["agent_roster"][agent_record.agent_id] = agent_data
        self.last_updated = datetime.utcnow()

    def get_agent_from_roster(self, agent_id: str) -> AgentRecord | None:
        """
        Get agent from control.agent_roster.

        Args:
            agent_id: Agent ID to retrieve

        Returns:
            AgentRecord if found, None otherwise
        """
        if "agent_roster" not in self.control:
            return None

        agent_data = self.control["agent_roster"].get(agent_id)
        if not agent_data:
            return None

        # Deserialize from dict to AgentRecord
        return AgentRecord(
            agent_id=agent_data["agent_id"],
            agent_type=agent_data["agent_type"],
            state=AgentState(agent_data["state"]),
            spawned_at_ms=agent_data["spawned_at_ms"],
            last_active_ms=agent_data["last_active_ms"],
            idle_timeout_ms=agent_data.get("idle_timeout_ms", 300000),
            assigned_tasks=agent_data.get("assigned_tasks", 0),
            completed_tasks=agent_data.get("completed_tasks", 0),
            failed_tasks=agent_data.get("failed_tasks", 0),
        )

    def update_agent_state(
        self, agent_id: str, new_state: AgentState, current_time_ms: int | None = None
    ) -> bool:
        """
        Update agent state in roster.

        Args:
            agent_id: Agent ID to update
            new_state: New agent state
            current_time_ms: Current time in epoch millis (optional, defaults to now)

        Returns:
            True if updated, False if agent not found
        """
        agent = self.get_agent_from_roster(agent_id)
        if not agent:
            return False

        agent.state = new_state
        if current_time_ms is not None:
            agent.last_active_ms = current_time_ms

        self.add_agent_to_roster(agent)
        return True

    def cleanup_expired_agents(self, current_time_ms: int) -> list[str]:
        """
        Remove agents that have exceeded idle TTL.

        Workflow:
          1. Iterate agent roster
          2. Check if agent is reusable (not expired)
          3. Remove expired agents
          4. Return list of removed agent IDs

        Args:
            current_time_ms: Current time in epoch millis

        Returns:
            List of removed agent IDs
        """
        if "agent_roster" not in self.control:
            return []

        expired_agents = []
        for agent_id, agent_data in list(self.control["agent_roster"].items()):
            agent = self.get_agent_from_roster(agent_id)
            if agent and not agent.is_reusable(current_time_ms):
                if agent.state == AgentState.IDLE:
                    expired_agents.append(agent_id)
                    del self.control["agent_roster"][agent_id]

        if expired_agents:
            self.last_updated = datetime.utcnow()

        return expired_agents

    def get_size_estimate_kb(self) -> float:
        """
        Estimate SessionState size in KB (rough approximation)

        Returns:
            Estimated size in KB
        """
        import sys

        total_bytes = (
            sys.getsizeof(self.beliefs)
            + sys.getsizeof(self.scoreboard)
            + sys.getsizeof(self.control)
            + sys.getsizeof(self.persona)
            + sys.getsizeof(self.multimodal)
            + sys.getsizeof(self.meta)
        )
        return total_bytes / 1024

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert SessionState to dict (for serialization)

        Returns:
            Dict representation
        """
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "cognitive_trace_id": self.cognitive_trace_id,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
            "beliefs": self.beliefs,
            "scoreboard": self.scoreboard,
            "control": self.control,
            "persona": self.persona,
            "multimodal": self.multimodal,
            "meta": self.meta,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "SessionState":
        """
        Create SessionState from dict

        Args:
            data: Dict representation

        Returns:
            SessionState instance
        """
        return SessionState(
            session_id=data["session_id"],
            user_id=data["user_id"],
            cognitive_trace_id=data.get("cognitive_trace_id", f"trace_{uuid.uuid4().hex[:12]}"),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if isinstance(data.get("created_at"), str)
                else data.get("created_at", datetime.utcnow())
            ),
            last_updated=(
                datetime.fromisoformat(data["last_updated"])
                if isinstance(data.get("last_updated"), str)
                else data.get("last_updated", datetime.utcnow())
            ),
            beliefs=data.get("beliefs", {}),
            scoreboard=data.get("scoreboard", {}),
            control=data.get("control", {}),
            persona=data.get("persona", {}),
            multimodal=data.get("multimodal", {}),
            meta=data.get("meta", {}),
        )

    # ==================== TIME CONTEXT UTILITIES ====================
    # Agents need time awareness for intelligent decision-making

    def init_time_context(self, user_timezone: str = "UTC") -> None:
        """
        Initialize time context in meta section.

        Call this once when session is created to enable time-aware agent features.

        Args:
            user_timezone: User's timezone (e.g., "America/New_York", "UTC")

        Example:
            session.init_time_context(user_timezone="America/New_York")
            # Now agents can access session.get_time_context()
        """
        now = datetime.utcnow()
        self.meta["time_context"] = {
            "current_time_utc": now.isoformat(),
            "current_time_epoch_ms": int(now.timestamp() * 1000),
            "user_timezone": user_timezone,
            "session_start_epoch_ms": int(self.created_at.timestamp() * 1000),
        }

    def get_time_context(self) -> Dict[str, Any]:
        """
        Get current time context (updates on each call).

        Returns dict with:
        - current_time_utc: ISO format UTC timestamp
        - current_time_epoch_ms: Epoch milliseconds
        - current_time_epoch_s: Epoch seconds
        - user_timezone: User's timezone
        - day_of_week: Day name (Monday, Tuesday, etc.)
        - hour_of_day: 0-23 (UTC)
        - is_business_hours: True if 9am-5pm UTC (rough, doesn't account for timezone)
        - is_peak_hours: True if 2pm-4pm UTC
        - is_off_hours: True if before 9am or after 5pm UTC
        - session_duration_seconds: How long session has been active

        Example:
            time_context = session.get_time_context()
            print(f"Current time: {time_context['current_time_utc']}")
            print(f"Is business hours: {time_context['is_business_hours']}")
        """
        now = datetime.utcnow()
        hour = now.hour

        return {
            "current_time_utc": now.isoformat(),
            "current_time_epoch_ms": int(now.timestamp() * 1000),
            "current_time_epoch_s": int(now.timestamp()),
            "user_timezone": self.meta.get("time_context", {}).get("user_timezone", "UTC"),
            "day_of_week": now.strftime("%A"),
            "day_of_week_num": now.weekday(),  # 0=Monday, 6=Sunday
            "hour_of_day": hour,
            "is_business_hours": 9 <= hour < 17,  # 9am-5pm UTC
            "is_peak_hours": 14 <= hour < 16,  # 2pm-4pm UTC
            "is_off_hours": hour < 9 or hour >= 17,  # Before 9am or after 5pm
            "is_weekend": now.weekday() >= 5,  # Saturday or Sunday
            "session_duration_seconds": int((now - self.created_at).total_seconds()),
            "session_start_iso": self.created_at.isoformat(),
        }

    def get_session_age_ms(self) -> int:
        """Get how long session has been active in milliseconds"""
        elapsed = datetime.utcnow() - self.created_at
        return int(elapsed.total_seconds() * 1000)

    def add_belief_with_timestamp(
        self,
        belief_key: str,
        belief_value: Any,
        context: str = "system",
    ) -> None:
        """
        Add belief to beliefs section with automatic timestamp tracking.

        This allows agents to know how fresh a belief is (critical for time-sensitive decisions).

        Args:
            belief_key: Key in beliefs dict
            belief_value: Actual belief value
            context: Where belief came from (e.g., "user_input", "memory_writer", "healthcare_agent")

        Example:
            session.add_belief_with_timestamp(
                "recent_medications",
                ["aspirin", "vitamin_d"],
                context="healthcare_agent"
            )
            # Now belief has timestamp: when did we learn about medications?
        """
        now = datetime.utcnow()
        self.beliefs[belief_key] = {
            "value": belief_value,
            "added_at_utc": now.isoformat(),
            "added_at_epoch_ms": int(now.timestamp() * 1000),
            "context": context,
        }
        self.last_updated = now

    def get_belief_value(self, belief_key: str) -> Any:
        """
        Get belief value (unwraps timestamped wrapper if present)

        Args:
            belief_key: Belief key

        Returns:
            Belief value or None
        """
        belief = self.beliefs.get(belief_key)
        if belief is None:
            return None
        # Handle both timestamped and raw beliefs
        if isinstance(belief, dict) and "value" in belief:
            return belief["value"]
        return belief

    def get_belief_age_seconds(self, belief_key: str) -> int | None:
        """
        Get how old a belief is in seconds.

        Critical for time-sensitive decisions. Example: if user took medication
        3 hours ago, agent can say "you took your medication earlier today".

        Args:
            belief_key: Belief key

        Returns:
            Age in seconds, or None if belief doesn't exist or has no timestamp
        """
        belief = self.beliefs.get(belief_key)
        if belief is None:
            return None

        if isinstance(belief, dict) and "added_at_epoch_ms" in belief:
            epoch_ms = belief["added_at_epoch_ms"]
            now_ms = int(datetime.utcnow().timestamp() * 1000)
            return int((now_ms - epoch_ms) / 1000)

        return None

    def get_fresh_beliefs(self, max_age_seconds: int) -> Dict[str, Any]:
        """
        Get all beliefs newer than max_age_seconds.

        Useful for agents that need recent information. Example: HealthcareAgent
        wants only medications taken in last 24 hours.

        Args:
            max_age_seconds: Maximum age threshold

        Returns:
            Dict of {belief_key: belief_value} for fresh beliefs only
        """
        now_ms = int(datetime.utcnow().timestamp() * 1000)
        fresh = {}

        for key, belief in self.beliefs.items():
            if isinstance(belief, dict) and "added_at_epoch_ms" in belief:
                age_ms = now_ms - belief["added_at_epoch_ms"]
                if age_ms <= max_age_seconds * 1000:
                    fresh[key] = belief["value"]
            else:
                # For non-timestamped beliefs, include them (assume recent)
                fresh[key] = belief

        return fresh

    def format_time_for_agent(self, epoch_ms: int, relative: bool = True) -> str:
        """
        Format timestamp for agent display (human-readable or relative).

        Args:
            epoch_ms: Epoch milliseconds
            relative: If True, return relative format ("2 hours ago"), else absolute ("2024-11-05T14:30:00")

        Returns:
            Formatted time string

        Example:
            # Last medication at 1414965000000 epoch_ms
            time_str = session.format_time_for_agent(1414965000000, relative=True)
            # Returns: "2 hours ago" (if current time is 2 hours later)
        """
        timestamp = datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)
        now = datetime.now(tz=timezone.utc)

        if not relative:
            return timestamp.isoformat()

        delta = now - timestamp
        seconds = int(delta.total_seconds())

        if seconds < 60:
            return f"{seconds}s ago"
        elif seconds < 3600:
            return f"{seconds // 60}m ago"
        elif seconds < 86400:
            return f"{seconds // 3600}h ago"
        else:
            return f"{seconds // 86400}d ago"

    def time_since_epoch_s(self) -> int:
        """Get current time as epoch seconds (convenience method for agents)"""
        return int(datetime.utcnow().timestamp())
