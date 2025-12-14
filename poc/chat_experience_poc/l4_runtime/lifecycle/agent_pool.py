"""
Agent Pool - IDLE Agent Management

Singleton pool for reusing IDLE agents to avoid spawn latency (~30s → <1ms).
Implements LRU eviction, health checks, and pooling constraints.

Related ADRs:
- ADR-0073: IDLE state pooling with TTL and health checks
"""

import asyncio
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class PooledAgent:
    """
    Metadata for a pooled agent

    Tracks agent state, timestamps, and health for pool management.
    """

    agent_id: str
    agent_type: str
    session_id: Optional[str]
    added_at: float  # timestamp when added to pool
    last_accessed: float  # timestamp of last get_from_pool()
    last_health_check: float  # timestamp of last health check
    health_check_count: int = 0
    is_healthy: bool = True

    def age_seconds(self) -> float:
        """Get age since added to pool (seconds)"""
        return time.time() - self.added_at

    def idle_seconds(self) -> float:
        """Get time since last access (seconds)"""
        return time.time() - self.last_accessed

    def time_since_health_check(self) -> float:
        """Get time since last health check (seconds)"""
        return time.time() - self.last_health_check


@dataclass
class PoolMetrics:
    """
    Pool metrics for observability
    """

    total_adds: int = 0
    total_gets: int = 0
    total_hits: int = 0  # get_from_pool() found agent
    total_misses: int = 0  # get_from_pool() found no agent
    total_evictions: int = 0
    total_health_check_failures: int = 0
    total_ttl_expirations: int = 0

    # Latency tracking
    reuse_latencies: List[float] = field(default_factory=list)  # milliseconds

    def hit_rate(self) -> float:
        """Calculate pool hit rate (0.0 to 1.0)"""
        total = self.total_gets
        if total == 0:
            return 0.0
        return self.total_hits / total

    def avg_reuse_latency(self) -> float:
        """Calculate average reuse latency (milliseconds)"""
        if not self.reuse_latencies:
            return 0.0
        return sum(self.reuse_latencies) / len(self.reuse_latencies)


class AgentPool:
    """
    Singleton pool for managing IDLE agents

    Pooling Constraints (ADR-0073):
    - Max 3 agents per session
    - Max 5 agents globally per type
    - TTL: 10 minutes idle → auto-drain

    Health Checks:
    - Run every 30s on pooled agents
    - Check: model loaded, capabilities valid, mailbox responsive
    - Unhealthy agents removed from pool

    LRU Eviction:
    - When pool full, evict least recently used agent
    """

    _instance: Optional["AgentPool"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return

        self._initialized = True

        # Pool storage: agent_type -> OrderedDict[agent_id, PooledAgent]
        # OrderedDict maintains insertion order for LRU eviction
        self._pools: Dict[str, OrderedDict[str, PooledAgent]] = {}

        # Session tracking: session_id -> Set[agent_id]
        self._session_agents: Dict[str, Set[str]] = {}

        # Metrics
        self._metrics = PoolMetrics()

        # Constraints (from ADR-0073)
        self._max_per_session = 3
        self._max_per_type = 5
        self._ttl_seconds = 600  # 10 minutes
        self._health_check_interval = 30  # 30 seconds

        # Health check task
        self._health_check_task: Optional[asyncio.Task] = None

        logger.info(
            f"[AgentPool] Initialized (max_per_session={self._max_per_session}, "
            f"max_per_type={self._max_per_type}, ttl={self._ttl_seconds}s)"
        )

    async def start_health_checks(self) -> None:
        """
        Start background health check task

        Runs every 30s to check pooled agents for:
        - TTL expiration (10 minutes)
        - Health status (model loaded, capabilities valid)
        """
        if self._health_check_task is not None:
            logger.warning("[AgentPool] Health checks already running")
            return

        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info("[AgentPool] Started health check loop")

    async def stop_health_checks(self) -> None:
        """Stop background health check task"""
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            logger.info("[AgentPool] Stopped health check loop")

    async def _health_check_loop(self) -> None:
        """
        Background health check loop

        Runs every 30s to:
        1. Check TTL expiration (10 minutes)
        2. Run health checks on agents
        3. Remove unhealthy agents
        """
        try:
            while True:
                await asyncio.sleep(self._health_check_interval)
                await self._run_health_checks()
        except asyncio.CancelledError:
            logger.debug("[AgentPool] Health check loop cancelled")

    async def _run_health_checks(self) -> None:
        """
        Run health checks on all pooled agents

        Checks:
        1. TTL expiration (idle > 10 minutes)
        2. Health status (future: model loaded, capabilities valid)
        """
        expired_agents: List[tuple[str, str]] = []  # (agent_type, agent_id)

        for agent_type, pool in self._pools.items():
            for agent_id, pooled_agent in list(pool.items()):
                # Check TTL expiration
                if pooled_agent.idle_seconds() > self._ttl_seconds:
                    logger.info(
                        f"[AgentPool] Agent {agent_id} TTL expired "
                        f"(idle: {pooled_agent.idle_seconds():.1f}s > {self._ttl_seconds}s)"
                    )
                    expired_agents.append((agent_type, agent_id))
                    self._metrics.total_ttl_expirations += 1
                    continue

                # Health check (basic - future: add model/capability checks)
                pooled_agent.last_health_check = time.time()
                pooled_agent.health_check_count += 1

                # Future: Check model loaded, capabilities valid, mailbox responsive
                # For now, all agents pass health check
                if not pooled_agent.is_healthy:
                    logger.warning(f"[AgentPool] Agent {agent_id} failed health check")
                    expired_agents.append((agent_type, agent_id))
                    self._metrics.total_health_check_failures += 1

        # Remove expired/unhealthy agents
        for agent_type, agent_id in expired_agents:
            self.remove_from_pool(agent_id)

        if expired_agents:
            logger.info(f"[AgentPool] Health check removed {len(expired_agents)} agents")

    def add_to_pool(
        self,
        agent_id: str,
        agent_type: str,
        session_id: Optional[str] = None,
    ) -> bool:
        """
        Add IDLE agent to pool

        Checks constraints:
        - Max 3 agents per session
        - Max 5 agents per type

        If pool full, evict LRU agent.

        Args:
            agent_id: Unique agent identifier
            agent_type: Agent type (e.g., "planner", "coder")
            session_id: Optional session identifier

        Returns:
            True if added, False if failed
        """
        # Check session constraint (max 3 per session)
        if session_id:
            session_count = len(self._session_agents.get(session_id, set()))
            if session_count >= self._max_per_session:
                # Check if this agent already in session (replacement)
                if agent_id not in self._session_agents.get(session_id, set()):
                    logger.warning(
                        f"[AgentPool] Session {session_id} at max capacity "
                        f"({session_count}/{self._max_per_session}), cannot add agent {agent_id}"
                    )
                    return False

        # Get or create pool for this agent type
        if agent_type not in self._pools:
            self._pools[agent_type] = OrderedDict()

        pool = self._pools[agent_type]

        # Check type constraint (max 5 per type)
        if len(pool) >= self._max_per_type:
            # Check if this agent already in pool (replacement)
            if agent_id not in pool:
                # Evict LRU agent
                logger.info(
                    f"[AgentPool] Type {agent_type} at max capacity "
                    f"({len(pool)}/{self._max_per_type}), evicting LRU"
                )
                self._evict_lru(agent_type)

        # Create pooled agent metadata
        now = time.time()
        pooled_agent = PooledAgent(
            agent_id=agent_id,
            agent_type=agent_type,
            session_id=session_id,
            added_at=now,
            last_accessed=now,
            last_health_check=now,
        )

        # Add to pool (move to end for LRU)
        pool[agent_id] = pooled_agent
        pool.move_to_end(agent_id)

        # Track session
        if session_id:
            if session_id not in self._session_agents:
                self._session_agents[session_id] = set()
            self._session_agents[session_id].add(agent_id)

        # Update metrics
        self._metrics.total_adds += 1

        logger.info(
            f"[AgentPool] Added agent {agent_id} (type={agent_type}, session={session_id}, "
            f"pool_size={len(pool)}/{self._max_per_type})"
        )

        return True

    def get_from_pool(
        self,
        agent_type: str,
        session_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Retrieve pooled agent from pool

        Returns agent_id if available, None otherwise.
        Updates last_accessed timestamp for LRU.

        Args:
            agent_type: Agent type to retrieve
            session_id: Optional session identifier (prefer same session)

        Returns:
            agent_id if found, None otherwise
        """
        start_time = time.time()

        self._metrics.total_gets += 1

        # Check if pool exists for this type
        pool = self._pools.get(agent_type)
        if not pool:
            self._metrics.total_misses += 1
            logger.debug(f"[AgentPool] No pool for type {agent_type} (miss)")
            return None

        # Prefer agent from same session (if specified)
        if session_id:
            session_agents = self._session_agents.get(session_id, set())
            for agent_id in pool.keys():
                if agent_id in session_agents:
                    # Found agent in same session
                    pooled_agent = pool[agent_id]
                    pooled_agent.last_accessed = time.time()
                    pool.move_to_end(agent_id)  # Move to end for LRU

                    # Calculate reuse latency
                    latency_ms = (time.time() - start_time) * 1000
                    self._metrics.reuse_latencies.append(latency_ms)
                    self._metrics.total_hits += 1

                    logger.info(
                        f"[AgentPool] Retrieved agent {agent_id} from pool "
                        f"(type={agent_type}, session={session_id}, latency={latency_ms:.3f}ms)"
                    )

                    return agent_id

        # No session match, return any agent of this type
        if pool:
            agent_id = next(iter(pool.keys()))
            pooled_agent = pool[agent_id]
            pooled_agent.last_accessed = time.time()
            pool.move_to_end(agent_id)  # Move to end for LRU

            # Calculate reuse latency
            latency_ms = (time.time() - start_time) * 1000
            self._metrics.reuse_latencies.append(latency_ms)
            self._metrics.total_hits += 1

            logger.info(
                f"[AgentPool] Retrieved agent {agent_id} from pool "
                f"(type={agent_type}, latency={latency_ms:.3f}ms)"
            )

            return agent_id

        # No agents available
        self._metrics.total_misses += 1
        logger.debug(f"[AgentPool] No agents in pool for type {agent_type} (miss)")
        return None

    def remove_from_pool(self, agent_id: str) -> bool:
        """
        Remove agent from pool

        Args:
            agent_id: Agent to remove

        Returns:
            True if removed, False if not found
        """
        # Find agent in pools
        for agent_type, pool in self._pools.items():
            if agent_id in pool:
                pooled_agent = pool[agent_id]
                del pool[agent_id]

                # Remove from session tracking
                if pooled_agent.session_id:
                    session_agents = self._session_agents.get(pooled_agent.session_id)
                    if session_agents:
                        session_agents.discard(agent_id)
                        if not session_agents:
                            del self._session_agents[pooled_agent.session_id]

                logger.info(
                    f"[AgentPool] Removed agent {agent_id} from pool "
                    f"(type={agent_type}, age={pooled_agent.age_seconds():.1f}s)"
                )

                return True

        logger.warning(f"[AgentPool] Agent {agent_id} not found in pool")
        return False

    def _evict_lru(self, agent_type: str) -> Optional[str]:
        """
        Evict least recently used agent from pool

        Args:
            agent_type: Agent type pool to evict from

        Returns:
            evicted agent_id, or None if pool empty
        """
        pool = self._pools.get(agent_type)
        if not pool:
            return None

        # OrderedDict maintains insertion order, first item is LRU
        agent_id = next(iter(pool.keys()))
        pooled_agent = pool[agent_id]

        logger.info(
            f"[AgentPool] Evicting LRU agent {agent_id} "
            f"(type={agent_type}, age={pooled_agent.age_seconds():.1f}s, "
            f"idle={pooled_agent.idle_seconds():.1f}s)"
        )

        self.remove_from_pool(agent_id)
        self._metrics.total_evictions += 1

        return agent_id

    def pool_size(self, agent_type: Optional[str] = None) -> int:
        """
        Get pool size

        Args:
            agent_type: If specified, return size for this type. Otherwise, total size.

        Returns:
            Number of pooled agents
        """
        if agent_type:
            pool = self._pools.get(agent_type)
            return len(pool) if pool else 0
        else:
            return sum(len(pool) for pool in self._pools.values())

    def get_metrics(self) -> PoolMetrics:
        """Get pool metrics for observability"""
        return self._metrics

    def get_pooled_agents(self, agent_type: Optional[str] = None) -> List[PooledAgent]:
        """
        Get list of pooled agents

        Args:
            agent_type: If specified, return agents for this type. Otherwise, all agents.

        Returns:
            List of PooledAgent metadata
        """
        if agent_type:
            pool = self._pools.get(agent_type)
            return list(pool.values()) if pool else []
        else:
            agents = []
            for pool in self._pools.values():
                agents.extend(pool.values())
            return agents

    def clear_pool(self, agent_type: Optional[str] = None) -> int:
        """
        Clear pool (for testing)

        Args:
            agent_type: If specified, clear only this type. Otherwise, clear all.

        Returns:
            Number of agents removed
        """
        if agent_type:
            pool = self._pools.get(agent_type)
            if pool:
                count = len(pool)
                pool.clear()
                # Clear session tracking for these agents
                for session_id, agents in list(self._session_agents.items()):
                    self._session_agents[session_id] = {a for a in agents if a not in pool}
                    if not self._session_agents[session_id]:
                        del self._session_agents[session_id]
                logger.info(f"[AgentPool] Cleared pool for type {agent_type} ({count} agents)")
                return count
            return 0
        else:
            count = sum(len(pool) for pool in self._pools.values())
            self._pools.clear()
            self._session_agents.clear()
            logger.info(f"[AgentPool] Cleared all pools ({count} agents)")
            return count

    def __repr__(self) -> str:
        return (
            f"AgentPool(total_agents={self.pool_size()}, "
            f"hit_rate={self._metrics.hit_rate():.2%}, "
            f"avg_reuse_latency={self._metrics.avg_reuse_latency():.3f}ms)"
        )
