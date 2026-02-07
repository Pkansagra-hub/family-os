"""
Base Sub-Agent Framework
========================

Provides the base class for all sub-agents with:
- READ-ONLY SessionState access (enforced)
- Separate LLM context from Concierge
- Standardized result message format
- Delta bus integration for reporting results

Reference: FULL_ARCHITECTURE_IMPLEMENTATION_PLAN.md - Milestone 8.1
"""

from __future__ import annotations

import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from poc.session_state_demo.anniversary_demo.bus.delta_bus import DeltaBus
    from poc.session_state_demo.bridge import SessionLLMBridge
    from poc.session_state_demo.llm_client import SimpleLLMClient

logger = logging.getLogger(__name__)


# =============================================================================
# AGENT RESULT MESSAGE FORMAT
# =============================================================================


class AgentStatus(Enum):
    """Status of agent task execution."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentResult:
    """
    Standardized result message from sub-agents.

    Published to Delta Bus for Concierge to consume.
    """

    # Identity
    agent_id: str
    agent_type: str  # "search", "booking", "monitor"
    task_id: str

    # Task info
    task_type: str  # "search_accommodations", "book_restaurant", etc.
    task_params: Dict[str, Any]

    # Result
    status: AgentStatus
    results: Any  # Task-specific results
    error: Optional[str] = None

    # Metadata
    timestamp: datetime = field(default_factory=datetime.now)
    duration_ms: int = 0
    tool_calls_made: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "task_id": self.task_id,
            "task_type": self.task_type,
            "task_params": self.task_params,
            "status": self.status.value,
            "results": self.results,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
            "tool_calls_made": self.tool_calls_made,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentResult":
        """Create from dictionary."""
        return cls(
            agent_id=data["agent_id"],
            agent_type=data["agent_type"],
            task_id=data["task_id"],
            task_type=data["task_type"],
            task_params=data["task_params"],
            status=AgentStatus(data["status"]),
            results=data["results"],
            error=data.get("error"),
            timestamp=(
                datetime.fromisoformat(data["timestamp"])
                if isinstance(data["timestamp"], str)
                else data["timestamp"]
            ),
            duration_ms=data.get("duration_ms", 0),
            tool_calls_made=data.get("tool_calls_made", 0),
        )


# =============================================================================
# READ-ONLY BRIDGE WRAPPER
# =============================================================================


class ReadOnlyBridge:
    """
    Wrapper that provides READ-ONLY access to SessionLLMBridge.

    Sub-agents receive this wrapper instead of the real bridge.
    Any write attempt raises PermissionError.
    """

    def __init__(self, bridge: "SessionLLMBridge"):
        """
        Initialize read-only wrapper.

        Args:
            bridge: The actual SessionLLMBridge to wrap
        """
        self._bridge = bridge
        self._blocked_writes = 0

    @property
    def session_id(self) -> str:
        """Get session ID (read-only)."""
        return self._bridge.session_id

    @property
    def blocked_writes(self) -> int:
        """Count of blocked write attempts."""
        return self._blocked_writes

    # =========================================================================
    # READ OPERATIONS (ALLOWED)
    # =========================================================================

    def get_section_data(self, section: str) -> Any:
        """Get data from a session section (READ)."""
        return self._bridge.get_section_data(section)

    def get_beliefs(self) -> Dict[str, Any]:
        """Get all beliefs from beliefs_active (READ)."""
        data = self._bridge.get_section_data("beliefs_active") or {}
        # Handle nested structure: {"beliefs": {...}}
        return data.get("beliefs", data) if isinstance(data, dict) else {}

    def get_persona(self) -> Dict[str, Any]:
        """Get user persona (READ)."""
        return self._bridge.get_section_data("persona") or {}

    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get conversation history (READ)."""
        history = self._bridge.get_section_data("history_active") or []
        return history[-limit:] if isinstance(history, list) else []

    def get_scoreboard(self) -> Dict[str, Any]:
        """Get current scoreboard (READ)."""
        return self._bridge.get_section_data("scoreboard") or {}

    def get_affective_state(self) -> Dict[str, Any]:
        """Get current emotional state (READ)."""
        return self._bridge.get_section_data("affective_now") or {}

    def build_context_for_agent(self) -> str:
        """Build context string for sub-agent LLM prompt (READ)."""
        context_parts = []

        # Known facts
        beliefs = self.get_beliefs()
        if beliefs:
            facts = []
            for subject, predicates in beliefs.items():
                if isinstance(predicates, dict):
                    for pred, obj in predicates.items():
                        facts.append(f"- {subject} {pred} {obj}")
            if facts:
                context_parts.append("KNOWN FACTS:\n" + "\n".join(facts[:15]))

        # User preferences
        persona = self.get_persona()
        if persona:
            prefs = []
            for key, val in persona.items():
                prefs.append(f"- {key}: {val}")
            if prefs:
                context_parts.append("USER PREFERENCES:\n" + "\n".join(prefs[:10]))

        # Current focus
        scoreboard = self.get_scoreboard()
        if scoreboard:
            if "topic" in scoreboard:
                context_parts.append(f"CURRENT TOPIC: {scoreboard['topic']}")
            if "qud" in scoreboard:
                context_parts.append(f"QUESTION UNDER DISCUSSION: {scoreboard['qud']}")

        return "\n\n".join(context_parts) if context_parts else "No context available."

    # =========================================================================
    # WRITE OPERATIONS (BLOCKED)
    # =========================================================================

    def execute_tool_calls(self, tool_calls: List[Dict]) -> List[Any]:
        """BLOCKED: Sub-agents cannot execute tool calls that write to state."""
        self._blocked_writes += 1
        raise PermissionError(
            "Sub-agents have READ-ONLY access to SessionState. "
            "Only the Concierge can write to SessionState."
        )

    def add_clarification_gap(self, *args, **kwargs) -> Any:
        """BLOCKED: Sub-agents cannot add clarification gaps."""
        self._blocked_writes += 1
        raise PermissionError("Sub-agents cannot modify clarifications section.")

    def resolve_clarification_gap(self, *args, **kwargs) -> Any:
        """BLOCKED: Sub-agents cannot resolve clarification gaps."""
        self._blocked_writes += 1
        raise PermissionError("Sub-agents cannot modify clarifications section.")

    def update_scoreboard(self, *args, **kwargs) -> Any:
        """BLOCKED: Sub-agents cannot update scoreboard."""
        self._blocked_writes += 1
        raise PermissionError("Sub-agents cannot modify scoreboard section.")

    def checkpoint(self, *args, **kwargs) -> Any:
        """BLOCKED: Sub-agents cannot create checkpoints."""
        self._blocked_writes += 1
        raise PermissionError("Sub-agents cannot create checkpoints.")


# =============================================================================
# BASE SUB-AGENT CLASS
# =============================================================================


class BaseSubAgent(ABC):
    """
    Base class for all sub-agents.

    Sub-agents:
    - Have their own LLM context (separate conversation)
    - Can only READ SessionState (via ReadOnlyBridge)
    - Report results via Delta Bus
    - Are spawned by Concierge for specialized tasks
    """

    # Class attributes to override
    AGENT_TYPE: str = "base"
    SYSTEM_PROMPT: str = "You are a helpful assistant."

    def __init__(
        self,
        bridge: "SessionLLMBridge",
        llm_client: "SimpleLLMClient",
        delta_bus: Optional["DeltaBus"] = None,
        agent_id: Optional[str] = None,
    ):
        """
        Initialize sub-agent.

        Args:
            bridge: SessionLLMBridge (will be wrapped as READ-ONLY)
            llm_client: LLM client for agent's own context
            delta_bus: Optional Delta bus for publishing results
            agent_id: Optional agent ID (auto-generated if not provided)
        """
        # Wrap bridge as read-only
        self._bridge = ReadOnlyBridge(bridge)
        self._llm = llm_client
        self._delta_bus = delta_bus
        self._agent_id = agent_id or f"{self.AGENT_TYPE}_{uuid.uuid4().hex[:8]}"

        # Agent state
        self._current_task_id: Optional[str] = None
        self._tool_calls_made = 0
        self._tasks_completed = 0

    @property
    def agent_id(self) -> str:
        """Get agent ID."""
        return self._agent_id

    @property
    def bridge(self) -> ReadOnlyBridge:
        """Get read-only bridge."""
        return self._bridge

    def _build_system_prompt(self) -> str:
        """Build full system prompt with context."""
        context = self._bridge.build_context_for_agent()

        return f"""{self.SYSTEM_PROMPT}

SESSION CONTEXT:
{context}

IMPORTANT:
- You have READ-ONLY access to the session state
- You cannot modify user preferences, beliefs, or history
- Return your findings to be processed by the Concierge
"""

    @abstractmethod
    def get_available_tools(self) -> List[Dict[str, Any]]:
        """
        Get list of tools this agent can use.

        Returns:
            List of tool schemas in Gemini format
        """
        pass

    @abstractmethod
    async def execute_tool(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """
        Execute a tool call.

        Args:
            tool_name: Name of the tool to execute
            args: Tool arguments

        Returns:
            Tool execution result
        """
        pass

    async def run_task(
        self,
        task_type: str,
        params: Dict[str, Any],
    ) -> AgentResult:
        """
        Run a task and return results.

        For POC: Directly executes the tool with mock data.
        In production: Would use LLM with tool calling.

        Args:
            task_type: Type of task (e.g., "search_accommodations")
            params: Task parameters

        Returns:
            AgentResult with task outcome
        """
        start_time = time.time()
        self._current_task_id = f"task_{uuid.uuid4().hex[:8]}"
        self._tool_calls_made = 0

        try:
            # POC: Directly execute the tool without LLM
            # Production would use LLM with tool calling
            tool_result = await self.execute_tool(task_type, params)
            self._tool_calls_made = 1

            # Wrap result for consistency
            results = [{"tool": task_type, "args": params, "result": tool_result}]

            duration_ms = int((time.time() - start_time) * 1000)

            result = AgentResult(
                agent_id=self._agent_id,
                agent_type=self.AGENT_TYPE,
                task_id=self._current_task_id,
                task_type=task_type,
                task_params=params,
                status=AgentStatus.COMPLETED,
                results=results,
                duration_ms=duration_ms,
                tool_calls_made=self._tool_calls_made,
            )

            # Publish to Delta Bus if available
            if self._delta_bus:
                await self._delta_bus.publish(
                    topic=f"agent.{self.AGENT_TYPE}.result",
                    message=result,
                )

            self._tasks_completed += 1
            return result

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Agent {self._agent_id} task failed: {e}")

            result = AgentResult(
                agent_id=self._agent_id,
                agent_type=self.AGENT_TYPE,
                task_id=self._current_task_id,
                task_type=task_type,
                task_params=params,
                status=AgentStatus.FAILED,
                results=None,
                error=str(e),
                duration_ms=duration_ms,
                tool_calls_made=self._tool_calls_made,
            )

            if self._delta_bus:
                await self._delta_bus.publish(
                    topic=f"agent.{self.AGENT_TYPE}.result",
                    message=result,
                )

            return result

    def _build_task_message(self, task_type: str, params: Dict[str, Any]) -> str:
        """Build user message for the task."""
        params_str = ", ".join(f"{k}={v}" for k, v in params.items())
        return f"Please execute task: {task_type}({params_str})"

    async def _process_llm_response(
        self,
        response: Any,
        task_type: str,
        params: Dict[str, Any],
    ) -> Any:
        """
        Process LLM response and execute any tool calls.

        Args:
            response: LLM response (may contain tool calls)
            task_type: Original task type
            params: Original task params

        Returns:
            Processed results
        """
        # Check if response has tool calls
        if hasattr(response, "tool_calls") and response.tool_calls:
            results = []
            for tool_call in response.tool_calls:
                tool_name = tool_call.get("name", "")
                tool_args = tool_call.get("args", {})

                self._tool_calls_made += 1
                tool_result = await self.execute_tool(tool_name, tool_args)
                results.append(
                    {
                        "tool": tool_name,
                        "args": tool_args,
                        "result": tool_result,
                    }
                )
            return results

        # No tool calls - just return the text response
        if hasattr(response, "text"):
            return {"message": response.text}

        return {"message": str(response)}
