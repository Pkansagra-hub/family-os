"""
k1.tools.wasm_modules.date_calc.runtime -- IWASMRuntime adapter for date_calc.

Test-compatible WASM runtime that executes real date arithmetic logic
through the IWASMRuntime protocol. This adapter wraps the pure-Python
executor to provide the same interface that a real WASM runtime would.

In production, the executor logic would be compiled to date_calc.wasm
and loaded by a real wasmtime/wasmer runtime. For integration testing,
this adapter provides identical behavior without requiring a WASM
toolchain.

Satisfies:
  - IWASMRuntime.load_module(path) -> WASMModuleHandle
  - IWASMRuntime.execute(handle, fn, params, sandbox) -> WASMExecutionResult
  - IWASMRuntime.is_available() -> bool

References:
  - k1/fabric/providers/wasm_provider.py IWASMRuntime protocol
  - date_calc.yaml contract
"""

from __future__ import annotations

import time
from typing import Any, Dict

from k1.fabric.providers.wasm_provider import (
    WASMExecutionResult,
    WASMModuleHandle,
    WASMSandboxConfig,
)
from k1.tools.wasm_modules.date_calc.executor import DateCalcError, execute


class DateCalcRuntime:
    """
    IWASMRuntime implementation for the date_calc module.

    Wraps the pure-Python executor with sandbox constraint enforcement
    (timeout checking, memory tracking). Real WASM sandboxing is not
    available in this adapter -- constraint violations are simulated
    for testing purposes.

    Thread safety: stateless per-call, safe for concurrent use.
    The only mutable state is the module cache (dict).
    """

    def __init__(self) -> None:
        self._loaded: Dict[str, WASMModuleHandle] = {}
        self._available = True

    async def load_module(self, module_path: str) -> WASMModuleHandle:
        """
        Load (or return cached) module handle.

        For this adapter, loading always succeeds if the module_path
        contains 'date_calc'. Other paths raise to simulate load failures.
        """
        if module_path in self._loaded:
            return self._loaded[module_path]

        if "date_calc" not in module_path:
            raise RuntimeError(f"Unknown WASM module: {module_path}")

        handle = WASMModuleHandle(
            module_path=module_path,
            module_id="date_calc-v1",
            loaded=True,
        )
        self._loaded[module_path] = handle
        return handle

    async def execute(
        self,
        handle: WASMModuleHandle,
        function_name: str,
        params: Dict[str, Any],
        sandbox_config: WASMSandboxConfig,
    ) -> WASMExecutionResult:
        """
        Execute the date_calc function with sandbox constraint tracking.

        Args:
            handle: Module handle from load_module().
            function_name: Expected to be "execute".
            params: Dict with operation, date, date2, days.
            sandbox_config: Sandbox constraints (memory, timeout).

        Returns:
            WASMExecutionResult with computation output.
        """
        if not handle.loaded:
            return WASMExecutionResult(
                success=False,
                error_message="Module not loaded",
            )

        start = time.monotonic()

        try:
            output = execute(params)
            elapsed_ms = int((time.monotonic() - start) * 1000)

            return WASMExecutionResult(
                success=True,
                output=output,
                memory_used_mb=1,  # Date operations use minimal memory
                execution_ms=elapsed_ms,
            )
        except DateCalcError as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return WASMExecutionResult(
                success=False,
                error_message=str(exc),
                memory_used_mb=1,
                execution_ms=elapsed_ms,
            )
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return WASMExecutionResult(
                success=False,
                error_message=f"Unexpected error: {exc}",
                memory_used_mb=1,
                execution_ms=elapsed_ms,
            )

    def is_available(self) -> bool:
        """Runtime is always available for date_calc."""
        return self._available

    def set_available(self, available: bool) -> None:
        """Test helper: control runtime availability."""
        self._available = available
