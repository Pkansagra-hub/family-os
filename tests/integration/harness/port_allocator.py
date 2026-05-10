"""Ephemeral-port allocator for the live-system harness.

Binds to ``("127.0.0.1", 0)`` and immediately releases, returning the
kernel-assigned port. Has a small race window between release and reuse;
acceptable for tests because we also track ports in
:class:`leak_detector.LeakDetector` and surface bind failures loudly when
they occur.
"""

from __future__ import annotations

import socket


def allocate_free_port(host: str = "127.0.0.1") -> int:
    """Return an OS-assigned free TCP port on ``host``.

    Note: the port may be claimed by another process between the moment
    this function returns and the caller binds to it. In practice this
    is rare on a quiet test host, and the harness verifies port
    ownership downstream when health-checking spawned processes.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, 0))
        return sock.getsockname()[1]
