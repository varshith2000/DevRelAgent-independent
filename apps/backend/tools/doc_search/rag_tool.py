"""
Unified RAG Tool — Document search across all indexed formats

Integrates all document indexers (PDF, Word, Text, Swagger) with the
vector store to provide unified semantic search.

Usage:
    tool = RagTool()
    tool.ingest_directory("data/docs/")
    results = tool.search("How do I configure OAuth2?")
"""

import sys
from pathlib import Path
from typing import List, Optional, Dict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from models.schemas import DocumentSearchResult
from tools.doc_search.pdf_indexer import PdfIndexer
from tools.doc_search.word_indexer import WordIndexer
from tools.doc_search.text_indexer import TextIndexer
from tools.doc_search.swagger_indexer import SwaggerIndexer
from tools.doc_search.image_indexer import ImageIndexer
from tools.doc_search.web_indexer import WebIndexer
from tools.doc_search.vector_store import DocumentVectorStore
from tools.doc_search.base import DocumentIndexer


class RagTool:
    """
    Unified RAG tool for document search.

    Supports: PDF, Word, Markdown, Text, OpenAPI/Swagger, Images, Web URLs
    """

    # File extension to indexer mapping
    INDEXERS = {
        ".pdf": PdfIndexer,
        ".docx": WordIndexer,
        ".doc": WordIndexer,
        ".md": TextIndexer,
        ".markdown": TextIndexer,
        ".txt": TextIndexer,
        ".rst": TextIndexer,
        ".yaml": SwaggerIndexer,
        ".yml": SwaggerIndexer,
        # Image formats
        ".png": ImageIndexer,
        ".jpg": ImageIndexer,
        ".jpeg": ImageIndexer,
        ".gif": ImageIndexer,
        ".bmp": ImageIndexer,
        ".svg": ImageIndexer,
        ".webp": ImageIndexer,
    }

    def __init__(self, index_name: str = "docs"):
        self.index_name = index_name
        self.vector_store = DocumentVectorStore(index_name=index_name)
        self.indexers: Dict[str, DocumentIndexer] = {}

        # Initialize indexers
        for ext, indexer_class in self.INDEXERS.items():
            self.indexers[ext] = indexer_class()

        # Initialize web indexer (not in INDEXERS dict)
        try:
            self.web_indexer = WebIndexer()
        except ImportError:
            self.web_indexer = None
            print("[RAG] Warning: WebIndexer not available. Install with: pip install trafilatura requests beautifulsoup4")

        # Load existing index if available
        self.vector_store.load()

    def ingest_file(self, file_path: str) -> int:
        """
        Ingest a single file into the vector index.

        Args:
            file_path: Path to the file

        Returns:
            Number of chunks added
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = path.suffix.lower()
        if ext not in self.INDEXERS:
            print(f"[RAG] Skipping {file_path}: unsupported type")
            return 0

        indexer = self.indexers[ext]
        source_type = self._get_source_type(ext)

        try:
            chunks = indexer.ingest(str(path), source_type=source_type)
            added = self.vector_store.add_chunks(chunks, show_progress=False)
            print(f"[RAG] Indexed {file_path}: {added} chunks")
            return added
        except Exception as e:
            print(f"[RAG] Failed to index {file_path}: {e}")
            return 0

    def ingest_directory(
        self,
        directory: str,
        recursive: bool = True,
        patterns: Optional[List[str]] = None
    ) -> Dict[str, int]:
        """
        Ingest all supported files from a directory.

        Args:
            directory: Path to directory
            recursive: Scan subdirectories
            patterns: Optional glob patterns to filter files

        Returns:
            Dictionary with counts per file type
        """
        dir_path = Path(directory)
        if not dir_path.exists() or not dir_path.is_dir():
            raise ValueError(f"Not a directory: {directory}")

        counts = {}
        files_to_process = []

        # Find all files
        if recursive:
            for ext in self.INDEXERS.keys():
                files_to_process.extend(dir_path.rglob(f"*{ext}"))
        else:
            for ext in self.INDEXERS.keys():
                files_to_process.extend(dir_path.glob(f"*{ext}"))

        # Apply pattern filters if provided
        if patterns:
            import fnmatch
            filtered = []
            for f in files_to_process:
                if any(fnmatch.fnmatch(f.name, p) for p in patterns):
                    filtered.append(f)
            files_to_process = filtered

        # Process files
        for file_path in files_to_process:
            ext = file_path.suffix.lower()
            added = self.ingest_file(str(file_path))
            counts[ext] = counts.get(ext, 0) + added

        # Save index after ingestion
        self.vector_store.save()

        return counts

    def ingest_url(self, url: str) -> int:
        """
        Ingest a web page from URL into the vector index.

        Args:
            url: URL to scrape and index

        Returns:
            Number of chunks added
        """
        if not self.web_indexer:
            print("[RAG] WebIndexer not available. Install with: pip install trafilatura requests beautifulsoup4")
            return 0

        if not url.startswith(("http://", "https://")):
            print(f"[RAG] Invalid URL: {url}")
            return 0

        try:
            chunks = self.web_indexer.ingest(url)
            added = self.vector_store.add_chunks(chunks, show_progress=False)
            print(f"[RAG] Indexed {url}: {added} chunks")

            # Save index after ingestion
            self.vector_store.save()

            return added
        except Exception as e:
            print(f"[RAG] Failed to index {url}: {e}")
            return 0

    def ingest_urls(self, urls: List[str]) -> Dict[str, int]:
        """
        Ingest multiple web pages from URLs.

        Args:
            urls: List of URLs to scrape and index

        Returns:
            Dictionary with domain-level counts
        """
        from urllib.parse import urlparse

        if not self.web_indexer:
            print("[RAG] WebIndexer not available. Install with: pip install trafilatura requests beautifulsoup4")
            return {}

        counts = {}
        for url in urls:
            if not url.startswith(("http://", "https://")):
                print(f"[RAG] Skipping invalid URL: {url}")
                continue

            domain = urlparse(url).netloc
            added = self.ingest_url(url)
            if added > 0:
                counts[domain] = counts.get(domain, 0) + added

        return counts

    def search(
        self,
        query: str,
        top_k: int = 5,
        source_type: Optional[str] = None
    ) -> List[DocumentSearchResult]:
        """
        Search indexed documents.

        Args:
            query: Natural language search query
            top_k: Number of results to return
            source_type: Optional filter by document type

        Returns:
            List of DocumentSearchResult objects
        """
        return self.vector_store.search(query, top_k=top_k, source_type=source_type)

    def search_with_context(
        self,
        query: str,
        top_k: int = 3
    ) -> str:
        """
        Search and return formatted results with context.

        Args:
            query: Natural language search query
            top_k: Number of results to return

        Returns:
            Formatted string with results and sources
        """
        results = self.search(query, top_k=top_k)

        if not results:
            return "No relevant documents found."

        output = []
        for i, result in enumerate(results, 1):
            chunk = result.chunk
            source_name = Path(chunk.source).name

            output.append(f"[{i}] {source_name}")
            if chunk.page_number:
                output.append(f"    Page: {chunk.page_number}")
            output.append(f"    Score: {result.score:.4f}")
            output.append(f"    Content: {chunk.content[:300]}...")
            output.append("")

        return "\n".join(output)

    def get_stats(self) -> Dict:
        """Get index statistics."""
        return self.vector_store.get_stats()

    def rebuild_index(self) -> bool:
        """Clear and rebuild index from saved chunks."""
        chunks = self.vector_store.chunks
        self.vector_store.clear()
        added = self.vector_store.add_chunks(chunks)
        self.vector_store.save()
        return added > 0

    def _get_source_type(self, ext: str) -> str:
        """Map file extension to source type."""
        type_map = {
            ".pdf": "pdf",
            ".docx": "word",
            ".doc": "word",
            ".md": "text",
            ".markdown": "text",
            ".txt": "text",
            ".rst": "text",
            ".yaml": "swagger",
            ".yml": "swagger",
            # Image formats
            ".png": "image",
            ".jpg": "image",
            ".jpeg": "image",
            ".gif": "image",
            ".bmp": "image",
            ".svg": "image",
            ".webp": "image",
        }
        return type_map.get(ext, "text")


# Convenience function for quick usage
def create_rag_tool(index_name: str = "docs") -> RagTool:
    """Create and initialize a RAG tool."""
    return RagTool(index_name=index_name)
