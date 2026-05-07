"""E8.M1.1 — End-to-end HIL integration test fixtures.

Provides:
  - ``kernel_config``: KernelConfig with isolated SQLite paths.
  - ``kernel_service``: real boot/shutdown of ``KernelService``.
  - ``HILUserSimulator`` + ``hil_user_simulator`` fixture.

The simulator subscribes to the SAME bus the kernel uses
(``kernel_service._bus``) on ``TOPIC_HIL_REQUEST`` and replies on
``TOPIC_HIL_RESPONSE`` with scripted payloads. No mocks: real bus,
real envelopes, real ``HumanInTheLoopService``.

Wire shape on both topics is the JSON-encoded ``HILEnvelope.to_dict()``
(request) / ``HILResponseEnvelope.to_dict()`` (response), exactly as
serialised by ``KernelHILEventAdapter``.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable

import pytest

from k1.bus.envelope.envelope import Envelope, Priority
from k1.concierge.config.kernel import KernelConfig
from k1.hil.topics import TOPIC_HIL_REQUEST, TOPIC_HIL_RESPONSE
from k1.hil.types import HILEnvelope, HILKind, HILResponseEnvelope
from k1.kernel.service import KernelService

ResponseFn = Callable[[HILEnvelope], dict[str, Any]]


def _now_ms() -> int:
    return int(time.time() * 1000)


class HILUserSimulator:
    """A scripted human responder.

    Subscribes synchronously to ``TOPIC_HIL_REQUEST`` on the kernel's
    bus. For each incoming HIL request:
      * Records the decoded ``HILEnvelope`` in ``received``.
      * Looks up a scripted handler keyed by ``HILKind``.
      * If a handler is registered, builds a ``HILResponseEnvelope``
        (echoing the same ``hil_request_id``) and publishes it back
        on ``TOPIC_HIL_RESPONSE``.
      * If no handler is registered, the request is captured but no
        response is sent — the service-side future will time out.
    """

    __slots__ = ("_bus", "_handle", "_lock", "_scripts", "received")

    def __init__(self, bus: Any) -> None:
        self._bus = bus
        self._handle: Any = None
        self._lock = threading.RLock()
        self._scripts: dict[HILKind, ResponseFn] = {}
        self.received: list[HILEnvelope] = []

    # -- scripting ----------------------------------------------------

    def script(self, kind: HILKind, response_payload_fn: ResponseFn) -> None:
        """Register a payload builder for ``kind``.

        ``response_payload_fn`` receives the inbound ``HILEnvelope`` and
        returns the dict that will become ``HILResponseEnvelope.payload``.
        """

        with self._lock:
            self._scripts[kind] = response_payload_fn

    def clear_scripts(self) -> None:
        with self._lock:
            self._scripts.clear()

    # -- lifecycle ----------------------------------------------------

    def start(self) -> None:
        if self._handle is not None:
            return
        self._handle = self._bus.subscribe(TOPIC_HIL_REQUEST, self._on_request)

    def stop(self) -> None:
        if self._handle is None:
            return
        try:
            self._bus.unsubscribe(self._handle)
        except Exception:
            pass
        self._handle = None

    # -- internals ----------------------------------------------------

    def _on_request(self, envelope: Any) -> None:
        try:
            data = json.loads(envelope.payload.decode("utf-8"))
            req_env = HILEnvelope.from_dict(data)
        except Exception:
            return

        with self._lock:
            self.received.append(req_env)
            handler = self._scripts.get(req_env.kind)

        if handler is None:
            return

        try:
            payload = handler(req_env)
        except Exception:
            return

        resp = HILResponseEnvelope(
            hil_request_id=req_env.hil_request_id,
            kind=req_env.kind,
            responded_at_ms=_now_ms(),
            payload=dict(payload),
            timed_out=False,
        )
        raw = json.dumps(resp.to_dict(), separators=(",", ":"), default=str).encode("utf-8")
        try:
            self._bus.publish(
                Envelope(
                    topic=TOPIC_HIL_RESPONSE,
                    payload=raw,
                    cognitive_trace_id=req_env.trace_id,
                    priority=Priority.INTERACTIVE,
                )
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def kernel_config(tmp_path) -> KernelConfig:
    return KernelConfig(
        sessionstate_db_path=str(tmp_path / "ssm.db"),
        workflow_db_path=str(tmp_path / "wf.db"),
        bridge_outbox_path=str(tmp_path / "bridge.db"),
    )


@pytest.fixture
async def kernel_service(kernel_config):
    svc = KernelService(config=kernel_config)
    await svc.startup()
    try:
        yield svc
    finally:
        await svc.shutdown()


@pytest.fixture
def hil_user_simulator(kernel_service):
    sim = HILUserSimulator(kernel_service._bus)
    sim.start()
    try:
        yield sim
    finally:
        sim.stop()
