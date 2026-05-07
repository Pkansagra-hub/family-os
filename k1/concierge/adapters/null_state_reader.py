"""
k1.concierge.adapters.null_state_reader -- Re-export shim.

Canonical location: k1.fabric.adapters.null_state_reader

Kept for backward compatibility (Issue 2.0.12).
"""

from k1.fabric.adapters.null_state_reader import NullSessionStateReaderAdapter

__all__ = ["NullSessionStateReaderAdapter"]
