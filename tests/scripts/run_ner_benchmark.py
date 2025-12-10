"""Run NER benchmark against golden dataset."""

import asyncio
import sys

from k0.modules.hippocampus.transformer_ner import NERModelTier, TransformerNER
from tests.fixtures.golden_dataset.loader import load_golden_dataset


async def benchmark(model_tier: str = "bert"):
    """Run NER benchmark."""
    dataset = load_golden_dataset()
    print(f"Loaded {len(dataset.memories)} memories")

    # Select model tier
    if model_tier == "ontonotes":
        ner = TransformerNER(
            model_tier=NERModelTier.ONTONOTES_FAST,
            enable_family_detection=True,
            enable_place_detection=True,
            enable_activity_detection=True,
            enable_event_detection=True,
            enable_food_detection=True,
            enable_pet_detection=True,
        )
    else:
        ner = TransformerNER(
            model_tier=NERModelTier.BERT_BASE,
            enable_family_detection=True,
            enable_place_detection=True,
            enable_activity_detection=True,
            enable_event_detection=True,
            enable_food_detection=True,
            enable_pet_detection=True,
        )

    await ner.initialize()
    print(f"NER initialized with model: {ner.model_name}")
    print(f"Model type: {ner._model_type}")
    print(f"SpaCy loaded: {ner._spacy_nlp is not None}")

    total_gt = 0
    total_pred = 0
    matches = 0
    by_type: dict = {}

    for mem in dataset.memories[:50]:  # First 50 for quick test
        result = ner.extract(mem.text)
        pred_texts = {e.text.lower(): e.label for e in result.entities}
        gt_texts = {e.text.lower(): e.type.value for e in mem.ground_truth.entities}

        for text, gt_type in gt_texts.items():
            total_gt += 1
            if gt_type not in by_type:
                by_type[gt_type] = {"gt": 0, "found": 0}
            by_type[gt_type]["gt"] += 1
            if text in pred_texts:
                matches += 1
                by_type[gt_type]["found"] += 1
        total_pred += len(pred_texts)

    print("\n=== Summary (first 50 memories) ===")
    print(f"Total GT: {total_gt}, Predicted: {total_pred}, Matches: {matches}")
    if total_gt > 0:
        print(f"Recall: {matches/total_gt:.1%}")
    if total_pred > 0:
        print(f"Precision: {matches/total_pred:.1%}")

    print("\n=== By Entity Type ===")
    for t, c in sorted(by_type.items()):
        r = c["found"] / c["gt"] if c["gt"] > 0 else 0
        print(f"  {t}: {c['found']}/{c['gt']} ({r:.1%})")

    # Print NER stats
    print("\n=== NER Stats ===")
    stats = ner.get_stats()
    print(f"  Avg latency: {stats['avg_latency_ms']:.1f}ms")
    print(f"  Model: {stats['model']}")


if __name__ == "__main__":
    model = sys.argv[1] if len(sys.argv) > 1 else "bert"
    print(f"Running benchmark with model: {model}")
    asyncio.run(benchmark(model))
