"""
Entry point for running CLI with: python -m backend.cli.chat

This script:
1. Initializes all required services (LLM, K0, metrics, etc.)
2. Creates ConciergeAgent instance
3. Launches ChatCLI interface
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.agents.concierge import ConciergeAgent
from backend.agents.proactive_generator import ProactiveGenerator
from backend.agents.reactive_handler import ReactiveHandler
from backend.cli.chat import ChatCLI
from backend.cli.display import DisplayHelper
from backend.config.settings import Settings
from backend.services.conversation_store import ConversationStore
from backend.services.k0_query_service import MockK0QueryService
from backend.services.llm_client import LLMClient
from backend.services.metrics_collector import MetricsCollector


async def main():
    """Initialize and run CLI."""
    try:
        # Initialize services
        print("Initializing Concierge PoC CLI...")

        # LLM settings
        settings = Settings()

        # LLM client
        llm_client = LLMClient(settings)

        # K0 service (mock for demo)
        k0_service = MockK0QueryService()

        # Metrics collector
        metrics_collector = MetricsCollector()

        # Conversation store
        conversation_store = ConversationStore(max_history_turns=10)

        # Create agent components
        reactive_handler = ReactiveHandler(
            llm_client=llm_client,
            conversation_store=conversation_store,
            metrics_collector=metrics_collector,
        )
        proactive_generator = ProactiveGenerator(
            llm_client=llm_client,
            metrics_collector=metrics_collector,
        )

        # Create main orchestrator
        concierge = ConciergeAgent(
            reactive_handler=reactive_handler,
            proactive_generator=proactive_generator,
            llm_client=llm_client,
            k0_query_service=k0_service,
            metrics_collector=metrics_collector,
            progress_publisher=None,  # Optional for CLI
        )

        # Create display helper
        display = DisplayHelper()

        # Create and run CLI
        cli = ChatCLI(concierge, display)
        await cli.start()

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\nFatal error: {str(e)}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
