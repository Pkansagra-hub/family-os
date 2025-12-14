# Chat Experience PoC - Makefile
# Fast, deterministic, no-persistence K0 PoC
# See: docs/plans/chat_experience_poc_plan.md

.PHONY: help run:poc test:fast test:int test:all clean

help: ## Show this help message
	@echo "Chat Experience PoC - Available Commands"
	@echo "========================================"
	@grep -E '^[a-zA-Z_:-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

run:poc: ## Start mocks (Mock K0 :8003, Mock MCP :8001) + run PoC
	@echo "Starting Mock K0 on :8003..."
	@powershell -Command "Start-Process powershell -ArgumentList '-NoExit', '-Command', 'cd $(CURDIR); python -m tests.mocks.mock_k0_server' -WindowStyle Normal"
	@timeout /t 2 /nobreak >nul
	@echo "Starting Mock MCP on :8001..."
	@powershell -Command "Start-Process powershell -ArgumentList '-NoExit', '-Command', 'cd $(CURDIR); python -m tests.mocks.mock_mcp_server' -WindowStyle Normal"
	@timeout /t 2 /nobreak >nul
	@echo "Running PoC main.py..."
	@python main.py --component all --log-level INFO

test:fast: ## Run unit tests only (fast, isolated, no network)
	@echo "Running unit tests..."
	@python -m pytest tests/ -v --tb=short -m "not integration" --ignore=tests/performance/

test:int: ## Run integration tests (requires mocks running)
	@echo "Running integration tests..."
	@python -m pytest tests/ -v --tb=short -m integration

test:all: ## Run all tests (unit + integration + performance)
	@echo "Running all tests..."
	@python -m pytest tests/ -v --tb=short

clean: ## Clean up generated files and caches
	@echo "Cleaning up..."
	@powershell -Command "Remove-Item -Recurse -Force __pycache__, .pytest_cache, *.pyc -ErrorAction SilentlyContinue"
	@echo "Clean complete."
