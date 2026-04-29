"""P2.1 -- Live end-to-end test for ProviderLoader against real Gemini.

Skipped automatically when GOOGLE_API_KEY is not set. When set, the test:

  1. Builds a real _HubCore via ModelHubFactory.create_for_testing().
  2. Runs ProviderLoader.load(ProviderConfig.default()) against the
     production manifest dir (k1/config/providers/).
  3. Asserts that "google" is in result.registered.
  4. Pulls the registered GooglePlugin out of the registry and makes one
     real Gemini chat call to prove the wiring is live.

This is the replacement-equivalent of the P0.1 smoke test, scaled to the
declarative loader path.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Load .env the same way test_google_live.py does so this test can run
# standalone without requiring boot_kernel.ps1 to set GOOGLE_API_KEY.
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
from k1.model_hub.loader import ProviderConfig, ProviderLoader
from k1.model_hub.plugins.base import NormalizedRequest, ProviderResponse
from k1.model_hub.types import CapabilityType, FinishReason, Message


@pytest.mark.asyncio
async def test_default_config_registers_google_against_real_api() -> None:
    facade, _adapters = ModelHubFactory.create_for_testing()

    loader = ProviderLoader(facade)
    result = await loader.load(ProviderConfig.default())

    print(
        f"\n[loader-live] registered={result.registered} "
        f"skipped={result.skipped} failed={result.failed}"
    )

    # Google must be registered -- the env var is set (skipif gate above).
    assert "google" in result.registered, (
        f"Expected 'google' in registered, got registered={result.registered} "
        f"skipped={result.skipped} failed={result.failed}"
    )

    # Pull the registered plugin and exercise one real Gemini call to
    # prove end-to-end wiring (loader -> registry -> plugin -> live API).
    plugin = facade._registry.get_plugin("google")
    req = NormalizedRequest(
        capability=CapabilityType.CHAT,
        messages=[Message(role="user", content="Reply with the single word: pong")],
        system_prompt=None,
        tools=None,
        tool_choice=None,
        max_tokens=32,
        temperature=0.0,
        model_id="gemini-2.5-flash",
        trace_id="loader-live-test",
        consumer_id="p2.1-loader-live",
        reasoning_effort=None,
        extra={},
    )
    resp = await plugin.execute(req)
    assert isinstance(resp, ProviderResponse)
    assert resp.text, "expected non-empty text from Gemini"
    assert resp.finish_reason == FinishReason.STOP
    print(
        f"[loader-live] gemini reply={resp.text!r} "
        f"in={resp.prompt_tokens} out={resp.completion_tokens}"
    )

    await plugin.close()
