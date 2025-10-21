"""ASGI entrypoint and runtime harness for the K0 kernel."""

from __future__ import annotations

import logging
import signal
from contextlib import contextmanager
from types import FrameType
from typing import Any, Iterator, Sequence

import uvicorn
from fastapi import FastAPI

from ..obs import configure_structured_logging
from .app import create_app
from .config import KernelSettings

logger = logging.getLogger(__name__)

__all__ = ["build_uvicorn_config", "install_signal_handlers", "run"]

DEFAULT_SIGNALS: tuple[int, ...] = (signal.SIGTERM, signal.SIGINT)


def run(
    settings: KernelSettings | None = None,
    *,
    host: str | None = None,
    port: int | None = None,
    log_level: str | None = None,
    timeout_graceful_shutdown: float | None = None,
) -> None:
    """Launch the kernel using Uvicorn with graceful shutdown semantics."""

    settings = settings or KernelSettings.default()

    telemetry_settings = settings.telemetry
    server_settings = settings.server
    resolved_host = host or server_settings.host
    resolved_port = port or server_settings.port
    resolved_log_level = (log_level or server_settings.log_level).lower()
    resolved_timeout = (
        timeout_graceful_shutdown
        if timeout_graceful_shutdown is not None
        else server_settings.timeout_graceful_shutdown
    )

    config = build_uvicorn_config(
        settings=settings,
        host=resolved_host,
        port=resolved_port,
        log_level=resolved_log_level,
        timeout_graceful_shutdown=resolved_timeout,
    )
    server = uvicorn.Server(config)

    configure_structured_logging(
        level=resolved_log_level,
        sensitive_keys=telemetry_settings.log_sensitive_keys,
        mask=telemetry_settings.log_mask,
        force=True,
    )

    logger.info(
        "Starting K0 kernel on %s:%s (graceful timeout %.1fs, log level %s)",
        resolved_host,
        resolved_port,
        resolved_timeout,
        resolved_log_level,
    )

    with install_signal_handlers(server, DEFAULT_SIGNALS):
        try:
            server.run()
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received; shutting down kernel.")
        except Exception:
            logger.exception("Kernel server terminated due to unexpected error")
            raise
        finally:
            logger.info("K0 kernel shutdown complete.")


def build_uvicorn_config(
    *,
    settings: KernelSettings,
    host: str,
    port: int,
    log_level: str,
    timeout_graceful_shutdown: float,
) -> uvicorn.Config:
    """Construct a Uvicorn configuration bound to the provided settings."""

    def _app_factory() -> FastAPI:
        return create_app(settings=settings)

    return uvicorn.Config(
        _app_factory,
        host=host,
        port=port,
        log_level=log_level,
        factory=True,
        lifespan="on",
        timeout_graceful_shutdown=int(round(timeout_graceful_shutdown)),
        server_header=False,
        date_header=False,
    )


@contextmanager
def install_signal_handlers(
    server: uvicorn.Server,
    signals_to_handle: Sequence[int],
) -> Iterator[None]:
    """Temporarily install signal handlers that delegate to Uvicorn."""

    previous: dict[int, Any] = {}

    def _handle(signum: int, frame: FrameType | None) -> None:
        try:
            signal_name = signal.Signals(signum).name
        except ValueError:
            signal_name = str(signum)
        logger.info("Received %s signal; initiating graceful shutdown", signal_name)
        server.handle_exit(signum, frame)

    try:
        for sig in signals_to_handle:
            previous[sig] = signal.getsignal(sig)
            signal.signal(sig, _handle)
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":  # pragma: no cover
    run()
