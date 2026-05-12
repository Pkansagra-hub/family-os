"""Process supervisor for the live-system harness.

Spawns subprocesses with a SIGTERM → grace-period → SIGKILL shutdown
policy. Cross-platform: on Windows we use ``CTRL_BREAK_EVENT`` for
graceful shutdown and ``Process.kill`` as the hard fallback.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

logger = logging.getLogger(__name__)

DEFAULT_GRACE_SECONDS = 10.0


@dataclass
class ProcessHandle:
    name: str
    proc: subprocess.Popen
    cwd: Path
    log_path: Path | None = None

    @property
    def pid(self) -> int:
        return self.proc.pid

    @property
    def returncode(self) -> int | None:
        return self.proc.returncode

    def is_alive(self) -> bool:
        return self.proc.poll() is None


class ProcessSupervisor:
    """Spawn and shut down subprocesses with a graceful policy.

    All spawned processes are tracked; :meth:`shutdown_all` issues
    SIGTERM (or ``CTRL_BREAK_EVENT`` on Windows), waits up to
    ``grace_seconds``, then SIGKILLs any survivors.
    """

    def __init__(self, *, grace_seconds: float = DEFAULT_GRACE_SECONDS) -> None:
        self._grace = grace_seconds
        self._handles: list[ProcessHandle] = []

    def spawn(
        self,
        name: str,
        argv: list[str],
        *,
        cwd: Path | str,
        env: Mapping[str, str] | None = None,
        log_path: Path | str | None = None,
    ) -> ProcessHandle:
        cwd_path = Path(cwd)
        log_p = Path(log_path) if log_path is not None else None
        stdout_target: int | object
        stderr_target: int | object
        log_handle = None
        if log_p is not None:
            log_p.parent.mkdir(parents=True, exist_ok=True)
            log_handle = log_p.open("ab")
            stdout_target = log_handle
            stderr_target = subprocess.STDOUT
        else:
            stdout_target = subprocess.PIPE
            stderr_target = subprocess.PIPE

        creationflags = 0
        if sys.platform == "win32":  # enable CTRL_BREAK_EVENT later
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

        full_env = dict(os.environ)
        if env is not None:
            full_env.update(env)

        logger.info("supervisor.spawn name=%s argv=%s cwd=%s", name, argv, cwd_path)
        proc = subprocess.Popen(  # noqa: S603 - argv is constructed by the harness
            argv,
            cwd=str(cwd_path),
            env=full_env,
            stdout=stdout_target,
            stderr=stderr_target,
            creationflags=creationflags,
        )
        # Detach the log file handle from this scope; the OS keeps it open
        # for the child. We do not close it here — leak is bounded to the
        # process lifetime and reaped by the OS at child exit.
        del log_handle
        handle = ProcessHandle(name=name, proc=proc, cwd=cwd_path, log_path=log_p)
        self._handles.append(handle)
        return handle

    def terminate(self, handle: ProcessHandle, *, grace_seconds: float | None = None) -> int | None:
        """Gracefully terminate a single handle. Returns final returncode."""
        grace = grace_seconds if grace_seconds is not None else self._grace
        if not handle.is_alive():
            return handle.returncode

        try:
            if sys.platform == "win32":
                handle.proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                handle.proc.terminate()
        except (OSError, ValueError) as exc:  # process may have died
            logger.debug("supervisor.terminate name=%s soft-signal failed: %s", handle.name, exc)

        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            if not handle.is_alive():
                return handle.returncode
            time.sleep(0.1)

        logger.warning("supervisor.kill name=%s pid=%s grace expired", handle.name, handle.pid)
        try:
            handle.proc.kill()
        except OSError:
            pass
        try:
            handle.proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            logger.error("supervisor.kill name=%s pid=%s did not exit", handle.name, handle.pid)
        return handle.returncode

    def shutdown_all(self) -> list[tuple[str, int | None]]:
        results: list[tuple[str, int | None]] = []
        for h in list(self._handles):
            rc = self.terminate(h)
            results.append((h.name, rc))
        return results

    @property
    def handles(self) -> list[ProcessHandle]:
        return list(self._handles)
