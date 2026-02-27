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
from .pdf_indexer import PdfIndexer
from .word_indexer import WordIndexer
from .text_indexer import TextIndexer
from .swagger_indexer import SwaggerIndexer
from .image_indexer import ImageIndexer
from .web_indexer import WebIndexer
from .vector_store import DocumentVectorStore
from .rag_tool import RagTool, create_rag_tool

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
