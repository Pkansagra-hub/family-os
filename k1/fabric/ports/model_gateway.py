"""
k1.fabric.ports.model_gateway -- IModelGatewayPort port (5.1.4).

LLM access for Agent Factory via capability-driven model selection.

Design:
  - Capability-driven routing: Model Hub exposes model manifests with
    capabilities (CHAT, TOOL_CALL, STRUCTURED, EMBED, VISION, BATCH).
  - ILLMHandle: opaque handle granting an agent LLM access within a
    token budget.  Returned by ``create_handle()``.
  - ModelCapability: enum of standard LLM capabilities.
  - ModelInfo: model metadata (id, capabilities, loaded status).
  - Per-provider circuit breakers handled by Model Hub internally.

Consumers:
  - AgentFactory (4.3.1 step 3) -- grant LLM access to spawned agents

Production adapter: Model Hub adapter (5.2.5)
Test adapter: TestModelGatewayAdapter (5.2.5)

References:
  - Agent Provider inline preview (agent_provider.py IModelGatewayPort)
  - Model Hub manifests (k1_cognitive_architecture_skeleton.mmd)
  - FAB-09 (trace_id on all LLM operations)

Exports:
  ILLMHandle
  IModelGatewayPort
  ModelCapability
  ModelInfo
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Supporting types
# ---------------------------------------------------------------------------


class ModelCapability(str, Enum):
    """
    Standard LLM capabilities from Model Hub manifests.

    Each model declares which capabilities it supports.
    Agent Factory uses these for capability-based model selection.
    """

    CHAT = "CHAT"
    """Conversational text generation."""

    TOOL_CALL = "TOOL_CALL"
    """Function/tool calling with structured output."""

    STRUCTURED = "STRUCTURED"
    """Structured JSON output generation."""

    EMBED = "EMBED"
    """Text embedding / vector generation."""

    VISION = "VISION"
    """Image/visual input processing."""

    BATCH = "BATCH"
    """Batch inference (non-interactive)."""


@dataclass(frozen=True)
class ModelInfo:
    """
    Model metadata from Model Hub.

    Attributes:
        model_id: Unique model identifier.
        capabilities: Set of capabilities this model supports.
        loaded: Whether the model is currently loaded and ready.
        max_tokens: Maximum context window size.
        provider: Model provider/backend identifier.
    """

    model_id: str = ""
    capabilities: List[str] = field(default_factory=list)
    loaded: bool = False
    max_tokens: int = 0
    provider: str = ""

    def has_capability(self, capability: str) -> bool:
        """Check if this model supports a given capability."""
        return capability in self.capabilities

    def has_all_capabilities(self, required: List[str]) -> bool:
        """Check if this model supports all required capabilities."""
        return all(cap in self.capabilities for cap in required)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "model_id": self.model_id,
            "capabilities": list(self.capabilities),
            "loaded": self.loaded,
            "max_tokens": self.max_tokens,
            "provider": self.provider,
        }


# ---------------------------------------------------------------------------
# ILLMHandle protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ILLMHandle(Protocol):
    """
    Opaque handle to an LLM model connection.

    Returned by ``IModelGatewayPort.create_handle()``.  Grants an agent
    access to a specific LLM within a token budget.

    Structurally compatible with inline preview in agent_provider.py.

    Token budget:
      Each handle has a remaining token budget.  Generation calls
      decrement the budget.  When exhausted, further calls should
      raise or return an error.

    Thread safety:
      A single handle is used by one agent at a time.
      Implementations need not be thread-safe.
    """

    async def generate(
        self,
        prompt: str,
        params: Dict[str, Any],
    ) -> str:
        """
        Generate a completion from the LLM.

        Args:
            prompt: The prompt text to send.
            params: Generation parameters (temperature, max_tokens,
                stop_sequences, etc.).

        Returns:
            Generated text string.
        """
        ...  # pragma: no cover

    @property
    def model_id(self) -> str:
        """Identifier of the model this handle connects to."""
        ...  # pragma: no cover

    @property
    def budget_tokens(self) -> int:
        """Remaining token budget for this handle."""
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# Port protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class IModelGatewayPort(Protocol):
    """
    LLM access port for the Capability Fabric.

    This is the canonical port interface (5.1.4).  Any object with
    matching method signatures satisfies this protocol (structural
    subtyping via ``typing.Protocol``).

    Capability-driven routing:
      Model Hub has manifests with capabilities (CHAT, TOOL_CALL,
      STRUCTURED, EMBED, VISION, BATCH).  ``find_model()`` returns
      a model ID that satisfies ALL required capabilities.
      ``create_handle()`` may accept a ``capabilities`` list to
      influence model selection beyond the preference string.

    Agent Factory integration:
      AgentFactory step 3 calls ``create_handle()`` to grant an LLM
      handle to a spawned agent.  The handle enforces token budget
      and model isolation.

    Thread safety:
      Implementations MUST support concurrent ``create_handle()``
      calls from multiple asyncio tasks.  ``is_model_loaded()`` and
      ``find_model()`` are read-only and safe for concurrent use.
    """

    def create_handle(
        self,
        budget_tokens: int,
        model_preference: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        trace_id: str = "",
    ) -> ILLMHandle:
        """
        Create an LLM handle with the given token budget.

        Args:
            budget_tokens: Maximum tokens this handle may consume.
            model_preference: Optional model ID preference.  If None,
                the gateway selects based on capabilities.
            capabilities: Optional list of required capabilities
                (e.g. ``["CHAT", "TOOL_CALL"]``).  Used for capability-
                driven model routing.
            trace_id: Trace ID for observability (FAB-09).

        Returns:
            ILLMHandle granting access to the selected model.
        """
        ...  # pragma: no cover

    async def is_model_loaded(self, model_id: str) -> bool:
        """
        Check if a model is currently loaded and ready.

        Args:
            model_id: The model identifier to check.

        Returns:
            True if the model is loaded, False otherwise.
        """
        ...  # pragma: no cover

    async def list_models(self) -> List[ModelInfo]:
        """
        List all available models with their capabilities.

        Returns:
            List of ModelInfo for all known models.
        """
        ...  # pragma: no cover

    async def find_model(self, required_capabilities: List[str]) -> Optional[str]:
        """
        Find a model that supports all required capabilities.

        Used for capability-driven routing when no model_preference
        is specified.

        Args:
            required_capabilities: List of capability strings the
                model must support.

        Returns:
            Model ID of a suitable model, or None if no model
            satisfies all requirements.
        """
        ...  # pragma: no cover
