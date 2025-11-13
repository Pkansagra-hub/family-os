"""
Tier-0 Realtime Classifier Implementation

Lexicon-based affect classification with <2ms P95 latency.

Reference: ADR-0012b (Tier-0 Realtime Classifier)
"""

from typing import Dict, List, Optional, Tuple

from .lexicon import AffectLexicon


class Tier0Classifier:
    """
    Tier-0 lexicon-based affect classifier.

    Performance: <2ms P95 latency

    Usage:
        classifier = Tier0Classifier()
        valence, arousal, tags, confidence = classifier.classify(
            text="I'm feeling stressed",
            behavior={"typing_speed": 150}
        )
    """

    def __init__(self, lexicon_path: Optional[str] = None):
        """
        Initialize Tier-0 classifier.

        Args:
            lexicon_path: Optional path to custom lexicon
        """
        # Load lexicon
        self.lexicon = AffectLexicon("anew_extended")

        # Negation words
        self.negations = {"not", "no", "never", "neither", "nobody", "nothing", "none"}

        # Intensity modifiers
        self.intensifiers = {"very", "extremely", "really", "absolutely"}
        self.diminishers = {"slightly", "somewhat", "barely", "hardly"}

    def classify(
        self, text: str, behavior: Optional[Dict] = None
    ) -> Tuple[float, float, List[str], float]:
        """
        Classify text affect.

        Args:
            text: Input text
            behavior: Optional behavioral signals (typing_speed, pause_duration)

        Returns:
            (valence, arousal, tags, confidence)
        """
        # 1. Tokenize and normalize
        import re

        text_lower = text.lower()
        words = re.findall(r"\b\w+\b", text_lower)

        if not words:
            # Empty text → neutral affect
            return 0.0, 0.0, ["neutral", "low_arousal"], 0.0

        # 2. Look up words in lexicon with negation/modifier handling
        valence_scores = []
        arousal_scores = []
        matched_words = 0

        i = 0
        while i < len(words):
            word = words[i]

            # Check if current word is a negation
            is_negated = False
            if i > 0 and words[i - 1] in self.negations:
                is_negated = True

            # Check if current word is an intensifier/diminisher
            modifier = 1.0
            if i > 0:
                if words[i - 1] in self.intensifiers:
                    modifier = 1.3
                elif words[i - 1] in self.diminishers:
                    modifier = 0.7

            # 3. Look up word in lexicon and handle negations/intensity modifiers
            va_scores = self.lexicon.get_valence_arousal(word)
            if va_scores:
                valence, arousal = va_scores

                # Apply negation (flip valence)
                if is_negated:
                    valence = -valence

                # Apply intensity modifier
                valence *= modifier
                arousal *= modifier

                # Clamp values
                valence = max(-1.0, min(1.0, valence))
                arousal = max(0.0, min(1.0, arousal))

                valence_scores.append(valence)
                arousal_scores.append(arousal)
                matched_words += 1

            i += 1

        # 4. Aggregate valence/arousal
        if valence_scores:
            avg_valence = sum(valence_scores) / len(valence_scores)
            avg_arousal = sum(arousal_scores) / len(arousal_scores)
        else:
            # No lexicon matches → neutral
            avg_valence = 0.0
            avg_arousal = 0.0

        # 5. Add behavioral arousal
        if behavior:
            typing_speed = behavior.get("typing_speed", 0)
            pause_duration = behavior.get("pause_duration", 0)

            # Fast typing → high arousal
            if typing_speed > 200:
                avg_arousal = min(1.0, avg_arousal + 0.2)
            elif typing_speed > 150:
                avg_arousal = min(1.0, avg_arousal + 0.1)

            # Long pauses → lower arousal
            if pause_duration > 5.0:
                avg_arousal = max(0.0, avg_arousal - 0.1)

        # Check for exclamation marks (high arousal indicator)
        exclamation_count = text.count("!")
        if exclamation_count > 0:
            avg_arousal = min(1.0, avg_arousal + (exclamation_count * 0.1))

        # 6. Generate tags
        tags = []

        # Valence tags
        if avg_valence > 0.3:
            tags.append("positive")
        elif avg_valence < -0.3:
            tags.append("negative")
        else:
            tags.append("neutral")

        # Arousal tags
        if avg_arousal > 0.6:
            tags.append("high_arousal")
        elif avg_arousal > 0.3:
            tags.append("medium_arousal")
        else:
            tags.append("low_arousal")

        # Specific emotion tags based on quadrants
        if avg_valence > 0.5 and avg_arousal > 0.6:
            tags.append("excited")
        elif avg_valence > 0.5 and avg_arousal < 0.3:
            tags.append("calm")
        elif avg_valence < -0.5 and avg_arousal > 0.6:
            tags.append("angry")
        elif avg_valence < -0.5 and avg_arousal < 0.3:
            tags.append("sad")

        # Compute confidence based on lexicon match rate
        confidence = min(1.0, matched_words / max(1, len(words)))

        return avg_valence, avg_arousal, tags, confidence
