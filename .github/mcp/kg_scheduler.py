"""
Knowledge Graph Auto-Scheduler

Automatic indexing scheduler with:
- Full reindex mode: Index all ADRs, modules, contracts
- Watch mode: Monitor file changes and incremental updates
- Git hook integration: Auto-index on commit
- Performance monitoring: Track indexing time and stats

Usage:
    # Full reindex
    python kg_scheduler.py --full

    # Watch mode (development)
    python kg_scheduler.py --watch

    # Background scheduler (6h intervals)
    python kg_scheduler.py --daemon --interval 21600
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kg_indexers import ADRIndexer, ContractIndexer, ModuleIndexer
from kg_store import KGStore


class KGScheduler:
    """Automatic indexer scheduler"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            # Use repo-relative path, compatible with .vscode/mcp.json pattern
            repo_root = Path(__file__).resolve().parent.parent.parent
            db_path = str(repo_root / ".github" / "copilot-memories" / "memories.sqlite3")

        # Ensure directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self.db_path = db_path
        self.store = KGStore(db_path)

        # Indexers
        self.adr_indexer = ADRIndexer(self.store)
        self.module_indexer = ModuleIndexer(self.store)
        self.contract_indexer = ContractIndexer(self.store)

        # Paths to index
        self.adr_paths = ["docs/architecture/decisions"]
        self.module_paths = ["k0", "k1", ".github/mcp"]
        self.contract_paths = ["k0/contracts", "k1/contracts", ".github/contracts/kg"]

    def full_reindex(self) -> dict:
        """Perform full reindex of all sources"""
        print(
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting full reindex..."
        )
        start_time = time.time()

        total_stats = {
            "adrs": {"indexed": 0, "errors": 0, "skipped": 0},
            "modules": {"indexed": 0, "errors": 0, "skipped": 0},
            "contracts": {"indexed": 0, "errors": 0, "skipped": 0},
        }

        # Index ADRs
        print("Indexing ADRs...")
        for adr_path in self.adr_paths:
            if Path(adr_path).exists():
                stats = self.adr_indexer.index_all(adr_path)
                total_stats["adrs"]["indexed"] += stats["indexed"]
                total_stats["adrs"]["errors"] += stats["errors"]
                total_stats["adrs"]["skipped"] += stats.get("skipped", 0)

        # Index modules
        print("Indexing modules...")
        for module_path in self.module_paths:
            if Path(module_path).exists():
                stats = self.module_indexer.index_all(module_path)
                total_stats["modules"]["indexed"] += stats["indexed"]
                total_stats["modules"]["errors"] += stats["errors"]
                total_stats["modules"]["skipped"] += stats.get("skipped", 0)

        # Index contracts
        print("Indexing contracts...")
        for contract_path in self.contract_paths:
            if Path(contract_path).exists():
                stats = self.contract_indexer.index_all(contract_path)
                total_stats["contracts"]["indexed"] += stats["indexed"]
                total_stats["contracts"]["errors"] += stats["errors"]

        duration = time.time() - start_time

        # Get summary
        summary = self.store.get_graph_summary()

        print(
            f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Reindex complete in {duration:.2f}s"
        )
        print(
            f"ADRs: {total_stats['adrs']['indexed']} indexed, {total_stats['adrs']['errors']} errors"
        )
        print(
            f"Modules: {total_stats['modules']['indexed']} indexed, {total_stats['modules']['errors']} errors"
        )
        print(
            f"Contracts: {total_stats['contracts']['indexed']} indexed, {total_stats['contracts']['errors']} errors"
        )
        print(
            f"\nGraph: {summary['total_nodes']} nodes, {summary['total_edges']} edges"
        )
        print(f"Types: {summary['nodes_by_type']}")

        return {"stats": total_stats, "duration": duration, "summary": summary}

    def watch_mode(self, interval: int = 10):
        """Watch for file changes and auto-reindex"""
        print(
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting watch mode (checking every {interval}s)..."
        )
        print("Press Ctrl+C to stop")

        # Track last modified times
        last_check = {}

        def get_files_to_watch():
            files = []
            # ADRs
            for path_str in self.adr_paths:
                path = Path(path_str)
                if path.exists():
                    files.extend(path.glob("*.md"))
            # Modules
            for path_str in self.module_paths:
                path = Path(path_str)
                if path.exists():
                    files.extend(path.rglob("*.py"))
            # Contracts
            for path_str in self.contract_paths:
                path = Path(path_str)
                if path.exists():
                    files.extend(path.rglob("*.yaml"))
                    files.extend(path.rglob("*.json"))
            return files

        try:
            while True:
                changed = False

                for file_path in get_files_to_watch():
                    try:
                        mtime = file_path.stat().st_mtime
                        if (
                            str(file_path) not in last_check
                            or last_check[str(file_path)] < mtime
                        ):
                            last_check[str(file_path)] = mtime
                            changed = True
                            print(
                                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Detected change: {file_path}"
                            )
                    except Exception:
                        pass

                if changed:
                    print(
                        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Reindexing..."
                    )
                    self.full_reindex()

                time.sleep(interval)

        except KeyboardInterrupt:
            print(
                f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Watch mode stopped"
            )

    def daemon_mode(self, interval: int = 21600):
        """Run as background daemon with periodic reindexing"""
        print(
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting daemon mode (interval: {interval}s = {interval/3600:.1f}h)..."
        )

        try:
            while True:
                self.full_reindex()
                print(
                    f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Next reindex in {interval/3600:.1f} hours..."
                )
                time.sleep(interval)

        except KeyboardInterrupt:
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Daemon stopped")

    def close(self):
        """Close store"""
        self.store.close()


def main():
    parser = argparse.ArgumentParser(description="KG Auto-Scheduler")
    parser.add_argument("--full", action="store_true", help="Run full reindex once")
    parser.add_argument(
        "--watch", action="store_true", help="Watch for changes and auto-reindex"
    )
    parser.add_argument(
        "--daemon", action="store_true", help="Run as daemon with periodic reindexing"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=21600,
        help="Interval in seconds (default: 21600 = 6h)",
    )
    parser.add_argument(
        "--db",
        type=str,
        help="Database path (default: ~/.github/copilot-memories/kg.db)",
    )

    args = parser.parse_args()

    scheduler = KGScheduler(db_path=args.db)

    try:
        if args.watch:
            scheduler.watch_mode(interval=10)
        elif args.daemon:
            scheduler.daemon_mode(interval=args.interval)
        else:
            # Default: full reindex
            scheduler.full_reindex()
    finally:
        scheduler.close()


if __name__ == "__main__":
    main()
