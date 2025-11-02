"""
Comprehensive DAG + LLM Test Framework

This test framework demonstrates:
  1. Modular LLM provider (imported from root, shared across POCs)
  2. DAG execution with real LLM calls
  3. Sequential vs Parallel comparison
  4. Multiple scenarios (simple, complex, Q&A, API calls)
  5. Performance metrics and bottleneck analysis

Usage: python comprehensive_test.py [scenario]
  Scenarios: simple, complex, qa, api
"""

import asyncio
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set

# Import from POC root directory
sys.path.insert(0, "..")
from llm_provider import get_provider, reset_provider


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskNode:
    """DAG task node."""

    task_id: str
    name: str
    prompt: str
    dependencies: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    latency_ms: float = 0.0
    llm_time_ms: float = 0.0
    result: Optional[str] = None
    error: Optional[str] = None
    wave: int = -1

    def __hash__(self):
        return hash(self.task_id)


@dataclass
class ExecutionMetrics:
    """Execution metrics."""

    total_latency_ms: float
    llm_total_time_ms: float
    dag_overhead_ms: float
    wave_count: int
    tasks_completed: int
    parallelism: float
    wave_times: Dict[int, float] = field(default_factory=dict)


class DAGExecutor:
    """Execute DAG with parallel waves using external LLM provider."""

    def __init__(self, llm_provider):
        self.llm_provider = llm_provider
        self.tasks: Dict[str, TaskNode] = {}

    def add_task(
        self, task_id: str, name: str, prompt: str, dependencies: Optional[List[str]] = None
    ):
        """Add task to DAG."""
        dependencies = dependencies or []
        self.tasks[task_id] = TaskNode(
            task_id=task_id, name=name, prompt=prompt, dependencies=dependencies
        )

    def compute_waves(self) -> List[Set[str]]:
        """Compute topological sort waves."""
        in_degree = {task_id: 0 for task_id in self.tasks}
        for task_id, task in self.tasks.items():
            for dep in task.dependencies:
                in_degree[task_id] += 1

        waves: List[Set[str]] = []
        processed = set()

        while len(processed) < len(self.tasks):
            current_wave = set()
            for task_id, task in self.tasks.items():
                if task_id not in processed:
                    dep_count = sum(1 for d in task.dependencies if d not in processed)
                    if dep_count == 0:
                        current_wave.add(task_id)

            if not current_wave:
                raise ValueError("Circular dependency")

            for task_id in current_wave:
                self.tasks[task_id].wave = len(waves)

            waves.append(current_wave)
            processed.update(current_wave)

        return waves

    async def execute_llm_task(self, task: TaskNode) -> bool:
        """Execute task with LLM call via provider."""
        task.status = TaskStatus.RUNNING
        start_time = time.perf_counter()

        try:
            print(f"    [{task.task_id:5s}] START")

            # Call LLM provider (non-blocking via executor)
            loop = asyncio.get_event_loop()
            llm_start = time.perf_counter()
            response = await loop.run_in_executor(
                self.llm_provider.executor, self.llm_provider.call_llm, task.prompt
            )
            task.llm_time_ms = (time.perf_counter() - llm_start) * 1000

            await asyncio.sleep(0.01)
            task.latency_ms = (time.perf_counter() - start_time) * 1000
            task.status = TaskStatus.COMPLETED
            task.result = response[:100]

            print(f"    [{task.task_id:5s}] END   {task.llm_time_ms:6.0f}ms")
            return True

        except Exception as e:
            task.error = str(e)
            task.status = TaskStatus.FAILED
            task.latency_ms = (time.perf_counter() - start_time) * 1000
            print(f"    [{task.task_id:5s}] ERROR: {type(e).__name__}")
            return False

    async def execute_wave(self, wave: Set[str], wave_num: int) -> tuple:
        """Execute tasks in wave in parallel."""
        print(f"  [WAVE {wave_num}] {len(wave)} tasks: {', '.join(sorted(wave)[:3])}")
        wave_start = time.perf_counter()

        try:
            tasks = [self.execute_llm_task(self.tasks[tid]) for tid in wave]
            results = await asyncio.gather(*tasks, return_exceptions=False)
            wave_time = (time.perf_counter() - wave_start) * 1000
            return all(results), wave_time
        except Exception as e:
            print(f"    ERROR: {type(e).__name__}")
            return False, 0

    async def execute_parallel_dag(self) -> ExecutionMetrics:
        """Execute DAG with parallel waves."""
        start_time = time.perf_counter()
        waves = self.compute_waves()
        wave_times = {}

        for i, wave in enumerate(waves):
            success, wave_time = await self.execute_wave(wave, i)
            wave_times[i] = wave_time

        total_latency_ms = (time.perf_counter() - start_time) * 1000
        llm_total = sum(t.llm_time_ms for t in self.tasks.values())
        completed = len([t for t in self.tasks.values() if t.status == TaskStatus.COMPLETED])

        return ExecutionMetrics(
            total_latency_ms=total_latency_ms,
            llm_total_time_ms=llm_total,
            dag_overhead_ms=total_latency_ms - max(wave_times.values()) if wave_times else 0,
            wave_count=len(waves),
            tasks_completed=completed,
            parallelism=len(self.tasks) / len(waves) if waves else 1.0,
            wave_times=wave_times,
        )

    async def execute_sequential(self) -> ExecutionMetrics:
        """Execute all tasks sequentially."""
        start_time = time.perf_counter()

        for task_id in sorted(self.tasks.keys()):
            await self.execute_llm_task(self.tasks[task_id])

        total_latency_ms = (time.perf_counter() - start_time) * 1000
        llm_total = sum(t.llm_time_ms for t in self.tasks.values())
        completed = len([t for t in self.tasks.values() if t.status == TaskStatus.COMPLETED])

        return ExecutionMetrics(
            total_latency_ms=total_latency_ms,
            llm_total_time_ms=llm_total,
            dag_overhead_ms=0,
            wave_count=len(self.tasks),
            tasks_completed=completed,
            parallelism=1.0,
        )


async def run_test(scenario: str = "simple"):
    """Run comprehensive test scenario."""
    print("=" * 90)
    print(f"COMPREHENSIVE DAG + LLM TEST: {scenario.upper()}")
    print("=" * 90)

    # Initialize LLM provider
    print("\n[LLM PROVIDER SETUP]")
    provider = get_provider(prefer_local=True, max_workers=5)
    print(f"Backend: {provider.get_backend()}")
    print("-" * 90)

    if scenario == "simple":
        await test_simple(provider)
    elif scenario == "complex":
        await test_complex(provider)
    elif scenario == "qa":
        await test_qa(provider)
    elif scenario == "api":
        await test_api(provider)
    else:
        print(f"Unknown scenario: {scenario}")

    reset_provider()


async def test_simple(provider):
    """Simple 3-task DAG test."""
    print("\n[SCENARIO: Simple 3-Task DAG]")
    print("  Wave 0: [A, B] (parallel)")
    print("  Wave 1: [C] (depends on A, B)")

    print("\n[SEQUENTIAL]")
    exec_seq = DAGExecutor(provider)
    exec_seq.add_task("A", "Q1", "What is 2 + 2? (max 5 words)")
    exec_seq.add_task("B", "Q2", "What is the capital of Japan? (max 5 words)")
    exec_seq.add_task("C", "Q3", "Combine previous answers (max 10 words)", dependencies=["A", "B"])

    seq_metrics = await exec_seq.execute_sequential()
    print(f"Sequential: {seq_metrics.total_latency_ms:.0f}ms, {seq_metrics.tasks_completed}/3 done")

    print("\n[PARALLEL]")
    exec_par = DAGExecutor(provider)
    exec_par.add_task("A", "Q1", "What is 2 + 2? (max 5 words)")
    exec_par.add_task("B", "Q2", "What is the capital of Japan? (max 5 words)")
    exec_par.add_task("C", "Q3", "Combine previous answers (max 10 words)", dependencies=["A", "B"])

    par_metrics = await exec_par.execute_parallel_dag()
    print(f"Parallel:   {par_metrics.total_latency_ms:.0f}ms, {par_metrics.tasks_completed}/3 done")

    speedup = (
        seq_metrics.total_latency_ms / par_metrics.total_latency_ms
        if par_metrics.total_latency_ms > 0
        else 1.0
    )
    print(
        f"\nSpeedup: {speedup:.2f}x ({seq_metrics.total_latency_ms - par_metrics.total_latency_ms:.0f}ms saved)"
    )


async def test_complex(provider):
    """Complex 9-task DAG test."""
    print("\n[SCENARIO: Complex 9-Task DAG]")
    print("  Wave 0: [A, B, C] (3 independent)")
    print("  Wave 1: [D, E] (depend on A, B)")
    print("  Wave 2: [F, G] (depend on D, E)")
    print("  Wave 3: [H, I] (sequential)")

    exec_par = DAGExecutor(provider)
    exec_par.add_task("A", "T1", "Math: What is 10 + 5? (max 5 words)")
    exec_par.add_task("B", "T2", "Math: What is 20 * 2? (max 5 words)")
    exec_par.add_task("C", "T3", "Math: What is 100 - 30? (max 5 words)")
    exec_par.add_task("D", "T4", "Combine A+B results (max 10 words)", dependencies=["A", "B"])
    exec_par.add_task("E", "T5", "Combine B+C results (max 10 words)", dependencies=["B", "C"])
    exec_par.add_task("F", "T6", "Summarize D result (max 10 words)", dependencies=["D"])
    exec_par.add_task("G", "T7", "Summarize E result (max 10 words)", dependencies=["E"])
    exec_par.add_task("H", "T8", "Analyze F+G (max 10 words)", dependencies=["F", "G"])
    exec_par.add_task("I", "T9", "Final report (max 15 words)", dependencies=["H"])

    par_metrics = await exec_par.execute_parallel_dag()
    print(
        f"\nParallel DAG: {par_metrics.total_latency_ms:.0f}ms, {par_metrics.tasks_completed}/9 done"
    )
    print(f"Parallelism: {par_metrics.parallelism:.2f} tasks/wave, {par_metrics.wave_count} waves")


async def test_qa(provider):
    """Q&A reasoning pipeline."""
    print("\n[SCENARIO: Q&A Reasoning Pipeline]")
    print("  Stage 1: 3 questions (parallel)")
    print("  Stage 2: Synthesis (parallel)")
    print("  Stage 3: Final report")

    exec_par = DAGExecutor(provider)
    exec_par.add_task("Q1", "Speed", "Train travels 120mi in 3h. Speed? (max 5 words)")
    exec_par.add_task("Q2", "Apples", "50 apples, 30% sold. Remain? (max 5 words)")
    exec_par.add_task("Q3", "Fraction", "25% of 200 as fraction? (max 5 words)")
    exec_par.add_task(
        "S1", "Syn1", "Summarize Q1-Q3 answers (max 15 words)", dependencies=["Q1", "Q2", "Q3"]
    )
    exec_par.add_task(
        "S2", "Syn2", "Analyze relationships in answers (max 15 words)", dependencies=["S1"]
    )
    exec_par.add_task(
        "F", "Final", "Create comprehensive report (max 20 words)", dependencies=["S2"]
    )

    par_metrics = await exec_par.execute_parallel_dag()
    print(
        f"\nQ&A Pipeline: {par_metrics.total_latency_ms:.0f}ms, {par_metrics.tasks_completed}/6 done"
    )


async def test_api(provider):
    """API parallel requests test."""
    print("\n[SCENARIO: 5 Parallel API Requests]")
    print("  All 5 requests run concurrently (max 5 workers)")

    exec_par = DAGExecutor(provider)
    exec_par.add_task("R1", "Req1", "What is Python used for? (max 10 words)")
    exec_par.add_task("R2", "Req2", "Explain async/await (max 10 words)")
    exec_par.add_task("R3", "Req3", "What is DAG? (max 10 words)")
    exec_par.add_task("R4", "Req4", "Define parallelism (max 10 words)")
    exec_par.add_task("R5", "Req5", "What is LLM? (max 10 words)")

    par_metrics = await exec_par.execute_parallel_dag()
    print(
        f"\nParallel Requests: {par_metrics.total_latency_ms:.0f}ms, {par_metrics.tasks_completed}/5 done"
    )
    print(
        f"Throughput: {par_metrics.tasks_completed / (par_metrics.total_latency_ms / 1000):.2f} req/sec"
    )


if __name__ == "__main__":
    import sys

    scenario = sys.argv[1] if len(sys.argv) > 1 else "simple"
    asyncio.run(run_test(scenario))
