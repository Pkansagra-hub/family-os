"""
K1 Concierge Chat REPL -- boot the production kernel and chat with it.

Usage:
    python -m k1.kernel.chat_repl               # test mode (canned "OK")
    python -m k1.kernel.chat_repl --model-hub   # production Model Hub + Gemini

The REPL boots the kernel with the requested model_mode via KernelConfig.
No post-boot mutation of runtime.model.

--model-hub    Uses ModelHubFactory.create_standalone() + GooglePlugin.
               Requires GOOGLE_API_KEY env var.
(default)      TestModelHubBridge (canned "OK" responses, no key needed).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time

from k1.concierge.bus.builders import build_user_input
from k1.concierge.bus.topics import TOPIC_FINAL_RESPONSE, TOPIC_RESPONSE_STREAM
from k1.kernel.bootstrap import KernelConfig, KernelRuntime, start_kernel, stop_kernel

logger = logging.getLogger(__name__)

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


async def chat_repl() -> None:
    """Boot K1 Concierge kernel and run an interactive chat loop."""

    # ── Parse args ────────────────────────────────────────────────────
    use_model_hub = "--model-hub" in sys.argv

    log_level = "WARNING"
    for arg in sys.argv:
        if arg.startswith("--log-level="):
            log_level = arg.split("=", 1)[1]

    logging.basicConfig(
        level=getattr(logging, log_level, logging.WARNING),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # ── Determine mode label ──────────────────────────────────────────
    llm_provider = _selected_llm_provider()
    if use_model_hub:
        mode_label = f"Production Model Hub + {llm_provider}"
        model_mode = "hub"
    else:
        mode_label = "TestModelHubBridge (canned)"
        model_mode = "test"

    # ── Validate early ─────────────────────────────────────────────
    if use_model_hub:
        if llm_provider in _VERTEX_PROVIDER_IDS:
            project, _location = _configure_vertex_env_aliases()
            if not project:
                print(
                    "ERROR: LLM_PROVIDER=vertex requires GOOGLE_CLOUD_PROJECT or GOOGLE_PROJECT_ID."
                )
                print("Set it and retry, or omit --model-hub for test mode.")
                return
            if not os.environ.get("GOOGLE_API_KEY") and not _has_adc_credentials():
                print("ERROR: LLM_PROVIDER=vertex requires GOOGLE_API_KEY or ADC credentials.")
                print("Run: gcloud auth application-default login")
                print("Or omit --model-hub for test mode.")
                return
        elif llm_provider in _GOOGLE_PROVIDER_IDS:
            api_key = os.environ.get("GOOGLE_API_KEY", "")
            if not api_key:
                print("ERROR: LLM_PROVIDER=google requires GOOGLE_API_KEY env var.")
                print(
                    "Set it and retry, set LLM_PROVIDER=vertex for Google Cloud billing, or omit --model-hub for test mode."
                )
                return
        else:
            print(f"ERROR: unsupported LLM_PROVIDER={llm_provider!r}. Supported: google, vertex.")
            return

    # ── Boot kernel with correct model_mode ───────────────────────────
    print("=" * 58)
    print("  K1 Concierge Chat REPL (Production Path)")
    print("=" * 58)
    print(f"  Mode: {mode_label}")
    if use_model_hub:
        print(f"  LLM provider: {llm_provider}")
    print("  Booting kernel...")

    cfg = KernelConfig(model_mode=model_mode)
    t0 = time.monotonic()
    runtime: KernelRuntime = await start_kernel(cfg)

    elapsed = time.monotonic() - t0
    print(f"  Kernel ready in {elapsed:.2f}s")
    print("  Type a message and press Enter. Type 'quit' to exit.")
    print("=" * 58)
    print()

    # ── Wire response capture ─────────────────────────────────────────
    response_queue: asyncio.Queue[str] = asyncio.Queue()
    stream_buffer: list[str] = []

    def _on_final_response(envelope) -> None:
        """Capture final_response from bus."""
        try:
            payload = (
                json.loads(envelope.payload)
                if isinstance(envelope.payload, (bytes, bytearray))
                else envelope.payload
            )
        except (json.JSONDecodeError, TypeError):
            payload = {"text": str(envelope.payload)}
        text = payload.get("text", "") if isinstance(payload, dict) else str(payload)
        response_queue.put_nowait(text)

    def _on_stream_chunk(envelope) -> None:
        """Capture stream chunks for live display."""
        try:
            payload = (
                json.loads(envelope.payload)
                if isinstance(envelope.payload, (bytes, bytearray))
                else envelope.payload
            )
        except (json.JSONDecodeError, TypeError):
            payload = {}
        if isinstance(payload, dict):
            chunk_text = payload.get("text", "")
            chunk_type = payload.get("chunk_type", "text")
            if chunk_text and chunk_type == "text":
                stream_buffer.append(chunk_text)
                print(chunk_text, end="", flush=True)

    bus = runtime.bus
    sub_final = bus.subscribe(TOPIC_FINAL_RESPONSE, _on_final_response)
    sub_stream = bus.subscribe(TOPIC_RESPONSE_STREAM, _on_stream_chunk)

    # ── Chat loop ─────────────────────────────────────────────────────
    turn = 0
    try:
        while True:
            try:
                user_text = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input("\n🧑 You: ")
                )
            except (EOFError, KeyboardInterrupt):
                break

            user_text = user_text.strip()
            if not user_text:
                continue
            if user_text.lower() in ("quit", "exit", "q"):
                break

            turn += 1
            stream_buffer.clear()

            # Publish user input to bus
            env = build_user_input({"text": user_text})
            bus.publish(env)

            # Wait for the final response (with timeout)
            print("\n🤖 Concierge: ", end="", flush=True)

            try:
                final_text = await asyncio.wait_for(response_queue.get(), timeout=30.0)
                # If we had stream chunks, they were already printed.
                # Print final text only if no stream chunks came through.
                if not stream_buffer:
                    print(final_text)
                else:
                    print()  # newline after stream
            except asyncio.TimeoutError:
                print("[timeout -- no response in 30s]")

            # Show FSM state for debugging
            try:
                state = runtime.fsm.state.name
                print(f"   📊 FSM state: {state} | turn: {turn}")
            except Exception:
                pass

    finally:
        # ── Cleanup ───────────────────────────────────────────────────
        print("\n\nShutting down kernel...")
        try:
            bus.unsubscribe(sub_final)
            bus.unsubscribe(sub_stream)
        except Exception:
            pass
        await stop_kernel(runtime)
        print("Kernel stopped. Bye!")


if __name__ == "__main__":
    asyncio.run(chat_repl())
