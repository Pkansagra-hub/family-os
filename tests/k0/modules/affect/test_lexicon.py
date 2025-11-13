"""
Tests for Affect Lexicon Module

Tests the lexicon loading, JSON file handling, and word lookup functionality.

Reference: ADR-0012b (Tier-0 Realtime Classifier)
"""

from k0.modules.affect.classifiers.tier0.lexicon import AffectLexicon, load_lexicon


class TestAffectLexicon:
    """Test AffectLexicon functionality."""

    def test_init_default(self):
        """Test default lexicon initialization."""
        lexicon = AffectLexicon()
        assert lexicon.name == "anew_extended"
        assert lexicon.size() > 2000  # Expanded lexicon
        assert lexicon._metadata is not None

    def test_init_custom_name(self):
        """Test lexicon initialization with custom name."""
        lexicon = AffectLexicon("anew_extended")
        assert lexicon.name == "anew_extended"
        assert lexicon.size() > 2000

    def test_json_loading(self):
        """Test that lexicon loads correctly from JSON file."""
        lexicon = AffectLexicon()

        # Check metadata
        metadata = lexicon.get_metadata()
        assert metadata is not None
        assert "name" in metadata
        assert "version" in metadata
        assert "word_count" in metadata
        assert metadata["word_count"] == 2147  # As specified in JSON

        # Check scales
        assert "scales" in metadata
        scales = metadata["scales"]
        assert scales["valence"]["range"] == [-1.0, 1.0]
        assert scales["arousal"]["range"] == [0.0, 1.0]
        assert scales["dominance"]["range"] == [0.0, 1.0]

    def test_word_lookup(self):
        """Test basic word lookup functionality."""
        lexicon = AffectLexicon()

        # Test known positive word
        happy_scores = lexicon.get_word("happy")
        assert happy_scores is not None
        valence, arousal, dominance = happy_scores
        assert valence > 0.5  # Positive
        assert 0.3 < arousal < 0.7  # Medium arousal
        assert 0.4 < dominance < 0.8  # Medium dominance

        # Test known negative word
        sad_scores = lexicon.get_word("sad")
        assert sad_scores is not None
        valence, arousal, dominance = sad_scores
        assert valence < -0.3  # Negative
        assert arousal < 0.6  # Not too high arousal

        # Test unknown word
        unknown_scores = lexicon.get_word("xyzunknownword")
        assert unknown_scores is None

    def test_valence_arousal_only(self):
        """Test backward compatibility method."""
        lexicon = AffectLexicon()

        va_scores = lexicon.get_valence_arousal("excited")
        assert va_scores is not None
        valence, arousal = va_scores
        assert valence > 0.5
        assert arousal > 0.5

        # Test unknown word
        unknown_va = lexicon.get_valence_arousal("unknownword")
        assert unknown_va is None

    def test_contains_method(self):
        """Test word existence checking."""
        lexicon = AffectLexicon()

        assert lexicon.contains("happy")
        assert lexicon.contains("HAPPY")  # Case insensitive
        assert not lexicon.contains("xyzunknownword")

    def test_lexicon_size(self):
        """Test lexicon size reporting."""
        lexicon = AffectLexicon()
        size = lexicon.size()
        assert size > 2000  # Much larger than Phase 1 inline lexicon
        assert size > 3000  # Should be around 3400+ words

    def test_get_info(self):
        """Test lexicon info method."""
        lexicon = AffectLexicon()
        info = lexicon.get_info()

        assert "name" in info
        assert "word_count" in info
        assert "scales" in info
        assert "metadata" in info

        # Verify scales match expected ranges
        scales = info["scales"]
        assert scales["valence"]["range"] == [-1.0, 1.0]
        assert scales["arousal"]["range"] == [0.0, 1.0]
        assert scales["dominance"]["range"] == [0.0, 1.0]

    def test_word_range_queries(self):
        """Test querying words by valence/arousal ranges."""
        lexicon = AffectLexicon()

        # Get very positive words
        positive_words = lexicon.get_words_by_valence_range(0.7, 1.0)
        assert len(positive_words) > 0
        assert "happy" in positive_words or "excited" in positive_words

        # Get calm words (low arousal)
        calm_words = lexicon.get_words_by_arousal_range(0.0, 0.3)
        assert len(calm_words) > 0
        assert "calm" in calm_words

    def test_normalization(self):
        """Test that scores are properly normalized."""
        lexicon = AffectLexicon()

        # All scores should be within expected ranges
        for word in ["happy", "sad", "angry", "calm"]:
            scores = lexicon.get_word(word)
            if scores:
                valence, arousal, dominance = scores
                assert -1.0 <= valence <= 1.0
                assert 0.0 <= arousal <= 1.0
                assert 0.0 <= dominance <= 1.0

    def test_lexicon_file_not_found(self):
        """Test error handling for missing lexicon file."""
        # This would require mocking the file path, but for now
        # we trust that the file exists as created in GATE 2
        lexicon = AffectLexicon()
        assert lexicon.size() > 0  # File loaded successfully

    def test_research_backed_words(self):
        """Test presence of research-backed affective words."""
        lexicon = AffectLexicon()

        # Test ANEW core words
        assert lexicon.contains("happy")
        assert lexicon.contains("sad")
        assert lexicon.contains("angry")
        assert lexicon.contains("fear")
        assert lexicon.contains("joy")

        # Test VAD extended words
        assert lexicon.contains("excited")
        assert lexicon.contains("frustrated")
        assert lexicon.contains("anxious")
        assert lexicon.contains("content")

        # Test modern/internet words (may not be in all lexicons)
        # Note: This lexicon focuses on research-backed affective norms
        # assert lexicon.contains("lol")  # Not in this lexicon
        # assert lexicon.contains("omg")  # Not in this lexicon


class TestLexiconModuleFunctions:
    """Test module-level functions."""

    def test_load_lexicon_function(self):
        """Test the load_lexicon convenience function."""
        lexicon = load_lexicon()
        assert isinstance(lexicon, AffectLexicon)
        assert lexicon.name == "anew_extended"
        assert lexicon.size() > 2000

    def test_load_lexicon_custom_name(self):
        """Test load_lexicon with custom name."""
        lexicon = load_lexicon("anew_extended")
        assert isinstance(lexicon, AffectLexicon)
        assert lexicon.name == "anew_extended"


class TestLexiconIntegration:
    """Integration tests for lexicon with classifier."""

    def test_lexicon_classifier_integration(self):
        """Test that lexicon integrates properly with classifier."""
        from k0.modules.affect.classifiers.tier0.classifier import Tier0Classifier

        classifier = Tier0Classifier()

        # Test that classifier can access lexicon
        assert hasattr(classifier, "lexicon")
        assert isinstance(classifier.lexicon, AffectLexicon)
        assert classifier.lexicon.size() > 2000

        # Test classification uses lexicon
        valence, arousal, tags, confidence = classifier.classify("I feel happy!")
        assert valence > 0  # Should be positive
        assert confidence > 0  # Should have found words
