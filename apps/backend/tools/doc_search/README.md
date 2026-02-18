# Document Search Tool — Team Implementation Guide

> **Owner**: Team members (R2 — Backend + Data)  
> **Status**: Stub — interfaces and models defined, implementation needed

## Supported Formats

| Format | Library | Priority |
|--------|---------|----------|
| **PDF** | `pymupdf4llm` | P1 |
| **Word (.docx)** | `markitdown` | P1 |
| **Plain Text** (.md, .txt, .rst) | Built-in | P1 |
| **Images (OCR)** | `pillow` + Tesseract | P2 |
| **Web Scraping** | `trafilatura` | P2 |
| **Swagger/OpenAPI** | JSON/YAML parser + chunking | P1 |

## Install Dependencies

```bash
# From project root
pip install -e ".[docs]"
```

## Interface Contract

Your implementation must follow the `DocumentIndexer` abstract class in `base.py`:

```python
class DocumentIndexer(ABC):
    def ingest(self, source: str, source_type: str) -> List[DocumentChunk]
    def search(self, query: str, top_k: int = 5) -> List[DocumentSearchResult]
    def get_status(self) -> IndexStatus
```

## Models

All Pydantic models are defined in `apps/backend/models/schemas.py`:
- `DocumentChunk` — A chunk of document content
- `DocumentSearchResult` — Search result with score
- `IndexStatus` — Index health/status

## Integration Points

1. **Tool Registry**: Register your tool in `apps/backend/tools/registry.py`
2. **Agent Loop**: The agent will call your tool via the registry
3. **MCP Server**: Optionally expose as MCP tool in `apps/backend/mcp/server.py`
4. **Vector Store**: You can reuse the FAISS pattern from `tools/code_search/vector_store.py`

## Quick Start

```python
from tools.doc_search.base import DocumentIndexer
from models.schemas import DocumentChunk

class PdfIndexer(DocumentIndexer):
    def ingest(self, source: str, source_type: str = "pdf"):
        import pymupdf4llm
        md_text = pymupdf4llm.to_markdown(source)
        # Chunk and return DocumentChunk list
        ...
```
