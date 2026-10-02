"""
Document Search Module

Provides indexing and search for multiple document formats:
- PDF: Ensemble extraction (PyMuPDF + pdfplumber + unstructured)
- Word: DOCX with heading hierarchy
- Text: Markdown, TXT with smart chunking
- Swagger: OpenAPI specification indexing

Main classes:
- RagTool: Unified document search tool
- DocumentVectorStore: FAISS-based vector storage
"""

from .base import DocumentIndexer
from .image_indexer import ImageIndexer
from .pdf_indexer import PdfIndexer
from .rag_tool import RagTool, create_rag_tool
from .swagger_indexer import SwaggerIndexer
from .text_indexer import TextIndexer
from .vector_store import DocumentVectorStore
from .web_indexer import WebIndexer
from .word_indexer import WordIndexer

__all__ = [
    "DocumentIndexer",
    "PdfIndexer",
    "WordIndexer",
    "TextIndexer",
    "SwaggerIndexer",
    "ImageIndexer",
    "WebIndexer",
    "DocumentVectorStore",
    "RagTool",
    "create_rag_tool",
]
