"""Application bootstrap primitives for the K0 kernel.

The `k0.kernel` package owns process-level wiring: configuration loading,
dependency injection, and the FastAPI factory that exposes the privileged
ports defined under `k0.ports`.
"""

from __future__ import annotations

from .app import create_app
from .config import KernelSettings
from .readiness import ReadinessState

__all__ = ["create_app", "KernelSettings", "ReadinessState"]
