from __future__ import annotations

from typing import List, Tuple

from ward import test  # type: ignore[attr-defined]

from k0.cli.k0ctl import ServeOptions, main
from k0.kernel.config import KernelSettings


@test("serve command delegates to provided runner with resolved options")
def _() -> None:
    calls: List[Tuple[KernelSettings, ServeOptions]] = []

    def runner(settings: KernelSettings, options: ServeOptions) -> int:
        calls.append((settings, options))
        return 0

    exit_code = main(
        [
            "--set",
            "server.port=9011",
            "--set",
            "telemetry.prometheus_enabled=false",
            "--set",
            "retention.default.wal_days=3",
            "serve",
            "--host",
            "127.0.0.2",
            "--log-level",
            "debug",
            "--graceful-timeout",
            "15",
        ],
        serve_runner=runner,
    )

    assert exit_code == 0
    assert len(calls) == 1
    kernel_settings, options = calls[0]
    assert isinstance(kernel_settings, KernelSettings)
    assert kernel_settings.server.port == 9011
    assert kernel_settings.telemetry.prometheus_enabled is False
    assert kernel_settings.retention.default.wal_days == 3
    assert options.host == "127.0.0.2"
    assert options.port == 9011
    assert options.log_level == "debug"
    assert options.timeout_graceful_shutdown == 15.0


@test("unimplemented commands return error exit code")
def _() -> None:
    exit_code = main(["schema"])
    assert exit_code != 0
