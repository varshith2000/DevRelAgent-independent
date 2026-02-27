"""
Test Script for Web Scraping Indexing

Demonstrates web page scraping and indexing with the WebIndexer.

Usage:
    # Scrape a single URL
    python scripts/test_web_scraping.py --url https://example.com/article

    # Scrape multiple URLs
    python scripts/test_web_scraping.py --urls https://example.com/page1 https://example.com/page2

    # Scrape from a file containing URLs
    python scripts/test_web_scraping.py --file urls.txt

    # Search indexed web pages
    python scripts/test_web_scraping.py --search "machine learning"
"""

import sys
import argparse
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "backend"))

from tools.doc_search import WebIndexer, RagTool


def scrape_single_url(url: str):
    """Test scraping a single URL."""
    print(f"🌐 Scraping: {url}")

    indexer = WebIndexer()

    try:
        chunks = indexer.ingest(url)

        if chunks:
            print(f"\n✓ Successfully scraped {len(chunks)} chunks")

            # Show metadata from first chunk
            metadata = chunks[0].metadata
            print(f"\n  Metadata:")
            print(f"    Title: {metadata.get('title', 'N/A')[:80]}...")
            print(f"    URL: {metadata.get('url', 'N/A')}")
            print(f"    Domain: {metadata.get('domain', 'N/A')}")
            print(f"    Author: {metadata.get('author', 'N/A')}")
            print(f"    Date: {metadata.get('date', 'N/A')}")

            print(f"\n  Content Preview:")
            print(f"    {chunks[0].content[:200]}...")

            return True
        else:
            print("✗ No content extracted")
            return False

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def index_urls(urls: list, index_name: str = "web_pages"):
    """Index multiple URLs."""
    print(f"🌐 Indexing {len(urls)} web pages...")

    rag = RagTool(index_name=index_name)

    if not rag.web_indexer:
        print("✗ WebIndexer not available")
        print("  Install with: pip install trafilatura requests beautifulsoup4")
        return False

    success_count = 0
    results_by_domain = {}

    for i, url in enumerate(urls, 1):
        print(f"\n[{i}/{len(urls)}] {url[:60]}...")
        try:
            added = rag.ingest_url(url)
            if added > 0:
                success_count += 1

                # Track by domain
                from urllib.parse import urlparse
                domain = urlparse(url).netloc
                results_by_domain[domain] = results_by_domain.get(domain, 0) + added

                print(f"  ✓ Indexed ({added} chunks)")
            else:
                print(f"  ✗ Failed")
        except Exception as e:
            print(f"  ✗ Error: {e}")

    # Show stats
    print(f"\n📊 Results:")
    print(f"  Successfully indexed: {success_count}/{len(urls)}")

    if results_by_domain:
        print(f"\n  By domain:")
        for domain, count in results_by_domain.items():
            print(f"    {domain}: {count} chunks")

    stats = rag.get_stats()
    print(f"\n  Total chunks in index: {stats['total_chunks']}")
    print(f"  Source types: {stats['source_types']}")

    return success_count > 0


def search_web_pages(query: str, index_name: str = "web_pages"):
    """Search indexed web pages."""
    print(f"🔍 Searching for: {query}")

    rag = RagTool(index_name=index_name)

    if not rag.vector_store.is_ready:
        print("✗ Index not ready. Please index pages first.")
        return False

    results = rag.search(query, top_k=5, source_type="web")

    if not results:
        print("No results found")
        return False

    print(f"\nFound {len(results)} results:\n")
    for i, result in enumerate(results, 1):
        chunk = result.chunk
        metadata = chunk.metadata

        print(f"[{i}] {metadata.get('title', 'Unknown Title')}")
        print(f"    URL: {metadata.get('url', 'N/A')}")
        print(f"    Domain: {metadata.get('domain', 'N/A')}")
        print(f"    Score: {result.score:.4f}")
        print(f"    Preview: {chunk.content[:150]}...")
        print()

    return True


def load_urls_from_file(file_path: str) -> list:
    """Load URLs from a text file (one per line)."""
    path = Path(file_path)
    if not path.exists():
        print(f"✗ File not found: {file_path}")
        return []

    urls = []
    with open(path, 'r') as f:
        for line in f:
            url = line.strip()
            if url and url.startswith(("http://", "https://")):
                urls.append(url)
            elif url and not url.startswith("#"):
                print(f"  ⚠️  Skipped invalid URL: {url[:50]}...")

    print(f"Loaded {len(urls)} URLs from {file_path}")
    return urls


def main():
    parser = argparse.ArgumentParser(
        description="Test web scraping and indexing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("--url", help="Single URL to scrape")
    parser.add_argument("--urls", nargs="+", help="Multiple URLs to scrape")
    parser.add_argument("--file", help="File containing URLs (one per line)")
    parser.add_argument("--search", help="Search query for indexed pages")
    parser.add_argument("--index-name", default="web_pages", help="Index name")
    parser.add_argument("--timeout", type=int, default=10, help="Request timeout in seconds")

    args = parser.parse_args()

    if args.url:
        # Scrape single URL
        indexer = WebIndexer(timeout=args.timeout)
        chunks = indexer.ingest(args.url)
        if chunks:
            print("\n" + "="*50)
            print("Scraped Content:")
            print("="*50)
            print(chunks[0].content)
        return

    if args.urls:
        # Index multiple URLs
        success = index_urls(args.urls, args.index_name)
        sys.exit(0 if success else 1)
        return

    if args.file:
        # Load and index URLs from file
        urls = load_urls_from_file(args.file)
        if urls:
            success = index_urls(urls, args.index_name)
            sys.exit(0 if success else 1)
        return

    if args.search:
        # Search indexed pages
        success = search_web_pages(args.search, args.index_name)
        sys.exit(0 if success else 1)
        return

    # Default: show help
    parser.print_help()


if __name__ == "__main__":
    main()
