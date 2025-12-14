from __future__ import annotations

import base64
import copy
import hashlib
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from nacl.signing import SigningKey

import k0.policy.pep_syscall as pep_syscall
import scripts.k0_bootstrap_harness as harness
from k0.automation.migrate import apply_migrations

# TEST0001: Validating K0 bootstrap harness expectations end-to-end.
CONTRACT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "contracts" / "k0_bootstrap_harness.yml"
)
POLICY_FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "policy"
CANONICAL_BRIDGE_POLICY = (
    Path(__file__).resolve().parents[2] / "k0" / "contracts" / "policy" / "bridge_policy.yml"
)
# Secret corresponding to the ACTIVE verify key embedded in the test contract.
TEST_SECRET_BASE64 = "zd5M1iHPJjGaJnxt6UEtU7FxslBua_oL8V_cGR7X8gA"


@pytest.fixture
def policy_manifest_allow_all() -> Path:
    return POLICY_FIXTURES_DIR / "allow_all.json"


@pytest.fixture
def policy_manifest_deny_household() -> Path:
    return POLICY_FIXTURES_DIR / "deny_household_device.json"


@pytest.fixture
def policy_manifest_redact_shared() -> Path:
    return POLICY_FIXTURES_DIR / "redact_shared_device.json"


def _install_policy_manifest(
    target_dir: Path,
    *,
    manifest_fixture: Path,
    bridge_contract_fixture: Path | None = None,
) -> tuple[Path, Path]:
    target_dir.mkdir(parents=True, exist_ok=True)
    manifest_target = target_dir / manifest_fixture.name
    manifest_target.write_text(manifest_fixture.read_text(encoding="utf-8"), encoding="utf-8")

    if bridge_contract_fixture is None:
        contract_source = CANONICAL_BRIDGE_POLICY
    else:
        contract_source = bridge_contract_fixture
    contract_target = target_dir / contract_source.name
    contract_target.write_text(contract_source.read_text(encoding="utf-8"), encoding="utf-8")

    return manifest_target, contract_target


@contextmanager
def _bootstrap_runtime(
    tmp_path: Path,
    monkeypatch,
    *,
    manifest_fixture: Path | None = None,
    bridge_contract_fixture: Path | None = None,
):
    harness._import_kernel_dependencies()
    pep_syscall._cached_manifest.cache_clear()
    pep_syscall._clear_manifest_fingerprint_cache()
    contract = harness._load_contract(CONTRACT_PATH)

    overrides: dict[str, object] = {
        "database": {"path": str(tmp_path / "k0_runtime.sqlite3")},
        "telemetry": {"otlp_endpoint": None, "prometheus_enabled": True},
    }
    apply_migrations(Path(overrides["database"]["path"]))
    if manifest_fixture is not None:
        manifest_path, contract_path = _install_policy_manifest(
            tmp_path,
            manifest_fixture=manifest_fixture,
            bridge_contract_fixture=bridge_contract_fixture,
        )
        monkeypatch.setenv("K0_POLICY_MANIFEST_PATH", str(manifest_path))
        monkeypatch.setenv("K0_BRIDGE_POLICY_CONTRACT_PATH", str(contract_path))
    else:
        monkeypatch.delenv("K0_POLICY_MANIFEST_PATH", raising=False)
        monkeypatch.delenv("K0_BRIDGE_POLICY_CONTRACT_PATH", raising=False)

    settings = harness.KernelSettings.load(overrides=overrides)
    app = harness.create_app(settings=settings)

    harness._seed_schema(app, contract["seed"].get("schemas", []))
    harness._seed_devices(app, contract["seed"].get("devices", []))

    signing_key = SigningKey(harness._decode_base64url(TEST_SECRET_BASE64))

    try:
        with TestClient(app) as client:
            yield app, client, contract, signing_key
    finally:
        connections = getattr(app.state, "_sqlite_connections", [])
        for conn in connections:
            try:
                conn.close()
            except Exception:  # pragma: no cover - defensive cleanup
                pass

        if harness.shutdown_pool is not None:
            harness.shutdown_pool()
        pep_syscall._cached_manifest.cache_clear()
        pep_syscall._clear_manifest_fingerprint_cache()


@pytest.fixture
def bootstrap_context(tmp_path, monkeypatch):
    with _bootstrap_runtime(tmp_path, monkeypatch) as context:
        yield context


@contextmanager
def run_with_manifest(
    tmp_path: Path,
    monkeypatch,
    *,
    manifest_path: Path,
    bridge_contract_path: Path | None = None,
):
    with _bootstrap_runtime(
        tmp_path,
        monkeypatch,
        manifest_fixture=manifest_path,
        bridge_contract_fixture=bridge_contract_path,
    ) as context:
        yield context


def _post_command(client: TestClient, envelope: dict[str, object]):
    return client.post("/k0/command.submit", json=envelope)


def _make_signed_envelope(
    contract: dict[str, object],
    signing_key: SigningKey,
) -> dict[str, object]:
    request_cfg = contract["requests"]["command_submit"]
    fixture_path = Path(request_cfg["envelope_fixture"])
    if not fixture_path.is_absolute():
        fixture_path = harness.REPO_ROOT / fixture_path

    verify_key = None
    for device in contract["seed"].get("devices", []):
        if device.get("device_id") != "device-local-001":
            continue
        keys = device.get("keys", [])
        if keys:
            verify_key = str(keys[0]["verify_key"])
            break
    if verify_key is None:
        raise AssertionError("Verify key for device-local-001 not present in contract")

    envelope = harness._build_command_envelope(
        fixture_path,
        signing_key,
        verify_key,
    )
    return copy.deepcopy(envelope)


def _resign_envelope(envelope: dict[str, object], signing_key: SigningKey) -> None:
    message = harness.canonical_envelope(envelope)
    signature = signing_key.sign(message).signature
    envelope["sig"] = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")


def _query_scalar(sql: str) -> int:
    with harness.connection_scope() as conn:
        row = conn.execute(sql).fetchone()
    return int(row[0]) if row is not None else 0


def _metric_value(metrics_blob: str, metric: str, labels: dict[str, str]) -> float:
    label_text = ",".join(f'{key}="{value}"' for key, value in sorted(labels.items()))
    token = f"{metric}{{{label_text}}}"
    for line in metrics_blob.splitlines():
        if line.startswith(token):
            try:
                return float(line.split(" ", 1)[1])
            except (IndexError, ValueError):
                return 0.0
    return 0.0


def _compute_manifest_fingerprint(manifest_path: Path | None) -> str | None:
    if manifest_path is None or not manifest_path.exists():
        return None
    return hashlib.sha256(manifest_path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    ("manifest_fixture", "expectation"),
    [
        (
            "policy_manifest_allow_all",
            {
                "status": 200,
                "wal_delta": 1,
                "receipt_delta": 1,
                "obligation_delta": 0,
                "redacted": False,
                "obligations": ["kernel.audit.trace"],
            },
        ),
        (
            "policy_manifest_deny_household",
            {
                "status": 403,
                "wal_delta": 0,
                "receipt_delta": 0,
                "obligation_delta": 0,
                "redacted": False,
                "deny_reason": "ROLE_FORBIDDEN",
                "obligations": ["kernel.audit.log", "kernel.audit.log"],
            },
        ),
        (
            "policy_manifest_redact_shared",
            {
                "status": 200,
                "wal_delta": 1,
                "receipt_delta": 1,
                "obligation_delta": 1,
                "redacted": True,
                "obligations": ["kernel.audit.log", "kernel.redact.field"],
            },
        ),
    ],
)
def test_command_policy_matrix(
    manifest_fixture: str,
    expectation: dict[str, object],
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch,
):
    manifest_path: Path = request.getfixturevalue(manifest_fixture)

    with run_with_manifest(tmp_path, monkeypatch, manifest_path=manifest_path) as (
        app,
        client,
        contract,
        signing_key,
    ):
        _assert_migration_and_seed_ok(app, client)

        initial_wal = _query_scalar("SELECT COUNT(1) FROM st_wal")
        initial_receipts = _query_scalar("SELECT COUNT(1) FROM st_receipts")
        initial_obligations = _query_scalar("SELECT COUNT(1) FROM st_obligation_log")

        envelope = _make_signed_envelope(
            contract,
            signing_key,
        )

        emitter = app.state.observability_emitter
        emitter.clear()

        metrics_before = app.state.metrics_exporter.latest().decode("utf-8")
        decision_label = "allow" if expectation["status"] == 200 else "deny"
        decision_labels = {
            "decision": decision_label,
            "port": "command",
        }
        decision_before = _metric_value(
            metrics_before,
            "k0_kernel_admission_decisions_total",
            decision_labels,
        )

        obligation_counts = Counter(expectation.get("obligations", []))
        obligation_before: dict[str, float] = {}
        for obligation in obligation_counts:
            obligation_before[obligation] = _metric_value(
                metrics_before,
                "k0_kernel_k0_pep_obligations_total",
                {
                    "obligation": obligation,
                    "decision": decision_label,
                    "band": envelope["band"],
                },
            )

        response = _post_command(client, envelope)
        assert response.status_code == expectation["status"]

        wal_after = _query_scalar("SELECT COUNT(1) FROM st_wal")
        receipts_after = _query_scalar("SELECT COUNT(1) FROM st_receipts")
        obligations_after = _query_scalar("SELECT COUNT(1) FROM st_obligation_log")

        assert wal_after - initial_wal == expectation["wal_delta"]
        assert receipts_after - initial_receipts == expectation["receipt_delta"]
        assert obligations_after - initial_obligations == expectation["obligation_delta"]

        metrics_after = app.state.metrics_exporter.latest().decode("utf-8")
        decision_after = _metric_value(
            metrics_after,
            "k0_kernel_admission_decisions_total",
            decision_labels,
        )
        assert decision_after == pytest.approx(decision_before + 1.0)

        for obligation, before_value in obligation_before.items():
            expected_increment = obligation_counts[obligation]
            after_value = _metric_value(
                metrics_after,
                "k0_kernel_k0_pep_obligations_total",
                {
                    "obligation": obligation,
                    "decision": decision_label,
                    "band": envelope["band"],
                },
            )
            assert after_value == pytest.approx(before_value + float(expected_increment))

        decision_events = [
            event
            for event in app.state.observability_emitter.snapshot()
            if event.get("event") == "command_policy_decision"
        ]

        response_fingerprint: str | None = None

        if expectation["status"] == 200:
            payload = response.json()
            assert payload.get("receipt_id")
            assert payload.get("offsets")

            with harness.connection_scope() as conn:
                row = conn.execute(
                    "SELECT body, redacted_body_json FROM st_wal ORDER BY pos DESC LIMIT 1"
                ).fetchone()

            if expectation["redacted"]:
                assert row["redacted_body_json"]
                assert "***REDACTED***" in row["redacted_body_json"]
                body_json = row["body"].decode("utf-8") if row["body"] else ""
                assert "***REDACTED***" in body_json
            else:
                assert row["redacted_body_json"] is None
                body_json = row["body"].decode("utf-8") if row["body"] else ""
                assert "***REDACTED***" not in body_json

            response_fingerprint = payload.get("policy_manifest_fingerprint")

            assert sorted(payload.get("obligations", [])) == sorted(
                expectation.get("obligations", [])
            )

            if response_fingerprint:
                with harness.connection_scope() as conn:
                    receipt_row = conn.execute(
                        "SELECT manifest_fingerprint FROM st_receipts ORDER BY wal_pos DESC LIMIT 1"
                    ).fetchone()
                assert receipt_row and receipt_row["manifest_fingerprint"] == response_fingerprint
            else:
                with harness.connection_scope() as conn:
                    receipt_row = conn.execute(
                        "SELECT manifest_fingerprint FROM st_receipts ORDER BY wal_pos DESC LIMIT 1"
                    ).fetchone()
                assert receipt_row and receipt_row["manifest_fingerprint"] is None
        else:
            payload = response.json()
            error = payload.get("error", {})
            assert error.get("code") == "PEP_DENY"
            assert error.get("reason") == expectation.get("deny_reason")
            response_fingerprint = payload.get("policy_manifest_fingerprint")

        # obligations recorded when redaction required
        if expectation.get("obligation_delta", 0) > 0:
            with harness.connection_scope() as conn:
                row = conn.execute(
                    "SELECT details_json FROM st_obligation_log ORDER BY id DESC LIMIT 1"
                ).fetchone()
            assert row and "***REDACTED***" in row["details_json"]

        assert decision_events
        latest_event = decision_events[-1]
        assert latest_event.get("decision") == decision_label
        if expectation["status"] != 200:
            assert latest_event.get("deny_reason") == expectation.get("deny_reason")
        expected_obligations = expectation.get("obligations", [])
        assert sorted(latest_event.get("obligations", [])) == sorted(expected_obligations)
        event_fingerprint = latest_event.get("manifest_fingerprint")
        assert event_fingerprint == response_fingerprint
        if expectation["status"] == 200:
            assert latest_event.get("receipt_id") == payload.get("receipt_id")
            assert event_fingerprint == payload.get("policy_manifest_fingerprint")


def test_storage_contract_receipts_has_manifest_fingerprint():
    storage_sql = (
        Path(__file__).resolve().parents[2] / "k0" / "contracts" / "sql" / "storage.sql"
    ).read_text(encoding="utf-8")
    assert "manifest_fingerprint" in storage_sql


def test_policy_env_overrides(monkeypatch, tmp_path):
    harness._import_kernel_dependencies()

    manifest_path = tmp_path / "policy_manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    contract_path = tmp_path / "bridge_policy.yml"
    contract_path.write_text("meta: {}\n", encoding="utf-8")

    monkeypatch.setenv("K0_POLICY_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setenv("K0_BRIDGE_POLICY_CONTRACT_PATH", str(contract_path))

    overrides: dict[str, object] = {
        "database": {"path": str(tmp_path / "k0_policy.sqlite3")},
        "telemetry": {"otlp_endpoint": None, "prometheus_enabled": True},
    }

    settings = harness.KernelSettings.load(overrides=overrides)

    assert settings.policy.manifest_path == manifest_path
    assert settings.policy.bridge_policy_contract_path == contract_path


def _assert_migration_and_seed_ok(app, client):
    health = client.get("/healthz")
    ready = client.get("/readyz")
    metrics = client.get("/metrics")

    assert health.status_code == 200, "/healthz should report OK"
    assert ready.status_code == 200, "/readyz should report ready"
    assert metrics.status_code == 200, "/metrics should be exposed"
    assert b"k0_kernel_deployment_info" in metrics.content

    with harness.connection_scope() as conn:
        schema_rows = conn.execute(
            "SELECT COUNT(1) FROM schema_registry WHERE status='ACTIVE'"
        ).fetchone()
        assert schema_rows and schema_rows[0] > 0, "Seeded schema not registered as ACTIVE"

        device_rows = conn.execute("SELECT COUNT(1) FROM st_device_keys").fetchone()
        assert device_rows and device_rows[0] > 0, "Seeded device keys missing"


def test_command_submit_status_ok(bootstrap_context):
    app, client, contract, signing_key = bootstrap_context
    _assert_migration_and_seed_ok(app, client)

    result = harness._invoke_command(app, client, contract, signing_key)
    expect = contract["requests"]["command_submit"]["expect"]

    assert result["status"] == expect["status"]
    assert result["status_ok"] is True
    assert result["wal_ok"] is True
    assert result["receipt_ok"] is True
    assert result["metrics_ok"] is True


def test_command_policy_version_mismatch_returns_412(tmp_path: Path, monkeypatch):
    manifest_source = POLICY_FIXTURES_DIR / "allow_all.json"
    with run_with_manifest(
        tmp_path,
        monkeypatch,
        manifest_path=manifest_source,
    ) as (app, client, contract, signing_key):
        _assert_migration_and_seed_ok(app, client)

        envelope = _make_signed_envelope(contract, signing_key)
        envelope["manifest_fingerprint"] = "deadbeef"
        _resign_envelope(envelope, signing_key)

        response = _post_command(client, envelope)
        assert response.status_code == 412

        payload = response.json()
        error = payload.get("error", {})
        assert error.get("code") == "POLICY_VERSION_MISMATCH"
        assert "manifest" in (error.get("reason") or "").lower()


def test_command_policy_manifest_unavailable_returns_503(tmp_path: Path, monkeypatch):
    with _bootstrap_runtime(
        tmp_path,
        monkeypatch,
        manifest_fixture=POLICY_FIXTURES_DIR / "allow_all.json",
    ) as (_app, client, contract, signing_key):
        pep_syscall._cached_manifest.cache_clear()

        def _raise_policy_error() -> dict[str, object]:
            raise pep_syscall.PolicyConfigurationError("manifest unavailable")

        monkeypatch.setattr(pep_syscall, "_load_policy_manifest", _raise_policy_error)

        envelope = _make_signed_envelope(contract, signing_key)

        response = _post_command(client, envelope)
        assert response.status_code == 503

        payload = response.json()
        error = payload.get("error", {})
        assert error.get("code") == "POLICY_UNAVAILABLE"
        assert "manifest" in (error.get("reason") or "").lower()


def test_command_submit_rejects_payload_hash_mismatch(bootstrap_context):
    _app, client, contract, signing_key = bootstrap_context
    envelope = _make_signed_envelope(contract, signing_key)
    envelope["body"]["payload"]["value"] = 999  # mutate body without updating hash/signature

    response = _post_command(client, envelope)

    assert response.status_code == 400
    payload = response.json()
    error = payload.get("error", {})
    assert error.get("code") == "REJECTED_KERNEL_GATE"
    assert "PAYLOAD_HASH_MISMATCH" in (error.get("reason") or "")


def test_command_submit_rejects_unknown_schema(bootstrap_context):
    _app, client, contract, signing_key = bootstrap_context
    envelope = _make_signed_envelope(contract, signing_key)
    envelope["schema_uri"] = "schema://nonexistent"

    response = _post_command(client, envelope)

    assert response.status_code == 400
    payload = response.json()
    error = payload.get("error", {})
    assert error.get("code") == "REJECTED_KERNEL_GATE"
    assert "SCHEMA_NOT_ACTIVE" in (error.get("reason") or "")


def test_command_submit_rejects_blocked_schema(bootstrap_context):
    app, client, contract, signing_key = bootstrap_context
    with harness.connection_scope() as conn:
        conn.execute(
            "UPDATE schema_registry SET status='BLOCKED' WHERE schema_uri=? AND version=?",
            (
                contract["seed"]["schemas"][0]["uri"],
                contract["seed"]["schemas"][0]["version"],
            ),
        )
        conn.commit()
    app.state.schema_registry.clear_cache()

    envelope = _make_signed_envelope(contract, signing_key)
    response = _post_command(client, envelope)

    assert response.status_code == 400
    payload = response.json()
    error = payload.get("error", {})
    assert error.get("code") == "REJECTED_KERNEL_GATE"
    assert "SCHEMA_BLOCKED" in (error.get("reason") or "")


def test_command_submit_rejects_unprovisioned_device(bootstrap_context):
    _app, client, contract, signing_key = bootstrap_context
    envelope = _make_signed_envelope(contract, signing_key)
    envelope["device_id"] = "device-attacker"

    response = _post_command(client, envelope)

    assert response.status_code == 400
    payload = response.json()
    error = payload.get("error", {})
    assert error.get("code") == "REJECTED_KERNEL_GATE"
    assert error.get("reason") == "DEVICE_NOT_PROVISIONED"


def test_command_submit_idempotency_duplicate_reuses_ledger_entry(bootstrap_context):
    _app, client, contract, signing_key = bootstrap_context
    envelope = _make_signed_envelope(contract, signing_key)

    initial_wal = _query_scalar("SELECT COUNT(1) FROM st_wal")
    initial_idem = _query_scalar("SELECT COUNT(1) FROM idem_ledger")

    first = _post_command(client, copy.deepcopy(envelope))
    assert first.status_code == 200

    wal_after_first = _query_scalar("SELECT COUNT(1) FROM st_wal")
    idem_after_first = _query_scalar("SELECT COUNT(1) FROM idem_ledger")
    assert wal_after_first == initial_wal + 1
    assert idem_after_first == initial_idem + 1

    second = _post_command(client, copy.deepcopy(envelope))
    assert second.status_code == 409
    duplicate_payload = second.json()
    assert duplicate_payload.get("idem_key")
    assert duplicate_payload.get("receipt_id")

    wal_after_second = _query_scalar("SELECT COUNT(1) FROM st_wal")
    idem_after_second = _query_scalar("SELECT COUNT(1) FROM idem_ledger")
    assert wal_after_second == wal_after_first
    assert idem_after_second == idem_after_first


def test_query_recall_status_ok(bootstrap_context):
    _app, client, contract, _signing_key = bootstrap_context

    result = harness._invoke_query(client, contract)
    expect = contract["requests"]["query_recall"]["expect"]

    assert result["status"] == expect["status"]
    assert result["status_ok"] is True
    assert result["admission_logged"] is True
    assert isinstance(result["payload"], dict)
    selector = result["payload"]["bundle"]["selectors"][0]
    assert selector["selector"]["topic"] == "memory.delta"


def test_driver_handshake_status_ok(bootstrap_context):
    _app, client, contract, _signing_key = bootstrap_context

    result = harness._invoke_driver_handshake(client, contract)
    expect = contract["requests"]["driver_handshake"]["expect"]

    assert result["status"] == expect["status"]
    assert result["status_ok"] is True
    payload = result["payload"]
    assert isinstance(payload, dict)
    assert payload.get("session_id")
    assert payload.get("capabilities") == ["wal"]


def test_sse_subscribe_status_ok(bootstrap_context):
    _app, client, contract, _signing_key = bootstrap_context

    result = harness._invoke_sse(client, contract)
    expect = contract["requests"]["sse_subscribe"]["expect"]

    assert result["status"] == expect["status"]
    assert result["status_ok"] is True
