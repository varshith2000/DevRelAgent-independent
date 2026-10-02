"""
RAG MCP Server — Document indexing and search via Model Context Protocol

This is a simplified version that uses the new document indexers.
Original comprehensive version is in rag.py (legacy).

MCP Tools:
- reindex_documents: Trigger document indexing
- get_indexing_status: Get indexing progress
- search_stored_documents_rag: Search indexed documents
- preview_document: Preview document content
"""

import json
import sys
from pathlib import Path
from typing import List

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.doc_search.rag_tool import RagTool

from mcp.server.fastmcp import FastMCP

# Initialize MCP server
mcp = FastMCP("RAG Document Server")

# Global RAG tool instance
_rag_tool: RagTool = None

# Indexing status
INDEXING_STATUS = {
    "active": False,
    "total": 0,
    "completed": 0,
    "currentFile": ""
}


def mcp_log(level: str, message: str) -> None:
    """Log to stderr (MCP uses stdout for JSON)."""
    sys.stderr.write(f"[{level}] {message}\n")
    sys.stderr.flush()


def get_rag_tool() -> RagTool:
    """Get or create the global RAG tool instance."""
    global _rag_tool
    if _rag_tool is None:
        _rag_tool = RagTool(index_name="docs")
        # Try to load existing index
        _rag_tool.vector_store.load()
    return _rag_tool


@mcp.tool()
async def reindex_documents(target_path: str = None, force: bool = False) -> str:
    """
    Trigger manual re-index of RAG documents.

    Args:
        target_path: Optional specific file/directory to index
        force: Force rebuild even if cached

    Returns:
        Status message
    """
    global INDEXING_STATUS

    if INDEXING_STATUS["active"]:
        return "Indexing already in progress."

    INDEXING_STATUS["active"] = True
    INDEXING_STATUS["completed"] = 0
    INDEXING_STATUS["total"] = 0

    try:
        rag = get_rag_tool()

        if target_path:
            # Index specific path
            path = Path(target_path)
            if path.is_file():
                added = rag.ingest_file(str(path))
                return f"Indexed {target_path}: {added} chunks"
            elif path.is_dir():
                counts = rag.ingest_directory(str(path))
                total = sum(counts.values())
                return f"Indexed {target_path}: {total} chunks from {len(counts)} file types"
            else:
                return f"Path not found: {target_path}"
        else:
            # Index default docs directory
            docs_dir = Path(__file__).parent.parent.parent.parent / "data" / "docs"
            if not docs_dir.exists():
                return f"Documents directory not found: {docs_dir}"

            counts = rag.ingest_directory(str(docs_dir))
            total = sum(counts.values())
            rag.vector_store.save()

            INDEXING_STATUS["active"] = False
            return f"Indexed {total} chunks from {len(counts)} file types"

    except Exception as e:
        INDEXING_STATUS["active"] = False
        mcp_log("ERROR", str(e))
        return f"Error: {str(e)}"


@mcp.tool()
async def get_indexing_status() -> str:
    """
    Get current indexing progress.

    Returns:
        JSON string with indexing status
    """
    rag = get_rag_tool()
    stats = rag.get_stats()

    status = {
        "active": INDEXING_STATUS["active"],
        "completed": INDEXING_STATUS["completed"],
        "total": INDEXING_STATUS["total"],
        "currentFile": INDEXING_STATUS["currentFile"],
        "indexStats": stats
    }

    return json.dumps(status)


@mcp.tool()
def search_stored_documents_rag(query: str, source_type: str = None) -> List[str]:
    """
    Search indexed documents with semantic search.

    Args:
        query: Natural language search query
        source_type: Optional filter by document type (pdf, word, text, swagger)

    Returns:
        List of matching document chunks with sources
    """
    rag = get_rag_tool()

    if not rag.vector_store.is_ready:
        return ["Index not found. Please run reindex_documents first."]

    results = rag.search(query, top_k=5, source_type=source_type)

    if not results:
        return ["No relevant documents found."]

    output = []
    for i, result in enumerate(results, 1):
        chunk = result.chunk
        source_name = Path(chunk.source).name

        # Format result
        chunk_type = chunk.source_type.upper()
        source_info = f"[Source: {source_name}"
        if chunk.page_number:
            source_info += f" p{chunk.page_number}"
        source_info += "]"

        output.append(f"{chunk_type} {chunk.content[:500]}...\n{source_info}")

    return output


@mcp.tool()
def preview_document(path: str) -> str:
    """
    Preview document content.

    Args:
        path: Path to document file

    Returns:
        Document content as markdown/text
    """
    file_path = Path(path)
    if not file_path.exists():
        return f"### ❌ Error\nFile not found: `{path}`"

    ext = file_path.suffix.lower()

    try:
        # Use appropriate indexer
        if ext == ".pdf":
            from tools.doc_search.pdf_indexer import PdfIndexer
            indexer = PdfIndexer()
            chunks = indexer.ingest(str(file_path))
            return "\n\n".join([c.content for c in chunks[:5]]) + "\n\n... (truncated)"
        elif ext in [".docx", ".doc"]:
            from tools.doc_search.word_indexer import WordIndexer
            indexer = WordIndexer()
            chunks = indexer.ingest(str(file_path))
            return "\n\n".join([c.content for c in chunks[:5]]) + "\n\n... (truncated)"
        elif ext in [".yaml", ".yml"]:
            # Check if OpenAPI
            content = file_path.read_text()
            if "openapi" in content.lower() or "swagger" in content.lower():
                from tools.doc_search.swagger_indexer import SwaggerIndexer
                indexer = SwaggerIndexer()
                chunks = indexer.ingest(str(file_path))
                return "\n\n".join([c.content for c in chunks[:10]]) + "\n\n... (truncated)"
        # Default to text
        return file_path.read_text(errors='replace')
    except Exception as e:
        return f"### ❌ Error\n{str(e)}"


def ensure_index_ready():
    """Ensure index is ready, auto-index if needed."""
    rag = get_rag_tool()
    if not rag.vector_store.is_ready:
        mcp_log("INFO", "Index not found — attempting to index default docs directory...")
        docs_dir = Path(__file__).parent.parent.parent.parent / "data" / "docs"
        if docs_dir.exists():
            try:
                rag.ingest_directory(str(docs_dir))
                rag.vector_store.save()
                mcp_log("INFO", f"Auto-indexed {rag.vector_store.total_chunks} chunks")
            except Exception as e:
                mcp_log("WARN", f"Auto-index failed: {e}")


if __name__ == "__main__":
    mcp_log("INFO", "🚀 Starting RAG MCP Server...")
    ensure_index_ready()
    mcp.run()
