"""Bridge runtime errors.

Distinct error classes so callers can `except` precisely. All bridge
boundary failures inherit from one of these — never raw `RuntimeError`.
"""

from __future__ import annotations


class UnboundContractError(RuntimeError):
    """Raised when code tries to publish/consume a topic that no manifest
    declares (R10: K1 bus rejects unknown cross-kernel contracts)."""


class ManifestValidationError(ValueError):
    """Raised when a manifest fails the meta-schema at runtime load.

    Distinct from :class:`tooling.contracts.manifest_loader.ManifestValidationError`
    so the runtime path can stay independent of the build-time path."""


class OfflineError(RuntimeError):
    """Raised when an online_required contract is invoked while the
    bridge transport is offline and no offline-queue option applies."""
