"""
R5 Dream Phase Benchmarks and Real-World Testing.

This package contains comprehensive benchmarking infrastructure for
validating the R5 dream algorithms with realistic data:

- CPN (Causal Perturbation Network) - Counterfactual scenario generation
- TPN-MCTS (Forward Simulation) - Monte Carlo Tree Search with UCT
- BGT-SM (Insight Generation) - Bisociative Graph Traversal
- SPC-UQ (Episodic Simulation) - Schematic Pattern Completion
- TDL-HCO (Motor Rehearsal) - Integrated in DreamExplorer

Modules:
- realistic_data: Generators for production-like test data
- performance_metrics: Timing and quality measurement
- benchmark_cpn: CPN algorithm benchmarks
- benchmark_mcts: MCTS algorithm benchmarks
- benchmark_bgt_sm: BGT-SM algorithm benchmarks
- benchmark_spc_uq: SPC-UQ algorithm benchmarks
- benchmark_dream_explorer: End-to-end DreamExplorer benchmarks (includes TDL-HCO)
- run_benchmarks: Main runner script for executing full benchmark suite

Usage:
    # Run full benchmark suite
    python -m tests.k0.modules.consolidation.benchmarks.run_benchmarks

    # Run quick benchmarks (skip slow tests)
    python -m tests.k0.modules.consolidation.benchmarks.run_benchmarks --quick

    # Run with pytest
    pytest tests/k0/modules/consolidation/benchmarks/ -v -m benchmark

    # Run specific benchmark
    pytest tests/k0/modules/consolidation/benchmarks/benchmark_cpn.py -v
"""
