"""
TestModelHubBridge -- IModelHubPort backed by TestConciergeAdapter
===================================================================

Convenience wrapper: creates a ModelHubPOCBridge around a
TestConciergeAdapter so tests can configure deterministic responses
using the familiar set_response(actor, scenario, ...) API while
callers use K1 HubRequest / HubResponse types.

Usage:
    bridge = TestModelHubBridge()
    bridge.set_response("front", "user_input", ConciergeModelResponse(...))
    resp = await bridge.execute(hub_request)
"""

from __future__ import annotations

from k1.concierge.llm.model_hub_bridge import ModelHubPOCBridge
from k1.concierge.llm.test_adapter import TestConciergeAdapter
from k1.concierge.llm.types import ConciergeModelResponse


class TestModelHubBridge(ModelHubPOCBridge):
    """IModelHubPort for tests. Wraps TestConciergeAdapter.

    Exposes the inner adapter's configuration API so tests can
    set deterministic responses keyed by (actor, scenario).
    """

    def __init__(self) -> None:
        self._test_adapter = TestConciergeAdapter()
        super().__init__(inner=self._test_adapter)

    @property
    def inner(self) -> TestConciergeAdapter:
        """Access the underlying TestConciergeAdapter for configuration."""
        return self._test_adapter

    # ------------------------------------------------------------------
    # Pass-through configuration API
    # ------------------------------------------------------------------

    def set_response(
        self,
        actor: str,
        scenario: str,
        response: ConciergeModelResponse,
    ) -> None:
        """Set a fixed POC response for (actor, scenario)."""
        self._test_adapter.set_response(actor, scenario, response)

    def set_response_sequence(
        self,
        actor: str,
        scenario: str,
        responses: list[ConciergeModelResponse],
    ) -> None:
        """Set a sequence of POC responses for (actor, scenario)."""
        self._test_adapter.set_response_sequence(actor, scenario, responses)

    def set_default_response(self, response: ConciergeModelResponse) -> None:
        """Set fallback POC response."""
        self._test_adapter.set_default_response(response)

    # ------------------------------------------------------------------
    # Assertion pass-throughs
    # ------------------------------------------------------------------

    @property
    def call_count(self) -> int:
        return self._test_adapter.call_count

    def reset(self) -> None:
        self._test_adapter.reset()
