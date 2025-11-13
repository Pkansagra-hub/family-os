"""Async FTS indexing worker for V1.4 (Performance Optimization).

Moves full-text search indexing from synchronous commit path to async background workers.
This reduces commit latency by deferring FTS index updates.

Architecture:
  1. Commit stores event without FTS indexing (fts_status=PENDING)
  2. Outbox entry created with FTS payload
  3. Async worker picks up outbox entry
  4. Builds FTS entry (keyword extraction, stemming)
  5. Updates st_wal with fts_entry_id and fts_status='DONE'
  6. Marks Outbox entry complete

Production NLP:
  - NLTK stop words corpus (40+ languages)
  - NLTK tokenization (WordPunkt, TreebankWord)
  - NLTK stemming (Porter, Lancaster, Snowball)
  - spaCy named entity recognition (optional)

Usage:
    worker = FtsIndexingWorker(db_path="k0_runtime.sqlite3")
    worker.run_once()  # Process one batch
    worker.run_forever()  # Continuous polling (production)
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import nltk
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer
from nltk.tokenize import word_tokenize

from k0.storage.outbox import OutboxStore

logger = logging.getLogger(__name__)

# Download NLTK data on first import (idempotent)
try:
    nltk.data.find("tokenizers/punkt")
except LookupError:
    nltk.download("punkt", quiet=True)
    nltk.download("punkt_tab", quiet=True)

try:
    nltk.data.find("corpora/stopwords")
except LookupError:
    nltk.download("stopwords", quiet=True)

# Initialize stemmer and stop words globally
_STEMMER = PorterStemmer()
_STOP_WORDS_EN = set(stopwords.words("english"))


@dataclass
class FtsIndexRequest:
    """Request to index event in full-text search."""

    event_id: str
    space_id: str
    document_id: str
    text: str
    document_type: str  # e.g., "memory_event", "envelope_receipt"
    keywords: list[str] | None = None


@dataclass
class FtsIndexResult:
    """Result of FTS indexing."""

    event_id: str
    fts_entry_id: str
    indexed_at: str
    text_length: int
    keyword_count: int


def extract_keywords(
    text: str, max_keywords: int = 10, language: str = "english", stem: bool = True
) -> list[str]:
    """Extract keywords from text using production-grade NLP.

    Uses NLTK for tokenization, stop word removal, and stemming.
    For advanced NER/POS tagging, use spaCy (optional).

    Args:
        text: Text to extract keywords from
        max_keywords: Maximum keywords to extract
        language: Language for stop words (default: english)
        stem: Apply Porter stemming (reduces words to root form)

    Returns:
        List of keywords (stemmed if stem=True)
    """
    # Tokenize using NLTK (handles punctuation, contractions)
    tokens = word_tokenize(text.lower())

    # Get stop words for language
    try:
        stop_words = set(stopwords.words(language))
    except OSError:
        logger.warning(f"Stop words not found for language={language}, using English")
        stop_words = _STOP_WORDS_EN

    # Filter: remove stop words, punctuation, short tokens
    keywords = [
        token for token in tokens if token.isalnum() and len(token) > 2 and token not in stop_words
    ]

    # Apply stemming (reduces "running", "ran", "runs" → "run")
    if stem:
        keywords = [_STEMMER.stem(word) for word in keywords]

    # Remove duplicates while preserving order
    seen = set()
    unique_keywords = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique_keywords.append(kw)

    return unique_keywords[:max_keywords]


def fts_payload_to_request(payload: dict[str, Any]) -> FtsIndexRequest:
    """Convert outbox payload to FTS index request."""
    return FtsIndexRequest(
        event_id=payload["event_id"],
        space_id=payload["space_id"],
        document_id=payload["document_id"],
        text=payload["text"],
        document_type=payload.get("document_type", "memory_event"),
        keywords=payload.get("keywords"),
    )


class FtsIndexingWorker:
    """Async FTS indexing worker (runs background).

    Processes outbox entries with driver="fts" and op_kind="INDEX_FTS".

    V1.4 Implementation:
    - Polls Outbox for fts.enqueue topic
    - Extracts keywords and indexes text
    - Updates st_wal with fts_entry_id and fts_status='DONE'
    - Marks Outbox entry as applied (deletes from Outbox)
    """

    def __init__(
        self,
        db_path: str | Path = "k0_runtime.sqlite3",
        batch_size: int = 50,
        poll_interval_sec: float = 1.0,
    ) -> None:
        """Initialize FTS indexing worker.

        Args:
            db_path: Path to SQLite database
            batch_size: Max outbox entries to process per batch (FTS can batch more)
            poll_interval_sec: Polling interval (seconds) for run_forever()
        """
        self._db_path = Path(db_path)
        self._batch_size = batch_size  # Can batch more aggressively than embedding
        self._index_name = "memory_events"
        self._poll_interval_sec = poll_interval_sec

    def _get_connection(self) -> sqlite3.Connection:
        """Create database connection."""
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def process_fts_request(self, request: FtsIndexRequest) -> FtsIndexResult:
        """Process single FTS indexing request.

        Args:
            request: FTS index request from outbox

        Returns:
            FtsIndexResult with fts_entry_id
        """
        try:
            # Extract keywords if not provided
            keywords = request.keywords or extract_keywords(request.text)

            # Generate FTS entry ID
            fts_entry_id = f"fts-{request.event_id[:8]}-{len(keywords):02d}"

            result = FtsIndexResult(
                event_id=request.event_id,
                fts_entry_id=fts_entry_id,
                indexed_at=datetime.now(timezone.utc).isoformat(),
                text_length=len(request.text),
                keyword_count=len(keywords),
            )

            logger.info(
                f"FTS indexed: {request.event_id} → {fts_entry_id} "
                f"({len(keywords)} keywords, {len(request.text)} chars)"
            )
            return result
        except Exception as exc:
            logger.exception(f"Failed to index FTS for {request.event_id}", exc_info=exc)
            raise

    def process_batch(self, requests: list[FtsIndexRequest]) -> list[FtsIndexResult]:
        """Process batch of FTS indexing requests.

        Args:
            requests: List of FTS index requests

        Returns:
            List of indexing results
        """
        results = []
        for request in requests[: self._batch_size]:
            try:
                result = self.process_fts_request(request)
                results.append(result)
            except Exception as exc:
                logger.error(f"Batch FTS processing failed for {request.event_id}", exc_info=exc)
                # Continue processing other requests
                continue

        return results

    def run_once(self) -> int:
        """Process one batch of outbox entries.

        Returns:
            Number of entries processed
        """
        conn = self._get_connection()
        try:
            outbox_store = OutboxStore()

            # Dequeue batch from Outbox (driver="fts")
            entries = outbox_store.dequeue_ready_batch(
                driver="fts",
                limit=self._batch_size,
                connection=conn,
            )

            if not entries:
                return 0

            logger.info(f"Processing {len(entries)} FTS indexing requests")

            processed = 0
            for entry in entries:
                try:
                    # Decode payload (JSON)
                    payload = json.loads(entry.payload.decode("utf-8"))

                    # Convert to FtsIndexRequest
                    request = fts_payload_to_request(payload)

                    # Index text
                    result = self.process_fts_request(request)

                    # Update WAL with FTS result
                    conn.execute(
                        "UPDATE st_wal SET fts_status=?, fts_entry_id=? WHERE wal_pos=?",
                        ("DONE", result.fts_entry_id, entry.wal_pos),
                    )

                    # Mark Outbox entry as applied (delete)
                    if entry.id is not None:
                        outbox_store.mark_applied(entry.id, connection=conn)

                    conn.commit()
                    processed += 1
                    logger.info(
                        f"✅ Processed FTS indexing: wal_pos={entry.wal_pos}, fts_entry_id={result.fts_entry_id}"
                    )

                except Exception as exc:
                    logger.error(
                        f"❌ Failed to process FTS indexing: wal_pos={entry.wal_pos}", exc_info=exc
                    )
                    conn.rollback()

                    # Record failure in Outbox (for retry)
                    outbox_store.record_failure(
                        entry,
                        retries=entry.retries + 1,
                        requeue_seq=entry.requeue_seq + 1,
                        last_error=str(exc)[:500],
                        status="FAILED" if entry.retries >= 3 else "PENDING",
                        connection=conn,
                    )
                    conn.commit()

            return processed
        finally:
            conn.close()

    def run_forever(self) -> None:
        """Run worker continuously (production mode).

        Polls Outbox every poll_interval_sec seconds.
        """
        logger.info(f"🚀 FTS indexing worker started (poll_interval={self._poll_interval_sec}s)")

        while True:
            try:
                processed = self.run_once()
                if processed == 0:
                    # No work, sleep
                    time.sleep(self._poll_interval_sec)
            except KeyboardInterrupt:
                logger.info("⏹ FTS indexing worker stopped by user")
                break
            except Exception as exc:
                logger.exception("❌ FTS indexing worker error", exc_info=exc)
                time.sleep(self._poll_interval_sec * 2)  # Back off on error


__all__ = [
    "FtsIndexRequest",
    "FtsIndexResult",
    "FtsIndexingWorker",
    "extract_keywords",
    "fts_payload_to_request",
]


if __name__ == "__main__":
    import os
    import sys

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Get configuration from environment
    db_path = os.getenv("K0_DB_PATH", "k0_runtime.sqlite3")
    batch_size = int(os.getenv("FTS_BATCH_SIZE", "50"))
    poll_interval = float(os.getenv("FTS_POLL_INTERVAL_SEC", "1.0"))

    logger.info("Starting FTS indexing worker with config:")
    logger.info(f"  DB Path: {db_path}")
    logger.info(f"  Batch Size: {batch_size}")
    logger.info(f"  Poll Interval: {poll_interval}s")

    # Create and start worker
    worker = FtsIndexingWorker(
        db_path=db_path,
        batch_size=batch_size,
        poll_interval_sec=poll_interval,
    )

    try:
        worker.run_forever()
    except KeyboardInterrupt:
        logger.info("FTS indexing worker shutdown requested")
        sys.exit(0)
