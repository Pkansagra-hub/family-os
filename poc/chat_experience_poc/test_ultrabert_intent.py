"""Test UltraBERT-based intent classification directly."""

import sys

sys.path.insert(0, ".")

from k0.runtime.ultrabert_adapter import classify_activity, is_ultrabert_available


def map_ultrabert_to_intent(ultrabert_intent: str, ingress_category: str) -> tuple:
    """Map UltraBERT outputs to POC intent types."""
    ingress_to_specialist = {
        "HEALTH": "healthcare",
        "FINANCE": "finance",
        "EDUCATION": "research",
        "FAMILY": "research",
    }
    planning_intents = {"set_reminder", "log_memory", "share_news", "express_emotion"}
    query_intents = {"query_memory", "ask_question"}

    if ingress_category == "META":
        return "meta", None
    if ingress_category == "PLANNING":
        return "planning-intent", ingress_to_specialist.get(ingress_category)
    if ultrabert_intent in planning_intents:
        return "planning-intent", ingress_to_specialist.get(ingress_category)
    if ultrabert_intent in query_intents:
        return "query-intent", ingress_to_specialist.get(ingress_category, "research")
    if ingress_category in ("HEALTH", "FINANCE", "EDUCATION"):
        return "query-intent", ingress_to_specialist.get(ingress_category, "research")
    return "meta", None


def test_intent():
    test_cases = [
        "Plan a dinner at an Italian restaurant nearby tonight",
        "How is my recovery going?",
        "Send a reminder to take my medication at 8pm",
        "Hello, how are you?",
        "What is my financial status?",
        "Remember that I had coffee with Sarah today",
    ]

    print(f"UltraBERT Available: {is_ultrabert_available()}\n")
    print("=== UltraBERT Intent Classification ===\n")

    for text in test_cases:
        result = classify_activity(text)
        if result:
            intent_type, specialist = map_ultrabert_to_intent(
                result.intent, result.ingress_category
            )
            print(f"Input: {text[:45]}...")
            print(f"  UB Intent: {result.intent} -> POC: {intent_type}")
            print(f'  UB Ingress: {result.ingress_category} -> Specialist: {specialist or "N/A"}')
            print(f"  Confidence: {result.intent_confidence:.2f}")
            print()


if __name__ == "__main__":
    test_intent()
if __name__ == "__main__":
    test_intent()
if __name__ == "__main__":
    test_intent()
if __name__ == "__main__":
    test_intent()
