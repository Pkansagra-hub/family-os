"""
k1.fabric.providers.wasm_provider -- WASMProvider (3.3.3).

Sandboxed WASM execution for untrusted or computationally isolated tools.

Execution flow (from fabric_discussion.md Section 11 -- Provider Type 2):
  1. Receive CapabilityRequest
  2. Load WASM module from ProviderConfig.module_path (cached after first load)
  3. Create sandbox with configured memory limit
  4. Marshal request.params into WASM-compatible format
  5. Execute WASM function
  6. Unmarshal result
  7. Return CapabilityResult

Sandbox constraints:
  - Memory limit: configurable (default 64MB via ProviderConfig.sandbox_memory_mb)
  - Execution timeout: configurable (default 5s via ProviderConfig.max_execution_ms)
  - No network access (pure computation only)

Design:
  - WASM runtime is injected via ``IWASMRuntime`` port (Protocol).
    Concrete implementations use wasmtime, wasmer, or similar WASM runtimes.
    Injected by FabricFactory during bootstrap.
  - WASMProvider does NOT depend on any WASM library at import time.
  - Module caching is managed by the IWASMRuntime implementation.
  - Thread-safe: no mutable state after construction.

References:
  - fabric_discussion.md Section 11 (Provider Type 2: WASM Provider)
  - k1_cognitive_architecture_skeleton.mmd (WASM_SANDBOX node, L4)
  - whiteboard Section 7 (Fabric execution: WASM Sandbox)
  - Epic 3.3.3 in fabric-implementation-plan.md

Exports:
  WASMProvider               -- WASM sandboxed execution provider
  IWASMRuntime               -- Runtime port protocol
  WASMModuleHandle           -- Opaque handle to a loaded WASM module
  WASMSandboxConfig          -- Sandbox configuration
  WASMProviderError          -- Base WASM exception
  WASMModuleLoadError        -- Module loading failed
  WASMExecutionError         -- Execution inside sandbox failed
  WASMMemoryLimitError       -- Sandbox memory limit exceeded
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from k1.fabric.providers.base_provider import (
    BaseProvider,
    ProviderExecutionError,
    ProviderTimeoutError,
    attach_provider_metadata,
    build_provider_metadata,
)
from k1.fabric.types import (
    CapabilityRequest,
    CapabilityResult,
    ExecutionContext,
    ProviderConfig,
    ProviderHealth,
    ProviderStatus,
)

logger = logging.getLogger(__name__)

# Default sandbox constraints (from fabric_discussion.md Section 11)
DEFAULT_SANDBOX_MEMORY_MB = 64
DEFAULT_MAX_EXECUTION_MS = 5000


# ---------------------------------------------------------------------------
# WASM types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WASMModuleHandle:
    """
    Opaque handle to a loaded and validated WASM module.

    Returned by IWASMRuntime.load_module(). Passed back to
    IWASMRuntime.execute() for actual invocation.

    Attributes:
        module_path: Filesystem path to the .wasm file.
        module_id: Unique identifier (hash or name).
        loaded: Whether the module is loaded and ready.
    """

    module_path: str = ""
    module_id: str = ""
    loaded: bool = False


@dataclass(frozen=True)
class WASMSandboxConfig:
    """
    Sandbox constraints for WASM execution.

    Attributes:
        memory_limit_mb: Maximum memory allocation (default 64MB).
        timeout_ms: Maximum execution time (default 5000ms).
        allow_network: Network access (always False for WASM).
        allow_filesystem: Filesystem access (always False for WASM).
    """

    memory_limit_mb: int = DEFAULT_SANDBOX_MEMORY_MB
    timeout_ms: int = DEFAULT_MAX_EXECUTION_MS
    allow_network: bool = False
    allow_filesystem: bool = False


@dataclass(frozen=True)
class WASMExecutionResult:
    """
    Raw result from WASM function execution.

    Attributes:
        success: Whether execution completed without error.
        output: Unmarshalled output data.
        error_message: Error description if success=False.
        memory_used_mb: Peak memory usage during execution.
        execution_ms: Actual execution time inside sandbox.
    """

    success: bool = True
    output: Dict[str, Any] = field(default_factory=dict)
    error_message: str = ""
    memory_used_mb: int = 0
    execution_ms: int = 0


# ---------------------------------------------------------------------------
# Runtime port (Protocol)
# ---------------------------------------------------------------------------


class IWASMRuntime(Protocol):
    """
    WASM runtime port for module loading and sandboxed execution.

    Concrete implementations wrap wasmtime, wasmer, or similar
    WASM runtimes. Injected into WASMProvider by FabricFactory.

    Implementations handle:
      - Module loading and caching
      - Sandbox creation with memory limits
      - Parameter marshalling (Python dict -> WASM arguments)
      - Result unmarshalling (WASM return -> Python dict)
      - Timeout enforcement within the sandbox

    All methods are async to support non-blocking execution.
    """

    async def load_module(self, module_path: str) -> WASMModuleHandle:
        """
        Load a WASM module from the filesystem.

        Implementations should cache loaded modules for repeated use.

        Args:
            module_path: Path to the .wasm file.

        Returns:
            WASMModuleHandle referencing the loaded module.

        Raises:
            Exception if module cannot be loaded or validated.
        """
        ...

    async def execute(
        self,
        handle: WASMModuleHandle,
        function_name: str,
        params: Dict[str, Any],
        sandbox_config: WASMSandboxConfig,
    ) -> WASMExecutionResult:
        """
        Execute a function within a sandboxed WASM module.

        Args:
            handle: Handle to a previously loaded module.
            function_name: Name of the exported WASM function.
            params: Marshalled parameters for the function.
            sandbox_config: Sandbox constraints (memory, timeout).

        Returns:
            WASMExecutionResult with output data or error.

        Raises:
            Exception on sandbox violation (memory, timeout) or
            execution failure.
        """
        ...

    def is_available(self) -> bool:
        """Check if the WASM runtime is available and functional."""
        ...


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class WASMProviderError(ProviderExecutionError):
    """Base exception for WASM provider operations."""

    def __init__(
        self,
        provider_id: str,
        message: str,
        *,
        retriable: bool = False,
    ) -> None:
        super().__init__(
            provider_id,
            message,
            retriable=retriable,
            error_code="wasm_error",
        )


class WASMModuleLoadError(WASMProviderError):
    """WASM module could not be loaded from disk."""

    def __init__(self, provider_id: str, module_path: str, reason: str = "") -> None:
        self.module_path = module_path
        detail = f": {reason}" if reason else ""
        super().__init__(
            provider_id,
            f"Failed to load WASM module '{module_path}'{detail}",
            retriable=False,
        )


class WASMExecutionError(WASMProviderError):
    """Execution inside the WASM sandbox failed."""

    def __init__(
        self,
        provider_id: str,
        message: str,
        *,
        retriable: bool = False,
    ) -> None:
        super().__init__(provider_id, message, retriable=retriable)


class WASMMemoryLimitError(WASMProviderError):
    """WASM sandbox exceeded its memory limit."""

    def __init__(self, provider_id: str, limit_mb: int, used_mb: int = 0) -> None:
        self.limit_mb = limit_mb
        self.used_mb = used_mb
        super().__init__(
            provider_id,
            f"WASM sandbox exceeded memory limit: {used_mb}MB / {limit_mb}MB",
            retriable=False,
        )


# ---------------------------------------------------------------------------
# WASMProvider
# ---------------------------------------------------------------------------


class WASMProvider(BaseProvider):
    """
    WASM sandboxed execution provider (3.3.3).

    Executes capabilities inside a WASM sandbox with strict resource
    constraints: limited memory, limited time, no network.

    Constructor Args:
        config: ProviderConfig with module_path, sandbox_memory_mb, limits.
        runtime: IWASMRuntime implementation for WASM execution.
        capability_names: List of capability names this provider handles.
        function_name: The exported WASM function to call (default: "execute").

    Usage::

        provider = WASMProvider(
            config=ProviderConfig(
                provider_id="calc_wasm",
                provider_type="WASM",
                module_path="k1/wasm/calc.wasm",
                sandbox_memory_mb=64,
                max_execution_ms=5000,
            ),
            runtime=my_wasm_runtime,
            capability_names=["tool.execute.calculator"],
        )
        result = await provider.execute(request, context, trace_id)

    Wrapped by CircuitBreaker (3.4.1): 5s timeout, 5 failures/min.
    """

    __slots__ = (
        "_runtime",
        "_capability_names",
        "_function_name",
        "_module_handle",
    )

    def __init__(
        self,
        config: ProviderConfig,
        *,
        runtime: IWASMRuntime,
        capability_names: Optional[List[str]] = None,
        function_name: str = "execute",
        **_kwargs: Any,
    ) -> None:
        """
        Args:
            config: Provider configuration (module_path, sandbox limits).
            runtime: WASM runtime implementation.
            capability_names: Capabilities this provider handles.
            function_name: WASM function name to invoke (default "execute").
            **_kwargs: Ignored (ProviderFactory pass-through).
        """
        super().__init__(config)
        self._runtime = runtime
        self._capability_names: List[str] = list(capability_names or [])
        self._function_name = function_name
        self._module_handle: Optional[WASMModuleHandle] = None

    # ======================================================================
    # CapabilityProvider interface
    # ======================================================================

    def capabilities(self) -> List[str]:
        """Return the list of capability names this WASM provider handles."""
        return list(self._capability_names)

    async def health_check(self) -> ProviderHealth:
        """
        Check WASM runtime availability and module loadability.

        Verifies the runtime is available and the configured module
        can be loaded (or is already cached).
        """
        start = time.monotonic()
        try:
            if not self._runtime.is_available():
                return ProviderHealth(
                    provider_id=self.provider_id,
                    status=ProviderStatus.UNHEALTHY.value,
                    error="WASM runtime not available",
                )

            # Try to load module (should be cached after first load)
            module_path = self.config.module_path or ""
            handle = await self._runtime.load_module(module_path)
            latency_ms = int((time.monotonic() - start) * 1000)

            if handle.loaded:
                return ProviderHealth(
                    provider_id=self.provider_id,
                    status=ProviderStatus.HEALTHY.value,
                    latency_ms=latency_ms,
                )
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderStatus.UNHEALTHY.value,
                latency_ms=latency_ms,
                error="Module not loaded",
            )
        except Exception as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.warning("[%s] health_check failed: %s", self.provider_id, exc)
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderStatus.UNHEALTHY.value,
                latency_ms=latency_ms,
                error=str(exc),
            )

    # ======================================================================
    # Internal execution (BaseProvider._execute)
    # ======================================================================

    async def _execute(
        self,
        request: CapabilityRequest,
        context: ExecutionContext,
        trace_id: str,
    ) -> CapabilityResult:
        """
        WASM-specific execution logic.

        Flow:
          1. Check runtime availability
          2. Load WASM module (cached)
          3. Build sandbox config
          4. Execute within sandbox
          5. Parse result
          6. Return CapabilityResult
        """
        start = time.monotonic()

        # --- Step 1: Check runtime ---
        if not self._runtime.is_available():
            raise WASMProviderError(
                self.provider_id,
                "WASM runtime is not available",
                retriable=True,
            )

        # --- Step 2: Load module ---
        module_path = self.config.module_path or ""
        try:
            handle = await self._runtime.load_module(module_path)
        except Exception as exc:
            raise WASMModuleLoadError(self.provider_id, module_path, str(exc)) from exc

        if not handle.loaded:
            raise WASMModuleLoadError(self.provider_id, module_path, "Module not loaded")

        # --- Step 3: Build sandbox config ---
        sandbox_config = self._build_sandbox_config()

        logger.debug(
            "[%s] WASM exec: module=%s, function=%s, memory=%dMB, trace=%s",
            self.provider_id,
            module_path,
            self._function_name,
            sandbox_config.memory_limit_mb,
            trace_id,
        )

        # --- Step 4: Execute within sandbox ---
        params = attach_provider_metadata(
            dict(request.params),
            build_provider_metadata(request, context),
        )
        try:
            wasm_result = await self._runtime.execute(
                handle=handle,
                function_name=self._function_name,
                params=params,
                sandbox_config=sandbox_config,
            )
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            # Check timeout
            if elapsed_ms >= self.config.max_execution_ms:
                raise ProviderTimeoutError(self.provider_id, self.config.max_execution_ms) from exc
            # Check memory-related errors
            err_msg = str(exc).lower()
            if "memory" in err_msg or "oom" in err_msg:
                raise WASMMemoryLimitError(
                    self.provider_id,
                    sandbox_config.memory_limit_mb,
                ) from exc
            raise WASMExecutionError(
                self.provider_id,
                f"WASM execution failed: {exc}",
                retriable=False,
            ) from exc

        # --- Step 5: Check timeout ---
        self._check_timeout(start)

        # --- Step 6: Parse and return ---
        return self._parse_result(request, wasm_result, trace_id, start)

    # ======================================================================
    # Private helpers
    # ======================================================================

    def _build_sandbox_config(self) -> WASMSandboxConfig:
        """Build sandbox config from ProviderConfig."""
        return WASMSandboxConfig(
            memory_limit_mb=self.config.sandbox_memory_mb or DEFAULT_SANDBOX_MEMORY_MB,
            timeout_ms=self.config.max_execution_ms,
            allow_network=False,
            allow_filesystem=False,
        )

    def _parse_result(
        self,
        request: CapabilityRequest,
        wasm_result: WASMExecutionResult,
        trace_id: str,
        start: float,
    ) -> CapabilityResult:
        """Convert WASMExecutionResult to CapabilityResult."""
        elapsed_ms = int((time.monotonic() - start) * 1000)

        if not wasm_result.success:
            # Check for memory limit errors
            if wasm_result.memory_used_mb > 0:
                sandbox_mb = self.config.sandbox_memory_mb or DEFAULT_SANDBOX_MEMORY_MB
                if wasm_result.memory_used_mb >= sandbox_mb:
                    raise WASMMemoryLimitError(
                        self.provider_id,
                        sandbox_mb,
                        wasm_result.memory_used_mb,
                    )
            return CapabilityResult.failure_result(
                request_id=request.request_id,
                error_code="wasm_execution_error",
                error_message=wasm_result.error_message or "WASM execution failed",
                retriable=False,
                provider_id=self.provider_id,
                trace_id=trace_id,
                duration_ms=elapsed_ms,
                execution_time_ms=wasm_result.execution_ms,
            )

        return CapabilityResult.success_result(
            request_id=request.request_id,
            data=wasm_result.output if wasm_result.output else {"result": None},
            provider_id=self.provider_id,
            trace_id=trace_id,
            duration_ms=elapsed_ms,
            execution_time_ms=wasm_result.execution_ms,
        )

    def __repr__(self) -> str:
        return (
            f"WASMProvider("
            f"provider_id={self.provider_id!r}, "
            f"module={self.config.module_path!r}, "
            f"memory={self.config.sandbox_memory_mb}MB, "
            f"capabilities={len(self._capability_names)})"
        )
