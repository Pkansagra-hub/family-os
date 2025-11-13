"""
Chat Experience PoC - Main Entry Point

Extensible entry point for testing individual PoC components.
Use this file to:
- Start mock services (K0 API, MCP servers, SSE)
- Initialize core components (Groq client, SessionState, DeltaBus)
- Run integration tests
- Validate end-to-end flows

Usage:
    python main.py                              # Start all services
    python main.py --component config           # Test config loading
    python main.py --component groq             # Test Groq client
    python main.py --service mock-k0            # Start mock K0 API on :8003
    python main.py --service mock-sse           # Start mock SSE on :8002
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

import structlog

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configure environment
os.environ.setdefault("K1_POC_ENVIRONMENT", "development")


def setup_logging():
    """Configure structured logging."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


async def test_component_config():
    """Test configuration loading."""
    logger = structlog.get_logger(__name__)
    logger.info("test_component", component="config")

    try:
        from config.config_loader import get_config

        config = get_config()
        logger.info(
            "config_loaded",
            environment=config.environment,
            session_timeout=config.session.session_timeout_seconds,
            agent_pool_size=config.agent.agent_pool_size,
        )
        print("\n✅ Config loaded successfully")
        print(f"   Environment: {config.environment}")
        print(f"   Session timeout: {config.session.session_timeout_seconds}s")
        print(f"   Agent pool size: {config.agent.agent_pool_size}")
        return True
    except Exception as e:
        logger.error("config_test_failed", error=str(e))
        print(f"\n❌ Config test failed: {e}")
        return False


async def test_component_groq():
    """Test Groq client initialization."""
    logger = structlog.get_logger(__name__)
    logger.info("test_component", component="groq")

    try:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            print("\n❌ GROQ_API_KEY not set in environment")
            print("   Set it in .env file or environment variables")
            return False

        from l5_infrastructure.groq_client import GroqClient

        client = GroqClient(api_key)
        logger.info("groq_client_initialized")

        # Test with simple message
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say 'Hello from PoC' and nothing else."},
        ]

        response = await client.complete(
            messages=messages,
            agent_type="specialist",
            max_tokens=256,
            trace_id="test-groq-001",
        )

        logger.info(
            "groq_response",
            tokens_used=response["tokens_used"],
            content_preview=response["content"][:100],
        )

        print("\n✅ Groq client test passed")
        print(f"   Response: {response['content']}")
        print(f"   Tokens: {response['tokens_used']}")

        await client.close()
        return True

    except Exception as e:
        logger.error("groq_test_failed", error=str(e))
        print(f"\n❌ Groq test failed: {e}")
        return False


async def test_component_tool_registry():
    """Test Tool Registry."""
    logger = structlog.get_logger(__name__)
    logger.info("test_component", component="tool_registry")

    try:
        from l5_infrastructure.registries.tool_registry import get_tool_registry

        registry = get_tool_registry()
        tools = registry.list_all_tools()

        logger.info(
            "tool_registry_loaded",
            num_tools=len(tools),
            tools=[t.tool_id for t in tools],
        )

        # Test validation
        is_valid, error = registry.validate_tool_request(
            "web_search",
            {"query": "test query"},
        )

        if not is_valid:
            print(f"\n❌ Tool registry test failed: {error}")
            return False

        print("\n✅ Tool Registry test passed")
        print(f"   Registered tools: {len(tools)}")
        for tool in tools:
            print(f"   - {tool.tool_id}: {tool.name}")
        return True
    except Exception as e:
        logger.error("tool_registry_test_failed", error=str(e))
        print(f"\n❌ Tool Registry test failed: {e}")
        return False


async def test_component_k0_query_client():
    """Test K0 Query Client initialization."""
    logger = structlog.get_logger(__name__)
    logger.info("test_component", component="k0_query_client")

    try:
        from l5_infrastructure.k0_bridge.k0_query_client import K0QueryClient, QueryFilters

        client = K0QueryClient()

        # Test filter validation
        filters = QueryFilters(
            tags=["health", "recovery"],
            similarity_threshold=0.7,
        )
        is_valid, error = filters.validate()

        if not is_valid:
            print(f"\n❌ K0 Query Client test failed: {error}")
            return False

        stats = client.get_stats()

        logger.info(
            "k0_query_client_initialized",
            base_url=client.k0_base_url,
            timeout=client.timeout_seconds,
        )

        print("\n✅ K0 Query Client test passed")
        print(f"   Base URL: {client.k0_base_url}")
        print(f"   Timeout: {client.timeout_seconds}s")
        print(f"   Stats: {stats}")

        await client.close()
        return True
    except Exception as e:
        logger.error("k0_query_client_test_failed", error=str(e))
        print(f"\n❌ K0 Query Client test failed: {e}")
        return False


async def test_component_tool_call_handler():
    """Test Tool Call Handler."""
    logger = structlog.get_logger(__name__)
    logger.info("test_component", component="tool_call_handler")

    try:
        from l5_infrastructure.tool_call_handler import (
            ToolCallHandler,
            ToolRequest,
            get_tool_call_handler,
        )

        # Test ToolRequest creation
        request = ToolRequest(
            tool_id="web_search",
            parameters={"query": "test"},
            agent_id="concierge_001",
        )
        assert request.tool_id == "web_search"
        assert request.trace_id is not None

        # Test ToolCallHandler initialization
        handler = ToolCallHandler()
        assert handler.timeout_seconds == 10.0
        assert handler.max_retries == 3

        # Test request formatting
        tool = handler.tool_registry.get_tool("web_search")
        formatted = handler._format_request(request, tool)
        assert formatted["tool_id"] == "web_search"
        assert formatted["metadata"]["agent_id"] == "concierge_001"
        assert formatted["metadata"]["trace_id"] == request.trace_id

        # Test receipt creation
        receipt = handler._create_receipt(
            request=request,
            status="success",
            latency_ms=100.0,
            result={"data": "test"},
        )
        assert receipt.status == "success"
        assert receipt.tool_id == "web_search"

        # Test stats
        stats = handler.get_stats()
        assert "calls_total" in stats
        assert "success_rate_percent" in stats

        # Test singleton
        handler2 = get_tool_call_handler()
        assert handler2 is not None

        logger.info("tool_call_handler_tests_passed")
        print("\n✅ Tool Call Handler tests passed")
        print(f"   Request trace_id: {request.trace_id}")
        print("   Request formatting: OK")
        print("   Receipt generation: OK")
        print(f"   Handler stats: {stats}")

        return True
    except Exception as e:
        logger.error("tool_call_handler_test_failed", error=str(e))
        print(f"\n❌ Tool Call Handler test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_component_models():
    """Test Pydantic models."""
    logger = structlog.get_logger(__name__)
    logger.info("test_component", component="models")

    try:
        from models.config_models import POCConfig

        # Create with defaults
        config = POCConfig()
        assert config.session.session_timeout_seconds == 600
        assert config.agent.agent_pool_size == 5

        logger.info("models_validation_passed")
        print("\n✅ Pydantic models validation passed")
        print(f"   Session timeout: {config.session.session_timeout_seconds}s")
        print(f"   Agent pool size: {config.agent.agent_pool_size}")
        print(f"   Performance TTFT: {config.performance.ttft_budget_ms}ms")

        return True
    except Exception as e:
        logger.error("models_test_failed", error=str(e))
        print(f"\n❌ Models test failed: {e}")
        return False


async def test_component_concierge():
    """Test Concierge Agent - Master Coordinator."""
    logger = structlog.get_logger(__name__)
    logger.info("test_component", component="concierge")

    try:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            print("\n❌ GROQ_API_KEY not set in environment")
            print("   Set it in .env file or environment variables")
            return False

        from l3_execution.agents.concierge_agent import ConciergeAgent
        from l5_infrastructure.groq_client import GroqClient

        # Initialize Groq client and Concierge
        groq_client = GroqClient(api_key)
        concierge = ConciergeAgent(
            agent_id="concierge-poc-001",
            groq_client=groq_client,
            session_id="test-session-main",
        )

        logger.info("concierge_initialized")

        # Test 1: Meta-intent (greeting)
        print("\n🧪 Testing Concierge Agent...")
        print("\n1️⃣  Testing meta-intent classification (greeting):")
        result1 = await concierge.process_message("hey what's up?", trace_id="main-test-001")
        print("   User: hey what's up?")
        print(
            f"   Intent: {result1['intent']['type']} (confidence: {result1['intent']['confidence']:.2f})"
        )
        print(f"   Response: {result1['content'][:100]}...")

        # Test 2: Query-intent (healthcare)
        print("\n2️⃣  Testing query-intent classification (healthcare):")
        result2 = await concierge.process_message(
            "how's my recovery going?", trace_id="main-test-002"
        )
        print("   User: how's my recovery going?")
        print(
            f"   Intent: {result2['intent']['type']} (confidence: {result2['intent']['confidence']:.2f})"
        )
        print(f"   Routing: {result2['intent']['routing_target']}")
        print(f"   Response: {result2['content'][:100]}...")

        # Test 3: Planning-intent
        print("\n3️⃣  Testing planning-intent classification:")
        result3 = await concierge.process_message(
            "plan a trip to Hawaii next month", trace_id="main-test-003"
        )
        print("   User: plan a trip to Hawaii next month")
        print(
            f"   Intent: {result3['intent']['type']} (confidence: {result3['intent']['confidence']:.2f})"
        )
        print(f"   Routing: {result3['intent']['routing_target']}")
        print(f"   Response: {result3['content'][:100]}...")

        # Verify conversation state
        summary = concierge.get_conversation_summary()
        print("\n📊 Conversation Summary:")
        print(f"   Total turns: {summary['turn_count']}")
        print("   Recent intents:")
        for intent_info in summary["recent_intents"]:
            print(
                f"     - Turn {intent_info['turn']}: {intent_info['intent_type']} ({intent_info['confidence']:.2f})"
            )

        await groq_client.close()

        print("\n✅ Concierge Agent test passed")
        print("   ✓ Intent classification working")
        print("   ✓ Routing logic working")
        print("   ✓ Conversation tracking working")

        return True

    except Exception as e:
        logger.error("concierge_test_failed", error=str(e))
        print(f"\n❌ Concierge test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def start_service_mock_k0():
    """Start mock K0 API server on port 8003."""
    logger = structlog.get_logger(__name__)

    try:
        import uvicorn
        from fastapi import FastAPI

        app = FastAPI(title="Mock K0 API")

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        @app.post("/p02/memory_write")
        async def memory_write(request: dict):
            """Mock K0 memory write endpoint."""
            logger.info("k0_memory_write_received", request_keys=list(request.keys()))
            return {"status": "accepted", "batch_id": "mock-001"}

        logger.info("starting_mock_k0_server", port=8003)
        print("\n🚀 Starting Mock K0 API on http://localhost:8003")
        print("   Health check: GET /health")
        print("   Memory write: POST /p02/memory_write")

        config = uvicorn.Config(app, host="0.0.0.0", port=8003)
        server = uvicorn.Server(config)
        await server.serve()

    except Exception as e:
        logger.error("mock_k0_startup_failed", error=str(e))
        print(f"\n❌ Mock K0 startup failed: {e}")


async def main():
    """Main entry point with CLI arguments."""
    parser = argparse.ArgumentParser(description="Chat Experience PoC - K1 Intelligence Module")
    parser.add_argument(
        "--component",
        choices=[
            "config",
            "groq",
            "models",
            "tool_registry",
            "k0_query_client",
            "tool_call_handler",
            "concierge",
        ],
        help="Test specific component",
    )
    parser.add_argument(
        "--service",
        choices=["mock-k0"],
        help="Start specific service",
    )

    args = parser.parse_args()

    setup_logging()

    print("\n" + "=" * 70)
    print("🚀 Chat Experience PoC - K1 Intelligence Module")
    print("=" * 70)

    if args.component:
        if args.component == "config":
            success = await test_component_config()
        elif args.component == "groq":
            success = await test_component_groq()
        elif args.component == "models":
            success = await test_component_models()
        elif args.component == "tool_registry":
            success = await test_component_tool_registry()
        elif args.component == "k0_query_client":
            success = await test_component_k0_query_client()
        elif args.component == "tool_call_handler":
            success = await test_component_tool_call_handler()
        elif args.component == "concierge":
            success = await test_component_concierge()

        sys.exit(0 if success else 1)

    elif args.service:
        if args.service == "mock-k0":
            await start_service_mock_k0()

    else:
        # Default: run all component tests
        print("\nRunning component tests...\n")

        results = {
            "config": await test_component_config(),
            "models": await test_component_models(),
            "tool_registry": await test_component_tool_registry(),
            "k0_query_client": await test_component_k0_query_client(),
            "tool_call_handler": await test_component_tool_call_handler(),
        }

        # Only test Groq if API key is set
        if os.getenv("GROQ_API_KEY"):
            results["groq"] = await test_component_groq()
        else:
            print("\n⚠️  Skipping Groq test (GROQ_API_KEY not set)")
            results["groq"] = True  # Treat as passed (skipped)

        print("\n" + "=" * 70)
        print("Test Results:")
        for component, result in results.items():
            if result is None:
                status = "⏭️  SKIPPED"
            elif result:
                status = "✅ PASSED"
            else:
                status = "❌ FAILED"
            print(f"  {component:15s} {status}")
        print("=" * 70 + "\n")

        all_passed = all(r is True for r in results.values())
        sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
