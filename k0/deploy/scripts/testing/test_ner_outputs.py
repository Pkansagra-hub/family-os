#!/usr/bin/env python3
"""
NER Output Comparison Script - Compare BERT-NER vs UltraBERT NER outputs.

This script sends test sentences to both NER models and shows raw outputs
to help understand their label outputs and identify misclassification patterns.

Usage (inside k0-kernel container):
    python -m k0.deploy.test_ner_outputs

Or directly:
    docker exec -it k0-kernel python -m k0.deploy.test_ner_outputs
"""

from typing import Any


def test_bert_ner(sentences: list[str]) -> dict[str, Any]:
    """Test BERT-NER (dslim/bert-base-NER) on sentences."""
    print("\n" + "=" * 80)
    print("BERT-NER (dslim/bert-base-NER) - Labels: PER, ORG, LOC, MISC")
    print("=" * 80)

    try:
        from k0.modules.consolidation.algorithms.bert_ner_adapter import get_bert_ner

        ner = get_bert_ner()
        print(f"Model: {ner.MODEL_NAME}")
        print("-" * 80)

        results = {}
        for sentence in sentences:
            entities = ner.extract(sentence)
            results[sentence] = [
                {"text": e.text, "label": e.label, "score": round(e.score, 3)} for e in entities
            ]

            print(f"\nText: {sentence}")
            if entities:
                for e in entities:
                    print(f"  -> '{e.text}' | {e.label} | score={e.score:.3f}")
            else:
                print("  -> (no entities)")

        return results

    except Exception as e:
        print(f"ERROR: {e}")
        return {}


def test_ultrabert_ner(sentences: list[str]) -> dict[str, Any]:
    """Test UltraBERT NER heads on sentences."""
    print("\n" + "=" * 80)
    print("UltraBERT NER - 3 heads: ner_family, ner_general, temporal")
    print("=" * 80)

    try:
        from k0.runtime.ultrabert_adapter import get_ultrabert_client

        client = get_ultrabert_client()
        if client is None:
            print("ERROR: UltraBERT client not available")
            return {}

        print(f"Model: UltraBERT v{getattr(client, 'VERSION', 'unknown')}")
        print("-" * 80)

        results = {}
        for sentence in sentences:
            result = client.analyze(sentence)

            # Extract entities from all 3 heads
            ner_family = getattr(result, "entities", None) or []
            ner_general = getattr(result, "general_entities", None) or []
            temporal = getattr(result, "temporal", None) or []

            results[sentence] = {
                "ner_family": ner_family,
                "ner_general": ner_general,
                "temporal": temporal,
            }

            print(f"\nText: {sentence}")

            print("  ner_family:")
            if ner_family:
                for e in ner_family:
                    text = e.get("text", e) if isinstance(e, dict) else str(e)
                    label = e.get("label", "?") if isinstance(e, dict) else "?"
                    print(f"    - '{text}' | {label}")
            else:
                print("    -> (none)")

            print("  ner_general:")
            if ner_general:
                for e in ner_general:
                    text = e.get("text", e) if isinstance(e, dict) else str(e)
                    label = e.get("label", "?") if isinstance(e, dict) else "?"
                    print(f"    -> '{text}' | {label}")
            else:
                print("    -> (none)")

            print("  temporal:")
            if temporal:
                for e in temporal:
                    text = e.get("text", e) if isinstance(e, dict) else str(e)
                    label = e.get("label", "?") if isinstance(e, dict) else "?"
                    print(f"    -> '{text}' | {label}")
            else:
                print("    -> (none)")

        return results

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback

        traceback.print_exc()
        return {}


def test_entity_extractor(sentences: list[str]) -> dict[str, Any]:
    """Test full entity extractor pipeline (hybrid mode)."""
    print("\n" + "=" * 80)
    print("Entity Extractor (Hybrid Mode) - UltraBERT ner_family + BERT-NER general")
    print("=" * 80)

    try:
        from k0.modules.consolidation.algorithms.entity_extractor import UltraBERTEntityExtractor
        from k0.runtime.ultrabert_adapter import get_ultrabert_client

        client = get_ultrabert_client()
        extractor = UltraBERTEntityExtractor()

        print("Label Mapping (source label -> KG type):")
        for label, (kg_type, priority) in extractor.LABEL_MAPPING.items():
            print(f"  {label:15} -> {kg_type.value:15} (priority={priority})")
        print("-" * 80)

        results = {}
        for sentence in sentences:
            # Get UltraBERT output
            ultrabert_result = client.analyze(sentence)

            # Extract using hybrid mode (ner_family from UltraBERT, general from BERT-NER)
            entities = extractor.extract_hybrid(
                source_text=sentence,
                ner_family_output={"entities": ultrabert_result.entities or []},
                temporal_output={"entities": ultrabert_result.temporal or []},
            )

            results[sentence] = [e.to_dict() for e in entities]

            print(f"\nText: {sentence}")
            if entities:
                for e in entities:
                    print(
                        f"  -> '{e.text}' | {e.kg_type.value} | source={e.source_head} | label={e.source_label}"
                    )
            else:
                print("  -> (no entities)")

        return results

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback

        traceback.print_exc()
        return {}


def print_label_schemas():
    """Print all NER label schemas from UltraBERT."""
    print("\n" + "#" * 80)
    print("# NER LABEL SCHEMAS (from familyos_ultrabert.labels)")
    print("#" * 80)

    try:
        from familyos_ultrabert.labels import NER_FAMILY_LABELS, NER_GENERAL_LABELS, TEMPORAL_LABELS

        print("\n" + "=" * 80)
        print("NER_FAMILY_LABELS - Family-specific entity recognition")
        print("=" * 80)
        print(f"Description: {NER_FAMILY_LABELS.description}")
        print(f"Problem type: {NER_FAMILY_LABELS.problem_type}")
        print("\nLabels (excluding BIO prefixes):")

        # Extract unique labels (remove B-/I- prefixes and O tag)
        family_labels = set()
        for label in NER_FAMILY_LABELS.label2id.keys():
            if label != "O" and "-" in label:
                family_labels.add(label.split("-", 1)[1])

        label_descriptions = {
            "PERSON": "Named individuals (e.g., 'Emma', 'John')",
            "KINSHIP": "Family relationship terms (e.g., 'mom', 'grandma', 'wife')",
            "NICKNAME": "Family nicknames (e.g., 'kiddo', 'sweetie')",
            "PET": "Family pets (e.g., 'Fluffy the cat', 'Max')",
            "HOME_LOC": "Family-related locations (e.g., 'home', 'grandma's house')",
            "FAMILY_EVENT": "Family occasions (e.g., 'birthday', 'reunion', 'wedding')",
            "ROUTINE": "Daily family routines (e.g., 'bedtime', 'dinner time')",
            "TRADITION": "Family traditions (e.g., 'Sunday dinner', 'Christmas eve')",
            "MILESTONE": "Life milestones (e.g., 'graduation', 'first steps')",
            "HEIRLOOM": "Family heirlooms/keepsakes (e.g., 'grandma's ring')",
        }

        for label in sorted(family_labels):
            desc = label_descriptions.get(label, "(no description)")
            print(f"  {label:15} - {desc}")

        print("\n" + "=" * 80)
        print("NER_GENERAL_LABELS - Standard NER (CoNLL-style)")
        print("=" * 80)
        print(f"Description: {NER_GENERAL_LABELS.description}")

        general_labels = set()
        for label in NER_GENERAL_LABELS.label2id.keys():
            if label != "O" and "-" in label:
                general_labels.add(label.split("-", 1)[1])

        general_descriptions = {
            "PER": "Person names",
            "ORG": "Organizations",
            "LOC": "Locations",
            "MISC": "Miscellaneous (nationalities, languages, etc.)",
            "DATE": "Date expressions",
            "TIME": "Time expressions",
            "EVENT": "Events",
            "PRODUCT": "Products",
        }

        for label in sorted(general_labels):
            desc = general_descriptions.get(label, "(no description)")
            print(f"  {label:15} - {desc}")

        print("\n" + "=" * 80)
        print("TEMPORAL_LABELS - Temporal expression extraction")
        print("=" * 80)
        print(f"Description: {TEMPORAL_LABELS.description}")

        temporal_labels = set()
        for label in TEMPORAL_LABELS.label2id.keys():
            if label != "O" and "-" in label:
                temporal_labels.add(label.split("-", 1)[1])

        temporal_descriptions = {
            "DATE_ABS": "Absolute dates (e.g., 'January 15, 2024')",
            "DATE_REL": "Relative dates (e.g., 'yesterday', 'next week')",
            "TIME": "Time expressions (e.g., '3pm', 'noon')",
            "DURATION": "Durations (e.g., '2 hours', 'all day')",
            "FREQUENCY": "Frequencies (e.g., 'every day', 'weekly')",
            "AGE": "Ages (e.g., '5 years old', 'toddler')",
        }

        for label in sorted(temporal_labels):
            desc = temporal_descriptions.get(label, "(no description)")
            print(f"  {label:15} - {desc}")

    except Exception as e:
        print(f"ERROR loading label schemas: {e}")


def main():
    """Run NER comparison tests."""

    # First, print label schemas
    print_label_schemas()

    # Test sentences covering ALL 10 ner_family labels
    test_sentences = [
        # === KINSHIP (family relationship terms) ===
        "Mom and Dad took Emma to the doctor yesterday",
        "Grandma is visiting us next weekend",
        "Had dinner with my wife Sarah and the kids",
        "My brother helped me move furniture",
        "Auntie made her famous cookies",
        "My husband picked up groceries",
        # === PERSON (named individuals) ===
        "Met with John from Microsoft about the project",
        "Our team lead Sarah approved the authentication changes",
        "Emma learned Spanish at school today",
        "Called my friend Maria about the party",
        # === PET (family pets) ===
        "Had a great conversation with Fur the cat",
        "Took Buddy the dog for a walk",
        "Fed the fish this morning",
        "Max the golden retriever ate my homework",
        # === HOME_LOC (family-related locations) ===
        "Visited Golden Gate Bridge in San Francisco with Mike",
        "Traveled to Paris, France last summer",
        "We cleaned grandma's house yesterday",
        "Stopped by home to grab my keys",
        "Picked up kids from school",
        # === TRADITION (family traditions) ===
        "Went to Italian restaurant downtown",
        "Made Christmas cookies with the kids",
        "Had our Sunday family dinner",
        "Lit the menorah for Hanukkah",
        "Watched fireworks on the Fourth of July",
        # === MILESTONE (life milestones) ===
        "Emma's graduation ceremony was beautiful",
        "Baby took her first steps today",
        "Got my driver's license finally",
        "Celebrated our 10th wedding anniversary",
        "Son got accepted to college",
        # === FAMILY_EVENT (family occasions) ===
        "Attended cousin's birthday party",
        "Planning the family reunion for August",
        "Went to nephew's baptism",
        "Baby shower for my sister",
        "Thanksgiving dinner was amazing",
        # === NICKNAME (family nicknames) ===
        "Picked up kiddo from soccer practice",
        "Sweetie made me breakfast in bed",
        "Little one had a nightmare",
        "Honey called to say she'll be late",
        "Bubba helped with the yard work",
        # === ROUTINE (daily family routines) ===
        "Put the kids to bed at 8pm",
        "Morning routine went smoothly today",
        "Breakfast time was chaotic",
        "Did the school drop-off this morning",
        "Evening prayers with the family",
        # === HEIRLOOM (family keepsakes) ===
        "Wore grandma's ring to the wedding",
        "Found dad's old watch in the attic",
        "Passed down the family Bible to my son",
        "Mom's china set is beautiful",
        "Using great-grandpa's pocket knife",
        # === EDGE CASES (technical/work content - should NOT trigger ner_family) ===
        "Fixed the authentication bug in the login module",
        "Deployed the new API to production servers",
        "Updated the machine learning model weights",
        "Attended a meeting at Google HQ with the engineering team",
        "The fur coat was expensive",
        "Drove to the gym at 6am",
    ]

    print("\n" + "#" * 80)
    print("# NER OUTPUT COMPARISON TEST")
    print("# Testing", len(test_sentences), "sentences")
    print("#" * 80)

    # Run BERT-NER tests
    bert_results = test_bert_ner(test_sentences)

    # Run UltraBERT tests
    ultrabert_results = test_ultrabert_ner(test_sentences)

    # Run Entity Extractor (hybrid mode)
    extractor_results = test_entity_extractor(test_sentences)

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    print("\nBERT-NER Label Distribution:")
    bert_labels: dict[str, int] = {}
    for sentence, entities in bert_results.items():
        for e in entities:
            label = e.get("label", "UNKNOWN")
            bert_labels[label] = bert_labels.get(label, 0) + 1
    for label, count in sorted(bert_labels.items()):
        print(f"  {label}: {count}")

    print("\nUltraBERT ner_family Label Distribution:")
    ner_family_labels: dict[str, int] = {}
    ner_family_texts: dict[str, list[str]] = {}  # Track examples
    for sentence, heads in ultrabert_results.items():
        for e in heads.get("ner_family", []):
            label = e.get("label", "UNKNOWN") if isinstance(e, dict) else "UNKNOWN"
            text = e.get("text", "?") if isinstance(e, dict) else str(e)
            ner_family_labels[label] = ner_family_labels.get(label, 0) + 1
            if label not in ner_family_texts:
                ner_family_texts[label] = []
            if len(ner_family_texts[label]) < 5:  # Keep up to 5 examples
                ner_family_texts[label].append(text)

    print("\n  Label           Count   Examples")
    print("  " + "-" * 60)
    for label, count in sorted(ner_family_labels.items(), key=lambda x: -x[1]):
        examples = ", ".join(ner_family_texts.get(label, [])[:3])
        print(f"  {label:15} {count:5}   {examples}")

    print("\nEntity Extractor KG Type Distribution:")
    kg_types: dict[str, int] = {}
    for sentence, entities in extractor_results.items():
        for e in entities:
            kg_type = e.get("kg_type", "UNKNOWN")
            kg_types[kg_type] = kg_types.get(kg_type, 0) + 1
    for kg_type, count in sorted(kg_types.items()):
        print(f"  {kg_type}: {count}")

    # Identify ner_family hallucinations
    print("\n" + "-" * 80)
    print("NER_FAMILY LABEL ANALYSIS BY CATEGORY:")
    print("-" * 80)

    # Define expected labels for each sentence category
    label_analysis: dict[str, dict[str, list[str]]] = {
        "KINSHIP": {"expected": [], "actual": []},
        "PERSON": {"expected": [], "actual": []},
        "PET": {"expected": [], "actual": []},
        "HOME_LOC": {"expected": [], "actual": []},
        "TRADITION": {"expected": [], "actual": []},
        "MILESTONE": {"expected": [], "actual": []},
        "FAMILY_EVENT": {"expected": [], "actual": []},
        "NICKNAME": {"expected": [], "actual": []},
        "ROUTINE": {"expected": [], "actual": []},
        "HEIRLOOM": {"expected": [], "actual": []},
    }

    # Collect all entities by label
    for sentence, heads in ultrabert_results.items():
        for e in heads.get("ner_family", []):
            if isinstance(e, dict):
                label = e.get("label", "UNKNOWN")
                text = e.get("text", "?")
                if label in label_analysis:
                    label_analysis[label]["actual"].append(f"'{text}'")

    print("\n  Per-Label Quality Assessment:")
    print("  " + "-" * 70)

    for label in [
        "KINSHIP",
        "PERSON",
        "PET",
        "HOME_LOC",
        "TRADITION",
        "MILESTONE",
        "FAMILY_EVENT",
        "NICKNAME",
        "ROUTINE",
        "HEIRLOOM",
    ]:
        entities = label_analysis[label]["actual"]
        count = len(entities)
        if count > 0:
            examples = ", ".join(entities[:8])
            if len(entities) > 8:
                examples += f" (+{len(entities)-8} more)"
            print(f"\n  {label} ({count} entities):")
            print(f"    Extracted: {examples}")
        else:
            print(f"\n  {label} (0 entities):")
            print("    [!] No entities extracted for this label!")

    print("\n" + "-" * 80)
    print("NER_FAMILY HALLUCINATIONS (non-family words tagged with family labels):")
    print("-" * 80)

    # Words that should NOT be tagged by ner_family
    non_family_words = {
        "authentication",
        "api",
        "python",
        "machine",
        "learning",
        "production",
        "fixed",
        "deployed",
        "updated",
        "met",
        "from",
        "about",
        "our",
        "approved",
        "changes",
        "new",
        "learned",
        "the",
        "a",
        "and",
        "to",
        "is",
        "was",
        "with",
    }

    for sentence, heads in ultrabert_results.items():
        for e in heads.get("ner_family", []):
            if isinstance(e, dict):
                text_lower = e.get("text", "").lower().strip()
                label = e.get("label", "")
                if text_lower in non_family_words:
                    print(f"  [!]  '{e['text']}' -> {label} in: \"{sentence[:50]}...\"")

    # Identify BERT-NER potential misclassifications
    print("\n" + "-" * 80)
    print("BERT-NER POTENTIAL ISSUES (PER label on non-person entities):")
    print("-" * 80)

    suspicious_words = {
        "italian",
        "british",
        "german",
        "spanish",
        "french",
        "chinese",
        "japanese",
        "authentication",
        "api",
        "python",
        "machine",
        "learning",
        "production",
        "gym",
        "restaurant",
        "bridge",
        "museum",
        "school",
        "fur",
        "coat",
    }

    issues_found = False
    for sentence, entities in bert_results.items():
        for e in entities:
            text_lower = e.get("text", "").lower()
            label = e.get("label", "")
            if label == "PER" and text_lower in suspicious_words:
                print(f"  [!]  '{e['text']}' tagged as PER in: \"{sentence[:50]}...\"")
                issues_found = True

    if not issues_found:
        print("  [OK] No suspicious PER tags found!")

    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
