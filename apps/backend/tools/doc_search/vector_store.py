"""
Document Vector Store — FAISS-based semantic memory for document chunks

Adapted from tools/code_search/vector_store.py

Uses nomic-embed-text via Ollama for embeddings, FAISS for vector search.
Supports save/load to disk for persistent indexes.
"""

import hashlib
import json
import pickle
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from models.schemas import DocumentChunk, DocumentSearchResult

from tools.code_search.config import EMBED_DIMENSION, EMBED_MODEL, OLLAMA_EMBED_URL

try:
    import faiss
except ImportError:
    faiss = None
    print("[doc_vector_store] Warning: faiss not available", file=sys.stderr)


def log(msg: str):
    """Log to stderr."""
    sys.stderr.write(f"[doc_vector_store] {msg}\n")
    sys.stderr.flush()


class DocumentVectorStore:
    """
    FAISS-based semantic memory for document chunks.

    Stores embeddings for all document types (PDF, Word, Text, Swagger).
    """

    def __init__(self, index_name: str = "docs"):
        self.index_name = index_name
        self.index = None
        self.chunks: List[DocumentChunk] = []
        self.metadata: List[Dict] = []  # Additional metadata for FAISS lookup
        self.dimension = EMBED_DIMENSION
        self.index_dir = Path(__file__).parent.parent.parent.parent / "data" / "doc_indexes"
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self._init_index()

    def _init_index(self):
        """Initialize a fresh FAISS index."""
        if faiss:
            self.index = faiss.IndexFlatL2(self.dimension)
            log(f"Initialized FAISS index (dim={self.dimension})")

    def _get_embedding(self, text: str) -> Optional[np.ndarray]:
        """Get embedding from Ollama nomic-embed-text model."""
        try:
            response = requests.post(
                OLLAMA_EMBED_URL,
                json={"model": EMBED_MODEL, "prompt": text},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            embedding = data.get("embedding")
            if embedding:
                return np.array(embedding, dtype=np.float32)
            return None
        except Exception as e:
            log(f"Embedding failed: {e}")
            return None

    def add_chunk(self, chunk: DocumentChunk) -> bool:
        """Add a document chunk to the vector index."""
        if not self.index:
            log("FAISS not available")
            return False

        # Use full content for embedding
        embed_text = chunk.content

        embedding = self._get_embedding(embed_text)
        if embedding is None:
            return False

        self.index.add(embedding.reshape(1, -1))
        self.chunks.append(chunk)

        # Store metadata for lookup
        self.metadata.append({
            "chunk_id": hashlib.md5(chunk.content.encode()).hexdigest(),
            "source": chunk.source,
            "source_type": chunk.source_type,
            "page": chunk.page_number,
            "index": len(self.chunks) - 1
        })

        return True

    def add_chunks(self, chunks: List[DocumentChunk], show_progress: bool = True) -> int:
        """Add multiple chunks. Returns count of successfully added."""
        added = 0
        total = len(chunks)
        for i, chunk in enumerate(chunks):
            if self.add_chunk(chunk):
                added += 1
            if show_progress and (i + 1) % 50 == 0:
                log(f"Indexed {i + 1}/{total} chunks...")
        return added

    def search(self, query: str, top_k: int = 5, source_type: Optional[str] = None) -> List[DocumentSearchResult]:
        """
        Search for similar document chunks.

        Args:
            query: Natural language search query
            top_k: Number of results to return
            source_type: Optional filter by document type (pdf, word, text, swagger)

        Returns:
            List of DocumentSearchResult with chunks and scores
        """
        if not self.index or self.index.ntotal == 0:
            return []

        embedding = self._get_embedding(query)
        if embedding is None:
            return []

        k = min(top_k, self.index.ntotal)
        distances, indices = self.index.search(embedding.reshape(1, -1), k)

        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < len(self.chunks):
                chunk = self.chunks[idx]

                # Filter by source_type if specified
                if source_type and chunk.source_type != source_type:
                    continue

                result = DocumentSearchResult(
                    chunk=chunk,
                    score=float(dist),
                    rank=len(results) + 1
                )
                results.append(result)

        return results

    def save(self) -> bool:
        """Save index and metadata to disk."""
        if not self.index:
            return False

        save_dir = self.index_dir / self.index_name
        save_dir.mkdir(parents=True, exist_ok=True)

        try:
            faiss.write_index(self.index, str(save_dir / "faiss.index"))
            with open(save_dir / "chunks.pkl", "wb") as f:
                pickle.dump(self.chunks, f)
            with open(save_dir / "metadata.pkl", "wb") as f:
                pickle.dump(self.metadata, f)
            with open(save_dir / "meta.json", "w") as f:
                json.dump({
                    "index_name": self.index_name,
                    "chunk_count": len(self.chunks),
                    "dimension": self.dimension,
                    "last_updated": datetime.now().isoformat()
                }, f, indent=2)
            log(f"Saved index: {len(self.chunks)} chunks → {save_dir}")
            return True
        except Exception as e:
            log(f"Save failed: {e}")
            return False

    def load(self) -> bool:
        """Load index and metadata from disk."""
        save_dir = self.index_dir / self.index_name
        index_path = save_dir / "faiss.index"
        chunks_path = save_dir / "chunks.pkl"
        metadata_path = save_dir / "metadata.pkl"

        if not index_path.exists() or not chunks_path.exists():
            log(f"No saved index for {self.index_name}")
            return False

        try:
            self.index = faiss.read_index(str(index_path))
            with open(chunks_path, "rb") as f:
                self.chunks = pickle.load(f)
            if metadata_path.exists():
                with open(metadata_path, "rb") as f:
                    self.metadata = pickle.load(f)
            log(f"Loaded index: {len(self.chunks)} chunks from {save_dir}")
            return True
        except Exception as e:
            log(f"Load failed: {e}")
            return False

    def clear(self):
        """Clear the index."""
        self._init_index()
        self.chunks = []
        self.metadata = []

    @property
    def total_chunks(self) -> int:
        return len(self.chunks)

    @property
    def is_ready(self) -> bool:
        return self.index is not None and self.index.ntotal > 0

    def get_stats(self) -> Dict:
        """Get index statistics."""
        source_type_counts = {}
        for chunk in self.chunks:
            source_type_counts[chunk.source_type] = source_type_counts.get(chunk.source_type, 0) + 1

        return {
            "index_name": self.index_name,
            "total_chunks": len(self.chunks),
            "dimension": self.dimension,
            "source_types": source_type_counts,
            "is_ready": self.is_ready
        }
