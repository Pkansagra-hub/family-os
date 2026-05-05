"""Test-only scripted LLM provider plugin.

A real ``IProviderPlugin`` implementation (not a mock) that returns
deterministic ``ProviderResponse`` instances chosen by predicates over
the inbound ``NormalizedRequest``.  Used by integration tests that need
to drive the Concierge ReAct loop through specific tool-call sequences
without making real LLM calls.

Wiring helper ``install_scripted_plugin(kernel_service)`` swaps the
already-registered ``StubProviderPlugin`` for a fresh
``ScriptedProviderPlugin`` under the same provider/model id, so
ModelHub routing decisions remain unchanged.

Not for production. Lives in ``tests/`` and is never imported by k1.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable

from k1.kernel.service import KernelService
from k1.model_hub.manifest import ProviderManifest
from k1.model_hub.plugins.base import (
    NormalizedRequest,
    ProviderChunk,
    ProviderHealth,
    ProviderResponse,
)
from k1.model_hub.plugins.stub_plugin import build_stub_manifest
from k1.model_hub.types import (
    CapabilityType,
    FinishReason,
    HealthStatus,
    ToolCallResult,
)


@dataclass
class ScriptedRule:
    """One rule in the scripted plugin's queue.

    ``predicate`` decides which incoming request this rule answers.
    Default predicate matches any request.

    ``response`` is what the plugin returns when the rule fires.
    """

    response: ProviderResponse
    predicate: Callable[[NormalizedRequest], bool] = field(default=lambda req: True)
    label: str = ""
    fired: int = field(default=0, init=False)


def _make_tool_call(
    name: str, arguments: dict[str, Any], call_id: str | None = None
) -> ToolCallResult:
    return ToolCallResult(
        id=call_id or f"call-{name}-0",
        name=name,
        arguments=json.dumps(arguments, separators=(",", ":")),
    )


def make_text_response(text: str = "OK") -> ProviderResponse:
    """Helper: build a plain text ProviderResponse with FinishReason.STOP."""
    return ProviderResponse(
        text=text,
        tool_calls=None,
        prompt_tokens=10,
        completion_tokens=2,
        model_id="stub-canned-v1",
        finish_reason=FinishReason.STOP,
    )


def make_tool_call_response(
    *tool_calls: tuple[str, dict[str, Any]],
    text: str = "",
) -> ProviderResponse:
    """Helper: build a ProviderResponse carrying one or more tool calls."""
    tcs = [
        _make_tool_call(name, args, call_id=f"call-{i}")
        for i, (name, args) in enumerate(tool_calls)
    ]
    return ProviderResponse(
        text=text,
        tool_calls=tcs,
        prompt_tokens=10,
        completion_tokens=4,
        model_id="stub-canned-v1",
        finish_reason=FinishReason.TOOL_CALLS,
    )


class ScriptedProviderPlugin:
    """Real plugin (not a mock) returning queued canned responses.

    Behaviour:
      * On each ``execute()`` call, walk ``rules`` left-to-right and
        return the first rule whose ``predicate`` matches AND has
        ``fired == 0``.  Increment ``fired`` on the chosen rule.
      * If no rule matches, fall back to ``default_response`` (defaults
        to plain text ``"OK"``).
      * All inbound ``NormalizedRequest`` objects are recorded in
        ``calls`` for assertions.

    Thread-safe: a single ``RLock`` guards rule selection + recording.
    """

    def __init__(
        self,
        rules: list[ScriptedRule] | None = None,
        default_response: ProviderResponse | None = None,
    ) -> None:
        self.rules: list[ScriptedRule] = list(rules or [])
        self.default_response: ProviderResponse = (
            default_response if default_response is not None else make_text_response("OK")
        )
        self.calls: list[NormalizedRequest] = []
        self._lock = threading.RLock()

    # -- scripting API ----------------------------------------------------

    def queue(
        self,
        response: ProviderResponse,
        *,
        predicate: Callable[[NormalizedRequest], bool] | None = None,
        label: str = "",
    ) -> ScriptedRule:
        rule = ScriptedRule(
            response=response,
            predicate=predicate or (lambda _req: True),
            label=label,
        )
        with self._lock:
            self.rules.append(rule)
        return rule

    def reset(self) -> None:
        with self._lock:
            self.rules.clear()
            self.calls.clear()

    # -- IProviderPlugin protocol ----------------------------------------

    async def initialize(self, manifest: ProviderManifest) -> None:
        return None

    def supports(self, capability: CapabilityType) -> bool:
        return True

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        with self._lock:
            self.calls.append(request)
            chosen: ScriptedRule | None = None
            for rule in self.rules:
                if rule.fired:
                    continue
                try:
                    if rule.predicate(request):
                        chosen = rule
                        break
                except Exception:
                    continue
            if chosen is None:
                return self.default_response
            chosen.fired += 1
            return chosen.response

    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]:
        resp = await self.execute(request)
        yield ProviderChunk(
            text=resp.text,
            done=True,
            tool_calls=resp.tool_calls,
        )

    def estimate_tokens(self, messages: Any) -> int:
        if isinstance(messages, str):
            return max(1, len(messages.split()))
        if isinstance(messages, list):
            total = 0
            for m in messages:
                content = getattr(m, "content", None) or (
                    m.get("content") if isinstance(m, dict) else ""
                )
                if isinstance(content, str):
                    total += max(1, len(content.split()))
            return max(1, total)
        return 1

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(status=HealthStatus.HEALTHY, latency_ms=0)

    async def close(self) -> None:
        return None


async def install_scripted_plugin(
    kernel_service: KernelService,
) -> ScriptedProviderPlugin:
    """Swap the kernel's ``StubProviderPlugin`` for a fresh ``ScriptedProviderPlugin``.

    Reuses the stub's manifest (provider_id="stub", model_id="stub-canned-v1")
    so all routing decisions remain valid.  Returns the scripted plugin so
    tests can ``queue(...)`` rules and inspect ``calls``.

    Must be called AFTER ``KernelService.startup()``.
    """
    hub = kernel_service._model_hub
    if hub is None:
        raise RuntimeError(
            "install_scripted_plugin: kernel ModelHub is None — startup() not called?"
        )

    manifest = build_stub_manifest()
    plugin = ScriptedProviderPlugin()
    await plugin.initialize(manifest)

    registry = hub._registry  # type: ignore[attr-defined]
    dispatcher = hub._router._dispatcher  # type: ignore[attr-defined]

    # Unregister the stub if present, then register the scripted plugin
    # under the same provider_id so routing tables are unchanged.
    try:
        registry.unregister(manifest.provider_id)
    except Exception:
        pass
    registry.register(manifest, plugin)
    dispatcher.register_plugin(manifest.provider_id, plugin)

    return plugin
