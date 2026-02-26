"""
poc.k1_poc.demo -- End-to-end demo bootstrap for the K1 Concierge POC.

Provides:
    - K1DemoCoordinator: 6-phase system bootstrap (config, bus, session,
      FSM/actors, support systems, health check)
    - InteractiveDemoLoop: stdin-driven turn loop with device identity
    - OutputChannel: bus-subscribed response renderer
    - IoTMonitorStub: scripted proactive events per storyline turn
    - SmithFamily: demo family profile, device registry, preloaded memories

Entry point::

    python -m poc.k1_poc.demo.runner [--test-mode] [--auto-play]
"""

from __future__ import annotations

__all__ = [
    "K1DemoCoordinator",
    "get_k1_demo_coordinator",
]
