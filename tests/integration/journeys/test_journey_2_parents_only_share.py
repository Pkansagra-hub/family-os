"""Journey 2 — Family member shares to a parents-only sub-space.

Story: A parent writes a sensitive note to ``{family}/parents_only`` while
that same parent's other device writes a casual note to the shared
``{family}/family`` space. After both commit, ``st_receipts`` shows
the parents-only row only in its own space (not in ``/family``), and a
recall against ``{family}/family`` is admitted but does not bleed in
parents-only counts.

This pins K0's ``SPACE_TENANT_MISMATCH`` behavior at the journey level:
each scope band must be a separately provisioned device.
"""

from __future__ import annotations

import uuid

import pytest

from tests.integration.harness.device_provisioner import provision_extra_device
from tests.integration.harness.envelope_publisher import publish_memory_write_native
from tests.integration.harness.k0_observer import (
    count_receipts,
    list_receipt_device_ids,
)
from tests.integration.harness.k0_query_client import query_recall

_K0_BASE_URL = "http://127.0.0.1:8080"


def _hex(n: int = 8) -> str:
    return uuid.uuid4().hex[:n]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_journey_parent_shares_to_parents_only_subspace() -> None:
    tenant_id = f"fam-parents-{_hex()}"
    parents_space = f"{tenant_id}/parents_only"
    family_space = f"{tenant_id}/family"

    parents_dev = provision_extra_device(
        device_id=f"dev-parents-{_hex()}",
        tenant_id=tenant_id,
        space_id=parents_space,
    )
    family_dev = provision_extra_device(
        device_id=f"dev-family-{_hex()}",
        tenant_id=tenant_id,
        space_id=family_space,
    )

    parents_baseline = count_receipts(space_id=parents_space)
    family_baseline = count_receipts(space_id=family_space)

    # Parent writes a private note (parents_only).
    r_parents = await publish_memory_write_native(
        k0_base_url=_K0_BASE_URL,
        tenant_id=tenant_id,
        space_id=parents_space,
        device_id=parents_dev.device_id,
        actor=f"parent-{_hex()}",
        signing_seed=parents_dev.ed25519_seed,
        text="Reminder: pay credit card before due date.",
        topics=["finance", "private"],
    )
    assert r_parents["http_status"] == 200, r_parents

    # Same parent writes a shared family note.
    r_family = await publish_memory_write_native(
        k0_base_url=_K0_BASE_URL,
        tenant_id=tenant_id,
        space_id=family_space,
        device_id=family_dev.device_id,
        actor=f"parent-{_hex()}",
        signing_seed=family_dev.ed25519_seed,
        text="Pizza night Friday — kids voted!",
        topics=["family", "events"],
    )
    assert r_family["http_status"] == 200, r_family

    # Each space gained exactly one row, and its row's device is its own.
    assert count_receipts(space_id=parents_space) - parents_baseline == 1
    assert count_receipts(space_id=family_space) - family_baseline == 1

    parents_devices = list_receipt_device_ids(space_id=parents_space)
    family_devices = list_receipt_device_ids(space_id=family_space)
    assert parents_dev.device_id in parents_devices
    assert family_dev.device_id in family_devices
    assert family_dev.device_id not in parents_devices, parents_devices
    assert parents_dev.device_id not in family_devices, family_devices

    # Recall against the family space is admitted (no role escalation needed).
    recall_family = await query_recall(
        k0_base_url=_K0_BASE_URL,
        tenant_id=tenant_id,
        space_id=family_space,
    )
    assert recall_family["http_status"] == 200, recall_family
    assert recall_family["body"]["trace"]["policy"]["decision"] == "ADMIT"

    # Cross-space negative: parents row never surfaces in family-space.
    assert (
        count_receipts(tenant_id=tenant_id, space_id=family_space, device_id=parents_dev.device_id)
        == 0
    )
