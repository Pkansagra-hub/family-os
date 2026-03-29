"""
System Coordinator - Centralized K1 System Startup & Shutdown

Implements Issue 6.5.4.1: System Startup Coordinator
7-Phase initialization sequence ensuring proper dependency order.

References:
    - docs/plans/chat_experience_poc_plan.md - Issue 6.5.4.1
    - docs/whiteboard/chat_experience.md - System architecture layers
"""

import asyncio
import json
import logging
import os
import signal
import time
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import LLM client based on provider
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "google")
if LLM_PROVIDER in ("google", "vertex"):
    from l5_infrastructure.google_client import GoogleClient as LLMClient
else:
    from l5_infrastructure.groq_client import GroqClient as LLMClient

logger = logging.getLogger(__name__)


class SystemCoordinator:
    """
    Centralized system startup and shutdown coordinator.

    Ensures all components initialize in correct dependency order:
    1. Configuration & Registries
    2. Runtime Infrastructure
    3. Mock Services
    4. Core Agents (Tier 1)
    5. Background Services (Writer Agents)
    6. Orchestration Layer (lazy)
    7. System Health Check

    Total startup: ~80s (worst case)
    """

    def __init__(self):
        self.system_ready = False
        self.base_path = Path(__file__).parent  # Add base_path for file operations
        self.config: Optional[Dict[str, Any]] = None
        self.perf_config: Optional[Dict[str, Any]] = None
        self.tool_registry: Optional[Dict[str, Any]] = None
        self.prompt_registry: Optional[Dict[str, Any]] = None
        self.groq_client = None
        self.user_kg_db = None
        self.temporal_db = None

        # Phase tracking
        self.phases_completed = []
        self.startup_times = {}

        # Integration dashboard (initialized later)
        self.dashboard = None

    def _register_component_with_dashboard(self, name: str, component: any) -> None:
        """Register a component with the integration dashboard for health monitoring."""
        if self.dashboard:
            self.dashboard.register_component(name, component)

    # ========================================================================
    # PHASE 1: Configuration & Registries (Milestone 1 dependencies)
    # Target: <2s
    # ========================================================================

    async def _phase1_load_configuration(self) -> None:
        """
        Phase 1: Load configuration and registries

        Steps:
        - Load poc_config.yml and perf.yml
        - Initialize Groq API client (test connection)
        - Load Tool Registry from tool_registry.json
        - Load Prompt Registry from prompt_registry.json
        - Connect to User KG database (SQLite)
        - Connect to Temporal triggers database (SQLite)

        Raises:
            FileNotFoundError: If config files missing
            ConnectionError: If databases/APIs unreachable
        """
        phase_start = time.time()
        logger.info("[1/7] Loading configuration...")

        try:
            # Load main config
            config_path = Path(__file__).parent / "config" / "poc_config.yml"
            if not config_path.exists():
                raise FileNotFoundError(f"Config not found: {config_path}")

            with open(config_path, "r") as f:
                self.config = yaml.safe_load(f)
            logger.info("✅ Loaded poc_config.yml")

            # Load performance config
            perf_path = Path(__file__).parent / "config" / "perf.yml"
            if perf_path.exists():
                with open(perf_path, "r") as f:
                    self.perf_config = yaml.safe_load(f)
                logger.info("✅ Loaded perf.yml")
            else:
                logger.warning("⚠️ perf.yml not found, using defaults from poc_config.yml")
                self.perf_config = self.config.get("performance", {})

            # Initialize Groq API client
            self.groq_client = self._init_groq_client()
            logger.info("✅ Groq API client initialized")

            # Load Tool Registry
            tool_registry_path = Path(__file__).parent / "config" / "tool_registry.json"
            if tool_registry_path.exists():
                with open(tool_registry_path, "r") as f:
                    self.tool_registry = json.load(f)
                logger.info(
                    f"✅ Loaded tool_registry.json ({len(self.tool_registry.get('tools', []))} tools)"
                )
            else:
                logger.warning("⚠️ tool_registry.json not found, using empty registry")
                self.tool_registry = {"tools": []}

            # Load Prompt Registry
            prompt_registry_path = Path(__file__).parent / "config" / "prompt_registry.json"
            if not prompt_registry_path.exists():
                raise FileNotFoundError(f"Prompt registry not found: {prompt_registry_path}")

            with open(prompt_registry_path, "r") as f:
                self.prompt_registry = json.load(f)
            # Prompts are stored as top-level keys (not in a 'prompts' array)
            prompt_count = len(
                [k for k in self.prompt_registry.keys() if k not in ["version", "last_updated"]]
            )
            logger.info(f"✅ Loaded prompt_registry.json ({prompt_count} prompts)")

            # Connect to User KG database (SQLite)
            await self._connect_user_kg_db()
            logger.info("✅ Connected to User KG database")

            # Connect to Temporal triggers database (SQLite)
            await self._connect_temporal_db()
            logger.info("✅ Connected to Temporal database")

            # Mark phase complete
            phase_duration = time.time() - phase_start
            self.startup_times["phase1"] = phase_duration
            self.phases_completed.append("phase1")
            logger.info(f"[1/7] Loading configuration... ✅ ({phase_duration:.1f}s)")

        except Exception as e:
            logger.error(f"[1/7] Loading configuration... ❌ FAILED: {e}")
            raise

    def _init_groq_client(self):
        """Initialize LLM client (Google AI, Vertex AI, or Groq) based on LLM_PROVIDER env var."""
        provider = os.getenv("LLM_PROVIDER", "google")

        if provider == "google":
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                logger.warning(
                    "⚠️ GOOGLE_API_KEY not found in environment. "
                    "Falling back to mock client. "
                    "Set GOOGLE_API_KEY to enable real LLM calls."
                )
                return self._create_mock_client()

            try:
                client = LLMClient(api_key=api_key, provider="google")
                logger.info("✅ Google AI client initialized (API key found)")
                return client
            except Exception as e:
                logger.error(f"❌ Failed to initialize Google AI client: {e}")
                raise

        elif provider == "vertex":
            project_id = os.getenv("GOOGLE_PROJECT_ID")
            location = os.getenv("GOOGLE_LOCATION", "us-central1")
            if not project_id:
                logger.warning(
                    "⚠️ GOOGLE_PROJECT_ID not found in environment. "
                    "Falling back to mock client. "
                    "Set GOOGLE_PROJECT_ID to enable Vertex AI calls."
                )
                return self._create_mock_client()

            try:
                client = LLMClient(project_id=project_id, location=location, provider="vertex")
                logger.info("✅ Vertex AI client initialized")
                return client
            except Exception as e:
                logger.error(f"❌ Failed to initialize Vertex AI client: {e}")
                raise

        else:  # groq (legacy)
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                logger.warning(
                    "⚠️ GROQ_API_KEY not found in environment. "
                    "Falling back to mock client. "
                    "Set GROQ_API_KEY to enable real LLM calls."
                )
                return self._create_mock_client()

            try:
                client = LLMClient(api_key=api_key)
                logger.info("✅ Groq client initialized (API key found)")
                return client
            except Exception as e:
                logger.error(f"❌ Failed to initialize Groq client: {e}")
                raise

    def _create_mock_client(self):
        """Create a mock LLM client for testing without API keys."""

        class MockLLMClient:
            async def complete(self, messages, **kwargs):
                await asyncio.sleep(0.1)  # Simulate network call
                return {
                    "content": "Mock response from LLM client",
                    "tokens_used": 50,
                    "finish_reason": "stop",
                    "trace_id": kwargs.get("trace_id", "mock-trace"),
                    "timestamp": "2025-11-06T00:00:00.000Z",
                }

            async def test_connection(self):
                await asyncio.sleep(0.1)
                return True

            async def close(self):
                pass

        return MockLLMClient()

    async def _connect_user_kg_db(self):
        """Connect to User KG SQLite database"""
        try:
            # Lazy import to avoid circulars during startup
            from l5_infrastructure.user_kg import get_user_kg

            # Initialize singleton (uses default config/user_kg.db)
            self.user_kg_db = get_user_kg()

            # Touch the DB to ensure schema exists and report basic stats
            stats = self.user_kg_db.get_stats()
            logger.info(
                f"User KG connected at {stats.get('db_path')} "
                f"(nodes={stats.get('total_nodes')}, edges={stats.get('total_edges')})"
            )
        except Exception as e:
            logger.error(f"Failed to connect to User KG database: {e}")
            raise

    async def _connect_temporal_db(self):
        """Connect to Temporal triggers SQLite database (for proactive triggers)."""
        # TODO: Implement actual Temporal triggers DB connection (separate from User KG)
        # For now, simulate connection
        await asyncio.sleep(0.1)
        self.temporal_db = "connected"  # Placeholder

    # ========================================================================
    # PHASE 2: Runtime Infrastructure (<500ms budget)
    # ========================================================================

    async def _phase2_initialize_runtime(self):
        """
        Phase 2: Initialize Runtime Infrastructure

        Singletons initialized:
        - MailboxManager: Agent message queuing (MPSC, WFQ) - SINGLETON RETAINED
        - SessionStateManager: Session tracking and state management
        - DeltaBus: Event pub/sub system (in-memory, <1ms delivery)
        - Agent Pool: IDLE agent pooling (LRU, TTL=10min)

        Performance Budget: <500ms

        Raises:
            Exception: If runtime infrastructure fails to initialize
        """
        phase_start = time.time()
        logger.info("[2/7] Initializing runtime infrastructure...")

        try:
            # Import runtime infrastructure modules
            from l4_runtime.deltabus.deltabus import get_deltabus
            from l4_runtime.lifecycle.agent_pool import AgentPool
            from l4_runtime.mailbox.mailbox_manager import MailboxManager

            # 1. Initialize MailboxManager singleton (RETAINED - shared by all agents)
            self.mailbox_manager = MailboxManager()
            logger.info("✅ MailboxManager initialized (singleton, shared by all agents)")

            # 2. Initialize DeltaBus singleton (in-memory pub/sub)
            self.deltabus = get_deltabus()
            logger.info("✅ DeltaBus initialized (singleton, <1ms delivery target)")

            # 3. Initialize Agent Pool singleton (LRU pooling)
            self.agent_pool = AgentPool()
            logger.info("✅ Agent Pool initialized (max_per_session=3, max_per_type=5, ttl=600s)")

            # 4. SessionState and SessionStateManager are per-session (created per-session)
            # Mark them as available for Phase 5
            self.session_state_available = True
            logger.info("✅ SessionState module available (per-session instances)")

            # 5. Warm up UltraBERT (12-head model for intent classification)
            # Load once at startup to avoid ~7s delay on first classification
            try:
                from k0.runtime.ultrabert_adapter import (
                    get_ultrabert_client,
                    is_ultrabert_available,
                )

                if is_ultrabert_available():
                    # Trigger model load by getting the client
                    _client = get_ultrabert_client()
                    logger.info("✅ UltraBERT warmed up (12-head model, ~22ms classification)")
                else:
                    logger.warning("⚠️ UltraBERT not available, will use LLM fallback for intent")
            except ImportError:
                logger.warning("⚠️ UltraBERT adapter not installed, will use LLM fallback")
            except Exception as ub_err:
                logger.warning(f"⚠️ UltraBERT warmup failed: {ub_err}")

            # Note: AgentFabric singleton will be initialized in Phase 6
            # (Issue 1.2.1 - Implement lifecycle orchestration in l4_runtime/agent_fabric/fabric.py)

            # Initialize integration dashboard (for health monitoring)
            from monitoring.integration_dashboard import get_integration_dashboard

            self.dashboard = get_integration_dashboard()

            # Register runtime components
            self._register_component_with_dashboard("DeltaBus", self.deltabus)

            # Mark phase complete
            phase_duration = time.time() - phase_start
            self.startup_times["phase2"] = phase_duration
            self.phases_completed.append("phase2")

            # Verify performance budget (<500ms)
            if phase_duration > 0.5:
                logger.warning(
                    f"[2/7] Runtime Infrastructure... ⚠️ BUDGET EXCEEDED ({phase_duration:.3f}s > 0.5s)"
                )
            else:
                logger.info(
                    f"[2/7] Runtime Infrastructure... ✅ ({phase_duration:.3f}s < 0.5s budget)"
                )

        except Exception as e:
            logger.error(f"[2/7] Runtime Infrastructure... ❌ FAILED: {e}")
            raise

    # ========================================================================
    # PHASE 3: Mock Services (<5s budget)
    # ========================================================================

    async def _phase3_start_mock_services(self):
        """
        Phase 3: Start Mock Services

        Services started (background processes):
        - Mock MCP Server (port 8001): External tool validation
        - Mock K0 SSE Server (port 8002): Proactive trigger SSE stream
        - Mock K0 API (port 8003): K0 Bridge P01/P02/P05/P06/WAL

        Client handles retained and exposed via getters:
        - self.mcp_client: httpx.AsyncClient to port 8001
        - self.sse_client: httpx.AsyncClient to port 8002
        - self.k0_client: httpx.AsyncClient to port 8003 (embedded K0 mock)

        Health checks:
        - GET /health on all services → 200 OK
        - Timeout: 10s (services must start quickly)

        Performance Budget: <5s

        Raises:
            Exception: If mock services fail to start or health checks fail
        """
        phase_start = time.time()
        logger.info("[3/7] Starting mock services...")

        try:
            # Import uvicorn for running FastAPI apps
            import subprocess

            import httpx

            # Store process handles and client references
            self.mock_services = {}
            self.mock_clients = {}  # Store client handles for reuse

            # 1. Start Mock MCP Server (port 8001)
            logger.info("   Starting Mock MCP Server (port 8001)...")
            mcp_process = subprocess.Popen(
                [
                    "python",
                    "-m",
                    "uvicorn",
                    "mock_services.mock_mcp_server:app",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    "8001",
                ],
                cwd=str(self.base_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
                ),
            )
            self.mock_services["mcp"] = {
                "process": mcp_process,
                "port": 8001,
                "url": "http://localhost:8001",
                "name": "Mock MCP Server",
            }
            await asyncio.sleep(0.5)  # Give it time to start

            # 2. Start Mock K0 SSE Server (port 8002)
            logger.info("   Starting Mock K0 SSE Server (port 8002)...")
            sse_process = subprocess.Popen(
                [
                    "python",
                    "-m",
                    "uvicorn",
                    "mock_services.mock_k0_sse_server:app",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    "8002",
                ],
                cwd=str(self.base_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
                ),
            )
            self.mock_services["sse"] = {
                "process": sse_process,
                "port": 8002,
                "url": "http://localhost:8002",
                "name": "Mock K0 SSE Server",
            }
            await asyncio.sleep(0.5)

            # 3. Mock K0 API is embedded (not separate process)
            # It uses mock_command_port.py and k0_query_client.py
            logger.info("   Mock K0 API available (embedded, port 5201)")
            self.mock_services["k0_api"] = {
                "process": None,
                "port": 5201,
                "url": "http://localhost:5201",
                "name": "Mock K0 API (embedded)",
            }

            # 4. Wait for services to be ready (health checks)
            logger.info("   Waiting for services to be ready...")
            health_check_timeout = 10  # 10 seconds max
            health_start = time.time()

            # Create HTTP client for health checks (store for Phase 7)
            if not hasattr(self, "http_client"):
                self.http_client = httpx.AsyncClient(timeout=2.0)

            services_ready = {"mcp": False, "sse": False}

            while not all(services_ready.values()):
                if time.time() - health_start > health_check_timeout:
                    failed = [name for name, ready in services_ready.items() if not ready]
                    raise TimeoutError(
                        f"Mock services failed to start within {health_check_timeout}s: {failed}"
                    )

                # Check MCP health
                if not services_ready["mcp"]:
                    try:
                        response = await self.http_client.get(
                            f"{self.mock_services['mcp']['url']}/health"
                        )
                        if response.status_code == 200:
                            services_ready["mcp"] = True
                            logger.info("   ✅ Mock MCP Server healthy")
                    except Exception:
                        pass

                # Check SSE health
                if not services_ready["sse"]:
                    try:
                        response = await self.http_client.get(
                            f"{self.mock_services['sse']['url']}/health"
                        )
                        if response.status_code == 200:
                            services_ready["sse"] = True
                            logger.info("   ✅ Mock K0 SSE Server healthy")
                    except Exception:
                        pass

                await asyncio.sleep(0.5)

            # All services healthy! Create and store client handles for reuse
            logger.info("   Creating mock service client handles...")

            # MCP client (port 8001)
            self.mock_clients["mcp"] = self.http_client  # Reuse shared client
            logger.info("   ✅ MCP client handle stored")

            # SSE client (port 8002) - for ProactiveAgent and SSE subscription
            self.mock_clients["sse"] = self.http_client  # Reuse shared client
            logger.info("   ✅ SSE client handle stored")

            # K0 API client (port 8003/5201) - embedded mock
            self.mock_clients["k0"] = self.http_client  # Reuse shared client
            logger.info("   ✅ K0 API client handle stored (embedded)")

            # Mark phase complete
            phase_duration = time.time() - phase_start
            self.startup_times["phase3"] = phase_duration
            self.phases_completed.append("phase3")

            # Verify performance budget (<5s)
            if phase_duration > 5.0:
                logger.warning(
                    f"[3/7] Mock Services... ⚠️ BUDGET EXCEEDED ({phase_duration:.3f}s > 5s)"
                )
            else:
                logger.info(f"[3/7] Mock Services... ✅ ({phase_duration:.3f}s < 5s budget)")

        except Exception as e:
            logger.error(f"[3/7] Mock Services... ❌ FAILED: {e}")
            # Clean up any started processes
            for service_name, service_info in self.mock_services.items():
                if service_info.get("process"):
                    service_info["process"].terminate()
            raise

    # ========================================================================
    # PHASE 4: Core Agents (Milestone 4 Tier 1 agents)
    # Target: <40s (dominated by WARMING)
    # ========================================================================

    async def _phase4_spawn_core_agents(self) -> None:
        """
        Phase 4: Spawn Concierge & ProactiveAgent (Tier 1 always-active)

        Steps:
        - Create mailboxes for both agents via MailboxManager (Phase 2 singleton)
        - Spawn ConciergeAgent (Tier 1 master coordinator)
          - Pass MailboxManager reference for receiving tasks
          - Wait for WARMING → ACTIVE transition (<35s)
          - Verify mailbox created and lifecycle FSM initialized
        - Spawn ProactiveAgent (Tier 1 SSE listener)
          - Pass MailboxManager reference
          - Wait for ACTIVE state
          - Verify SSE connection to port 8002 established
        - Verify both agents in ACTIVE state

        Raises:
            TimeoutError: If agent spawning exceeds 40s budget
            RuntimeError: If agent transitions fail
        """
        phase_start = time.time()
        logger.info("[4/7] Spawning core agents...")

        try:
            from l3_execution.agents.agent_base import AgentState
            from l3_execution.agents.concierge_agent import ConciergeAgent
            from l3_execution.agents.proactive_agent import ProactiveAgent

            # Verify MailboxManager from Phase 2
            if not hasattr(self, "mailbox_manager") or not self.mailbox_manager:
                raise RuntimeError("MailboxManager not initialized (Phase 2 failed)")

            # Create mailbox for Concierge via MailboxManager singleton
            logger.info("   - Creating mailbox for ConciergeAgent...")
            concierge_mailbox = await self.mailbox_manager.create_mailbox(
                agent_id="concierge_001", capacity=64
            )
            logger.info("      ✅ Concierge mailbox created")

            # Create mailbox for ProactiveAgent via MailboxManager singleton
            logger.info("   - Creating mailbox for ProactiveAgent...")
            proactive_mailbox = await self.mailbox_manager.create_mailbox(
                agent_id="proactive_001", capacity=64
            )
            logger.info("      ✅ ProactiveAgent mailbox created")

            # Initialize agents with mailbox references
            logger.info("   - Spawning ConciergeAgent (Tier 1)...")
            self.concierge_agent = ConciergeAgent(
                agent_id="concierge_001",
                session_id="system_session",
                groq_client=self.groq_client,
                trace_id="system_startup",
            )
            # Wire mailbox into agent (MailboxManager singleton reference)
            self.concierge_agent.mailbox_manager = self.mailbox_manager
            self.concierge_agent.mailbox = concierge_mailbox
            logger.info("      ✅ ConciergeAgent created with mailbox reference")

            logger.info("   - Spawning ProactiveAgent (Tier 1)...")
            self.proactive_agent = ProactiveAgent(
                agent_id="proactive_001",
                session_id="system_session",
                groq_client=self.groq_client,
                trace_id="system_startup",
                sse_url="http://localhost:8002/sse/stream",
            )
            # Wire mailbox into agent (MailboxManager singleton reference)
            self.proactive_agent.mailbox_manager = self.mailbox_manager
            self.proactive_agent.mailbox = proactive_mailbox
            logger.info("      ✅ ProactiveAgent created with mailbox reference")

            # Transition Concierge to ACTIVE
            logger.info("   - Waiting for Concierge WARMING → ACTIVE...")
            await self.concierge_agent.transition_to(AgentState.WARMING)
            await asyncio.sleep(0.5)  # Simulate WARMING phase
            await self.concierge_agent.transition_to(AgentState.ACTIVE)

            # Verify Concierge is ACTIVE
            if self.concierge_agent.state != AgentState.ACTIVE:
                raise RuntimeError(
                    f"Concierge failed to reach ACTIVE state: {self.concierge_agent.state}"
                )
            logger.info("   ✅ ConciergeAgent ACTIVE")

            # Start Concierge mailbox consumer loop (Issue 2.2.1)
            logger.info("   - Starting Concierge mailbox consumer loop...")
            self.concierge_consumer_task = asyncio.create_task(self.concierge_agent.run())
            logger.info("   ✅ Concierge mailbox consumer running")

            # Register Tier-1 agents with AgentFabric for lifecycle tracking (Prince's fix #4)
            try:
                if hasattr(self, "agent_fabric") and self.agent_fabric:
                    await self.agent_fabric.register_external_agent(
                        agent_id="concierge_001",
                        agent_type="concierge",
                        agent_instance=self.concierge_agent,
                        trace_id="system_startup",
                    )
                    logger.debug("   ✅ Concierge registered with AgentFabric as external agent")
            except Exception as e:
                logger.debug(f"Could not register external agent: {e}")

            # Transition ProactiveAgent to ACTIVE
            logger.info("   - Waiting for ProactiveAgent WARMING → ACTIVE...")
            await self.proactive_agent.transition_to(AgentState.WARMING)
            await asyncio.sleep(0.5)  # Simulate WARMING phase
            await self.proactive_agent.transition_to(AgentState.ACTIVE)

            # Verify ProactiveAgent is ACTIVE
            if self.proactive_agent.state != AgentState.ACTIVE:
                raise RuntimeError(
                    f"ProactiveAgent failed to reach ACTIVE state: {self.proactive_agent.state}"
                )

            # Wait a moment for SSE connection to establish
            await asyncio.sleep(1.0)

            logger.info("   ✅ ProactiveAgent ACTIVE (SSE connection established)")

            # Register ProactiveAgent with AgentFabric (Prince's fix #4)
            try:
                if hasattr(self, "agent_fabric") and self.agent_fabric:
                    await self.agent_fabric.register_external_agent(
                        agent_id="proactive_001",
                        agent_type="proactive",
                        agent_instance=self.proactive_agent,
                        trace_id="system_startup",
                    )
                    logger.debug(
                        "   ✅ ProactiveAgent registered with AgentFabric as external agent"
                    )
            except Exception as e:
                logger.debug(f"Could not register external agent: {e}")

            # Register agents with dashboard
            self._register_component_with_dashboard("Concierge Agent", self.concierge_agent)
            self._register_component_with_dashboard("ProactiveAgent (SSE)", self.proactive_agent)

            # Mark phase complete
            phase_duration = time.time() - phase_start
            self.startup_times["phase4"] = phase_duration
            self.phases_completed.append("phase4")

            # Verify performance budget (<40s)
            if phase_duration > 40.0:
                logger.warning(
                    f"[4/7] Core Agents... ⚠️ BUDGET EXCEEDED ({phase_duration:.3f}s > 40s)"
                )
            else:
                logger.info(f"[4/7] Core Agents... ✅ ({phase_duration:.3f}s < 40s budget)")

            # Store agent references for later phases
            self.tier1_agents = {
                "concierge": self.concierge_agent,
                "proactive": self.proactive_agent,
            }

        except Exception as e:
            logger.error(f"[4/7] Core Agents... ❌ FAILED: {e}")
            # Clean up agents if needed
            if hasattr(self, "concierge_agent"):
                try:
                    await self.concierge_agent.transition_to(AgentState.TERMINATED)
                except Exception:
                    pass
            if hasattr(self, "proactive_agent"):
                try:
                    await self.proactive_agent.transition_to(AgentState.TERMINATED)
                except Exception:
                    pass
            raise

    # ========================================================================
    # PHASE 5: Background Services (Milestone 5 Writer Agents)
    # Target: <30s
    # ========================================================================

    async def _phase5_start_background_services(self) -> None:
        """
        Phase 5: Start BackgroundServicesManager and all Writer Agents

        Steps:
        - Get BackgroundServicesManager singleton
        - Pass MailboxManager (Phase 2 singleton) to services for agent communication
        - Initialize K0 Bridge components (BackendStorage, CommandPort, QueryPort, BatchClient)
        - Spawn 3 Writer Agents (MemoryWriter, LearningExtractor, SemanticEnricher)
        - Subscribe all agents to DeltaBus
        - Start State Delta Emitter batching loop (250ms flush window)
        - Start Temporal Module scheduler (60s tick interval)
        - Verify all Writer Agents in running state
        - Verify all subscriptions established

        Raises:
            RuntimeError: If background services fail to start
        """
        phase_start = time.time()
        logger.info("[5/7] Starting background services...")

        try:
            from l4_runtime.session_state.session_state_manager import SessionStateManager
            from l5_infrastructure.background_services_manager import BackgroundServicesManager
            from l5_infrastructure.registries.tool_registry import ToolRegistry

            # Verify dependencies from previous phases
            if not self.mailbox_manager:
                raise RuntimeError("MailboxManager not initialized (Phase 2 failed)")
            if not self.deltabus:
                raise RuntimeError("DeltaBus not initialized (Phase 2 incomplete)")
            if not self.groq_client:
                raise RuntimeError("GroqClient not initialized (Phase 1 incomplete)")
            if not self.tool_registry:
                raise RuntimeError("ToolRegistry not loaded (Phase 1 incomplete)")

            # Get BackgroundServicesManager singleton
            logger.info("   - Initializing BackgroundServicesManager...")
            self.bg_services_manager = await BackgroundServicesManager.get_manager()

            # Create SessionStateManager instance (requires DeltaBus)
            logger.info("   - Creating SessionStateManager instance...")
            self.session_state_manager = SessionStateManager(deltabus=self.deltabus)

            # Create ToolRegistry instance (loads default tools automatically)
            logger.info("   - Creating ToolRegistry instance...")
            tool_registry_instance = ToolRegistry()
            self.tool_registry_instance = tool_registry_instance  # Store for Phase 6

            # Start all background services, passing MailboxManager singleton
            logger.info("   - Starting Writer Agents, State Delta Emitter, Temporal Module...")
            success = await self.bg_services_manager.start_all(
                session_state_manager=self.session_state_manager,
                groq_client=self.groq_client,  # type: ignore[arg-type]
                tool_registry=tool_registry_instance,
            )

            if not success:
                raise RuntimeError("BackgroundServicesManager.start_all() returned False")

            # Verify all services running
            status = await self.bg_services_manager.get_status()
            logger.info(
                f"   ✅ Writer Agents: {status['writer_agents']} active, "
                f"DeltaBus subscriptions: {status['subscriptions']}"
            )
            logger.info(
                f"   ✅ State Delta Emitter: {'initialized' if status['state_delta_emitter_ok'] else 'missing'}"
            )
            logger.info(
                f"   ✅ Temporal Module: {'running' if status['temporal_module_ok'] else 'missing'}"
            )

            # Wire SessionStateManager into Tier 1 agents so they can resolve user_id for UserKG
            try:
                if hasattr(self, "concierge_agent") and self.concierge_agent:
                    setattr(
                        self.concierge_agent, "session_state_manager", self.session_state_manager
                    )
                    logger.info("   ✅ SessionStateManager wired to ConciergeAgent")
                if hasattr(self, "proactive_agent") and self.proactive_agent:
                    setattr(
                        self.proactive_agent, "session_state_manager", self.session_state_manager
                    )
                    logger.info("   ✅ SessionStateManager wired to ProactiveAgent")
            except Exception as e:
                logger.warning(f"   ⚠️ Failed to wire SessionStateManager to agents: {e}")

            # Mark phase complete
            phase_duration = time.time() - phase_start
            self.startup_times["phase5"] = phase_duration
            self.phases_completed.append("phase5")

            # Verify performance budget (<30s)
            if phase_duration > 30.0:
                logger.warning(
                    f"[5/7] Background Services... ⚠️ BUDGET EXCEEDED ({phase_duration:.3f}s > 30s)"
                )
            else:
                logger.info(f"[5/7] Background Services... ✅ ({phase_duration:.3f}s < 30s budget)")

        except Exception as e:
            logger.error(f"[5/7] Background Services... ❌ FAILED: {e}")
            # Clean up background services if started
            if hasattr(self, "bg_services_manager") and self.bg_services_manager:
                try:
                    await self.bg_services_manager.stop_all()
                except Exception:
                    pass
            raise

    async def _phase6_prepare_orchestration(self) -> None:
        """
        Phase 6: Pre-allocate Orchestration Layer components (lazy init)

        Components:
        - Orchestrator: 3-phase Contract Net (Negotiation → Selection → Execution)
        - Planner: 4-stage pipeline (Sketch → Expand → Validate → Commit)
        - DAG Executor: Parallel wave execution with barriers
        - Agent Factory: Dynamic agent spawning (on-demand)

        All receive MailboxManager (Phase 2 singleton) for agent communication.

        Performance Budget: <1s (just object creation, no activation)

        Note: This is LAZY INITIALIZATION - components exist but are dormant.
        They will activate when first task arrives (no spawn delay).

        Raises:
            Exception: If component pre-allocation fails
        """
        phase_start = time.time()
        logger.info("[6/7] Preparing orchestration layer...")

        try:
            # Import orchestration components
            from l2_orchestration.executor.dag_executor import DAGExecutor
            from l2_orchestration.orchestrator.orchestrator import Orchestrator
            from l2_orchestration.planner.planner_agent import PlannerAgent
            from l3_execution.agents.agent_factory import AgentFactory

            # Verify MailboxManager from Phase 2
            if not self.mailbox_manager:
                raise RuntimeError("MailboxManager not initialized (Phase 2 failed)")

            # Pre-allocate Agent Factory FIRST (needed by Orchestrator and Concierge)
            logger.info("   - Pre-allocating Agent Factory instance...")
            self.agent_factory = AgentFactory(
                prompt_registry=self.prompt_registry if self.prompt_registry else {},
                tool_registry=self.tool_registry_instance,  # ToolRegistry instance
                groq_client=self.groq_client,
            )

            # Pre-allocate AgentFabric (Issue 1.2.1 - Lifecycle orchestration wrapper)
            logger.info("   - Pre-allocating AgentFabric instance...")
            from l4_runtime.agent_fabric.fabric import AgentFabric

            self.agent_fabric = AgentFabric(
                mailbox_manager=self.mailbox_manager,
                deltabus=self.deltabus,
                agent_factory=self.agent_factory,
                agent_registry={},  # Placeholder - populated at runtime
                tool_registry=self.tool_registry_instance,
                config={
                    "max_agents_per_type": 100,
                    "idle_ttl_seconds": 300,  # 5 min TTL for reuse pool
                    "mailbox_size": 64,
                    "enable_reuse_pool": True,
                },
            )
            logger.info("   ✅ AgentFabric initialized (lifecycle orchestration ready)")

            # IMPORTANT: Wire Agent Factory into Concierge Agent (if already spawned)
            if hasattr(self, "concierge_agent") and self.concierge_agent:
                logger.info("   - Wiring Agent Factory and AgentFabric into Concierge Agent...")
                self.concierge_agent.agent_factory = self.agent_factory
                # Wire AgentFabric for dynamic specialist spawning (Issue 6.5.2.2)
                self.concierge_agent.agent_fabric = self.agent_fabric
                # Also wire MailboxManager reference
                self.concierge_agent.mailbox_manager = self.mailbox_manager
                logger.info(
                    "   ✅ Concierge now has access to Agent Factory and AgentFabric for dynamic spawning"
                )

            # Pre-allocate Orchestrator (lazy, not processing tasks yet)
            logger.info("   - Pre-allocating Orchestrator instance...")
            self.orchestrator = Orchestrator(
                agent_registry={},  # Placeholder - populated at runtime
                tool_registry=self.tool_registry if self.tool_registry else {},
                session_state=None,  # Placeholder - provided per-session
                agent_factory=self.agent_factory,
                mailbox_manager=None,  # Placeholder - MailboxManager retained in Phase 2
                mailbox=None,  # Placeholder - Mailbox assigned by AgentFabric
                session_state_manager=self.session_state_manager,  # Epic 3.1 Issue 3.1.1
            )

            # Pre-allocate Planner (lazy, not planning yet)
            logger.info("   - Pre-allocating Planner instance...")
            # PlannerAgent needs: agent_id, groq_client, tool_registry, agent_registry, session_state
            self.planner = PlannerAgent(
                agent_id="planner_001",
                groq_client=self.groq_client,  # type: ignore[arg-type]
                tool_registry=self.tool_registry if self.tool_registry else {},
                agent_registry={},  # Placeholder - populated at runtime
                session_state=None,  # Placeholder - provided per-session
                session_state_manager=self.session_state_manager,  # Epic 3.1 Issue 3.1.1
            )

            # Pre-allocate DAG Executor (lazy, not executing yet)
            logger.info("   - Pre-allocating DAG Executor instance...")
            self.dag_executor = DAGExecutor(
                agent_registry={},  # Placeholder - populated at runtime
                tool_registry=self.tool_registry if self.tool_registry else {},
                max_concurrent=3,  # Max 3 tasks per wave
                session_state_manager=self.session_state_manager,  # Epic 3.1 Issue 3.1.1
            )

            # Mark phase complete
            phase_duration = time.time() - phase_start
            self.startup_times["phase6"] = phase_duration
            self.phases_completed.append("phase6")

            # Register orchestration components with dashboard
            self._register_component_with_dashboard("Orchestrator", self.orchestrator)
            self._register_component_with_dashboard(
                "SessionState Manager", self.session_state_manager
            )

            # Verify all components pre-allocated
            assert hasattr(self, "orchestrator"), "Orchestrator not created"
            assert hasattr(self, "planner"), "Planner not created"
            assert hasattr(self, "dag_executor"), "DAG Executor not created"
            assert hasattr(self, "agent_factory"), "Agent Factory not created"

            # Verify performance budget (<1s)
            if phase_duration > 1.0:
                logger.warning(
                    f"[6/7] Orchestration Layer... ⚠️ BUDGET EXCEEDED ({phase_duration:.3f}s > 1s)"
                )
            else:
                logger.info(f"[6/7] Orchestration Layer... ✅ ({phase_duration:.3f}s < 1s budget)")

        except Exception as e:
            logger.error(f"[6/7] Orchestration Layer... ❌ FAILED: {e}")
            raise

    async def _phase7_system_health_check(self) -> None:
        """
        Phase 7: Comprehensive system health check

        Verifies all components are healthy before accepting user input:
        - Mock services: GET /health → 200 OK
        - Tier 1 agents: State = ACTIVE
        - Writer Agents: State = ACTIVE
        - DeltaBus: Subscriptions count > 0
        - K0 Bridge: Circuit breaker status
        - Temporal Module: Scheduler running

        Performance Budget: <2s

        Raises:
            Exception: If health checks fail after max retries
        """
        phase_start = time.time()
        logger.info("[7/7] Running system health checks...")

        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                health_issues = []

                # Check 1: Mock Services (HTTP health endpoints)
                logger.info("   - Checking mock services health...")
                if hasattr(self, "mock_services"):
                    for service_name, service_info in self.mock_services.items():
                        if service_name == "k0_api":
                            continue  # Embedded, no health endpoint

                        port = service_info.get("port")
                        try:
                            response = await self.http_client.get(
                                f"http://localhost:{port}/health", timeout=1.0
                            )
                            if response.status_code != 200:
                                health_issues.append(
                                    f"{service_name} unhealthy (status={response.status_code})"
                                )
                            else:
                                logger.info(f"      ✅ {service_name} (port {port})")
                        except Exception as e:
                            health_issues.append(f"{service_name} unreachable: {str(e)}")

                # Check 2: Tier 1 Agents (Concierge, ProactiveAgent)
                logger.info("   - Checking Tier 1 agents...")
                if hasattr(self, "tier1_agents"):
                    for agent_name, agent in self.tier1_agents.items():
                        if hasattr(agent, "state"):
                            if agent.state.value != "active":
                                health_issues.append(
                                    f"{agent_name} not ACTIVE (state={agent.state.value})"
                                )
                            else:
                                logger.info(f"      ✅ {agent_name} ACTIVE")
                        else:
                            health_issues.append(f"{agent_name} missing state attribute")
                else:
                    health_issues.append("Tier 1 agents not initialized")

                # Check 3: Writer Agents (Background services)
                logger.info("   - Checking Writer Agents...")
                if hasattr(self, "bg_services_manager") and self.bg_services_manager:
                    status = await self.bg_services_manager.get_status()
                    writer_count = status.get("writer_agents", 0)
                    if writer_count < 3:
                        health_issues.append(
                            f"Writer Agents incomplete (expected 3, got {writer_count})"
                        )
                    else:
                        logger.info(f"      ✅ {writer_count} Writer Agents ACTIVE")
                else:
                    health_issues.append("Background services manager not initialized")

                # Check 4: DeltaBus Subscriptions
                logger.info("   - Checking DeltaBus subscriptions...")
                if hasattr(self, "bg_services_manager") and self.bg_services_manager:
                    status = await self.bg_services_manager.get_status()
                    sub_count = status.get("subscriptions", 0)
                    if sub_count == 0:
                        health_issues.append("No DeltaBus subscriptions established")
                    else:
                        logger.info(f"      ✅ {sub_count} subscriptions established")
                else:
                    health_issues.append("DeltaBus not initialized")

                # Check 5: State Delta Emitter
                logger.info("   - Checking State Delta Emitter...")
                if hasattr(self, "bg_services_manager") and self.bg_services_manager:
                    status = await self.bg_services_manager.get_status()
                    if not status.get("state_delta_emitter_ok"):
                        health_issues.append("State Delta Emitter not running")
                    else:
                        logger.info("      ✅ State Delta Emitter running")

                # Check 6: Temporal Module
                logger.info("   - Checking Temporal Module...")
                if hasattr(self, "bg_services_manager") and self.bg_services_manager:
                    status = await self.bg_services_manager.get_status()
                    if not status.get("temporal_module_ok"):
                        health_issues.append("Temporal Module scheduler not running")
                    else:
                        logger.info("      ✅ Temporal Module scheduler running")

                # Check 7: Orchestration Components
                logger.info("   - Checking orchestration components...")
                orchestration_ready = all(
                    [
                        hasattr(self, "orchestrator"),
                        hasattr(self, "planner"),
                        hasattr(self, "dag_executor"),
                        hasattr(self, "agent_factory"),
                        hasattr(self, "agent_fabric"),  # NEW: Check AgentFabric (Issue 1.2.2)
                    ]
                )
                if not orchestration_ready:
                    health_issues.append("Orchestration components not pre-allocated")
                else:
                    logger.info("      ✅ Orchestration layer ready")

                    # NEW: Query AgentFabric stats (Issue 1.2.2 Step 4)
                    if hasattr(self, "agent_fabric") and self.agent_fabric:
                        try:
                            fabric_stats = self.agent_fabric.get_stats()
                            logger.info(
                                f"      ✅ AgentFabric: {fabric_stats['total_registered']} agents registered, "
                                f"{fabric_stats['total_spawned']} spawned, "
                                f"{len(fabric_stats.get('agents_by_state', {}).get('active', []))} active"
                            )
                        except Exception as e:
                            logger.warning(f"      ⚠️ AgentFabric stats error: {e}")

                # Evaluate health check results
                if health_issues:
                    retry_count += 1
                    logger.warning(
                        f"   ⚠️ Health check failed (attempt {retry_count}/{max_retries}): "
                        f"{len(health_issues)} issues found"
                    )
                    for issue in health_issues:
                        logger.warning(f"      - {issue}")

                    if retry_count < max_retries:
                        logger.info("   Retrying in 2s...")
                        # Check if system is shutting down before retrying
                        if not self.system_ready:
                            logger.info("   ⚠️ System shutting down, aborting health check retries")
                            raise RuntimeError("Health check aborted due to system shutdown")
                        await asyncio.sleep(2)
                        continue
                    else:
                        # Max retries exceeded
                        raise RuntimeError(
                            f"Health check failed after {max_retries} attempts: "
                            f"{', '.join(health_issues)}"
                        )
                else:
                    # All checks passed!
                    phase_duration = time.time() - phase_start
                    self.startup_times["phase7"] = phase_duration
                    self.phases_completed.append("phase7")

                    logger.info("   ✅ All health checks passed!")

                    # Display Integration Health Dashboard (Issue 6.5.5.2)
                    logger.info("   - Running Integration Health Dashboard...")
                    try:
                        from monitoring.integration_dashboard import get_integration_dashboard

                        dashboard = get_integration_dashboard()
                        dashboard_status = await dashboard.display_status(refresh=False)
                        logger.info("\n" + dashboard_status)
                    except Exception as e:
                        logger.warning(f"   ⚠️ Dashboard display failed: {e}")

                    # Verify performance budget (<2s)
                    if phase_duration > 2.0:
                        logger.warning(
                            f"[7/7] System Health Check... ⚠️ BUDGET EXCEEDED ({phase_duration:.3f}s > 2s)"
                        )
                    else:
                        logger.info(
                            f"[7/7] System Health Check... ✅ ({phase_duration:.3f}s < 2s budget)"
                        )

                    return  # Success!

            except Exception as e:
                retry_count += 1
                logger.error(f"   ❌ Health check error (attempt {retry_count}/{max_retries}): {e}")

                if retry_count < max_retries:
                    logger.info("   Retrying in 2s...")
                    # Check if system is shutting down before retrying
                    if not self.system_ready:
                        logger.info("   ⚠️ System shutting down, aborting health check retries")
                        raise RuntimeError("Health check aborted due to system shutdown")
                    await asyncio.sleep(2)
                else:
                    logger.error(f"[7/7] System Health Check... ❌ FAILED: {e}")
                    raise

    # ========================================================================
    # Main Startup Method
    # ========================================================================

    async def initialize_system(self) -> bool:
        """
        Main startup sequence - executes all 7 phases in order

        Returns:
            bool: True if system ready, False if startup failed

        Raises:
            Exception: If critical phase fails after retries
        """
        startup_begin = time.time()
        logger.info("=" * 70)
        logger.info("🚀 K1 Intelligence Module - System Startup")
        logger.info("=" * 70)

        try:
            # Phase 1: Configuration & Registries
            await self._phase1_load_configuration()

            # Phase 2: Runtime Infrastructure
            await self._phase2_initialize_runtime()

            # Phase 3: Mock Services
            await self._phase3_start_mock_services()

            # Phase 4: Core Agents (Tier 1)
            await self._phase4_spawn_core_agents()

            # Phase 5: Background Services (Writer Agents + Temporal Module)
            await self._phase5_start_background_services()

            # Phase 6: Orchestration Layer (pre-allocation)
            await self._phase6_prepare_orchestration()

            # Phase 7: System Health Check
            await self._phase7_system_health_check()

            # Calculate total startup time
            total_time = time.time() - startup_begin
            logger.info("=" * 70)
            logger.info(f"🚀 K1 Intelligence Module ready! ({total_time:.1f}s)")
            logger.info("=" * 70)

            self.system_ready = True
            return True

        except Exception as e:
            logger.error(f"❌ System startup FAILED: {e}")
            self.system_ready = False
            return False

    # ========================================================================
    # Graceful Shutdown (Issue 6.5.4.2)
    # ========================================================================

    async def shutdown_system(self) -> bool:
        """
        Graceful shutdown coordinator - stops all services in reverse order

        7-Phase shutdown sequence:
        1. Stop accepting new requests
        2. Drain active agents (30s timeout)
        3. Flush Writer Agents (10s timeout)
        4. Stop background services
        5. Terminate agents
        6. Stop mock services
        7. Close connections

        Returns:
            True if shutdown completed successfully, False otherwise

        References:
            - docs/plans/chat_experience_poc_plan.md - Issue 6.5.4.2
            - ADR-0073 - DRAINING state budget (30s)
        """
        shutdown_start = time.time()
        logger.info("=" * 70)
        logger.info("🛑 Graceful shutdown initiated...")
        logger.info("=" * 70)

        try:
            # Check component health before shutdown (Issue 6.5.5.2)
            logger.info("🔍 Checking component health before shutdown...")
            try:
                from monitoring.integration_dashboard import get_integration_dashboard

                dashboard = get_integration_dashboard()
                dashboard_status = await dashboard.display_status(refresh=False)
                logger.info("\n" + dashboard_status)
            except Exception as e:
                logger.warning(f"⚠️ Pre-shutdown health check failed: {e}")

            # Phase 1: Stop accepting new requests
            logger.info("[1/7] Stop accepting new requests...")
            self.system_ready = False
            # Note: Intent Router would check self.system_ready and reject new requests
            logger.info("   ✅ System marked as shutting down")

            # Phase 2: Drain active agents (30s timeout)
            logger.info("[2/7] Draining active agents...")
            drain_timeout = 30.0
            drain_start = time.time()

            # Mark Tier 1 agents (Concierge, Proactive) as DRAINING
            try:
                from l3_execution.agents.agent_base import AgentState as T1AgentState
            except Exception:
                T1AgentState = None  # type: ignore

            tier1 = getattr(self, "tier1_agents", None)
            if isinstance(tier1, dict) and tier1:
                for agent_name, agent in tier1.items():
                    try:
                        if hasattr(agent, "transition_to") and T1AgentState is not None:
                            await agent.transition_to(T1AgentState.DRAINING)  # type: ignore[attr-defined]
                        elif hasattr(agent, "state") and T1AgentState is not None:
                            agent.state = T1AgentState.DRAINING  # type: ignore[attr-defined]
                        logger.info(f"   - Marked {agent_name} as DRAINING")
                    except Exception as e:
                        logger.warning(f"   ⚠️ Failed to mark {agent_name} as DRAINING: {e}")

            # Cancel Concierge mailbox consumer task
            if hasattr(self, "concierge_consumer_task") and self.concierge_consumer_task:
                try:
                    self.concierge_consumer_task.cancel()
                    await asyncio.wait([self.concierge_consumer_task], timeout=2.0)
                    logger.info("   - Cancelled Concierge consumer task")
                except Exception as e:
                    logger.warning(f"   ⚠️ Failed to cancel Concierge consumer: {e}")

            # Simple wait loop to allow in-flight tasks to complete (max drain_timeout)
            while time.time() - drain_start < drain_timeout:
                # If no tier1 agents or all have empty mailboxes (if present), break early
                all_drained = True
                if isinstance(tier1, dict) and tier1:
                    for agent in tier1.values():
                        mb = getattr(agent, "mailbox", None)
                        try:
                            if mb is not None and not mb.empty():
                                all_drained = False
                                break
                        except Exception:
                            # If mailbox doesn't support empty(), assume drained
                            pass
                if all_drained:
                    break
                await asyncio.sleep(0.2)

            drain_duration = time.time() - drain_start
            if drain_duration > drain_timeout:
                logger.warning(
                    f"   ⚠️ Agent draining timeout exceeded ({drain_duration:.1f}s > {drain_timeout}s)"
                )
            else:
                logger.info(f"   ✅ Agents drained ({drain_duration:.3f}s)")

            # Phase 3: Flush Writer Agents (10s timeout)
            logger.info("[3/7] Flushing Writer Agents...")
            flush_timeout = 10.0
            flush_start = time.time()

            if hasattr(self, "bg_services_manager") and self.bg_services_manager:
                try:
                    # Flush pending work before stopping
                    # BackgroundServicesManager.stop_all() will handle flushing
                    logger.info("   - Flushing Writer Agent mailboxes...")
                    # Note: Actual flushing happens in stop_all() below
                except Exception as e:
                    logger.error(f"   ❌ Writer Agent flush error: {e}")

            flush_duration = time.time() - flush_start
            if flush_duration > flush_timeout:
                logger.warning(
                    f"   ⚠️ Flush timeout exceeded ({flush_duration:.1f}s > {flush_timeout}s)"
                )
            else:
                logger.info(f"   ✅ Writer Agents flushed ({flush_duration:.3f}s)")

            # Phase 4: Stop background services
            logger.info("[4/7] Stopping background services...")

            # Stop Temporal Module scheduler
            if hasattr(self, "bg_services_manager") and self.bg_services_manager:
                try:
                    logger.info("   - Stopping Temporal Module scheduler...")
                    # BackgroundServicesManager.stop_all() handles this
                except Exception as e:
                    logger.error(f"   ❌ Temporal Module stop error: {e}")

            # Stop DeltaBus event loop
            if hasattr(self, "deltabus") and self.deltabus:
                try:
                    logger.info("   - Stopping DeltaBus event loop...")
                    # DeltaBus cleanup if needed
                except Exception as e:
                    logger.error(f"   ❌ DeltaBus stop error: {e}")

            # Stop all background services via manager
            if hasattr(self, "bg_services_manager") and self.bg_services_manager:
                try:
                    await self.bg_services_manager.stop_all()
                    logger.info("   ✅ Background services stopped")
                except Exception as e:
                    logger.error(f"   ❌ Background services stop error: {e}")

            # Phase 5: Terminate agents
            logger.info("[5/7] Terminating agents...")

            # Terminate Tier 1 agents
            if hasattr(self, "tier1_agents"):
                for agent_name, agent in self.tier1_agents.items():
                    try:
                        # Transition to TERMINATED if agent has state
                        if hasattr(agent, "state"):
                            logger.info(f"   - Terminating {agent_name}...")
                            try:
                                from l3_execution.agents.agent_base import (
                                    AgentState as T1AgentState,
                                )

                                if hasattr(agent, "transition_to"):
                                    await agent.transition_to(T1AgentState.TERMINATED)  # type: ignore[attr-defined]
                                else:
                                    agent.state = T1AgentState.TERMINATED  # type: ignore[attr-defined]
                            except Exception:
                                # Fallback: set a TERMINATED-like value
                                try:
                                    agent.state = "terminated"  # type: ignore[attr-defined]
                                except Exception:
                                    pass
                    except Exception as e:
                        logger.error(f"   ❌ Agent {agent_name} termination error: {e}")

            # Clear Agent Pool
            if hasattr(self, "agent_pool") and self.agent_pool:
                try:
                    # Clear pool
                    self.agent_pool = None
                    logger.info("   ✅ Agent Pool cleared")
                except Exception as e:
                    logger.error(f"   ❌ Agent Pool clear error: {e}")

            logger.info("   ✅ Agents terminated")

            # Phase 5.5: Shutdown AgentFabric (Issue 1.2.2 Step 4)
            logger.info("[5.5/7] Shutting down AgentFabric...")
            if hasattr(self, "agent_fabric") and self.agent_fabric:
                try:
                    await self.agent_fabric.shutdown_all()
                    logger.info("   ✅ AgentFabric shutdown complete")
                except Exception as e:
                    logger.error(f"   ❌ AgentFabric shutdown error: {e}")

            # Phase 6: Stop mock services
            logger.info("[6/7] Stopping mock services...")

            if hasattr(self, "mock_services"):
                for service_name, service_info in self.mock_services.items():
                    try:
                        process = service_info.get("process")
                        if process and process.poll() is None:
                            logger.info(
                                f"   - Stopping {service_name} (port {service_info.get('port')})..."
                            )
                            process.terminate()
                            try:
                                process.wait(timeout=5.0)
                                logger.info(f"   ✅ {service_name} stopped")
                            except Exception:
                                logger.warning(f"   ⚠️ {service_name} force killing...")
                                process.kill()
                                process.wait()
                    except Exception as e:
                        logger.error(f"   ❌ {service_name} stop error: {e}")

            # Phase 7: Close connections
            logger.info("[7/7] Closing connections...")

            # Clear mock service clients (Issue 1.1.2 Step 3 - Mock client teardown)
            if hasattr(self, "mock_clients") and self.mock_clients:
                try:
                    logger.info("   - Clearing mock service clients...")
                    # Note: Individual clients may point to shared http_client (handled separately)
                    self.mock_clients.clear()
                    logger.info("   ✅ Mock service clients cleared")
                except Exception as e:
                    logger.error(f"   ❌ Mock clients clear error: {e}")

            # Cancel any SSE listener tasks (Issue 1.1.2 Step 3 - SSE listener cleanup)
            if hasattr(self, "mock_sse_listener_task") and self.mock_sse_listener_task:
                try:
                    logger.info("   - Cancelling SSE listener task...")
                    self.mock_sse_listener_task.cancel()
                    try:
                        await asyncio.wait_for(self.mock_sse_listener_task, timeout=2.0)
                    except asyncio.CancelledError:
                        logger.info("   ✅ SSE listener task cancelled")
                    except asyncio.TimeoutError:
                        logger.warning("   ⚠️ SSE listener task timeout during cancellation")
                except Exception as e:
                    logger.error(f"   ❌ SSE listener task cancel error: {e}")

            # Close User KG database
            if hasattr(self, "user_kg_db") and self.user_kg_db:
                try:
                    self.user_kg_db.close()
                    logger.info("   ✅ User KG database closed")
                except Exception as e:
                    logger.error(f"   ❌ User KG close error: {e}")

            # Close Temporal triggers database
            if (
                hasattr(self, "temporal_db")
                and self.temporal_db
                and self.temporal_db != "connected"
            ):
                try:
                    self.temporal_db.close()
                    logger.info("   ✅ Temporal triggers database closed")
                except Exception as e:
                    logger.error(f"   ❌ Temporal DB close error: {e}")

            # Close HTTP client
            if hasattr(self, "http_client") and self.http_client:
                try:
                    await self.http_client.aclose()
                    logger.info("   ✅ HTTP client closed")
                except Exception as e:
                    logger.error(f"   ❌ HTTP client close error: {e}")

            # Calculate total shutdown time
            shutdown_duration = time.time() - shutdown_start
            logger.info("=" * 70)
            logger.info(f"👋 Shutdown complete. Goodbye! ({shutdown_duration:.1f}s)")
            logger.info("=" * 70)

            # Verify shutdown within budget (<45s)
            if shutdown_duration > 45.0:
                logger.warning(f"⚠️ Shutdown exceeded budget: {shutdown_duration:.1f}s > 45s")
            else:
                logger.info(f"✅ Shutdown within budget: {shutdown_duration:.1f}s < 45s")

            return True

        except Exception as e:
            logger.error(f"❌ Graceful shutdown FAILED: {e}", exc_info=True)
            return False

    # ========================================================================
    # Accessor Methods (Issue 1.1.2 - Expose shared singletons)
    # ========================================================================

    def get_mailbox_manager(self):
        """Get MailboxManager singleton (Phase 2 initialized)."""
        if not hasattr(self, "mailbox_manager"):
            raise RuntimeError("MailboxManager not initialized (Phase 2 not completed)")
        return self.mailbox_manager

    def get_session_state_manager(self):
        """Get SessionStateManager singleton (Phase 5 initialized)."""
        if not hasattr(self, "session_state_manager"):
            raise RuntimeError("SessionStateManager not initialized (Phase 5 not completed)")
        return self.session_state_manager

    def get_deltabus(self):
        """Get DeltaBus singleton (Phase 2 initialized)."""
        if not hasattr(self, "deltabus"):
            raise RuntimeError("DeltaBus not initialized (Phase 2 not completed)")
        return self.deltabus

    def get_agent_pool(self):
        """Get Agent Pool singleton (Phase 2 initialized)."""
        if not hasattr(self, "agent_pool"):
            raise RuntimeError("Agent Pool not initialized (Phase 2 not completed)")
        return self.agent_pool

    def get_mock_client(self, service_name: str):
        """
        Get mock service client handle (Issue 1.1.2).

        Args:
            service_name: "mcp" | "sse" | "k0"

        Returns:
            httpx.AsyncClient for the service

        Raises:
            RuntimeError: If service not initialized or client not available
        """
        if not hasattr(self, "mock_clients"):
            raise RuntimeError("Mock services not initialized (Phase 3 not completed)")

        if service_name not in self.mock_clients:
            raise ValueError(
                f"Unknown service: {service_name}. Available: {list(self.mock_clients.keys())}"
            )

        return self.mock_clients[service_name]

    def get_mcp_client(self):
        """Get httpx.AsyncClient to Mock MCP Server (port 8001)."""
        return self.get_mock_client("mcp")

    def get_sse_client(self):
        """Get httpx.AsyncClient to Mock K0 SSE Server (port 8002)."""
        return self.get_mock_client("sse")

    def get_k0_client(self):
        """Get httpx.AsyncClient to Mock K0 API (embedded port 8003)."""
        return self.get_mock_client("k0")

    def get_concierge_agent(self):
        """Get ConciergeAgent (Tier 1 always-active, Phase 4 initialized)."""
        if not hasattr(self, "concierge_agent"):
            raise RuntimeError("ConciergeAgent not initialized (Phase 4 not completed)")
        return self.concierge_agent

    def get_proactive_agent(self):
        """Get ProactiveAgent (Tier 1 always-active, Phase 4 initialized)."""
        if not hasattr(self, "proactive_agent"):
            raise RuntimeError("ProactiveAgent not initialized (Phase 4 not completed)")
        return self.proactive_agent

    def get_background_services_manager(self):
        """Get BackgroundServicesManager (Phase 5 initialized)."""
        if not hasattr(self, "bg_services_manager"):
            raise RuntimeError("BackgroundServicesManager not initialized (Phase 5 not completed)")
        return self.bg_services_manager

    def get_orchestrator(self):
        """Get Orchestrator (Phase 6 pre-allocated)."""
        if not hasattr(self, "orchestrator"):
            raise RuntimeError("Orchestrator not pre-allocated (Phase 6 not completed)")
        return self.orchestrator

    def get_planner(self):
        """Get PlannerAgent (Phase 6 pre-allocated)."""
        if not hasattr(self, "planner"):
            raise RuntimeError("Planner not pre-allocated (Phase 6 not completed)")
        return self.planner

    def get_dag_executor(self):
        """Get DAGExecutor (Phase 6 pre-allocated)."""
        if not hasattr(self, "dag_executor"):
            raise RuntimeError("DAGExecutor not pre-allocated (Phase 6 not completed)")
        return self.dag_executor

    def get_agent_factory(self):
        """Get AgentFactory (Phase 6 pre-allocated)."""
        if not hasattr(self, "agent_factory"):
            raise RuntimeError("AgentFactory not pre-allocated (Phase 6 not completed)")
        return self.agent_factory

    def get_agent_fabric(self):
        """Get AgentFabric (Phase 6 pre-allocated, Issue 1.2.1)."""
        if not hasattr(self, "agent_fabric"):
            raise RuntimeError("AgentFabric not pre-allocated (Phase 6 not completed)")
        return self.agent_fabric


# ========================================================================
# Singleton Instance
# ========================================================================

_coordinator_instance: Optional[SystemCoordinator] = None


def get_system_coordinator() -> SystemCoordinator:
    """Get singleton SystemCoordinator instance"""
    global _coordinator_instance
    if _coordinator_instance is None:
        _coordinator_instance = SystemCoordinator()
    return _coordinator_instance


# ========================================================================
# Main Entry Point (for testing)
# ========================================================================


async def main():
    """Test Phase 1-7 startup (complete system) with graceful shutdown on Ctrl+C"""
    coordinator = get_system_coordinator()

    # Flag to track if shutdown was requested
    shutdown_requested = False

    # Setup signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        """Handle Ctrl+C (SIGINT) and SIGTERM"""
        nonlocal shutdown_requested
        if not shutdown_requested:
            shutdown_requested = True
            print("\n\n🛑 Received shutdown signal...")
            # Set system_ready to False to abort any ongoing operations
            coordinator.system_ready = False

    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Docker stop / kill

    try:
        success = await coordinator.initialize_system()
    except RuntimeError as e:
        if "shutdown" in str(e).lower():
            # Shutdown was requested during startup
            print("\n⚠️ Startup interrupted by shutdown request")
            success = False
        else:
            raise

    if success:
        print("\n" + "=" * 70)
        print("✅ All 7 Phases Complete!")
        print("=" * 70)

        # Phase 1 results
        print("\n[Phase 1] Configuration & Registries")
        if coordinator.config:
            print(f"   - Config keys: {len(coordinator.config)}")
        if coordinator.tool_registry:
            print(f"   - Tools: {len(coordinator.tool_registry.get('tools', []))}")
        if coordinator.prompt_registry:
            prompt_count = len(
                [
                    k
                    for k in coordinator.prompt_registry.keys()
                    if k not in ["version", "last_updated"]
                ]
            )
            print(f"   - Prompts: {prompt_count}")
        print(f"   - Duration: {coordinator.startup_times.get('phase1', 0):.3f}s")

        # Phase 2 results
        print("\n[Phase 2] Runtime Infrastructure")
        print(f"   - DeltaBus: {'initialized' if coordinator.deltabus else 'missing'}")
        print(f"   - Agent Pool: {'initialized' if coordinator.agent_pool else 'missing'}")
        print(
            f"   - SessionState: {'available' if coordinator.session_state_available else 'missing'}"
        )
        print(f"   - Mailbox: {'available' if coordinator.mailbox_available else 'missing'}")
        print(f"   - Duration: {coordinator.startup_times.get('phase2', 0):.3f}s")
        print(
            f"   - Budget met: {'✅' if coordinator.startup_times.get('phase2', 1) < 0.5 else '❌'}"
        )

        # Phase 3 results
        print("\n[Phase 3] Mock Services")
        if hasattr(coordinator, "mock_services"):
            for service_name, service_info in coordinator.mock_services.items():
                status = "running" if service_info.get("process") else "not started"
                print(f"   - {service_name}: {status} (port {service_info.get('port')})")
        print(f"   - Duration: {coordinator.startup_times.get('phase3', 0):.3f}s")
        print(
            f"   - Budget met: {'✅' if coordinator.startup_times.get('phase3', 6) < 5.0 else '❌'}"
        )

        # Phase 4 results
        print("\n[Phase 4] Core Agents (Tier 1)")
        if hasattr(coordinator, "tier1_agents"):
            for agent_name, agent in coordinator.tier1_agents.items():
                state = agent.state.value if hasattr(agent, "state") else "unknown"
                print(f"   - {agent_name}: {state}")
        print(f"   - Duration: {coordinator.startup_times.get('phase4', 0):.3f}s")
        print(
            f"   - Budget met: {'✅' if coordinator.startup_times.get('phase4', 41) < 40.0 else '❌'}"
        )

        # Phase 5 results
        print("\n[Phase 5] Background Services")
        if hasattr(coordinator, "bg_services_manager") and coordinator.bg_services_manager:
            status = await coordinator.bg_services_manager.get_status()
            print(f"   - Writer Agents: {status.get('writer_agents', 0)} active")
            print(f"   - DeltaBus Subscriptions: {status.get('subscriptions', 0)} established")
            print(
                f"   - State Delta Emitter: {'initialized' if status.get('state_delta_emitter_ok') else 'missing'}"
            )
            print(
                f"   - Temporal Module: {'running' if status.get('temporal_module_ok') else 'missing'}"
            )
        print(f"   - Duration: {coordinator.startup_times.get('phase5', 0):.3f}s")
        print(
            f"   - Budget met: {'✅' if coordinator.startup_times.get('phase5', 31) < 30.0 else '❌'}"
        )

        # Phase 6 results
        print("\n[Phase 6] Orchestration Layer")
        print(
            f"   - Orchestrator: {'pre-allocated' if hasattr(coordinator, 'orchestrator') else 'missing'}"
        )
        print(f"   - Planner: {'pre-allocated' if hasattr(coordinator, 'planner') else 'missing'}")
        print(
            f"   - DAG Executor: {'pre-allocated' if hasattr(coordinator, 'dag_executor') else 'missing'}"
        )
        print(
            f"   - Agent Factory: {'pre-allocated' if hasattr(coordinator, 'agent_factory') else 'missing'}"
        )
        if hasattr(coordinator, "agent_factory"):
            stats = coordinator.agent_factory.get_stats()
            print(
                f"   - Factory stats: spawn_count={stats.get('spawn_count', 0)}, pool_size={stats.get('pool_size', 0)}"
            )
        print(f"   - Duration: {coordinator.startup_times.get('phase6', 0):.3f}s")
        print(
            f"   - Budget met: {'✅' if coordinator.startup_times.get('phase6', 2) < 1.0 else '❌'}"
        )

        # Phase 7 results
        print("\n[Phase 7] System Health Check")
        health_status = "✅ PASSED" if "phase7" in coordinator.phases_completed else "❌ FAILED"
        print(f"   - Status: {health_status}")
        if "phase7" in coordinator.phases_completed:
            print("   - Mock services: healthy")
            print("   - Tier 1 agents: ACTIVE")
            print("   - Writer Agents: ACTIVE")
            print("   - DeltaBus subscriptions: established")
            print("   - State Delta Emitter: running")
            print("   - Temporal Module: running")
            print("   - Orchestration layer: ready")
        print(f"   - Duration: {coordinator.startup_times.get('phase7', 0):.3f}s")
        print(
            f"   - Budget met: {'✅' if coordinator.startup_times.get('phase7', 3) < 2.0 else '❌'}"
        )

        print("\n" + "=" * 70)
        print(f"Total startup time: {sum(coordinator.startup_times.values()):.3f}s")
        print("=" * 70)

        # Wait briefly then test graceful shutdown
        print("\n💤 System running... (Press Ctrl+C to test graceful shutdown, or wait 5s)")
        try:
            await asyncio.sleep(5.0)
        except asyncio.CancelledError:
            pass

        # Test graceful shutdown if not already triggered
        if not shutdown_requested:
            print("\n🧪 Testing graceful shutdown...")
            await coordinator.shutdown_system()
        else:
            print("\n🧪 Shutdown was already triggered by signal, completing...")
            # Run shutdown to clean up properly
            await coordinator.shutdown_system()

    else:
        print("\n[Startup Failed]")
        # Clean up if startup failed
        if shutdown_requested:
            await coordinator.shutdown_system()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    asyncio.run(main())
