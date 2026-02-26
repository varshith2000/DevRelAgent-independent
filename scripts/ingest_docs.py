"""
Document Ingestion Script

Ingest documents into the vector index for semantic search.

Supports: PDF, Word, Markdown, Text, OpenAPI/Swagger

Usage:
    # Index all files in a directory
    python scripts/ingest_docs.py --source data/docs/

    # Index a specific file
    python scripts/ingest_docs.py --source data/docs/api_guide.pdf

    # Index with custom patterns
    python scripts/ingest_docs.py --source data/docs/ --patterns "*.pdf" "*.md"

    # Show index statistics
    python scripts/ingest_docs.py --stats
"""

import sys
import argparse
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "backend"))

from tools.doc_search.rag_tool import RagTool


def main():
    parser = argparse.ArgumentParser(
        description="Ingest documents into vector index",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("--source", help="Path to file or directory to index")
    parser.add_argument("--patterns", nargs="+", help="Glob patterns to filter files")
    parser.add_argument("--index-name", default="docs", help="Name of the index")
    parser.add_argument("--stats", action="store_true", help="Show index statistics")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild index from scratch")

    args = parser.parse_args()

    # Initialize RAG tool
    print(f"🔍 Initializing RAG tool (index: {args.index_name})...")
    rag = RagTool(index_name=args.index_name)

    # Show stats and exit
    if args.stats:
        stats = rag.get_stats()
        print("\n📊 Index Statistics:")
        print(f"  Total Chunks: {stats['total_chunks']}")
        print(f"  Source Types: {stats['source_types']}")
        print(f"  Is Ready: {stats['is_ready']}")
        return

    # Rebuild index
    if args.rebuild:
        print("🔄 Rebuilding index...")
        if rag.rebuild_index():
            print("✓ Index rebuilt successfully")
        else:
            print("✗ Failed to rebuild index")
        return

    # Validate source
    if not args.source:
        parser.error("--source is required (unless using --stats or --rebuild)")

    source_path = Path(args.source)

    # Index a single file
    if source_path.is_file():
        print(f"📄 Indexing file: {args.source}")
        added = rag.ingest_file(str(source_path))
        print(f"✓ Added {added} chunks to index")
        rag.vector_store.save()
        return

    # Index a directory
    if source_path.is_dir():
        print(f"📁 Indexing directory: {args.source}")
        counts = rag.ingest_directory(
            str(source_path),
            recursive=True,
            patterns=args.patterns
        )

        print("\n✓ Indexing complete:")
        total = 0
        for ext, count in counts.items():
            print(f"  {ext}: {count} chunks")
            total += count
        print(f"  Total: {total} chunks")

        rag.vector_store.save()

        # Show final stats
        stats = rag.get_stats()
        print(f"\n📊 Final Index Stats: {stats['total_chunks']} total chunks")
        return

    print(f"✗ Not a valid file or directory: {args.source}")


if __name__ == "__main__":
    main()
