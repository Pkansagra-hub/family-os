"""Family layout dataclasses for the live-system harness.

Encodes the per-test "who's in this family" so the harness can spawn
the right number of K1 processes with the right person/device IDs.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


def _hex(n: int = 8) -> str:
    return uuid.uuid4().hex[:n]


@dataclass(frozen=True)
class DeviceSpec:
    device_id: str
    label: str = "phone"


@dataclass(frozen=True)
class PersonSpec:
    person_id: str
    role: str  # "father" | "mother" | "kid" | "single" | ...
    devices: tuple[DeviceSpec, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FamilyLayout:
    """A family's people + devices, used to drive K1 spawn count."""

    family_id: str
    people: tuple[PersonSpec, ...]

    @property
    def total_devices(self) -> int:
        return sum(len(p.devices) for p in self.people)


def default_father_mother_kid_layout(*, family_id: str | None = None) -> FamilyLayout:
    fid = family_id or f"fam-{_hex()}"
    return FamilyLayout(
        family_id=fid,
        people=(
            PersonSpec(
                person_id=f"father-{_hex()}",
                role="father",
                devices=(DeviceSpec(device_id=f"dev-{_hex()}", label="phone"),),
            ),
            PersonSpec(
                person_id=f"mother-{_hex()}",
                role="mother",
                devices=(DeviceSpec(device_id=f"dev-{_hex()}", label="phone"),),
            ),
            PersonSpec(
                person_id=f"kid-{_hex()}",
                role="kid",
                devices=(DeviceSpec(device_id=f"dev-{_hex()}", label="tablet"),),
            ),
        ),
    )


def single_father_layout(*, family_id: str | None = None) -> FamilyLayout:
    fid = family_id or f"fam-{_hex()}"
    return FamilyLayout(
        family_id=fid,
        people=(
            PersonSpec(
                person_id=f"father-{_hex()}",
                role="single",
                devices=(DeviceSpec(device_id=f"dev-{_hex()}", label="phone"),),
            ),
        ),
    )
