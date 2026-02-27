"""
Quick verification script to test the document search setup.

Usage:
    python scripts/verify_setup.py
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "backend"))


def test_imports():
    """Test that all modules can be imported."""
    print("🔍 Testing imports...")

    try:
        from tools.doc_search import (
            DocumentIndexer,
            PdfIndexer,
            WordIndexer,
            TextIndexer,
            SwaggerIndexer,
            ImageIndexer,
            WebIndexer,
            DocumentVectorStore,
            RagTool,
            create_rag_tool
        )
        print("  ✓ All doc_search modules imported")
        return True
    except ImportError as e:
        print(f"  ✗ Import failed: {e}")
        return False


def test_rag_tool():
    """Test RAG tool initialization."""
    print("\n🔍 Testing RAG tool...")

    try:
        from tools.doc_search import RagTool

        rag = RagTool(index_name="test")
        stats = rag.get_stats()

        print(f"  ✓ RAG tool initialized")
        print(f"    - Index name: {stats['index_name']}")
        print(f"    - Total chunks: {stats['total_chunks']}")
        print(f"    - Is ready: {stats['is_ready']}")
        return True
    except Exception as e:
        print(f"  ✗ RAG tool test failed: {e}")
        return False


def test_indexers():
    """Test individual indexers."""
    print("\n🔍 Testing indexers...")

    from tools.doc_search import PdfIndexer, WordIndexer, TextIndexer, SwaggerIndexer, ImageIndexer

    indexers = [
        ("PDF", PdfIndexer),
        ("Word", WordIndexer),
        ("Text", TextIndexer),
        ("Swagger", SwaggerIndexer),
        ("Image", ImageIndexer),
    ]

    for name, indexer_class in indexers:
        try:
            indexer = indexer_class()
            status = indexer.get_status()
            print(f"  ✓ {name} Indexer: {status.source_type}")
        except Exception as e:
            print(f"  ✗ {name} Indexer failed: {e}")
            return False

    # Test WebIndexer separately (requires additional dependencies)
    try:
        from tools.doc_search import WebIndexer
        print(f"  ✓ Web Indexer: Available (trafilatura + requests + beautifulsoup4)")
    except ImportError:
        print(f"  ⚠️  Web Indexer: Not available (install with: pip install trafilatura requests beautifulsoup4)")

    return True


def test_vector_store():
    """Test vector store."""
    print("\n🔍 Testing vector store...")

    try:
        from tools.doc_search import DocumentVectorStore

        store = DocumentVectorStore(index_name="test")
        print(f"  ✓ Vector store created")
        print(f"    - Dimension: {store.dimension}")
        print(f"    - Is ready: {store.is_ready}")
        print(f"    - Total chunks: {store.total_chunks}")
        return True
    except Exception as e:
        print(f"  ✗ Vector store test failed: {e}")
        return False


def test_config():
    """Test config module."""
    print("\n🔍 Testing config...")

    try:
        from mcp.config.settings_loader import get_ollama_url, get_model, get_timeout

        embed_url = get_ollama_url("embeddings")
        model = get_model("embedding")
        timeout = get_timeout()

        print(f"  ✓ Config loaded")
        print(f"    - Embed URL: {embed_url}")
        print(f"    - Model: {model}")
        print(f"    - Timeout: {timeout}s")
        return True
    except Exception as e:
        print(f"  ✗ Config test failed: {e}")
        return False


def check_dependencies():
    """Check optional dependencies."""
    print("\n🔍 Checking dependencies...")

    # Core dependencies
    deps = [
        ("faiss", "faiss"),
        ("PyMuPDF", "fitz"),
        ("pdfplumber", "pdfplumber"),
        ("python-docx", "docx"),
        ("PyYAML", "yaml"),
        ("PIL (Pillow)", "PIL"),
        ("requests", "requests"),
        ("numpy", "numpy"),
    ]

    missing = []
    for name, module in deps:
        try:
            __import__(module)
            print(f"  ✓ {name}")
        except ImportError:
            print(f"  ✗ {name} (not installed)")
            missing.append(name)

    # Web scraping dependencies (optional)
    print("\n  Web Scraping (optional):")
    web_deps = [
        ("trafilatura", "trafilatura"),
        ("beautifulsoup4", "bs4"),
    ]

    web_missing = []
    for name, module in web_deps:
        try:
            __import__(module)
            print(f"  ✓ {name}")
        except ImportError:
            print(f"  ✗ {name} (not installed)")
            web_missing.append(name)

    if web_missing:
        print(f"\n  ⚠️  Web scraping disabled. Install with:")
        print(f"     pip install {' '.join(web_missing)}")

    if missing:
        print(f"\n⚠️  Missing core dependencies: {', '.join(missing)}")
        print("Install with: pip install " + " ".join(missing).lower().replace(" (pillow)", ""))

    return len(missing) == 0


def main():
    print("=" * 50)
    print("🧪 DevRelAgent Document Search — Verification")
    print("=" * 50)

    results = {
        "imports": test_imports(),
        "rag_tool": test_rag_tool(),
        "indexers": test_indexers(),
        "vector_store": test_vector_store(),
        "config": test_config(),
        "dependencies": check_dependencies(),
    }

    print("\n" + "=" * 50)
    print("📊 Results:")
    print("=" * 50)

    for test, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {test}")

    all_passed = all(results.values())
    print("\n" + "=" * 50)
    if all_passed:
        print("✅ All tests passed! Ready to use.")
    else:
        print("⚠️  Some tests failed. Check the output above.")
    print("=" * 50)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
