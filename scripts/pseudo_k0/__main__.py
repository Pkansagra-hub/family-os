"""Pseudo-K0 entry point.

Usage::

    python -m scripts.pseudo_k0 --port 8090 --db data/pseudo_k0.db
    python -m scripts.pseudo_k0 --check                  # smoke test

The server binds the FastAPI app from :mod:`scripts.pseudo_k0.server`
to a fresh :class:`SQLiteK0Store` and runs uvicorn until interrupted.
"""

from __future__ import annotations

import argparse
import logging

from scripts.pseudo_k0.store import SQLiteK0Store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scripts.pseudo_k0")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument(
        "--db",
        type=str,
        default="data/pseudo_k0.db",
        help="SQLite path for WAL + obs_log (':memory:' for ephemeral).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Open the store, print row counts, and exit (no server).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    store = SQLiteK0Store(args.db)
    wal, obs = store.counts()
    print(f"pseudo-K0: db={args.db} wal_rows={wal} obs_rows={obs}")

    if args.check:
        store.close()
        return 0

    from scripts.pseudo_k0.server import create_app  # noqa: PLC0415

    app = create_app(store)
    print(f"pseudo-K0: serving on http://{args.host}:{args.port}")
    print("  POST /k0/command.submit   (recall.request.v1, memory.write.*, connector.execute.*)")
    print("  POST /k0/obs.emit         ({kind, body})")
    print("  GET  /k0/sse/{topic}      (SSE heartbeat)")
    print("  GET  /healthz")

    try:
        import uvicorn  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        print(f"pseudo-K0: uvicorn not installed: {exc}")
        store.close()
        return 1

    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level.lower())
    finally:
        store.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
