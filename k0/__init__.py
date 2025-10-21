"""K0 kernel package scaffolding.

This module exposes minimal package metadata so downstream tooling can
import k0.* namespaces while the implementation is still under active
construction.
"""

from __future__ import annotations

__all__ = ["__version__"]

# NOTE: The version string is pinned to a dev placeholder until the
# runtime reaches a promoted milestone. CI pipelines can override this
# via environment variables or dynamic packaging metadata when the
# kernel ships a proper distribution artifact.
__version__ = "0.0.0-dev"
