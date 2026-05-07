"""K0-K1 Bridge - Kernel Transport.

Communication ports for K0 <-> K1.

MS-3c: ``KernelQueryPort`` was removed; recall is now reachable only
through the typed paired contract surface
``BridgeRuntime.query.recall_request_v1.request(...)``.

MS-3d: ``KernelSSEPort`` was removed; SSE streaming is now codegen-
driven on the consumer side and powered by
``bridge/core/transport/sse_client.py`` on the wire side.
"""

from .command_port import ContractViolationError, KernelCommandPort, PolicyDeniedError
from .obs_port import KernelObsPort

__all__ = [
    "ContractViolationError",
    "KernelCommandPort",
    "KernelObsPort",
    "PolicyDeniedError",
]
