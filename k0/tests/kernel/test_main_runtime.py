from __future__ import annotations

import signal
from types import FrameType
from typing import Any, Callable, cast

import uvicorn
from ward import test  # type: ignore[attr-defined]

from k0.kernel.config import KernelSettings
from k0.kernel.main import build_uvicorn_config, install_signal_handlers


class _StubServer:
    def __init__(self) -> None:
        self.handled: list[int] = []

    def handle_exit(self, signum: int, frame: FrameType | None) -> None:  # pragma: no cover - signature compatibility
        self.handled.append(signum)


@test("uvicorn config reflects resolved server settings")
def _() -> None:
    settings = KernelSettings.load(
        overrides={
            "server": {
                "host": "127.0.0.1",
                "port": 9100,
                "log_level": "debug",
                "timeout_graceful_shutdown": 12.5,
            }
        }
    )

    config = build_uvicorn_config(
        settings=settings,
        host=settings.server.host,
        port=settings.server.port,
        log_level=settings.server.log_level,
        timeout_graceful_shutdown=settings.server.timeout_graceful_shutdown,
    )

    assert config.host == "127.0.0.1"
    assert config.port == 9100
    assert config.log_level == "debug"
    assert config.factory is True
    assert config.lifespan == "on"
    assert config.server_header is False
    assert config.date_header is False
    assert config.timeout_graceful_shutdown == int(
        round(settings.server.timeout_graceful_shutdown)
    )


@test("signal handlers forward exit signals and restore originals")
def _() -> None:
    stub = _StubServer()
    original_handler = signal.getsignal(signal.SIGINT)

    with install_signal_handlers(cast(uvicorn.Server, stub), (signal.SIGINT,)):
        active_handler = signal.getsignal(signal.SIGINT)
        assert active_handler is not original_handler

        callable_handler = cast(Callable[[int, Any], Any], active_handler)
        assert callable(callable_handler)
        callable_handler(signal.SIGINT, None)

    assert signal.getsignal(signal.SIGINT) is original_handler
    assert stub.handled == [signal.SIGINT]
