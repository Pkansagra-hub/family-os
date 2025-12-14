"""
Benchmarks package for K0 module accuracy testing.

This package provides:
- Accuracy benchmark runner for comparing module output vs golden dataset
- Scoring functions for entities, emotions, activities, and social context
- Regression testing support for CI/CD

Issue: 1.2.1 - Golden Dataset for Module Accuracy
"""

from .accuracy_benchmark import (
    AccuracyBenchmark,
    ActivityScore,
    BenchmarkResult,
    EmotionScore,
    EntityScore,
    ModuleScores,
    SocialScore,
    empty_baseline_processor,
    random_baseline_processor,
    run_accuracy_benchmark,
)

__all__ = [
    "AccuracyBenchmark",
    "BenchmarkResult",
    "ModuleScores",
    "EntityScore",
    "EmotionScore",
    "ActivityScore",
    "SocialScore",
    "run_accuracy_benchmark",
    "empty_baseline_processor",
    "random_baseline_processor",
]
