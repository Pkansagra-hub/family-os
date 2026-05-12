# Live-System Test Harness (Epic 7.1)

Real-process integration harness for MS-7. Spawns honest subprocesses
against a running K0 — **no mocks**.

## Deployment shape

This harness is built for the canonical local dev shape:

* **K0** runs in **Docker** (kernel `localhost:8080`, postgres `5432`,
  pgbouncer `6432`, neo4j `7474`, prometheus `9090`, grafana `3000`,
  tempo `3200`, alertmanager `9093`).
* **K1** is spawned **locally** by the harness as a Python subprocess
  (`python -m k1.kernel.runner`).

K0 lifecycle is owned by Docker. The harness only **attaches** to it —
spawning K0 from Python (testcontainers path) is deferred.

## Usage

```python
import pytest
from tests.integration.harness import LiveSystem, single_father_layout

@pytest.mark.requires_live_k0
@pytest.mark.asyncio
async def test_my_journey():
    async with LiveSystem(family=single_father_layout()) as sys_:
        # K0 is the live Dockered kernel
        assert sys_.k0.healthz()["status"] == "ok"

        # Each K1 is a real subprocess
        k1 = sys_.k1s[0]
        assert k1.is_alive

        # In-process bridge runtime, K1 role, points at the live K0
        runtime = k1.bridge_runtime()
        # ... drive a memory.write.v1 / query.recall etc.
```

## Bring K0 up

```powershell
docker compose up -d
curl http://localhost:8080/healthz
```

If K0 is not reachable, tests marked `requires_live_k0` are
auto-skipped (see `conftest.py`).

## Environment variables

| Var             | Default                                              | Purpose                          |
| --------------- | ---------------------------------------------------- | -------------------------------- |
| `K0_BASE_URL`   | `http://127.0.0.1:8080`                              | K0 kernel HTTP base URL          |
| `K0_DB_URL`     | `postgresql://familyos:familyos@127.0.0.1:5432/...`  | K0 postgres DSN                  |

## Modules

| Module                  | Role                                                    |
| ----------------------- | ------------------------------------------------------- |
| `port_allocator.py`     | Ephemeral free-port allocation                          |
| `leak_detector.py`      | Track PIDs / ports / tempdirs; assert clean teardown    |
| `process_supervisor.py` | SIGTERM (Win: CTRL_BREAK_EVENT) → grace → SIGKILL       |
| `k0_handle.py`          | Attach-mode handle to the running Docker K0             |
| `k1_handle.py`          | Spawn one K1 subprocess + in-process bridge runtime     |
| `family_layout.py`      | `PersonSpec`, `DeviceSpec`, default layouts             |
| `live_system.py`        | `LiveSystem` async context manager (orchestrator)       |
| `conftest.py`           | `requires_live_k0` marker + `live_system` fixture       |
| `test_harness_self.py`  | Self-tests for the harness primitives                   |

## Deferred (future PRs)

* `spawn_k0=True` mode (provision K0 from Python via testcontainers).
* Per-test PG schema isolation (`AttachExistingK0Backend.create_schema`).
* Subprocess-driven K1 test API (so tests publish *through* the K1
  subprocess instead of via in-process bridge runtime).
* SQLite-backed fast loop for journey tests that don't need PG.
