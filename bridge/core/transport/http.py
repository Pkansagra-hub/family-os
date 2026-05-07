"""Production HTTP transport (re-export of the legacy single-file impl).

Lifts :class:`HttpTransport` and :class:`TransportConfig` out of the
package's ``__init__`` namespace so callers can import them at a stable
path going forward:

    from bridge.core.transport.http import HttpTransport, TransportConfig

The package ``__init__`` continues to re-export the same names for
backwards compatibility with the existing test suite.
"""

from __future__ import annotations

from bridge.core.transport import HttpResult, HttpTransport, TransportConfig

__all__ = ["HttpResult", "HttpTransport", "TransportConfig"]
