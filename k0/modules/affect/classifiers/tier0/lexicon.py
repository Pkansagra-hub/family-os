"""
Affect Lexicon Module

Provides standardized affect lexicons for valence/arousal classification.
Based on established psychological research and affective norms.

Supported Lexicons:
- ANEW (Affective Norms for English Words) - Bradley & Lang (1999)
- VAD (Valence-Arousal-Dominance) - Warriner et al. (2013)
- Custom domain-specific extensions

Reference: ADR-0012b (Tier-0 Realtime Classifier)
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class AffectLexicon:
    """
    Standardized affect lexicon with valence/arousal scores.

    Format: word → (valence, arousal, dominance)
    - valence: [-1, 1] (negative to positive)
    - arousal: [0, 1] (calm to excited)
    - dominance: [0, 1] (submissive to dominant)

    Based on ANEW and VAD research datasets.
    """

    def __init__(self, lexicon_name: str = "anew_extended"):
        """
        Initialize lexicon.

        Args:
            lexicon_name: Name of lexicon to load ('anew', 'vad', 'anew_extended')
        """
        self.name = lexicon_name
        self.lexicon: Dict[str, Tuple[float, float, float]] = {}
        self._metadata: Optional[Dict] = None
        self._load_lexicon(lexicon_name)

    def _load_lexicon(self, name: str) -> None:
        """Load specified lexicon."""
        if name == "anew_extended":
            self._load_anew_extended()
        elif name == "anew":
            self._load_anew()
        elif name == "vad":
            self._load_vad()
        else:
            raise ValueError(f"Unknown lexicon: {name}")

    def _load_anew_extended(self) -> None:
        """
        Load extended ANEW lexicon from external JSON file.

        Based on:
        - ANEW (Bradley & Lang, 1999) - 1,034 words
        - Extended with VAD norms (Warriner et al., 2013)
        - Domain-specific additions for modern contexts

        Loads from: k0/modules/affect/resources/lexicons/affect_lexicon_v1.json
        """
        # Get path to lexicon file
        module_dir = Path(__file__).parent.parent.parent  # k0/modules/affect/
        lexicon_path = module_dir / "resources" / "lexicons" / "affect_lexicon_v1.json"

        try:
            with open(lexicon_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Validate structure
            if "_metadata" not in data or "lexicon" not in data:
                raise ValueError("Invalid lexicon file structure")

            # Load lexicon data
            for word, scores in data["lexicon"].items():
                if len(scores) != 3:
                    raise ValueError(f"Invalid scores for word '{word}': expected 3 values")
                self.lexicon[word] = tuple(scores)

            # Store metadata for introspection
            self._metadata = data["_metadata"]

        except FileNotFoundError:
            raise FileNotFoundError(f"Lexicon file not found: {lexicon_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in lexicon file: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to load lexicon: {e}")

    def _load_anew(self) -> None:
        """Load original ANEW lexicon (~1,034 words)."""
        # Simplified version - in production, load from data file
        self._load_anew_extended()  # Fallback to extended

    def _load_vad(self) -> None:
        """Load VAD norms (~13,000 words)."""
        # Simplified version - in production, load from data file
        self._load_anew_extended()  # Fallback to extended

    def get_word(self, word: str) -> Optional[Tuple[float, float, float]]:
        """
        Get valence, arousal, dominance for a word.

        Returns:
            (valence, arousal, dominance) or None if not found
        """
        return self.lexicon.get(word.lower())

    def get_valence_arousal(self, word: str) -> Optional[Tuple[float, float]]:
        """
        Get valence and arousal only (for backward compatibility).

        Returns:
            (valence, arousal) or None if not found
        """
        full = self.get_word(word)
        return (full[0], full[1]) if full else None

    def contains(self, word: str) -> bool:
        """Check if word is in lexicon."""
        return word.lower() in self.lexicon

    def size(self) -> int:
        """Get number of words in lexicon."""
        return len(self.lexicon)

    def get_words_by_arousal_range(self, min_arousal: float, max_arousal: float) -> List[str]:
        """Get words within arousal range."""
        return [word for word, (_, a, _) in self.lexicon.items() if min_arousal <= a <= max_arousal]

    def get_metadata(self) -> Optional[Dict]:
        """Get lexicon metadata if available."""
        return self._metadata

    def get_info(self) -> Dict:
        """Get lexicon information."""
        info = {
            "name": self.name,
            "word_count": self.size(),
            "scales": {
                "valence": {"range": [-1.0, 1.0], "neutral": 0.0},
                "arousal": {"range": [0.0, 1.0], "neutral": 0.5},
                "dominance": {"range": [0.0, 1.0], "neutral": 0.5},
            },
        }
        if self._metadata:
            info["metadata"] = self._metadata
        return info

    def get_words_by_valence_range(self, min_val: float, max_val: float) -> List[str]:
        """Get words within valence range."""
        return [word for word, (v, _, _) in self.lexicon.items() if min_val <= v <= max_val]

    def get_words_by_arousal_range(self, min_arousal: float, max_arousal: float) -> List[str]:
        """Get words within arousal range."""
        return [word for word, (_, a, _) in self.lexicon.items() if min_arousal <= a <= max_arousal]


def load_lexicon(name: str = "anew_extended") -> AffectLexicon:
    """
    Load a named affect lexicon.

    Args:
        name: Lexicon name ('anew', 'vad', 'anew_extended')

    Returns:
        Loaded AffectLexicon instance
    """
    return AffectLexicon(name)


# Default lexicon instance
DEFAULT_LEXICON = AffectLexicon("anew_extended")
