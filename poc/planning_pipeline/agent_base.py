"""
Agent Base Class - Foundation for all domain-specific agents

Every agent in the circular hub-and-spoke model extends this base.
Agents have tools, can ask user questions, and can collaborate.
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class AgentContext:
    """Context passed to agent for execution"""

    agent_id: str
    agent_type: str  # e.g., "travel_agent", "restaurant_agent"
    user_input: str
    user_id: str = "user"
    tools: Dict[str, Any] = field(default_factory=dict)  # Tools available to agent
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    user_profile: Dict[str, Any] = field(default_factory=dict)  # User preferences, past data
    clarification_history: List[str] = field(default_factory=list)  # Previous clarifications
    current_time: str = field(
        default_factory=lambda: datetime.now().strftime("%A, %B %d, %Y, %I:%M %p")
    )
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResponse:
    """Response from agent execution"""

    agent_id: str
    agent_type: str
    status: str  # "completed", "needs_clarification", "error"
    result: Optional[Dict[str, Any]] = None
    clarification_question: Optional[str] = None
    required_data: Optional[List[str]] = None  # What info agent needs
    tools_used: List[str] = field(default_factory=list)
    latency_ms: float = 0.0
    error: Optional[str] = None


class Agent(ABC):
    """
    Base class for all domain-specific agents.

    Agents operate in circular hub-and-spoke model:
    - User is at center
    - Agents are workers around the circle
    - Each agent has specific tools
    - Agents can ask user for clarification
    - Agents can collaborate with other agents
    """

    def __init__(self, agent_id: str, agent_type: str, llm_provider):
        """
        Initialize agent.

        Args:
            agent_id: Unique ID for this agent instance
            agent_type: Type of agent (e.g., "travel_agent")
            llm_provider: LLM provider for agent reasoning
        """
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.llm_provider = llm_provider
        self.context: Optional[AgentContext] = None
        self.prompt_template: str = ""

    @abstractmethod
    async def execute(self, context: AgentContext) -> AgentResponse:
        """
        Execute agent logic.

        Args:
            context: AgentContext with user input, tools, history

        Returns:
            AgentResponse with result or clarification request
        """
        pass

    @abstractmethod
    def get_required_tools(self) -> List[str]:
        """Get list of tool names this agent needs."""
        pass

    def set_prompt_template(self, prompt: str):
        """Set the prompt template for this agent."""
        self.prompt_template = prompt

    async def ask_user(self, question: str) -> str:
        """
        Ask user a question directly.
        In circular model, user is at center - agents can ask directly.

        Args:
            question: Question to ask user

        Returns:
            User's answer
        """
        # This will be implemented by orchestrator to route back to user
        raise NotImplementedError("ask_user must be implemented by orchestrator")

    async def get_from_agent(self, agent_type: str, query: str) -> Optional[Dict[str, Any]]:
        """
        Ask another agent for data (agent collaboration).

        Args:
            agent_type: Type of agent to query
            query: What data to request

        Returns:
            Data from the other agent
        """
        # This will be implemented by orchestrator
        raise NotImplementedError("get_from_agent must be implemented by orchestrator")

    async def use_tool(self, tool_name: str, **kwargs) -> Any:
        """
        Use a tool available to this agent.

        Args:
            tool_name: Name of the tool
            **kwargs: Arguments for the tool

        Returns:
            Tool result
        """
        if not self.context or tool_name not in self.context.tools:
            raise ValueError(f"Tool {tool_name} not available to {self.agent_type}")

        tool = self.context.tools[tool_name]
        return await tool(**kwargs) if asyncio.iscoroutinefunction(tool) else tool(**kwargs)

    def get_time_context(self) -> str:
        """Get formatted current time for agent."""
        return (
            self.context.current_time
            if self.context
            else datetime.now().strftime("%A, %B %d, %Y, %I:%M %p")
        )

    def get_user_profile(self) -> Dict[str, Any]:
        """Get user profile/preferences."""
        return self.context.user_profile if self.context else {}

    def get_conversation_context(self, last_n: int = 5) -> str:
        """Get recent conversation history."""
        if not self.context or not self.context.conversation_history:
            return ""

        recent = self.context.conversation_history[-last_n:]
        context = ""
        for msg in recent:
            context += f"{msg.get('role', 'USER').upper()}: {msg.get('content', '')}\n"
        return context.strip()
