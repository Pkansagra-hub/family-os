"""
Agent Registry Extension for Dynamic Agents (ADR-0086g)

Purpose:
    Extend agent_fabric.registry to support dynamic agent lookups by type,
    session, state, and capabilities. Enables O(1) multi-index queries for
    efficient agent discovery and resource management.

Architecture:
    - Multi-index registry (~350 lines code)
    - 5 indexes: type, session, state, capability, primary (agent_id)
    - 58+ agent type specifications in YAML
    - Thread-safe with RLock

Performance Targets:
    - Primary lookup (agent_id): O(1), <1ms P95
    - Type lookup: O(1), <1ms P95
    - Combined queries (type + session + state): <2ms P95
    - Cardinality: <500 agents per session

Key Indexes:
    1. Primary: agent_id → AgentRecord (O(1))
    2. Type: agent_type → set[agent_id] (O(1))
    3. Session: session_id → set[agent_id] (O(1))
    4. State: AgentState → set[agent_id] (O(1))
    5. Capability: Capability → set[agent_id] (O(1))

Related ADRs:
    - ADR-0086: Dynamic Agent Creation Subsystem (parent)
    - ADR-0086a: Agent Factory (creates agents to register)
    - ADR-0086d: Agent Composition (capability lookups)
    - ADR-0005: Agent Lifecycle (state tracking)

Research Foundation:
    - Multi-Index Containers (Boost C++ Libraries)
    - Inverted Index (Zobel & Moffat 2006)

Implementation Status: STUB (M2 - 4 days planned)
"""

from typing import Dict, Set, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
from threading import RLock
from datetime import datetime


class AgentState(Enum):
    """Agent lifecycle states."""
    PENDING = "PENDING"
    WARMING = "WARMING"
    ACTIVE = "ACTIVE"
    IDLE = "IDLE"
    DRAINING = "DRAINING"
    TERMINATED = "TERMINATED"


class Capability(Enum):
    """Agent capabilities for composition."""
    TOOL_CALL = "TOOL_CALL"
    MEMORY_READ = "MEMORY_READ"
    MEMORY_WRITE = "MEMORY_WRITE"
    MODEL_CALL = "MODEL_CALL"
    NETWORK_ACCESS = "NETWORK_ACCESS"
    FILE_ACCESS = "FILE_ACCESS"
    SHELL_EXEC = "SHELL_EXEC"


@dataclass
class AgentRecord:
    """Agent registry record.
    
    Attributes:
        agent_id: Unique identifier (agent-{session}-{ts}-{counter})
        agent_type: Type name (health_specialist, code_assistant, etc.)
        session_id: Owning session
        state: Current lifecycle state
        capabilities: Granted capabilities
        created_at: Creation timestamp
        memory_mb: Allocated memory
        accelerator: Assigned accelerator (NPU/GPU/CPU/REMOTE)
    """
    agent_id: str
    agent_type: str
    session_id: str
    state: AgentState
    capabilities: Set[Capability]
    created_at: datetime
    memory_mb: int
    accelerator: str


@dataclass
class AgentTypeSpec:
    """Agent type specification from YAML.
    
    Attributes:
        type_name: Type identifier
        display_name: Human-readable name
        description: Type description
        base_template: Base template to extend (or null for root)
        default_capabilities: Default capability set
        default_memory_mb: Default memory allocation
        preferred_accelerator: Preferred accelerator type
        persistent: Whether agent persists beyond session
    """
    type_name: str
    display_name: str
    description: str
    base_template: Optional[str]
    default_capabilities: Set[Capability]
    default_memory_mb: int
    preferred_accelerator: str
    persistent: bool = False


class DynamicAgentRegistry:
    """Multi-index registry for dynamic agents.
    
    Responsibilities:
        - Register/unregister agents
        - O(1) lookups by agent_id, type, session, state, capability
        - Combined queries (type + session + state)
        - Thread-safe operations with RLock
        - Type specification loading from YAML
    
    Performance: <1ms single index, <2ms combined queries
    
    Example:
        registry = DynamicAgentRegistry()
        
        # Register agent
        record = AgentRecord(
            agent_id="agent-abc-1234567890-000001",
            agent_type="health_specialist",
            session_id="session_abc",
            state=AgentState.ACTIVE,
            capabilities={Capability.TOOL_CALL, Capability.MEMORY_READ},
            created_at=datetime.now(),
            memory_mb=128,
            accelerator="NPU"
        )
        registry.register(record)
        
        # Lookup by ID (O(1))
        agent = registry.get_by_id("agent-abc-1234567890-000001")
        
        # Lookup by type (O(1))
        health_agents = registry.get_by_type("health_specialist")
        
        # Combined query (<2ms)
        active_health_agents = registry.query(
            agent_type="health_specialist",
            session_id="session_abc",
            state=AgentState.ACTIVE
        )
    """
    
    def __init__(self):
        """Initialize multi-index registry."""
        # Primary index: agent_id → AgentRecord
        self._agents: Dict[str, AgentRecord] = {}
        
        # Secondary indexes
        self._by_type: Dict[str, Set[str]] = {}      # agent_type → set[agent_id]
        self._by_session: Dict[str, Set[str]] = {}   # session_id → set[agent_id]
        self._by_state: Dict[AgentState, Set[str]] = {}  # state → set[agent_id]
        self._by_capability: Dict[Capability, Set[str]] = {}  # capability → set[agent_id]
        
        # Type specifications (loaded from YAML)
        self._type_specs: Dict[str, AgentTypeSpec] = {}
        
        # Thread safety
        self._lock = RLock()
    
    def register(self, record: AgentRecord) -> None:
        """Register agent in all indexes.
        
        Args:
            record: Agent record to register
        
        Raises:
            ValueError: If agent_id already exists
        """
        with self._lock:
            # TODO: Implement registration
            # 1. Check if agent_id exists
            # 2. Add to primary index
            # 3. Add to all secondary indexes
            # 4. Update metrics
            raise NotImplementedError("register not yet implemented (M2)")
    
    def unregister(self, agent_id: str) -> Optional[AgentRecord]:
        """Unregister agent from all indexes.
        
        Args:
            agent_id: Agent to unregister
        
        Returns:
            Unregistered record or None if not found
        """
        with self._lock:
            # TODO: Implement unregistration
            # 1. Remove from primary index
            # 2. Remove from all secondary indexes
            # 3. Update metrics
            raise NotImplementedError("unregister not yet implemented (M2)")
    
    def get_by_id(self, agent_id: str) -> Optional[AgentRecord]:
        """Get agent by ID (O(1)).
        
        Args:
            agent_id: Agent identifier
        
        Returns:
            Agent record or None
        
        Performance: <1ms P95
        """
        with self._lock:
            return self._agents.get(agent_id)
    
    def get_by_type(self, agent_type: str) -> List[AgentRecord]:
        """Get all agents of a specific type (O(1)).
        
        Args:
            agent_type: Type name
        
        Returns:
            List of agent records
        
        Performance: <1ms P95
        """
        with self._lock:
            # TODO: Implement type lookup
            # 1. Get agent_ids from _by_type
            # 2. Fetch records from primary index
            raise NotImplementedError("get_by_type not yet implemented (M2)")
    
    def get_by_session(self, session_id: str) -> List[AgentRecord]:
        """Get all agents in a session (O(1)).
        
        Args:
            session_id: Session identifier
        
        Returns:
            List of agent records
        
        Performance: <1ms P95
        """
        with self._lock:
            # TODO: Implement session lookup
            raise NotImplementedError("get_by_session not yet implemented (M2)")
    
    def get_by_state(self, state: AgentState) -> List[AgentRecord]:
        """Get all agents in a specific state (O(1)).
        
        Args:
            state: Agent state
        
        Returns:
            List of agent records
        
        Performance: <1ms P95
        """
        with self._lock:
            # TODO: Implement state lookup
            raise NotImplementedError("get_by_state not yet implemented (M2)")
    
    def get_by_capability(self, capability: Capability) -> List[AgentRecord]:
        """Get all agents with a specific capability (O(1)).
        
        Args:
            capability: Required capability
        
        Returns:
            List of agent records
        
        Performance: <1ms P95
        """
        with self._lock:
            # TODO: Implement capability lookup
            raise NotImplementedError("get_by_capability not yet implemented (M2)")
    
    def query(
        self,
        agent_type: Optional[str] = None,
        session_id: Optional[str] = None,
        state: Optional[AgentState] = None,
        capability: Optional[Capability] = None
    ) -> List[AgentRecord]:
        """Combined multi-index query.
        
        Args:
            agent_type: Filter by type
            session_id: Filter by session
            state: Filter by state
            capability: Filter by capability
        
        Returns:
            List of matching agent records
        
        Performance: <2ms P95 for combined queries
        
        Example:
            # Find all ACTIVE health specialists in session
            agents = registry.query(
                agent_type="health_specialist",
                session_id="session_abc",
                state=AgentState.ACTIVE
            )
        """
        with self._lock:
            # TODO: Implement combined query
            # 1. Get candidate sets from each index
            # 2. Compute intersection
            # 3. Fetch records
            raise NotImplementedError("query not yet implemented (M2)")
    
    def update_state(self, agent_id: str, new_state: AgentState) -> bool:
        """Update agent state (must update state index).
        
        Args:
            agent_id: Agent to update
            new_state: New state
        
        Returns:
            True if updated, False if not found
        """
        with self._lock:
            # TODO: Implement state update
            # 1. Get record
            # 2. Remove from old state index
            # 3. Update record
            # 4. Add to new state index
            raise NotImplementedError("update_state not yet implemented (M2)")
    
    def load_type_specs(self, spec_file: str) -> int:
        """Load agent type specifications from YAML.
        
        Args:
            spec_file: Path to YAML file with 58+ type specs
        
        Returns:
            Number of specs loaded
        
        Format:
            agent_types:
              - type_name: health_specialist
                display_name: "Health Specialist"
                description: "Analyzes health metrics..."
                base_template: base_ai_agent
                default_capabilities: [TOOL_CALL, MEMORY_READ]
                default_memory_mb: 128
                preferred_accelerator: NPU
                persistent: false
        """
        # TODO: Implement YAML loading
        # 1. Load YAML file
        # 2. Parse type specs
        # 3. Store in _type_specs
        raise NotImplementedError("load_type_specs not yet implemented (M2)")
    
    def get_type_spec(self, agent_type: str) -> Optional[AgentTypeSpec]:
        """Get type specification.
        
        Args:
            agent_type: Type name
        
        Returns:
            Type specification or None
        """
        return self._type_specs.get(agent_type)
    
    def get_registry_stats(self) -> Dict[str, Any]:
        """Get registry statistics for monitoring.
        
        Returns:
            Dict with counts by type/session/state/capability
        """
        with self._lock:
            # TODO: Implement stats collection
            raise NotImplementedError("get_registry_stats not yet implemented (M2)")


# TODO: Implement integration with existing registry
# - Extend k1/l4_runtime/agent_fabric/registry.py
# - Add multi-index support
# - Add type specification loading
# - Add combined query methods
# - Add metrics emission (lookup_latency_ms, registry_size, index_sizes)
# - WARD test cases (5 test cases planned)
