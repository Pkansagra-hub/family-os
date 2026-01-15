"""
MS-MARCO Official Benchmark for UltraBERT

Compares UltraBERT against published scores from:
- OpenAI text-embedding-3-large: MTEB avg 64.6%
- OpenAI text-embedding-3-small: MTEB avg 62.3%
- E5-large-v2: Industry standard open-source

Reference: https://openai.com/blog/new-embedding-models-and-api-updates
"""

import time
from typing import Dict, List, Tuple

import numpy as np
from datasets import load_dataset

# UltraBERT imports
try:
    from familyos_ultrabert import Client

    ULTRABERT_AVAILABLE = True
except ImportError:
    ULTRABERT_AVAILABLE = False
    print("WARNING: familyos_ultrabert not available")


# ============================================================================
# REFERENCE SCORES FROM PUBLISHED BENCHMARKS
# ============================================================================

REFERENCE_SCORES = {
    # OpenAI Blog: https://openai.com/blog/new-embedding-models-and-api-updates
    "text-embedding-3-large": {
        "MTEB_avg": 0.646,
        "MIRACL_avg": 0.549,
        "dimensions": 3072,
        "source": "OpenAI Blog Jan 2024",
    },
    "text-embedding-3-small": {
        "MTEB_avg": 0.623,
        "MIRACL_avg": 0.440,
        "dimensions": 1536,
        "source": "OpenAI Blog Jan 2024",
    },
    "text-embedding-ada-002": {
        "MTEB_avg": 0.610,
        "MIRACL_avg": 0.314,
        "dimensions": 1536,
        "source": "OpenAI Blog Jan 2024",
    },
    # MTEB Leaderboard top models
    "E5-large-v2": {
        "MTEB_avg": 0.624,
        "MS-MARCO_MRR@10": 0.430,
        "dimensions": 1024,
        "source": "MTEB Leaderboard",
    },
    "all-mpnet-base-v2": {
        "MTEB_avg": 0.578,
        "STS-B": 0.838,
        "dimensions": 768,
        "source": "MTEB Leaderboard",
    },
    "all-MiniLM-L6-v2": {
        "MTEB_avg": 0.569,
        "STS-B": 0.789,
        "dimensions": 384,
        "source": "MTEB Leaderboard",
    },
}


class MSMARCOBenchmark:
    """Benchmark UltraBERT on MS-MARCO subset."""

    def __init__(self):
        if ULTRABERT_AVAILABLE:
            print("Loading UltraBERT...")
            self.client = Client()
            print("UltraBERT loaded.")
        else:
            self.client = None

        self._embedding_cache: Dict[str, np.ndarray] = {}

    def get_embedding(self, text: str) -> np.ndarray:
        """Get embedding with caching."""
        if text in self._embedding_cache:
            return self._embedding_cache[text]

        if self.client is None:
            raise RuntimeError("UltraBERT not available")

        result = self.client.analyze(text)
        embedding = np.array(result.embedding)
        self._embedding_cache[text] = embedding
        return embedding

    def cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity."""
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    def load_msmarco_dev(self, num_samples: int = 100) -> List[Dict]:
        """Load MS-MARCO dev set samples."""
        print(f"\nLoading MS-MARCO dev set ({num_samples} samples)...")

        try:
            # Load MS-MARCO passage ranking dataset
            dataset = load_dataset("ms_marco", "v1.1", split="validation", trust_remote_code=True)

            samples = []
            for i, item in enumerate(dataset):
                if i >= num_samples:
                    break

                query = item.get("query", "")
                passages = item.get("passages", {})

                if not query or not passages:
                    continue

                passage_texts = passages.get("passage_text", [])
                is_selected = passages.get("is_selected", [])

                if not passage_texts or not is_selected:
                    continue

                # Find positive passage
                positive_idx = None
                for idx, selected in enumerate(is_selected):
                    if selected == 1:
                        positive_idx = idx
                        break

                if positive_idx is None:
                    continue

                samples.append(
                    {
                        "query": query,
                        "positive": passage_texts[positive_idx],
                        "negatives": [
                            p for idx, p in enumerate(passage_texts) if idx != positive_idx
                        ],
                    }
                )

            print(f"  Loaded {len(samples)} query-passage pairs")
            return samples

        except Exception as e:
            print(f"  Error loading MS-MARCO: {e}")
            print("  Using synthetic MS-MARCO-style data instead...")
            return self._get_synthetic_msmarco()

    def _get_synthetic_msmarco(self) -> List[Dict]:
        """Synthetic MS-MARCO-style data for testing."""
        return [
            {
                "query": "what is the capital of france",
                "positive": "Paris is the capital and most populous city of France, with an estimated population of 2,161,000 residents.",
                "negatives": [
                    "France is a country located in Western Europe, known for its art, culture, and cuisine.",
                    "The French Revolution began in 1789 and fundamentally changed French society.",
                    "French is a Romance language that originated in France and is now spoken worldwide.",
                    "The Eiffel Tower is a wrought-iron lattice tower on the Champ de Mars in Paris.",
                ],
            },
            {
                "query": "how does photosynthesis work",
                "positive": "Photosynthesis is the process by which green plants use sunlight to synthesize foods from carbon dioxide and water, generating oxygen as a byproduct.",
                "negatives": [
                    "Plants are multicellular organisms that belong to the kingdom Plantae.",
                    "Chlorophyll is the green pigment found in the chloroplasts of plant cells.",
                    "The carbon cycle describes the movement of carbon through Earth's systems.",
                    "Sunlight travels at approximately 299,792 kilometers per second.",
                ],
            },
            {
                "query": "symptoms of diabetes",
                "positive": "Common symptoms of diabetes include increased thirst, frequent urination, extreme hunger, unexplained weight loss, fatigue, and blurred vision.",
                "negatives": [
                    "Diabetes is a metabolic disease that affects how the body processes blood sugar.",
                    "Insulin is a hormone produced by the pancreas that regulates blood glucose.",
                    "The American Diabetes Association provides resources for diabetes management.",
                    "Blood sugar levels can be affected by diet, exercise, and medication.",
                ],
            },
            {
                "query": "who wrote romeo and juliet",
                "positive": "Romeo and Juliet is a tragedy written by William Shakespeare early in his career about two young Italian star-crossed lovers.",
                "negatives": [
                    "Shakespeare was an English playwright and poet who lived during the late 16th century.",
                    "The Globe Theatre was a famous London theater where many of Shakespeare's plays were performed.",
                    "Tragedy is a form of drama based on human suffering that invokes catharsis.",
                    "Italian literature has a rich history dating back to the Middle Ages.",
                ],
            },
            {
                "query": "how to make pizza dough",
                "positive": "To make pizza dough, combine flour, yeast, salt, and warm water. Knead for 10 minutes until smooth, then let rise for 1-2 hours until doubled.",
                "negatives": [
                    "Pizza originated in Italy and has become one of the world's most popular foods.",
                    "Yeast is a single-celled fungus used in baking and brewing.",
                    "Flour is a powder made by grinding raw grains or roots.",
                    "Italian cuisine is known for its regional diversity and emphasis on fresh ingredients.",
                ],
            },
            {
                "query": "what causes earthquakes",
                "positive": "Earthquakes are caused by the sudden release of energy in Earth's lithosphere due to tectonic plate movements, volcanic activity, or fault line ruptures.",
                "negatives": [
                    "The Richter scale measures the magnitude of earthquakes from 0 to 10.",
                    "Seismology is the scientific study of earthquakes and seismic waves.",
                    "The Pacific Ring of Fire is a region with frequent volcanic and seismic activity.",
                    "Tectonic plates are massive segments of Earth's lithosphere that move slowly.",
                ],
            },
            {
                "query": "benefits of meditation",
                "positive": "Meditation offers numerous benefits including reduced stress, improved concentration, lower blood pressure, enhanced self-awareness, and better emotional health.",
                "negatives": [
                    "Meditation is a practice where an individual uses techniques like mindfulness.",
                    "Yoga is an ancient practice that combines physical postures with breathing exercises.",
                    "Stress management involves techniques to cope with psychological stress.",
                    "Mental health includes emotional, psychological, and social well-being.",
                ],
            },
            {
                "query": "difference between alligators and crocodiles",
                "positive": "Alligators have U-shaped snouts and only upper teeth visible, while crocodiles have V-shaped snouts with both upper and lower teeth visible when mouths closed.",
                "negatives": [
                    "Crocodilians are large reptiles that live in tropical regions worldwide.",
                    "Reptiles are cold-blooded vertebrates with scaly skin.",
                    "The Everglades in Florida is home to both alligators and crocodiles.",
                    "Apex predators are animals at the top of the food chain.",
                ],
            },
            {
                "query": "how do vaccines work",
                "positive": "Vaccines work by training the immune system to recognize and fight pathogens by introducing weakened or inactivated parts of the pathogen to trigger an immune response.",
                "negatives": [
                    "Immunology is the study of the immune system and its functions.",
                    "Pathogens are microorganisms that can cause disease in hosts.",
                    "The World Health Organization coordinates international health efforts.",
                    "Antibodies are proteins produced by the immune system to neutralize threats.",
                ],
            },
            {
                "query": "why is the sky blue",
                "positive": "The sky appears blue because molecules in the atmosphere scatter shorter wavelength blue light from the sun more than longer wavelength red light, a phenomenon called Rayleigh scattering.",
                "negatives": [
                    "The atmosphere is the layer of gases surrounding Earth.",
                    "Light travels in waves with different wavelengths corresponding to colors.",
                    "Sunsets appear red because light travels through more atmosphere.",
                    "The color spectrum ranges from red to violet in visible light.",
                ],
            },
        ]

    def compute_mrr(self, samples: List[Dict]) -> Tuple[float, Dict]:
        """Compute Mean Reciprocal Rank."""
        print("\nComputing MRR@10...")

        reciprocal_ranks = []
        hits_at_1 = 0
        hits_at_5 = 0
        hits_at_10 = 0

        for i, sample in enumerate(samples):
            query = sample["query"]
            positive = sample["positive"]
            negatives = sample["negatives"]

            # Get embeddings
            query_emb = self.get_embedding(query)
            pos_emb = self.get_embedding(positive)
            neg_embs = [self.get_embedding(n) for n in negatives]

            # Score all candidates
            pos_score = self.cosine_similarity(query_emb, pos_emb)
            neg_scores = [self.cosine_similarity(query_emb, e) for e in neg_embs]

            # Combine and rank
            all_scores = [(positive, pos_score)] + list(zip(negatives, neg_scores))
            all_scores.sort(key=lambda x: x[1], reverse=True)

            # Find rank of positive
            rank = None
            for idx, (text, score) in enumerate(all_scores, 1):
                if text == positive:
                    rank = idx
                    break

            if rank:
                reciprocal_ranks.append(1.0 / rank)
                if rank == 1:
                    hits_at_1 += 1
                if rank <= 5:
                    hits_at_5 += 1
                if rank <= 10:
                    hits_at_10 += 1

                status = f"rank={rank}" if rank > 1 else "HIT@1"
                print(f"  [{i+1:3d}/{len(samples)}] {status:8s} | {query[:50]}...")
            else:
                reciprocal_ranks.append(0.0)
                print(f"  [{i+1:3d}/{len(samples)}] MISS     | {query[:50]}...")

        mrr = float(np.mean(reciprocal_ranks)) if reciprocal_ranks else 0.0
        n = len(samples)

        results = {
            "MRR@10": mrr,
            "Recall@1": hits_at_1 / n if n > 0 else 0,
            "Recall@5": hits_at_5 / n if n > 0 else 0,
            "Recall@10": hits_at_10 / n if n > 0 else 0,
            "num_samples": n,
        }

        return mrr, results

    def run_benchmark(self, num_samples: int = 100) -> Dict:
        """Run full MS-MARCO benchmark."""
        print("\n" + "=" * 70)
        print("MS-MARCO BENCHMARK FOR ULTRABERT")
        print("=" * 70)

        # Load data
        samples = self.load_msmarco_dev(num_samples)

        if not samples:
            print("ERROR: No samples loaded")
            return {}

        # Compute MRR
        start_time = time.time()
        mrr, results = self.compute_mrr(samples)
        elapsed = time.time() - start_time

        results["elapsed_seconds"] = elapsed
        results["queries_per_second"] = len(samples) / elapsed if elapsed > 0 else 0

        # Print results
        self._print_results(results)

        return results

    def _print_results(self, results: Dict):
        """Print benchmark results with comparison."""
        print("\n" + "=" * 70)
        print("RESULTS")
        print("=" * 70)

        print("\n  UltraBERT Performance:")
        print(f"    MRR@10:    {results['MRR@10']:.4f}")
        print(f"    Recall@1:  {results['Recall@1']:.4f}")
        print(f"    Recall@5:  {results['Recall@5']:.4f}")
        print(f"    Recall@10: {results['Recall@10']:.4f}")
        print(f"    Samples:   {results['num_samples']}")
        print(f"    Time:      {results['elapsed_seconds']:.1f}s")
        print(f"    QPS:       {results['queries_per_second']:.1f}")

        print("\n" + "-" * 70)
        print("COMPARISON WITH PUBLISHED SCORES")
        print("-" * 70)

        print("\n  Model                      | MTEB Avg | Dimensions | Source")
        print("  " + "-" * 66)

        for model, scores in REFERENCE_SCORES.items():
            mteb = scores.get("MTEB_avg", 0) * 100
            dims = scores.get("dimensions", "N/A")
            source = scores.get("source", "")
            print(f"  {model:27s} | {mteb:6.1f}%  | {dims:10} | {source}")

        print(f"  {'UltraBERT v3.0.1':27s} | {'TBD':>6s}   | {768:10} | This benchmark")

        # E5-large comparison (most relevant)
        e5_mrr = REFERENCE_SCORES["E5-large-v2"].get("MS-MARCO_MRR@10", 0.43)
        our_mrr = results["MRR@10"]

        print("\n" + "-" * 70)
        print("MS-MARCO MRR@10 COMPARISON")
        print("-" * 70)

        if our_mrr > e5_mrr:
            verdict = "EXCEEDS"
            delta = f"+{our_mrr - e5_mrr:.3f}"
        elif our_mrr > e5_mrr * 0.9:
            verdict = "COMPETITIVE"
            delta = f"{our_mrr - e5_mrr:.3f}"
        else:
            verdict = "BELOW"
            delta = f"{our_mrr - e5_mrr:.3f}"

        print(f"\n  E5-large-v2 (reference):  {e5_mrr:.3f}")
        print(f"  UltraBERT:                {our_mrr:.3f} ({delta})")
        print(f"\n  Verdict: {verdict}")

        if our_mrr > 0.40:
            print("  Assessment: EXCELLENT - Competitive with SOTA open-source models")
        elif our_mrr > 0.35:
            print("  Assessment: GOOD - Reasonable retrieval performance")
        elif our_mrr > 0.30:
            print("  Assessment: FAIR - Below average for retrieval")
        else:
            print("  Assessment: NEEDS WORK - Consider retrieval fine-tuning")


def main():
    """Run the benchmark."""
    if not ULTRABERT_AVAILABLE:
        print("ERROR: familyos_ultrabert not installed")
        return

    benchmark = MSMARCOBenchmark()

    # Run on 500 samples for statistical significance
    print("\n" + "=" * 70)
    print("MS-MARCO BENCHMARK (500 samples)")
    print("=" * 70)
    benchmark.run_benchmark(num_samples=500)


if __name__ == "__main__":
    main()
