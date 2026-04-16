"""K0-K1 Bridge - Core.

Cross-kernel security gateway providing:
- Kernel Transport (K0 <-> K1)
- Connector Security (Tools -> External devices)
"""

from .envelope_builder import BridgeConfig, CommandEnvelope, EnvelopeBuilder
from .health import DegradedModeManager, K0AvailabilityStatus, K0HealthChecker, K0HealthSnapshot
from .signing import Ed25519Signing, HmacSigning, SigningBackend, SigningResult
from .transport import HttpResult, HttpTransport, TransportConfig

__all__ = [
    "BridgeConfig",
    "CommandEnvelope",
    "DegradedModeManager",
    "Ed25519Signing",
    "EnvelopeBuilder",
    "HmacSigning",
    "HttpResult",
    "HttpTransport",
    "K0AvailabilityStatus",
    "K0HealthChecker",
    "K0HealthSnapshot",
    "SigningBackend",
    "SigningResult",
    "TransportConfig",
]
