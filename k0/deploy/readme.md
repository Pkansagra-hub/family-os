# How to deploy k0 kernel

Run from d:/familyos/k0/deploy:

```powershell
powershell -ExecutionPolicy Bypass -File .\k0.ps1 up -Verify -WaitSeconds 10
```

Notes:

- -Verify waits for services to become healthy
- -WaitSeconds sets readiness timeout (e.g., 10)
- If scripts are blocked, run: `Set-ExecutionPolicy -Scope Process Bypass -Force`
