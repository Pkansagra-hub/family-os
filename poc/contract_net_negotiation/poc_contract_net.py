"""
PoC 2.1: Contract Net Negotiation - 50ms Proposal Collection

Objective: Prove <50ms proposal collection timeout with 10+ agents

Module: k1/l2_orchestration/orchestrator/negotiation.py

Reference ADR: ADR-0006 (3-Phase Orchestration with Contract Net Protocol)

This PoC validates the negotiation phase of the 3-phase orchestration pipeline:
1. Task announcement broadcast to agents
2. Agents evaluate and submit bids (proposals) 
3. Proposals collected with 50ms deadline

Performance SLO Target: <50ms P95 proposal collection latency
"""

import asyncio
import time
import random
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from uuid import uuid4
from enum import Enum
import numpy as np


# ============================================================================
# Data Models (from ADR-0006)
# ============================================================================

class AgentState(Enum):
    """Agent lifecycle states (from ADR-0005)"""
    PENDING = "PENDING"
    WARMING = "WARMING"
    ACTIVE = "ACTIVE"
    IDLE = "IDLE"
    DRAINING = "DRAINING"
    TERMINATED = "TERMINATED"


@dataclass
class TaskAnnouncement:
    """
    Task broadcast to agents for bidding
    
    Research: Contract Net Protocol (Smith, 1980)
    """
    task_id: str
    turn_plan: dict = field(default_factory=dict)
    requirements: Dict = field(default_factory=dict)
    deadline_ms: int = 50
    trace_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass
class Proposal:
    """
    Agent's bid for task execution
    
    Research: Contract Net Protocol (Smith, 1980)
    """
    agent_id: str
    task_id: str
    estimated_latency_ms: int
    estimated_cost: float
    confidence: float  # 0.0-1.0
    strategy: str  # "parallel" | "sequential" | "hybrid"
    tools_required: List[str] = field(default_factory=list)
    reasoning: str = ""
    submission_time_ms: float = 0.0  # For latency measurement


@dataclass
class ExecutionEstimate:
    """Estimated cost and latency for plan execution"""
    latency_ms: int
    cost: float
    tools: List[str] = field(default_factory=list)
    parallelizable: bool = False


# ============================================================================
# Mock Agent (Bidder Side)
# ============================================================================

class MockAgent:
    """
    Simulated agent that can receive task announcements and submit bids
    """
    
    def __init__(self, agent_id: str, bid_latency_ms: float = 10.0, 
                 bid_probability: float = 0.9, capabilities: Optional[List[str]] = None):
        """
        Args:
            agent_id: Unique agent identifier (e.g., "agent_0", "agent_1")
            bid_latency_ms: Simulated time to prepare bid (realism)
            bid_probability: Probability this agent will bid (0.0-1.0)
            capabilities: Tools this agent has (e.g., ["web_search", "calculator"])
        """
        self.agent_id = agent_id
        self.bid_latency_ms = bid_latency_ms
        self.bid_probability = bid_probability
        self.capabilities = capabilities or ["web_search", "calculator", "email"]
        self.state = AgentState.ACTIVE
        self.bid_count = 0
        self.success_rate = 0.85 + random.uniform(0, 0.1)  # 85-95%
        
    async def handle_task_announcement(self, announcement: TaskAnnouncement) -> Optional[Proposal]:
        """
        Evaluate task and submit bid if capable
        
        Returns: Proposal if bidding, None if declining
        """
        # Simulate processing time (network latency, decision making)
        await asyncio.sleep(self.bid_latency_ms / 1000.0)
        
        # Stochastic bidding: agent may decline even if capable
        if random.random() > self.bid_probability:
            return None
        
        # Check capability match
        required_tools = set(announcement.requirements.get("tools", []))
        if not required_tools.issubset(set(self.capabilities)):
            return None
        
        # Calculate confidence based on success rate and capability match
        confidence = self.success_rate * (1.0 - random.uniform(0, 0.2))
        confidence = min(1.0, max(0.0, confidence))
        
        # Estimate execution metrics
        estimate = self._estimate_execution(announcement)
        
        # Create proposal (bid)
        proposal = Proposal(
            agent_id=self.agent_id,
            task_id=announcement.task_id,
            estimated_latency_ms=estimate.latency_ms,
            estimated_cost=estimate.cost,
            confidence=confidence,
            strategy="parallel" if random.random() > 0.5 else "sequential",
            tools_required=list(required_tools),
            reasoning=f"Agent {self.agent_id} ready to execute task",
            submission_time_ms=time.perf_counter() * 1000,
        )
        
        self.bid_count += 1
        return proposal
    
    def _estimate_execution(self, announcement: TaskAnnouncement) -> ExecutionEstimate:
        """Estimate latency and cost for task execution"""
        # Simulate latency estimate based on agent's speed
        base_latency = random.randint(50, 200)
        latency_variance = random.uniform(0.8, 1.2)
        
        # Simulate cost estimate
        cost = random.uniform(0.1, 1.0)
        
        tools = announcement.requirements.get("tools", [])
        
        return ExecutionEstimate(
            latency_ms=int(base_latency * latency_variance),
            cost=cost,
            tools=tools,
            parallelizable=random.random() > 0.3,  # 70% can parallelize
        )


# ============================================================================
# Negotiator (Orchestrator Side)
# ============================================================================

class ContractNetNegotiator:
    """
    Phase 1: Broadcast task announcements and collect proposals
    
    Research: Contract Net Protocol (Smith, 1980)
    """
    
    def __init__(self, num_agents: int = 20):
        """
        Args:
            num_agents: Number of agents to create for the PoC
        """
        self.agents: List[MockAgent] = []
        self.num_agents = num_agents
        self.proposal_queue: asyncio.Queue = None
        self.negotiation_count = 0
        
        # Metrics
        self.negotiation_times_ms: List[float] = []
        self.proposal_counts: List[int] = []
        self.successful_negotiations: int = 0
        
        # Create agent pool
        self._create_agent_pool()
    
    def _create_agent_pool(self):
        """Create mock agents with varied characteristics"""
        for i in range(self.num_agents):
            agent = MockAgent(
                agent_id=f"agent_{i}",
                bid_latency_ms=random.uniform(5, 20),  # 5-20ms to prepare bid
                bid_probability=random.uniform(0.7, 1.0),  # 70-100% bid
                capabilities=random.sample(
                    ["web_search", "calculator", "email", "calendar", "payment", "booking"],
                    k=random.randint(2, 5)
                )
            )
            self.agents.append(agent)
    
    async def negotiate(self, turn_plan: dict, deadline_ms: int = 50, 
                       trace_id: Optional[str] = None) -> List[Proposal]:
        """
        Broadcast task and collect proposals with deadline
        
        Args:
            turn_plan: Plan from Planner (steps, dependencies)
            deadline_ms: Proposal collection timeout (50ms target)
            trace_id: Cognitive trace ID for observability
            
        Returns: List of proposals received within deadline
        """
        if trace_id is None:
            trace_id = str(uuid4())
        
        self.proposal_queue = asyncio.Queue()
        self.negotiation_count += 1
        
        # 1. Create task announcement
        announcement = TaskAnnouncement(
            task_id=f"task_{self.negotiation_count}",
            turn_plan=turn_plan,
            requirements={
                "tools": turn_plan.get("required_tools", ["web_search", "calculator"]),
                "latency_budget_ms": 500,
                "cost_budget": 5.0,
            },
            deadline_ms=deadline_ms,
            trace_id=trace_id,
        )
        
        # Get active agents
        active_agents = [a for a in self.agents if a.state == AgentState.ACTIVE]
        
        if len(active_agents) == 0:
            print(f"[{trace_id}] WARNING: No active agents available")
            return []
        
        # 2. Broadcast to all active agents (non-blocking)
        broadcast_tasks = [
            self._broadcast_to_agent(agent, announcement, trace_id)
            for agent in active_agents
        ]
        
        # 3. Start collecting proposals with deadline
        start_time = time.perf_counter()
        
        # Launch broadcast and collection concurrently
        await asyncio.gather(*broadcast_tasks)
        
        # 4. Collect proposals until deadline
        proposals = await self._collect_proposals_with_deadline(
            announcement.task_id,
            deadline_ms,
            trace_id
        )
        
        # Calculate negotiation duration
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        # Record metrics
        self.negotiation_times_ms.append(duration_ms)
        self.proposal_counts.append(len(proposals))
        if len(proposals) > 0:
            self.successful_negotiations += 1
        
        print(f"[{trace_id}] Negotiation complete: {len(proposals)} proposals, "
              f"{duration_ms:.2f}ms latency")
        
        return proposals
    
    async def _broadcast_to_agent(self, agent: MockAgent, 
                                 announcement: TaskAnnouncement, 
                                 trace_id: str):
        """Broadcast task announcement to single agent"""
        try:
            proposal = await agent.handle_task_announcement(announcement)
            if proposal:
                await self.proposal_queue.put(proposal)
        except Exception as e:
            print(f"[{trace_id}] ERROR: Agent {agent.agent_id} failed: {e}")
    
    async def _collect_proposals_with_deadline(self, task_id: str, 
                                              deadline_ms: int,
                                              trace_id: str) -> List[Proposal]:
        """
        Collect proposals from agents with timeout
        
        Args:
            task_id: Task ID to filter proposals
            deadline_ms: Collection deadline in milliseconds
            trace_id: Trace ID for logging
            
        Returns: List of proposals received within deadline
        """
        proposals: List[Proposal] = []
        start_time = time.perf_counter()
        deadline = start_time + (deadline_ms / 1000.0)
        
        while time.perf_counter() < deadline:
            remaining_time = deadline - time.perf_counter()
            
            if remaining_time <= 0:
                break
            
            try:
                # Poll with timeout
                proposal = await asyncio.wait_for(
                    self.proposal_queue.get(),
                    timeout=min(0.005, remaining_time)  # 5ms polling interval
                )
                
                # Verify proposal matches task
                if proposal.task_id == task_id:
                    proposals.append(proposal)
                
            except asyncio.TimeoutError:
                # No proposal available, continue polling
                continue
        
        return proposals


# ============================================================================
# PoC Benchmark
# ============================================================================

class ContractNetPoC:
    """
    Validate negotiation phase latency (Contract Net Protocol)
    
    SLO Target: <50ms P95 proposal collection
    """
    
    def __init__(self, num_agents: int = 20):
        """
        Args:
            num_agents: Number of agents in negotiation pool
        """
        self.negotiator = ContractNetNegotiator(num_agents=num_agents)
        self.num_agents = num_agents
    
    async def benchmark_negotiation(self, num_tasks: int = 100, 
                                   deadline_ms: int = 50) -> Dict:
        """
        Measure proposal collection latency across multiple tasks
        
        Args:
            num_tasks: Number of tasks to negotiate (100 samples)
            deadline_ms: Proposal collection deadline (50ms)
            
        Returns: Benchmark results with latency percentiles
        """
        print(f"\n{'='*70}")
        print("PoC 2.1: Contract Net Negotiation")
        print(f"{'='*70}")
        print(f"Agents: {self.num_agents}")
        print(f"Tasks: {num_tasks}")
        print(f"Deadline: {deadline_ms}ms")
        print("SLO Target: <50ms P95\n")
        
        # Execute negotiations
        for i in range(num_tasks):
            turn_plan = {
                "id": f"plan_{i}",
                "required_tools": random.sample(
                    ["web_search", "calculator", "email"],
                    k=random.randint(1, 3)
                ),
                "steps": [{"id": f"step_{j}", "op": "Tool"} for j in range(random.randint(1, 3))],
            }
            
            await self.negotiator.negotiate(turn_plan, deadline_ms=deadline_ms)
            
            if (i + 1) % 20 == 0:
                print(f"Progress: {i + 1}/{num_tasks} tasks negotiated")
        
        # Calculate statistics
        latencies = self.negotiator.negotiation_times_ms
        proposal_counts = self.negotiator.proposal_counts
        
        if len(latencies) == 0:
            print("ERROR: No negotiations completed")
            return {}
        
        # Percentiles
        p50 = float(np.percentile(latencies, 50))
        p95 = float(np.percentile(latencies, 95))
        p99 = float(np.percentile(latencies, 99))
        avg = float(np.mean(latencies))
        
        # Proposal statistics
        avg_proposals = float(np.mean(proposal_counts)) if proposal_counts else 0
        max_proposals = int(np.max(proposal_counts)) if proposal_counts else 0
        
        # SLO validation
        passes_slo = p95 < deadline_ms
        
        results = {
            "p50_ms": p50,
            "p95_ms": p95,
            "p99_ms": p99,
            "avg_ms": avg,
            "min_ms": float(np.min(latencies)),
            "max_ms": float(np.max(latencies)),
            "std_ms": float(np.std(latencies)),
            "avg_proposals": avg_proposals,
            "max_proposals": max_proposals,
            "successful_negotiations": self.negotiator.successful_negotiations,
            "negotiation_success_rate": self.negotiator.successful_negotiations / num_tasks,
            "passes_slo": passes_slo,
            "slo_target_ms": deadline_ms,
        }
        
        return results
    
    def print_results(self, results: Dict):
        """Pretty print benchmark results"""
        print(f"\n{'='*70}")
        print("RESULTS: Contract Net Negotiation PoC")
        print(f"{'='*70}\n")
        
        print("Latency Distribution (ms):")
        print(f"  P50:  {results['p50_ms']:7.2f}")
        print(f"  P95:  {results['p95_ms']:7.2f}  {'✅ PASS' if results['passes_slo'] else '❌ FAIL'} (target: <{results['slo_target_ms']}ms)")
        print(f"  P99:  {results['p99_ms']:7.2f}")
        print(f"  Avg:  {results['avg_ms']:7.2f}")
        print(f"  Min:  {results['min_ms']:7.2f}")
        print(f"  Max:  {results['max_ms']:7.2f}")
        print(f"  Std:  {results['std_ms']:7.2f}")
        
        print(f"\nProposal Statistics:")
        print(f"  Avg per task:     {results['avg_proposals']:6.2f}")
        print(f"  Max per task:     {results['max_proposals']:6d}")
        print(f"  Success rate:     {results['negotiation_success_rate']*100:5.1f}%")
        
        print(f"\nSLO Target: <{results['slo_target_ms']}ms P95")
        if results['passes_slo']:
            print("✅ PASSED: Negotiation phase latency meets SLO")
        else:
            print(f"❌ FAILED: P95={results['p95_ms']:.2f}ms exceeds {results['slo_target_ms']}ms target")
        
        print(f"\n{'='*70}\n")


# ============================================================================
# Main Entry Point
# ============================================================================

async def main():
    """Run the PoC benchmark"""
    poc = ContractNetPoC(num_agents=20)
    results = await poc.benchmark_negotiation(num_tasks=100, deadline_ms=50)
    poc.print_results(results)
    
    return results


if __name__ == "__main__":
    results = asyncio.run(main())
