"""
k1.concierge.adapters.hub_llm -- Production adapter for ILLMPort.

Re-exports ModelHubPOCBridge from its canonical location so all
production adapters live under k1.concierge.adapters.
"""

from __future__ import annotations

from k1.concierge.llm.model_hub_bridge import ModelHubPOCBridge

__all__ = ["ModelHubPOCBridge"]
