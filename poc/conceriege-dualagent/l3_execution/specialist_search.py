"""
Specialist Search Tool - TF-IDF + Cosine Similarity (Battle-tested IR algorithm)
Prevents token bloat: LLM sees 10 results, not 300 specialists
Research: Salton & McGill (1983), Okapi BM25 variant
"""

import json
import logging
import math
import os
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class SpecialistSearchEngine:
    """
    TF-IDF + Cosine Similarity search engine
    Research: Salton & McGill (1983) - Information Retrieval

    Two-stage specialist selection:
    1. LLM searches: "search_specialists(query='health related')" → 10 results (ranked by relevance)
    2. Server picks: max() by score (deterministic)
    """

    def __init__(self):
        self.specialists: List[Dict[str, Any]] = []
        self.documents: List[str] = []  # Document vectors for TF-IDF
        self.idf_cache: Dict[str, float] = {}  # IDF scores
        self._load_specialists()
        self._build_tfidf_index()

    def _load_specialists(self):
        """Load all specialists from config (cached locally)"""
        # Try multiple path locations
        possible_paths = [
            os.path.join(os.path.dirname(__file__), "../../config/specialists.json"),
            os.path.join(os.path.dirname(__file__), "../config/specialists.json"),
            "config/specialists.json",
        ]

        config_path = None
        for path in possible_paths:
            if os.path.exists(path):
                config_path = path
                break

        if config_path:
            try:
                with open(config_path, "r") as f:
                    config = json.load(f)
                    self.specialists = config.get("specialists", [])
                    logger.info(
                        f"[SpecialistSearch] Loaded {len(self.specialists)} specialists from {config_path}"
                    )
            except Exception as e:
                logger.error(f"[SpecialistSearch] Error loading specialists: {e}")
                self.specialists = []
        else:
            logger.warning(f"[SpecialistSearch] No specialists.json found. Tried: {possible_paths}")
            self.specialists = []

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text: lowercase, split on whitespace and punctuation"""
        text = text.lower()
        # Split on punctuation and whitespace
        tokens = []
        current_token = ""
        for char in text:
            if char.isalnum() or char == "_":
                current_token += char
            else:
                if current_token:
                    tokens.append(current_token)
                    current_token = ""
        if current_token:
            tokens.append(current_token)
        return [t for t in tokens if len(t) > 1]  # Skip single chars

    def _build_tfidf_index(self):
        """Build TF-IDF index from specialist domains"""
        if not self.specialists:
            return

        # Step 1: Tokenize all specialist documents
        all_tokens = set()
        doc_tokens = []

        for spec in self.specialists:
            domain = spec.get("domain", "")
            tokens = self._tokenize(domain)
            doc_tokens.append(tokens)
            all_tokens.update(tokens)

        # Step 2: Calculate IDF (inverse document frequency)
        num_docs = len(self.specialists)
        for token in all_tokens:
            # Count how many documents contain this token
            doc_count = sum(1 for tokens in doc_tokens if token in tokens)
            # IDF = log(N / n_t) where N = total docs, n_t = docs with token
            if doc_count > 0:
                self.idf_cache[token] = math.log(num_docs / doc_count)
            else:
                self.idf_cache[token] = 0.0

    def _cosine_similarity(self, query_tokens: List[str], doc_tokens: List[str]) -> float:
        """Calculate cosine similarity between query and document"""
        if not query_tokens or not doc_tokens:
            return 0.0

        # Calculate TF for query
        query_tf = {}
        for token in query_tokens:
            query_tf[token] = query_tf.get(token, 0) + 1

        # Calculate TF for document
        doc_tf = {}
        for token in doc_tokens:
            doc_tf[token] = doc_tf.get(token, 0) + 1

        # Calculate dot product of TF-IDF vectors
        dot_product = 0.0
        for token in query_tf:
            if token in doc_tf:
                query_tfidf = query_tf[token] * self.idf_cache.get(token, 0.0)
                doc_tfidf = doc_tf[token] * self.idf_cache.get(token, 0.0)
                dot_product += query_tfidf * doc_tfidf

        # Calculate magnitudes
        query_magnitude = (
            sum((query_tf[token] * self.idf_cache.get(token, 0.0)) ** 2 for token in query_tf)
        ) ** 0.5
        doc_magnitude = (
            sum((doc_tf[token] * self.idf_cache.get(token, 0.0)) ** 2 for token in doc_tf)
        ) ** 0.5

        if query_magnitude == 0.0 or doc_magnitude == 0.0:
            return 0.0

        return dot_product / (query_magnitude * doc_magnitude)

    def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        """
        Search for specialists using TF-IDF + Cosine Similarity + semantic fallback

        Args:
            query: User's search query
            limit: Max results to return

        Returns:
            List of specialist dicts sorted by relevance (match_score 0.0-1.0)
        """
        if not query or not self.specialists:
            return []

        # Tokenize query
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        # Semantic synonyms for fallback matching
        query_semantics = {
            "stressed": ["stress", "mental", "anxiety"],
            "anxious": ["anxiety", "stress", "mental", "therapy"],
            "feeling": [],  # Stop word
            "anxieties": ["anxiety"],
            "trouble": [],  # Stop word
            "sleeping": ["sleep", "insomnia", "rest"],
            "exhausted": ["sleep", "rest", "energy"],
            "tired": ["sleep", "rest", "energy"],
            "weight": ["fitness", "exercise", "training"],
            "lose": ["fitness", "weight", "exercise"],
            "improve": ["fitness", "health"],
            "fitness": ["exercise", "training"],
        }

        results = []

        # Score each specialist using cosine similarity
        for specialist in self.specialists:
            domain = specialist.get("domain", "")
            doc_tokens = self._tokenize(domain)

            # Calculate TF-IDF cosine similarity
            score = self._cosine_similarity(query_tokens, doc_tokens)

            # Fallback: semantic keyword matching if TF-IDF score is low
            if score < 0.3:
                domain_lower = domain.lower()
                for query_token in query_tokens:
                    if query_token in query_semantics:
                        for semantic_match in query_semantics[query_token]:
                            if semantic_match in domain_lower:
                                score = max(score, 0.6)
                                break

            # ID exact match boost
            spec_id = specialist.get("id", "").lower()
            if any(token == spec_id or token in spec_id for token in query_tokens):
                score = max(score, 0.9)

            if score > 0.0:
                results.append(
                    {
                        "id": specialist.get("id"),
                        "name": specialist.get("name"),
                        "domain": specialist.get("domain"),
                        "priority": specialist.get("priority", "medium"),
                        "match_score": round(score, 2),
                    }
                )

        # Sort by score (descending) then by priority
        results.sort(key=lambda x: (x["match_score"], x["priority"] == "high"), reverse=True)

        top_results = results[:limit]

        logger.info(
            f"[SpecialistSearch TF-IDF] Query='{query}' → {len(top_results)} results "
            f"(top: {top_results[0]['id'] if top_results else 'none'} @ {top_results[0]['match_score'] if top_results else 0})"
        )

        return top_results

    def validate_specialist(self, specialist_id: str) -> bool:
        """Validate if specialist exists"""
        for spec in self.specialists:
            if spec.get("id") == specialist_id:
                return True
        return False

    def get_specialist_info(self, specialist_id: str) -> Dict[str, str]:
        """Get full specialist info"""
        for spec in self.specialists:
            if spec.get("id") == specialist_id:
                return {
                    "id": spec.get("id"),
                    "name": spec.get("name"),
                    "domain": spec.get("domain"),
                    "priority": spec.get("priority", "medium"),
                }
        return {}


# Global instance (singleton)
_search_engine: SpecialistSearchEngine = None


def get_specialist_search_engine() -> SpecialistSearchEngine:
    """Get or create specialist search engine"""
    global _search_engine
    if _search_engine is None:
        _search_engine = SpecialistSearchEngine()
    return _search_engine
