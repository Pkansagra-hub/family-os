"""
Dynamic Agent Lifecycle Integration (ADR-0086f)

Purpose:
    Integrate dynamic agent creation with existing agent lifecycle (ADR-0005).
    Manages IDLE pool for reactivation (<10ms vs 100ms creation) and implements
    5 termination policies for task-specific vs persistent agents.

Architecture:
    - Factory ↔ hire_fire integration (~400 lines code)
    - create_or_reuse() method with IDLE pool checking
    - IDLE pooling: 60s timeout, LRU eviction, max 3 per session
    - 5 termination policies: IDLE_TIMEOUT, SESSION_END, RESOURCE_PRESSURE, CRASH, MANUAL

Performance Targets:
    - Reactivation: <10ms P95 (vs 100ms creation)
    - Pool hit rate: >60%
    - IDLE timeout: 60s (task-specific agents)

Key Components:
    1. IDLEPoolManager (pool coordination)
    2. create_or_reuse() method (factory integration)
    3. TerminationPolicyEngine (5 policies)
    4. SupervisorIntegration (5s check cycle)

Related ADRs:
    - ADR-0086: Dynamic Agent Creation Subsystem (parent)
    - ADR-0086a: Agent Factory (factory integration)
    - ADR-0005: Agent Lifecycle (FSM integration)
    - ADR-0005b: IDLE Pooling (reuse existing pool)

Research Foundation:
    - Object Pooling Pattern (Gamma et al. 1994)
    - LRU Cache (Belady 1966)

Implementation Status: STUB (M2 - 5 days planned)
"""

from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class TerminationPolicy(Enum):
    """Termination policies for agents."""
    IDLE_TIMEOUT = "IDLE_TIMEOUT"          # Idle >60s (task-specific agents)
    SESSION_END = "SESSION_END"            # Session terminated
    RESOURCE_PRESSURE = "RESOURCE_PRESSURE"  # Memory/accelerator pressure
    CRASH = "CRASH"                        # Agent crashed
    MANUAL = "MANUAL"                      # Manual termination request


@dataclass
class IDLEPoolConfig:
    """Configuration for IDLE pool.
    
    Attributes:
        timeout_seconds: IDLE timeout (60s for task-specific)
        max_agents_per_session: Maximum agents in pool per session (3)
        eviction_policy: LRU eviction when pool full
        persistent_agent_types: Agent types that never timeout
    """
    timeout_seconds: int = 60
    max_agents_per_session: int = 3
    eviction_policy: str = "LRU"
    persistent_agent_types: Optional[List[str]] = None
    
    def __post_init__(self):
        if self.persistent_agent_types is None:
            # Persistent agents: concierge, planner, researcher, safety_watch
            self.persistent_agent_types = [
                "concierge",
                "planner",
                "researcher",
                "safety_watch"
            ]


@dataclass
class PooledAgent:
    """Agent in IDLE pool.
    
    Attributes:
        agent_id: Unique agent identifier
        agent_type: Type of agent
        session_id: Session ownership
        idle_since: Timestamp when became IDLE
        last_active: Last activity timestamp
        reactivation_count: Number of times reactivated
    """
    agent_id: str
    agent_type: str
    session_id: str
    idle_since: datetime
    last_active: datetime
    reactivation_count: int = 0


class IDLEPoolManager:
    """Manages IDLE agent pool for reactivation.
    
    Responsibilities:
        - Track agents in IDLE state
        - Implement create_or_reuse() logic
        - LRU eviction when pool full
        - Apply termination policies
        - Integrate with supervisor (5s check cycle)
    
    Performance: <10ms reactivation, >60% hit rate
    
    Example:
        pool_manager = IDLEPoolManager(config)
        
        # Try to reuse existing IDLE agent
        agent = await pool_manager.create_or_reuse(
            agent_type="health_specialist",
            session_id="session_abc123"
        )
        
        if agent.from_pool:
            print(f"Reactivated in {agent.latency_ms}ms")  # <10ms
        else:
            print(f"Created new in {agent.latency_ms}ms")  # ~100ms
    """
    
    def __init__(self, config: Optional[IDLEPoolConfig] = None):
        """Initialize IDLE pool manager.
        
        Args:
            config: Pool configuration (defaults if None)
        """
        self.config = config or IDLEPoolConfig()
        
        # IDLE pool (agent_id -> PooledAgent)
        self._pool: Dict[str, PooledAgent] = {}
        
        # Session tracking (session_id -> list[agent_id])
        self._session_pool: Dict[str, List[str]] = {}
    
    async def create_or_reuse(
        self,
        agent_type: str,
        session_id: str,
        capabilities: Optional[List[str]] = None
    ) -> Any:
        """Create new agent or reuse from IDLE pool.
        
        Process:
            1. Check IDLE pool for matching agent (agent_type + session_id)
            2. If found: Reactivate (IDLE → ACTIVE) <10ms
            3. If not found: Create new agent via AgentFactory ~100ms
            4. Update pool tracking
        
        Args:
            agent_type: Type of agent to create/reuse
            session_id: Session ID
            capabilities: Optional capability requirements
        
        Returns:
            Agent result with from_pool flag and latency
        
        Performance: <10ms reactivation, ~100ms creation
        """
        # TODO: Implement create_or_reuse logic
        # 1. Check pool for matching agent
        # 2. If found: reactivate (<10ms)
        # 3. If not: call AgentFactory.create_agent()
        # 4. Update tracking
        raise NotImplementedError("create_or_reuse not yet implemented (M2)")
    
    async def add_to_pool(self, agent_id: str, agent_type: str, session_id: str) -> None:
        """Add agent to IDLE pool when transitions to IDLE state.
        
        Args:
            agent_id: Agent identifier
            agent_type: Agent type
            session_id: Session ID
        
        Note: Called by agent lifecycle FSM on ACTIVE → IDLE transition
        """
        # TODO: Implement pool addition
        # 1. Check if persistent (never timeout)
        # 2. Check pool size for session
        # 3. Evict LRU if full
        # 4. Add to pool
        raise NotImplementedError("add_to_pool not yet implemented (M2)")
    
    async def remove_from_pool(self, agent_id: str, policy: TerminationPolicy) -> None:
        """Remove agent from pool and terminate.
        
        Args:
            agent_id: Agent to remove
            policy: Termination policy that triggered removal
        """
        # TODO: Implement pool removal
        # 1. Remove from pool
        # 2. Apply termination policy
        # 3. Update metrics
        raise NotImplementedError("remove_from_pool not yet implemented (M2)")
    
    def _evict_lru_agent(self, session_id: str) -> Optional[str]:
        """Evict least recently used agent from session pool.
        
        Args:
            session_id: Session to evict from
        
        Returns:
            Evicted agent_id or None
        """
        # TODO: Implement LRU eviction
        # 1. Get session agents
        # 2. Sort by last_active
        # 3. Evict oldest
        raise NotImplementedError("LRU eviction not yet implemented (M2)")
    
    async def check_timeouts(self) -> List[str]:
        """Check for timed-out agents (called by supervisor every 5s).
        
        Returns:
            List of agent_ids that timed out
        
        Timeout Rules:
            - Persistent agents: Never timeout
            - Task-specific agents: 60s IDLE timeout
        """
        # TODO: Implement timeout checking
        # 1. Iterate pool
        # 2. Check idle_since
        # 3. Skip persistent agents
        # 4. Return timed-out agents
        raise NotImplementedError("Timeout checking not yet implemented (M2)")
    
    def get_pool_stats(self) -> Dict[str, Any]:
        """Get pool statistics for monitoring.
        
        Returns:
            Dict with pool size, hit rate, reactivation count
        """
        # TODO: Implement stats collection
        raise NotImplementedError("Stats collection not yet implemented (M2)")


# TODO: Implement supporting classes and integration
# - Integration with AgentFactory (ADR-0086a)
# - Integration with hire_fire module (ADR-0005)
# - Integration with supervisor (ADR-0005d)
# - TerminationPolicyEngine (5 policies)
# - Metrics emission (reactivation_latency_ms, pool_hit_rate, timeout_events)
# - WARD test cases (4 test cases planned)
