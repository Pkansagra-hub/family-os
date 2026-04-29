"""P2.2 -- Live end-to-end test for ModelHubFactory.from_config.

Skipped automatically when GOOGLE_API_KEY is not set. When set, the test:

  1. Builds a real production-shaped hub via ModelHubFactory.from_config
     using ProviderConfig.default() (env-var-gated cloud providers only).
  2. Asserts "google" is in result.registered.
  3. Executes one real Gemini chat call directly through the registered
     plugin (mirrors test_loader_live.py to prove from_config wires the
     loader the same way the loader-direct path does).
  4. Calls hub.shutdown() and verifies no exception.

This is the production-path-equivalent of test_loader_live.py.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Load .env so the test can run standalone without boot_kernel.ps1.
_ENV_FILE = Path(__file__).resolve().parents[3] / "poc" / "chat_experience_poc" / ".env"
if not os.environ.get("GOOGLE_API_KEY") and _ENV_FILE.exists():
    for line in _ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line.startswith("GOOGLE_API_KEY="):
            val = line.split("=", 1)[1].strip().strip('"').strip("'")
            os.environ["GOOGLE_API_KEY"] = val
            break

_HAS_KEY = bool(os.environ.get("GOOGLE_API_KEY"))
pytestmark = pytest.mark.skipif(not _HAS_KEY, reason="GOOGLE_API_KEY not set")

from k1.model_hub.factory import ModelHubFactory
from k1.model_hub.loader import ProviderConfig
from k1.model_hub.plugins.base import NormalizedRequest, ProviderResponse
from k1.model_hub.types import CapabilityType, FinishReason, Message


@pytest.mark.asyncio
async def test_from_config_default_registers_google_and_shuts_down() -> None:
    hub, result = await ModelHubFactory.from_config(
        ProviderConfig.default(),
        ports=None,  # uses create_standalone path
    )

    print(
        f"\n[from_config-live] registered={result.registered} "
        f"skipped={result.skipped} failed={result.failed}"
    )

    assert "google" in result.registered, (
        f"Expected 'google' in registered, got registered={result.registered} "
        f"skipped={result.skipped} failed={result.failed}"
    )

    # Pull the registered plugin and exercise one real Gemini call to
    # prove from_config wired the loader correctly.
    plugin = hub._registry.get_plugin("google")
    req = NormalizedRequest(
        capability=CapabilityType.CHAT,
        messages=[Message(role="user", content="Reply with the single word: pong")],
        system_prompt=None,
        tools=None,
        tool_choice=None,
        max_tokens=32,
        temperature=0.0,
        model_id="gemini-2.5-flash",
        trace_id="from-config-live-test",
        consumer_id="p2.2-from-config-live",
        reasoning_effort=None,
        extra={},
    )
    resp = await plugin.execute(req)
    assert isinstance(resp, ProviderResponse)
    assert resp.text, "expected non-empty text from Gemini"
    assert resp.finish_reason == FinishReason.STOP
    print(
        f"[from_config-live] gemini reply={resp.text!r} "
        f"in={resp.prompt_tokens} out={resp.completion_tokens}"
    )

    # Drain plugin sessions; must not raise.
    await hub.shutdown()
    print("[from_config-live] hub.shutdown() OK")
