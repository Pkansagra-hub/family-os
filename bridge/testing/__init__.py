"""Test-only fixtures for the Bridge package.

Contains stub/fake implementations of bridge clients and ports that are
intended to be imported ONLY from test modules.  Production code MUST NOT
import from this package.

P7.6: ``StubBridgeClient`` was relocated here from ``bridge/client.py`` so
that the production module no longer ships test fixtures.
"""

from __future__ import annotations

from .stub_client import StubBridgeClient

__all__ = ["StubBridgeClient"]
