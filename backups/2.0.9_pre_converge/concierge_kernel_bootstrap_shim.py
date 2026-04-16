"""Backward-compat shim -- real code moved to k1.kernel.bootstrap (Issue 2.0.6)."""

from k1.kernel.bootstrap import (  # noqa: F401
    KernelConfig,
    KernelRuntime,
    _build_delta_applicator,
    _create_capability_registry,
    _create_fabric,
    _create_model,
    _create_session_state,
    _DeltaEmitAdapter,
    _FabricGatewayAdapter,
    _mailbox_consumer,
    _StateReadAdapter,
    start_kernel,
    stop_kernel,
)
