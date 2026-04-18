"""Backward-compat shim -- real code moved to k1.kernel.bootstrap (Issue 2.0.6).

P4B.5: re-exports of the OrchestratorStub adapter trinity
(`_FabricGatewayAdapter`, `_StateReadAdapter`, `_DeltaEmitAdapter`) and
`_build_delta_applicator` were removed. They were never the canonical surface;
import them from `k1.concierge.factory` if still needed.
"""

from k1.kernel.bootstrap import KernelConfig, KernelRuntime, start_kernel, stop_kernel  # noqa: F401
