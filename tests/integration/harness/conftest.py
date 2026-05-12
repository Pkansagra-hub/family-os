"""Pytest conftest for the live-system harness.

Provides:

* ``requires_live_k0`` marker — skips a test if the running K0 is not
  reachable on ``K0_BASE_URL`` (default ``http://127.0.0.1:8080``).
* ``live_k0`` fixture — yields an attached :class:`K0Handle`.
* ``live_system`` fixture — yields a default :class:`LiveSystem` with
  the father/mother/kid family layout.
"""

from __future__ import annotations

import os

import httpx
import pytest
import pytest_asyncio

from .k0_handle import DEFAULT_K0_BASE_URL, K0Handle
from .live_system import LiveSystem


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "requires_live_k0: skip if the Docker K0 stack is not reachable",
    )


def _k0_reachable(base_url: str) -> bool:
    try:
        with httpx.Client(timeout=1.0) as client:
            r = client.get(f"{base_url}/healthz")
            return r.status_code == 200
    except httpx.HTTPError:
        return False


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    base_url = os.environ.get("K0_BASE_URL", DEFAULT_K0_BASE_URL)
    if _k0_reachable(base_url):
        return
    skip_marker = pytest.mark.skip(
        reason=(
            f"Live K0 not reachable at {base_url}. Bring up the Docker stack "
            "(docker compose up -d) or set K0_BASE_URL."
        )
    )
    for item in items:
        if "requires_live_k0" in item.keywords:
            item.add_marker(skip_marker)


@pytest.fixture
def live_k0() -> K0Handle:
    return K0Handle.attach()


@pytest_asyncio.fixture
async def live_system():
    async with LiveSystem() as system:
        yield system
