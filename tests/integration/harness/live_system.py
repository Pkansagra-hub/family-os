"""Live-system orchestrator for the harness.

``LiveSystem`` is an async context manager that:

1. Attaches to the running Docker K0 (default mode for Epic 7.1).
2. Spawns one K1 subprocess per (person, device) in the
   :class:`FamilyLayout`.
3. Tracks all PIDs/ports/tempdirs in a :class:`LeakDetector`.
4. On exit, sends SIGTERM (Windows: ``CTRL_BREAK_EVENT``) with a grace
   period, then SIGKILL, and asserts no resources leaked.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import time
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .device_provisioner import ProvisionedSecrets, provision_family
from .family_layout import FamilyLayout, default_father_mother_kid_layout
from .k0_handle import DEFAULT_K0_BASE_URL, DEFAULT_K0_DB_URL, K0Handle
from .k1_handle import K1Handle, spawn_k1
from .leak_detector import LeakDetector
from .port_allocator import allocate_free_port
from .process_supervisor import DEFAULT_GRACE_SECONDS, ProcessSupervisor

logger = logging.getLogger(__name__)


@dataclass
class LiveSystem(AbstractAsyncContextManager):
    """Orchestrator for one live K0 + N K1 processes.

    Default behaviour matches the Epic 7.1 deployment shape:
    K0 is already running in Docker; only K1s are spawned locally.
    """

    family: FamilyLayout = field(default_factory=default_father_mother_kid_layout)
    spawn_k1_count: int | None = None
    k0_base_url: str = DEFAULT_K0_BASE_URL
    k0_db_url: str = DEFAULT_K0_DB_URL
    grace_seconds: float = DEFAULT_GRACE_SECONDS
    spawn_k0: bool = False  # not implemented in 7.1 — attach mode only

    # populated in __aenter__
    k0: K0Handle | None = field(default=None, init=False)
    k1s: list[K1Handle] = field(default_factory=list, init=False)
    secrets: ProvisionedSecrets | None = field(default=None, init=False)
    leak_detector: LeakDetector = field(default_factory=LeakDetector, init=False)
    supervisor: ProcessSupervisor | None = field(default=None, init=False)
    _root_tempdir: Path | None = field(default=None, init=False)

    async def __aenter__(self) -> "LiveSystem":
        if self.spawn_k0:
            raise NotImplementedError(
                "spawn_k0=True is deferred. Epic 7.1 supports attach mode only "
                "(K0 must already be running in Docker)."
            )
        self.supervisor = ProcessSupervisor(grace_seconds=self.grace_seconds)
        self.k0 = K0Handle.attach(base_url=self.k0_base_url, db_url=self.k0_db_url)

        # Provision every device in the family into K0's device ledger
        # so the kernel.gate accepts envelopes from these device_ids.
        self.secrets = provision_family(self.family)

        self._root_tempdir = Path(tempfile.mkdtemp(prefix="familyos-live-"))
        self.leak_detector.track_tempdir(self._root_tempdir)

        targets = list(self._person_device_pairs())
        for idx, (person, device) in enumerate(targets):
            port = allocate_free_port()
            workdir = self._root_tempdir / f"k1-{idx:02d}-{person.role}"
            handle = spawn_k1(
                person=person,
                device=device,
                family=self.family,
                supervisor=self.supervisor,
                workdir=workdir,
                k0_base_url=self.k0_base_url,
                test_api_port=port,
                hmac_secret=self.secrets.secret_for(device.device_id),
                signing_seed=self.secrets.signing_seed_for(device.device_id),
            )
            self.leak_detector.track_pid(handle.pid)
            self.leak_detector.track_port(port)
            self.k1s.append(handle)

        # Brief settle window — give the runners a moment to wire up.
        time.sleep(0.5)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        # Tear down any in-process bridge runtimes first so their async
        # tasks (health poller, SSE client) stop before we kill PIDs.
        for k1 in self.k1s:
            await k1.stop_bridge_runtime()

        if self.supervisor is not None:
            for k1 in self.k1s:
                self.leak_detector.untrack_port(k1.test_api_port)
            results = self.supervisor.shutdown_all()
            for name, rc in results:
                logger.info("live_system.shutdown name=%s rc=%s", name, rc)
            for k1 in self.k1s:
                self.leak_detector.untrack_pid(k1.pid)

        if self._root_tempdir is not None and self._root_tempdir.exists():
            shutil.rmtree(self._root_tempdir, ignore_errors=True)
            self.leak_detector.untrack_tempdir(self._root_tempdir)

        self.leak_detector.assert_clean()

    # -- iteration helpers ------------------------------------------------
    def _person_device_pairs(self) -> Iterable[tuple]:
        """Yield (person, device) pairs respecting ``spawn_k1_count``."""
        all_pairs = [(p, d) for p in self.family.people for d in p.devices]
        if self.spawn_k1_count is None:
            yield from all_pairs
        else:
            yield from all_pairs[: max(0, self.spawn_k1_count)]
