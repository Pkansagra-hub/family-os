"""
M22 DreamExplorer — Dream-Like Exploration Orchestrator.

This module implements the core DreamExplorer class that orchestrates
R5 dream-like exploration algorithms:
- CPN: Counterfactual Perturbation Network (Issue 8.1.4)
- TPN-MCTS: Forward Simulation with UCT (Issue 8.1.5, 8.1.6)
- SPC-UQ: Episodic Simulation (Issue 8.1.8)
- BGT-SM: Insight Generation (Issue 8.1.9, 8.1.10)
- TDL-HCO: Motor Rehearsal (Issue 8.1.11)

Issue 8.1.15: R5 Algorithm Orchestration
- Parallel execution where possible (CPN, BGT-SM, SPC-UQ are independent)
- Error isolation per algorithm (failures don't crash entire R5)
- Shared ComputeBudget for cycle-level resource control
- All algorithms are sync with async wrappers for non-blocking orchestration

References:
- M8_EXECUTION.md Issue 8.1.3: M22 DreamExplorer scaffold
- M8_EXECUTION.md Issue 8.1.15: R5 Algorithm Orchestration
- Dossier section 4.6: R5 Dream-Like Exploration (REM)
- Dossier section 7.4.5: M22 DreamExplorer

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import asyncio
import logging
import time
import traceback
from typing import Any, Coroutine, Dict, List, Optional, TypeVar

from k0.modules.consolidation.dream.compute_budget import (
    AlgorithmResult,
    ComputeBudget,
    OrchestrationResult,
)
from k0.modules.consolidation.dream.config import DreamConfig
from k0.modules.consolidation.dream.models import (
    CounterfactualScenario,
    DreamExplorerInput,
    DreamExplorerOutput,
    Insight,
    ProspectiveMemory,
    RoutineOptimization,
)

# Note: IntentSignalDetector is imported at runtime inside explore() to avoid
# circular import with dream/__init__.py. See GAP-001 implementation.


logger = logging.getLogger(__name__)

# Type variable for algorithm outputs
T = TypeVar("T")


class DreamExplorer:
    """
    M22 DreamExplorer — Dream-Like Exploration Orchestrator.

    Orchestrates the R5 dream-like exploration algorithms to generate:
    - Insights: Non-obvious connections from BGT-SM
    - Counterfactuals: What-if scenarios from CPN
    - Prospective memories: Future intention predictions from SPC-UQ
    - Routine optimizations: Behavioral improvements from TDL-HCO

    Determinism:
    - All algorithms are seeded with cycle_id for reproducibility
    - Outputs are sorted by novelty/priority for deterministic ordering
    - Random walks and MCTS rollouts use derived seeds

    Thread Safety:
    - DreamExplorer is stateless after construction
    - Multiple calls to explore() can run concurrently

    Usage:
        config = DreamConfig(max_insights=10, creativity=0.5)
        explorer = DreamExplorer(config)

        input_data = DreamExplorerInput(
            cycle_id="01JFXYZ...",
            tenant_id="tenant-1",
            space_id="space-1",
            recent_episodes=[...],
            kg_entities=[...],
            kg_edges=[...],
        )

        output = await explorer.explore(input_data)
        print(f"Generated {len(output.insights)} insights")
    """

    def __init__(self, config: Optional[DreamConfig] = None):
        """
        Initialize DreamExplorer with configuration.

        Args:
            config: DreamConfig with exploration parameters
        """
        self.config = config or DreamConfig()
        self._logger = logger

    async def explore(
        self,
        input_data: DreamExplorerInput,
        compute_budget: Optional[ComputeBudget] = None,
    ) -> DreamExplorerOutput:
        """
        Execute dream exploration and generate outputs.

        Issue 8.1.15: R5 Algorithm Orchestration with:
        - Parallel execution (CPN, BGT-SM, SPC-UQ are independent)
        - Error isolation (individual failures don't crash entire R5)
        - Shared ComputeBudget for cycle-level resource control
        - Deterministic seeding from cycle_id

        Orchestrates the following algorithms:
        1. BGT-SM — Bisociative Graph Traversal for insights
        2. CPN — Counterfactual Perturbation Network for scenarios
        3. SPC-UQ — Sparse Predictive Coding for prospective memories
        4. TDL-HCO — Temporal Difference Learning for routine optimization

        Results are sorted by novelty and limited per configuration.

        Args:
            input_data: DreamExplorerInput with context and data
            compute_budget: Optional shared budget (created if None)

        Returns:
            DreamExplorerOutput with generated artifacts
        """
        start_ms = int(time.time() * 1000)

        # Create shared MCTS compute budget for cycle (per A.0.4 invariant)
        if compute_budget is None:
            compute_budget = ComputeBudget(max_mcts_rollouts=self.config.mcts_max_total_rollouts)

        # Derive seeds for deterministic execution
        cycle_id = input_data.cycle_id
        if self.config.seed:
            cycle_id = self.config.seed

        self._logger.debug(
            "DreamExplorer starting exploration",
            extra={
                "cycle_id": input_data.cycle_id,
                "episodes_count": len(input_data.recent_episodes),
                "entities_count": len(input_data.kg_entities),
                "edges_count": len(input_data.kg_edges),
                "creativity": self.config.creativity,
                "depth": self.config.depth,
                "mcts_budget": compute_budget.max_mcts_rollouts,
            },
        )

        # Initialize orchestration result tracker with compute budget
        orchestration = OrchestrationResult(
            cycle_id=input_data.cycle_id,
            compute_budget=compute_budget,
        )

        # =====================================================================
        # PHASE 1: Run independent algorithms in parallel (Issue 8.1.15)
        # BGT-SM, CPN, SPC-UQ, MCTS are independent and can run concurrently
        # =====================================================================
        parallel_results = await self._run_parallel_algorithms(
            input_data=input_data,
            cycle_id=cycle_id,
            orchestration=orchestration,
        )

        insights = parallel_results.get("bgt_sm", [])
        counterfactuals = parallel_results.get("cpn", [])
        prospective_memories = parallel_results.get("spc_uq", [])
        mcts_scenarios = parallel_results.get("mcts", [])

        # =====================================================================
        # PHASE 2: Run TDL-HCO (Issue 8.1.11 - Motor Rehearsal for Habits)
        # Sequential because it analyzes patterns from previous phases
        # =====================================================================
        routine_result = await self._run_with_error_isolation(
            algorithm_name="tdl_hco",
            coro=self._run_tdl_hco(input_data, cycle_id, compute_budget),
            orchestration=orchestration,
        )
        routine_optimizations = routine_result if routine_result else []

        # =====================================================================
        # PHASE 3: Apply quality filters and limits
        # =====================================================================
        insights = self._rank_and_limit_insights(insights)
        counterfactuals = self._limit_counterfactuals(counterfactuals)
        prospective_memories = self._limit_prospective_memories(prospective_memories)
        routine_optimizations = self._limit_routine_optimizations(routine_optimizations)

        # =====================================================================
        # PHASE 4: Detect intent signals (GAP-001)
        # Scan event_states for intent-bearing events and route to layers
        # =====================================================================
        # Runtime import to avoid circular dependency
        from k0.modules.consolidation.algorithms.intent_signal_detector import (
            IntentSignalDetector as _IntentSignalDetector,
        )

        intent_detector = _IntentSignalDetector()
        intent_signals = intent_detector.detect_all(input_data.event_states)

        compute_ms = int(time.time() * 1000) - start_ms

        # Store final budget snapshot
        orchestration.total_compute_ms = compute_ms
        orchestration.budget_snapshot = compute_budget.to_dict()

        # Log completion with orchestration stats
        self._logger.info(
            "DreamExplorer completed exploration",
            extra={
                "cycle_id": input_data.cycle_id,
                "insights_count": len(insights),
                "counterfactuals_count": len(counterfactuals),
                "prospective_count": len(prospective_memories),
                "routines_count": len(routine_optimizations),
                "intent_signals_count": len(intent_signals),
                "mcts_rollouts_used": compute_budget.used_rollouts,
                "compute_ms": compute_ms,
                "all_succeeded": orchestration.all_succeeded,
                "failures": list(orchestration.failures.keys()),
            },
        )

        return DreamExplorerOutput(
            insights=insights,
            counterfactuals=counterfactuals,
            prospective_memories=prospective_memories,
            routine_optimizations=routine_optimizations,
            intent_signals=intent_signals,
            mcts_decisions_evaluated=compute_budget.used_rollouts,
            compute_ms=compute_ms,
        )

    # =========================================================================
    # ISSUE 8.1.15: PARALLEL EXECUTION HELPERS
    # =========================================================================

    async def _run_parallel_algorithms(
        self,
        input_data: DreamExplorerInput,
        cycle_id: str,
        orchestration: OrchestrationResult,
    ) -> Dict[str, List[Any]]:
        """
        Run independent algorithms in parallel with error isolation.

        Issue 8.1.15: CPN, BGT-SM, and SPC-UQ are independent and can
        execute concurrently for better performance.

        Args:
            input_data: DreamExplorerInput with context and data
            cycle_id: Cycle ID for seeding
            orchestration: Result tracker

        Returns:
            Dictionary mapping algorithm name to outputs
        """
        # Create tasks for parallel execution
        # Note: MCTS is included here but requires compute_budget tracking
        tasks: Dict[str, Coroutine[Any, Any, List[Any]]] = {
            "bgt_sm": self._run_bgt_sm(input_data, cycle_id),
            "cpn": self._run_cpn(input_data, cycle_id),
            "spc_uq": self._run_spc_uq(input_data, cycle_id),
            "mcts": self._run_mcts(input_data, cycle_id, orchestration.compute_budget),
        }

        results: Dict[str, List[Any]] = {}

        # Run all tasks concurrently with error isolation
        task_names = list(tasks.keys())
        coros = [tasks[name] for name in task_names]

        # Gather with return_exceptions=True for error isolation
        gathered = await asyncio.gather(*coros, return_exceptions=True)

        for name, result in zip(task_names, gathered):
            start_ms = int(time.time() * 1000)

            if isinstance(result, Exception):
                # Algorithm failed - log and continue
                error_msg = f"{type(result).__name__}: {result}"
                self._logger.error(
                    f"Algorithm {name} failed with error",
                    extra={
                        "algorithm": name,
                        "error": error_msg,
                        "traceback": traceback.format_exc(),
                    },
                )
                orchestration.add_result(
                    AlgorithmResult(
                        algorithm_name=name,
                        success=False,
                        outputs=[],
                        error_message=error_msg,
                        compute_ms=int(time.time() * 1000) - start_ms,
                    )
                )
                results[name] = []
            else:
                # Algorithm succeeded
                output_list = result if result else []
                orchestration.add_result(
                    AlgorithmResult(
                        algorithm_name=name,
                        success=True,
                        outputs=output_list,
                        compute_ms=int(time.time() * 1000) - start_ms,
                    )
                )
                results[name] = output_list

        return results

    async def _run_with_error_isolation(
        self,
        algorithm_name: str,
        coro: Coroutine[Any, Any, List[Any]],
        orchestration: OrchestrationResult,
    ) -> List[Any]:
        """
        Run a single algorithm with error isolation.

        Issue 8.1.15: Individual algorithm failures don't crash entire R5.

        Args:
            algorithm_name: Name of the algorithm
            coro: Coroutine to execute
            orchestration: Result tracker

        Returns:
            Algorithm outputs or empty list on failure
        """
        start_ms = int(time.time() * 1000)

        try:
            result = await coro
            output_list = result if result else []

            orchestration.add_result(
                AlgorithmResult(
                    algorithm_name=algorithm_name,
                    success=True,
                    outputs=output_list,
                    compute_ms=int(time.time() * 1000) - start_ms,
                )
            )
            return output_list

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            self._logger.error(
                f"Algorithm {algorithm_name} failed with error",
                extra={
                    "algorithm": algorithm_name,
                    "error": error_msg,
                    "traceback": traceback.format_exc(),
                },
            )
            orchestration.add_result(
                AlgorithmResult(
                    algorithm_name=algorithm_name,
                    success=False,
                    outputs=[],
                    error_message=error_msg,
                    compute_ms=int(time.time() * 1000) - start_ms,
                )
            )
            return []

    # =========================================================================
    # ALGORITHM RUNNERS
    # =========================================================================

    async def _run_bgt_sm(
        self,
        input_data: DreamExplorerInput,
        cycle_id: str,
    ) -> List[Insight]:
        """
        Run BGT-SM (Bisociative Graph Traversal for Semantic Memory).

        Discovers non-obvious connections between concepts by:
        1. Sampling seed nodes from recent episodes (high-salience entities)
        2. Executing random walks with restart (RWR) to explore KG
        3. Finding remote associates (semantic distance > threshold)
        4. Computing PMI for surprise quantification
        5. Scoring novelty: distance × PMI / (visit_count + 1)
        6. Generating human-readable insight descriptions

        Args:
            input_data: Input data with episodes and KG
            cycle_id: Cycle ID for seeding

        Returns:
            List of generated insights
        """
        from k0.modules.consolidation.algorithms.bgt_sm import BGTConfig, BisociativeGraphTraversal

        seed = self.config.derive_seed(cycle_id, "bgt_sm")

        self._logger.debug(
            "BGT-SM executing",
            extra={
                "seed": seed,
                "depth": self.config.depth,
                "creativity": self.config.creativity,
                "semantic_distance_threshold": self.config.semantic_distance_threshold,
                "pmi_threshold": self.config.pmi_threshold,
                "entities_count": len(input_data.kg_entities),
                "edges_count": len(input_data.kg_edges),
            },
        )

        # Skip if no entities or edges
        if not input_data.kg_entities or not input_data.kg_edges:
            self._logger.debug("BGT-SM skipped: no KG data available")
            return []

        # Create BGT config from DreamConfig
        bgt_config = BGTConfig(
            semantic_distance_threshold=self.config.semantic_distance_threshold,
            pmi_threshold=self.config.pmi_threshold,
            novelty_threshold=self.config.min_novelty_score,
            corpus_size_n=self.config.corpus_size_n,
            max_total_insights=self.config.max_insights,
            seed=seed,
        )

        # Select seed entities from recent episodes (high-salience)
        seed_entity_ids = self._select_seed_entities(input_data)

        if not seed_entity_ids:
            self._logger.debug("BGT-SM skipped: no seed entities available")
            return []

        # Build embeddings from KG entities (if available)
        embeddings = self._extract_embeddings(input_data)

        # Run BGT-SM algorithm
        bgt = BisociativeGraphTraversal(config=bgt_config)
        bgt_insights = bgt.discover(
            entities=input_data.kg_entities,
            edges=input_data.kg_edges,
            seed_entity_ids=seed_entity_ids,
            embeddings=embeddings,
            rng_seed=seed,
        )

        # Convert BGT insights to standard Insight model
        insights = [bgt_insight.to_insight() for bgt_insight in bgt_insights]

        self._logger.info(
            "BGT-SM completed",
            extra={
                "insights_generated": len(insights),
                "seeds_explored": len(seed_entity_ids),
            },
        )

        return insights

    def _select_seed_entities(
        self,
        input_data: DreamExplorerInput,
    ) -> List[str]:
        """
        Select seed entities for BGT-SM exploration.

        Prioritizes:
        1. Entities from recent episodes with high salience
        2. High-observation-count entities from KG
        3. Entities mentioned in event states

        Args:
            input_data: Input data with episodes and KG

        Returns:
            List of entity IDs to use as seeds
        """
        seed_candidates: Dict[str, float] = {}  # entity_id -> score

        # Extract entities from recent episodes
        for episode in input_data.recent_episodes:
            entity_ids = getattr(episode, "entity_ids", [])
            salience = getattr(episode, "salience_score", 0.5)

            for entity_id in entity_ids:
                if entity_id not in seed_candidates:
                    seed_candidates[entity_id] = 0.0
                seed_candidates[entity_id] += salience

        # Add high-observation entities from KG
        for entity in input_data.kg_entities:
            entity_id = getattr(entity, "entity_id", None)
            obs_count = getattr(entity, "observation_count", 0)

            if entity_id and obs_count >= 5:  # Min 5 observations
                if entity_id not in seed_candidates:
                    seed_candidates[entity_id] = 0.0
                seed_candidates[entity_id] += obs_count / 100.0  # Normalize

        # Sort by score and take top N
        sorted_seeds = sorted(
            seed_candidates.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        # Limit to reasonable number of seeds (e.g., 5)
        max_seeds = min(5, len(sorted_seeds))
        return [entity_id for entity_id, _ in sorted_seeds[:max_seeds]]

    def _extract_embeddings(
        self,
        input_data: DreamExplorerInput,
    ) -> Dict[str, List[float]]:
        """
        Extract embeddings from KG entities.

        Args:
            input_data: Input data with KG entities

        Returns:
            Dictionary of entity_id -> embedding vector
        """
        embeddings: Dict[str, List[float]] = {}

        for entity in input_data.kg_entities:
            entity_id = getattr(entity, "entity_id", None)
            embedding = getattr(entity, "embedding", None)

            if entity_id and embedding and isinstance(embedding, (list, tuple)):
                embeddings[entity_id] = list(embedding)

        return embeddings

    async def _run_cpn(
        self,
        input_data: DreamExplorerInput,
        cycle_id: str,
    ) -> List[CounterfactualScenario]:
        """
        Run CPN (Causal Perturbation Network).

        Generates counterfactual scenarios by:
        1. Selecting emotionally significant episodes
        2. Building causal DAGs from knowledge graph
        3. Perturbing nodes to generate what-if scenarios
        4. Evaluating plausibility and utility changes

        Args:
            input_data: Input data with episodes and KG
            cycle_id: Cycle ID for seeding

        Returns:
            List of counterfactual scenarios
        """
        from k0.modules.consolidation.algorithms.cpn import CausalPerturbationNetwork, CPNConfig

        seed = self.config.derive_seed(cycle_id, "cpn")

        self._logger.debug(
            "CPN executing",
            extra={
                "seed": seed,
                "perturbation_std": self.config.cpn_perturbation_std,
                "types": self.config.cpn_counterfactual_types,
                "episodes_count": len(input_data.recent_episodes),
                "edges_count": len(input_data.kg_edges),
            },
        )

        # Create CPN config from DreamConfig
        cpn_config = CPNConfig(
            perturbation_std=self.config.cpn_perturbation_std,
            counterfactual_types=self.config.cpn_counterfactual_types,
            min_plausibility=self.config.min_confidence,
            seed=seed,
        )

        # Run CPN algorithm
        cpn = CausalPerturbationNetwork(config=cpn_config)
        cpn_scenarios = cpn.generate(
            episodes=input_data.recent_episodes,
            kg_edges=input_data.kg_edges,
            rng_seed=seed,
        )

        # Convert CPN output to CounterfactualScenario model
        return [
            CounterfactualScenario.create(
                scenario_id=s.scenario_id,
                scenario_type=s.scenario_type.value,
                base_episode_id=s.base_episode_id,
                perturbation_target=s.perturbation_target,
                original_outcome=s.original_outcome,
                counterfactual_outcome=s.counterfactual_outcome,
                plausibility=s.plausibility,
                success_probability=s.success_probability,
                utility_delta=s.utility_delta,
            )
            for s in cpn_scenarios
        ]

    async def _run_spc_uq(
        self,
        input_data: DreamExplorerInput,
        cycle_id: str,
    ) -> List[ProspectiveMemory]:
        """
        Run SPC-UQ (Schematic Pattern Completion with Uncertainty Quantification).

        Generates prospective memories by:
        1. Identifying gaps in episodic memory
        2. Reconstructing incomplete episodes using schema priors
        3. Converting reconstructions to prospective memories
        4. Ranking by importance and confidence

        CRITICAL (A.0.6): All reconstructions are NON-CANONICAL.

        Args:
            input_data: Input data with episodes and KG
            cycle_id: Cycle ID for seeding

        Returns:
            List of prospective memories
        """
        from k0.modules.consolidation.algorithms.spc_uq import EpisodicSimulator, SPCConfig

        seed = self.config.derive_seed(cycle_id, "spc_uq")

        self._logger.debug(
            "SPC-UQ executing",
            extra={
                "seed": seed,
                "simulation_count": self.config.spc_simulation_count,
                "uncertainty_alpha": self.config.spc_uncertainty_alpha,
                "uncertainty_beta": self.config.spc_uncertainty_beta,
                "episodes_count": len(input_data.recent_episodes),
            },
        )

        # Create SPC config from DreamConfig
        spc_config = SPCConfig(
            simulation_count=self.config.spc_simulation_count,
            min_confidence=self.config.min_confidence,
            coherence_threshold=self.config.coherence_threshold,
            uncertainty_alpha=self.config.spc_uncertainty_alpha,
            uncertainty_beta=self.config.spc_uncertainty_beta,
            seed=seed,
        )

        # Build context from input
        context = self._build_spc_context(input_data)

        # Convert episodes to fragments for temporal coherence
        fragments = self._extract_fragments(input_data)

        # Run SPC-UQ algorithm
        simulator = EpisodicSimulator(config=spc_config)
        reconstructions = simulator.simulate(
            episodes=input_data.recent_episodes,
            fragments=fragments,
            schemas=[],  # Issue 8.1.9 will provide schemas from semantic memory
            context=context,
            rng_seed=seed,
        )

        # Convert reconstructions to ProspectiveMemory
        prospective_memories: List[ProspectiveMemory] = []
        for reconstruction in reconstructions:
            # Generate prospective memory from reconstruction
            memory = ProspectiveMemory.create(
                prosp_id=reconstruction.episode_id,
                intention_type="RECONSTRUCTION",
                description=reconstruction.summary,
                trigger_condition=f"Recalling episode {reconstruction.original_episode_id}",
                action_to_take="Review reconstructed context for accuracy",
                importance=reconstruction.temporal_coherence_score,
                confidence=reconstruction.confidence_score,
                source_episode_id=reconstruction.original_episode_id,
            )
            prospective_memories.append(memory)

        self._logger.debug(
            "SPC-UQ completed",
            extra={
                "reconstructions_count": len(reconstructions),
                "prospective_memories_count": len(prospective_memories),
            },
        )

        return prospective_memories

    def _build_spc_context(self, input_data: DreamExplorerInput) -> dict:
        """Build context dictionary for SPC-UQ from input data."""
        # Extract known locations from episodes
        known_locations = set()
        frequent_contacts = set()

        for episode in input_data.recent_episodes:
            loc = getattr(episode, "location_name", None)
            if loc:
                known_locations.add(loc)

            participants = getattr(episode, "participants", None)
            if participants:
                for p in participants:
                    frequent_contacts.add(p)

        # Add locations from KG entities
        for entity in input_data.kg_entities:
            entity_type = getattr(entity, "entity_type", None)
            if entity_type == "LOCATION":
                name = getattr(entity, "name", None)
                if name:
                    known_locations.add(name)
            elif entity_type == "PERSON":
                name = getattr(entity, "name", None)
                if name:
                    frequent_contacts.add(name)

        return {
            "known_locations": list(known_locations),
            "nearby_locations": list(known_locations)[:5],  # Top 5 as nearby
            "frequent_contacts": list(frequent_contacts),
        }

    def _extract_fragments(
        self,
        input_data: DreamExplorerInput,
    ) -> list:
        """Extract episode fragments for temporal coherence analysis."""
        from k0.modules.consolidation.algorithms.spc_uq import EpisodeFragment

        fragments = []
        for episode in input_data.recent_episodes:
            episode_id = getattr(episode, "episode_id", None)
            start_ms = getattr(episode, "start_time_ms", 0)
            end_ms = getattr(episode, "end_time_ms", start_ms + 3600000)  # Default 1 hour

            if episode_id:
                fragment = EpisodeFragment(
                    fragment_id=f"{episode_id}_frag",
                    source_episode_id=episode_id,
                    source_event_id=episode_id,
                    start_time_ms=start_ms,
                    end_time_ms=end_ms or start_ms + 3600000,
                    content=getattr(episode, "summary", ""),
                )
                fragments.append(fragment)

        return fragments

    async def _run_mcts(
        self,
        input_data: DreamExplorerInput,
        cycle_id: str,
        compute_budget: Optional[ComputeBudget],
    ) -> List[Any]:
        """
        Run TPN-MCTS (Temporal Projection Network with Monte Carlo Tree Search).

        Generates forward scenarios by:
        1. Building decision tree from current state
        2. Running UCT-based exploration
        3. Extracting predicted future paths
        4. Ranking by expected reward

        Args:
            input_data: Input data with episodes and KG
            cycle_id: Cycle ID for seeding
            compute_budget: Shared compute budget for rollout allocation

        Returns:
            List of MCTS scenarios
        """
        from k0.modules.consolidation.algorithms.mcts import ComputeBudget as MCTSBudget
        from k0.modules.consolidation.algorithms.mcts import (
            MCTSConfig,
            SimpleState,
            TemporalProjectionMCTS,
        )

        seed = self.config.derive_seed(cycle_id, "mcts")

        self._logger.debug(
            "MCTS executing",
            extra={
                "seed": seed,
                "exploration_constant": self.config.mcts_exploration_constant,
                "max_rollout_depth": self.config.mcts_max_rollout_depth,
                "episodes_count": len(input_data.recent_episodes),
            },
        )

        # Skip if no episodes to analyze
        if not input_data.recent_episodes:
            self._logger.debug("MCTS skipped: no episodes available")
            return []

        # Create MCTS config from DreamConfig
        mcts_config = MCTSConfig(
            exploration_constant=self.config.mcts_exploration_constant,
            max_rollout_depth=self.config.mcts_max_rollout_depth,
            discount_factor=self.config.mcts_discount_factor,
            max_total_rollouts=self.config.mcts_max_total_rollouts,
            seed=seed,
        )

        # Build initial state from recent episodes
        initial_state = SimpleState(
            state_id=f"state_{cycle_id[:8]}",
            features={
                "episode_count": float(len(input_data.recent_episodes)),
                "entity_count": float(len(input_data.kg_entities)),
            },
        )

        # Build available actions from entities and episodes
        available_actions = self._build_mcts_actions(input_data)

        if not available_actions:
            self._logger.debug("MCTS skipped: no available actions")
            return []

        # Create MCTS budget from shared compute budget if available
        mcts_budget = None
        if compute_budget:
            mcts_budget = MCTSBudget(
                max_mcts_rollouts=compute_budget.remaining,
            )

        # Run MCTS simulation
        mcts = TemporalProjectionMCTS(config=mcts_config)
        scenarios = mcts.simulate(
            initial_state=initial_state,
            available_actions=available_actions,
            budget=mcts_budget,
            rng_seed=seed,
        )

        # Update shared compute budget
        if compute_budget and mcts_budget:
            # Track how many rollouts were used
            compute_budget.allocate(mcts_budget.used_rollouts)

        self._logger.info(
            "MCTS completed",
            extra={
                "scenarios_generated": len(scenarios),
                "rollouts_used": mcts_budget.used_rollouts if mcts_budget else 0,
            },
        )

        return scenarios

    def _build_mcts_actions(self, input_data: DreamExplorerInput) -> List[Any]:
        """
        Build available actions for MCTS from input data.

        Extracts potential future actions from:
        1. Entity interactions from KG
        2. Historical patterns from episodes
        3. Pending goals/intentions

        Args:
            input_data: Input data with episodes and KG

        Returns:
            List of SimpleAction objects
        """
        from k0.modules.consolidation.algorithms.mcts import SimpleAction

        actions = []

        # Generate actions from entities
        for entity in input_data.kg_entities[:10]:  # Limit to 10 entities
            entity_id = getattr(entity, "entity_id", None)
            entity_type = getattr(entity, "entity_type", "generic")

            if entity_id:
                actions.append(
                    SimpleAction(
                        action_id=f"interact_{entity_id[:8]}",
                        action_type=f"interact_{entity_type.lower()}",
                    )
                )

        # Add generic future actions if no entity-based actions
        if not actions:
            actions = [
                SimpleAction(action_id="action_explore", action_type="explore"),
                SimpleAction(action_id="action_consolidate", action_type="consolidate"),
                SimpleAction(action_id="action_rest", action_type="rest"),
            ]

        return actions

    async def _run_tdl_hco(
        self,
        input_data: DreamExplorerInput,
        cycle_id: str,
        compute_budget: Optional[ComputeBudget],
    ) -> List[RoutineOptimization]:
        """
        Run TDL-HCO (Temporal Difference Learning for Habit/Cognitive Optimization).

        Issue 8.1.11: Full implementation of motor rehearsal for habits.

        Generates routine optimizations by:
        1. Extracting routines from episodic memory
        2. Learning value function V(s) via TD(0)
        3. Detecting bottlenecks where V drops sharply (gradient < -2.0)
        4. Generating optimization suggestions

        TD Update Rule:
            V(s) <- V(s) + alpha * [r + gamma * V(s') - V(s)]
        Where:
            alpha = 0.1 (learning rate)
            gamma = 0.9 (discount factor)

        Bottleneck Detection:
            delta_V = V(s_{t+1}) - V(s_t) < -2.0

        Args:
            input_data: Input data with episodes and KG
            cycle_id: Cycle ID for seeding
            compute_budget: Shared compute budget (for future extensions)

        Returns:
            List of routine optimizations
        """
        from k0.modules.consolidation.algorithms.tdl_hco import (
            TDLConfig,
            TemporalDifferenceLearning,
            extract_routines_from_episodes,
        )

        seed = self.config.derive_seed(cycle_id, "tdl_hco")

        self._logger.debug(
            "TDL-HCO executing",
            extra={
                "seed": seed,
                "learning_rate": self.config.tdl_learning_rate,
                "discount_factor": self.config.tdl_discount_factor,
                "episodes_count": len(input_data.recent_episodes),
            },
        )

        # Skip if no episodes to analyze
        if not input_data.recent_episodes:
            self._logger.debug("TDL-HCO skipped: no episodes available")
            return []

        # Extract routines from episodic memory
        routines = extract_routines_from_episodes(
            episodes=input_data.recent_episodes,
            min_routine_length=3,
            min_occurrences=2,  # Lower threshold for testing
        )

        if not routines:
            self._logger.debug("TDL-HCO skipped: no routines found")
            return []

        # Create TDL config from DreamConfig
        tdl_config = TDLConfig(
            learning_rate=self.config.tdl_learning_rate,
            discount_factor=self.config.tdl_discount_factor,
            bottleneck_threshold=-2.0,  # Per Issue 8.1.11
            max_optimizations=self.config.max_routine_optimizations,
            seed=seed,
        )

        # Run TDL-HCO optimization
        tdl = TemporalDifferenceLearning(config=tdl_config)
        optimizations = tdl.optimize(
            routines=routines,
            rng_seed=seed,
        )

        # Convert to RoutineOptimization model
        result = [opt.to_routine_optimization() for opt in optimizations]

        self._logger.info(
            "TDL-HCO completed",
            extra={
                "routines_found": len(routines),
                "optimizations_generated": len(result),
            },
        )

        return result

    def _rank_and_limit_insights(
        self,
        insights: List[Insight],
    ) -> List[Insight]:
        """
        Rank insights by serendipity and apply quality thresholds.

        Issue 8.1.10: Applies comprehensive quality filtering:
        - semantic_distance >= semantic_distance_threshold (0.7)
        - pmi_score >= pmi_threshold (3.0)
        - novelty_score >= min_novelty_score (0.5)
        - serendipity_score >= serendipity_threshold (0.6)

        Insights are sorted by serendipity_score descending for stable ranking.
        Only top max_insights are returned.

        Args:
            insights: List of generated insights

        Returns:
            Filtered and sorted list of insights meeting quality thresholds
        """
        # Issue 8.1.10: Apply all quality thresholds
        filtered = [
            i
            for i in insights
            if (
                i.semantic_distance >= self.config.semantic_distance_threshold
                and (i.pmi_score or 0.0) >= self.config.pmi_threshold
                and i.novelty_score >= self.config.min_novelty_score
                and i.serendipity_score >= self.config.serendipity_threshold
            )
        ]

        # Sort by serendipity descending (stable: uses novelty as tiebreaker)
        sorted_insights = sorted(
            filtered,
            key=lambda i: (i.serendipity_score, i.novelty_score),
            reverse=True,
        )

        # Limit to max
        return sorted_insights[: self.config.max_insights]

    def _limit_counterfactuals(
        self,
        counterfactuals: List[CounterfactualScenario],
    ) -> List[CounterfactualScenario]:
        """
        Limit counterfactuals to max_counterfactuals.

        Sorted by plausibility descending.

        Args:
            counterfactuals: List of generated scenarios

        Returns:
            Limited list of scenarios
        """
        sorted_cf = sorted(counterfactuals, key=lambda c: c.plausibility, reverse=True)
        return sorted_cf[: self.config.max_counterfactuals]

    def _limit_prospective_memories(
        self,
        memories: List[ProspectiveMemory],
    ) -> List[ProspectiveMemory]:
        """
        Limit prospective memories to max_prospective_memories.

        Sorted by importance descending.

        Args:
            memories: List of generated memories

        Returns:
            Limited list of memories
        """
        sorted_pm = sorted(memories, key=lambda m: m.importance, reverse=True)
        return sorted_pm[: self.config.max_prospective_memories]

    def _limit_routine_optimizations(
        self,
        routines: List[RoutineOptimization],
    ) -> List[RoutineOptimization]:
        """
        Limit routine optimizations to max_routine_optimizations.

        Sorted by expected_improvement descending.

        Args:
            routines: List of generated optimizations

        Returns:
            Limited list of optimizations
        """
        sorted_ro = sorted(routines, key=lambda r: r.expected_improvement, reverse=True)
        return sorted_ro[: self.config.max_routine_optimizations]
