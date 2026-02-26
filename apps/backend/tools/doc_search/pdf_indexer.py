"""
PDF Indexer — High-accuracy PDF extraction with ensemble approach

Extracts content from PDFs using multiple engines:
- PyMuPDF: Layout backbone with font analysis
- pdfplumber: Table specialization
- unstructured: Semantic labeling

Processes: Ensemble → Merge → Deduplicate → Semantic Chunking
"""

import re
import sys
import uuid
import statistics
from pathlib import Path
from typing import List, Dict, Optional
from collections import Counter

import fitz  # PyMuPDF
import pdfplumber

# Optional imports
try:
    from unstructured.partition.pdf import partition_pdf
    UNSTRUCTURED_AVAILABLE = True
except ImportError:
    UNSTRUCTURED_AVAILABLE = False

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.doc_search.base import DocumentIndexer
from models.schemas import DocumentChunk, DocumentSearchResult, IndexStatus


class PdfIndexer(DocumentIndexer):
    """
    PDF document indexer using ensemble extraction.

    Uses multiple extraction engines and merges results with priority:
    Tables > Headings > Paragraphs
    """

    def __init__(self, index_dir: Optional[Path] = None):
        self.index_dir = index_dir or Path(__file__).parent.parent.parent.parent / "data" / "doc_indexes"
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self._status = IndexStatus(source="", source_type="pdf", chunk_count=0, is_ready=False)

    def ingest(self, source: str, source_type: str = "pdf") -> List[DocumentChunk]:
        """
        Ingest a PDF file and return chunks.

        Args:
            source: Path to PDF file
            source_type: Must be "pdf"

        Returns:
            List of DocumentChunk objects
        """
        source_path = Path(source)
        if not source_path.exists():
            raise FileNotFoundError(f"PDF not found: {source}")

        if source_path.suffix.lower() != ".pdf":
            raise ValueError(f"Not a PDF file: {source}")

        # Process PDF with ensemble extraction
        result = self._process_pdf_ensemble(str(source_path))

        # Convert to DocumentChunk objects
        chunks = []
        for i, chunk_text in enumerate(result["chunks"]):
            chunk = DocumentChunk(
                content=chunk_text,
                source=str(source_path),
                source_type="pdf",
                page_number=result.get("page_map", {}).get(i, 1),
                chunk_index=i,
                metadata={
                    "extraction_engine": "ensemble",
                    "chunk_id": f"{source_path.name}_{i}"
                }
            )
            chunks.append(chunk)

        # Update status
        self._status = IndexStatus(
            source=str(source_path),
            source_type="pdf",
            chunk_count=len(chunks),
            is_ready=len(chunks) > 0
        )

        return chunks

    def search(self, query: str, top_k: int = 5) -> List[DocumentSearchResult]:
        """Search indexed PDFs (requires vector store integration)."""
        # This will be implemented by the vector store
        raise NotImplementedError("Search requires vector store integration")

    def get_status(self) -> IndexStatus:
        """Get current indexing status."""
        return self._status

    # ========================================================================
    # PDF ENSEMBLE EXTRACTION (Extracted from mcp/rag.py)
    # ========================================================================

    def _process_pdf_ensemble(self, pdf_path: str) -> Dict:
        """High-accuracy PDF extraction pipeline with ensemble approach."""

        pymu = self._extract_pymupdf_layout(pdf_path)
        plumber = self._extract_pdfplumber_layout(pdf_path)
        unstructured = self._extract_unstructured_layout(pdf_path)

        merged = self._merge_layouts(pymu, plumber, unstructured)
        cleaned = self._remove_repeated_blocks(merged)

        markdown = self._generate_markdown_from_layout(cleaned)
        chunks = self._chunk_markdown_semantic(markdown)

        # Create page mapping
        page_map = {}
        chunk_idx = 0
        for page in cleaned.get("pages", []):
            page_chunks = len([b for b in page.get("blocks", []) if b.get("text", "").strip()])
            for _ in range(max(1, page_chunks)):
                page_map[chunk_idx] = page.get("page_number", 1)
                chunk_idx += 1

        return {
            "layout_json": cleaned,
            "markdown": markdown,
            "chunks": chunks,
            "page_map": page_map
        }

    def _extract_pymupdf_layout(self, pdf_path: str) -> Dict:
        """Engine A: PyMuPDF for layout backbone with font analysis."""
        doc = fitz.open(pdf_path)
        pages = []
        for page_index, page in enumerate(doc):
            blocks = page.get_text("dict")["blocks"]
            structured_blocks = []
            for b in blocks:
                if "lines" not in b:
                    continue
                text = ""
                font_sizes = []
                for line in b["lines"]:
                    for span in line["spans"]:
                        text += span["text"] + " "
                        font_sizes.append(span["size"])
                text = text.strip()
                if not text:
                    continue
                avg_font = statistics.mean(font_sizes) if font_sizes else 0
                structured_blocks.append({
                    "id": str(uuid.uuid4()),
                    "type": "paragraph",
                    "bbox": b["bbox"],
                    "text": text,
                    "metadata": {
                        "font_size": avg_font,
                        "engine": "pymupdf"
                    }
                })
            pages.append({
                "page_number": page_index + 1,
                "blocks": structured_blocks
            })
        doc.close()
        return {"engine": "pymupdf", "pages": pages}

    def _extract_pdfplumber_layout(self, pdf_path: str) -> Dict:
        """Engine B: pdfplumber for table specialization."""
        pages = []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_index, page in enumerate(pdf.pages):
                    structured_blocks = []
                    tables = page.extract_tables()
                    for table in tables:
                        table_text = "\n".join(
                            [" | ".join([cell or "" for cell in row]) for row in table]
                        )
                        if table_text.strip():
                            structured_blocks.append({
                                "id": str(uuid.uuid4()),
                                "type": "table",
                                "bbox": None,
                                "text": table_text,
                                "metadata": {
                                    "engine": "pdfplumber"
                                }
                            })
                    pages.append({
                        "page_number": page_index + 1,
                        "blocks": structured_blocks
                    })
        except Exception as e:
            sys.stderr.write(f"pdfplumber error: {e}\n")
        return {"engine": "pdfplumber", "pages": pages}

    def _extract_unstructured_layout(self, pdf_path: str) -> Dict:
        """Engine C: Unstructured for semantic labeling."""
        if not UNSTRUCTURED_AVAILABLE:
            return {"engine": "unstructured", "pages": []}
        try:
            elements = partition_pdf(pdf_path)
            pages = {}
            for el in elements:
                page_num = el.metadata.page_number or 1
                pages.setdefault(page_num, [])
                pages[page_num].append({
                    "id": str(uuid.uuid4()),
                    "type": el.category.lower(),
                    "bbox": None,
                    "text": el.text or "",
                    "metadata": {
                        "engine": "unstructured"
                    }
                })
            return {
                "engine": "unstructured",
                "pages": [
                    {"page_number": k, "blocks": v}
                    for k, v in sorted(pages.items())
                ]
            }
        except Exception as e:
            sys.stderr.write(f"Unstructured extraction failed: {e}\n")
            return {"engine": "unstructured", "pages": []}

    def _remove_repeated_blocks(self, layout_json: Dict) -> Dict:
        """Remove headers/footers that appear on >70% of pages."""
        block_counter = Counter()
        for page in layout_json["pages"]:
            for block in page["blocks"]:
                if block["text"].strip():
                    block_counter[block["text"]] += 1

        threshold = len(layout_json["pages"]) * 0.7
        for page in layout_json["pages"]:
            page["blocks"] = [
                b for b in page["blocks"]
                if block_counter.get(b["text"], 0) < threshold
            ]
        return layout_json

    def _merge_layouts(self, pymu: Dict, plumber: Dict, unstructured: Dict) -> Dict:
        """Merge extraction results with priority: tables > headings > paragraphs."""
        final_pages = []
        max_pages = max(
            len(pymu["pages"]),
            len(plumber.get("pages", [])),
            len(unstructured.get("pages", []))
        )

        for page_index in range(max_pages):
            base_blocks = pymu["pages"][page_index]["blocks"] if page_index < len(pymu["pages"]) else []
            plumber_blocks = plumber["pages"][page_index]["blocks"] if page_index < len(plumber.get("pages", [])) else []
            un_blocks = unstructured["pages"][page_index]["blocks"] if page_index < len(unstructured.get("pages", [])) else []

            merged_blocks = []
            for block in base_blocks:
                best_block = block.copy()
                # Replace with table from pdfplumber if detected
                for p_block in plumber_blocks:
                    if p_block["type"] == "table":
                        best_block = p_block.copy()
                        break
                # Upgrade to heading if unstructured marks it title
                for u_block in un_blocks:
                    if u_block["type"] in ["title", "header", "section-header"]:
                        if block["text"].strip() == u_block["text"].strip():
                            best_block["type"] = "heading"
                            best_block["metadata"]["semantic_type"] = u_block["type"]
                merged_blocks.append(best_block)

            # Add tables not already merged
            for p_block in plumber_blocks:
                if p_block["type"] == "table":
                    if not any(b.get("id") == p_block["id"] for b in merged_blocks):
                        merged_blocks.append(p_block)

            final_pages.append({
                "page_number": page_index + 1,
                "blocks": merged_blocks
            })

        return {"pages": final_pages}

    def _generate_markdown_from_layout(self, layout_json: Dict) -> str:
        """Generate markdown with page markers and semantic structure."""
        markdown = ""
        for page in layout_json["pages"]:
            markdown += f"\n<!-- PAGE_START: {page['page_number']} -->\n"
            for block in page["blocks"]:
                text = block["text"].strip()
                if not text:
                    continue
                if block["type"] == "heading":
                    markdown += f"\n## {text}\n"
                elif block["type"] == "table":
                    markdown += f"\n```\n{text}\n```\n"
                elif block["type"] == "list-item":
                    markdown += f"\n- {text}\n"
                else:
                    markdown += f"\n{text}\n"
            markdown += f"\n<!-- PAGE_END: {page['page_number']} -->\n"
        return markdown

    def _chunk_markdown_semantic(self, markdown: str, max_chars: int = 1200) -> List[str]:
        """Chunk by section boundaries (headings) for semantic coherence."""
        sections = re.split(r'(?=<!-- PAGE_START:|## )', markdown)
        chunks = []
        current_chunk = ""

        for sec in sections:
            if len(sec.strip()) < 50:
                continue
            if len(current_chunk) + len(sec) > max_chars and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = sec
            else:
                current_chunk += sec

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks
