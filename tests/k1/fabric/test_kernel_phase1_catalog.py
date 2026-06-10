"""Issue 7.3 — Tests for KernelService Phase 1 wiring (config + catalog helper).

These exercise the testable surface of Issue 7.3 WITHOUT booting the kernel:
  * KernelConfig Phase 1 fields default to OFF/safe values.
  * KernelService Phase 1 store fields default to None.
  * ``_load_phase1_catalog_and_verifier`` admits the 50-connector catalog.
  * The helper is best-effort (no store → no-op, never raises).

Lives under tests/k1/fabric/ (not tests/k1/kernel/) so it runs with the
Fabric suite and never triggers a full kernel boot.
"""

from __future__ import annotations

from k1.concierge.config.kernel import KernelConfig
from k1.fabric.stores.global_projection_store import GlobalProjectionStore
from k1.kernel.service import KernelService

# ──────────────────────────────────────────────────────────────────────
# Config defaults
# ──────────────────────────────────────────────────────────────────────


class TestKernelConfigPhase1Defaults:
    def test_enable_fabric_stores_defaults_off(self):
        assert KernelConfig().enable_fabric_stores is False

    def test_db_path_defaults(self):
        c = KernelConfig()
        assert c.global_projection_db_path == "./data/global_projection.db"
        assert c.idempotency_db_path == "./data/idempotency.db"


# ──────────────────────────────────────────────────────────────────────
# Service store fields
# ──────────────────────────────────────────────────────────────────────


class TestKernelServicePhase1Fields:
    def test_store_fields_default_none(self):
        ks = KernelService(KernelConfig())
        assert ks._global_projection_store is None
        assert ks._idempotency_store is None

    def test_catalog_helper_exists(self):
        ks = KernelService(KernelConfig())
        assert hasattr(ks, "_load_phase1_catalog_and_verifier")


# ──────────────────────────────────────────────────────────────────────
# Catalog admission helper
# ──────────────────────────────────────────────────────────────────────


class TestCatalogAdmissionHelper:
    def test_admits_full_catalog(self):
        ks = KernelService(KernelConfig())
        gps = GlobalProjectionStore(":memory:")
        gps.open()
        ks._global_projection_store = gps
        ks._load_phase1_catalog_and_verifier()
        # 5 domains × 10 services = 50 connectors.
        assert len(gps.list_connectors()) == 50
        assert gps.count_capabilities() > 0

    def test_admitted_catalog_is_discoverable(self):
        ks = KernelService(KernelConfig())
        gps = GlobalProjectionStore(":memory:")
        gps.open()
        ks._global_projection_store = gps
        ks._load_phase1_catalog_and_verifier()
        rows = gps.lookup_capability_by_type(
            domain="family",
            resource_family="calendar_event",
            operation_family="create",
            effect="write",
        )
        assert len(rows) >= 1

    def test_helper_noop_without_store(self):
        ks = KernelService(KernelConfig())
        assert ks._global_projection_store is None
        # Must not raise.
        ks._load_phase1_catalog_and_verifier()

    def test_verifier_not_wired_in_phase1(self):
        # The verifier needs a NativeReadbackPort that doesn't exist in
        # Phase 1; the helper must not fabricate one.
        ks = KernelService(KernelConfig())
        gps = GlobalProjectionStore(":memory:")
        gps.open()
        ks._global_projection_store = gps
        ks._load_phase1_catalog_and_verifier()
        # No shared fabric / verifier wired by the catalog helper.
        assert ks._shared_fabric is None
