"""Journey 3 — One person, multiple devices.

Story: A user writes from their phone in the morning and from their
laptop at night. Both devices are bound to the same ``(tenant, space)``,
both writes commit, and both device IDs are visible in ``st_receipts``
for that space — proving K0's per-device 1:1 binding does *not* prevent
multiple devices from sharing one space (the constraint is per-device,
not per-space).

This is the inverse of Journey 2: same space, different devices.
"""

from __future__ import annotations

import uuid

import pytest

from tests.integration.harness.family_layout import (
    DeviceSpec,
    FamilyLayout,
    PersonSpec,
)
from tests.integration.harness.k0_observer import (
    count_receipts,
    list_receipt_device_ids,
)
from tests.integration.harness.live_system import LiveSystem


def _hex(n: int = 8) -> str:
    return uuid.uuid4().hex[:n]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_journey_user_writes_from_phone_and_laptop() -> None:
    person_id = f"user-{_hex()}"
    fam = FamilyLayout(
        family_id=f"fam-multi-{_hex()}",
        people=(
            PersonSpec(
                person_id=person_id,
                role="single",
                devices=(
                    DeviceSpec(device_id=f"phone-{_hex()}", label="phone"),
                    DeviceSpec(device_id=f"laptop-{_hex()}", label="laptop"),
                ),
            ),
        ),
    )
    phone_id = fam.people[0].devices[0].device_id
    laptop_id = fam.people[0].devices[1].device_id
    baseline = count_receipts(tenant_id=fam.family_id, space_id=fam.family_id)

    async with LiveSystem(family=fam) as live:
        assert len(live.k1s) == 2  # one K1 per device

        # Morning: phone write.
        phone_k1 = next(k for k in live.k1s if k.device_id == phone_id)
        morning = await phone_k1.publish_memory_write_v1_native(
            text="Coffee with Sam at 9am",
            topics=["calendar", "morning"],
        )
        assert morning["http_status"] == 200, morning

        # Evening: laptop write.
        laptop_k1 = next(k for k in live.k1s if k.device_id == laptop_id)
        evening = await laptop_k1.publish_memory_write_v1_native(
            text="Wrapped up the proposal — sending tomorrow",
            topics=["work", "evening"],
        )
        assert evening["http_status"] == 200, evening

    # Two writes, two receipts in the shared space.
    assert count_receipts(tenant_id=fam.family_id, space_id=fam.family_id) - baseline == 2

    devices_seen = list_receipt_device_ids(space_id=fam.family_id)
    assert phone_id in devices_seen
    assert laptop_id in devices_seen
