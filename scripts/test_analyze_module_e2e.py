#!/usr/bin/env python3
"""
End-to-end test of analyze.py module with real text inputs.
Tests the psychologically-grounded valence/arousal calculation from emotions.
"""

import os
import sys

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from k0.modules.affect.analyze import ultrabert_classify


def test_real_texts():
    """Test analyze.py with real-world text inputs."""

    test_cases = [
        # Mixed emotions - should show complexity adjustment
        "Looking back, today was a mixed bag. The K0 bug was frustrating, but I am glad I fixed it.",

        # Positive family emotions
        "Watched a movie with Panda. It was a nice way to unwind after a busy day.",

        # Negative work emotions
        "Spent the first hour addressing the failed tests in my K1 branch. Annoying.",

        # Pure positive emotions
        "Feeling grateful for my family today. They always support me.",

        # High arousal negative
        "Really anxious about the presentation tomorrow. What if I mess up?",

        # Neutral/calm
        "Read a book before bed. Trying to wind down.",

        # Frustration
        "Got stuck on a tricky part of the K1 feature. Spent a couple of hours debugging it.",

        # Mixed caring/frustration
        "Panda called, and we talked about our day. She is feeling overwhelmed with her projects.",
    ]

    print("Testing analyze.py module end-to-end with real text inputs:")
    print("=" * 80)

    for i, text in enumerate(test_cases, 1):
        print(f"\nTest {i}: {text[:60]}{'...' if len(text) > 60 else ''}")

        result = ultrabert_classify(text)

        if result is None:
            print("  ERROR: ultrabert_classify returned None!")
            continue

        print(".3f")
        print(".3f")
        print(f"  Model Version: {result.model_version}")
        print(f"  Emotions: {result.dominant_emotions}")
        print(f"  Band: {result.affect_band}")
        print(f"  Confidence: {result.confidence:.3f}")

if __name__ == "__main__":
    test_real_texts()    test_real_texts()
