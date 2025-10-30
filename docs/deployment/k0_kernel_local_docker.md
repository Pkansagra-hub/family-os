# Start k0 kernel locally (Docker Compose)

This guide runs the k0 kernel locally with Docker Compose using the deploy setup in `k0/deploy`.

## Prerequisites

- Windows with Docker Desktop
- PowerShell 5.1+ (or Windows Terminal with PowerShell profile)
- Cloned repo at `D:\familyos`

## 1) Build the local image

```powershell
# From repo root
cd D:\familyos
docker build -t k0-kernel-local:latest -f .\Dockerfile .
```

## 2) Prepare the compose directory

```powershell
# Navigate to the deploy folder
cd D:\familyos\k0\deploy

# Ensure folders/files expected by compose exist
mkdir data -Force
mkdir secrets -Force
mkdir env -Force
if (!(Test-Path env\k0.env)) { New-Item -Path env\k0.env -ItemType File | Out-Null }
```

## 3) Fix policy schema bind mount (one-time)

The compose file binds a policy schema from the repo root. Ensure it exists at:
`D:\familyos\contracts\policy\pep.schema.json`.

If missing, copy it from `k0/contracts/policy`:

```powershell
if (!(Test-Path D:\familyos\contracts\policy)) { New-Item -Path D:\familyos\contracts\policy -ItemType Directory -Force | Out-Null }
Copy-Item -Path D:\familyos\k0\contracts\policy\pep.schema.json -Destination D:\familyos\contracts\policy\pep.schema.json -Force
```

## 4) Bootstrap the SQLite database (optional but recommended)

Create and migrate the local database at `data\kernel.sqlite3`.

```powershell
$env:PYTHONPATH = "D:\familyos"
python - <<'PY'
from pathlib import Path
from k0.automation.migrate import apply_migrations

# Target DB file inside the deploy folder
db = Path(r"D:\familyos\k0\deploy\data\kernel.sqlite3")
results = apply_migrations(db)
print("Applied:", sum(1 for r in results if r.action=="applied"),
      "Skipped:", sum(1 for r in results if r.action=="skipped"),
      "Pending:", sum(1 for r in results if r.action=="pending"))
PY
```

## 5) Start the stack

```powershell
# From: D:\familyos\k0\deploy
# Start kernel + telemetry stack
docker compose -f .\docker-compose.yml -f .\local-single-node-telemetry.yml up -d
```

## 6) Verify health

```powershell
# Check container status
docker compose ps

# Health endpoints
try { iwr -UseBasicParsing http://localhost:8080/healthz -TimeoutSec 5 | Select-Object -ExpandProperty StatusCode } catch { $_.Exception.Message }
try { iwr -UseBasicParsing http://localhost:8080/readyz  -TimeoutSec 5 | Select-Object -ExpandProperty StatusCode } catch { $_.Exception.Message }
```

Expected: HTTP 200 for both endpoints and container status `(healthy)`.

## 7) Stop / clean up

```powershell
# Stop and remove containers
docker compose down

# Optional: also remove any named/anonymous volumes
# docker compose down -v
```

## Troubleshooting

- Port 8080 in use: change the host port in the compose file or stop the conflicting process.
- Missing `env/k0.env`: create the file (can be empty to start).
- Bind mount error for `pep.schema.json`: ensure the file exists at `D:\familyos\contracts\policy\pep.schema.json` (copy step above).
- Validate compose file:

```powershell
docker compose config
```

## Paths reference

- Compose files: `k0/deploy/docker-compose.yml`, `k0/deploy/local-single-node-telemetry.yml`
- DB file: `k0/deploy/data/kernel.sqlite3`
- Policy schema: `k0/contracts/policy/pep.schema.json` (copied to `contracts/policy/pep.schema.json` at repo root)
