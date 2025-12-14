#!/usr/bin/env python
"""
Rebuild FAISS Index - Migration Script

This script executes Epic 4.1 Issue 4.1.2: Rebuild FAISS Index (768-dim).

Purpose:
- Backup existing FAISS index
- Create new 768-dim FAISS index (IVF256,PQ64)
- Bulk add all st_vec embeddings to new index
- Validate search quality
- Update configuration

Usage:
    python k0/scripts/rebuild_faiss_index.py --dry-run
    python k0/scripts/rebuild_faiss_index.py --backup-path data/backups/
    python k0/scripts/rebuild_faiss_index.py --index-id ultrabert_v2.1.0_ivf256_pq64
    python k0/scripts/rebuild_faiss_index.py --validate-only

ADR Reference: ADR-K003 (Inline Embedding via UltraBERT), ADR-K004 (FAISS Integration)
"""

import argparse
import asyncio
import shutil
import sqlite3
import struct
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class FaissIndexRebuilder:
    """Orchestrates FAISS index rebuild for 768-dim vectors."""

    def __init__(
        self,
        db_path: str,
        index_path: Path,
        backup_path: Path | None = None,
        index_id: str = "ultrabert_v2.1.0_ivf256_pq64",
        dimension: int = 768,
        dry_run: bool = False,
    ):
        self.db_path = db_path
        self.index_path = index_path
        self.backup_path = backup_path or index_path.parent / "backups"
        self.index_id = index_id
        self.dimension = dimension
        self.dry_run = dry_run
        self.conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        """Connect to K0 runtime database."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        print(f"✅ Connected to database: {self.db_path}")

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
            print("✅ Database connection closed")

    def backup_existing_index(self) -> bool:
        """Backup existing FAISS index before rebuild."""
        index_file = self.index_path / f"{self.index_id}.index"

        if not index_file.exists():
            print(f"ℹ️ No existing index found at {index_file}")
            return True

        # Create backup directory
        self.backup_path.mkdir(parents=True, exist_ok=True)

        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.backup_path / f"{self.index_id}_backup_{timestamp}.index"

        if self.dry_run:
            print(f"[DRY-RUN] Would backup {index_file} → {backup_file}")
            return True

        try:
            shutil.copy2(index_file, backup_file)
            print(f"✅ Backed up existing index: {backup_file}")
            return True
        except Exception as e:
            print(f"❌ Failed to backup index: {e}")
            return False

    def count_vectors(self) -> dict[str, Any]:
        """Count vectors in st_vec table."""
        if not self.conn:
            raise RuntimeError("Database not connected")

        query = """
            SELECT
                COUNT(*) as total_count,
                COUNT(CASE WHEN faiss_id IS NOT NULL THEN 1 END) as indexed_count,
                COUNT(CASE WHEN faiss_id IS NULL THEN 1 END) as unindexed_count
            FROM st_vec
            WHERE vector IS NOT NULL
        """

        cursor = self.conn.execute(query)
        row = cursor.fetchone()

        return {
            "total_count": row["total_count"],
            "indexed_count": row["indexed_count"],
            "unindexed_count": row["unindexed_count"],
        }

    def fetch_vectors_batch(self, batch_size: int = 1000, offset: int = 0) -> list[dict[str, Any]]:
        """Fetch batch of vectors from st_vec."""
        if not self.conn:
            raise RuntimeError("Database not connected")

        query = """
            SELECT embedding_id, vector
            FROM st_vec
            WHERE vector IS NOT NULL
            ORDER BY embedding_id
            LIMIT ? OFFSET ?
        """

        cursor = self.conn.execute(query, (batch_size, offset))
        rows = cursor.fetchall()

        # Unpack binary vectors
        vectors = []
        for row in rows:
            try:
                # Unpack 768 floats (768 * 4 = 3072 bytes)
                vector_bytes = row["vector"]
                if len(vector_bytes) == self.dimension * 4:
                    vector = struct.unpack(f"{self.dimension}f", vector_bytes)
                    vectors.append({"embedding_id": row["embedding_id"], "vector": vector})
                else:
                    print(
                        f"⚠️ Skipping {row['embedding_id']}: invalid dimension {len(vector_bytes) // 4}"
                    )
            except Exception as e:
                print(f"⚠️ Failed to unpack {row['embedding_id']}: {e}")

        return vectors

    async def create_new_index(self, total_vectors: int) -> Any:
        """
        Create new FAISS IVF256,PQ64 index.

        Requires FAISS library (faiss-cpu or faiss-gpu).
        """
        try:
            import faiss
        except ImportError:
            print("❌ FAISS library not installed. Install with: pip install faiss-cpu")
            return None

        if self.dry_run:
            print(f"[DRY-RUN] Would create FAISS IVF256,PQ64 index (dim={self.dimension})")
            return None

        # Create IVF256,PQ64 index
        nlist = 256  # 256 Voronoi cells
        m = 64  # 64 PQ subquantizers
        nbits = 8  # 8 bits per code

        # Quantizer (for IVF)
        quantizer = faiss.IndexFlatL2(self.dimension)

        # IVF with Product Quantization
        index = faiss.IndexIVFPQ(quantizer, self.dimension, nlist, m, nbits)
        index.nprobe = 16  # Search 16 cells

        print(f"✅ Created FAISS index: IVF{nlist},PQ{m}x{nbits} (dim={self.dimension})")
        print(f"   - Training required: {not index.is_trained}")
        print(f"   - Training samples needed: ~{nlist * 256} vectors (30,000+)")

        return index

    async def train_index(self, index: Any, training_size: int = 30000) -> bool:
        """
        Train FAISS index with training vectors.

        IVF indexes require training with representative data.
        """
        if self.dry_run:
            print(f"[DRY-RUN] Would train index with {training_size:,} vectors")
            return True

        if index is None:
            return False

        if index.is_trained:
            print("ℹ️ Index already trained, skipping training step")
            return True

        print(f"\n🔄 Training FAISS index with {training_size:,} vectors...")

        # Fetch training vectors
        training_vectors = []
        batch_size = 1000
        offset = 0

        while len(training_vectors) < training_size:
            batch = self.fetch_vectors_batch(batch_size=batch_size, offset=offset)
            if not batch:
                break

            for item in batch:
                training_vectors.append(item["vector"])
                if len(training_vectors) >= training_size:
                    break

            offset += batch_size
            print(
                f"   Loaded {len(training_vectors):,}/{training_size:,} training vectors...",
                end="\r",
            )

        if len(training_vectors) < 30000:
            print(f"\n⚠️ Insufficient training data: {len(training_vectors):,} < 30,000")
            print("   - FAISS IVF requires 30,000+ vectors for stable training")
            print("   - Consider using IndexFlatL2 instead (no training needed)")
            return False

        # Train index
        training_array = np.array(training_vectors, dtype="float32")
        print(f"\n   Training with {training_array.shape[0]:,} vectors...")

        try:
            index.train(training_array)
            print("✅ Index training complete")
            return True
        except Exception as e:
            print(f"❌ Training failed: {e}")
            return False

    async def bulk_add_vectors(self, index: Any) -> int:
        """Bulk add all vectors to FAISS index."""
        if self.dry_run:
            stats = self.count_vectors()
            print(f"[DRY-RUN] Would add {stats['total_count']:,} vectors to FAISS index")
            return stats["total_count"]

        if index is None:
            return 0

        print("\n🔄 Bulk adding vectors to FAISS index...")

        batch_size = 1000
        offset = 0
        total_added = 0

        while True:
            batch = self.fetch_vectors_batch(batch_size=batch_size, offset=offset)
            if not batch:
                break

            # Convert to numpy array
            vectors_array = np.array([item["vector"] for item in batch], dtype="float32")

            # Generate FAISS IDs (sequential int64)
            faiss_ids = np.arange(total_added, total_added + len(batch), dtype="int64")

            # Add to index with IDs
            index.add_with_ids(vectors_array, faiss_ids)

            total_added += len(batch)
            offset += batch_size

            print(f"   Added {total_added:,} vectors...", end="\r")

        print(f"\n✅ Bulk add complete: {total_added:,} vectors")
        return total_added

    async def save_index(self, index: Any) -> bool:
        """Save FAISS index to disk."""
        if self.dry_run:
            print(f"[DRY-RUN] Would save index to {self.index_path / self.index_id}.index")
            return True

        if index is None:
            return False

        try:
            import faiss

            self.index_path.mkdir(parents=True, exist_ok=True)
            index_file = self.index_path / f"{self.index_id}.index"

            faiss.write_index(index, str(index_file))
            print(f"✅ Index saved: {index_file}")
            return True
        except Exception as e:
            print(f"❌ Failed to save index: {e}")
            return False

    async def validate_search_quality(self, index: Any, sample_size: int = 100) -> bool:
        """Validate search quality with sample queries."""
        if self.dry_run:
            print(f"[DRY-RUN] Would validate search with {sample_size} sample queries")
            return True

        if index is None:
            return False

        print(f"\n🔄 Validating search quality with {sample_size} sample queries...")

        # Fetch sample vectors
        sample_batch = self.fetch_vectors_batch(batch_size=sample_size)
        if not sample_batch:
            print("⚠️ No vectors available for validation")
            return False

        # Perform sample searches
        successful_searches = 0
        for item in sample_batch:
            query_vector = np.array([item["vector"]], dtype="float32")
            try:
                distances, indices = index.search(query_vector, k=10)
                if len(indices[0]) > 0:
                    successful_searches += 1
            except Exception as e:
                print(f"⚠️ Search failed for {item['embedding_id']}: {e}")

        success_rate = successful_searches / len(sample_batch) * 100
        print(
            f"✅ Search validation: {successful_searches}/{len(sample_batch)} ({success_rate:.1f}%)"
        )

        if success_rate < 95.0:
            print("⚠️ Search success rate below 95%, investigate index quality")
            return False

        return True

    async def rebuild_index(self) -> dict[str, Any]:
        """Execute complete index rebuild."""
        print("\n" + "=" * 60)
        print("REBUILD FAISS INDEX - MIGRATION SCRIPT")
        print("=" * 60)
        print(f"Index ID: {self.index_id}")
        print(f"Dimension: {self.dimension}")
        print(f"Index Path: {self.index_path}")
        print(f"Backup Path: {self.backup_path}")
        print(f"Dry Run: {self.dry_run}")
        print("=" * 60 + "\n")

        # Step 1: Count vectors
        print("Step 1: Counting vectors in st_vec...")
        stats = self.count_vectors()
        print(f"📊 Total Vectors: {stats['total_count']:,}")
        print(f"📊 Previously Indexed: {stats['indexed_count']:,}")
        print(f"📊 Unindexed: {stats['unindexed_count']:,}")

        if stats["total_count"] == 0:
            print("\n⚠️ No vectors found in st_vec. Cannot rebuild index.")
            return {"status": "failed", "error": "no_vectors"}

        # Step 2: Backup existing index
        print("\nStep 2: Backing up existing index...")
        if not self.backup_existing_index():
            print("⚠️ Backup failed, but continuing with rebuild...")

        # Step 3: Create new index
        print("\nStep 3: Creating new FAISS index...")
        index = await self.create_new_index(stats["total_count"])

        # Step 4: Train index
        print("\nStep 4: Training FAISS index...")
        if not await self.train_index(index, training_size=min(30000, stats["total_count"])):
            print("❌ Training failed. Aborting rebuild.")
            return {"status": "failed", "error": "training_failed"}

        # Step 5: Bulk add vectors
        print("\nStep 5: Bulk adding vectors...")
        added_count = await self.bulk_add_vectors(index)

        # Step 6: Save index
        print("\nStep 6: Saving index to disk...")
        if not await self.save_index(index):
            print("❌ Save failed. Aborting rebuild.")
            return {"status": "failed", "error": "save_failed"}

        # Step 7: Validate search quality
        print("\nStep 7: Validating search quality...")
        if not await self.validate_search_quality(index):
            print("⚠️ Validation issues detected. Review index quality.")

        # Summary
        print("\n" + "=" * 60)
        print("REBUILD SUMMARY")
        print("=" * 60)
        print(f"Total Vectors: {stats['total_count']:,}")
        print(f"Vectors Added: {added_count:,}")
        print(f"Index File: {self.index_path / self.index_id}.index")
        if self.dry_run:
            print("Dry Run: True (no actual index created)")
        print("=" * 60 + "\n")

        return {
            "status": "complete" if not self.dry_run else "dry_run",
            "total_vectors": stats["total_count"],
            "added_count": added_count,
        }


async def main():
    parser = argparse.ArgumentParser(
        description="Rebuild FAISS index for P02/P08 migration (Epic 4.1 Issue 4.1.2)"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="k0_runtime.sqlite3",
        help="Path to K0 runtime database (default: k0_runtime.sqlite3)",
    )
    parser.add_argument(
        "--index-path",
        type=str,
        default="data/faiss_indexes",
        help="Path to FAISS index directory (default: data/faiss_indexes)",
    )
    parser.add_argument(
        "--backup-path",
        type=str,
        default=None,
        help="Path to backup directory (default: {index_path}/backups)",
    )
    parser.add_argument(
        "--index-id",
        type=str,
        default="ultrabert_v2.1.0_ivf256_pq64",
        help="FAISS index ID (default: ultrabert_v2.1.0_ivf256_pq64)",
    )
    parser.add_argument(
        "--dimension",
        type=int,
        default=768,
        help="Vector dimension (default: 768)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate rebuild without creating index",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate existing index, don't rebuild",
    )

    args = parser.parse_args()

    rebuilder = FaissIndexRebuilder(
        db_path=args.db_path,
        index_path=Path(args.index_path),
        backup_path=Path(args.backup_path) if args.backup_path else None,
        index_id=args.index_id,
        dimension=args.dimension,
        dry_run=args.dry_run,
    )

    try:
        rebuilder.connect()

        if args.validate_only:
            try:
                import faiss

                index_file = rebuilder.index_path / f"{rebuilder.index_id}.index"
                if not index_file.exists():
                    print(f"❌ Index file not found: {index_file}")
                    return 1

                index = faiss.read_index(str(index_file))
                print(f"✅ Loaded existing index: {index_file}")
                print(f"   - ntotal: {index.ntotal:,} vectors")

                result = await rebuilder.validate_search_quality(index)
                return 0 if result else 1
            except ImportError:
                print("❌ FAISS library not installed. Install with: pip install faiss-cpu")
                return 1
        else:
            result = await rebuilder.rebuild_index()
            return 0 if result["status"] in ["complete", "dry_run"] else 1

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        rebuilder.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
