# Chat Experience PoC - Run Scripts
# PowerShell equivalents for Makefile targets

param(
    [Parameter(Position = 0)]
    [string]$Command = "help"
)

Write-Host "Chat Experience PoC - Available Commands" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  run:poc      - Start mocks + run PoC (Mock K0 :8003, Mock MCP :8001)" -ForegroundColor Green
Write-Host "  test:fast    - Run unit tests only (fast, isolated)" -ForegroundColor Green
Write-Host "  test:int     - Run integration tests (requires mocks)" -ForegroundColor Green
Write-Host "  test:all     - Run all tests (unit + integration + performance)" -ForegroundColor Green
Write-Host "  clean        - Clean up generated files and caches" -ForegroundColor Green
Write-Host ""
Write-Host "Usage: .\run.ps1 <command>" -ForegroundColor Yellow
Write-Host "Example: .\run.ps1 test:fast" -ForegroundColor Yellow

switch ($Command) {
    "run:poc" {
        Write-Host "Starting Mock K0 on :8003..." -ForegroundColor Cyan
        Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd $PSScriptRoot; python -m tests.mocks.mock_k0_server"
        Start-Sleep -Seconds 2

        Write-Host "Starting Mock MCP on :8001..." -ForegroundColor Cyan
        Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd $PSScriptRoot; python -m tests.mocks.mock_mcp_server"
        Start-Sleep -Seconds 2

        Write-Host "Running PoC main.py..." -ForegroundColor Cyan
        python main.py --component all --log-level INFO
    }
    "test:fast" {
        Write-Host "Running unit tests..." -ForegroundColor Cyan
        python -m pytest tests/ -v --tb=short -m "not integration" --ignore=tests/performance/
    }
    "test:int" {
        Write-Host "Running integration tests..." -ForegroundColor Cyan
        python -m pytest tests/ -v --tb=short -m integration
    }
    "test:all" {
        Write-Host "Running all tests..." -ForegroundColor Cyan
        python -m pytest tests/ -v --tb=short
    }
    "clean" {
        Write-Host "Cleaning up..." -ForegroundColor Cyan
        Get-ChildItem -Recurse -Include __pycache__, .pytest_cache, *.pyc | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "Clean complete." -ForegroundColor Green
    }
    default {
        # Help already displayed at top
    }
}
