"""
k1.fabric.adapters.auto_wasm_runtime -- Auto-discovering WASM runtime.

Convention-based replacement for per-module runtime classes
(DateCalcRuntime, UnitConvertRuntime, etc.).  ONE runtime handles
ALL WASM modules by scanning ``k1/tools/wasm_modules/`` at
construction time.

Adding a new WASM module requires ZERO changes to this file or any
other Fabric code:

  1. Create ``k1/tools/wasm_modules/<name>/executor.py``
     with ``execute(params: dict) -> dict``
  2. Add YAML contract in ``k1/contracts/tools/``
  3. Done.

Convention:
  Each WASM module directory MUST have an ``executor.py`` that exports
  an ``execute(params: dict) -> dict`` function.  This function
  contains the pure computation logic (no I/O, no side effects).

  The module name in the directory path is matched against the
  ``module_path`` from ProviderConfig (which is derived from the
  contract's ``provider_id``).  For example,
  ``provider_id: "date_calc_wasm"`` produces
  ``module_path: "modules/date_calc_wasm.wasm"`` which matches
  directory name ``date_calc`` (substring match).

Implements IWASMRuntime (Protocol from wasm_provider.py).
"""

from __future__ import annotations

import importlib
import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from k1.fabric.providers.wasm_provider import (
    WASMExecutionResult,
    WASMModuleHandle,
    WASMSandboxConfig,
)

logger = logging.getLogger(__name__)


class AutoDiscoveryWASMRuntime:
    """
    Auto-discovering WASM runtime.

    Scans ``modules_dir`` for WASM module executors and routes
    execution requests to the correct one. No per-module runtime
    classes needed.

    Implements IWASMRuntime:
      - async load_module(module_path) -> WASMModuleHandle
      - async execute(handle, function_name, params, sandbox_config) -> WASMExecutionResult
      - is_available() -> bool
    """

    def __init__(
        self,
        modules_dir: str = "k1/tools/wasm_modules",
        *,
        auto_discover: bool = True,
    ) -> None:
        self._available = True
        # module_name -> execute(params) callable
        self._executors: Dict[str, Callable[..., Dict[str, Any]]] = {}
        # module_path -> WASMModuleHandle (cache)
        self._handles: Dict[str, WASMModuleHandle] = {}

        if auto_discover:
            self._discover_modules(Path(modules_dir))

        logger.info(
            "[AutoDiscoveryWASMRuntime] Discovered %d WASM modules: %s",
            len(self._executors),
            list(self._executors.keys()),
        )

    # ------------------------------------------------------------------
    # Public: manual executor registration
    # ------------------------------------------------------------------

    def register_executor(
        self,
        module_name: str,
        execute_fn: Callable[..., Dict[str, Any]],
    ) -> None:
        """
        Register an executor function for a module name.

        Use this for modules that don't follow the filesystem
        convention, or for testing.

        Args:
            module_name: Module identifier (e.g. ``date_calc``).
            execute_fn: Callable ``(params: dict) -> dict``.
        """
        self._executors[module_name] = execute_fn
        logger.debug(
            "[AutoDiscoveryWASMRuntime] Registered executor: %s",
            module_name,
        )

    # ------------------------------------------------------------------
    # IWASMRuntime protocol
    # ------------------------------------------------------------------

    async def load_module(self, module_path: str) -> WASMModuleHandle:
        """
        Load a WASM module (match by module name in path).

        Matches the module_path from ProviderConfig against known
        executor names using substring matching.

        Cached after first successful load.
        """
        if module_path in self._handles:
            return self._handles[module_path]

        matched_name = self._match_executor(module_path)
        if matched_name is None:
            raise RuntimeError(
                f"Unknown WASM module: {module_path}. "
                f"Known modules: {list(self._executors.keys())}"
            )

        handle = WASMModuleHandle(
            module_path=module_path,
            module_id=f"{matched_name}-v1",
            loaded=True,
        )
        self._handles[module_path] = handle
        return handle

    async def execute(
        self,
        handle: WASMModuleHandle,
        function_name: str,
        params: Dict[str, Any],
        sandbox_config: WASMSandboxConfig,
    ) -> WASMExecutionResult:
        """
        Execute a function in the matched WASM module.

        Finds the executor by matching handle.module_path against
        known module names, then calls executor.execute(params).

        Args:
            handle: Module handle from load_module().
            function_name: The function to call (typically "execute").
            params: Tool parameters.
            sandbox_config: Sandbox constraints.

        Returns:
            WASMExecutionResult with computation output.
        """
        if not handle.loaded:
            return WASMExecutionResult(
                success=False,
                error_message="Module not loaded",
            )

        matched_name = self._match_executor(handle.module_path)
        if matched_name is None:
            return WASMExecutionResult(
                success=False,
                error_message=f"No executor for module: {handle.module_path}",
            )

        executor_fn = self._executors[matched_name]
        start = time.monotonic()

        try:
            output = executor_fn(params)
            elapsed_ms = int((time.monotonic() - start) * 1000)

            # Enforce timeout (post-hoc check for pure Python executors)
            if sandbox_config.timeout_ms > 0 and elapsed_ms > sandbox_config.timeout_ms:
                return WASMExecutionResult(
                    success=False,
                    error_message=(
                        f"Execution exceeded timeout: "
                        f"{elapsed_ms}ms > {sandbox_config.timeout_ms}ms"
                    ),
                    memory_used_mb=1,
                    execution_ms=elapsed_ms,
                )

            return WASMExecutionResult(
                success=True,
                output=output,
                memory_used_mb=1,
                execution_ms=elapsed_ms,
            )

        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return WASMExecutionResult(
                success=False,
                error_message=str(exc),
                memory_used_mb=1,
                execution_ms=elapsed_ms,
            )

    def is_available(self) -> bool:
        """Runtime is available if any executors were discovered."""
        return self._available and bool(self._executors)

    # ------------------------------------------------------------------
    # Test helpers
    # ------------------------------------------------------------------

    def set_available(self, available: bool) -> None:
        """Toggle availability for testing failure scenarios."""
        self._available = available

    # ------------------------------------------------------------------
    # Discovery engine
    # ------------------------------------------------------------------

    def _discover_modules(self, modules_dir: Path) -> None:
        """
        Scan modules_dir for WASM module executors.

        Each subdirectory with an ``executor.py`` exporting an
        ``execute`` function is registered.
        """
        if not modules_dir.exists():
            logger.warning(
                "[AutoDiscoveryWASMRuntime] Modules dir not found: %s",
                modules_dir,
            )
            return

        for child in sorted(modules_dir.iterdir()):
            if not child.is_dir() or child.name.startswith("_"):
                continue
            executor_py = child / "executor.py"
            if not executor_py.exists():
                continue

            module_import_path = f"k1.tools.wasm_modules.{child.name}.executor"

            try:
                module = importlib.import_module(module_import_path)
            except Exception as exc:
                logger.warning(
                    "[AutoDiscoveryWASMRuntime] Failed to import %s: %s",
                    module_import_path,
                    exc,
                )
                continue

            execute_fn = getattr(module, "execute", None)
            if execute_fn is None or not callable(execute_fn):
                logger.warning(
                    "[AutoDiscoveryWASMRuntime] No execute() function in %s",
                    module_import_path,
                )
                continue

            self._executors[child.name] = execute_fn  # type: ignore[assignment]
            logger.debug(
                "[AutoDiscoveryWASMRuntime] Registered executor: %s",
                child.name,
            )

    def _match_executor(self, module_path: str) -> Optional[str]:
        """
        Match a module_path to a known executor name.

        Uses substring matching: if any registered executor name
        appears in the module_path, it's a match.

        For example:
          "modules/date_calc_wasm.wasm" matches "date_calc"
          "k1/tools/wasm_modules/unit_convert" matches "unit_convert"
        """
        for name in self._executors:
            if name in module_path:
                return name
        return None
