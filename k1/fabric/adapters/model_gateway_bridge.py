"""
k1.fabric.adapters.model_gateway_bridge -- Production IModelGatewayPort adapter.

Bridges Fabric's IModelGatewayPort (handle-based, budget-enforced LLM access)
to ModelHub's IModelHubPort (envelope-based request/response).

Two classes:
  - ModelGatewayBridgeAdapter: implements IModelGatewayPort, wraps IModelHubPort
  - LLMHandleBridge: implements ILLMHandle, wraps IModelHubPort.execute()

Design:
  - create_handle() returns a LLMHandleBridge bound to a specific model
    with a token budget. The handle translates generate(prompt, params)
    into HubRequest(CHAT, ChatPayload) -> HubResponse -> text.
  - is_model_loaded() calls discover_models() and checks by model_id.
  - list_models() translates MH ModelInfo -> Fabric ModelInfo.
  - find_model() filters discover_models() by required capabilities.

References:
  - E-0.5.2: Fabric->ModelHub Missing Bridge Adapter
  - Fabric ARCHITECTURE.md Section 4, Connection 4
  - ModelHub ARCHITECTURE.md Section 4, Connection 5
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from k1.fabric.ports.model_gateway import ModelInfo as FabricModelInfo
from k1.model_hub.ports.hub_port import IModelHubPort
from k1.model_hub.types import CapabilityType, ChatPayload, HubRequest, Message
from k1.model_hub.types import ModelInfo as HubModelInfo
from k1.model_hub.types import RequestConstraints, TokenUsage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLMHandleBridge -- implements ILLMHandle
# ---------------------------------------------------------------------------


class LLMHandleBridge:
    """ILLMHandle implementation backed by IModelHubPort.execute().

    Each handle tracks a remaining token budget. generate() translates
    (prompt, params) into a HubRequest with CHAT capability, calls
    execute(), extracts the text result, and decrements the budget by
    actual token usage reported in HubResponse.metadata.

    Thread safety:
      NOT thread-safe -- a single handle is used by one agent at a time
      (per ILLMHandle contract).
    """

    def __init__(
        self,
        hub: IModelHubPort,
        model_id: str,
        budget_tokens: int,
        trace_id: str = "",
    ) -> None:
        self._hub = hub
        self._model_id = model_id
        self._budget_tokens = budget_tokens
        self._trace_id = trace_id

    async def generate(
        self,
        prompt: str,
        params: Dict[str, Any],
    ) -> str:
        """Generate a completion via ModelHub execute().

        Translates prompt + params into HubRequest(CHAT), calls
        IModelHubPort.execute(), extracts text from HubResponse.result,
        decrements budget by actual usage.

        Args:
            prompt: The prompt text.
            params: Generation parameters (temperature, max_tokens, etc.).

        Returns:
            Generated text string.

        Raises:
            RuntimeError: If token budget is exhausted.
        """
        if self._budget_tokens <= 0:
            raise RuntimeError("LLMHandleBridge: token budget exhausted")

        # Build ChatPayload from prompt
        messages = [Message(role="user", content=prompt)]
        system_prompt = params.get("system_prompt")
        payload = ChatPayload(
            messages=messages,
            system_prompt=system_prompt,
        )

        # Build constraints from params + remaining budget
        max_tokens = min(
            params.get("max_tokens", 4096),
            self._budget_tokens,
        )
        temperature = params.get("temperature", 0.7)
        constraints = RequestConstraints(
            max_tokens=max_tokens,
            temperature=temperature,
        )

        # Build HubRequest
        request = HubRequest(
            capability=CapabilityType.CHAT,
            payload=payload,
            constraints=constraints,
            trace_id=self._trace_id or str(uuid.uuid4()),
        )

        response = await self._hub.execute(request)

        # Decrement budget by actual usage
        usage: TokenUsage = (
            getattr(getattr(response, "metadata", None), "usage", None) or TokenUsage()
        )
        tokens_used = usage.total_tokens or max(len(prompt) // 4, 1)
        self._budget_tokens = max(0, self._budget_tokens - tokens_used)

        # Extract text from result
        result = response.result
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            return result.get("content", str(result))
        return str(result)

    @property
    def model_id(self) -> str:
        """Model identifier."""
        return self._model_id

    @property
    def budget_tokens(self) -> int:
        """Remaining token budget."""
        return self._budget_tokens


# ---------------------------------------------------------------------------
# ModelGatewayBridgeAdapter -- implements IModelGatewayPort
# ---------------------------------------------------------------------------


class ModelGatewayBridgeAdapter:
    """Production IModelGatewayPort backed by IModelHubPort.

    Bridges Fabric's handle-based LLM API to ModelHub's envelope API.

    Method mapping:
      create_handle()  -> wraps hub in LLMHandleBridge
      is_model_loaded() -> discover_models() + check by id
      list_models()     -> discover_models() + translate ModelInfo
      find_model()      -> discover_models() + filter by capabilities

    Thread safety:
      Supports concurrent create_handle() calls (each creates an
      independent LLMHandleBridge). Discovery methods are read-only.
    """

    def __init__(self, hub: IModelHubPort) -> None:
        self._hub = hub

    def create_handle(
        self,
        budget_tokens: int,
        model_preference: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        trace_id: str = "",
    ) -> LLMHandleBridge:
        """Create an LLM handle backed by ModelHub.

        Args:
            budget_tokens: Maximum tokens this handle may consume.
            model_preference: Optional model ID preference.
            capabilities: Optional required capabilities (unused for
                handle creation -- model selection deferred to Hub).
            trace_id: Trace ID for observability.

        Returns:
            LLMHandleBridge granting LLM access within the budget.
        """
        model_id = model_preference or "auto"
        return LLMHandleBridge(
            hub=self._hub,
            model_id=model_id,
            budget_tokens=budget_tokens,
            trace_id=trace_id,
        )

    async def is_model_loaded(self, model_id: str) -> bool:
        """Check if a model is available via ModelHub.

        Calls discover_models() and checks if model_id is present.
        """
        try:
            models = await self._hub.discover_models()
            return any(m.id == model_id for m in models)
        except Exception as exc:
            logger.warning("is_model_loaded failed: %s", exc)
            return False

    async def list_models(self) -> List[FabricModelInfo]:
        """List models via ModelHub, translated to Fabric ModelInfo."""
        hub_models = await self._hub.discover_models()
        return [self._translate_model_info(m) for m in hub_models]

    async def find_model(self, required_capabilities: List[str]) -> Optional[str]:
        """Find a model supporting all required capabilities."""
        hub_models = await self._hub.discover_models()
        for m in hub_models:
            cap_values = [
                c.value if isinstance(c, CapabilityType) else str(c) for c in m.capabilities
            ]
            if all(req in cap_values for req in required_capabilities):
                return m.id
        return None

    @staticmethod
    def _translate_model_info(hub_model: HubModelInfo) -> FabricModelInfo:
        """Translate ModelHub ModelInfo -> Fabric ModelInfo."""
        return FabricModelInfo(
            model_id=hub_model.id,
            capabilities=[
                c.value if isinstance(c, CapabilityType) else str(c) for c in hub_model.capabilities
            ],
            loaded=True,  # If Hub reports it, it's available
            max_tokens=hub_model.max_context,
            provider=hub_model.provider_id,
        )
