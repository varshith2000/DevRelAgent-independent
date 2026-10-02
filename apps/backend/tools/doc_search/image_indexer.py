"""
Image Indexer — Image captioning and indexing with Ollama vision models

Features:
- Caption images using Ollama vision models (llava, moondream, etc.)
- Support for: PNG, JPG, JPEG, GIF, BMP, SVG, WebP
- Caption caching to avoid re-processing
- Image metadata extraction (dimensions, format)
- Integration with vector store for semantic search

Usage:
    indexer = ImageIndexer()
    chunks = indexer.ingest("data/docs/diagram.png")
"""

import base64
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

try:
    import io

    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from models.schemas import DocumentChunk, DocumentSearchResult, IndexStatus

from tools.code_search.config import EMBED_MODEL, OLLAMA_EMBED_URL, OLLAMA_URL, VISION_MODEL
from tools.doc_search.base import DocumentIndexer


class ImageIndexer(DocumentIndexer):
    """
    Image document indexer using Ollama vision models.

    Captions images for semantic search and extracts metadata.
    """

    def __init__(self, index_dir: Optional[Path] = None, vision_model: Optional[str] = None):
        self.index_dir = index_dir or Path(__file__).parent.parent.parent.parent / "data" / "doc_indexes"
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.vision_model = vision_model or VISION_MODEL
        self._status = IndexStatus(source="", source_type="image", chunk_count=0, is_ready=False)

        # Caption cache directory
        self.cache_dir = self.index_dir / "caption_cache"
        self.cache_dir.mkdir(exist_ok=True)
        self.captions_file = self.cache_dir / "captions.json"
        self._captions_cache = self._load_caption_cache()

    def ingest(self, source: str, source_type: str = "image") -> List[DocumentChunk]:
        """
        Ingest an image file and return captioned chunks.

        Args:
            source: Path to image file
            source_type: Must be "image"

        Returns:
            List of DocumentChunk objects with captions
        """
        source_path = Path(source)
        if not source_path.exists():
            raise FileNotFoundError(f"Image not found: {source}")

        # Check supported formats
        supported_exts = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".webp"}
        if source_path.suffix.lower() not in supported_exts:
            raise ValueError(f"Unsupported image format: {source_path.suffix}")

        # Generate caption
        caption = self._caption_image(str(source_path))

        if caption.startswith("[") or caption.startswith("Error"):
            raise ValueError(f"Failed to caption image: {caption}")

        # Extract metadata
        metadata = self._extract_image_metadata(source_path)

        # Create chunk with caption
        chunk = DocumentChunk(
            content=self._format_chunk(source_path, caption, metadata),
            source=str(source_path),
            source_type="image",
            page_number=None,
            chunk_index=0,
            metadata={
                **metadata,
                "caption": caption,
                "chunk_id": f"IMG_{source_path.name}",
                "caption_model": self.vision_model
            }
        )

        # Update status
        self._status = IndexStatus(
            source=str(source_path),
            source_type="image",
            chunk_count=1,
            is_ready=True
        )

        return [chunk]

    def search(self, query: str, top_k: int = 5) -> List[DocumentSearchResult]:
        """Search indexed images (requires vector store integration)."""
        raise NotImplementedError("Search requires vector store integration")

    def get_status(self) -> IndexStatus:
        """Get current indexing status."""
        return self._status

    # ========================================================================
    # IMAGE CAPTIONING
    # ========================================================================

    def _caption_image(self, img_path_or_url: str) -> str:
        """
        Caption image using Ollama vision model with caching.

        Args:
            img_path_or_url: Local path or URL to image

        Returns:
            Caption text (2-3 sentences)
        """
        # Check cache first
        filename = Path(img_path_or_url).name
        if filename in self._captions_cache:
            cached_caption = self._captions_cache[filename]
            if cached_caption and not cached_caption.startswith("["):
                return cached_caption

        # Load image data
        image_data = self._load_image_data(img_path_or_url)
        if not image_data:
            return "[No image data]"

        # Process image with PIL if available
        encoded_image = self._encode_image(image_data)
        if not encoded_image:
            return "[Image encoding failed]"

        # Generate caption with Ollama
        caption = self._generate_caption_ollama(encoded_image)

        # Cache the caption
        if caption and not caption.startswith("["):
            self._captions_cache[filename] = caption
            self._save_caption_cache()

        return caption

    def _load_image_data(self, img_path_or_url: str) -> Optional[bytes]:
        """Load image data from file path or URL."""
        try:
            # URL case
            if img_path_or_url.startswith(("http://", "https://")):
                response = requests.get(img_path_or_url, timeout=10)
                if response.status_code == 200:
                    return response.content
                return None

            # Local file case
            file_path = Path(img_path_or_url)
            if file_path.is_absolute():
                full_path = file_path
            else:
                # Try relative to data/docs/
                data_dir = Path(__file__).parent.parent.parent.parent / "data"
                full_path = data_dir / img_path_or_url
                if not full_path.exists():
                    full_path = Path(img_path_or_url).resolve()

            if full_path.exists():
                return full_path.read_bytes()
            return None

        except Exception as e:
            sys.stderr.write(f"[ImageIndexer] Failed to load image: {e}\n")
            return None

    def _encode_image(self, image_data: bytes) -> Optional[str]:
        """
        Encode image to base64, optionally resizing if too large.

        Args:
            image_data: Raw image bytes

        Returns:
            Base64 encoded string or None
        """
        if not PIL_AVAILABLE:
            # Fallback: encode directly
            return base64.b64encode(image_data).decode("utf-8")

        try:
            with Image.open(io.BytesIO(image_data)) as img:
                # Convert to RGB if necessary
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')

                # Resize if too large (max 1024px dimension)
                MAX_DIM = 1024
                width, height = img.size
                if width > MAX_DIM or height > MAX_DIM:
                    img.thumbnail((MAX_DIM, MAX_DIM), Image.Resampling.LANCZOS)

                # Encode to JPEG
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                return base64.b64encode(buf.getvalue()).decode("utf-8")

        except Exception as e:
            sys.stderr.write(f"[ImageIndexer] Image processing error: {e}\n")
            # Fallback to raw encoding
            return base64.b64encode(image_data).decode("utf-8")

    def _generate_caption_ollama(self, encoded_image: str) -> str:
        """
        Generate caption using Ollama vision model.

        Args:
            encoded_image: Base64 encoded image

        Returns:
            Caption text
        """
        caption_prompt = """Describe what this image shows. Focus on:
1. Any text or labels visible in the image.
2. The type of visual (diagram, chart, photo, table, code).
3. Key terms that would help retrieve this image in a search.

Keep your response concise (2-3 sentences max)."""

        try:
            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": self.vision_model,
                    "prompt": caption_prompt,
                    "images": [encoded_image],
                    "stream": True
                },
                stream=True,
                timeout=30
            )

            caption_parts = []
            for line in response.iter_lines():
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
            return caption if caption else "[No caption returned]"

        except Exception as e:
            sys.stderr.write(f"[ImageIndexer] Captioning failed: {e}\n")
            return f"[Image could not be processed: {str(e)}]"

    # ========================================================================
    # IMAGE METADATA
    # ========================================================================

    def _extract_image_metadata(self, image_path: Path) -> Dict:
        """Extract metadata from image file."""
        metadata = {
            "filename": image_path.name,
            "extension": image_path.suffix.lower(),
            "file_size": image_path.stat().st_size,
        }

        if PIL_AVAILABLE:
            try:
                with Image.open(image_path) as img:
                    metadata.update({
                        "width": img.width,
                        "height": img.height,
                        "mode": img.mode,
                        "format": img.format or image_path.suffix[1:].upper(),
                    })

                # Extract EXIF data if available
                from PIL.Image import Exif
                try:
                    exif = img._getexif()
                    if exif:
                        metadata["exif"] = {
                            "datetime": exif.get(306),  # DateTimeOriginal
                            "make": exif.get(271),       # Make
                            "model": exif.get(272),      # Model
                        }
                except:
                    pass

            except Exception as e:
                sys.stderr.write(f"[ImageIndexer] Metadata extraction failed: {e}\n")

        return metadata

    # ========================================================================
    # CHUNK FORMATTING
    # ========================================================================

    def _format_chunk(self, image_path: Path, caption: str, metadata: Dict) -> str:
        """Format image as searchable text chunk."""
        parts = [
            f"# Image: {image_path.name}",
            f"**Description:** {caption}",
        ]

        # Add metadata as searchable text
        if metadata.get("width"):
            parts.append(f"**Dimensions:** {metadata['width']}x{metadata['height']}")

        if metadata.get("format"):
            parts.append(f"**Format:** {metadata['format']}")

        # Add markdown image reference
        parts.append(f"![{image_path.name}]({image_path.name})")

        return "\n".join(parts)

    # ========================================================================
    # CAPTION CACHE
    # ========================================================================

    def _load_caption_cache(self) -> Dict[str, str]:
        """Load caption cache from disk."""
        if self.captions_file.exists():
            try:
                import json
                return json.loads(self.captions_file.read_text())
            except:
                return {}
        return {}

    def _save_caption_cache(self):
        """Save caption cache to disk."""
        try:
            import json
            self.captions_file.write_text(json.dumps(self._captions_cache, indent=2))
        except Exception as e:
            sys.stderr.write(f"[ImageIndexer] Failed to save cache: {e}\n")

    def clear_caption_cache(self):
        """Clear the caption cache."""
        self._captions_cache = {}
        if self.captions_file.exists():
            self.captions_file.unlink()
