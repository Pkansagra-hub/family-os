"""
Benchmark Diagnostic Suite - Validates the Benchmark Harness Itself

PURPOSE:
    The reviewer raised critical concerns about "statistically impossible"
    benchmark results. This diagnostic validates:

    1. Embedding normalization (are embeddings unit vectors?)
    2. Cosine similarity implementation (is it correct?)
    3. Distractor difficulty (are distractors actually challenging?)
    4. Data leakage detection (are targets distinguishable from distractors?)
    5. Statistical sanity checks (variance, distributions)

CONCERNS RAISED:
    - Perfect Recall@1/100 = 1.0000 (impossible for real embeddings)
    - Zero variance in 5 runs (never happens in ML)
    - Too-consistent STS scores (0.9307 ± 0.0255)
    - Contradictory: perfect recall but fails negation (0.9549 similarity)

HYPOTHESIS:
    The test is TOO EASY because distractors are topically unrelated.
    Semantic pairs like "market volatility" vs "market fluctuations"
    are trivially distinguishable from "elephants are the largest animals".

Author: Diagnostic Suite for GAP-001
"""

import random
from typing import Dict

import numpy as np

# =============================================================================
# DIAGNOSTIC 1: Embedding Normalization Check
# =============================================================================


def check_embedding_normalization(get_embedding_func) -> Dict:
    """
    Verify embeddings are properly normalized.

    If embeddings aren't unit vectors, cosine similarity may behave unexpectedly.
    """
    print("\n" + "=" * 70)
    print("DIAGNOSTIC 1: Embedding Normalization Check")
    print("=" * 70)

    test_texts = [
        "The quick brown fox jumps over the lazy dog.",
        "Machine learning models require training data.",
        "a",  # Single character
        "test",  # Single word
        "This is a very long sentence that contains many words and should " * 5,  # Long text
    ]

    results = {"all_normalized": True, "norms": [], "details": []}

    for text in test_texts:
        emb = get_embedding_func(text)
        if emb is None:
            print(f"  [ERROR] Failed to embed: {text[:40]}...")
            results["all_normalized"] = False
            continue

        norm = np.linalg.norm(emb)
        results["norms"].append(norm)

        is_unit = 0.99 < norm < 1.01
        status = "OK" if is_unit else "WARN"
        results["details"].append({"text": text[:40], "norm": norm, "is_unit": is_unit})

        print(f"  [{status}] norm={norm:.6f} | {text[:50]}...")

    # Summary
    norms = np.array(results["norms"])
    if len(norms) > 0:
        print(f"\n  Mean norm: {np.mean(norms):.6f}")
        print(f"  Std norm:  {np.std(norms):.6f}")
        print(f"  Min norm:  {np.min(norms):.6f}")
        print(f"  Max norm:  {np.max(norms):.6f}")

        if 0.99 < np.mean(norms) < 1.01 and np.std(norms) < 0.02:
            print("\n  [PASS] Embeddings are properly L2-normalized")
            results["verdict"] = "PASS"
        else:
            print("\n  [FAIL] Embeddings are NOT properly normalized!")
            print("         This may cause cosine similarity issues.")
            results["verdict"] = "FAIL"
            results["all_normalized"] = False

    return results


# =============================================================================
# DIAGNOSTIC 2: Cosine Similarity Implementation Check
# =============================================================================


def check_cosine_implementation(get_embedding_func) -> Dict:
    """
    Verify cosine similarity returns correct values.

    Tests:
    - Identical texts should have similarity ~1.0
    - Orthogonal vectors should have similarity 0.0
    - Opposite vectors should have similarity -1.0
    - Different texts should have similarity < 1.0
    """
    print("\n" + "=" * 70)
    print("DIAGNOSTIC 2: Cosine Similarity Implementation Check")
    print("=" * 70)

    def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
        """Standard cosine similarity."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    results = {"tests": [], "all_pass": True}

    # Test 1: Orthogonal vectors
    print("\n  Test 1: Orthogonal vectors (should be 0.0)")
    a = np.array([1, 0, 0])
    b = np.array([0, 1, 0])
    sim = cosine_sim(a, b)
    passed = abs(sim) < 0.001
    results["tests"].append({"name": "orthogonal", "expected": 0.0, "actual": sim, "pass": passed})
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] Expected: 0.0, Got: {sim:.6f}")
    if not passed:
        results["all_pass"] = False

    # Test 2: Identical vectors
    print("\n  Test 2: Identical vectors (should be 1.0)")
    a = np.array([1, 2, 3])
    sim = cosine_sim(a, a)
    passed = abs(sim - 1.0) < 0.001
    results["tests"].append({"name": "identical", "expected": 1.0, "actual": sim, "pass": passed})
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] Expected: 1.0, Got: {sim:.6f}")
    if not passed:
        results["all_pass"] = False

    # Test 3: Opposite vectors
    print("\n  Test 3: Opposite vectors (should be -1.0)")
    a = np.array([1, 2, 3])
    b = np.array([-1, -2, -3])
    sim = cosine_sim(a, b)
    passed = abs(sim + 1.0) < 0.001
    results["tests"].append({"name": "opposite", "expected": -1.0, "actual": sim, "pass": passed})
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] Expected: -1.0, Got: {sim:.6f}")
    if not passed:
        results["all_pass"] = False

    # Test 4: Identical text embeddings
    print("\n  Test 4: Same text embeddings (should be ~1.0)")
    text = "The stock market experienced volatility today."
    emb = get_embedding_func(text)
    if emb is not None:
        sim = cosine_sim(emb, emb)
        passed = abs(sim - 1.0) < 0.001
        results["tests"].append(
            {"name": "same_text", "expected": 1.0, "actual": sim, "pass": passed}
        )
        status = "PASS" if passed else "FAIL"
        print(f"    [{status}] Expected: 1.0, Got: {sim:.6f}")
        if not passed:
            results["all_pass"] = False

    # Test 5: Different text embeddings (should be < 1.0)
    print("\n  Test 5: Different texts (should be < 1.0)")
    text1 = "The stock market experienced volatility today."
    text2 = "Elephants are the largest land animals."
    emb1 = get_embedding_func(text1)
    emb2 = get_embedding_func(text2)
    if emb1 is not None and emb2 is not None:
        sim = cosine_sim(emb1, emb2)
        passed = sim < 0.95  # Should be significantly less than 1.0
        results["tests"].append(
            {"name": "different_text", "expected": "<0.95", "actual": sim, "pass": passed}
        )
        status = "PASS" if passed else "FAIL"
        print(f"    [{status}] Expected: <0.95, Got: {sim:.6f}")
        if not passed:
            results["all_pass"] = False

    verdict = "PASS" if results["all_pass"] else "FAIL"
    print(f"\n  [{verdict}] Cosine similarity implementation")
    results["verdict"] = verdict

    return results


# =============================================================================
# DIAGNOSTIC 3: Distractor Difficulty Analysis
# =============================================================================


def check_distractor_difficulty(get_embedding_func) -> Dict:
    """
    CRITICAL: Check if distractors are actually challenging.

    HYPOTHESIS: The benchmark is too easy because:
    - Semantic pairs are TOPICALLY related ("market" + "market")
    - Distractors are TOPICALLY unrelated ("elephants", "pyramids")

    A harder test would use:
    - Same-topic distractors ("market crash" vs "market rally")
    - Near-miss distractors (same domain, different meaning)
    """
    print("\n" + "=" * 70)
    print("DIAGNOSTIC 3: Distractor Difficulty Analysis")
    print("=" * 70)

    def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    # Test case: Financial query with target and distractors
    query = "The stock market experienced significant volatility today."
    target = "Financial markets saw major fluctuations in trading session."

    # Current (EASY) distractors - topically unrelated
    easy_distractors = [
        "Elephants are the largest land animals on Earth.",
        "The Roman Empire collapsed in the fifth century AD.",
        "Mount Everest is the tallest mountain above sea level.",
        "Shakespeare wrote 37 plays during his literary career.",
        "Photosynthesis converts sunlight into chemical energy.",
    ]

    # Proposed (HARD) distractors - same financial domain
    hard_distractors = [
        "The bond market remained stable despite interest rate concerns.",
        "Currency exchange rates showed minimal movement overnight.",
        "Cryptocurrency values declined slightly in Asian trading.",
        "Real estate investment trusts posted modest quarterly gains.",
        "Commodity futures indicated steady pricing through week's end.",
    ]

    # Get embeddings
    query_emb = get_embedding_func(query)
    target_emb = get_embedding_func(target)

    if query_emb is None or target_emb is None:
        print("  [ERROR] Failed to get query/target embeddings")
        return {"verdict": "ERROR"}

    target_sim = cosine_sim(query_emb, target_emb)
    print(f"\n  Query: {query[:60]}...")
    print(f"  Target: {target[:60]}...")
    print(f"  Target Similarity: {target_sim:.4f}")

    # Analyze EASY distractors
    print("\n  EASY DISTRACTORS (topically unrelated):")
    easy_sims = []
    for dist in easy_distractors:
        dist_emb = get_embedding_func(dist)
        if dist_emb is not None:
            sim = cosine_sim(query_emb, dist_emb)
            easy_sims.append(sim)
            gap = target_sim - sim
            status = "TRIVIAL" if gap > 0.2 else "OK" if gap > 0.1 else "HARD"
            print(f"    sim={sim:.4f} gap={gap:+.4f} [{status}] {dist[:50]}...")

    if easy_sims:
        print(f"\n    Mean distractor sim: {np.mean(easy_sims):.4f}")
        print(f"    Max distractor sim:  {np.max(easy_sims):.4f}")
        print(f"    Gap (target - max):  {target_sim - np.max(easy_sims):+.4f}")

    # Analyze HARD distractors
    print("\n  HARD DISTRACTORS (same financial domain):")
    hard_sims = []
    for dist in hard_distractors:
        dist_emb = get_embedding_func(dist)
        if dist_emb is not None:
            sim = cosine_sim(query_emb, dist_emb)
            hard_sims.append(sim)
            gap = target_sim - sim
            status = "TRIVIAL" if gap > 0.2 else "OK" if gap > 0.1 else "HARD"
            print(f"    sim={sim:.4f} gap={gap:+.4f} [{status}] {dist[:50]}...")

    if hard_sims:
        print(f"\n    Mean distractor sim: {np.mean(hard_sims):.4f}")
        print(f"    Max distractor sim:  {np.max(hard_sims):.4f}")
        print(f"    Gap (target - max):  {target_sim - np.max(hard_sims):+.4f}")

    # Verdict
    results = {
        "target_sim": target_sim,
        "easy_mean": np.mean(easy_sims) if easy_sims else 0,
        "easy_max": np.max(easy_sims) if easy_sims else 0,
        "hard_mean": np.mean(hard_sims) if hard_sims else 0,
        "hard_max": np.max(hard_sims) if hard_sims else 0,
    }

    easy_gap = target_sim - results["easy_max"]
    hard_gap = target_sim - results["hard_max"]

    print("\n  ANALYSIS:")
    print(f"    Easy distractor gap: {easy_gap:.4f}")
    print(f"    Hard distractor gap: {hard_gap:.4f}")

    if easy_gap > 0.15 and hard_gap < 0.05:
        print("\n  [CONFIRMED] Test is TOO EASY!")
        print(f"    - Easy distractors have large gap ({easy_gap:.4f}) -> trivial to rank")
        print(f"    - Hard distractors have small gap ({hard_gap:.4f}) -> would fail")
        print("    - Perfect R@1/100 is expected with current easy distractors")
        results["verdict"] = "TOO_EASY"
        results["explanation"] = (
            "Current distractors are topically unrelated. "
            "Perfect recall is expected because target is obviously closest. "
            "Need same-domain hard negatives for realistic benchmark."
        )
    elif easy_gap > 0.10:
        print("\n  [WARNING] Test may be too easy")
        print(f"    - Easy distractors have notable gap ({easy_gap:.4f})")
        results["verdict"] = "EASY"
    else:
        print("\n  [OK] Test difficulty appears reasonable")
        results["verdict"] = "OK"

    return results


# =============================================================================
# DIAGNOSTIC 4: Statistical Sanity Check
# =============================================================================


def check_statistical_sanity(get_embedding_func, num_runs: int = 5) -> Dict:
    """
    Check for statistical anomalies.

    Concerns:
    - Zero variance across runs (impossible in ML)
    - Too-consistent similarity scores
    - Missing randomization
    """
    print("\n" + "=" * 70)
    print("DIAGNOSTIC 4: Statistical Sanity Check")
    print("=" * 70)

    def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    # Test pairs
    pairs = [
        ("The economy grew by 3% last quarter.", "Economic growth reached three percent."),
        ("Machine learning is transforming industries.", "AI is reshaping businesses."),
        ("The weather will be sunny tomorrow.", "Forecast predicts clear skies."),
    ]

    # Easy distractors (same as original benchmark)
    distractors = [
        "Elephants are large animals.",
        "The Great Wall is in China.",
        "Pizza originated in Italy.",
        "Sharks swim in the ocean.",
        "Trees produce oxygen.",
    ]

    print(f"\n  Running {num_runs} retrieval trials with randomized distractors...")

    results_by_run = []

    for run_id in range(num_runs):
        random.seed(None)  # Ensure randomization
        run_results = []

        for query, target in pairs:
            query_emb = get_embedding_func(query)
            target_emb = get_embedding_func(target)

            if query_emb is None or target_emb is None:
                continue

            target_sim = cosine_sim(query_emb, target_emb)

            # Shuffle distractors each run
            shuffled = distractors.copy()
            random.shuffle(shuffled)

            # Compute distractor similarities
            distractor_sims = []
            for dist in shuffled[:3]:  # Use subset
                dist_emb = get_embedding_func(dist)
                if dist_emb is not None:
                    sim = cosine_sim(query_emb, dist_emb)
                    distractor_sims.append(sim)

            # Is target top-1?
            if distractor_sims:
                is_hit = target_sim > max(distractor_sims)
                run_results.append(1.0 if is_hit else 0.0)

        recall = np.mean(run_results) if run_results else 0
        results_by_run.append(recall)
        print(f"    Run {run_id+1}: R@1 = {recall:.4f}")

    # Analyze variance
    results_arr = np.array(results_by_run)
    mean_recall = np.mean(results_arr)
    std_recall = np.std(results_arr)

    print(f"\n  Mean R@1: {mean_recall:.4f}")
    print(f"  Std R@1:  {std_recall:.4f}")

    results = {
        "runs": results_by_run,
        "mean": mean_recall,
        "std": std_recall,
    }

    if std_recall == 0.0 and mean_recall == 1.0:
        print("\n  [EXPECTED] Zero variance + perfect recall")
        print("    - This is expected when distractors are trivially different")
        print("    - Not a bug, but indicates test is too easy")
        results["verdict"] = "EXPECTED_EASY"
    elif std_recall == 0.0:
        print("\n  [WARNING] Zero variance is suspicious")
        print("    - May indicate caching or deterministic bug")
        results["verdict"] = "SUSPICIOUS"
    else:
        print("\n  [OK] Variance is present")
        results["verdict"] = "OK"

    return results


# =============================================================================
# DIAGNOSTIC 5: Hard Negative Retrieval Test
# =============================================================================


def check_hard_negative_retrieval(get_embedding_func) -> Dict:
    """
    The REAL test: Can UltraBERT distinguish semantic matches from
    same-domain hard negatives?

    This is what the original benchmark SHOULD have tested.
    """
    print("\n" + "=" * 70)
    print("DIAGNOSTIC 5: Hard Negative Retrieval Test")
    print("=" * 70)

    def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    # Query-Target-HardNegative triplets (same domain!)
    triplets = [
        # Financial
        (
            "The stock market experienced significant volatility today.",
            "Financial markets saw major fluctuations in trading.",
            "The stock market remained calm with minimal trading activity.",  # Hard negative: opposite meaning!
        ),
        # Technical
        (
            "Machine learning models require large datasets for training.",
            "Neural networks need substantial data collections to learn.",
            "Machine learning models can work with small datasets.",  # Hard negative: contradicts!
        ),
        # Medical
        (
            "The patient's condition improved significantly after treatment.",
            "The person's health got much better following therapy.",
            "The patient's condition worsened despite treatment.",  # Hard negative: opposite!
        ),
        # Weather
        (
            "Heavy rainfall caused flooding in coastal regions.",
            "Intense precipitation led to inundation along shorelines.",
            "Drought conditions persisted in coastal regions.",  # Hard negative: opposite!
        ),
        # Business
        (
            "The company reported strong quarterly earnings growth.",
            "The firm announced impressive three-month revenue increases.",
            "The company reported weak quarterly earnings decline.",  # Hard negative: opposite!
        ),
        # Casual
        (
            "I really enjoyed the movie, it was fantastic.",
            "The film was great, I had a wonderful time watching it.",
            "I really hated the movie, it was terrible.",  # Hard negative: opposite!
        ),
    ]

    print("\n  Testing with same-domain hard negatives (the REAL test):\n")

    results = {"hits": 0, "misses": 0, "details": []}

    for query, target, hard_neg in triplets:
        query_emb = get_embedding_func(query)
        target_emb = get_embedding_func(target)
        hard_neg_emb = get_embedding_func(hard_neg)

        if query_emb is None or target_emb is None or hard_neg_emb is None:
            print("  [ERROR] Failed to embed triplet")
            continue

        target_sim = cosine_sim(query_emb, target_emb)
        hard_neg_sim = cosine_sim(query_emb, hard_neg_emb)

        is_hit = target_sim > hard_neg_sim
        gap = target_sim - hard_neg_sim

        status = "HIT" if is_hit else "MISS"
        results["hits" if is_hit else "misses"] += 1

        results["details"].append(
            {
                "query": query[:50],
                "target_sim": target_sim,
                "hard_neg_sim": hard_neg_sim,
                "gap": gap,
                "hit": is_hit,
            }
        )

        print(f"  [{status}] gap={gap:+.4f}")
        print(f"       Query: {query[:60]}...")
        print(f"       Target sim:    {target_sim:.4f}")
        print(f"       Hard-neg sim:  {hard_neg_sim:.4f}")
        print()

    # Summary
    total = results["hits"] + results["misses"]
    accuracy = results["hits"] / total if total > 0 else 0

    print(f"\n  HARD NEGATIVE ACCURACY: {accuracy:.1%} ({results['hits']}/{total})")

    results["accuracy"] = accuracy

    if accuracy < 0.5:
        print("\n  [FAIL] UltraBERT FAILS on hard negatives!")
        print("    - Cannot distinguish targets from same-domain contradictions")
        print("    - This confirms the original benchmark was TOO EASY")
        print("    - Perfect R@1/100 was due to trivial distractors, not model quality")
        results["verdict"] = "FAIL"
    elif accuracy < 0.8:
        print("\n  [WARN] UltraBERT struggles with hard negatives")
        results["verdict"] = "WEAK"
    else:
        print("\n  [PASS] UltraBERT handles hard negatives well")
        results["verdict"] = "PASS"

    return results


# =============================================================================
# DIAGNOSTIC 6: Embedding Determinism Check
# =============================================================================


def check_embedding_determinism(get_embedding_func) -> Dict:
    """
    Check if embeddings are deterministic (same input -> same output).

    If not deterministic, could explain variance issues.
    """
    print("\n" + "=" * 70)
    print("DIAGNOSTIC 6: Embedding Determinism Check")
    print("=" * 70)

    test_text = "The quick brown fox jumps over the lazy dog."

    embeddings = []
    for i in range(5):
        emb = get_embedding_func(test_text)
        if emb is not None:
            embeddings.append(emb.copy())

    if len(embeddings) < 2:
        print("  [ERROR] Could not get multiple embeddings")
        return {"verdict": "ERROR"}

    # Check if all embeddings are identical
    all_identical = True
    for i in range(1, len(embeddings)):
        if not np.allclose(embeddings[0], embeddings[i]):
            all_identical = False
            diff = np.linalg.norm(embeddings[0] - embeddings[i])
            print(f"  Run {i+1}: diff={diff:.6f}")

    if all_identical:
        print("\n  [OK] Embeddings are deterministic (identical across runs)")
        return {"verdict": "DETERMINISTIC", "identical": True}
    else:
        print("\n  [WARN] Embeddings are NOT deterministic")
        print("    This may cause variance in benchmarks")
        return {"verdict": "NON_DETERMINISTIC", "identical": False}


# =============================================================================
# MAIN DIAGNOSTIC RUNNER
# =============================================================================


def run_all_diagnostics():
    """Run all diagnostic checks."""
    print("\n" + "=" * 70)
    print("BENCHMARK DIAGNOSTIC SUITE")
    print("=" * 70)
    print("\n  Purpose: Validate the benchmark harness before trusting results")
    print("  Concern: Perfect R@1/100 = 1.0 is statistically impossible")
    print("\n  Loading UltraBERT adapter...")

    # Import UltraBERT (same method as embedding_benchmark_suite.py)
    try:
        from k0.runtime.ultrabert_adapter import get_embedding as ultrabert_get_embedding

        # Wrapper to convert list to numpy array
        def get_embedding(text: str):
            result = ultrabert_get_embedding(text)
            if result is not None:
                return np.array(result, dtype=np.float32)
            return None

        # Test the embedding function
        test_emb = get_embedding("test")
        if test_emb is None:
            print("  [ERROR] UltraBERT returned None for test embedding")
            return

        print(f"  UltraBERT loaded successfully (dim={len(test_emb)})")

    except ImportError as e:
        print(f"  [ERROR] Could not import UltraBERT: {e}")
        return

    # Run diagnostics
    results = {}

    results["normalization"] = check_embedding_normalization(get_embedding)
    results["cosine_impl"] = check_cosine_implementation(get_embedding)
    results["distractor_difficulty"] = check_distractor_difficulty(get_embedding)
    results["statistical_sanity"] = check_statistical_sanity(get_embedding)
    results["hard_negatives"] = check_hard_negative_retrieval(get_embedding)
    results["determinism"] = check_embedding_determinism(get_embedding)

    # Final Summary
    print("\n" + "=" * 70)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 70)

    print(f"\n  1. Normalization:      {results['normalization'].get('verdict', 'N/A')}")
    print(f"  2. Cosine Impl:        {results['cosine_impl'].get('verdict', 'N/A')}")
    print(f"  3. Distractor Diff:    {results['distractor_difficulty'].get('verdict', 'N/A')}")
    print(f"  4. Statistical Sanity: {results['statistical_sanity'].get('verdict', 'N/A')}")
    print(f"  5. Hard Negatives:     {results['hard_negatives'].get('verdict', 'N/A')}")
    print(f"  6. Determinism:        {results['determinism'].get('verdict', 'N/A')}")

    # Interpret results
    print("\n" + "=" * 70)
    print("INTERPRETATION")
    print("=" * 70)

    if results["distractor_difficulty"].get("verdict") == "TOO_EASY":
        print(
            """
  [CONFIRMED] The benchmark is TOO EASY.

  The "perfect" R@1/100 = 1.0 is REAL but MISLEADING:

  1. Current distractors are topically UNRELATED:
     - Target: "market volatility" vs "market fluctuations" (same topic)
     - Distractors: "elephants", "pyramids", "Shakespeare" (different topics)

  2. UltraBERT can trivially distinguish different topics.
     This is expected and not impressive.

  3. When tested with HARD negatives (same topic, different meaning),
     UltraBERT accuracy drops to: {:.1%}

  4. The reviewer was CORRECT: The results are "impossible" for a real
     benchmark, but the benchmark itself was flawed, not fabricated.

  RECOMMENDATION:
  - Replace current distractors with same-domain hard negatives
  - Use standard benchmarks (MTEB, BEIR) for comparison
  - Report hard-negative accuracy alongside easy-distractor accuracy
""".format(
                results["hard_negatives"].get("accuracy", 0)
            )
        )
    else:
        print("\n  Further investigation needed.")

    return results


if __name__ == "__main__":
    run_all_diagnostics()
    run_all_diagnostics()
    run_all_diagnostics()
    run_all_diagnostics()
    run_all_diagnostics()
    run_all_diagnostics()
    run_all_diagnostics()
