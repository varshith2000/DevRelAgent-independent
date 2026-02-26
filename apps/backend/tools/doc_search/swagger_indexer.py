"""
Swagger Indexer — OpenAPI/Swagger specification processing

Parses OpenAPI 2.0 and 3.x specs and indexes API endpoints as searchable chunks.
"""

import sys
import uuid
import json
from pathlib import Path
from typing import List, Optional

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.doc_search.base import DocumentIndexer
from models.schemas import DocumentChunk, DocumentSearchResult, IndexStatus


class SwaggerIndexer(DocumentIndexer):
    """
    OpenAPI/Swagger specification indexer.

    Parses API specs and creates searchable chunks for each endpoint.
    """

    def __init__(self, index_dir: Optional[Path] = None):
        self.index_dir = index_dir or Path(__file__).parent.parent.parent.parent / "data" / "doc_indexes"
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self._status = IndexStatus(source="", source_type="swagger", chunk_count=0, is_ready=False)

    def ingest(self, source: str, source_type: str = "swagger") -> List[DocumentChunk]:
        """
        Ingest an OpenAPI/Swagger spec and return chunks.

        Args:
            source: Path to OpenAPI spec (JSON or YAML)
            source_type: Must be "swagger"

        Returns:
            List of DocumentChunk objects (one per endpoint)
        """
        source_path = Path(source)
        if not source_path.exists():
            raise FileNotFoundError(f"Spec file not found: {source}")

        # Load OpenAPI spec
        spec = self._load_openapi(str(source_path))

        # Normalize endpoints
        endpoints = self._normalize_openapi(spec, version=str(source_path))

        # Convert to DocumentChunk objects
        chunks = []
        for endpoint in endpoints:
            chunk_text = self._build_endpoint_text(endpoint)
            chunk = DocumentChunk(
                content=chunk_text,
                source=str(source_path),
                source_type="swagger",
                page_number=None,
                chunk_index=len(chunks),
                metadata={
                    "path": endpoint["path"],
                    "method": endpoint["method"],
                    "operation_id": endpoint.get("operation_id"),
                    "tags": endpoint.get("tags", []),
                    "type": "api_endpoint"
                }
            )
            chunks.append(chunk)

        # Update status
        self._status = IndexStatus(
            source=str(source_path),
            source_type="swagger",
            chunk_count=len(chunks),
            is_ready=len(chunks) > 0
        )

        return chunks

    def search(self, query: str, top_k: int = 5) -> List[DocumentSearchResult]:
        """Search indexed API specs (requires vector store integration)."""
        raise NotImplementedError("Search requires vector store integration")

    def get_status(self) -> IndexStatus:
        """Get current indexing status."""
        return self._status

    # ========================================================================
    # OPENAPI PROCESSING (Extracted from mcp/rag.py)
    # ========================================================================

    def _load_openapi(self, file_path: str) -> dict:
        """Load OpenAPI spec from YAML or JSON."""
        with open(file_path, "r") as f:
            if file_path.endswith(".yaml") or file_path.endswith(".yml"):
                if not YAML_AVAILABLE:
                    raise ImportError("PyYAML is required for YAML specs. Install with: pip install pyyaml")
                return yaml.safe_load(f)
            return json.load(f)

    def _normalize_openapi(self, spec: dict, version: str = "v1") -> List[dict]:
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

    def _build_endpoint_text(self, endpoint: dict) -> str:
        """Build semantic text for API endpoint embedding/search."""
        param_text = ""
        for p in endpoint.get("parameters", []):
            param_text += f"- {p.get('name')} ({p.get('in')}, required={p.get('required', False)}): {p.get('description', '')}\n"

        return f"""{endpoint['method']} {endpoint['path']}
Summary: {endpoint['summary']}
Description: {endpoint['description']}
Parameters:
{param_text}
Tags: {', '.join(endpoint.get('tags', []))}""".strip()
