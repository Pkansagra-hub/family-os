#!/usr/bin/env python3
"""R5 Benchmark Runner CLI.

Usage:
    python run_benchmarks.py --pack toy
    python run_benchmarks.py --pack cpn_counterfactual --algorithm CPN --seeds 5
    python run_benchmarks.py --pack all --strict --output results/
    python run_benchmarks.py --pack toy --compare-baseline --report json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# R5 benchmark imports - use relative imports for module execution
try:
    from .r5_coverage import CoverageResult, CoverageValidator, aggregate_results
    from .r5_statistics import MultiSeedResult
    from .r5_baseline import BaselineComparator
except ImportError:
    # Fallback for direct execution
    from r5_coverage import CoverageResult, CoverageValidator, aggregate_results
    from r5_statistics import MultiSeedResult
    from r5_baseline import BaselineComparator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_benchmarks")


# ─────────────────────────────────────────────────────────────────────────────
# Pack Registry
# ─────────────────────────────────────────────────────────────────────────────

# Full module paths for packs
PACK_BASE = "tests.k0.modules.consolidation.benchmarks.packs"

PACK_REGISTRY: Dict[str, str] = {
    "toy": f"{PACK_BASE}.toy",
    "causal_deep": f"{PACK_BASE}.causal_deep",
    "causal_fork_join": f"{PACK_BASE}.causal_fork_join",
    "mcts_delayed": f"{PACK_BASE}.mcts_delayed",
    "mcts_constrained": f"{PACK_BASE}.mcts_constrained",
    "bgt_clustered": f"{PACK_BASE}.bgt_clustered",
    "bgt_adversarial": f"{PACK_BASE}.bgt_adversarial",
    "spc_multi_prov": f"{PACK_BASE}.spc_multi_prov",
    "spc_conflict": f"{PACK_BASE}.spc_conflict",
    "mixed_stress": f"{PACK_BASE}.mixed_stress",
    "real_world": f"{PACK_BASE}.real_world",
    # Edge case packs
    "cpn_sparse_graph": f"{PACK_BASE}.cpn_sparse_graph",
    "spc_high_conflict": f"{PACK_BASE}.spc_high_conflict",
    "perf_stress": f"{PACK_BASE}.perf_stress",
}

ALGORITHM_MAP = {
    "CPN": ["causal_deep", "causal_fork_join", "toy", "cpn_sparse_graph"],
    "MCTS": ["mcts_delayed", "mcts_constrained", "toy", "perf_stress"],
    "BGT": ["bgt_clustered", "bgt_adversarial", "toy", "perf_stress"],
    "SPC": ["spc_multi_prov", "spc_conflict", "toy", "spc_high_conflict"],
    "ALL": ["mixed_stress", "real_world", "toy", "perf_stress"],
    "EDGE_CASES": ["cpn_sparse_graph", "spc_high_conflict", "perf_stress"],
}


# ─────────────────────────────────────────────────────────────────────────────
# Run Result Dataclass
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class BenchmarkRun:
    """Complete benchmark run result."""

    pack_name: str
    algorithms: List[str]
    seed: int
    start_time: str
    end_time: str
    duration_seconds: float
    coverage_results: List[CoverageResult]
    baseline_comparisons: Optional[Dict[str, Any]] = None
    multi_seed_results: Optional[Dict[str, MultiSeedResult]] = None
    passed: bool = True
    exit_code: int = 0
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            f"Pack: {self.pack_name}",
            f"Algorithms: {', '.join(self.algorithms)}",
            f"Seed: {self.seed}",
            f"Duration: {self.duration_seconds:.2f}s",
            f"Status: {'PASSED' if self.passed else 'FAILED'}",
        ]

        for cr in self.coverage_results:
            lines.append(f"  {cr.algorithm}: {'✓' if cr.passed else '✗'}")

        if self.errors:
            lines.append("Errors:")
            for e in self.errors:
                lines.append(f"  - {e}")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        result = {
            "pack_name": self.pack_name,
            "algorithms": self.algorithms,
            "seed": self.seed,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
            "passed": self.passed,
            "exit_code": self.exit_code,
            "errors": self.errors,
            "coverage_results": [asdict(cr) for cr in self.coverage_results],
        }

        if self.baseline_comparisons:
            result["baseline_comparisons"] = {
                algo: [asdict(c) for c in comps]
                for algo, comps in self.baseline_comparisons.items()
            }

        if self.multi_seed_results:
            result["multi_seed_results"] = {
                algo: asdict(msr) for algo, msr in self.multi_seed_results.items()
            }

        return result


# ─────────────────────────────────────────────────────────────────────────────
# Pack Loading
# ─────────────────────────────────────────────────────────────────────────────


def load_pack(pack_name: str, seed: int = 42, real_embeddings: bool = False) -> Any:
    """Load a pack module and build its world.

    Args:
        pack_name: Name of the pack (e.g., 'toy', 'causal_deep').
        seed: Random seed for data generation.
        real_embeddings: If True, use real embedding model.

    Returns:
        Dict with 'module', 'world', and 'thresholds'.
    """
    if pack_name not in PACK_REGISTRY:
        raise ValueError(f"Unknown pack: {pack_name}. Available: {list(PACK_REGISTRY.keys())}")

    module_path = PACK_REGISTRY[pack_name]

    try:
        import importlib
        pack_module = importlib.import_module(module_path)

        # Build the world using the pack's build_world function
        world = None
        if hasattr(pack_module, "build_world"):
            world = pack_module.build_world(seed=seed, use_ultrabert=real_embeddings)

        # Get expected properties/thresholds
        thresholds = {}
        for attr in ["EXPECTED_PROPERTIES", "TOY_EXPECTED_PROPERTIES",
                     "CAUSAL_DEEP_EXPECTED_PROPERTIES", "STRESS_EXPECTED_PROPERTIES",
                     "REALWORLD_EXPECTED_PROPERTIES", "COVERAGE_THRESHOLDS"]:
            if hasattr(pack_module, attr):
                thresholds = getattr(pack_module, attr)
                break

        return {"module": pack_module, "world": world, "thresholds": thresholds}

    except ImportError as e:
        logger.warning(f"Could not import pack {pack_name}: {e}")
        return {"module": None, "world": None, "thresholds": {}, "error": str(e)}


def get_pack_thresholds(pack_name: str) -> Dict[str, Any]:
    """Get expected thresholds for a pack.

    Args:
        pack_name: Name of the pack.

    Returns:
        Dict of threshold values.
    """
    try:
        import importlib
        module_path = PACK_REGISTRY.get(pack_name, "")
        if module_path:
            pack_module = importlib.import_module(module_path)
            for attr in ["EXPECTED_PROPERTIES", "TOY_EXPECTED_PROPERTIES",
                         "CAUSAL_DEEP_EXPECTED_PROPERTIES", "STRESS_EXPECTED_PROPERTIES",
                         "REALWORLD_EXPECTED_PROPERTIES", "COVERAGE_THRESHOLDS"]:
                if hasattr(pack_module, attr):
                    return getattr(pack_module, attr)
    except Exception:
        pass
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# Algorithm Execution
# ─────────────────────────────────────────────────────────────────────────────


def run_cpn_on_world(world: Any) -> List[Any]:
    """Run CPN algorithm on a world and return counterfactuals."""
    try:
        from k0.modules.consolidation.algorithms.cpn import (
            CausalPerturbationNetwork,
            CPNConfig,
        )

        config = CPNConfig(
            emotional_threshold=0.6,
            top_k_regret_events=10,
            causal_chain_depth=5,
            seed=world.seed,
        )
        cpn = CausalPerturbationNetwork(config=config)

        counterfactuals = cpn.generate(
            episodes=world.episodes,
            kg_edges=world.kg_edges,
            rng_seed=world.seed,
        )
        return counterfactuals or []
    except Exception as e:
        logger.error(f"CPN execution failed: {e}")
        return []


def run_mcts_on_world(world: Any) -> List[Any]:
    """Run MCTS algorithm on a world and return scenarios."""
    try:
        from k0.modules.consolidation.algorithms.mcts import (
            TemporalProjectionMCTS,
            MCTSConfig,
            ComputeBudget,
            DecisionType,
        )

        config = MCTSConfig(
            exploration_constant=1.414,
            max_rollout_depth=5,
            discount_factor=0.95,
            seed=world.seed,
        )
        budget = ComputeBudget(max_mcts_rollouts=100)
        mcts = TemporalProjectionMCTS(config=config)

        # Get goals from the world
        goals = world.goals if world.goals else []
        goal = goals[0] if goals else None

        scenarios = mcts.simulate(
            initial_state=world.initial_state,
            available_actions=world.actions,
            budget=budget,
            rng_seed=world.seed,
            decision_type=DecisionType.GENERIC,
            goal=goal,
        )
        return scenarios or []
    except Exception as e:
        logger.error(f"MCTS execution failed: {e}")
        return []


def run_bgt_on_world(world: Any) -> List[Any]:
    """Run BGT-SM algorithm on a world and return insights."""
    try:
        from k0.modules.consolidation.algorithms.bgt_sm import (
            BisociativeGraphTraversal,
            BGTConfig,
        )

        config = BGTConfig(
            walk_steps=100,  # More steps for deeper exploration
            max_walks_per_seed=5,  # More walks per seed
            pmi_threshold=0.01,  # Very low threshold for more discoveries
            semantic_distance_threshold=0.1,  # Lower to allow more connections
            novelty_threshold=0.01,  # Lower for more discoveries
            seed=world.seed,
        )
        bgt = BisociativeGraphTraversal(config=config)

        # Get seed entity IDs - use multiple entities from different categories as seeds
        if world.entities:
            # Try to get 1 entity from each category
            categories_seen = set()
            seed_entity_ids = []
            for e in world.entities:
                if e.category not in categories_seen and len(seed_entity_ids) < 6:
                    seed_entity_ids.append(e.entity_id)
                    categories_seen.add(e.category)
            # If we don't have enough, add more
            if len(seed_entity_ids) < 3:
                seed_entity_ids = [e.entity_id for e in world.entities[:5]]
        else:
            seed_entity_ids = []

        insights = bgt.discover(
            entities=world.entities,
            edges=world.semantic_edges,
            seed_entity_ids=seed_entity_ids,
            embeddings=world.embeddings,
            rng_seed=world.seed,
        )
        return insights or []
    except Exception as e:
        logger.error(f"BGT-SM execution failed: {e}")
        return []


def run_spc_on_world(world: Any) -> List[Any]:
    """Run SPC-UQ algorithm on a world and return reconstructions."""
    try:
        from k0.modules.consolidation.algorithms.spc_uq import (
            EpisodicSimulator,
            SPCConfig,
        )

        config = SPCConfig(
            simulation_count=50,
            min_confidence=0.3,
            coherence_threshold=0.4,
            seed=world.seed,
        )
        spc = EpisodicSimulator(config=config)

        reconstructions = spc.simulate(
            episodes=world.incomplete_episodes,
            fragments=world.fragments,
            schemas=world.schemas,
            context=world.context,
            rng_seed=world.seed,
        )
        return reconstructions or []
    except Exception as e:
        logger.error(f"SPC-UQ execution failed: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Benchmark Execution
# ─────────────────────────────────────────────────────────────────────────────


def run_single_pack(
    pack_name: str,
    algorithms: Optional[List[str]] = None,
    seed: int = 42,
    real_embeddings: bool = False,
    compare_baseline: bool = False,
    strict: bool = False,
) -> BenchmarkRun:
    """Run benchmarks for a single pack.

    Args:
        pack_name: Pack name to run.
        algorithms: List of algorithms to test (None = all).
        seed: Random seed.
        real_embeddings: Use real embedding model.
        compare_baseline: Run baseline comparisons.
        strict: Fail on any threshold violation.

    Returns:
        BenchmarkRun result.
    """
    start_time = datetime.now().isoformat()
    start_ts = time.time()

    logger.info(f"Running pack: {pack_name} (seed={seed})")

    # Determine algorithms for this pack
    if algorithms is None:
        algorithms = []
        for algo, packs in ALGORITHM_MAP.items():
            if algo != "ALL" and pack_name in packs:
                algorithms.append(algo)

    if not algorithms:
        algorithms = ["CPN", "MCTS", "BGT", "SPC"]  # Default: try all

    # Load pack and build world
    pack = load_pack(pack_name, seed=seed, real_embeddings=real_embeddings)
    world = pack.get("world")
    thresholds = pack.get("thresholds", {})

    errors = []
    coverage_results = []

    # Check if world was loaded successfully
    if world is None:
        error_msg = pack.get("error", "Failed to load world from pack")
        logger.error(f"World not loaded for {pack_name}: {error_msg}")
        for algo in algorithms:
            coverage_results.append(CoverageResult(
                pack_name=pack_name,
                algorithm=algo,
                passed=False,
                metrics={},
                failures=[f"World not loaded: {error_msg}"],
                warnings=[],
            ))
        return BenchmarkRun(
            pack_name=pack_name,
            algorithms=algorithms,
            seed=seed,
            start_time=start_time,
            end_time=datetime.now().isoformat(),
            duration_seconds=time.time() - start_ts,
            coverage_results=coverage_results,
            passed=False,
            exit_code=1 if strict else 0,
            errors=[error_msg],
        )

    # Create validator with pack_name
    validator = CoverageValidator(pack_name=pack_name)

    # Helper to serialize outputs for reporting
    def serialize_output(obj: Any) -> Dict[str, Any]:
        """Convert algorithm output to serializable dict."""
        if hasattr(obj, "__dict__"):
            result = {}
            for k, v in obj.__dict__.items():
                if not k.startswith("_"):
                    if hasattr(v, "value"):  # Enum
                        result[k] = str(v)
                    elif hasattr(v, "__dict__"):
                        result[k] = serialize_output(v)
                    else:
                        result[k] = str(v) if not isinstance(v, (int, float, bool, str, type(None))) else v
            return result
        elif isinstance(obj, dict):
            return {k: serialize_output(v) for k, v in obj.items()}
        else:
            return str(obj)

    # Run each algorithm and validate
    for algo in algorithms:
        try:
            algo_outputs = []
            inputs_summary = {}

            # Run the actual algorithm on the world
            if algo == "CPN":
                # Capture detailed inputs
                episodes_detail = []
                for e in (world.episodes or [])[:8]:
                    ep_info = {
                        "id": e.episode_id,
                        "summary": e.summary[:150] if e.summary else "",
                        "emotional_valence": getattr(e, 'emotional_valence', None),
                        "participants": getattr(e, 'participants', []),
                        "location": getattr(e, 'location', None),
                        "activity": getattr(e, 'activity_type', None),
                    }
                    episodes_detail.append(ep_info)

                edges_detail = []
                for e in (world.kg_edges or [])[:10]:
                    edge_info = {
                        "source": getattr(e, 'source_id', getattr(e, 'source_entity_id', '?')),
                        "target": getattr(e, 'target_id', getattr(e, 'target_entity_id', '?')),
                        "relation": str(e.relation),
                        "weight": getattr(e, 'weight', None),
                    }
                    edges_detail.append(edge_info)

                inputs_summary = {
                    "episodes_count": len(world.episodes) if world.episodes else 0,
                    "episodes": episodes_detail,
                    "kg_edges_count": len(world.kg_edges) if world.kg_edges else 0,
                    "kg_edges": edges_detail,
                }
                algo_outputs = run_cpn_on_world(world)
                cr = validator.validate_cpn(
                    counterfactuals=algo_outputs,
                    thresholds=thresholds,
                )
                # Attach inputs and outputs
                cr.inputs = inputs_summary
                cr.outputs = [serialize_output(o) for o in algo_outputs[:10]]  # First 10 outputs
            elif algo == "MCTS":
                inputs_summary = {
                    "initial_state": serialize_output(world.initial_state) if world.initial_state else {},
                    "actions_count": len(world.actions) if world.actions else 0,
                    "actions_sample": [str(a) for a in (world.actions or [])[:5]],
                    "goals": [str(g) for g in (world.goals or [])[:3]],
                }
                algo_outputs = run_mcts_on_world(world)
                budget = 100  # Default budget
                cr = validator.validate_mcts(
                    scenarios=algo_outputs,
                    thresholds=thresholds,
                    budget=budget,
                )
                cr.inputs = inputs_summary
                cr.outputs = [serialize_output(o) for o in algo_outputs[:10]]
            elif algo == "BGT":
                inputs_summary = {
                    "entities_count": len(world.entities) if world.entities else 0,
                    "entities_sample": [{"id": e.entity_id, "category": e.category} for e in (world.entities or [])[:5]],
                    "semantic_edges_count": len(world.semantic_edges) if world.semantic_edges else 0,
                    "semantic_edges_sample": [(getattr(e, 'source_id', getattr(e, 'source_entity_id', '?')), getattr(e, 'target_id', getattr(e, 'target_entity_id', '?')), getattr(e, "weight", 1.0)) for e in (world.semantic_edges or [])[:5]],
                }
                algo_outputs = run_bgt_on_world(world)
                # Build entity clusters for cross-cluster validation
                entity_clusters = {e.entity_id: e.category for e in world.entities} if world.entities else {}
                cr = validator.validate_bgt(
                    insights=algo_outputs,
                    thresholds=thresholds,
                    entity_clusters=entity_clusters,
                )
                cr.inputs = inputs_summary
                cr.outputs = [serialize_output(o) for o in algo_outputs[:10]]
            elif algo == "SPC":
                # Detailed fragment info for SPC
                fragments_detail = []
                for f in (world.fragments or [])[:10]:
                    frag_info = {
                        "id": getattr(f, 'fragment_id', getattr(f, 'id', '?')),
                        "content": (getattr(f, 'content', '')[:120] if getattr(f, 'content', '') else ""),
                        "provenance_type": getattr(f, 'provenance_type', None),
                        "confidence": getattr(f, 'confidence', None),
                    }
                    # Check for conflict info
                    if hasattr(f, 'conflicts_with') and f.conflicts_with:
                        frag_info["conflicts_with"] = f.conflicts_with
                    if hasattr(f, 'conflict_type') and f.conflict_type:
                        frag_info["conflict_type"] = f.conflict_type
                    fragments_detail.append(frag_info)

                inputs_summary = {
                    "incomplete_episodes_count": len(world.incomplete_episodes) if world.incomplete_episodes else 0,
                    "incomplete_episodes": [
                        {
                            "id": e.episode_id,
                            "summary": e.summary[:150] if e.summary else "",
                            "location": getattr(e, 'location_name', None),
                            "participants": getattr(e, 'participants', None),
                            "activity": getattr(e, 'activity_type', None),
                            "ambiguity": getattr(e, 'ambiguity_score', None),
                        }
                        for e in (world.incomplete_episodes or [])[:5]
                    ],
                    "fragments_count": len(world.fragments) if world.fragments else 0,
                    "fragments": fragments_detail,
                    "schemas_count": len(world.schemas) if world.schemas else 0,
                    "context_keys": list(world.context.keys()) if world.context else [],
                }
                algo_outputs = run_spc_on_world(world)
                cr = validator.validate_spc(
                    reconstructions=algo_outputs,
                    thresholds=thresholds,
                    fragments=world.fragments,
                )
                cr.inputs = inputs_summary
                cr.outputs = [serialize_output(o) for o in algo_outputs[:10]]
            else:
                cr = CoverageResult(
                    pack_name=pack_name,
                    algorithm=algo,
                    passed=True,
                    metrics={"output_count": len(algo_outputs)},
                    failures=[],
                    warnings=[],
                )

            logger.info(f"  {algo}: {'PASSED' if cr.passed else 'FAILED'} ({len(algo_outputs)} outputs)")
            coverage_results.append(cr)

        except Exception as e:
            logger.error(f"Error running {algo} on {pack_name}: {e}")
            errors.append(f"{algo}: {e}")
            coverage_results.append(CoverageResult(
                pack_name=pack_name,
                algorithm=algo,
                passed=False,
                metrics={},
                failures=[str(e)],
                warnings=[],
            ))

    # Baseline comparisons
    baseline_comparisons = None
    if compare_baseline:
        try:
            comparator = BaselineComparator(seed=seed)
            baseline_comparisons = {}
            logger.info("Baseline comparison enabled (implementation pending full pack integration)")
        except Exception as e:
            errors.append(f"Baseline comparison failed: {e}")

    end_ts = time.time()
    end_time = datetime.now().isoformat()

    # Determine pass/fail
    all_passed = all(cr.passed for cr in coverage_results) and not errors

    if strict and not all_passed:
        exit_code = 1
    else:
        exit_code = 0

    return BenchmarkRun(
        pack_name=pack_name,
        algorithms=algorithms,
        seed=seed,
        start_time=start_time,
        end_time=end_time,
        duration_seconds=end_ts - start_ts,
        coverage_results=coverage_results,
        baseline_comparisons=baseline_comparisons,
        passed=all_passed,
        exit_code=exit_code,
        errors=errors,
    )


def run_multi_seed_pack(
    pack_name: str,
    algorithms: Optional[List[str]] = None,
    seeds: int = 5,
    real_embeddings: bool = False,
    strict: bool = False,
) -> BenchmarkRun:
    """Run benchmarks across multiple seeds for statistical significance.

    Args:
        pack_name: Pack name to run.
        algorithms: List of algorithms to test (None = all).
        seeds: Number of seeds to run (1, 2, 3, ..., seeds).
        real_embeddings: Use real embedding model.
        strict: Fail on any threshold violation.

    Returns:
        BenchmarkRun with aggregated multi-seed results.
    """
    start_time = datetime.now().isoformat()
    start_ts = time.time()

    logger.info(f"Running pack: {pack_name} with {seeds} seeds")

    all_coverage_results = []
    all_errors = []

    for seed in range(1, seeds + 1):
        run = run_single_pack(
            pack_name=pack_name,
            algorithms=algorithms,
            seed=seed,
            real_embeddings=real_embeddings,
            compare_baseline=False,
            strict=False,  # Don't exit early on multi-seed
        )
        all_coverage_results.extend(run.coverage_results)
        all_errors.extend(run.errors)

    end_ts = time.time()
    end_time = datetime.now().isoformat()

    # Aggregate results
    aggregated = aggregate_results(all_coverage_results)
    all_passed = all(cr.passed for cr in aggregated) and not all_errors

    if strict and not all_passed:
        exit_code = 1
    else:
        exit_code = 0

    # Determine algorithms used
    if algorithms is None:
        algorithms = list(set(cr.algorithm for cr in aggregated))

    return BenchmarkRun(
        pack_name=pack_name,
        algorithms=algorithms,
        seed=0,  # Multi-seed
        start_time=start_time,
        end_time=end_time,
        duration_seconds=end_ts - start_ts,
        coverage_results=aggregated,
        passed=all_passed,
        exit_code=exit_code,
        errors=all_errors,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Report Generation
# ─────────────────────────────────────────────────────────────────────────────


def generate_report(
    runs: List[BenchmarkRun],
    report_format: str = "text",
    output_path: Optional[Path] = None,
) -> str:
    """Generate a benchmark report.

    Args:
        runs: List of benchmark runs.
        report_format: 'text', 'json', or 'markdown'.
        output_path: Optional path to save report.

    Returns:
        Report string.
    """
    if report_format == "json":
        report_data = {
            "runs": [r.to_dict() for r in runs],
            "summary": {
                "total_packs": len(runs),
                "passed": sum(1 for r in runs if r.passed),
                "failed": sum(1 for r in runs if not r.passed),
                "total_duration": sum(r.duration_seconds for r in runs),
            },
        }
        report = json.dumps(report_data, indent=2)

    elif report_format == "markdown":
        lines = ["# R5 Benchmark Report", ""]
        lines.append(f"**Generated**: {datetime.now().isoformat()}")
        lines.append("")
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- Total packs: {len(runs)}")
        lines.append(f"- Passed: {sum(1 for r in runs if r.passed)}")
        lines.append(f"- Failed: {sum(1 for r in runs if not r.passed)}")
        lines.append(f"- Total duration: {sum(r.duration_seconds for r in runs):.2f}s")
        lines.append("")
        lines.append("## Details")
        lines.append("")

        for run in runs:
            status = "✅ PASSED" if run.passed else "❌ FAILED"
            lines.append(f"### {run.pack_name} {status}")
            lines.append("")
            lines.append(f"- Seed: {run.seed}")
            lines.append(f"- Duration: {run.duration_seconds:.2f}s")
            lines.append("")

            if run.coverage_results:
                for cr in run.coverage_results:
                    status_icon = "✅" if cr.passed else "❌"
                    lines.append(f"#### {cr.algorithm} {status_icon}")
                    lines.append("")

                    # Show INPUTS with full detail
                    if cr.inputs:
                        lines.append("**Inputs:**")
                        lines.append("")
                        lines.append("```json")
                        lines.append(json.dumps(cr.inputs, indent=2, default=str))
                        lines.append("```")
                        lines.append("")

                    # Show OUTPUTS (with full details)
                    if cr.outputs:
                        lines.append(f"**Outputs ({len(cr.outputs)} shown):**")
                        lines.append("")
                        lines.append("```json")
                        for i, out in enumerate(cr.outputs[:10]):
                            lines.append(f"[{i+1}] {json.dumps(out, indent=2, default=str)}")
                        if len(cr.outputs) > 10:
                            lines.append(f"... ({len(cr.outputs)} total outputs)")
                        lines.append("```")
                        lines.append("")

                    # Show METRICS table
                    if cr.metrics:
                        lines.append("**Metrics:**")
                        lines.append("")
                        lines.append("| Metric | Value |")
                        lines.append("|--------|-------|")
                        for key, value in cr.metrics.items():
                            # Format value nicely
                            if isinstance(value, float):
                                formatted = f"{value:.4f}"
                            elif isinstance(value, dict):
                                formatted = ", ".join(f"{k}:{v}" for k, v in value.items())
                            elif isinstance(value, list):
                                formatted = ", ".join(str(v) for v in value[:5])
                                if len(value) > 5:
                                    formatted += f"... ({len(value)} total)"
                            else:
                                formatted = str(value)
                            lines.append(f"| {key} | {formatted} |")
                        lines.append("")

                    # Show failures if any
                    if cr.failures:
                        lines.append("**Failures:**")
                        for f in cr.failures:
                            lines.append(f"- ❌ {f}")
                        lines.append("")

                    # Show warnings if any
                    if cr.warnings:
                        lines.append("**Warnings:**")
                        for w in cr.warnings:
                            lines.append(f"- ⚠️ {w}")
                        lines.append("")

            if run.errors:
                lines.append("**Errors:**")
                for e in run.errors:
                    lines.append(f"- {e}")
                lines.append("")

        report = "\n".join(lines)

    else:  # text
        lines = ["=" * 60, "R5 Benchmark Report", "=" * 60, ""]

        for run in runs:
            lines.append(run.summary())
            lines.append("-" * 40)

        lines.append("")
        lines.append(f"Total: {len(runs)} packs, "
                    f"{sum(1 for r in runs if r.passed)} passed, "
                    f"{sum(1 for r in runs if not r.passed)} failed")
        lines.append(f"Duration: {sum(r.duration_seconds for r in runs):.2f}s")

        report = "\n".join(lines)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        logger.info(f"Report saved to: {output_path}")

    return report


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="R5 Benchmark Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--pack",
        "-p",
        type=str,
        default="all",
        help="Pack name to run (e.g., 'toy', 'cpn_counterfactual') or 'all'",
    )

    parser.add_argument(
        "--algorithm",
        "-a",
        type=str,
        nargs="*",
        help="Algorithms to test (CPN, MCTS, BGT, SPC). Default: all applicable",
    )

    parser.add_argument(
        "--seeds",
        "-s",
        type=int,
        default=1,
        help="Number of seeds to run for statistical significance (default: 1)",
    )

    parser.add_argument(
        "--real-embeddings",
        action="store_true",
        help="Use real embedding model instead of mock",
    )

    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if any threshold is violated",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Output directory for results",
    )

    parser.add_argument(
        "--compare-baseline",
        action="store_true",
        help="Run baseline comparisons",
    )

    parser.add_argument(
        "--profile",
        action="store_true",
        help="Enable profiling",
    )

    parser.add_argument(
        "--report",
        "-r",
        type=str,
        choices=["text", "json", "markdown"],
        default="text",
        help="Report format (default: text)",
    )

    parser.add_argument(
        "--save-baseline",
        type=str,
        help="Save results as baseline to specified file",
    )

    parser.add_argument(
        "--load-baseline",
        type=str,
        help="Compare results against specified baseline file",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="List available packs and exit",
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.list:
        print("Available packs:")
        for pack_name in sorted(PACK_REGISTRY.keys()):
            print(f"  - {pack_name}")
        print("\nAlgorithm-pack mapping:")
        for algo, packs in ALGORITHM_MAP.items():
            print(f"  {algo}: {', '.join(packs)}")
        return 0

    # Determine packs to run
    if args.pack == "all":
        packs = list(PACK_REGISTRY.keys())
    else:
        packs = [args.pack]

    # Validate packs
    for pack in packs:
        if pack not in PACK_REGISTRY:
            logger.error(f"Unknown pack: {pack}")
            logger.info(f"Available packs: {', '.join(PACK_REGISTRY.keys())}")
            return 1

    # Run benchmarks
    runs: List[BenchmarkRun] = []

    for pack_name in packs:
        if args.seeds > 1:
            run = run_multi_seed_pack(
                pack_name=pack_name,
                algorithms=args.algorithm,
                seeds=args.seeds,
                real_embeddings=args.real_embeddings,
                strict=args.strict,
            )
        else:
            run = run_single_pack(
                pack_name=pack_name,
                algorithms=args.algorithm,
                seed=42,
                real_embeddings=args.real_embeddings,
                compare_baseline=args.compare_baseline,
                strict=args.strict,
            )

        runs.append(run)
        logger.info(f"Completed {pack_name}: {'PASSED' if run.passed else 'FAILED'}")

    # Generate report
    output_path = None
    if args.output:
        output_dir = Path(args.output)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = {"text": "txt", "json": "json", "markdown": "md"}[args.report]
        output_path = output_dir / f"benchmark_report_{timestamp}.{ext}"

    report = generate_report(runs, args.report, output_path)
    print(report)

    # Save baseline if requested
    if args.save_baseline:
        baseline_data = {
            "timestamp": datetime.now().isoformat(),
            "runs": [r.to_dict() for r in runs],
        }
        baseline_path = Path(args.save_baseline)
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(baseline_data, indent=2))
        logger.info(f"Baseline saved to: {baseline_path}")

    # Compare to baseline if requested
    if args.load_baseline:
        baseline_path = Path(args.load_baseline)
        if baseline_path.exists():
            baseline_data = json.loads(baseline_path.read_text())
            logger.info(f"Loaded baseline from: {baseline_path}")
            logger.info(f"Baseline timestamp: {baseline_data.get('timestamp', 'unknown')}")
            # TODO: Implement detailed comparison
        else:
            logger.error(f"Baseline file not found: {baseline_path}")

    # Determine exit code
    if args.strict:
        exit_code = max(r.exit_code for r in runs) if runs else 0
    else:
        exit_code = 0

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
