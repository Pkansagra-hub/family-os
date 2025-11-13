import sys
from pathlib import Path

import pytest

# Add POC root to path so we can import system_coordinator like other tests
poc_path = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(poc_path))

# Provide a minimal 'groq' stub to satisfy imports if the package is missing
import types

if "groq" not in sys.modules:
    groq_stub = types.ModuleType("groq")
    groq_stub.APIConnectionError = Exception
    groq_stub.APITimeoutError = Exception
    groq_stub.RateLimitError = Exception

    class AsyncGroq:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass

    groq_stub.AsyncGroq = AsyncGroq  # type: ignore
    sys.modules["groq"] = groq_stub

from system_coordinator import get_system_coordinator


@pytest.mark.asyncio
async def test_graceful_shutdown_end_to_end():
    coord = get_system_coordinator()

    # Initialize full system
    started = await coord.initialize_system()
    assert started is True
    assert coord.system_ready is True

    # Now shutdown
    shut = await coord.shutdown_system()
    assert shut is True

    # Verify Tier 1 agents terminated if present
    if hasattr(coord, "tier1_agents"):
        for name, agent in coord.tier1_agents.items():
            if hasattr(agent, "state"):
                # AgentBase.AgentState has .value, we compare string
                state_val = getattr(agent.state, "value", agent.state)
                assert str(state_val) == "terminated"

    # Background services should be stopped
    if hasattr(coord, "bg_services_manager") and coord.bg_services_manager:
        status = await coord.bg_services_manager.get_status()
        # writer_agents may be zero after stop_all
        assert status.get("writer_agents", 0) == 0

    # System flag reset
    assert coord.system_ready is False
