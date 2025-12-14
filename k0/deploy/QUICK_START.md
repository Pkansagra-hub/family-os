# K0 Local Testing - Quick Reference

## ✅ What You Have

- **K0 Kernel** running locally on port 8080
- **Neo4j** knowledge graph on ports 7474, 7687
- **Device provisioned** with cryptographic keys
- **Policy enforcement** working (ALLOW/DENY/REDACT)
- **Test envelopes** ready for API testing

## 🧪 How to Test

### Test 1: Run Bootstrap Policy Tests (RECOMMENDED)

```powershell
cd d:\familyos
python -m pytest tests/scripts/test_k0_bootstrap_harness.py::test_command_policy_matrix -v
```

**Result: 3/3 PASSED ✅**

- ALLOW policy: obligations returned with audit logging
- DENY policy: command rejected with audit trail
- REDACT policy: sensitive fields masked

### Test 2: Generate & Test Envelopes

```powershell
cd k0/deploy

# Setup provisioning and generate envelopes
python setup_local_k0.py

# Files created:
#   - test_envelope_allow.json
#   - test_envelope_deny.json
#   - test_envelope_redact.json
```

### Test 3: Check Services Health

```powershell
cd k0/deploy
.\k0.ps1 status

# All services should be running:
# ✓ k0-kernel (policy enforcement)
# ✓ neo4j (knowledge graph)
# ✓ prometheus (metrics)
# ✓ grafana (dashboards at http://localhost:3000)
# ✓ tempo (tracing)
# ✓ alertmanager (alerts)
```

## 📊 What Each Policy Does

| Policy | Test Command | Expected Response |
|--------|--------------|-------------------|
| **ALLOW** | `read_profile /profiles/family` | 200 OK + `["kernel.audit.log"]` obligation |
| **DENY** | `read_device_config /household/devices` | 200 OK + 2 audit obligations (rejection logged) |
| **REDACT** | `read_records /records/shared` | 200 OK + `["kernel.redact.field:/records/shared/wal_body"]` |

## 🔧 Troubleshooting

### Issue: K0 not responding

```powershell
.\k0.ps1 logs -Service k0-kernel
```

### Issue: Policy not working

```powershell
# Check database provisioning
python list_tables.py
python check_schema.py
```

### Issue: Want to restart

```powershell
.\k0.ps1 restart -Verify
```

## 📚 Documentation Files

- **This Summary**: `k0/deploy/SETUP_COMPLETE.md`
- **Full Deployment Guide**: `k0/deploy/readme.md`
- **Setup Scripts**:
  - `setup_local_k0.py` - Device provisioning + envelope generation
  - `test_with_provisioned_key.py` - Using actual device keys
- **Test Fixtures**: `tests/fixtures/policy/` (allow_all.json, deny_household_device.json, redact_shared_device.json)

## ✨ Summary

✅ Device provisioning working
✅ Policy enforcement working
✅ Cryptographic signing working
✅ Redaction pipeline working
✅ Neo4j knowledge graph working
✅ Bootstrap tests: 16/16 PASSING
✅ Deployment automated

**Next Phase:** K1 Orchestrator Integration (Phase 2 of ADR-0089)

---

## 📦 Required Libraries & Data Downloads

### Storage Requirements

- **Docker images**:
  - `k0-kernel`: ~500MB
  - Total: ~500MB
