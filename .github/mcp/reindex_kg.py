"""
Reindex Knowledge Graph from scratch with embeddings
"""

from pathlib import Path

from kg_indexers import ADRIndexer, ContractIndexer, ModuleIndexer
from kg_store import KGStore


def main():
    # Use repository-relative path (same as kg_v2_server.py)
    repo_root = Path(__file__).resolve().parent.parent.parent
    db_path = repo_root / ".github" / "copilot-memories" / "kg.sqlite3"

    print(f"Knowledge Graph Database: {db_path}")
    print("=" * 80)

    # Create fresh store
    store = KGStore(str(db_path))

    # Index ADRs with embeddings
    print("\n📄 Indexing ADRs...")
    adr_indexer = ADRIndexer(store, generate_embeddings=True)
    adr_stats = adr_indexer.index_all(
        str(repo_root / "docs" / "architecture" / "decisions")
    )
    print(
        f"   ✅ Indexed: {adr_stats['indexed']}, Errors: {adr_stats['errors']}, Skipped: {adr_stats.get('skipped', 0)}"
    )

    # Index K0 modules with embeddings
    print("\n🐍 Indexing K0 modules...")
    k0_indexer = ModuleIndexer(store, repo_root=repo_root, generate_embeddings=True)
    k0_stats = k0_indexer.index_all(str(repo_root / "k0"))
    print(
        f"   ✅ Indexed: {k0_stats['indexed']}, Errors: {k0_stats['errors']}, Skipped: {k0_stats.get('skipped', 0)}"
    )

    # Index K1 modules with embeddings
    print("\n🐍 Indexing K1 modules...")
    k1_indexer = ModuleIndexer(store, repo_root=repo_root, generate_embeddings=True)
    k1_stats = k1_indexer.index_all(str(repo_root / "k1"))
    print(
        f"   ✅ Indexed: {k1_stats['indexed']}, Errors: {k1_stats['errors']}, Skipped: {k1_stats.get('skipped', 0)}"
    )

    # Index K0 contracts
    print("\n📋 Indexing K0 contracts...")
    k0_contract_indexer = ContractIndexer(store, generate_embeddings=True)
    k0_contract_stats = k0_contract_indexer.index_all(
        str(repo_root / "k0" / "contracts")
    )
    print(
        f"   ✅ Indexed: {k0_contract_stats['indexed']}, Errors: {k0_contract_stats['errors']}, Skipped: {k0_contract_stats.get('skipped', 0)}"
    )

    # Index K1 contracts
    print("\n📋 Indexing K1 contracts...")
    k1_contract_indexer = ContractIndexer(store, generate_embeddings=True)
    k1_contract_stats = k1_contract_indexer.index_all(
        str(repo_root / "k1" / "contracts")
    )
    print(
        f"   ✅ Indexed: {k1_contract_stats['indexed']}, Errors: {k1_contract_stats['errors']}, Skipped: {k1_contract_stats.get('skipped', 0)}"
    )

    # Summary
    print("\n" + "=" * 80)
    print("INDEXING COMPLETE")
    print("=" * 80)

    summary = store.get_graph_summary()
    print("\n📊 Graph Summary:")
    print(f"   Total Nodes: {summary['total_nodes']}")
    print(f"   Total Edges: {summary['total_edges']}")
    print("   Nodes by Type:")
    for node_type, count in summary["nodes_by_type"].items():
        print(f"      - {node_type}: {count}")
    print("   Edges by Relation:")
    for relation, count in summary["edges_by_relation"].items():
        print(f"      - {relation}: {count}")

    # Check embeddings
    print("\n🧠 Checking embeddings...")
    sample_adr = store.find_by_type("adr", limit=1)
    if sample_adr:
        node_id = sample_adr[0]["node_id"]
        embedding = store.get_embedding(node_id)
        if embedding:
            print(f"   ✅ Embeddings enabled: {len(embedding)} dimensions")
        else:
            print("   ⚠️  No embeddings found (sentence-transformers not installed?)")

    store.close()
    print(f"\n✅ Database ready: {db_path}")


if __name__ == "__main__":
    main()
