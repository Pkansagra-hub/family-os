"""
poc.k1_poc.config -- Reverse shim.

Canonical location is now ``k1.concierge.config``.
This module re-exports for backward compatibility with POC demo scripts.
"""

from k1.concierge.config import *  # noqa: F401,F403
from k1.concierge.config import __all__  # noqa: F401
