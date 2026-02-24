from mcp.server.fastmcp import FastMCP, Image
from mcp.server.fastmcp.prompts import base
from mcp.types import TextContent
from mcp import types
from PIL import Image as PILImage
import math
import sys
import os
import json
from pathlib import Path
import subprocess
import hashlib
import time
import shutil
import uuid
import re
import base64
import asyncio
import concurrent.futures
import threading
import pickle
import statistics
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from typing import Optional, List, Dict
import requests
import numpy as np
import fitz  # PyMuPDF
import pdfplumber
import yaml
from docx import Document

# Fix attributes/imports pathing
sys.path.append(str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import local models
try:
    from models import (AddInput, AddOutput, SqrtInput, SqrtOutput, 
                       StringsToIntsInput, StringsToIntsOutput, 
                       ExpSumInput, ExpSumOutput, PythonCodeInput, 
                       PythonCodeOutput, UrlInput, FilePathInput, 
                       MarkdownInput, MarkdownOutput, ChunkListOutput, 
                       SearchDocumentsInput)
except ImportError:
    from mcp_servers.models import (AddInput, AddOutput, SqrtInput, SqrtOutput,
                                   StringsToIntsInput, StringsToIntsOutput,
                                   ExpSumInput, ExpSumOutput, PythonCodeInput,
                                   PythonCodeOutput, UrlInput, FilePathInput,
                                   MarkdownInput, MarkdownOutput, ChunkListOutput,
                                   SearchDocumentsInput)

import contextlib

# MCP Protocol Safety: Suppression of library noise on stdout
@contextlib.contextmanager
def suppress_stdout():
    old_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        yield
    finally:
        sys.stdout = old_stdout

with suppress_stdout():
    import faiss
    from tqdm import tqdm
    import trafilatura
    import pymupdf4llm
    try:
        from unstructured.partition.pdf import partition_pdf
        UNSTRUCTURED_AVAILABLE = True
    except ImportError:
        UNSTRUCTURED_AVAILABLE = False
        print("WARN: unstructured not available - install with: pip install unstructured")
    try:
        from rank_bm25 import BM25Okapi
        BM25_AVAILABLE = True
    except ImportError:
        BM25_AVAILABLE = False

from config.settings_loader import settings, get_ollama_url, get_model, get_timeout

mcp = FastMCP("Local Storage RAG v2")

# =============================================================================
# SETTINGS
# =============================================================================
EMBED_URL = get_ollama_url("embeddings")
OLLAMA_CHAT_URL = get_ollama_url("chat")
OLLAMA_URL = get_ollama_url("generate")
EMBED_MODEL = get_model("embedding")
RAG_LLM_MODEL = get_model("semantic_chunking")
VISION_MODEL = get_model("image_captioning")
CHUNK_SIZE = settings["rag"]["chunk_size"]
CHUNK_OVERLAP = settings["rag"]["chunk_overlap"]
MAX_CHUNK_LENGTH = settings["rag"]["max_chunk_length"]
TOP_K = settings["rag"]["top_k"]
OLLAMA_TIMEOUT = get_timeout()

ROOT = Path(__file__).parent.resolve()
BASE_DATA_DIR = ROOT.parent / "data"
MEMORY_SUMMARIES_DIR = ROOT.parent / "memory" / "session_summaries_index"
SYNC_TARGET_DIR = BASE_DATA_DIR / "conversation_history"

# Global indexing status
INDEXING_STATUS = {
    "active": False,
    "total": 0,
    "completed": 0,
    "currentFile": ""
}
INDEXING_LOCK = threading.Lock()
REINDEX_BUSY_LOCK = threading.Lock()
pdf_lock = threading.Lock()

# =============================================================================
# HIGH-ACCURACY PDF ENSEMBLE EXTRACTION
# =============================================================================

def extract_pymupdf_layout(pdf_path: str) -> Dict:
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


def extract_pdfplumber_layout(pdf_path: str) -> Dict:
    """Engine B: pdfplumber for table specialization."""
    pages = []
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
    return {"engine": "pdfplumber", "pages": pages}


def extract_unstructured_layout(pdf_path: str) -> Dict:
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
        mcp_log("WARN", f"Unstructured extraction failed: {e}")
        return {"engine": "unstructured", "pages": []}


def remove_repeated_blocks(layout_json: Dict) -> Dict:
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


def merge_layouts(pymu: Dict, plumber: Dict, unstructured: Dict) -> Dict:
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
                    # Check bbox overlap or use as separate block
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


def generate_markdown_from_layout(layout_json: Dict) -> str:
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


def chunk_markdown_semantic(markdown: str, max_chars: int = 1200) -> List[str]:
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


def process_pdf_high_accuracy(pdf_path: str) -> Dict:
    """High-accuracy PDF extraction pipeline with ensemble approach."""
    mcp_log("PDF", f"Starting ensemble extraction: {pdf_path}")
    
    with pdf_lock:
        pymu = extract_pymupdf_layout(pdf_path)
        plumber = extract_pdfplumber_layout(pdf_path)
        unstructured = extract_unstructured_layout(pdf_path)
        
        mcp_log("PDF", "Merging layouts...")
        merged = merge_layouts(pymu, plumber, unstructured)
        
        mcp_log("PDF", "Removing headers/footers...")
        cleaned = remove_repeated_blocks(merged)
        
        mcp_log("PDF", "Generating markdown...")
        markdown = generate_markdown_from_layout(cleaned)
        
        mcp_log("PDF", "Semantic chunking...")
        chunks = chunk_markdown_semantic(markdown)
    
    return {
        "layout_json": cleaned,
        "markdown": markdown,
        "chunks": chunks
    }


# =============================================================================
# OPENAPI EXTRACTION
# =============================================================================

def load_openapi(file_path: str) -> Dict:
    """Load OpenAPI spec from YAML or JSON."""
    with open(file_path, "r") as f:
        if file_path.endswith(".yaml") or file_path.endswith(".yml"):
            return yaml.safe_load(f)
        return json.load(f)


def normalize_openapi(spec: Dict, version: str = "v1") -> List[Dict]:
    """Normalize OpenAPI endpoints for indexing."""
    endpoints = []
    for path, methods in spec.get("paths", {}).items():
        for method, details in methods.items():
            if method.lower() in ["get", "post", "put", "delete", "patch"]:
                endpoint = {
                    "id": str(uuid.uuid4()),
                    "type": "api_endpoint",
                    "path": path,
                    "method": method.upper(),
                    "operation_id": details.get("operationId"),
                    "summary": details.get("summary", ""),
                    "description": details.get("description", ""),
                    "parameters": details.get("parameters", []),
                    "request_body": details.get("requestBody"),
                    "responses": details.get("responses"),
                    "tags": details.get("tags", []),
                    "version": version
                }
                endpoints.append(endpoint)
    return endpoints


def build_endpoint_embedding_text(endpoint: Dict) -> str:
    """Build semantic text for API endpoint embedding."""
    param_text = ""
    for p in endpoint.get("parameters", []):
        param_text += f"- {p.get('name')} ({p.get('in')}, required={p.get('required', False)}): {p.get('description', '')}\n"
    
    return f"""
{endpoint['method']} {endpoint['path']}
Summary: {endpoint['summary']}
Description: {endpoint['description']}
Parameters:
{param_text}
Tags: {', '.join(endpoint.get('tags', []))}
""".strip()


def process_openapi(file_path: str) -> Dict:
    """Process OpenAPI specification for RAG indexing."""
    spec = load_openapi(file_path)
    endpoints = normalize_openapi(spec)
    semantic_chunks = []
    
    for ep in endpoints:
        text = build_endpoint_embedding_text(ep)
        semantic_chunks.append({
            "id": ep["id"],
            "text": text,
            "metadata": {
                "path": ep["path"],
                "method": ep["method"],
                "tags": ep["tags"],
                "version": ep["version"],
                "type": "api_endpoint"
            }
        })
    
    return {
        "structured_index": endpoints,
        "semantic_chunks": semantic_chunks
    }


# =============================================================================
# DOCX EXTRACTION
# =============================================================================

def extract_docx_structure(file_path: str) -> List[Dict]:
    """Extract DOCX structure with heading hierarchy."""
    doc = Document(file_path)
    sections = []
    current_section = {
        "id": str(uuid.uuid4()),
        "heading": "ROOT",
        "level": 0,
        "content": []
    }
    
    for para in doc.paragraphs:
        if para.style.name.startswith("Heading"):
            sections.append(current_section)
            level = int(para.style.name.replace("Heading ", ""))
            current_section = {
                "id": str(uuid.uuid4()),
                "heading": para.text,
                "level": level,
                "content": []
            }
        else:
            if para.text.strip():
                current_section["content"].append({
                    "type": "paragraph",
                    "text": para.text
                })
    
    sections.append(current_section)
    return sections


def extract_docx_tables(file_path: str) -> List[str]:
    """Extract tables from DOCX as separate chunks."""
    doc = Document(file_path)
    tables = []
    for table in doc.tables:
        table_text = []
        for row in table.rows:
            row_text = [cell.text.strip() for cell in row.cells]
            table_text.append(" | ".join(row_text))
        if table_text:
            tables.append("\n".join(table_text))
    return tables


def process_docx(file_path: str) -> Dict:
    """Process DOCX with structure preservation."""
    sections = extract_docx_structure(file_path)
    tables = extract_docx_tables(file_path)
    chunks = []
    
    for sec in sections:
        if sec["heading"] == "ROOT" and not sec["content"]:
            continue
        text = f"Section: {sec['heading']}\n"
        for c in sec["content"]:
            text += c["text"] + "\n"
        if text.strip():
            chunks.append({
                "id": sec["id"],
                "text": text,
                "metadata": {
                    "heading": sec["heading"],
                    "level": sec["level"],
                    "type": "section"
                }
            })
    
    for t in tables:
        chunks.append({
            "id": str(uuid.uuid4()),
            "text": f"Table:\n{t}",
            "metadata": {
                "type": "table"
            }
        })
    
    return {"chunks": chunks}


# =============================================================================
# IMAGE CAPTIONING (OLLAMA-BASED)
# =============================================================================

def caption_image(img_url_or_path: str) -> str:
    """Caption image using Ollama vision model with caching."""
    mcp_log("CAPTION", f"Attempting to caption image: {img_url_or_path}")
    
    # Check caption ledger first
    captions_file = ROOT / "faiss_index" / "captions.json"
    captions_ledger = json.loads(captions_file.read_text()) if captions_file.exists() else {}
    
    filename = Path(img_url_or_path).name
    if filename in captions_ledger and captions_ledger[filename]:
        mcp_log("CAPTION", f"Using cached caption for {filename}")
        return captions_ledger[filename]
    
    # Load image data
    image_data = None
    try:
        if img_url_or_path.startswith("http://") or img_url_or_path.startswith("https://"):
            resp = requests.get(img_url_or_path, timeout=10)
            if resp.status_code == 200:
                image_data = resp.content
            else:
                return f"[Image download failed: {img_url_or_path}]"
        else:
            if Path(img_url_or_path).is_absolute():
                full_path = Path(img_url_or_path)
            else:
                full_path = BASE_DATA_DIR / img_url_or_path
                if not full_path.exists():
                    full_path = Path(__file__).parent / img_url_or_path
            full_path = full_path.resolve()
            if full_path.exists():
                image_data = full_path.read_bytes()
            else:
                return f"[Image file not found: {img_url_or_path}]"
        
        if not image_data:
            return "[No image data]"
        
        # Process Image with PIL
        from PIL import Image
        import io
        with Image.open(io.BytesIO(image_data)) as img:
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            width, height = img.size
            MAX_DIM = 1024
            if width > MAX_DIM or height > MAX_DIM:
                img.thumbnail((MAX_DIM, MAX_DIM), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            encoded_image = base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        mcp_log("WARN", f"Image processing error: {e}")
        return f"[Image error: {img_url_or_path}]"
    
    # Generate caption with Ollama
    caption_prompt = """Describe what this image shows. Focus on:
1. Any text or labels visible in the image.
2. The type of visual (diagram, chart, photo, table, code).
3. Key terms that would help retrieve this image in a search.
Keep your response concise (2-3 sentences max)."""
    
    try:
        with requests.post(OLLAMA_URL, json={
            "model": VISION_MODEL,
            "prompt": caption_prompt,
            "images": [encoded_image],
            "stream": True
        }, stream=True, timeout=OLLAMA_TIMEOUT) as result:
            caption_parts = []
            for line in result.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    caption_parts.append(data.get("response", ""))
                    if data.get("done", False):
                        break
                except json.JSONDecodeError:
                    continue
            caption = "".join(caption_parts).strip()
            
            # Cache the caption
            if caption and not caption.startswith("["):
                captions_ledger[filename] = caption
                captions_file.parent.mkdir(exist_ok=True)
                captions_file.write_text(json.dumps(captions_ledger, indent=2))
            
            mcp_log("CAPTION", f"Caption generated: {caption}")
            return caption if caption else "[No caption returned]"
    except Exception as e:
        mcp_log("ERROR", f"Failed to caption image {img_url_or_path}: {e}")
        return f"[Image could not be processed: {img_url_or_path}]"


# =============================================================================
# EMBEDDING & SEARCH
# =============================================================================

def get_embedding(text: str) -> np.ndarray:
    """Get embedding from Ollama."""
    result = requests.post(EMBED_URL, json={"model": EMBED_MODEL, "prompt": text}, timeout=OLLAMA_TIMEOUT)
    result.raise_for_status()
    return np.array(result.json()["embedding"], dtype=np.float32)


def get_safe_chunks(text: str, max_words: int = 512, overlap: int = 50) -> List[str]:
    """Sub-split large chunks with sentence-aware boundaries."""
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


@dataclass
class QueryAnalysis:
    """Result of query analysis for hybrid search."""
    original_query: str
    intent: str
    entities: list = field(default_factory=list)
    quoted_phrases: list = field(default_factory=list)
    proper_nouns: list = field(default_factory=list)


def analyze_query(query: str) -> QueryAnalysis:
    """Analyze query to determine intent and extract entities."""
    analysis = QueryAnalysis(original_query=query, intent="SEMANTIC")
    
    # Extract quoted phrases
    quoted_pattern = r'"([^"]+)"|\'([^\']+)\''
    quoted_matches = re.findall(quoted_pattern, query)
    analysis.quoted_phrases = [m[0] or m[1] for m in quoted_matches]
    
    # Extract emails/IDs
    ids_emails = []
    ids_emails.extend(re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', query))
    ids_emails.extend(re.findall(r'\b[A-Z]{2,4}[-]?\d{4,}\b', query))
    
    # Extract proper nouns
    clean_query = re.sub(quoted_pattern, '', query)
    words = clean_query.split()
    skip_words = {'the', 'a', 'an', 'this', 'find', 'search', 'show', 'get', 'about', 'for'}
    proper_nouns = []
    current_noun = []
    
    for word in words:
        clean_word = re.sub(r'[^\w]', '', word)
        if not clean_word or len(clean_word) < 2:
            if current_noun:
                proper_nouns.append(' '.join(current_noun))
                current_noun = []
            continue
        if clean_word.lower() in skip_words:
            if current_noun:
                proper_nouns.append(' '.join(current_noun))
                current_noun = []
            continue
        current_noun.append(clean_word)
    
    if current_noun:
        proper_nouns.append(' '.join(current_noun))
    
    analysis.proper_nouns = [pn for pn in proper_nouns if len(pn.split()) >= 2 or len(pn) > 2]
    
    # Determine intent
    all_entities = analysis.quoted_phrases + ids_emails + analysis.proper_nouns
    analysis.entities = list(set(all_entities))
    
    if analysis.quoted_phrases or ids_emails:
        analysis.intent = "LEXICAL_REQUIRED"
    elif analysis.proper_nouns:
        analysis.intent = "LEXICAL_PREFERRED"
    else:
        analysis.intent = "SEMANTIC"
    
    return analysis


class BM25Index:
    """BM25 keyword search index for hybrid search."""
    def __init__(self):
        self.bm25 = None
        self.corpus = []
        self.chunk_ids = []
        self.metadata = []
    
    def tokenize(self, text: str) -> List:
        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)
        return [t for t in text.split() if len(t) > 1]
    
    def build_from_metadata(self, metadata: list):
        if not BM25_AVAILABLE:
            return
        self.corpus = []
        self.chunk_ids = []
        self.metadata = metadata
        for entry in metadata:
            self.corpus.append(self.tokenize(entry.get('chunk', '')))
            self.chunk_ids.append(entry.get('chunk_id', ''))
        self.bm25 = BM25Okapi(self.corpus)
    
    def search(self, query: str, top_k: int = 20) -> List:
        if not self.bm25:
            return []
        tokens = self.tokenize(query)
        scores = self.bm25.get_scores(tokens)
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [(self.chunk_ids[i], float(scores[i])) for i in top_indices if scores[i] > 0]
    
    def save(self, path: str):
        with open(path, 'wb') as f:
            pickle.dump({'bm25': self.bm25, 'corpus': self.corpus, 'chunk_ids': self.chunk_ids}, f)
    
    def load(self, path: str) -> bool:
        try:
            with open(path, 'rb') as f:
                data = pickle.load(f)
                self.bm25 = data['bm25']
                self.corpus = data['corpus']
                self.chunk_ids = data['chunk_ids']
                return True
        except:
            return False


_bm25_index = BM25Index()


def rrf_fuse(bm25_results: list, faiss_results: list, k: int = 60) -> list:
    """Reciprocal Rank Fusion of BM25 and FAISS results."""
    scores = defaultdict(float)
    for rank, (chunk_id, _) in enumerate(bm25_results):
        scores[chunk_id] += 1.0 / (k + rank + 1)
    for rank, (chunk_id, _) in enumerate(faiss_results):
        scores[chunk_id] += 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def entity_gate(results: list, metadata: list, analysis: QueryAnalysis) -> tuple:
    """Filter results based on query entities."""
    if analysis.intent == "SEMANTIC" or not analysis.entities:
        return results, False
    
    chunk_lookup = {e['chunk_id']: e['chunk'].lower() for e in metadata}
    filtered = []
    
    for chunk_id, score in results:
        chunk_text = chunk_lookup.get(chunk_id, '')
        if analysis.quoted_phrases:
            if all(p.lower() in chunk_text for p in analysis.quoted_phrases):
                filtered.append((chunk_id, score))
                continue
        for noun in analysis.proper_nouns:
            tokens = noun.lower().split()
            if all(t in chunk_text for t in tokens):
                filtered.append((chunk_id, score))
                break
    
    return filtered, True


# =============================================================================
# DOCUMENT PROCESSING
# =============================================================================

def file_hash(path):
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


def process_single_file(file: Path, doc_path_root: Path, cache_meta: dict):
    """Worker function to process a single file with enhanced extraction."""
    try:
        rel_path = file.relative_to(doc_path_root).as_posix()
        fhash = file_hash(file)
        
        # Cache Check
        if rel_path in cache_meta:
            if cache_meta[rel_path] == fhash:
                return {"status": "SKIP", "rel_path": rel_path, "hash": fhash}
        
        ext = file.suffix.lower()
        chunks = []
        metadata_entries = []
        
        if ext == ".pdf":
            result = process_pdf_high_accuracy(str(file))
            for i, chunk in enumerate(result["chunks"]):
                chunks.append(chunk)
                metadata_entries.append({
                    "doc": rel_path,
                    "chunk": chunk,
                    "chunk_id": f"{rel_path}_{i}",
                    "type": "pdf_chunk"
                })
        
        elif ext in [".yaml", ".yml", ".json"]:
            # Check if OpenAPI
            try:
                content = file.read_text()
                if "openapi" in content.lower() or "swagger" in content.lower():
                    result = process_openapi(str(file))
                    for item in result["semantic_chunks"]:
                        chunks.append(item["text"])
                        metadata_entries.append({
                            "doc": rel_path,
                            "chunk": item["text"],
                            "chunk_id": item["id"],
                            "type": "api_endpoint",
                            **item["metadata"]
                        })
                else:
                    # Regular JSON/YAML
                    chunks.append(content)
                    metadata_entries.append({
                        "doc": rel_path,
                        "chunk": content,
                        "chunk_id": f"{rel_path}_0",
                        "type": "config"
                    })
            except:
                chunks.append(file.read_text())
                metadata_entries.append({
                    "doc": rel_path,
                    "chunk": file.read_text(),
                    "chunk_id": f"{rel_path}_0",
                    "type": "text"
                })
        
        elif ext == ".docx":
            result = process_docx(str(file))
            for i, item in enumerate(result["chunks"]):
                chunks.append(item["text"])
                metadata_entries.append({
                    "doc": rel_path,
                    "chunk": item["text"],
                    "chunk_id": f"{rel_path}_{i}",
                    "type": item["metadata"].get("type", "docx_chunk"),
                    **item["metadata"]
                })
        
        elif ext in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg"]:
            caption = caption_image(str(file))
            if not caption.startswith("["):
                chunk_text = f"# Image: {file.name}\n**Description:** {caption}\n![{file.name}]({rel_path})"
                chunks.append(chunk_text)
                metadata_entries.append({
                    "doc": rel_path,
                    "chunk": chunk_text,
                    "chunk_id": f"IMG_{rel_path}",
                    "type": "image_caption"
                })
            else:
                return {"status": "ERROR", "rel_path": rel_path, "message": caption}
        
        else:
            # Fallback to text extraction
            try:
                from markitdown import MarkItDown
                converter = MarkItDown()
                markdown = converter.convert(str(file)).text_content
                if markdown.strip():
                    for i, chunk in enumerate(get_safe_chunks(markdown)):
                        chunks.append(chunk)
                        metadata_entries.append({
                            "doc": rel_path,
                            "chunk": chunk,
                            "chunk_id": f"{rel_path}_{i}",
                            "type": "text"
                        })
            except:
                text = file.read_text(errors='replace')
                for i, chunk in enumerate(get_safe_chunks(text)):
                    chunks.append(chunk)
                    metadata_entries.append({
                        "doc": rel_path,
                        "chunk": chunk,
                        "chunk_id": f"{rel_path}_{i}",
                        "type": "text"
                    })
        
        if not chunks:
            return {"status": "WARN", "rel_path": rel_path, "message": "No content extracted"}
        
        # Batch Embedding
        BATCH_SIZE = 32
        embeddings_for_file = []
        
        for i in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[i:i + BATCH_SIZE]
            try:
                batch_url = EMBED_URL.replace("/api/embeddings", "/api/embed")
                res = requests.post(batch_url, json={
                    "model": EMBED_MODEL,
                    "input": batch
                }, timeout=OLLAMA_TIMEOUT)
                res.raise_for_status()
                embeddings_list = [np.array(e, dtype=np.float32) for e in res.json()["embeddings"]]
            except:
                embeddings_list = [get_embedding(t) for t in batch]
            
            embeddings_for_file.extend(embeddings_list)
        
        return {
            "status": "SUCCESS",
            "rel_path": rel_path,
            "hash": fhash,
            "embeddings": embeddings_for_file,
            "metadata": metadata_entries
        }
    
    except Exception as e:
        return {"status": "ERROR", "rel_path": str(file), "message": str(e)}


def process_documents(target_path: str = None, specific_files: list = None):
    """Process documents with parallel processing."""
    mcp_log("INFO", f"Indexing documents...")
    
    INDEX_CACHE = ROOT / "faiss_index"
    INDEX_CACHE.mkdir(exist_ok=True)
    INDEX_FILE = INDEX_CACHE / "index.bin"
    METADATA_FILE = INDEX_CACHE / "metadata.json"
    CACHE_FILE = INDEX_CACHE / "doc_index_cache.json"
    
    CACHE_META = json.loads(CACHE_FILE.read_text()) if CACHE_FILE.exists() else {}
    metadata = json.loads(METADATA_FILE.read_text()) if METADATA_FILE.exists() else []
    index = faiss.read_index(str(INDEX_FILE)) if INDEX_FILE.exists() else None
    
    files_to_process = []
    if specific_files:
        files_to_process = specific_files
    elif target_path:
        target_file = BASE_DATA_DIR / target_path
        if target_file.exists():
            files_to_process = [target_file]
    else:
        skip_dirs = {'.git', '.github', 'node_modules', '__pycache__', 'faiss_index'}
        skip_exts = {'.mp4', '.mov', '.wav', '.mp3', '.bin', '.exe', '.pyc'}
        for root, dirs, filenames in os.walk(BASE_DATA_DIR):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith('.')]
            for f in filenames:
                if f.startswith('.'):
                    continue
                if Path(f).suffix.lower() in skip_exts:
                    continue
                files_to_process.append(Path(root) / f)
    
    MAX_WORKERS = 2
    mcp_log("INFO", f"Processing {len(files_to_process)} files with {MAX_WORKERS} workers")
    
    with INDEXING_LOCK:
        INDEXING_STATUS["total"] = len(files_to_process)
        INDEXING_STATUS["completed"] = 0
    
    index_lock = threading.Lock()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_single_file, f, BASE_DATA_DIR, CACHE_META.copy()): f for f in files_to_process}
        
        for future in tqdm(concurrent.futures.as_completed(futures), total=len(files_to_process), desc="Indexing", file=sys.stderr):
            result = future.result()
            status = result.get("status")
            rel_path = result.get("rel_path")
            
            if status == "SKIP":
                with INDEXING_LOCK:
                    INDEXING_STATUS["completed"] += 1
            elif status == "SUCCESS":
                fhash = result.get("hash")
                new_embs = result.get("embeddings")
                new_meta = result.get("metadata")
                
                if new_embs:
                    with index_lock:
                        # Remove old entries
                        metadata = [m for m in metadata if m.get("doc") != rel_path]
                        
                        # Add new
                        if index is None:
                            dim = len(new_embs[0])
                            index = faiss.IndexFlatL2(dim)
                        index.add(np.stack(new_embs))
                        metadata.extend(new_meta)
                        CACHE_META[rel_path] = fhash
                        
                        # Save
                        CACHE_FILE.write_text(json.dumps(CACHE_META, indent=2))
                        METADATA_FILE.write_text(json.dumps(metadata, indent=2))
                        faiss.write_index(index, str(INDEX_FILE))
                    
                    mcp_log("DONE", f"Indexed {rel_path} ({len(new_embs)} chunks)")
                
                with INDEXING_LOCK:
                    INDEXING_STATUS["completed"] += 1
                    INDEXING_STATUS["currentFile"] = Path(rel_path).name
            elif status == "ERROR":
                mcp_log("ERROR", f"Failed {rel_path}: {result.get('message')}")
                with INDEXING_LOCK:
                    INDEXING_STATUS["completed"] += 1
    
    # Rebuild BM25
    if BM25_AVAILABLE:
        _bm25_index.build_from_metadata(metadata)
        _bm25_index.save(str(INDEX_CACHE / "bm25_index.pkl"))
    
    with INDEXING_LOCK:
        INDEXING_STATUS["active"] = False


@mcp.tool()
async def reindex_documents(target_path: str = None, force: bool = False) -> str:
    """Trigger manual re-index of RAG documents."""
    if not REINDEX_BUSY_LOCK.acquire(blocking=False):
        return "Indexing already in progress."
    
    with INDEXING_LOCK:
        INDEXING_STATUS["active"] = True
        INDEXING_STATUS["completed"] = 0
        INDEXING_STATUS["total"] = 0
    
    try:
        INDEX_CACHE = ROOT / "faiss_index"
        if force and not target_path:
            for f in ["index.bin", "metadata.json", "doc_index_cache.json"]:
                path = INDEX_CACHE / f
                if path.exists():
                    path.unlink()
        
        threading.Thread(target=process_documents, args=(target_path,), daemon=True).start()
        return f"Re-indexing started {'for ' + target_path if target_path else 'for all documents'}."
    except Exception as e:
        with INDEXING_LOCK:
            INDEXING_STATUS["active"] = False
        try:
            REINDEX_BUSY_LOCK.release()
        except:
            pass
        return f"Error: {str(e)}"


@mcp.tool()
async def get_indexing_status() -> str:
    """Get current indexing progress."""
    return json.dumps(INDEXING_STATUS)


@mcp.tool()
def search_stored_documents_rag(query: str, doc_path: str = None) -> List[str]:
    """Search with hybrid search (BM25 + vector + entity gating)."""
    global _bm25_index
    
    INDEX_CACHE = ROOT / "faiss_index"
    INDEX_FILE = INDEX_CACHE / "index.bin"
    METADATA_FILE = INDEX_CACHE / "metadata.json"
    
    if not (INDEX_FILE.exists() and METADATA_FILE.exists()):
        return ["Index not found. Please run reindex_documents first."]
    
    metadata = json.loads(METADATA_FILE.read_text())
    analysis = analyze_query(query)
    
    # FAISS search
    index = faiss.read_index(str(INDEX_FILE))
    query_vec = get_embedding(query).reshape(1, -1)
    D, I = index.search(query_vec, k=50)
    
    faiss_results = []
    for rank, idx in enumerate(I[0]):
        if idx < 0 or idx >= len(metadata):
            continue
        chunk_id = metadata[idx].get('chunk_id', f'idx_{idx}')
        faiss_results.append((chunk_id, float(D[0][rank])))
    
    # BM25 search
    bm25_results = []
    if BM25_AVAILABLE:
        bm25_path = INDEX_CACHE / "bm25_index.pkl"
        if not _bm25_index.bm25:
            if bm25_path.exists():
                _bm25_index.load(str(bm25_path))
            else:
                _bm25_index.build_from_metadata(metadata)
                _bm25_index.save(str(bm25_path))
        bm25_results = _bm25_index.search(query, top_k=30)
    
    # RRF Fusion
    if bm25_results:
        fused_results = rrf_fuse(bm25_results, faiss_results)
    else:
        fused_results = faiss_results
    
    # Entity Gate
    gated_results, gate_applied = entity_gate(fused_results, metadata, analysis)
    
    # Build results
    chunk_lookup = {e['chunk_id']: e for e in metadata}
    results = []
    
    for chunk_id, score in (gated_results if gate_applied else fused_results)[:TOP_K * 2]:
        data = chunk_lookup.get(chunk_id)
        if not data:
            continue
        if doc_path and data.get('doc') != doc_path:
            continue
        
        doc_rel_path = data.get('doc', '')
        if not doc_rel_path:
            continue
        
        full_path = BASE_DATA_DIR / doc_rel_path
        if not full_path.exists():
            continue
        
        chunk_text = data.get('chunk', '').strip()
        if not chunk_text:
            continue
        
        page = data.get('page', 1)
        chunk_type = data.get('type', 'text')
        results.append(f"[{chunk_type.upper()}] {chunk_text}\n[Source: {doc_rel_path} p{page}]")
        
        if len(results) >= TOP_K:
            break
    
    return results if results else ["No relevant documents found."]


@mcp.tool()
def preview_document(path: str) -> MarkdownOutput:
    """Preview document with enhanced extraction."""
    file = Path(path)
    if not file.exists():
        return MarkdownOutput(markdown=f"### ❌ Error\nFile not found: `{path}`")
    
    ext = file.suffix.lower()
    
    try:
        if ext == ".pdf":
            result = process_pdf_high_accuracy(str(file))
            return MarkdownOutput(markdown=result["markdown"])
        elif ext == ".docx":
            result = process_docx(str(file))
            md = "\n\n".join([c["text"] for c in result["chunks"]])
            return MarkdownOutput(markdown=md)
        elif ext in [".yaml", ".yml", ".json"]:
            content = file.read_text()
            if "openapi" in content.lower():
                result = process_openapi(str(file))
                md = "\n\n".join([c["text"] for c in result["semantic_chunks"]])
                return MarkdownOutput(markdown=md)
            return MarkdownOutput(markdown=f"```{ext.strip('.')}\n{content}\n```")
        else:
            text = file.read_text(errors='replace')
            return MarkdownOutput(markdown=f"```\n{text}\n```")
    except Exception as e:
        return MarkdownOutput(markdown=f"### ❌ Error\n{str(e)}")


def mcp_log(level: str, message: str) -> None:
    sys.stderr.write(f"{level}: {message}\n")
    sys.stderr.flush()


def ensure_faiss_ready():
    index_path = ROOT / "faiss_index" / "index.bin"
    meta_path = ROOT / "faiss_index" / "metadata.json"
    if not (index_path.exists() and meta_path.exists()):
        mcp_log("INFO", "Index not found — running process_documents()...")
        process_documents()


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    mcp_log("INFO", "🚀 Starting RAG MCP Server v2...")
    ensure_faiss_ready()
    mcp.run()