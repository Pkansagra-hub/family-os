"""
Agent Factory Pattern (ADR-0086a)

Purpose:
    Singleton factory for dynamic agent creation. Creates agents on-demand based on
    user requests (e.g., "health specialist", "code assistant"). Provides O(1) lookup
    and <100ms P95 creation time.

Architecture:
    - AgentFactory singleton class (~500 lines implementation)
    - ID generation: `agent-{session_id}-{timestamp_ms}-{counter:06d}`
    - O(1) hash table lookup by agent_id
    - Integration with ResourceReserver, TemplateLoader, CompositionEngine

Performance Targets:
    - Agent creation: <100ms P95
    - Agent lookup: <1ms P95
    - Factory overhead: <5ms

Key Components:
    1. AgentFactory (singleton)
    2. AgentIDGenerator (unique ID generation)
    3. AgentRegistry (O(1) lookup hash table)
    4. ResourceIntegration (thermal-aware placement)

Related ADRs:
    - ADR-0086: Dynamic Agent Creation Subsystem (parent)
    - ADR-0086b: Template System (template consumer)
    - ADR-0086c: Resource Reservation (resource allocation)
    - ADR-0086d: Composition Pattern (agent composition)
    - ADR-0005: Agent Lifecycle (FSM integration)

Research Foundation:
    - Singleton Pattern (Gamma et al. 1994 - Design Patterns)
    - Factory Pattern (Gamma et al. 1994)
    - Actor Model (Hewitt 1973)

Implementation Status: STUB (M1 - 6 days planned)
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime
import threading


@dataclass
class AgentCreationRequest:
    """Request to create a new agent dynamically.
    
    Attributes:
        agent_type: Type of agent to create (e.g., "health_specialist", "code_assistant")
        session_id: Session ID for agent ownership
        requested_capabilities: List of required capabilities
        resource_hints: Optional resource placement hints (NPU/GPU/CPU/Remote)
    """
    agent_type: str
    session_id: str
    requested_capabilities: list[str]
    resource_hints: Optional[Dict[str, Any]] = None


@dataclass
class AgentCreationResult:
    """Result of agent creation operation.
    
    Attributes:
        agent_id: Unique agent identifier
        agent_type: Type of created agent
        state: Current FSM state (PENDING/WARMING/ACTIVE)
        creation_latency_ms: Time taken to create agent
        accelerator_placement: Assigned accelerator (NPU/GPU/CPU/Remote)
    """
    agent_id: str
    agent_type: str
    state: str
    creation_latency_ms: float
    accelerator_placement: str


class AgentFactory:
    """Singleton factory for dynamic agent creation.
    
    Responsibilities:
        - Create agents on-demand based on user requests
        - Generate unique agent IDs
        - O(1) agent lookup by ID
        - Integrate with resource reservation and composition
        - Track active agents per session (max 3)
    
    Thread Safety: Thread-safe singleton with lock
    Performance: <100ms creation, <1ms lookup
    
    Example:
        factory = AgentFactory.get_instance()
        request = AgentCreationRequest(
            agent_type="health_specialist",
            session_id="session_abc123",
            requested_capabilities=["MEMORY_READ", "TOOL_CALL"]
        )
        result = await factory.create_agent(request)
        print(f"Created agent: {result.agent_id}")
    """
    
    _instance: Optional['AgentFactory'] = None
    _lock: threading.Lock = threading.Lock()
    
    def __init__(self):
        """Private constructor. Use get_instance() instead."""
        if AgentFactory._instance is not None:
            raise RuntimeError("Use AgentFactory.get_instance() instead")
        
        # Agent registry (agent_id -> AgentMetadata)
        self._agents: Dict[str, Any] = {}
        
        # Session tracking (session_id -> list[agent_id])
        self._session_agents: Dict[str, list[str]] = {}
        
        # ID counter for uniqueness
        self._id_counter: int = 0
        self._counter_lock: threading.Lock = threading.Lock()
    
    @classmethod
    def get_instance(cls) -> 'AgentFactory':
        """Get singleton instance of AgentFactory.
        
        Returns:
            AgentFactory singleton instance
        
        Thread Safety: Thread-safe double-checked locking
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def _generate_agent_id(self, session_id: str) -> str:
        """Generate unique agent ID.
        
        Format: agent-{session_id}-{timestamp_ms}-{counter:06d}
        
        Args:
            session_id: Session ID for agent
        
        Returns:
            Unique agent ID string
        
        Example: "agent-session_abc123-1729728000000-000001"
        """
        with self._counter_lock:
            self._id_counter += 1
            counter = self._id_counter
        
        timestamp_ms = int(datetime.now().timestamp() * 1000)
        return f"agent-{session_id}-{timestamp_ms}-{counter:06d}"
    
    async def create_agent(self, request: AgentCreationRequest) -> AgentCreationResult:
        """Create a new agent dynamically.
        
        Process:
            1. Validate session capacity (max 3 agents per session)
            2. Generate unique agent ID
            3. Reserve resources (via ResourceReserver)
            4. Load agent template (via TemplateLoader)
            5. Compose agent (via CompositionEngine)
            6. Spawn agent process/thread
            7. Register agent in lookup table
        
        Args:
            request: Agent creation request
        
        Returns:
            AgentCreationResult with agent_id and metadata
        
        Raises:
            ResourceExhaustedError: No resources available
            TemplateNotFoundError: Agent template not found
            SessionCapacityError: Session has max 3 agents already
        
        Performance: <100ms P95
        """
        # TODO: Implement agent creation logic
        # 1. Validate session capacity
        # 2. Generate agent ID
        # 3. Reserve resources (call ResourceReserver)
        # 4. Load template (call TemplateLoader)
        # 5. Compose agent (call CompositionEngine)
        # 6. Spawn agent (integrate with hire_fire module)
        # 7. Register agent
        raise NotImplementedError("Agent creation not yet implemented (M1)")
    
    def lookup_agent(self, agent_id: str) -> Optional[Any]:
        """Lookup agent by ID (O(1) hash table lookup).
        
        Args:
            agent_id: Unique agent identifier
        
        Returns:
            AgentMetadata if found, None otherwise
        
        Performance: <1ms P95
        """
        return self._agents.get(agent_id)
    
    def get_session_agents(self, session_id: str) -> list[str]:
        """Get all agent IDs for a session.
        
        Args:
            session_id: Session identifier
        
        Returns:
            List of agent IDs belonging to session
        """
        return self._session_agents.get(session_id, [])


# TODO: Implement supporting classes
# - AgentMetadata: Store agent state, type, capabilities, resources
# - ResourceExhaustedError, TemplateNotFoundError, SessionCapacityError exceptions
# - Integration with ResourceReserver (ADR-0086c)
# - Integration with TemplateLoader (ADR-0086b)
# - Integration with CompositionEngine (ADR-0086d)
# - Integration with hire_fire module (ADR-0005)
# - WARD test cases (7 test cases planned)
