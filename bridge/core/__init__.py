"""K0-K1 Bridge - Core.

Cross-kernel security gateway providing:
- Kernel Transport (K0 <-> K1)
- Connector Security (Tools -> External devices)
"""

from .envelope_builder import BridgeConfig, CommandEnvelope, EnvelopeBuilder
from .signing import Ed25519Signing, HmacSigning, SigningBackend, SigningResult
from .transport import HttpResult, HttpTransport, TransportConfig

__all__ = [
    "BridgeConfig",
    "CommandEnvelope",
    "Ed25519Signing",
    "EnvelopeBuilder",
    "HmacSigning",
    "HttpResult",
    "HttpTransport",
    "SigningBackend",
    "SigningResult",
    "TransportConfig",
]
