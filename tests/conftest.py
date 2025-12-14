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
