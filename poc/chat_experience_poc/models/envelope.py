"""
Envelope Data Models - Message Envelope Structure for All Inter-Component Communication

Defines the complete envelope structure used for all messages passing through the K1 system:
- IntentRouter → Concierge
- Concierge → Orchestrator
- Orchestrator → Agents
- Agents ↔ K0 Bridge
- All DeltaBus events

Single unified envelope shape simplifies logging, replay, and adapters.

References:
- docs/plans/chat_experience_poc_plan.md - Issue 6.5.1.1 (Envelope Design)
- ADR-0017 - SessionState & envelope structure
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict
from uuid import uuid4

from pydantic import BaseModel, Field


class QoSBand(str, Enum):
    """Quality of Service bands for message prioritization."""

    INTERACTIVE = "INTERACTIVE"  # User-facing requests (priority 2)
    STANDARD = "STANDARD"  # Normal agent tasks (priority 1)
    BACKGROUND = "BACKGROUND"  # Background/async work (priority 0)


class EnvelopeHeader(BaseModel):
    """
    Envelope Header - Metadata for all messages

    Contains routing, tracing, and QoS information. Every message carries this header
    for complete request visibility and propagation of cognitive_trace_id.
    """

    envelope_id: str = Field(
        default_factory=lambda: f"env_{uuid4().hex[:12]}",
        description="Unique envelope ID for this message (UUID-based)",
    )
    trace_id: str = Field(
        description="Cognitive trace ID for end-to-end request tracing",
        min_length=1,
    )
    session_id: str = Field(
        description="Session ID this message belongs to",
        min_length=1,
    )
    user_id: str = Field(
        description="User ID for this request",
        min_length=1,
    )
    qos_band: QoSBand = Field(
        default=QoSBand.INTERACTIVE,
        description="Quality of Service band for prioritization",
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When this envelope was created",
    )
    actor: str = Field(
        description="Component that created this envelope (intent_router, concierge, etc.)",
        min_length=1,
    )

    class Config:
        """Pydantic config."""

        use_enum_values = False
        json_encoders = {datetime: lambda v: v.isoformat()}


class EnvelopePayload(BaseModel):
    """
    Envelope Payload - Message-specific content

    Flexible payload structure that can contain any message type:
    - user_input: Raw message from user
    - task_announcement: Orchestrator announcing task to agents
    - task_assignment: Selection of winner agent
    - task_result: Agent returning result
    - delta: SessionState delta from DeltaBus
    - etc.
    """

    message_type: str = Field(
        description="Type of message (user_input, task_announcement, delta, etc.)",
        min_length=1,
    )
    content: Dict[str, Any] = Field(
        default_factory=dict,
        description="Message-specific content (flexible structure)",
    )

    class Config:
        """Pydantic config."""

        arbitrary_types_allowed = True


class Envelope(BaseModel):
    """
    Complete Message Envelope

    Single unified message structure for all inter-component communication.
    Separates metadata (header) from content (payload) for clean separation of concerns.

    Example Usage:
        ```python
        envelope = Envelope(
            header=EnvelopeHeader(
                trace_id="trace_20251105_a1b2c3d4",
                session_id="session_xyz",
                user_id="user_123",
                actor="intent_router"
            ),
            payload=EnvelopePayload(
                message_type="user_input",
                content={"text": "Hello!", "timestamp": "2025-11-05T..."}
            )
        )
        ```

    Fields:
        header: EnvelopeHeader with routing/tracing metadata
        payload: EnvelopePayload with message content
    """

    header: EnvelopeHeader = Field(description="Message metadata and routing info")
    payload: EnvelopePayload = Field(description="Message-specific content")

    class Config:
        """Pydantic config."""

        json_encoders = {datetime: lambda v: v.isoformat()}

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert envelope to dictionary for serialization.

        Returns:
            Dictionary representation of envelope
        """
        return {
            "header": self.header.dict(),
            "payload": self.payload.dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Envelope":
        """
        Create envelope from dictionary (deserialization).

        Args:
            data: Dictionary with 'header' and 'payload' keys

        Returns:
            Envelope instance

        Raises:
            ValueError: If data structure invalid
        """
        try:
            header = EnvelopeHeader(**data.get("header", {}))
            payload = EnvelopePayload(**data.get("payload", {}))
            return cls(header=header, payload=payload)
        except Exception as e:
            raise ValueError(f"Invalid envelope data: {str(e)}")

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"Envelope(trace_id={self.header.trace_id}, "
            f"type={self.payload.message_type}, "
            f"session_id={self.header.session_id})"
        )


class AgentSpawnRequest(BaseModel):
    """
    Agent Spawn Request - Request to spawn a new specialist agent

    Sent from Orchestrator Phase 3 to Agent Factory when dynamic agent spawning
    is needed for a new agent type.

    Attributes:
        agent_id: Unique identifier for agent instance
        agent_type: Type of agent to spawn (e.g., "TicketBookingAgent")
        system_prompt: System prompt for the agent
        available_tools: List of tools available to agent (dict format)
        task_context: Task details for agent initialization
        session_id: Session this agent belongs to
        trace_id: Cognitive trace ID for observability
        timestamp_ms: When spawn request was created (epoch millis)
    """

    agent_id: str = Field(description="Unique agent instance ID")
    agent_type: str = Field(description="Type of agent (e.g., TicketBookingAgent)")
    system_prompt: str = Field(description="System prompt for agent initialization")
    available_tools: list[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of available tools in dict format",
    )
    task_context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Task context for agent",
    )
    session_id: str = Field(description="Session ID")
    trace_id: str = Field(description="Cognitive trace ID")
    timestamp_ms: int = Field(description="Spawn request timestamp (epoch millis)")
