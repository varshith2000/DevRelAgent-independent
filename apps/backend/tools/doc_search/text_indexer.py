"""
Text Indexer — Plain text and Markdown document processing

Handles: .md, .txt, .rst, and other text-based formats.
"""

import re
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.doc_search.base import DocumentIndexer
from models.schemas import DocumentChunk, DocumentSearchResult, IndexStatus


class TextIndexer(DocumentIndexer):
    """
    Text document indexer for Markdown, TXT, and other text files.

    Uses smart chunking that respects:
    - Code blocks
    - Headings (MD)
    - Paragraph boundaries
    """

    def __init__(self, index_dir: Optional[Path] = None):
        self.index_dir = index_dir or Path(__file__).parent.parent.parent.parent / "data" / "doc_indexes"
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self._status = IndexStatus(source="", source_type="text", chunk_count=0, is_ready=False)

    def ingest(self, source: str, source_type: str = "text") -> List[DocumentChunk]:
        """
        Ingest a text file and return chunks.

        Args:
            source: Path to text file
            source_type: One of: text, md, rst, markdown

        Returns:
            List of DocumentChunk objects
        """
        source_path = Path(source)
        if not source_path.exists():
            raise FileNotFoundError(f"Text file not found: {source}")

        # Read file content
        try:
            content = source_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = source_path.read_text(encoding="latin-1")

        # Detect if markdown
        is_markdown = source_path.suffix.lower() in [".md", ".markdown"]

        # Chunk content
        if is_markdown:
            chunks = self._chunk_markdown(content)
        else:
            chunks = self._chunk_text(content)

        # Convert to DocumentChunk objects
        chunk_objects = []
        for i, chunk_text in enumerate(chunks):
            chunk = DocumentChunk(
                content=chunk_text,
                source=str(source_path),
                source_type=source_type,
                page_number=None,
                chunk_index=i,
                metadata={
                    "file_type": source_path.suffix,
                    "line_estimate": content[:content.find(chunk_text)].count('\n') if chunk_text in content else 0
                }
            )
            chunk_objects.append(chunk)

        # Update status
        self._status = IndexStatus(
            source=str(source_path),
            source_type=source_type,
            chunk_count=len(chunk_objects),
            is_ready=len(chunk_objects) > 0
        )

        return chunk_objects

    def search(self, query: str, top_k: int = 5) -> List[DocumentSearchResult]:
        """Search indexed text documents (requires vector store integration)."""
        raise NotImplementedError("Search requires vector store integration")

    def get_status(self) -> IndexStatus:
        """Get current indexing status."""
        return self._status

    # ========================================================================
    # TEXT CHUNKING
    # ========================================================================

    def _chunk_markdown(self, markdown: str, max_chars: int = 1200) -> List[str]:
        """Chunk markdown respecting headings and code blocks."""
        chunks = []

        # Split by headings
        sections = re.split(r'^(#{1,6}\s+.+)$', markdown, flags=re.MULTILINE)

        current_chunk = ""
        for section in sections:
            if not section.strip():
                continue

            # If this is a heading, add it
            if section.startswith('#'):
                if current_chunk and len(current_chunk) > 200:
                    chunks.append(current_chunk.strip())
                    current_chunk = section + "\n"
                else:
                    current_chunk += section + "\n"
            else:
                # Check if adding this would exceed max_chars
                if len(current_chunk) + len(section) > max_chars and len(current_chunk) > 200:
                    chunks.append(current_chunk.strip())
                    current_chunk = section
                else:
                    current_chunk += section

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks if chunks else ([markdown] if markdown.strip() else [])

    def _chunk_text(self, text: str, max_chars: int = 1500) -> List[str]:
        """Chunk plain text by paragraph boundaries."""
        # Split by paragraphs
        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) > max_chars and len(current_chunk) > 100:
                chunks.append(current_chunk.strip())
                current_chunk = para + "\n\n"
            else:
                current_chunk += para + "\n\n"

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks if chunks else ([text] if text.strip() else [])

    def _get_safe_chunks(self, text: str, max_words: int = 512) -> List[str]:
        """Sub-split large chunks with sentence-aware boundaries (from rag.py)."""
        words = text.split()
        if len(words) <= max_words:
            return [text]

        chunks = []
        start_char = 0
        total_len = len(text)
        avg_chars_per_word = 6
        target_chunk_len = max_words * avg_chars_per_word

        while start_char < total_len:
            remaining = text[start_char:]
            if not remaining.strip():
                break
            if len(remaining.split()) <= max_words:
                chunks.append(remaining.strip())
                break

            end_pos = min(start_char + target_chunk_len, total_len)
            lookback_window = int(target_chunk_len * 0.3)

            # Find sentence boundary
            search_area = text[max(0, end_pos - lookback_window):end_pos]
            matches = list(re.finditer(r'[.!?](\s+|$)', search_area))
            if matches:
                new_end = max(0, end_pos - lookback_window) + matches[-1].end()
            else:
                new_end = end_pos

            chunk = text[start_char:new_end].strip()
            if chunk:
                chunks.append(chunk)

            start_char = new_end
            if start_char >= total_len:
                break

        return chunks
