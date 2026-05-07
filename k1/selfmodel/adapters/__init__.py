"""Adapters for k1.selfmodel ports.

Production adapters land across M2–M4. Test doubles live under
``tests/k1/selfmodel/adapters/_stubs.py``.
"""

from __future__ import annotations

from k1.selfmodel.adapters.memory_projection_store import InMemoryProjectionStore

__all__ = ["InMemoryProjectionStore"]
