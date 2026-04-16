"""Backward-compat shim -- real code moved to k1.kernel.bootstrap (Issue 2.0.6)."""

from k1.kernel.bootstrap import (  # noqa: F401
    KernelConfig,
    KernelRuntime,
    _build_delta_applicator,
    _DeltaEmitAdapter,
    _FabricGatewayAdapter,
    _StateReadAdapter,
    start_kernel,
    stop_kernel,
)
