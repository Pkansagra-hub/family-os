"""Epic 7.2 — Multi-tenant partition isolation tests.

Validates that K0 commits each write into the partition keyed by the
publishing device's ``(tenant_id, space_id)`` and that no foreign
tenant/space sees the row in ``st_receipts``.

These tests use :meth:`K1Handle.publish_memory_write_v1_native`, which
mirrors the proven ``k0/deploy/scripts/events/family_life_events.py``
wire shape and reliably yields HTTP 200 + a real receipt from the
live K0 stack. Direct PG observation goes through
:mod:`tests.integration.harness.k0_observer` (``docker exec psql``).

The tests are scaffolded as a writer×scope×reader matrix; the first
slice is the foundational *cross-family* isolation check. Subsequent
parametrized cases will extend coverage to intra-family scope bands
(parents_only, kids_only, child_visible) once K0 admission of those
band labels is wired up — they are deliberately gated behind a single
parametrize so adding bands does not disturb the foundation.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from tests.integration.harness.device_provisioner import provision_extra_device
from tests.integration.harness.envelope_publisher import publish_memory_write_native
from tests.integration.harness.family_layout import (
    DeviceSpec,
    FamilyLayout,
    PersonSpec,
)
from tests.integration.harness.k0_observer import (
    count_receipts,
    latest_receipt_for_device,
    list_receipt_device_ids,
    list_wal_positions_for_space,
    partition_view,
)
from tests.integration.harness.live_system import LiveSystem


def _hex(n: int = 8) -> str:
    return uuid.uuid4().hex[:n]


def _two_isolated_families() -> tuple[FamilyLayout, FamilyLayout]:
    """Return two families with non-overlapping tenant/space/device ids."""
    fam_a = FamilyLayout(
        family_id=f"fam-A-{_hex()}",
        people=(
            PersonSpec(
                person_id=f"father-A-{_hex()}",
                role="single",
                devices=(DeviceSpec(device_id=f"dev-A-{_hex()}", label="phone"),),
            ),
        ),
    )
    fam_b = FamilyLayout(
        family_id=f"fam-B-{_hex()}",
        people=(
            PersonSpec(
                person_id=f"father-B-{_hex()}",
                role="single",
                devices=(DeviceSpec(device_id=f"dev-B-{_hex()}", label="phone"),),
            ),
        ),
    )
    return fam_a, fam_b


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cross_family_write_isolation_in_st_receipts() -> None:
    """Two families publishing concurrently must not see each other's receipts.

    Family A writes 3 memories, family B writes 2. After both round-trips
    commit, ``st_receipts`` filtered by family A's space contains exactly
    family A's device id (and only it), and the count for family A's
    (tenant, space) is exactly 3 (delta against the snapshot taken before
    publishing). Symmetric assertion for family B.
    """
    fam_a, fam_b = _two_isolated_families()
    a_dev = fam_a.people[0].devices[0].device_id
    b_dev = fam_b.people[0].devices[0].device_id

    async with LiveSystem(family=fam_a) as live_a, LiveSystem(family=fam_b) as live_b:
        # Snapshot baselines so the test is hermetic against prior runs.
        baseline_a = count_receipts(tenant_id=fam_a.family_id, space_id=fam_a.family_id)
        baseline_b = count_receipts(tenant_id=fam_b.family_id, space_id=fam_b.family_id)

        # Publish concurrently to maximize chance of cross-tenant interleaving.
        k1_a = live_a.k1s[0]
        k1_b = live_b.k1s[0]
        a_results, b_results = await asyncio.gather(
            asyncio.gather(
                *[
                    k1_a.publish_memory_write_v1_native(
                        text=f"family-A memory #{i}",
                        topics=["integration", "isolation"],
                        conversation_turn=i + 1,
                    )
                    for i in range(3)
                ]
            ),
            asyncio.gather(
                *[
                    k1_b.publish_memory_write_v1_native(
                        text=f"family-B memory #{i}",
                        topics=["integration", "isolation"],
                        conversation_turn=i + 1,
                    )
                    for i in range(2)
                ]
            ),
        )

        # Every publish landed (HTTP 200 from K0, with a receipt_id).
        assert all(r["http_status"] == 200 for r in a_results), a_results
        assert all(r["http_status"] == 200 for r in b_results), b_results
        assert all("receipt_id" in r["body"] for r in a_results), a_results
        assert all("receipt_id" in r["body"] for r in b_results), b_results

    # Receipts arrived in the correct partition only.
    after_a = count_receipts(tenant_id=fam_a.family_id, space_id=fam_a.family_id)
    after_b = count_receipts(tenant_id=fam_b.family_id, space_id=fam_b.family_id)
    assert after_a - baseline_a == 3, (baseline_a, after_a)
    assert after_b - baseline_b == 2, (baseline_b, after_b)

    # Family A's space contains only family A's device — no leakage from B.
    a_devices = list_receipt_device_ids(space_id=fam_a.family_id)
    assert a_dev in a_devices, a_devices
    assert b_dev not in a_devices, a_devices

    # Symmetric: family B's space contains only family B's device.
    b_devices = list_receipt_device_ids(space_id=fam_b.family_id)
    assert b_dev in b_devices, b_devices
    assert a_dev not in b_devices, b_devices

    # Cross-tenant queries also confirm no row was misfiled.
    assert count_receipts(tenant_id=fam_a.family_id, device_id=b_dev) == 0
    assert count_receipts(tenant_id=fam_b.family_id, device_id=a_dev) == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_partition_view_shape_after_single_write() -> None:
    """Smallest-possible isolation check: one family, one write, asserts
    that the receipt's tenant/space/device fields exactly match the
    publishing device, and ``partition_view`` reports it.
    """
    fam_a, _ = _two_isolated_families()
    dev_id = fam_a.people[0].devices[0].device_id

    async with LiveSystem(family=fam_a) as live:
        k1 = live.k1s[0]
        result = await k1.publish_memory_write_v1_native(
            text="single-write partition view probe",
            topics=["integration"],
        )
        assert result["http_status"] == 200, result

    receipt = latest_receipt_for_device(dev_id)
    assert receipt is not None, "no receipt found for the publishing device"
    assert receipt["tenant_id"] == fam_a.family_id
    assert receipt["space_id"] == fam_a.family_id
    assert receipt["device_id"] == dev_id

    view = partition_view(tenant_id=fam_a.family_id, space_id=fam_a.family_id)
    assert view.receipts >= 1
    assert dev_id in view.devices


@pytest.mark.integration
@pytest.mark.asyncio
async def test_no_cross_space_device_leakage_after_burst() -> None:
    """Burst write from family A must not surface family A's device id
    in any *other* space's ``st_receipts`` device list.
    """
    fam_a, fam_b = _two_isolated_families()
    a_dev = fam_a.people[0].devices[0].device_id

    # Bring up family B first so its space exists in the ledger,
    # then write only from family A.
    async with LiveSystem(family=fam_b):
        pass

    async with LiveSystem(family=fam_a) as live_a:
        k1_a = live_a.k1s[0]
        await asyncio.gather(
            *[
                k1_a.publish_memory_write_v1_native(
                    text=f"burst memory #{i}", topics=["integration"]
                )
                for i in range(4)
            ]
        )

    devices_in_b = list_receipt_device_ids(space_id=fam_b.family_id)
    assert a_dev not in devices_in_b, (
        f"Family A's device {a_dev!r} leaked into family B's space "
        f"{fam_b.family_id!r}: {devices_in_b}"
    )


# ---------------------------------------------------------------------------
# Intra-family scope-band slices
#
# K0 has no first-class "parents_only / kids_only / child_visible" enum.
# The natural model is one *space_id* per logical scope band, all sharing
# the family's ``tenant_id``. Because the K0 ``minimal_gate`` enforces
# ``SPACE_TENANT_MISMATCH`` against the device's *provisioned* binding,
# each scope-band space requires its own provisioned device row. The
# tests below provision one ad-hoc device per band and publish from
# each, then assert per-space isolation in ``st_receipts``.
# ---------------------------------------------------------------------------


_K0_BASE_URL = "http://127.0.0.1:8080"


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scope_bands",
    [
        ("private", "family", "parents_only"),
        ("kids_only", "child_visible", "family"),
    ],
    ids=["private+family+parents_only", "kids_only+child_visible+family"],
)
async def test_intra_family_scope_band_partitions_are_isolated(
    scope_bands: tuple[str, str, str],
) -> None:
    """One ad-hoc device per scope-band space, all under one tenant.

    Each band's space must contain exactly one new receipt and that
    receipt must reference *only* its own band-bound device. Writes to
    sibling bands under the same tenant must not leak into any other
    band's space.
    """
    tenant_id = f"fam-{_hex()}"
    band_spaces = {band: f"{tenant_id}/{band}" for band in scope_bands}
    band_devices = {
        band: provision_extra_device(
            device_id=f"dev-{band}-{_hex()}",
            tenant_id=tenant_id,
            space_id=sp,
        )
        for band, sp in band_spaces.items()
    }
    baselines = {sp: count_receipts(space_id=sp) for sp in band_spaces.values()}

    for band, dev in band_devices.items():
        r = await publish_memory_write_native(
            k0_base_url=_K0_BASE_URL,
            tenant_id=tenant_id,
            space_id=dev.space_id,
            device_id=dev.device_id,
            actor=f"actor-{band}",
            signing_seed=dev.ed25519_seed,
            text=f"memory for scope {band}",
            topics=["integration", "scope-band"],
        )
        assert r["http_status"] == 200, (band, r)

    for band, sp in band_spaces.items():
        delta = count_receipts(space_id=sp) - baselines[sp]
        assert delta == 1, (band, sp, baselines[sp], delta)
        # Each band-space should contain only its band's device id.
        devices_seen = list_receipt_device_ids(space_id=sp)
        own_dev = band_devices[band].device_id
        assert own_dev in devices_seen, (band, sp, devices_seen)
        for other_band, other_dev in band_devices.items():
            if other_band == band:
                continue
            assert other_dev.device_id not in devices_seen, (
                f"device {other_dev.device_id!r} from band {other_band!r} "
                f"leaked into band {band!r} space {sp!r}: {devices_seen}"
            )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_devices_same_space_all_present() -> None:
    """Two devices in one family writing to the *same* (provisioned)
    space must both appear in that space's receipt device list, and
    the receipt count must equal the sum of their writes.
    """
    fam = FamilyLayout(
        family_id=f"fam-{_hex()}",
        people=(
            PersonSpec(
                person_id=f"father-{_hex()}",
                role="single",
                devices=(
                    DeviceSpec(device_id=f"dev-A-{_hex()}", label="phone"),
                    DeviceSpec(device_id=f"dev-B-{_hex()}", label="laptop"),
                ),
            ),
        ),
    )
    # Both devices are provisioned to space_id == family.family_id by
    # ``provision_family``, so we publish to that exact space.
    space = fam.family_id
    dev_a, dev_b = (d.device_id for d in fam.people[0].devices)
    baseline = count_receipts(space_id=space)

    async with LiveSystem(family=fam) as live:
        # The K1 spawn loop creates one K1 per (person, device) pair.
        assert len(live.k1s) == 2, [k.device_id for k in live.k1s]
        k1_by_device = {k.device_id: k for k in live.k1s}

        results = await asyncio.gather(
            k1_by_device[dev_a].publish_memory_write_v1_native(
                text="from dev A", topics=["integration"]
            ),
            k1_by_device[dev_b].publish_memory_write_v1_native(
                text="from dev B", topics=["integration"]
            ),
            k1_by_device[dev_a].publish_memory_write_v1_native(
                text="from dev A again", topics=["integration"]
            ),
        )
        assert all(r["http_status"] == 200 for r in results), results

    delta = count_receipts(space_id=space) - baseline
    assert delta == 3, delta
    devices = list_receipt_device_ids(space_id=space)
    assert dev_a in devices, devices
    assert dev_b in devices, devices


@pytest.mark.integration
@pytest.mark.asyncio
async def test_wal_positions_strictly_monotonic_within_space() -> None:
    """WAL positions for receipts in the same provisioned space must be
    strictly increasing in the order they were committed.
    """
    fam_id = f"fam-{_hex()}"
    space = f"{fam_id}/wal-monotonic"
    dev = provision_extra_device(device_id=f"dev-{_hex()}", tenant_id=fam_id, space_id=space)
    baseline_positions = list_wal_positions_for_space(space)

    for i in range(5):
        r = await publish_memory_write_native(
            k0_base_url=_K0_BASE_URL,
            tenant_id=fam_id,
            space_id=space,
            device_id=dev.device_id,
            actor=f"actor-{i}",
            signing_seed=dev.ed25519_seed,
            text=f"sequential write #{i}",
            topics=["integration", "wal"],
        )
        assert r["http_status"] == 200, (i, r)

    positions = list_wal_positions_for_space(space)
    assert len(positions) == len(baseline_positions) + 5, (
        baseline_positions,
        positions,
    )
    new_positions = positions[len(baseline_positions) :]
    assert all(
        new_positions[i] < new_positions[i + 1] for i in range(len(new_positions) - 1)
    ), new_positions


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tenant_query_excludes_other_tenants_completely() -> None:
    """Strong cross-tenant negative: a row written under tenant A's
    second space must never surface under tenant B, even when both
    tenants have receipts in the system.
    """
    tenant_a = f"tenA-{_hex()}"
    tenant_b = f"tenB-{_hex()}"
    space_a1 = f"{tenant_a}/private"
    space_a2 = f"{tenant_a}/family"
    space_b1 = f"{tenant_b}/private"

    dev_a1 = provision_extra_device(
        device_id=f"dev-A1-{_hex()}", tenant_id=tenant_a, space_id=space_a1
    )
    dev_a2 = provision_extra_device(
        device_id=f"dev-A2-{_hex()}", tenant_id=tenant_a, space_id=space_a2
    )
    dev_b1 = provision_extra_device(
        device_id=f"dev-B1-{_hex()}", tenant_id=tenant_b, space_id=space_b1
    )

    for sp, dev in ((space_a1, dev_a1), (space_a2, dev_a2)):
        r = await publish_memory_write_native(
            k0_base_url=_K0_BASE_URL,
            tenant_id=tenant_a,
            space_id=sp,
            device_id=dev.device_id,
            actor=f"actor-{tenant_a}",
            signing_seed=dev.ed25519_seed,
            text=f"A→{sp}",
            topics=["integration"],
        )
        assert r["http_status"] == 200, (sp, r)

    r = await publish_memory_write_native(
        k0_base_url=_K0_BASE_URL,
        tenant_id=tenant_b,
        space_id=space_b1,
        device_id=dev_b1.device_id,
        actor=f"actor-{tenant_b}",
        signing_seed=dev_b1.ed25519_seed,
        text=f"B→{space_b1}",
        topics=["integration"],
    )
    assert r["http_status"] == 200, r

    # Tenant A: each of its two spaces has exactly one receipt.
    assert count_receipts(tenant_id=tenant_a, space_id=space_a1) == 1
    assert count_receipts(tenant_id=tenant_a, space_id=space_a2) == 1
    # No tenant-A row leaked into tenant-B's space.
    assert count_receipts(tenant_id=tenant_a, space_id=space_b1) == 0
    # No tenant-B row leaked into either tenant-A space.
    assert count_receipts(tenant_id=tenant_b, space_id=space_a1) == 0
    assert count_receipts(tenant_id=tenant_b, space_id=space_a2) == 0
    # Tenant A's grand total equals the sum of its two spaces (closed-set).
    total_a = count_receipts(tenant_id=tenant_a)
    sum_a = count_receipts(tenant_id=tenant_a, space_id=space_a1) + count_receipts(
        tenant_id=tenant_a, space_id=space_a2
    )
    assert total_a == sum_a, (total_a, sum_a)
