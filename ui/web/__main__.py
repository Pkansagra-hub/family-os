"""ui.web.__main__ — uvicorn CLI entry-point for the K1 web UI.

Usage::

    python -m ui.web [--port 8765] [--host 127.0.0.1] [--test-mode]
                     [--log-level DEBUG|INFO|WARNING]
"""

from __future__ import annotations

import argparse
import logging
import os


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ui.web",
        description="FamilyOS K1 Concierge — Web UI",
    )
    parser.add_argument("--port", type=int, default=8765, help="Port (default: 8765)")
    parser.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1)")
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Use the in-process test LLM adapter (no external API calls)",
    )
    parser.add_argument(
        "--model-hub",
        action="store_true",
        default=None,
        help="Force live ModelHub + Gemini (requires GOOGLE_API_KEY). "
        "Auto-enabled when --test-mode is not set.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Root logger level (default: INFO)",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # Derive model_mode: test_mode → "test", otherwise → "hub" (Gemini)
    if args.test_mode:
        model_mode = "test"
    else:
        model_mode = "hub"

    # Validate GOOGLE_API_KEY before booting uvicorn (fast fail)
    if model_mode == "hub":
        api_key = os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            print(
                "ERROR: Production mode requires GOOGLE_API_KEY env var.\n"
                "  Set it and retry, or pass --test-mode for local stub mode."
            )
            raise SystemExit(1)

    # Configure FastAPI module globals BEFORE uvicorn starts
    from ui.web import app as app_module

    app_module.configure(test_mode=args.test_mode, model_mode=model_mode)

    # M14: surface K0_ENDPOINT so operators see whether K1 is wired to a live K0.
    k0_endpoint = os.environ.get("K0_ENDPOINT", "")
    if k0_endpoint:
        logging.getLogger(__name__).info(
            "K0_ENDPOINT=%s → LiveBridgeAdapter will be used at S4", k0_endpoint
        )

    import uvicorn

    print("\n  FamilyOS K1 Concierge — Web UI")
    print(f"  Open http://{args.host}:{args.port} in your browser")
    print(f"  Mode: {'TEST' if args.test_mode else 'PRODUCTION'}")
    print()

    uvicorn.run(
        app_module.app,
        host=args.host,
        port=args.port,
        log_level=args.log_level.lower(),
    )


if __name__ == "__main__":
    main()
