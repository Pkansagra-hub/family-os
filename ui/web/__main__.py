"""ui.web.__main__ — uvicorn CLI entry-point for the K1 web UI.

Usage::

    python -m ui.web [--port 8765] [--host 127.0.0.1] [--test-mode]
                     [--log-level DEBUG|INFO|WARNING]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

# Python 3.13 on Windows: ProactorEventLoop (IOCP) has broken task-context
# tracking that corrupts SSL/shutdown for aiohttp, httpx, and httpcore.
# SelectorEventLoop avoids this entirely.
if sys.platform == "win32":
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Python 3.13 strict task-context tracking raises RuntimeError when
# aiohttp connection cleanup callbacks run in a different task context
# than WebSocket broadcasts. These are harmless — tasks still complete.
# Filter them at the event-loop level so real errors stay visible.
_py313_original_new_event_loop = asyncio.get_event_loop_policy().new_event_loop


def _py313_patched_new_event_loop(policy_self):
    loop = _py313_original_new_event_loop(policy_self)
    if sys.platform == "win32":
        original_handler = loop.get_exception_handler()

        def _filter(loop_ctx, context):
            exc = context.get("exception")
            if isinstance(exc, RuntimeError):
                s = str(exc)
                if "Cannot enter into task" in s or "does not match the current task" in s:
                    return
            if original_handler is not None:
                original_handler(loop_ctx, context)
            else:
                loop_ctx.default_exception_handler(context)

        loop.set_exception_handler(_filter)
    return loop


# Patch the policy class so all future event loops get the filter
_policy_cls = type(asyncio.get_event_loop_policy())
_policy_cls.new_event_loop = _py313_patched_new_event_loop

_VERTEX_PROVIDER_IDS = {
    "vertex",
    "vertex-ai",
    "vertex_ai",
    "agent-platform",
    "agent_platform",
    "gemini-enterprise",
    "gemini_enterprise",
    "google-cloud",
    "google_cloud",
}

_GOOGLE_PROVIDER_IDS = {
    "google",
    "gemini",
    "developer",
    "ai-studio",
    "ai_studio",
    "google-ai",
    "google_ai",
}
_DEEPSEEK_PROVIDER_IDS = {
    "deepseek",
    "deepseek-v4",
    "deepseek_v4",
}


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _selected_llm_provider() -> str:
    raw = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
    if raw:
        return raw
    if _truthy(os.environ.get("GOOGLE_GENAI_USE_VERTEXAI")):
        return "vertex"
    return "google"


def _configure_vertex_env_aliases() -> tuple[str, str]:
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
    if not os.environ.get("GOOGLE_CLOUD_PROJECT") and os.environ.get("GOOGLE_PROJECT_ID"):
        os.environ["GOOGLE_CLOUD_PROJECT"] = os.environ["GOOGLE_PROJECT_ID"]
    if not os.environ.get("GOOGLE_CLOUD_LOCATION") and os.environ.get("GOOGLE_LOCATION"):
        os.environ["GOOGLE_CLOUD_LOCATION"] = os.environ["GOOGLE_LOCATION"]
    return (
        os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
        os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
    )


def _has_adc_credentials() -> bool:
    try:
        import google.auth

        google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        return True
    except Exception:
        return False


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
        help="Force live ModelHub + Gemini (requires configured provider auth). "
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
    # Suppress high-frequency orchestrator dequeue polling spam
    logging.getLogger("k1.orchestrator.orchestration.orchestrator_service").setLevel(logging.INFO)

    # Derive model_mode: test_mode → "test", otherwise → "hub" (Gemini)
    if args.test_mode:
        model_mode = "test"
    else:
        model_mode = "hub"

    # Validate provider auth before booting uvicorn (fast fail)
    if model_mode == "hub":
        provider = _selected_llm_provider()
        if provider in _VERTEX_PROVIDER_IDS:
            project, location = _configure_vertex_env_aliases()
            if not project:
                print(
                    "ERROR: LLM_PROVIDER=vertex requires GOOGLE_CLOUD_PROJECT "
                    "or GOOGLE_PROJECT_ID.\n"
                    "  Set project/location and retry, or pass --test-mode for local stub mode."
                )
                raise SystemExit(1)
            if not os.environ.get("GOOGLE_API_KEY") and not _has_adc_credentials():
                print(
                    "ERROR: LLM_PROVIDER=vertex requires either GOOGLE_API_KEY "
                    "for Google Cloud API-key auth or ADC credentials.\n"
                    "  Run: gcloud auth application-default login\n"
                    "  Or pass --test-mode for local stub mode."
                )
                raise SystemExit(1)
            logging.getLogger(__name__).info(
                "LLM_PROVIDER=vertex -> Gemini Enterprise Agent Platform "
                "project=%s location=%s auth=%s",
                project,
                location,
                "api_key" if os.environ.get("GOOGLE_API_KEY") else "adc",
            )
        elif provider in _GOOGLE_PROVIDER_IDS:
            api_key = os.environ.get("GOOGLE_API_KEY", "")
            if not api_key:
                print(
                    "ERROR: LLM_PROVIDER=google requires GOOGLE_API_KEY env var.\n"
                    "  Set it and retry, set LLM_PROVIDER=vertex for Google Cloud billing, "
                    "or pass --test-mode for local stub mode."
                )
                raise SystemExit(1)
        elif provider in _DEEPSEEK_PROVIDER_IDS:
            api_key = os.environ.get("DEEPSEEK_API_KEY", "")
            if not api_key:
                print(
                    "ERROR: LLM_PROVIDER=deepseek requires DEEPSEEK_API_KEY env var.\n"
                    "  Set it and retry, or pass --test-mode for local stub mode."
                )
                raise SystemExit(1)
        else:
            print(
                f"ERROR: unsupported LLM_PROVIDER={provider!r}.\n"
                "  Supported production providers here: google, vertex, deepseek. "
                "Use --test-mode for local stub mode."
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
    if not args.test_mode:
        print(f"  LLM Provider: {_selected_llm_provider()}")
    print()

    uvicorn.run(
        app_module.app,
        host=args.host,
        port=args.port,
        log_level=args.log_level.lower(),
    )


if __name__ == "__main__":
    main()
