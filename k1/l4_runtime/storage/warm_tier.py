"""
Warm Tier (L2 SSD/K0 WAL) Storage Implementation

This module implements the warm tier of K1's multi-tier storage architecture,
providing <50ms access to recently-used SessionState data backed by SSD storage
or K0's Write-Ahead Log (WAL).

Use Cases:
    1. SessionState fallback when hot tier misses (9% of queries)
    2. Durable storage for sessions evicted from hot tier
    3. 30-day retention before cold tier archival
    4. Automatic reconstruction from K0 WAL deltas

Performance Targets:
    - Get (SSD read): <50ms P95
    - Put (async write): <20ms P95
    - Delta reconstruction: <20ms for 10 deltas
    - Capacity: 100MB compressed (2000 sessions)
    - Compression: zstd level 3 (66% size reduction: 50KB → 17KB)
    - Retention: 30 days

Cost Analysis (vs Hot Tier):
    - Hot tier: 1000 sessions × 56KB = 56MB RAM (~$1016/month all-hot)
    - Warm tier: 2000 sessions × 17KB = 34MB SSD (~$0.10/month SSD)
    - Cost savings: ~99% for warm tier vs all-hot
    - Combined hot+warm: $6.30/month total

Trade-offs:
    - Slower than hot tier: 50ms vs <1ms (50× slower)
    - Faster than cold tier: 50ms vs 200ms (4× faster)
    - Supports delta reconstruction (K0 WAL backend)
    - Compression reduces capacity by 66%

Integration:
    - TierManager: Falls back to warm tier on hot miss
    - LifecycleManager: Migrates sessions after 30 days
    - K0 Bridge: Uses WAL for durable delta storage
    - HotTier: Caches reconstructed sessions on warm hit

ADR References:
    - ADR-0020: Multi-Tier Storage Architecture
    - ADR-0020b: Warm Tier (L2 SSD/K0 WAL) Design
    - ADR-0014: FlatBuffers for delta serialization
"""

import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class WarmTier:
    """
    Warm tier: SSD/K0 WAL storage with <50ms access and delta reconstruction.

    The warm tier provides durable storage for SessionState data that has been
    evicted from the hot tier but is still accessed occasionally. It uses either:
    1. K0 Write-Ahead Log (WAL) for delta-based reconstruction (preferred)
    2. SSD cache with zstd compression (fallback)

    Features:
        - <50ms P95 latency (50× slower than hot, 4× faster than cold)
        - 100MB capacity (2000 sessions compressed, 5× more than hot tier)
        - 30-day retention (automatic cold tier migration)
        - zstd compression (66% size reduction: 50KB → 17KB)
        - Delta reconstruction from K0 WAL (append-only, zero overwrites)
        - Async operations (non-blocking I/O)

    Delta Reconstruction (K0 WAL Backend):
        1. Query WAL for session_id deltas (chronologically ordered)
        2. Deserialize FlatBuffers delta payloads (zero-copy)
        3. Replay deltas to reconstruct SessionState (<20ms for 10 deltas)
        4. Cache in hot tier for future <1ms access

    Compression (SSD Backend):
        - Algorithm: zstd level 3 (fast compression/decompression)
        - Ratio: 66% size reduction (50KB → 17KB average)
        - Compress latency: <5ms P95
        - Decompress latency: <5ms P95

    Capacity Management:
        - Max capacity: 100MB compressed
        - Average session: 17KB compressed (50KB uncompressed)
        - Max sessions: ~5,882 (100MB / 17KB)
        - Eviction: Automatic migration to cold tier after 30 days
        - No LRU needed (time-based archival only)

    Lifecycle Transitions:
        - Hot → Warm: Eviction (LRU or idle timeout) via LifecycleManager
        - Warm → Hot: Cache promotion on access (hot tier caching)
        - Warm → Cold: 30-day archival via LifecycleManager background task

    Backend Selection:
        - Preferred: K0 WAL (delta-based, append-only, durable)
        - Fallback: SSD cache (full snapshot, zstd compressed)
        - Selection: Constructor arg `backend="k0_wal"` or `backend="ssd_cache"`

    Performance Budget:
        - Get (K0 WAL): <30ms query + <20ms reconstruction = <50ms P95
        - Get (SSD): <40ms read + <5ms decompress = <50ms P95
        - Put (K0 WAL): <20ms append (async, non-blocking)
        - Put (SSD): <5ms compress + <10ms write = <20ms P95
        - Migration (30-day): <500ms per session (background task)

    Example Usage:
        ```python
        # Initialize warm tier with K0 WAL backend
        warm_tier = WarmTier(
            capacity_mb=100,
            backend="k0_wal",
            retention_days=30,
            k0_bridge=k0_bridge,  # K0 integration
            hot_tier=hot_tier,    # Cache promotion
            cold_tier=cold_tier,  # Archival target
        )

        # Get session (reconstructs from K0 WAL deltas)
        session_state = await warm_tier.get("session_123")
        if session_state:
            print("Warm hit:", session_state)
        else:
            print("Warm miss")

        # Put session (appends to K0 WAL)
        await warm_tier.put("session_123", session_state)

        # Background migration (30+ days)
        await warm_tier.migrate_to_cold()

        # Get statistics
        stats = await warm_tier.get_stats()
        print(f"Sessions: {stats['sessions']}")
        print(f"Size: {stats['size_mb']:.2f} MB")
        print(f"Hit rate: {stats['hit_rate']:.2%}")
        print(f"Compress ratio: {stats['compress_ratio']:.2f}")
        ```

    WARD Test Examples:
        ```python
        # Test 1: Store and retrieve session (K0 WAL)
        @ward.test("warm_tier stores and retrieves session from K0 WAL")
        async def test_warm_tier_k0_wal():
            k0_bridge = MockK0Bridge()
            warm_tier = WarmTier(backend="k0_wal", k0_bridge=k0_bridge)

            session_state = {"session_id": "s1", "beliefs": {"user": "Alice"}}
            await warm_tier.put("s1", session_state)

            retrieved = await warm_tier.get("s1")
            ward.assert_equal(retrieved["session_id"], "s1")
            ward.assert_equal(retrieved["beliefs"]["user"], "Alice")

        # Test 2: Delta reconstruction from K0 WAL
        @ward.test("warm_tier reconstructs session from K0 WAL deltas")
        async def test_warm_tier_delta_reconstruction():
            k0_bridge = MockK0Bridge()
            warm_tier = WarmTier(backend="k0_wal", k0_bridge=k0_bridge)

            # Append 3 deltas to K0 WAL
            k0_bridge.append_delta("s1", {"beliefs": {"user": "Alice"}})
            k0_bridge.append_delta("s1", {"beliefs": {"age": "30"}})
            k0_bridge.append_delta("s1", {"scoreboard": {"entities": ["person1"]}})

            # Get should reconstruct from deltas
            session_state = await warm_tier.get("s1")
            ward.assert_equal(session_state["beliefs"]["user"], "Alice")
            ward.assert_equal(session_state["beliefs"]["age"], "30")
            ward.assert_equal(len(session_state["scoreboard"]["entities"]), 1)

        # Test 3: 30-day migration to cold tier
        @ward.test("warm_tier migrates 30-day sessions to cold tier")
        async def test_warm_tier_cold_migration():
            cold_tier = MockColdTier()
            warm_tier = WarmTier(retention_days=30, cold_tier=cold_tier)

            # Store session 31 days ago
            session_state = {"session_id": "s1", "created_at": (datetime.utcnow() - timedelta(days=31)).isoformat()}
            await warm_tier.put("s1", session_state)

            # Trigger migration
            await warm_tier.migrate_to_cold()

            # Verify session moved to cold tier
            ward.assert_equal(cold_tier.get("s1")["session_id"], "s1")
            ward.assert_is_none(await warm_tier.get("s1"))  # Removed from warm
        ```

    TODO List:
        - TODO(@storage-team): Initialize K0 bridge connection
        - TODO(@storage-team): Implement delta reconstruction from K0 WAL
        - TODO(@storage-team): Add zstd compression for SSD backend
        - TODO(@storage-team): Implement 30-day migration background task
        - TODO(@storage-team): Add Prometheus metrics (get_latency, put_latency, migration_total)
        - TODO(@storage-team): Implement SSD cache fallback backend
        - TODO(@storage-team): Add retention policy enforcement
        - TODO(@storage-team): Implement hot tier caching on warm hit
        - TODO(@storage-team): Add delta replay testing with FlatBuffers
        - TODO(@storage-team): Implement capacity tracking (100MB limit)

    ADR References:
        - ADR-0020: Multi-Tier Storage Architecture
        - ADR-0020b: Warm Tier (L2 SSD/K0 WAL) Design
        - ADR-0014: FlatBuffers Serialization (delta payloads)
    """

    # Constants
    MAX_CAPACITY_MB = 100  # 100MB compressed capacity
    RETENTION_DAYS = 30  # 30-day retention before cold migration
    COMPRESSION_LEVEL = 3  # zstd level 3 (fast, 66% reduction)
    MIGRATION_INTERVAL_SEC = 3600  # Check every hour for old sessions

    def __init__(
        self,
        capacity_mb: int = MAX_CAPACITY_MB,
        backend: str = "k0_wal",  # "k0_wal" or "ssd_cache"
        retention_days: int = RETENTION_DAYS,
        k0_bridge=None,  # K0 bridge for WAL backend
        hot_tier=None,  # Hot tier for cache promotion
        cold_tier=None,  # Cold tier for 30-day archival
    ):
        """
        Initialize warm tier.

        Args:
            capacity_mb: Total capacity in MB (default: 100MB compressed)
            backend: Storage backend ("k0_wal" or "ssd_cache", default: "k0_wal")
            retention_days: Retention period (default: 30 days)
            k0_bridge: K0 bridge instance (required for "k0_wal" backend)
            hot_tier: HotTier instance for cache promotion (optional)
            cold_tier: ColdTier instance for archival (optional)

        Raises:
            ValueError: If backend="k0_wal" but k0_bridge is None

        Implementation Notes:
            - K0 WAL backend: Uses delta-based reconstruction (preferred)
            - SSD cache backend: Uses full snapshots with zstd compression
            - Metrics initialized: warm_tier_get_latency_ms, warm_tier_put_total

        ADR: ADR-0020b (Warm Tier)
        """
        # TODO(@storage-team): Initialize warm tier
        # 1. Validate backend ("k0_wal" or "ssd_cache")
        # 2. Check k0_bridge if backend="k0_wal"
        # 3. Initialize storage backend connection
        # 4. Setup compression (zstd level 3)
        # 5. Initialize size/retention tracking
        # 6. Initialize Prometheus metrics:
        #    - warm_tier_get_latency_ms (Histogram)
        #    - warm_tier_put_total (Counter)
        #    - warm_tier_migrated_total (Counter)
        #    - warm_tier_reconstruction_latency_ms (Histogram)
        # 7. Store references: hot_tier, cold_tier
        self.capacity_mb = capacity_mb
        self.backend = backend
        self.retention_days = retention_days
        self.k0_bridge = k0_bridge
        self.hot_tier = hot_tier
        self.cold_tier = cold_tier

        # Tracking
        self.sessions = OrderedDict()  # session_id → metadata (created_at, size_kb)
        self.hit_count = 0
        self.miss_count = 0

        logger.info(
            "[WarmTier] Initialized warm tier",
            capacity_mb=capacity_mb,
            backend=backend,
            retention_days=retention_days,
        )

    async def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve SessionState from warm tier.

        Args:
            session_id: Session identifier

        Returns:
            SessionState dict or None if not found

        Flow:
            1. Query backend (K0 WAL or SSD cache)
            2. Reconstruct from deltas (K0 WAL) or decompress (SSD)
            3. Cache in hot tier (if configured)
            4. Return session or None

        Performance:
            - K0 WAL: <30ms query + <20ms reconstruction = <50ms P95
            - SSD cache: <40ms read + <5ms decompress = <50ms P95

        Metrics:
            - warm_tier_get_latency_ms (Histogram): Total get latency
            - warm_tier_reconstruction_latency_ms (Histogram): Delta reconstruction time

        ADR: ADR-0020b
        """
        start_ns = time.perf_counter_ns()

        # TODO(@storage-team): Implement async get
        # 1. Check backend type (k0_wal vs ssd_cache)
        # 2. K0 WAL path:
        #    a. Query deltas: deltas = await self.k0_bridge.query_wal(session_id)
        #    b. If no deltas, return None (miss)
        #    c. Reconstruct: session_state = await self._reconstruct_from_deltas(session_id, deltas)
        # 3. SSD cache path:
        #    a. Read compressed file: compressed = await self._read_ssd(session_id)
        #    b. If not found, return None (miss)
        #    c. Decompress: session_state = zstd.decompress(compressed)
        # 4. Cache in hot tier: if self.hot_tier: self.hot_tier.put(session_id, session_state)
        # 5. Update hit/miss counters
        # 6. Emit metrics (warm_tier_get_latency_ms)
        # 7. Return session_state

        # Placeholder implementation
        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        logger.debug(
            "[WarmTier] Get operation",
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
        Store SessionState in warm tier.

        Args:
            session_id: Session identifier
            state: SessionState dict

        Flow:
            1. Serialize state (full snapshot or delta)
            2. Compress (zstd) if SSD backend
            3. Write to backend (async, non-blocking)
            4. Update retention timestamp

        Performance:
            - K0 WAL: <20ms append (async)
            - SSD cache: <5ms compress + <10ms write = <20ms P95

        Metrics:
            - warm_tier_put_total (Counter): Total put operations

        ADR: ADR-0020b
        """
        start_ns = time.perf_counter_ns()

        # TODO(@storage-team): Implement async put
        # 1. Check backend type
        # 2. K0 WAL path:
        #    a. Serialize full state: serialized = self.serializer.serialize_full(state)
        #    b. Append to WAL: await self.k0_bridge.append_wal(session_id, serialized)
        # 3. SSD cache path:
        #    a. Serialize: serialized = json.dumps(state).encode()
        #    b. Compress: compressed = zstd.compress(serialized, self.COMPRESSION_LEVEL)
        #    c. Write: await self._write_ssd(session_id, compressed)
        # 4. Update tracking:
        #    - self.sessions[session_id] = {"created_at": datetime.utcnow(), "size_kb": len(serialized) / 1024}
        # 5. Emit metrics (warm_tier_put_total.inc())

        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        logger.info(
            "[WarmTier] Put operation",
            session_id=session_id,
            latency_ms=round(latency_ms, 2),
        )

    async def remove(self, session_id: str) -> None:
        """
        Remove session from warm tier.

        Args:
            session_id: Session to remove

        Flow:
            1. Delete from backend (K0 WAL or SSD)
            2. Remove from tracking

        Performance:
            - Remove: <5ms P95

        ADR: ADR-0020b
        """
        # TODO(@storage-team): Implement async remove
        # 1. Check backend type
        # 2. K0 WAL: await self.k0_bridge.delete_session(session_id)
        # 3. SSD cache: await self._delete_ssd(session_id)
        # 4. Remove from tracking: del self.sessions[session_id]

        logger.info("[WarmTier] Remove operation", session_id=session_id)

    async def contains(self, session_id: str) -> bool:
        """
        Check if session exists in warm tier.

        Args:
            session_id: Session to check

        Returns:
            True if session exists, False otherwise

        Performance:
            - Check: <1ms (metadata lookup)

        ADR: ADR-0020b
        """
        # TODO(@storage-team): Implement async contains
        # 1. Check self.sessions dict (O(1) lookup)
        # 2. Return bool

        return session_id in self.sessions

    async def migrate_to_cold(self) -> int:
        """
        Migrate sessions older than 30 days to cold tier.

        This background task runs periodically (every hour) to:
        1. Query sessions older than retention_days (30 days)
        2. Retrieve each session from warm tier
        3. Archive to cold tier
        4. Delete from warm tier

        Returns:
            Number of sessions migrated

        Performance:
            - Per session: <500ms (get + cold put + delete)
            - Batch: Parallelized with asyncio.gather()

        Metrics:
            - warm_tier_migrated_total (Counter): Sessions migrated

        ADR: ADR-0020b
        """
        start_ns = time.perf_counter_ns()

        # TODO(@storage-team): Implement 30-day migration
        # 1. Calculate cutoff: cutoff = datetime.utcnow() - timedelta(days=self.retention_days)
        # 2. Find old sessions:
        #    old_sessions = [
        #        sid for sid, meta in self.sessions.items()
        #        if meta["created_at"] < cutoff
        #    ]
        # 3. Migrate each session:
        #    for session_id in old_sessions:
        #        a. session_state = await self.get(session_id)
        #        b. if self.cold_tier: await self.cold_tier.put(session_id, session_state)
        #        c. await self.remove(session_id)
        # 4. Emit metrics (warm_tier_migrated_total.inc(len(old_sessions)))
        # 5. Return count

        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        logger.info(
            "[WarmTier] Migration to cold tier complete",
            migrated_count=0,  # TODO: Replace with actual count
            total_latency_ms=round(latency_ms, 2),
        )
        return 0  # TODO: Replace with actual count

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get warm tier statistics.

        Returns:
            Dict with:
                - sessions: Current session count
                - size_mb: Current size (compressed)
                - capacity_mb: Total capacity
                - retention_days: Current retention policy
                - hit_rate: Cache hit rate (hits / (hits + misses))
                - compress_ratio: Compression ratio (original / compressed)
                - backend: Storage backend ("k0_wal" or "ssd_cache")

        Performance:
            - Stats: <5ms (aggregate tracking data)

        ADR: ADR-0020b
        """
        # TODO(@storage-team): Implement stats
        # 1. Calculate total size: sum([meta["size_kb"] for meta in self.sessions.values()]) / 1024
        # 2. Calculate hit rate: self.hit_count / (self.hit_count + self.miss_count) if total > 0 else 0.0
        # 3. Return comprehensive dict

        return {
            "sessions": len(self.sessions),
            "size_mb": 0.0,  # TODO: Calculate actual size
            "capacity_mb": self.capacity_mb,
            "retention_days": self.retention_days,
            "hit_rate": 0.0,  # TODO: Calculate hit rate
            "compress_ratio": 0.66,  # 66% reduction (approximate)
            "backend": self.backend,
        }

    async def _reconstruct_from_deltas(
        self, session_id: str, deltas: List[bytes]
    ) -> Dict[str, Any]:
        """
        Reconstruct SessionState from K0 WAL delta chain.

        Args:
            session_id: Session identifier
            deltas: List of FlatBuffers delta payloads (chronologically ordered)

        Returns:
            Reconstructed SessionState dict

        Flow:
            1. Start with empty SessionState
            2. Deserialize each delta (FlatBuffers, zero-copy)
            3. Apply delta to session state
            4. Return final state

        Performance:
            - <20ms for 10 deltas
            - O(n) where n = number of deltas

        ADR: ADR-0020b, ADR-0014 (FlatBuffers)
        """
        # TODO(@storage-team): Implement delta reconstruction
        # 1. Initialize: session_state = {"session_id": session_id, "beliefs": {}, "scoreboard": {}, ...}
        # 2. Replay deltas:
        #    for i, delta_bytes in enumerate(deltas):
        #        a. delta = self.deserializer.deserialize_delta(delta_bytes)
        #        b. self._apply_delta(session_state, delta)
        # 3. Return session_state

        logger.debug(
            "[WarmTier] Delta reconstruction",
            session_id=session_id,
            delta_count=len(deltas),
        )
        return {}  # TODO: Replace with actual implementation

    def _apply_delta(self, session_state: Dict[str, Any], delta: Any) -> None:
        """
        Apply FlatBuffers delta to SessionState.

        Args:
            session_state: SessionState dict to modify
            delta: FlatBuffers SessionStateDelta

        Flow:
            1. Apply beliefs section (if present)
            2. Apply scoreboard section (if present)
            3. Apply control section (if present)
            4. Apply persona section (if present)
            5. Apply multimodal section (if present)
            6. Apply meta section (if present)

        Performance:
            - <2ms per delta (zero-copy deserialization)

        ADR: ADR-0014 (FlatBuffers delta format)
        """
        # TODO(@storage-team): Implement delta application
        # 1. Check delta.BeliefsLength() > 0:
        #    for i in range(delta.BeliefsLength()):
        #        fact = delta.Beliefs(i)
        #        session_state["beliefs"][fact.Key().decode()] = fact.Value().decode()
        # 2. Check delta.ScoreboardLength() > 0:
        #    for i in range(delta.ScoreboardLength()):
        #        entity = delta.Scoreboard(i)
        #        session_state["scoreboard"]["entities"].append(entity.Name().decode())
        # 3. Apply other sections similarly (control, persona, multimodal, meta)

        pass

    async def _read_ssd(self, session_id: str) -> Optional[bytes]:
        """
        Read compressed session from SSD cache.

        Args:
            session_id: Session identifier

        Returns:
            Compressed bytes or None if not found

        Performance:
            - <40ms P95 (SSD read)

        ADR: ADR-0020b
        """
        # TODO(@storage-team): Implement SSD read
        # 1. Construct path: f"/var/lib/familyos/warm_tier/{session_id}.json.zst"
        # 2. Read file: async with aiofiles.open(path, "rb") as f: compressed = await f.read()
        # 3. Return compressed or None

        return None

    async def _write_ssd(self, session_id: str, compressed: bytes) -> None:
        """
        Write compressed session to SSD cache.

        Args:
            session_id: Session identifier
            compressed: Compressed session bytes

        Performance:
            - <10ms P95 (async SSD write)

        ADR: ADR-0020b
        """
        # TODO(@storage-team): Implement SSD write
        # 1. Construct path: f"/var/lib/familyos/warm_tier/{session_id}.json.zst"
        # 2. Create directory if not exists
        # 3. Write file: async with aiofiles.open(path, "wb") as f: await f.write(compressed)

        pass

    async def _delete_ssd(self, session_id: str) -> None:
        """
        Delete session from SSD cache.

        Args:
            session_id: Session identifier

        Performance:
            - <5ms P95 (async file delete)

        ADR: ADR-0020b
        """
        # TODO(@storage-team): Implement SSD delete
        # 1. Construct path: f"/var/lib/familyos/warm_tier/{session_id}.json.zst"
        # 2. Delete file: os.remove(path)

        pass


# Expected lint errors (documented):
# - Unused imports: time (used in perf_counter_ns, will be used for idle checks)
# - Unused imports: asyncio (used for background tasks, will be used in migration loop)
# - Unused imports: zstd (will be used for SSD backend compression)
# - structlog not resolved (dependency not installed yet)
# These will be resolved when dependencies are installed and implementation is complete.
