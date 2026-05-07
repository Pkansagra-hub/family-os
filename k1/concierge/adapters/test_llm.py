"""
k1.concierge.adapters.test_llm -- Test adapter for ILLMPort.

Re-exports TestModelHubBridge from its canonical location so all test
adapters live under k1.concierge.adapters.
"""

from __future__ import annotations

from k1.concierge.llm.test_model_hub_bridge import TestModelHubBridge

__all__ = ["TestModelHubBridge"]
