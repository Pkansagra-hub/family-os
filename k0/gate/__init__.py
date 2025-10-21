"""Minimal gate scaffolding package."""

from __future__ import annotations

from .minimal_gate import GateOutcome, MinimalGate
from .schema_registry import SchemaRecord, SchemaRegistry

__all__ = [
    "GateOutcome",
    "MinimalGate",
    "SchemaRecord",
    "SchemaRegistry",
]
