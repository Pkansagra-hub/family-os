"""
Module-Level Benchmark Suite

Benchmarks each K0 module individually to measure:
- Accuracy against golden dataset annotations
- Latency (P50, P95, P99)
- Memory usage

This bypasses the pipeline runner and tests modules directly with
properly structured inputs, enabling isolated accuracy measurement.

Usage:
    python -m tests.benchmarks.module_benchmark --modules all --limit 50
    python -m tests.benchmarks.module_benchmark --modules m02,m04 --verbose
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import statistics
import time
import tracemalloc
from dataclasses import dataclass, field
from datetime import datetime, timezone

# Golden dataset
from golden_dataset import (
    ActivityAnnotation,
    EmotionAnnotation,
    EntityAnnotation,
    GoldenMemory,
    SocialAnnotation,
    load_golden_dataset,
)

# Suppress verbose logging during benchmark
logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger("module_benchmark")


# =============================================================================
# Mock Objects for Module Invocation
# =============================================================================


@dataclass
class MockBusMessage:
    """Mock BusMessage for module invocation."""

    payload: bytes
    trace_id: str = "bench_trace_001"
    offset: int = 1000
    topic: str = "cognitive.memory.write.committed.v1"
    space_id: str = "personal:benchmark"


@dataclass
class MockLogger:
    """Mock logger that captures logs."""

    logs: list = field(default_factory=list)

    def debug(self, msg: str, **kwargs):
        self.logs.append(("DEBUG", msg, kwargs))

    def info(self, msg: str, **kwargs):
        self.logs.append(("INFO", msg, kwargs))

    def warning(self, msg: str, **kwargs):
        self.logs.append(("WARNING", msg, kwargs))

    def error(self, msg: str, **kwargs):
        self.logs.append(("ERROR", msg, kwargs))

    def isEnabledFor(self, level):
        return False


@dataclass
class MockSyscalls:
    """Mock syscalls for modules requiring DB access."""

    pipeline_id: str = "P02_BENCHMARK"
    granted_caps: set = field(
        default_factory=lambda: {
            "st_hipp_events.write",
            "st_relationships.read",
            "social.family_graph_resolve",
        }
    )

    async def relationships_query(self, actor_id: str) -> list:
        """Return empty relationships (no DB)."""
        return []


@dataclass
class MockContext:
    """Mock PipelineContext for module invocation."""

    syscalls: MockSyscalls = field(default_factory=MockSyscalls)
    config: dict = field(default_factory=dict)
    logger: MockLogger = field(default_factory=MockLogger)
    preloaded_models: dict | None = None


# =============================================================================
# Module Score Dataclasses
# =============================================================================


@dataclass
class ModuleScore:
    """Base class for module scores."""

    module_id: str
    samples_processed: int = 0
    latency_samples_ms: list = field(default_factory=list)
    errors: int = 0

    @property
    def latency_p50_ms(self) -> float:
        if not self.latency_samples_ms:
            return 0.0
        return statistics.median(self.latency_samples_ms)

    @property
    def latency_p95_ms(self) -> float:
        if not self.latency_samples_ms:
            return 0.0
        sorted_samples = sorted(self.latency_samples_ms)
        idx = int(len(sorted_samples) * 0.95)
        return sorted_samples[min(idx, len(sorted_samples) - 1)]

    @property
    def latency_p99_ms(self) -> float:
        if not self.latency_samples_ms:
            return 0.0
        sorted_samples = sorted(self.latency_samples_ms)
        idx = int(len(sorted_samples) * 0.99)
        return sorted_samples[min(idx, len(sorted_samples) - 1)]


@dataclass
class M02Score(ModuleScore):
    """M02 semantic_project scores."""

    module_id: str = "hippocampus.semantic_project"
    ner_precision_samples: list = field(default_factory=list)
    ner_recall_samples: list = field(default_factory=list)
    ner_f1_samples: list = field(default_factory=list)

    @property
    def ner_precision(self) -> float:
        return statistics.mean(self.ner_precision_samples) if self.ner_precision_samples else 0.0

    @property
    def ner_recall(self) -> float:
        return statistics.mean(self.ner_recall_samples) if self.ner_recall_samples else 0.0

    @property
    def ner_f1(self) -> float:
        return statistics.mean(self.ner_f1_samples) if self.ner_f1_samples else 0.0


@dataclass
class M04Score(ModuleScore):
    """M04 affect.analyze scores."""

    module_id: str = "affect.analyze"
    emotion_accuracy_samples: list = field(default_factory=list)
    valence_mae_samples: list = field(default_factory=list)
    arousal_mae_samples: list = field(default_factory=list)

    @property
    def emotion_accuracy(self) -> float:
        return (
            statistics.mean(self.emotion_accuracy_samples) if self.emotion_accuracy_samples else 0.0
        )

    @property
    def valence_mae(self) -> float:
        return statistics.mean(self.valence_mae_samples) if self.valence_mae_samples else 0.0

    @property
    def arousal_mae(self) -> float:
        return statistics.mean(self.arousal_mae_samples) if self.arousal_mae_samples else 0.0


@dataclass
class M07Score(ModuleScore):
    """M07 social.family_graph_resolve scores."""

    module_id: str = "social.family_graph_resolve"
    context_accuracy_samples: list = field(default_factory=list)
    participant_count_mae_samples: list = field(default_factory=list)

    @property
    def context_accuracy(self) -> float:
        return (
            statistics.mean(self.context_accuracy_samples) if self.context_accuracy_samples else 0.0
        )

    @property
    def participant_count_mae(self) -> float:
        return (
            statistics.mean(self.participant_count_mae_samples)
            if self.participant_count_mae_samples
            else 0.0
        )


@dataclass
class M10Score(ModuleScore):
    """M10 context.ingress_classify (activity) scores."""

    module_id: str = "context.ingress_classify"
    activity_accuracy_samples: list = field(default_factory=list)

    @property
    def activity_accuracy(self) -> float:
        return (
            statistics.mean(self.activity_accuracy_samples)
            if self.activity_accuracy_samples
            else 0.0
        )


# =============================================================================
# Scoring Functions
# =============================================================================


def score_entities(
    predicted_entities: list[str],
    ground_truth: list[EntityAnnotation],
) -> tuple[float, float, float]:
    """
    Score entity extraction.

    Returns: (precision, recall, f1)
    """
    if not ground_truth:
        return (1.0, 1.0, 1.0) if not predicted_entities else (0.0, 1.0, 0.0)

    gt_texts = {e.text.lower().strip() for e in ground_truth}

    # Predicted entities may be in format "person_sarah" or "Sarah" or dict with 'text'
    pred_texts = set()
    for e in predicted_entities:
        if not e:
            continue
        e_lower = e.lower().strip()
        # Remove type prefix (person_, date_, place_, time_, org_)
        for prefix in ("person_", "date_", "place_", "time_", "org_", "food_", "event_"):
            if e_lower.startswith(prefix):
                e_lower = e_lower[len(prefix) :]
                break
        # Handle compound like "7_today" -> "7 today"
        e_lower = e_lower.replace("_", " ")
        pred_texts.add(e_lower)

    if not pred_texts and not gt_texts:
        return (1.0, 1.0, 1.0)

    # Fuzzy matching: check if prediction contains or is contained in ground truth
    true_positives = 0
    matched_gt = set()
    matched_pred = set()

    for pred in pred_texts:
        for gt in gt_texts:
            if gt in matched_gt:
                continue
            # Exact match
            if pred == gt:
                true_positives += 1
                matched_gt.add(gt)
                matched_pred.add(pred)
                break
            # Fuzzy: pred in gt or gt in pred
            if pred in gt or gt in pred:
                true_positives += 1
                matched_gt.add(gt)
                matched_pred.add(pred)
                break

    false_positives = len(pred_texts) - len(matched_pred)
    false_negatives = len(gt_texts) - len(matched_gt)

    precision = (
        true_positives / (true_positives + false_positives)
        if (true_positives + false_positives) > 0
        else 0
    )
    recall = (
        true_positives / (true_positives + false_negatives)
        if (true_positives + false_negatives) > 0
        else 0
    )
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    return precision, recall, f1


def score_emotion(
    pred_valence: float,
    pred_arousal: float,
    pred_emotions: list[str],
    ground_truth: EmotionAnnotation,
) -> tuple[float, float, float]:
    """
    Score emotion detection.

    Returns: (emotion_accuracy, valence_mae, arousal_mae)
    """
    # Primary emotion match
    gt_primary = ground_truth.primary.value.lower()
    pred_primary = pred_emotions[0].lower() if pred_emotions else ""

    # Map predicted emotions to ground truth labels
    emotion_match = 1.0 if pred_primary == gt_primary else 0.0

    # For VADER, we don't get emotion labels, so check valence direction
    if not pred_emotions or pred_primary in ("positive", "negative", "neutral"):
        # Infer from valence
        gt_is_positive = ground_truth.valence > 0.5
        pred_is_positive = pred_valence > 0.5
        emotion_match = 1.0 if gt_is_positive == pred_is_positive else 0.0

    # Valence MAE (ground truth is -1 to 1, predictions may vary)
    # Normalize prediction to -1 to 1 if needed
    if 0 <= pred_valence <= 1:
        pred_valence_normalized = (pred_valence * 2) - 1  # 0-1 to -1 to 1
    else:
        pred_valence_normalized = pred_valence

    valence_mae = abs(pred_valence_normalized - ground_truth.valence)

    # Arousal MAE (both 0-1)
    arousal_mae = abs(pred_arousal - ground_truth.arousal)

    return emotion_match, valence_mae, arousal_mae


def score_social(
    pred_context: str,
    pred_participant_count: int,
    ground_truth: SocialAnnotation,
) -> tuple[float, float]:
    """
    Score social context.

    Returns: (context_accuracy, participant_count_mae)
    """
    gt_context = ground_truth.context.value.lower()
    pred_context_lower = pred_context.lower() if pred_context else ""

    context_match = 1.0 if pred_context_lower == gt_context else 0.0

    gt_count = ground_truth.participant_count or len(ground_truth.participants)
    count_mae = abs(pred_participant_count - gt_count)

    return context_match, count_mae


def score_activity(
    pred_activity: str,
    ground_truth: ActivityAnnotation,
) -> float:
    """
    Score activity classification.

    Returns: activity_accuracy
    """
    gt_type = ground_truth.type.value.lower()
    pred_type = pred_activity.lower() if pred_activity else ""

    # Direct match
    if pred_type == gt_type:
        return 1.0

    # Fuzzy match (activity in prediction or vice versa)
    if gt_type in pred_type or pred_type in gt_type:
        return 0.5

    return 0.0


# =============================================================================
# Module Benchmarks
# =============================================================================


def create_envelope(memory: GoldenMemory, idx: int) -> dict:
    """Create a test envelope from golden memory."""
    import hashlib
    import uuid

    now = datetime.now(timezone.utc)
    trace_id = str(uuid.uuid4())

    body = {
        "text": memory.text,
        "event_time": now.isoformat(),
        "language": "en",
    }

    # Add participants if social annotations exist
    if memory.ground_truth.social and memory.ground_truth.social.participants:
        body["participants"] = [
            f"person_{i}" for i in range(len(memory.ground_truth.social.participants))
        ]

    return {
        "cognitive_trace_id": trace_id,
        "event_id": f"evt_{idx:05d}",
        "wal_pos": 5000 + idx,
        "tenant_id": "benchmark-tenant",
        "space_id": "personal:benchmark",
        "topic": "cognitive.memory.write.committed.v1",
        "schema_version": "1.0.0",
        "envelope_sha256": hashlib.sha256(trace_id.encode()).hexdigest(),
        "band": "GREEN",
        "policy_decision": "ALLOW",
        "actor": "benchmark_user",
        "actor_id": "benchmark_user",
        "ts": int(now.timestamp()),
        "body": body,
    }


async def benchmark_m02(memories: list[GoldenMemory], verbose: bool = False) -> M02Score:
    """Benchmark M02 hippocampus.semantic_project (NER)."""
    from k0.modules.hippocampus.semantic_project import run as m02_run

    score = M02Score()
    context = MockContext()

    for idx, memory in enumerate(memories):
        envelope = create_envelope(memory, idx)
        message = MockBusMessage(
            payload=json.dumps(envelope).encode("utf-8"),
            trace_id=envelope["cognitive_trace_id"],
        )

        try:
            start = time.perf_counter()
            result = await m02_run(message=message, context=context, envelope=envelope)
            duration_ms = (time.perf_counter() - start) * 1000

            score.latency_samples_ms.append(duration_ms)
            score.samples_processed += 1

            # Extract entities from result
            entities_json = result.get("entities_json", "[]")
            if isinstance(entities_json, str):
                entities = json.loads(entities_json)
            else:
                entities = entities_json

            # Extract entity texts
            entity_texts = []
            for e in entities:
                if isinstance(e, dict):
                    entity_texts.append(e.get("text", e.get("entity", "")))
                else:
                    entity_texts.append(str(e))

            # Score
            precision, recall, f1 = score_entities(entity_texts, memory.ground_truth.entities)
            score.ner_precision_samples.append(precision)
            score.ner_recall_samples.append(recall)
            score.ner_f1_samples.append(f1)

            if verbose:
                print(
                    f"  M02 [{idx}]: P={precision:.2f} R={recall:.2f} F1={f1:.2f} ({duration_ms:.1f}ms)"
                )
                print(f"       Expected: {[e.text for e in memory.ground_truth.entities]}")
                print(f"       Got: {entity_texts}")

        except Exception as e:
            score.errors += 1
            if verbose:
                print(f"  M02 [{idx}] ERROR: {e}")

    return score


async def benchmark_m04(memories: list[GoldenMemory], verbose: bool = False) -> M04Score:
    """Benchmark M04 affect.analyze (emotion detection)."""
    from k0.modules.affect.analyze import run as m04_run

    score = M04Score()
    context = MockContext()

    for idx, memory in enumerate(memories):
        envelope = create_envelope(memory, idx)
        message = MockBusMessage(
            payload=json.dumps(envelope).encode("utf-8"),
            trace_id=envelope["cognitive_trace_id"],
        )

        try:
            start = time.perf_counter()
            result = await m04_run(message=message, context=context, envelope=envelope)
            duration_ms = (time.perf_counter() - start) * 1000

            score.latency_samples_ms.append(duration_ms)
            score.samples_processed += 1

            # Extract affect data
            valence = result.get("affect_valence", 0.5)
            arousal = result.get("affect_arousal", 0.5)
            emotions_json = result.get("dominant_emotions_json", "[]")
            if isinstance(emotions_json, str):
                emotions = json.loads(emotions_json)
            else:
                emotions = emotions_json or []

            # Score
            emotion_acc, valence_mae, arousal_mae = score_emotion(
                valence, arousal, emotions, memory.ground_truth.emotions
            )
            score.emotion_accuracy_samples.append(emotion_acc)
            score.valence_mae_samples.append(valence_mae)
            score.arousal_mae_samples.append(arousal_mae)

            if verbose:
                gt = memory.ground_truth.emotions
                print(
                    f"  M04 [{idx}]: EmotAcc={emotion_acc:.2f} VMAE={valence_mae:.2f} AMAE={arousal_mae:.2f} ({duration_ms:.1f}ms)"
                )
                print(f"       Expected: primary={gt.primary.value} v={gt.valence} a={gt.arousal}")
                print(f"       Got: emotions={emotions} v={valence} a={arousal}")

        except Exception as e:
            score.errors += 1
            if verbose:
                print(f"  M04 [{idx}] ERROR: {e}")

    return score


async def benchmark_m07(memories: list[GoldenMemory], verbose: bool = False) -> M07Score:
    """Benchmark M07 social.family_graph_resolve."""
    from k0.modules.social.family_graph_resolve import run as m07_run

    score = M07Score()
    context = MockContext()

    for idx, memory in enumerate(memories):
        envelope = create_envelope(memory, idx)
        message = MockBusMessage(
            payload=json.dumps(envelope).encode("utf-8"),
            trace_id=envelope["cognitive_trace_id"],
        )

        try:
            start = time.perf_counter()
            result = await m07_run(message=message, context=context, envelope=envelope)
            duration_ms = (time.perf_counter() - start) * 1000

            score.latency_samples_ms.append(duration_ms)
            score.samples_processed += 1

            # Extract social data
            social_context = result.get("social_context", "")
            num_participants = result.get("num_participants", 1)

            # Score
            context_acc, count_mae = score_social(
                social_context, num_participants, memory.ground_truth.social
            )
            score.context_accuracy_samples.append(context_acc)
            score.participant_count_mae_samples.append(count_mae)

            if verbose:
                gt = memory.ground_truth.social
                print(
                    f"  M07 [{idx}]: CtxAcc={context_acc:.2f} CountMAE={count_mae} ({duration_ms:.1f}ms)"
                )
                print(
                    f"       Expected: context={gt.context.value} count={gt.participant_count or len(gt.participants)}"
                )
                print(f"       Got: context={social_context} count={num_participants}")

        except Exception as e:
            score.errors += 1
            if verbose:
                print(f"  M07 [{idx}] ERROR: {e}")

    return score


async def benchmark_m10(memories: list[GoldenMemory], verbose: bool = False) -> M10Score:
    """Benchmark M10 context.ingress_classify (activity detection)."""
    from k0.modules.context.ingress_classify import run as m10_run

    score = M10Score()
    context = MockContext()

    for idx, memory in enumerate(memories):
        envelope = create_envelope(memory, idx)
        message = MockBusMessage(
            payload=json.dumps(envelope).encode("utf-8"),
            trace_id=envelope["cognitive_trace_id"],
        )

        try:
            start = time.perf_counter()
            result = await m10_run(message=message, context=context, envelope=envelope)
            duration_ms = (time.perf_counter() - start) * 1000

            score.latency_samples_ms.append(duration_ms)
            score.samples_processed += 1

            # Extract activity data
            activity_type = result.get("activity_type", "")

            # Score
            activity_acc = score_activity(activity_type, memory.ground_truth.activity)
            score.activity_accuracy_samples.append(activity_acc)

            if verbose:
                gt = memory.ground_truth.activity
                print(f"  M10 [{idx}]: ActAcc={activity_acc:.2f} ({duration_ms:.1f}ms)")
                print(f"       Expected: {gt.type.value}")
                print(f"       Got: {activity_type}")

        except Exception as e:
            score.errors += 1
            if verbose:
                print(f"  M10 [{idx}] ERROR: {e}")

    return score


# =============================================================================
# Report Generation
# =============================================================================


def print_report(
    m02: M02Score | None,
    m04: M04Score | None,
    m07: M07Score | None,
    m10: M10Score | None,
    total_time_ms: float,
    memory_peak_mb: float,
):
    """Print benchmark report."""
    print("\n" + "=" * 70)
    print("MODULE BENCHMARK REPORT")
    print("=" * 70)
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print(f"Total Time: {total_time_ms:.1f}ms")
    print(f"Memory Peak: {memory_peak_mb:.1f}MB")
    print()

    if m02:
        print("M02 hippocampus.semantic_project (NER):")
        print(f"  Samples: {m02.samples_processed} (errors: {m02.errors})")
        print(f"  NER Precision: {m02.ner_precision:.3f}")
        print(f"  NER Recall:    {m02.ner_recall:.3f}")
        print(f"  NER F1:        {m02.ner_f1:.3f}")
        print(f"  Latency P50:   {m02.latency_p50_ms:.1f}ms")
        print(f"  Latency P95:   {m02.latency_p95_ms:.1f}ms")
        print(f"  Latency P99:   {m02.latency_p99_ms:.1f}ms")
        print()

    if m04:
        print("M04 affect.analyze (Emotion Detection):")
        print(f"  Samples: {m04.samples_processed} (errors: {m04.errors})")
        print(f"  Emotion Accuracy: {m04.emotion_accuracy:.3f}")
        print(f"  Valence MAE:      {m04.valence_mae:.3f}")
        print(f"  Arousal MAE:      {m04.arousal_mae:.3f}")
        print(f"  Latency P50:      {m04.latency_p50_ms:.1f}ms")
        print(f"  Latency P95:      {m04.latency_p95_ms:.1f}ms")
        print(f"  Latency P99:      {m04.latency_p99_ms:.1f}ms")
        print()

    if m07:
        print("M07 social.family_graph_resolve (Social Context):")
        print(f"  Samples: {m07.samples_processed} (errors: {m07.errors})")
        print(f"  Context Accuracy:     {m07.context_accuracy:.3f}")
        print(f"  Participant Count MAE: {m07.participant_count_mae:.2f}")
        print(f"  Latency P50:          {m07.latency_p50_ms:.1f}ms")
        print(f"  Latency P95:          {m07.latency_p95_ms:.1f}ms")
        print(f"  Latency P99:          {m07.latency_p99_ms:.1f}ms")
        print()

    if m10:
        print("M10 context.ingress_classify (Activity Detection):")
        print(f"  Samples: {m10.samples_processed} (errors: {m10.errors})")
        print(f"  Activity Accuracy: {m10.activity_accuracy:.3f}")
        print(f"  Latency P50:       {m10.latency_p50_ms:.1f}ms")
        print(f"  Latency P95:       {m10.latency_p95_ms:.1f}ms")
        print(f"  Latency P99:       {m10.latency_p99_ms:.1f}ms")
        print()

    print("=" * 70)


# =============================================================================
# Main Entry Point
# =============================================================================


async def run_benchmark(
    modules: list[str],
    limit: int | None,
    verbose: bool,
) -> dict:
    """Run benchmark for specified modules."""
    # Load golden dataset
    print("Loading golden dataset...")
    dataset = load_golden_dataset()
    memories = list(dataset.memories)

    if limit:
        memories = memories[:limit]

    print(f"Loaded {len(memories)} memories from golden dataset v{dataset.version}")

    # Track memory
    tracemalloc.start()
    start_time = time.perf_counter()

    # Run benchmarks
    m02_score = None
    m04_score = None
    m07_score = None
    m10_score = None

    if "all" in modules or "m02" in modules:
        print("\nBenchmarking M02 (semantic_project)...")
        m02_score = await benchmark_m02(memories, verbose)

    if "all" in modules or "m04" in modules:
        print("\nBenchmarking M04 (affect.analyze)...")
        m04_score = await benchmark_m04(memories, verbose)

    if "all" in modules or "m07" in modules:
        print("\nBenchmarking M07 (social.family_graph_resolve)...")
        m07_score = await benchmark_m07(memories, verbose)

    if "all" in modules or "m10" in modules:
        print("\nBenchmarking M10 (ingress_classify)...")
        m10_score = await benchmark_m10(memories, verbose)

    # Memory stats
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    total_time_ms = (time.perf_counter() - start_time) * 1000

    # Print report
    print_report(m02_score, m04_score, m07_score, m10_score, total_time_ms, peak / 1024 / 1024)

    return {
        "m02": m02_score,
        "m04": m04_score,
        "m07": m07_score,
        "m10": m10_score,
        "total_time_ms": total_time_ms,
        "memory_peak_mb": peak / 1024 / 1024,
    }


def main():
    parser = argparse.ArgumentParser(description="K0 Module Benchmark Suite")
    parser.add_argument(
        "--modules",
        type=str,
        default="all",
        help="Comma-separated list of modules to benchmark (m02,m04,m07,m10,all)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of memories to process",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print detailed per-sample results",
    )

    args = parser.parse_args()

    modules = [m.strip().lower() for m in args.modules.split(",")]

    asyncio.run(run_benchmark(modules, args.limit, args.verbose))


if __name__ == "__main__":
    main()
