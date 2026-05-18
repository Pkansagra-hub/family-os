"""Guarded live smoke test for Gemini Enterprise Agent Platform.

This test is opt-in because it makes a real Google Cloud billed request.

Run:
  $env:RUN_VERTEX_LIVE = "1"
  $env:LLM_PROVIDER = "vertex"
  $env:GOOGLE_CLOUD_PROJECT = "your-project"
  $env:GOOGLE_CLOUD_LOCATION = "us-central1"
  # optional: $env:GOOGLE_API_KEY = "..."; otherwise ADC is used
  pytest tests/k1/model_hub/test_vertex_live.py -v -s
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _project() -> str:
    return os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GOOGLE_PROJECT_ID", "")


def _location() -> str:
    return os.environ.get("GOOGLE_CLOUD_LOCATION") or os.environ.get("GOOGLE_LOCATION", "global")


def _has_adc() -> bool:
    try:
        import google.auth

        google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        return True
    except Exception:
        return False


_HAS_AUTH = bool(os.environ.get("GOOGLE_API_KEY")) or _has_adc()
pytestmark = pytest.mark.skipif(
    not _truthy(os.environ.get("RUN_VERTEX_LIVE")) or not _project() or not _HAS_AUTH,
    reason="Set RUN_VERTEX_LIVE=1, GOOGLE_CLOUD_PROJECT/GOOGLE_PROJECT_ID, and GOOGLE_API_KEY or ADC",
)

from k1.model_hub.manifest import load_manifest
from k1.model_hub.plugins.base import NormalizedRequest, ProviderResponse
from k1.model_hub.plugins.vertex_plugin import VertexPlugin
from k1.model_hub.types import CapabilityType, FinishReason, Message

MANIFEST_PATH = (
    Path(__file__).resolve().parents[3] / "k1" / "config" / "providers" / "vertex.manifest.yaml"
)
MODEL = os.environ.get("VERTEX_MODEL", "gemini-2.5-flash")


@pytest.mark.asyncio
async def test_vertex_agent_platform_chat_smoke() -> None:
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
    os.environ["GOOGLE_CLOUD_PROJECT"] = _project()
    os.environ["GOOGLE_CLOUD_LOCATION"] = _location()

    manifest = load_manifest(MANIFEST_PATH)
    plugin = VertexPlugin()
    await plugin.initialize(manifest)
    if os.environ.get("GOOGLE_API_KEY"):
        plugin.set_api_key(os.environ["GOOGLE_API_KEY"])

    req = NormalizedRequest(
        capability=CapabilityType.CHAT,
        messages=[Message(role="user", content="Reply with the single word: pong")],
        system_prompt=None,
        tools=None,
        tool_choice=None,
        max_tokens=32,
        temperature=0.0,
        model_id=MODEL,
        trace_id="vertex-live-test",
        consumer_id="vertex-live-smoke",
        reasoning_effort=None,
        extra={},
    )
    try:
        resp = await plugin.execute(req)
    finally:
        await plugin.close()

    assert isinstance(resp, ProviderResponse)
    assert resp.text, "expected non-empty text from Gemini Enterprise Agent Platform"
    assert resp.finish_reason == FinishReason.STOP
    print(
        f"[vertex-live] model={resp.model_id} reply={resp.text!r} "
        f"in={resp.prompt_tokens} out={resp.completion_tokens}"
    )
