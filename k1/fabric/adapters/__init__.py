"""
k1.fabric.adapters -- Hexagonal adapter implementations for Fabric ports.

Production adapters connect to real infrastructure (SessionState, EventBus,
Bridge, Model Hub, etc.).  Test adapters are self-contained in-memory stubs
for standalone / testing modes.

Adapter catalog:
  SessionStateReaderAdapter (5.2.1) -- Wraps real SessionStateManager
  TestSessionStateReaderAdapter (5.2.2) -- In-memory dict stub
  LocalEventAdapter (5.2.3) -- In-process event dispatch + capture mode
  TestBridgeAdapter (5.2.4) -- Canned K0 responses
  TestModelGatewayAdapter (5.2.5) -- Canned LLM responses
  TestPromptSystemAdapter (5.2.6) -- Static prompt templates
  TestDeltaBusAdapter (5.2.7) -- Delta capture for assertions
  BridgeConnectionAdapter (5.2.8) -- Production Bridge connection

Pattern:
  Adapters implement port protocols via structural subtyping (no ABC).
  FabricFactory (5.3.1) selects adapter set based on factory method.

Exports:
  SessionStateReaderAdapter
  TestSessionStateReaderAdapter
  LocalEventAdapter
  TestBridgeAdapter
  TestModelGatewayAdapter
  TestLLMHandle
  TestPromptSystemAdapter
  CapturedBridgeCall
  TestDeltaBusAdapter
  CapturedDelta
  BridgeConnectionAdapter
  BridgeConnectionConfig
"""

from k1.fabric.adapters.bridge_connection import BridgeConnectionAdapter, BridgeConnectionConfig
from k1.fabric.adapters.local_event import LocalEventAdapter
from k1.fabric.adapters.sessionstate_reader import SessionStateReaderAdapter
from k1.fabric.adapters.test_bridge import CapturedBridgeCall, TestBridgeAdapter
from k1.fabric.adapters.test_delta_bus import CapturedDelta, TestDeltaBusAdapter
from k1.fabric.adapters.test_model_gateway import TestLLMHandle, TestModelGatewayAdapter
from k1.fabric.adapters.test_prompt_system import TestPromptSystemAdapter
from k1.fabric.adapters.test_state_reader import TestSessionStateReaderAdapter

__all__ = [
    # --- 5.2.1 Production SessionState ---
    "SessionStateReaderAdapter",
    # --- 5.2.2 Test SessionState ---
    "TestSessionStateReaderAdapter",
    # --- 5.2.3 Local Event ---
    "LocalEventAdapter",
    # --- 5.2.4 Test Bridge ---
    "TestBridgeAdapter",
    "CapturedBridgeCall",
    # --- 5.2.5 Test Model Gateway ---
    "TestModelGatewayAdapter",
    "TestLLMHandle",
    # --- 5.2.6 Test Prompt System ---
    "TestPromptSystemAdapter",
    # --- 5.2.7 Test Delta Bus ---
    "TestDeltaBusAdapter",
    "CapturedDelta",
    # --- 5.2.8 Production Bridge ---
    "BridgeConnectionAdapter",
    "BridgeConnectionConfig",
]
