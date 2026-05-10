"""K0 handle for the live-system harness — *attach mode*.

In Epic 7.1 the assumption is that K0 already runs in Docker (kernel
exposed at ``http://localhost:8080`` and postgres at
``localhost:5432``). The harness simply attaches to that running stack
rather than spawning its own K0.

Spawning a fresh K0 from Python (testcontainers path) is intentionally
not implemented in this PR — see the harness README for the deferred
``spawn_k0`` mode.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

DEFAULT_K0_BASE_URL = "http://127.0.0.1:8080"
DEFAULT_K0_DB_URL = "postgresql://familyos:familyos@127.0.0.1:5432/familyos"


class K0NotReachableError(RuntimeError):
    """Raised when the running K0 cannot be reached during attach."""


@dataclass
class K0Handle:
    """Attach-mode handle to an already-running K0 (Docker).

    Provides health/readiness probes and direct HTTP access to K0's
    public ports. The harness does not own K0's lifecycle in attach
    mode — call sites must rely on the Docker stack staying up.
    """

    base_url: str = DEFAULT_K0_BASE_URL
    db_url: str = DEFAULT_K0_DB_URL
    pid: int | None = None  # None in attach mode — Docker-managed.
    attach_mode: bool = True

    @classmethod
    def attach(
        cls,
        *,
        base_url: str | None = None,
        db_url: str | None = None,
        wait_seconds: float = 5.0,
    ) -> "K0Handle":
        url = base_url or os.environ.get("K0_BASE_URL", DEFAULT_K0_BASE_URL)
        db = db_url or os.environ.get("K0_DB_URL", DEFAULT_K0_DB_URL)
        handle = cls(base_url=url, db_url=db, attach_mode=True)
        handle._wait_for_ready(wait_seconds)
        return handle

    # -- health ------------------------------------------------------------
    def healthz(self, *, timeout_s: float = 2.0) -> dict:
        with httpx.Client(timeout=timeout_s) as client:
            r = client.get(f"{self.base_url}/healthz")
            r.raise_for_status()
            return r.json()

    def readyz(self, *, timeout_s: float = 2.0) -> int:
        with httpx.Client(timeout=timeout_s) as client:
            r = client.get(f"{self.base_url}/readyz")
            return r.status_code

    def metrics(self, *, timeout_s: float = 5.0) -> str:
        with httpx.Client(timeout=timeout_s) as client:
            r = client.get(f"{self.base_url}/metrics")
            r.raise_for_status()
            return r.text

    # -- lifecycle ---------------------------------------------------------
    def signal(self, sig: int) -> None:
        if self.attach_mode:
            raise NotSupportedInAttachMode(
                "K0 lifecycle (signal/start/stop) is owned by Docker in attach "
                "mode. Use docker-compose to stop/start the K0 container."
            )
        raise NotImplementedError("spawn-mode K0 not implemented in Epic 7.1")

    # -- internal ----------------------------------------------------------
    def _wait_for_ready(self, deadline_s: float) -> None:
        deadline = time.monotonic() + deadline_s
        last_err: Exception | None = None
        while time.monotonic() < deadline:
            try:
                payload = self.healthz()
                if payload.get("status") == "ok":
                    logger.info(
                        "k0_handle.attach: K0 reachable at %s (version=%s)",
                        self.base_url,
                        payload.get("version"),
                    )
                    return
            except (httpx.HTTPError, ValueError) as exc:
                last_err = exc
            time.sleep(0.25)
        raise K0NotReachableError(
            f"K0 healthz at {self.base_url}/healthz did not return ok within "
            f"{deadline_s:.1f}s. Make sure the Docker stack is up. Last error: {last_err!r}"
        )


class NotSupportedInAttachMode(RuntimeError):
    """Raised when an operation requires spawn-mode K0."""
