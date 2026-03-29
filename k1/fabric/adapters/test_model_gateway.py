"""
k1.fabric.adapters.test_model_gateway -- TestModelGatewayAdapter (5.2.5).

In-memory LLM stub for testing.  Returns canned responses from
a configurable model catalog.  No real LLM dependency.

Design:
  - ``create_handle()`` returns a TestLLMHandle with configurable
    text responses (round-robin or static).
  - Model catalog: dict of ModelInfo keyed by model_id.
  - ``add_model()`` / ``remove_model()`` for test setup.
  - ``find_model()`` scans catalog for capability match.
  - ``is_model_loaded()`` checks catalog by model_id.
  - Thread-safe via RLock for concurrent test scenarios.

Structural subtyping:
  Satisfies IModelGatewayPort and ILLMHandle protocols without
  inheriting from them.

Exports:
  TestModelGatewayAdapter
  TestLLMHandle
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from k1.fabric.ports.model_gateway import ModelInfo

# ---------------------------------------------------------------------------
# TestLLMHandle
# ---------------------------------------------------------------------------


class TestLLMHandle:
    """
    In-memory LLM handle stub.

    Satisfies ILLMHandle structurally:
      - async generate(prompt, params) -> str
      - model_id property
      - budget_tokens property

    Configuration:
      - ``responses``: list of strings returned round-robin on generate().
      - ``budget_tokens``: remaining budget (decremented on each call).
      - ``error_after``: raise RuntimeError after N calls (0 = never).

    Introspection:
      - ``call_count``: number of generate() calls.
      - ``prompts``: list of prompts received.
    """

    def __init__(
        self,
        *,
        model_id: str = "test-model",
        budget_tokens: int = 10000,
        responses: Optional[List[str]] = None,
        error_after: int = 0,
    ) -> None:
        self._model_id = model_id
        self._budget_tokens = budget_tokens
        self._responses = responses or ["test response"]
        self._error_after = error_after
        self._call_index = 0
        self._call_count = 0
        self._prompts: List[str] = []

    async def generate(
        self,
        prompt: str,
        params: Dict[str, Any],
    ) -> str:
        """Return canned response (round-robin)."""
        self._call_count += 1
        self._prompts.append(prompt)

        if self._error_after > 0 and self._call_count > self._error_after:
            raise RuntimeError(f"TestLLMHandle: error_after={self._error_after} exceeded")

        if self._budget_tokens <= 0:
            raise RuntimeError("TestLLMHandle: token budget exhausted")

        # Decrement budget by a rough estimate
        tokens_used = max(len(prompt) // 4, 1)
        self._budget_tokens = max(0, self._budget_tokens - tokens_used)

        response = self._responses[self._call_index % len(self._responses)]
        self._call_index += 1
        return response

    @property
    def model_id(self) -> str:
        """Model identifier."""
        return self._model_id

    @property
    def budget_tokens(self) -> int:
        """Remaining token budget."""
        return self._budget_tokens

    @property
    def call_count(self) -> int:
        """Number of generate() calls made."""
        return self._call_count

    @property
    def prompts(self) -> List[str]:
        """List of prompts received."""
        return list(self._prompts)


# ---------------------------------------------------------------------------
# TestModelGatewayAdapter
# ---------------------------------------------------------------------------


class TestModelGatewayAdapter:
    """
    In-memory model gateway stub for testing (5.2.5).

    Implements IModelGatewayPort structurally:
      - create_handle(budget_tokens, model_preference, capabilities, trace_id) -> ILLMHandle
      - is_model_loaded(model_id) -> bool
      - list_models() -> list[ModelInfo]
      - find_model(required_capabilities) -> Optional[str]

    Setup helpers:
      - add_model(model_info) -- register a model in the catalog
      - remove_model(model_id) -- unregister a model
      - set_default_responses(responses) -- set responses for new handles
      - set_error_after(n) -- handles error after N generate() calls
      - clear() -- reset all models and tracking
      - get_handles() -- list of created handles
      - handle_count -- number of handles created
    """

    def __init__(
        self,
        *,
        default_responses: Optional[List[str]] = None,
        error_after: int = 0,
    ) -> None:
        self._models: Dict[str, ModelInfo] = {}
        self._default_responses = default_responses or ["test response"]
        self._error_after = error_after
        self._handles: List[TestLLMHandle] = []
        self._lock = threading.RLock()

    # -- Setup helpers -----------------------------------------------------

    def add_model(self, model_info: ModelInfo) -> None:
        """Register a model in the catalog."""
        with self._lock:
            self._models[model_info.model_id] = model_info

    def remove_model(self, model_id: str) -> None:
        """Unregister a model."""
        with self._lock:
            self._models.pop(model_id, None)

    def set_default_responses(self, responses: List[str]) -> None:
        """Set default responses for newly created handles."""
        with self._lock:
            self._default_responses = list(responses)

    def set_error_after(self, n: int) -> None:
        """Set error_after for newly created handles."""
        with self._lock:
            self._error_after = n

    def clear(self) -> None:
        """Reset all models, handles, and settings."""
        with self._lock:
            self._models.clear()
            self._handles.clear()
            self._default_responses = ["test response"]
            self._error_after = 0

    def get_handles(self) -> List[TestLLMHandle]:
        """Return all created handles."""
        with self._lock:
            return list(self._handles)

    @property
    def handle_count(self) -> int:
        """Number of handles created."""
        with self._lock:
            return len(self._handles)

    # -- Protocol methods --------------------------------------------------

    def create_handle(
        self,
        budget_tokens: int,
        model_preference: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        trace_id: str = "",
    ) -> TestLLMHandle:
        """Create a test LLM handle with canned responses."""
        with self._lock:
            # Resolve model_id
            model_id = model_preference or "test-model"

            # If model_preference given, check catalog
            if model_preference and model_preference in self._models:
                model_id = model_preference
            elif capabilities:
                # Try to find matching model
                found = self._find_model_internal(capabilities)
                if found:
                    model_id = found

            handle = TestLLMHandle(
                model_id=model_id,
                budget_tokens=budget_tokens,
                responses=list(self._default_responses),
                error_after=self._error_after,
            )
            self._handles.append(handle)
            return handle

    def is_model_loaded(self, model_id: str) -> bool:
        """Check if a model is in the catalog and loaded."""
        with self._lock:
            info = self._models.get(model_id)
            return info is not None and info.loaded

    def list_models(self) -> List[ModelInfo]:
        """List all models in the catalog."""
        with self._lock:
            return list(self._models.values())

    def find_model(self, required_capabilities: List[str]) -> Optional[str]:
        """Find a model supporting all required capabilities."""
        with self._lock:
            return self._find_model_internal(required_capabilities)

    # -- Internals ---------------------------------------------------------

    def _find_model_internal(
        self,
        required_capabilities: List[str],
    ) -> Optional[str]:
        """Find matching model (caller holds lock)."""
        for model_id, info in self._models.items():
            if info.has_all_capabilities(required_capabilities) and info.loaded:
                return model_id
        # Second pass: include unloaded models
        for model_id, info in self._models.items():
            if info.has_all_capabilities(required_capabilities):
                return model_id
        return None

    def __repr__(self) -> str:
        with self._lock:
            return (
                f"TestModelGatewayAdapter(models={len(self._models)}, "
                f"handles={len(self._handles)})"
            )
