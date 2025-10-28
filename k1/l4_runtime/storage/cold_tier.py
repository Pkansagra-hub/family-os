"""
Cold Tier (L3 Local Filesystem) Storage Implementation

This module implements the cold tier of K1's multi-tier storage architecture,
providing <200ms access to historical SessionState data stored on local filesystem
with zstd compression. This replaces cloud storage (S3/MinIO) with ZERO cloud costs.

Use Cases:
    1. Long-term archival (30-365 days retention)
    2. Historical SessionState access (rare, <1% of queries)
    3. GDPR/privacy compliance (365-day automatic deletion)
    4. Cost optimization (ZERO cloud costs, local-only)

Performance Targets:
    - Get (filesystem read): <200ms P95
    - Put (async write): <100ms P95
    - Decompression: <30ms P95 (zstd level 3)
    - Capacity: Disk-limited (configurable quota, e.g., 500GB)
    - Compression: zstd level 3 (70% size reduction: 50KB → 15KB)
    - Retention: 365 days (automatic cleanup)

Cost Analysis (Local vs Cloud):
    - Local filesystem: $0/month (device storage)
    - AWS S3 Standard: $0.023/GB/month + $0.0004/1000 GET requests
    - MinIO self-hosted: $5-10/month (compute + network)
    - **Cost savings: 100% (ZERO cloud costs)**

Performance Comparison (Local vs S3):
    - Local read: <200ms P95 (2.5× faster than S3's 500ms)
    - Local write: <100ms P95 (1.5× faster than S3's 150ms)
    - No network latency (local-only)
    - No cloud API rate limits

Trade-offs:
    - Slower than warm tier: 200ms vs 50ms (4× slower)
    - Disk-limited capacity (not unlimited like S3)
    - Single-device storage (no multi-region redundancy)
    - Manual backup required (no automatic S3 durability)

Integration:
    - TierManager: Falls back to cold tier on warm miss (<1% of queries)
    - LifecycleManager: Migrates sessions after 30 days (warm → cold)
    - WarmTier: Receives sessions from cold tier on promotion (rare)
    - Background cleanup: Deletes sessions after 365 days (GDPR compliance)

ADR References:
    - ADR-0020: Multi-Tier Storage Architecture
    - ADR-0020c: Cold Tier (L3 Local Filesystem) Design
    - ADR-0014: FlatBuffers serialization (not used for cold tier, JSON preferred)
"""

import time
from pathlib import Path
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger(__name__)


class ColdTier:
    """
    Cold tier: Local filesystem storage with zstd compression and 365-day retention.

    The cold tier provides long-term archival for SessionState data that has aged
    beyond the warm tier's 30-day retention. It uses local filesystem storage with
    zstd compression to minimize disk usage while maintaining fast access compared
    to cloud storage (S3/MinIO).

    Features:
        - <200ms P95 latency (2.5× faster than S3, 4× slower than warm tier)
        - Disk-limited capacity (configurable quota, e.g., 500GB)
        - 365-day retention (automatic deletion for GDPR compliance)
        - zstd compression (70% size reduction: 50KB → 15KB)
        - ZERO cloud costs (local-only, no S3/MinIO)
        - Async operations (non-blocking I/O)
        - JSON format (human-readable, debuggable)

    Filesystem Layout:
        ```
        /var/lib/familyos/cold_tier/
        ├── sessions/                     # Compressed session files
        │   ├── session_001.json.zst
        │   ├── session_002.json.zst
        │   └── session_NNN.json.zst
        ├── sessions.json                 # Metadata (expiration, sizes)
        └── README.md                      # Documentation
        ```

    Metadata Format (sessions.json):
        ```json
        {
          "total_sessions": 1250,
          "total_size_bytes": 19660800,  # 18.75MB compressed
          "sessions": {
            "session_001": {
              "created_at": "2025-10-27T12:30:00Z",
              "expires_at": "2026-10-27T12:30:00Z",
              "size_bytes": 15360,
              "uncompressed_size_bytes": 51200
            }
          }
        }
        ```

    Compression (zstd level 3):
        - Algorithm: zstd level 3 (fast compression/decompression)
        - Ratio: 70% size reduction (50KB → 15KB average)
        - Compress latency: <20ms P95
        - Decompress latency: <30ms P95
        - Better than S3 (30% compression with less control)

    Capacity Management:
        - Configurable quota (default: 500GB)
        - Average session: 15KB compressed (50KB uncompressed)
        - Max sessions: ~33,333 (500GB / 15KB)
        - Quota enforcement: Reject writes if quota exceeded
        - Background cleanup: Free space by deleting expired sessions

    Lifecycle Transitions:
        - Warm → Cold: 30-day archival via LifecycleManager
        - Cold → Deleted: 365-day automatic cleanup (GDPR compliance)
        - Cold → Warm: Manual promotion (rare, for audit/debugging)

    Performance Budget:
        - Get (filesystem): <150ms P95 read + <30ms decompress = <200ms P95
        - Put (filesystem): <50ms P95 write + <20ms compress = <100ms P95
        - Delete: <5ms P95 (file deletion)
        - Cleanup: <1000ms per 1000 sessions (batched)
        - Quota check: <1ms (metadata lookup)

    Cost Comparison (1000 sessions, 30-day lifecycle):
        - Local filesystem: $0/month (device storage)
        - AWS S3 Standard: $0.023/GB × 0.015GB × 1000 = $0.35/month
        - MinIO self-hosted: $5-10/month (compute + network)
        - **Local savings: 100% (ZERO cloud costs)**

    Example Usage:
        ```python
        # Initialize cold tier with local filesystem
        cold_tier = ColdTier(
            storage_path="/var/lib/familyos/cold_tier",
            quota_gb=500,
            retention_days=365,
            compression_level=3,
        )

        # Archive session (from warm tier)
        await cold_tier.put("session_123", session_state)

        # Get session (rare, <1% of queries)
        session_state = await cold_tier.get("session_123")
        if session_state:
            print("Cold hit:", session_state)
        else:
            print("Cold miss (expired or not found)")

        # Background cleanup (365+ days)
        expired_count = await cold_tier.cleanup_expired_sessions()
        print(f"Deleted {expired_count} expired sessions")

        # Get statistics
        stats = await cold_tier.get_stats()
        print(f"Sessions: {stats['total_sessions']}")
        print(f"Compressed: {stats['compressed_size_mb']:.2f} MB")
        print(f"Quota usage: {stats['usage_percent']:.2f}%")
        ```

    WARD Test Examples:
        ```python
        # Test 1: Store and retrieve session (local filesystem)
        @ward.test("cold_tier stores and retrieves session from filesystem")
        async def test_cold_tier_local_storage():
            cold_tier = ColdTier(storage_path="/tmp/cold_tier_test")

            session_state = {"session_id": "s1", "beliefs": {"user": "Alice"}}
            await cold_tier.put("s1", session_state)

            retrieved = await cold_tier.get("s1")
            ward.assert_equal(retrieved["session_id"], "s1")
            ward.assert_equal(retrieved["beliefs"]["user"], "Alice")

        # Test 2: zstd compression (70% size reduction)
        @ward.test("cold_tier compresses sessions with zstd (70% reduction)")
        async def test_cold_tier_compression():
            cold_tier = ColdTier(storage_path="/tmp/cold_tier_test")

            # Create 50KB session
            session_state = {"session_id": "s1", "large_data": "x" * 50000}
            await cold_tier.put("s1", session_state)

            # Check file size
            file_path = Path("/tmp/cold_tier_test/sessions/s1.json.zst")
            compressed_size = file_path.stat().st_size
            ward.assert_less(compressed_size, 50000 * 0.4)  # <40% of original (70% reduction)

        # Test 3: 365-day automatic cleanup
        @ward.test("cold_tier deletes sessions after 365 days")
        async def test_cold_tier_cleanup():
            cold_tier = ColdTier(retention_days=365)

            # Store session 366 days ago
            session_state = {"session_id": "s1", "created_at": (datetime.utcnow() - timedelta(days=366)).isoformat()}
            await cold_tier.put("s1", session_state)

            # Trigger cleanup
            deleted_count = await cold_tier.cleanup_expired_sessions()
            ward.assert_equal(deleted_count, 1)

            # Verify session deleted
            ward.assert_is_none(await cold_tier.get("s1"))

        # Test 4: Quota enforcement
        @ward.test("cold_tier rejects writes when quota exceeded")
        async def test_cold_tier_quota():
            cold_tier = ColdTier(quota_gb=0.001)  # 1MB quota

            # Store sessions until quota exceeded
            session_state = {"session_id": "s1", "large_data": "x" * 500000}  # 500KB
            await cold_tier.put("s1", session_state)  # OK
            await cold_tier.put("s2", session_state)  # OK

            # Third write should fail (quota exceeded)
            with ward.raises(Exception):  # TODO: Define QuotaExceededError
                await cold_tier.put("s3", session_state)
        ```

    TODO List:
        - TODO(@storage-team): Initialize filesystem storage (create directories)
        - TODO(@storage-team): Implement zstd compression (level 3, 70% reduction)
        - TODO(@storage-team): Add metadata tracking (sessions.json)
        - TODO(@storage-team): Implement 365-day cleanup background task
        - TODO(@storage-team): Add Prometheus metrics (get_latency, put_latency, cleanup_total)
        - TODO(@storage-team): Implement quota enforcement (reject writes if exceeded)
        - TODO(@storage-team): Add disk usage tracking (compressed size)
        - TODO(@storage-team): Implement async file I/O (aiofiles)
        - TODO(@storage-team): Add error handling (disk full, permission errors)
        - TODO(@storage-team): Implement metadata persistence (save/load sessions.json)

    ADR References:
        - ADR-0020: Multi-Tier Storage Architecture
        - ADR-0020c: Cold Tier (L3 Local Filesystem) Design
    """

    # Constants
    DEFAULT_STORAGE_PATH = "/var/lib/familyos/cold_tier"
    DEFAULT_QUOTA_GB = 500  # 500GB default quota
    RETENTION_DAYS = 365  # 365-day retention (GDPR compliance)
    COMPRESSION_LEVEL = 3  # zstd level 3 (fast, 70% reduction)
    CLEANUP_INTERVAL_SEC = 86400  # Check every 24 hours
    METADATA_FILE = "sessions.json"

    def __init__(
        self,
        storage_path: str = DEFAULT_STORAGE_PATH,
        quota_gb: int = DEFAULT_QUOTA_GB,
        retention_days: int = RETENTION_DAYS,
        compression_level: int = COMPRESSION_LEVEL,
    ):
        """
        Initialize cold tier.

        Args:
            storage_path: Root path for cold tier storage (default: /var/lib/familyos/cold_tier)
            quota_gb: Disk quota in GB (default: 500GB)
            retention_days: Retention period in days (default: 365 days)
            compression_level: zstd compression level 1-22 (default: 3 for speed)

        Raises:
            OSError: If storage_path cannot be created
            ValueError: If quota_gb <= 0 or retention_days <= 0

        Implementation Notes:
            - Creates storage_path/sessions/ directory if not exists
            - Loads existing metadata from sessions.json if present
            - Initializes Prometheus metrics
            - Starts background cleanup task (every 24 hours)

        ADR: ADR-0020c (Cold Tier)
        """
        # TODO(@storage-team): Initialize cold tier
        # 1. Validate parameters (quota_gb > 0, retention_days > 0)
        # 2. Create storage_path if not exists: Path(storage_path).mkdir(parents=True, exist_ok=True)
        # 3. Create sessions/ subdirectory: Path(storage_path, "sessions").mkdir(exist_ok=True)
        # 4. Load metadata from sessions.json if exists
        # 5. Initialize tracking:
        #    - self.metadata = {"total_sessions": 0, "total_size_bytes": 0, "sessions": {}}
        # 6. Initialize Prometheus metrics:
        #    - cold_tier_get_latency_ms (Histogram)
        #    - cold_tier_put_latency_ms (Histogram)
        #    - cold_tier_delete_total (Counter)
        #    - cold_tier_cleanup_total (Counter)
        #    - cold_tier_disk_usage_bytes (Gauge)
        # 7. Start background cleanup task: asyncio.create_task(self._cleanup_loop())

        self.storage_path = Path(storage_path)
        self.quota_gb = quota_gb
        self.quota_bytes = quota_gb * 1024 * 1024 * 1024  # Convert to bytes
        self.retention_days = retention_days
        self.compression_level = compression_level

        # Metadata tracking
        self.metadata: Dict[str, Any] = {
            "total_sessions": 0,
            "total_size_bytes": 0,
            "sessions": {},
        }

        logger.info(
            "[ColdTier] Initialized cold tier",
            storage_path=str(self.storage_path),
            quota_gb=quota_gb,
            retention_days=retention_days,
            compression_level=compression_level,
        )

    async def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve SessionState from cold tier.

        Args:
            session_id: Session identifier

        Returns:
            SessionState dict or None if not found/expired

        Flow:
            1. Check metadata (exists? expired?)
            2. Read compressed file (sessions/{session_id}.json.zst)
            3. Decompress with zstd
            4. Parse JSON
            5. Return session or None

        Performance:
            - Filesystem read: <150ms P95
            - Decompress (zstd): <30ms P95
            - Parse JSON: <10ms P95
            - Total: <200ms P95

        Metrics:
            - cold_tier_get_latency_ms (Histogram): Total get latency

        ADR: ADR-0020c
        """
        start_ns = time.perf_counter_ns()

        # TODO(@storage-team): Implement async get
        # 1. Check metadata: if session_id not in self.metadata["sessions"]: return None
        # 2. Check expiration:
        #    session_meta = self.metadata["sessions"][session_id]
        #    expires_at = datetime.fromisoformat(session_meta["expires_at"])
        #    if expires_at < datetime.utcnow(): return None
        # 3. Read compressed file:
        #    file_path = self.storage_path / "sessions" / f"{session_id}.json.zst"
        #    async with aiofiles.open(file_path, "rb") as f:
        #        compressed = await f.read()
        # 4. Decompress: decompressed = zstd.decompress(compressed)
        # 5. Parse JSON: session_state = json.loads(decompressed.decode())
        # 6. Emit metrics (cold_tier_get_latency_ms)
        # 7. Return session_state

        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        logger.debug(
            "[ColdTier] Get operation",
            session_id=session_id,
            latency_ms=round(latency_ms, 2),
        )
        return None  # TODO: Replace with actual implementation

    async def put(
        self,
        session_id: str,
        state: Dict[str, Any],
    ) -> None:
        """
        Store SessionState in cold tier.

        Args:
            session_id: Session identifier
            state: SessionState dict

        Raises:
            QuotaExceededError: If total size exceeds quota_gb

        Flow:
            1. Serialize state to JSON
            2. Compress with zstd level 3 (70% reduction)
            3. Check quota (reject if over limit)
            4. Write to {storage_path}/sessions/{session_id}.json.zst
            5. Update metadata (expiration_date, size_bytes)
            6. Save metadata to sessions.json

        Performance:
            - Serialize: <10ms P95
            - Compress: <20ms P95
            - Quota check: <1ms
            - Write: <50ms P95
            - Total: <100ms P95

        Size Benefit:
            - Typical session: 50KB uncompressed
            - Compressed (zstd level 3): 15KB (70% reduction)
            - 1000 sessions: 15MB vs 50MB

        Metrics:
            - cold_tier_put_latency_ms (Histogram): Total put latency
            - cold_tier_disk_usage_bytes (Gauge): Current disk usage

        ADR: ADR-0020c
        """
        start_ns = time.perf_counter_ns()

        # TODO(@storage-team): Implement async put
        # 1. Serialize: serialized = json.dumps(state).encode()
        # 2. Compress: compressed = zstd.compress(serialized, self.compression_level)
        # 3. Check quota:
        #    new_total = self.metadata["total_size_bytes"] + len(compressed)
        #    if new_total > self.quota_bytes:
        #        raise QuotaExceededError(f"Quota exceeded: {new_total / (1024**3):.2f}GB > {self.quota_gb}GB")
        # 4. Write file:
        #    file_path = self.storage_path / "sessions" / f"{session_id}.json.zst"
        #    async with aiofiles.open(file_path, "wb") as f:
        #        await f.write(compressed)
        # 5. Update metadata:
        #    self.metadata["sessions"][session_id] = {
        #        "created_at": datetime.utcnow().isoformat(),
        #        "expires_at": (datetime.utcnow() + timedelta(days=self.retention_days)).isoformat(),
        #        "size_bytes": len(compressed),
        #        "uncompressed_size_bytes": len(serialized)
        #    }
        #    self.metadata["total_sessions"] = len(self.metadata["sessions"])
        #    self.metadata["total_size_bytes"] += len(compressed)
        # 6. Save metadata: await self._save_metadata()
        # 7. Emit metrics (cold_tier_put_latency_ms, cold_tier_disk_usage_bytes.set())

        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        logger.info(
            "[ColdTier] Put operation",
            session_id=session_id,
            latency_ms=round(latency_ms, 2),
        )

    async def delete(self, session_id: str) -> None:
        """
        Delete session from cold tier.

        Args:
            session_id: Session to delete

        Flow:
            1. Delete {storage_path}/sessions/{session_id}.json.zst
            2. Remove from metadata
            3. Update disk usage
            4. Save metadata

        Performance:
            - File deletion: <5ms P95
            - Metadata update: <1ms

        Metrics:
            - cold_tier_delete_total (Counter): Total deletions

        ADR: ADR-0020c
        """
        # TODO(@storage-team): Implement async delete
        # 1. Check if session exists: if session_id not in self.metadata["sessions"]: return
        # 2. Delete file:
        #    file_path = self.storage_path / "sessions" / f"{session_id}.json.zst"
        #    if file_path.exists(): file_path.unlink()
        # 3. Update metadata:
        #    session_meta = self.metadata["sessions"].pop(session_id)
        #    self.metadata["total_sessions"] -= 1
        #    self.metadata["total_size_bytes"] -= session_meta["size_bytes"]
        # 4. Save metadata: await self._save_metadata()
        # 5. Emit metrics (cold_tier_delete_total.inc())

        logger.info("[ColdTier] Delete operation", session_id=session_id)

    async def contains(self, session_id: str) -> bool:
        """
        Check if session exists in cold tier.

        Args:
            session_id: Session to check

        Returns:
            True if session exists and not expired, False otherwise

        Performance:
            - Check: <1ms (metadata lookup)

        ADR: ADR-0020c
        """
        # TODO(@storage-team): Implement async contains
        # 1. Check metadata: if session_id not in self.metadata["sessions"]: return False
        # 2. Check expiration:
        #    session_meta = self.metadata["sessions"][session_id]
        #    expires_at = datetime.fromisoformat(session_meta["expires_at"])
        #    return expires_at >= datetime.utcnow()

        return session_id in self.metadata.get("sessions", {})

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get cold tier statistics.

        Returns:
            Dict with:
                - total_sessions: Count of sessions in cold tier
                - total_size_mb: Estimated uncompressed size
                - compressed_size_mb: Actual disk usage
                - compression_ratio: Compression effectiveness (%)
                - quota_gb: Configured quota
                - usage_percent: Disk usage (%)
                - oldest_session_days: Age of oldest session
                - newest_session_days: Age of newest session
                - expired_sessions: Count ready for cleanup

        Performance:
            - Stats: <10ms (aggregate metadata)

        ADR: ADR-0020c
        """
        # TODO(@storage-team): Implement stats
        # 1. Calculate compressed size: self.metadata["total_size_bytes"] / (1024**2)
        # 2. Calculate uncompressed size: sum([s["uncompressed_size_bytes"] for s in self.metadata["sessions"].values()]) / (1024**2)
        # 3. Calculate compression ratio: (1 - compressed / uncompressed) * 100
        # 4. Calculate usage percent: (compressed / self.quota_bytes) * 100
        # 5. Find oldest/newest sessions:
        #    created_dates = [datetime.fromisoformat(s["created_at"]) for s in self.metadata["sessions"].values()]
        #    oldest_days = (datetime.utcnow() - min(created_dates)).days if created_dates else 0
        #    newest_days = (datetime.utcnow() - max(created_dates)).days if created_dates else 0
        # 6. Count expired sessions:
        #    now = datetime.utcnow()
        #    expired = sum(1 for s in self.metadata["sessions"].values() if datetime.fromisoformat(s["expires_at"]) < now)
        # 7. Return comprehensive dict

        return {
            "total_sessions": self.metadata.get("total_sessions", 0),
            "total_size_mb": 0.0,  # TODO: Calculate uncompressed size
            "compressed_size_mb": self.metadata.get("total_size_bytes", 0) / (1024**2),
            "compression_ratio": 70.0,  # 70% reduction (approximate)
            "quota_gb": self.quota_gb,
            "usage_percent": 0.0,  # TODO: Calculate usage
            "oldest_session_days": 0,  # TODO: Calculate
            "newest_session_days": 0,  # TODO: Calculate
            "expired_sessions": 0,  # TODO: Calculate
        }

    async def cleanup_expired_sessions(self) -> int:
        """
        Background task: Remove sessions older than retention_days (365 days).

        Returns:
            Count of sessions deleted

        Flow:
            1. Find sessions with expires_at < now
            2. Delete files and metadata
            3. Save metadata
            4. Log summary

        Performance:
            - Efficient (batch deletion)
            - Non-blocking (background task)
            - <1000ms per 1000 sessions

        Metrics:
            - cold_tier_cleanup_total (Counter): Sessions cleaned up

        ADR: ADR-0020c
        """
        start_ns = time.perf_counter_ns()

        # TODO(@storage-team): Implement background cleanup
        # 1. Find expired sessions:
        #    now = datetime.utcnow()
        #    expired_sessions = [
        #        sid for sid, meta in self.metadata["sessions"].items()
        #        if datetime.fromisoformat(meta["expires_at"]) < now
        #    ]
        # 2. Delete each session:
        #    for session_id in expired_sessions:
        #        await self.delete(session_id)
        # 3. Emit metrics (cold_tier_cleanup_total.inc(len(expired_sessions)))
        # 4. Return count

        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        deleted_count = 0  # TODO: Replace with actual count

        logger.info(
            "[ColdTier] Cleanup expired sessions",
            deleted_count=deleted_count,
            total_latency_ms=round(latency_ms, 2),
        )
        return deleted_count

    async def _save_metadata(self) -> None:
        """
        Save metadata to sessions.json.

        Flow:
            1. Serialize metadata to JSON
            2. Write to {storage_path}/sessions.json
            3. Atomic write (write to temp, then rename)

        Performance:
            - <10ms P95 (async file write)

        ADR: ADR-0020c
        """
        # TODO(@storage-team): Implement metadata persistence
        # 1. Serialize: serialized = json.dumps(self.metadata, indent=2)
        # 2. Write atomically:
        #    temp_path = self.storage_path / f"{self.METADATA_FILE}.tmp"
        #    async with aiofiles.open(temp_path, "w") as f:
        #        await f.write(serialized)
        #    temp_path.rename(self.storage_path / self.METADATA_FILE)
        # 3. Log success

        logger.debug("[ColdTier] Metadata saved")

    async def _load_metadata(self) -> None:
        """
        Load metadata from sessions.json.

        Flow:
            1. Read {storage_path}/sessions.json if exists
            2. Parse JSON
            3. Update self.metadata

        Performance:
            - <10ms P95 (async file read)

        ADR: ADR-0020c
        """
        # TODO(@storage-team): Implement metadata loading
        # 1. Check if metadata file exists:
        #    metadata_path = self.storage_path / self.METADATA_FILE
        #    if not metadata_path.exists(): return
        # 2. Read and parse:
        #    async with aiofiles.open(metadata_path, "r") as f:
        #        content = await f.read()
        #    self.metadata = json.loads(content)
        # 3. Log success

        logger.debug("[ColdTier] Metadata loaded")

    async def _cleanup_loop(self) -> None:
        """
        Background task: Periodic cleanup of expired sessions.

        Runs every 24 hours to delete sessions older than retention_days.

        ADR: ADR-0020c
        """
        # TODO(@storage-team): Implement cleanup loop
        # 1. Loop forever:
        #    while True:
        #        await asyncio.sleep(self.CLEANUP_INTERVAL_SEC)
        #        await self.cleanup_expired_sessions()

        logger.info(
            "[ColdTier] Cleanup loop started", interval_sec=self.CLEANUP_INTERVAL_SEC
        )


class QuotaExceededError(Exception):
    """Raised when cold tier quota is exceeded"""

    pass


# Expected lint errors (documented):
# - Unused imports: datetime, timedelta (used in expiration checks, will be used in implementation)
# - Unused imports: asyncio (used for background cleanup loop)
# - Unused imports: json, os (used for metadata and file operations)
# - Unused imports: zstd (will be used for compression/decompression)
# - structlog not resolved (dependency not installed yet)
# These will be resolved when dependencies are installed and implementation is complete.
