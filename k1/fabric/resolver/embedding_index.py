"""EmbeddingIndex — semantic capability search via MiniLM / SPLADE.

Zero external services.  The model runs locally.  At init we embed every
capability's searchable text (description + action_name + connector_label)
into a dense vector.  At query time we embed the action text and return
the top-K capabilities by cosine similarity.

Supports:
  - all-MiniLM-L6-v2 (22 MB, 384-dim) — smallest production-grade model
  - SPLADE-v3 (~80 MB, 768-dim) — sparse neural retrieval with term expansion
  - Reciprocal Rank Fusion (RRF) for BM25 + embedding hybrid search

Design authority: ``docs/whiteboard/capability_search_algorithm.md`` §K11.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ── Lazy imports (heavy) ──
_SentenceTransformer: Any = None
_torch: Any = None
_Autotokenizer: Any = None
_Automodel: Any = None


def _get_sentence_transformer():
    global _SentenceTransformer
    if _SentenceTransformer is None:
        from sentence_transformers import SentenceTransformer as _ST

        _SentenceTransformer = _ST
    return _SentenceTransformer


class EmbeddingIndex:
    """Semantic search over capability descriptions.

    Usage::

        index = EmbeddingIndex.for_capabilities(capability_records, model_name="all-MiniLM-L6-v2")
        results = index.search("add eggs to shopping list", top_k=10)
        # → [(capability_name, score), ...]
    """

    def __init__(
        self,
        capability_texts: list[str],
        capability_names: list[str],
        embeddings: np.ndarray,
        model_name: str = "all-MiniLM-L6-v2",
    ) -> None:
        self._texts = capability_texts
        self._names = capability_names
        self._embeddings = embeddings  # (N, dim)
        self._model_name = model_name
        self._dim = embeddings.shape[1]
        # Normalize for cosine similarity
        self._norms = np.linalg.norm(self._embeddings, axis=1, keepdims=True)
        self._norms[self._norms == 0] = 1.0  # avoid div-by-zero
        self._normalized = self._embeddings / self._norms
        # ── Cache the model so we don't reload on every search() call ──
        self._model: Any = None

    def _get_model(self) -> Any:
        """Return the cached model, loading it once."""
        if self._model is None:
            ST = _get_sentence_transformer()
            self._model = ST(self._model_name)
        return self._model

    @classmethod
    def for_capabilities(
        cls,
        capabilities: list[Any],
        *,
        model_name: str = "all-MiniLM-L6-v2",
    ) -> "EmbeddingIndex":
        """Build an index from capability records.

        Each capability's searchable text is::

            {action_name} {description} {connector_label}
        """
        ST = _get_sentence_transformer()
        logger.info("EmbeddingIndex: loading model %s ...", model_name)
        model = ST(model_name)
        logger.info(
            "EmbeddingIndex: model loaded. dim=%d", model.get_sentence_embedding_dimension()
        )

        texts: list[str] = []
        names: list[str] = []
        for cap in capabilities:
            # Build rich searchable text per capability
            parts = [
                getattr(cap, "action_name", "") or "",
                getattr(cap, "description", "") or "",
            ]
            # Add connector label if available (derived from connector_id)
            connector_id = getattr(cap, "connector_id", "") or ""
            if connector_id:
                # "family.shopping" → "shopping"
                parts.append(connector_id.split(".")[-1] if "." in connector_id else connector_id)
            text = " ".join(p for p in parts if p).strip()
            if not text:
                text = getattr(cap, "capability_name", "") or ""
            texts.append(text)
            names.append(getattr(cap, "capability_name", "") or "")

        logger.info("EmbeddingIndex: encoding %d capability texts ...", len(texts))
        embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        logger.info("EmbeddingIndex: ready. %d vectors, dim=%d", len(names), embeddings.shape[1])
        return cls(texts, names, embeddings, model_name=model_name)

    def search(
        self,
        query: str,
        top_k: int = 10,
    ) -> list[tuple[str, float]]:
        """Return top-K (capability_name, similarity_score) for *query*."""
        if not query.strip():
            return []
        model = self._get_model()
        query_vec = model.encode([query], convert_to_numpy=True, show_progress_bar=False)
        # Normalize query
        q_norm = np.linalg.norm(query_vec)
        if q_norm > 0:
            query_vec = query_vec / q_norm
        # Cosine similarity = dot product of normalized vectors
        scores = np.dot(self._normalized, query_vec.T).flatten()
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [(self._names[i], float(scores[i])) for i in top_indices if scores[i] > 0]

    def search_with_connectors(
        self,
        query: str,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Return top-K results with connector grouping.

        Each result::

            {
                "capability_name": str,
                "score": float,
                "connector_id": str,
            }
        """
        raw = self.search(query, top_k=top_k)
        # connector_id is derivable from capability_name prefix
        results: list[dict[str, Any]] = []
        for name, score in raw:
            # "tool.read.calendar.list_events" → connector = "family.calendar"
            # Actually, we need the real connector_id from the GPS.
            # For now, derive it from the capability_name pattern:
            # "tool.{mode}.{connector_short}.{action}" → "family.{connector_short}"
            parts = name.split(".")
            connector_short = parts[2] if len(parts) >= 4 else ""
            connector_id = f"family.{connector_short}" if connector_short else ""
            results.append(
                {
                    "capability_name": name,
                    "score": score,
                    "connector_id": connector_id,
                }
            )
        return results


# ── SPLADE Index ──────────────────────────────────────────────────────


class SpladeIndex:
    """SPLADE-v3 sparse neural retrieval index.

    SPLADE learns term expansions: "pencil in" → {schedule:0.8, create:0.7,
    appointment:0.6, calendar:0.5, ...}.  It produces sparse vectors where
    most dimensions are near-zero.  Cosine similarity on these sparse vectors
    combines the precision of lexical matching with the recall of semantic
    understanding.

    Uses transformers AutoModel + max-pooling + log(1+ReLU(x)) activation —
    the canonical SPLADE encoding.  NOT sentence-transformers (which uses
    mean pooling and loses sparsity).

    Model: naver/splade-v3 (~80 MB download, 768-dim output).
    Requires HF_TOKEN env var for gated model access.
    """

    def __init__(
        self,
        capability_texts: list[str],
        capability_names: list[str],
        embeddings: np.ndarray,
    ) -> None:
        self._texts = capability_texts
        self._names = capability_names
        self._embeddings = embeddings  # (N, 768)
        self._dim = embeddings.shape[1]
        # Normalize for cosine similarity
        self._norms = np.linalg.norm(self._embeddings, axis=1, keepdims=True)
        self._norms[self._norms == 0] = 1.0
        self._normalized = self._embeddings / self._norms
        # ── Cached model ──
        self._model: Any = None
        self._tokenizer: Any = None

    def _load_model(self) -> tuple[Any, Any]:
        """Load SPLADE model + tokenizer once."""
        global _torch, _Autotokenizer, _Automodel
        if _torch is None:
            import torch as _torch
        if _Autotokenizer is None:
            from transformers import AutoTokenizer as _Autotokenizer
        if _Automodel is None:
            from transformers import AutoModel as _Automodel

        hf_token = os.environ.get("HF_TOKEN", "")
        self._tokenizer = _Autotokenizer.from_pretrained(
            "naver/splade-v3",
            token=hf_token or None,
        )
        self._model = _Automodel.from_pretrained(
            "naver/splade-v3",
            token=hf_token or None,
        )
        self._model.eval()
        return self._model, self._tokenizer

    @classmethod
    def for_capabilities(
        cls,
        capabilities: list[Any],
    ) -> "SpladeIndex":
        """Build a SPLADE index from capability records."""
        global _torch
        if _torch is None:
            import torch as _torch

        logger.info("SpladeIndex: loading naver/splade-v3 ...")
        idx = cls.__new__(cls)
        model, tokenizer = idx._load_model()
        logger.info("SpladeIndex: model loaded. dim=768")

        texts: list[str] = []
        names: list[str] = []
        for cap in capabilities:
            parts = [
                getattr(cap, "action_name", "") or "",
                getattr(cap, "description", "") or "",
            ]
            connector_id = getattr(cap, "connector_id", "") or ""
            if connector_id:
                parts.append(connector_id.split(".")[-1] if "." in connector_id else connector_id)
            text = " ".join(p for p in parts if p).strip()
            if not text:
                text = getattr(cap, "capability_name", "") or ""
            texts.append(text)
            names.append(getattr(cap, "capability_name", "") or "")

        logger.info("SpladeIndex: encoding %d capability texts ...", len(texts))
        all_embeddings = []
        batch_size = 32
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            with _torch.no_grad():
                tokens = tokenizer(batch, padding=True, truncation=True, return_tensors="pt")
                outputs = model(**tokens)
                attention_mask = tokens["attention_mask"].unsqueeze(-1)
                token_emb = outputs.last_hidden_state
                # SPLADE activation: log(1 + ReLU(x)) then max-pool over tokens
                activated = _torch.log(1 + _torch.relu(token_emb))
                activated = activated * attention_mask
                sparse_vec = activated.max(dim=1).values
                all_embeddings.append(sparse_vec.numpy())

        embeddings = np.concatenate(all_embeddings, axis=0)
        logger.info("SpladeIndex: ready. %d vectors, dim=%d", len(names), embeddings.shape[1])
        return cls(texts, names, embeddings)

    def search(
        self,
        query: str,
        top_k: int = 10,
    ) -> list[tuple[str, float]]:
        """Return top-K (capability_name, similarity_score) for *query*."""
        if not query.strip():
            return []
        global _torch
        if _torch is None:
            import torch as _torch

        if self._model is None:
            self._load_model()

        with _torch.no_grad():
            tokens = self._tokenizer([query], padding=True, truncation=True, return_tensors="pt")
            outputs = self._model(**tokens)
            attention_mask = tokens["attention_mask"].unsqueeze(-1)
            token_emb = outputs.last_hidden_state
            activated = _torch.log(1 + _torch.relu(token_emb))
            activated = activated * attention_mask
            query_vec = activated.max(dim=1).values.numpy()

        # Normalize query
        q_norm = np.linalg.norm(query_vec)
        if q_norm > 0:
            query_vec = query_vec / q_norm
        # Cosine similarity
        scores = np.dot(self._normalized, query_vec.T).flatten()
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [(self._names[i], float(scores[i])) for i in top_indices if scores[i] > 0]


# ── Reciprocal Rank Fusion ───────────────────────────────────────────


def reciprocal_rank_fusion(
    bm25_results: list[tuple[str, float]],
    embedding_results: list[tuple[str, float]],
    k: int = 60,
    graph_weight: float = 3.0,
) -> list[tuple[str, float]]:
    """Merge BM25 and embedding ranked lists via RRF.

    RRF score = Σ w_i/(k + rank_i) for each result list the item appears in.
    Higher RRF score = better consensus between BM25 and embeddings.

    Args:
        bm25_results: [(capability_name, bm25_score), ...] ranked by BM25/graph
        embedding_results: [(capability_name, embedding_score), ...] ranked by embedding
        k: RRF constant (default 60, standard from literature)
        graph_weight: multiplier for graph/BM25 rank contribution (default 3.0).
                      Graph results are 3x more influential than embedding results.
                      Set to 1.0 for equal weight, 0.0 to ignore graph entirely.

    Returns:
        [(capability_name, rrf_score), ...] sorted by RRF score descending
    """
    rrf: dict[str, float] = {}
    for rank, (name, _) in enumerate(bm25_results):
        rrf[name] = rrf.get(name, 0.0) + graph_weight / (k + rank + 1)
    for rank, (name, _) in enumerate(embedding_results):
        rrf[name] = rrf.get(name, 0.0) + 1.0 / (k + rank + 1)
    sorted_items = sorted(rrf.items(), key=lambda x: x[1], reverse=True)
    return sorted_items
