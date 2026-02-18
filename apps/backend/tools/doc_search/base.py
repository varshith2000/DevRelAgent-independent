"""
Document Indexer — Abstract Base Class

Team implements concrete indexers for each format:
- PdfIndexer
- WordIndexer  
- TextIndexer
- OcrIndexer
- WebScraperIndexer
- SwaggerIndexer
"""

from abc import ABC, abstractmethod
from typing import List

import sys
from pathlib import Path

try:
    from models.schemas import DocumentChunk, DocumentSearchResult, IndexStatus
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from models.schemas import DocumentChunk, DocumentSearchResult, IndexStatus


class DocumentIndexer(ABC):
    """
    Abstract base class for document indexing.
    
    Each format (PDF, Word, etc.) implements this interface.
    The agent loop calls these through the tool registry.
    """

    @abstractmethod
    def ingest(self, source: str, source_type: str = "text") -> List[DocumentChunk]:
        """
        Ingest a document and return chunks.
        
        Args:
            source: File path or URL
            source_type: One of: pdf, word, text, image, web, swagger
            
        Returns:
            List of DocumentChunk objects
        """
        ...

    @abstractmethod
    def search(self, query: str, top_k: int = 5) -> List[DocumentSearchResult]:
        """
        Search indexed documents.
        
        Args:
            query: Natural language search query
            top_k: Number of results
            
        Returns:
            List of DocumentSearchResult objects
        """
        ...

    @abstractmethod
    def get_status(self) -> IndexStatus:
        """
        Get the current status of the document index.
        
        Returns:
            IndexStatus with source, chunk count, readiness
        """
        ...
