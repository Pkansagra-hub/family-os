"""K0-K1 Bridge - Core.

Cross-kernel security gateway providing:
- Kernel Transport (K0 <-> K1)
- Connector Security (Tools -> External devices)
"""

from .envelope_builder import BridgeConfig, CommandEnvelope, EnvelopeBuilder
from .events import EventBus, HealthTransition
from .health import (
    DegradedModeManager,
    K0AvailabilityStatus,
    K0HealthChecker,
    K0HealthSnapshot,
    K0HealthState,
)
from .online_first import OfflineError, OnlineFirstClient
from .signing import Ed25519Signing, HmacSigning, SigningBackend, SigningResult
from .transport import BridgeTransportError, HttpResult, HttpTransport, TransportConfig

__all__ = [
    "BridgeConfig",
    "BridgeTransportError",
    "CommandEnvelope",
    "DegradedModeManager",
    "Ed25519Signing",
    "EnvelopeBuilder",
    "EventBus",
    "HealthTransition",
    "HmacSigning",
    "HttpResult",
    "HttpTransport",
    "K0AvailabilityStatus",
    "K0HealthChecker",
    "K0HealthSnapshot",
    "K0HealthState",
    "OfflineError",
    "OnlineFirstClient",
    "SigningBackend",
    "SigningResult",
    "TransportConfig",
]
