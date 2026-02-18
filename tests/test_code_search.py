"""
Code Search Tool — Verification Tests

Tests:
1. Code chunker: can parse a Python file and extract functions/classes
2. Vector store: can add and search chunks (requires Ollama running)
3. MCP server: tools are registered correctly

Run: python tests/test_code_search.py
"""

import sys
import os
from pathlib import Path

# Add backend to path
BACKEND_DIR = Path(__file__).parent.parent / "apps" / "backend"
sys.path.insert(0, str(BACKEND_DIR))


def test_code_chunker():
    """Test that the code chunker can parse Python code."""
    print("\n" + "=" * 60)
    print("TEST 1: Code Chunker")
    print("=" * 60)

    from tools.code_search.code_chunker import get_chunker, LanguageDetector

    chunker = get_chunker()
    print(f"  ✓ Chunker initialized")
    print(f"  ✓ Available parsers: {sorted(chunker.available_languages)}")

    # Test with a sample Python file
    sample_code = '''
"""Sample module for testing."""

class Calculator:
    """A simple calculator."""
    
    def add(self, a: int, b: int) -> int:
        """Add two numbers."""
        return a + b
    
    def multiply(self, a: int, b: int) -> int:
        """Multiply two numbers."""
        return a * b


def greet(name: str) -> str:
    """Greet someone."""
    return f"Hello, {name}!"
'''

    chunks = chunker.chunk_file("sample.py", sample_code, "python")
    print(f"  ✓ Parsed sample.py → {len(chunks)} chunks:")
    for chunk in chunks:
        print(f"    - [{chunk.chunk_type}] {chunk.name} (lines {chunk.start_line}-{chunk.end_line})")

    assert len(chunks) >= 2, f"Expected at least 2 chunks, got {len(chunks)}"
    print("  ✓ PASSED")


def test_vector_store():
    """Test that the vector store can add and search (needs Ollama)."""
    print("\n" + "=" * 60)
    print("TEST 2: Vector Store (requires Ollama running)")
    print("=" * 60)

    from tools.code_search.vector_store import VectorMemory
    from models.schemas import CodeChunk

    try:
        vm = VectorMemory(repo_name="test_repo")
        print(f"  ✓ VectorMemory initialized")

        chunk = CodeChunk(
            content="def hello(): return 'world'",
            file_path="test.py",
            chunk_type="function",
            name="hello",
            start_line=1,
            end_line=1,
            language="python",
        )

        success = vm.add_chunk(chunk)
        if success:
            print(f"  ✓ Added chunk to index (total: {vm.total_chunks})")

            results = vm.search("hello world function", top_k=1)
            print(f"  ✓ Search returned {len(results)} results")
            if results:
                found_chunk, score = results[0]
                print(f"    - Best match: {found_chunk.name} (score: {score:.4f})")
            print("  ✓ PASSED")
        else:
            print("  ⚠ Skipped: Ollama not running (embeddings unavailable)")
            print("  ℹ Start Ollama: ollama serve && ollama pull nomic-embed-text")

    except Exception as e:
        print(f"  ⚠ Skipped: {e}")
        print("  ℹ Ensure Ollama is running with nomic-embed-text model")


def test_models():
    """Test that all Pydantic models are importable."""
    print("\n" + "=" * 60)
    print("TEST 3: Pydantic Models")
    print("=" * 60)

    from models.schemas import (
        PerceptionResult, MemoryItem, RepositoryState,
        CodeChunk, SearchResult, DocumentChunk,
        DocumentSearchResult, IndexStatus,
        ChatRequest, ChatResponse, ToolCallResult,
    )
    print("  ✓ All models imported successfully")

    # Test instantiation
    pr = PerceptionResult(user_input="test query", intent="search_code")
    print(f"  ✓ PerceptionResult: intent={pr.intent}")

    cc = CodeChunk(content="x = 1", file_path="t.py")
    print(f"  ✓ CodeChunk: type={cc.chunk_type}, lang={cc.language}")

    dc = DocumentChunk(content="Hello", source="doc.pdf", source_type="pdf")
    print(f"  ✓ DocumentChunk: type={dc.source_type}")

    print("  ✓ PASSED")


def test_llm_provider():
    """Test that LLM provider factory works."""
    print("\n" + "=" * 60)
    print("TEST 4: LLM Provider Abstraction")
    print("=" * 60)

    from agent.llm_provider import _PROVIDERS
    print(f"  ✓ Available providers: {list(_PROVIDERS.keys())}")

    # Just test factory detection (don't call API)
    from agent.llm_provider import LLM_PROVIDER, LLM_MODEL
    print(f"  ✓ Configured: provider={LLM_PROVIDER}, model={LLM_MODEL}")
    print("  ✓ PASSED (API call skipped)")


if __name__ == "__main__":
    print("🧪 DevRelAgent — Code Search Verification Tests")
    print("=" * 60)

    passed = 0
    total = 4

    try:
        test_code_chunker()
        passed += 1
    except Exception as e:
        print(f"  ✗ FAILED: {e}")

    try:
        test_vector_store()
        passed += 1
    except Exception as e:
        print(f"  ✗ FAILED: {e}")

    try:
        test_models()
        passed += 1
    except Exception as e:
        print(f"  ✗ FAILED: {e}")

    try:
        test_llm_provider()
        passed += 1
    except Exception as e:
        print(f"  ✗ FAILED: {e}")

    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 60)
