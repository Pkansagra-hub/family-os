import logging
import sys
from pathlib import Path

# Pretty, fast tracebacks (no locals to keep it clean)
try:
    from rich.console import Console
    from rich.logging import RichHandler
    from rich.traceback import install as rich_traceback_install

    rich_traceback_install(show_locals=False, width=120, word_wrap=False)

    # Nicer logging in tests
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, tracebacks_show_locals=False)],
    )
    _console = Console()
except ImportError:
    # Graceful fallback if Rich is not installed
    logging.basicConfig(level=logging.INFO)
    _console = None


# Ignore archived and deprecated tests (PostgreSQL migration cleanup)
collect_ignore_glob = [
    "**/archived/**",
]

# Specific files to ignore (import errors due to deprecated modules)
collect_ignore = [
    "k0/automation/test_migrate.py",
    "k0/test_accuracy_benchmark.py",
    "k0/test_golden_dataset.py",
    "scripts/test_k0_bootstrap_harness.py",
    "performance/test_pem_latency.py",
    "integration/test_v1_privacy_performance_pipeline.py",
    "k0/integration/test_cli_integration.py",
    "k0/integration/test_hmac_idempotency.py",
    "k0/integration/test_scheduler_fairness.py",
    "k0/integration/test_v1_performance.py",
    # PostgreSQL migration - SQLite-based tests to be migrated
    "integration/p02/test_p02_pipeline_e2e.py",
    "integration/test_p02_inline_embedding.py",
    "k0/integration/test_crdt_merge_logging.py",
    "k0/integration/test_outbox_exponential_backoff.py",
    "k0/integration/test_retention_policies.py",
    "k0/integration/test_schema_cache_thread_safety.py",
    "k0/modules/builders/test_embedding_queue_write.py",
    "k0/modules/builders/test_hipp_events_row.py",
    "k0/modules/context/test_ingress_classify.py",
    "k0/modules/context/test_spatial_minimal.py",
    "k0/modules/core/test_event_emitter.py",
    "k0/modules/embedding/test_extract_from_cache.py",
    "k0/modules/embedding/test_faiss_indexer.py",
    "k0/modules/hippocampus/test_semantic_project_full.py",
    "k0/policy/test_retention_enforcer.py",
    "k0/receipts/test_receipt_audit_fields.py",
    "k0/runtime/test_p02_parallel_execution.py",
    "k0/runtime/test_schemas_trigger.py",
]


def ensure_workspace_on_path() -> None:
    root = Path(__file__).resolve().parents[1]
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


ensure_workspace_on_path()


def pytest_report_header(config):
    """Display a beautiful header at the top of each test run."""
    return "🧪✨ K1/K0 Test Run — colorful, fast, and readable"


def pytest_collection_modifyitems(config, items):
    """Add visual markers to test names based on markers."""
    for item in items:
        if "integration" in item.keywords:
            item.user_properties.append(("category", "integration"))
        elif "unit" in item.keywords:
            item.user_properties.append(("category", "unit"))
        elif "performance" in item.keywords:
            item.user_properties.append(("category", "performance"))


def pytest_configure(config):
    """Configure pytest-emoji marks for test outcomes."""
    # Set emoji outcomes if pytest-emoji is available
    try:
        config._inicache.setdefault("emoji_passed", "✅")
        config._inicache.setdefault("emoji_failed", "❌")
        config._inicache.setdefault("emoji_skipped", "⏭️")
        config._inicache.setdefault("emoji_error", "💥")
        config._inicache.setdefault("emoji_xfailed", "🟡")
        config._inicache.setdefault("emoji_xpassed", "🟢")
    except (AttributeError, TypeError):
        # Graceful fallback if pytest-emoji config is unavailable
        pass
