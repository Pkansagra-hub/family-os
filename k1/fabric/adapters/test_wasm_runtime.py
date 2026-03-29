"""
k1.fabric.adapters.test_wasm_runtime -- TestWASMRuntime (5.2.x).

In-memory WASM runtime stub for testing. Returns canned execution
results keyed by function_name.

Design:
  - ``is_available()`` configurable via constructor (default True).
  - Canned results keyed by ``function_name`` string.
  - Dynamic handlers for custom per-test behavior.
  - Thread-safe via RLock for concurrent test scenarios.
  - Capture mode: records all execute() calls for assertions.
  - No real WASM runtime dependency.

Structural subtyping:
  Satisfies IWASMRuntime protocol without inheriting from it.

References:
  - wasm_provider.py (3.3.3) -- IWASMRuntime protocol
  - TestBridgeAdapter (5.2.4) -- same pattern
  - Epic 5.2 in fabric-implementation-plan.md

Exports:
  TestWASMRuntime
  CapturedWASMCall
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from k1.fabric.providers.wasm_provider import (
    WASMExecutionResult,
    WASMModuleHandle,
    WASMSandboxConfig,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Captured call record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CapturedWASMCall:
    """Record of a WASM execution call for test assertions."""

    function_name: str
    params: Dict[str, Any] = field(default_factory=dict)
    module_path: str = ""
    timestamp_ms: int = 0


# ---------------------------------------------------------------------------
# TestWASMRuntime
# ---------------------------------------------------------------------------


class TestWASMRuntime:
    """
    In-memory WASM runtime stub for testing.

    Implements IWASMRuntime structurally:
      - async load_module(module_path) -> WASMModuleHandle
      - async execute(handle, function_name, params, sandbox_config) -> WASMExecutionResult
      - is_available() -> bool

    Setup helpers for tests:
      - set_available(flag) -- toggle availability
      - add_result(function_name, result) -- canned WASMExecutionResult
      - add_handler(function_name, handler) -- dynamic handler
      - clear_results() -- reset all canned data
      - get_captured() -- list of all captured calls
      - drain() -- return + clear captured calls
      - call_count -- total calls made
    """

    def __init__(
        self,
        *,
        available: bool = True,
        default_result: Optional[WASMExecutionResult] = None,
    ) -> None:
        self._available = available
        self._default_result = default_result or WASMExecutionResult(
            success=True,
            output={"result": "test_output"},
            execution_ms=1,
            memory_used_mb=1,
        )
        self._results: Dict[str, WASMExecutionResult] = {}
        self._handlers: Dict[str, Callable[..., WASMExecutionResult]] = {}
        self._modules: Dict[str, WASMModuleHandle] = {}
        self._captured: List[CapturedWASMCall] = []
        self._lock = threading.RLock()

    # ======================================================================
    # IWASMRuntime protocol
    # ======================================================================

    async def load_module(self, module_path: str) -> WASMModuleHandle:
        """
        Load a WASM module (returns cached or new handle).
        """
        with self._lock:
            if module_path not in self._modules:
                self._modules[module_path] = WASMModuleHandle(
                    module_id=f"test-{module_path}",
                    module_path=module_path,
                    loaded=True,
                )
            return self._modules[module_path]

    async def execute(
        self,
        handle: WASMModuleHandle,
        function_name: str,
        params: Dict[str, Any],
        sandbox_config: WASMSandboxConfig,
    ) -> WASMExecutionResult:
        """
        Execute a WASM function and return canned result.

        Priority:
          1. Dynamic handler (if registered for function_name)
          2. Canned result (if registered for function_name)
          3. Default result
        """
        with self._lock:
            self._captured.append(
                CapturedWASMCall(
                    function_name=function_name,
                    params=dict(params),
                    module_path=handle.module_path,
                    timestamp_ms=int(time.monotonic() * 1000),
                )
            )

            # Dynamic handler first
            handler = self._handlers.get(function_name)
            if handler is not None:
                return handler(handle, function_name, params, sandbox_config)

            # Canned result
            canned = self._results.get(function_name)
            if canned is not None:
                return canned

            return self._default_result

    def is_available(self) -> bool:
        """Check if WASM runtime is available."""
        return self._available

    # ======================================================================
    # Test setup helpers
    # ======================================================================

    def set_available(self, flag: bool) -> None:
        """Toggle availability state."""
        self._available = flag

    def add_result(self, function_name: str, result: WASMExecutionResult) -> None:
        """Register a canned WASMExecutionResult for a function_name."""
        with self._lock:
            self._results[function_name] = result

    def add_handler(
        self,
        function_name: str,
        handler: Callable[..., WASMExecutionResult],
    ) -> None:
        """Register a dynamic handler for a function_name."""
        with self._lock:
            self._handlers[function_name] = handler

    def clear_results(self) -> None:
        """Remove all canned results and handlers."""
        with self._lock:
            self._results.clear()
            self._handlers.clear()

    def get_captured(self) -> List[CapturedWASMCall]:
        """Return defensive copy of captured calls."""
        with self._lock:
            return list(self._captured)

    def drain(self) -> List[CapturedWASMCall]:
        """Return and clear captured calls."""
        with self._lock:
            captured = list(self._captured)
            self._captured.clear()
            return captured

    @property
    def call_count(self) -> int:
        """Total number of execute() calls."""
        with self._lock:
            return len(self._captured)
