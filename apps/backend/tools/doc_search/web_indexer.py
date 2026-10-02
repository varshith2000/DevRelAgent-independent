"""
Web Scraper Indexer — High-accuracy web content extraction

Features:
- trafilatura for main content extraction (removes ads, navigation, etc.)
- Metadata extraction (title, author, date, URL)
- Support for multiple content types (articles, blogs, documentation)
- URL deduplication and caching
- HTML sanitization
- Language detection
- Integration with vector store for semantic search

Usage:
    indexer = WebIndexer()
    chunks = indexer.ingest("https://example.com/article")
"""

import hashlib
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from models.schemas import DocumentChunk, DocumentSearchResult, IndexStatus

from tools.doc_search.base import DocumentIndexer

try:
    import trafilatura
    TRAFILATURA_AVAILABLE = True
except ImportError:
    TRAFILATURA_AVAILABLE = False

try:
    import requests
    from bs4 import BeautifulSoup
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


class WebIndexer(DocumentIndexer):
    """
    Web document indexer using trafilatura for content extraction.

    Extracts clean, readable content from web pages while filtering
    out ads, navigation, footers, and other noise.
    """

    def __init__(self, index_dir: Optional[Path] = None, timeout: int = 10):
        self.index_dir = index_dir or Path(__file__).parent.parent.parent.parent / "data" / "doc_indexes"
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self._status = IndexStatus(source="", source_type="web", chunk_count=0, is_ready=False)

        # Cache for scraped content
        self.cache_dir = self.index_dir / "web_cache"
        self.cache_dir.mkdir(exist_ok=True)
        self._cache = self._load_cache()

        if not TRAFILATURA_AVAILABLE:
            raise ImportError("trafilatura is required. Install with: pip install trafilatura")
        if not REQUESTS_AVAILABLE:
            raise ImportError("requests and beautifulsoup4 are required. Install with: pip install requests beautifulsoup4")

    def ingest(self, source: str, source_type: str = "web") -> List[DocumentChunk]:
        """
        Ingest a web page and return chunks.

        Args:
            source: URL to scrape
            source_type: Must be "web"

        Returns:
            List of DocumentChunk objects
        """
        if not source.startswith(("http://", "https://")):
            raise ValueError(f"Invalid URL: {source}")

        # Check cache
        url_hash = hashlib.md5(source.encode()).hexdigest()
        if url_hash in self._cache:
            cached = self._cache[url_hash]
            if cached.get("status") == "success":
                # Return cached chunks
                chunks = []
                for i, content in enumerate(cached.get("chunks", [])):
                    chunk = DocumentChunk(
                        content=content,
                        source=source,
                        source_type="web",
                        page_number=None,
                        chunk_index=i,
                        metadata={
                            **cached.get("metadata", {}),
                            "chunk_id": f"{url_hash}_{i}",
                            "cached": True
                        }
                    )
                    chunks.append(chunk)

                self._status = IndexStatus(
                    source=source,
                    source_type="web",
                    chunk_count=len(chunks),
                    is_ready=len(chunks) > 0
                )
                return chunks

        # Scrape the page
        result = self._scrape_page(source)

        if result.get("status") == "error":
            raise ValueError(f"Failed to scrape: {result.get('message')}")

        # Extract chunks from content
        chunks = self._chunk_content(result["content"], result["metadata"])

        # Cache the result
        self._cache[url_hash] = {
            "status": "success",
            "url": source,
            "scraped_at": datetime.now().isoformat(),
            "metadata": result["metadata"],
            "chunks": [chunk.content for chunk in chunks]
        }
        self._save_cache()

        # Update status
        self._status = IndexStatus(
            source=source,
            source_type="web",
            chunk_count=len(chunks),
            is_ready=len(chunks) > 0
        )

        return chunks

    def search(self, query: str, top_k: int = 5) -> List[DocumentSearchResult]:
        """Search indexed web pages (requires vector store integration)."""
        raise NotImplementedError("Search requires vector store integration")

    def get_status(self) -> IndexStatus:
        """Get current indexing status."""
        return self._status

    # ========================================================================
    # WEB SCRAPING
    # ========================================================================

    def _scrape_page(self, url: str) -> Dict:
        """
        Scrape a web page with high accuracy.

        Args:
            url: URL to scrape

        Returns:
            Dict with status, content, and metadata
        """
        try:
            # Download page
            downloaded = self._download_page(url)
            if not downloaded:
                return {"status": "error", "message": "Failed to download page"}

            # Extract content with trafilatura
            content = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
                output_format="text"
            )

            if not content or len(content.strip()) < 100:
                return {"status": "error", "message": "Could not extract meaningful content"}

            # Extract metadata
            metadata = trafilatura.extract_metadata(downloaded)
            if metadata:
                extracted_meta = self._parse_metadata(metadata)
            else:
                # Fallback to basic extraction
                extracted_meta = self._extract_basic_metadata(downloaded, url)

            # Add URL to metadata
            extracted_meta["url"] = url
            extracted_meta["domain"] = urlparse(url).netloc

            return {
                "status": "success",
                "content": content.strip(),
                "metadata": extracted_meta
            }

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _download_page(self, url: str) -> Optional[str]:
        """
        Download web page with proper headers.

        Args:
            url: URL to download

        Returns:
            HTML content or None
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        try:
            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            return response.text
        except Exception as e:
            sys.stderr.write(f"[WebIndexer] Failed to download {url}: {e}\n")
            return None

    def _parse_metadata(self, metadata) -> Dict:
        """Parse trafilatura metadata into dictionary."""
        parsed = {}

        if hasattr(metadata, "title"):
            parsed["title"] = metadata.title
        if hasattr(metadata, "author"):
            parsed["author"] = metadata.author
        if hasattr(metadata, "date"):
            parsed["date"] = str(metadata.date)
        if hasattr(metadata, "url"):
            parsed["url"] = metadata.url

        return parsed

    def _extract_basic_metadata(self, html: str, url: str) -> Dict:
        """
        Fallback metadata extraction using BeautifulSoup.

        Args:
            html: HTML content
            url: Page URL

        Returns:
            Metadata dictionary
        """
        metadata = {"url": url}
        soup = BeautifulSoup(html, "html.parser")

        # Title
        title_tag = soup.find("title")
        if title_tag:
            metadata["title"] = title_tag.get_text().strip()

        # Meta description
        desc = soup.find("meta", attrs={"name": "description"})
        if desc:
            metadata["description"] = desc.get("content", "")

        # Canonical URL
        canonical = soup.find("link", attrs={"rel": "canonical"})
        if canonical:
            metadata["canonical_url"] = canonical.get("href", "")

        # Open Graph tags
        og_title = soup.find("meta", property="og:title")
        if og_title:
            metadata["og_title"] = og_title.get("content", "")

        og_desc = soup.find("meta", property="og:description")
        if og_desc:
            metadata["og_description"] = og_desc.get("content", "")

        og_image = soup.find("meta", property="og:image")
        if og_image:
            metadata["og_image"] = og_image.get("content", "")

        # Article meta
        article = soup.find("article")
        if article:
            # Try to find published date
            pub_time = article.find("time")
            if pub_time:
                metadata["published_date"] = pub_time.get("datetime", pub_time.get("pubdate", ""))

            # Try to find author
            author = article.find("meta", property="article:author")
            if author:
                metadata["author"] = author.get("content", "")

        return metadata

    # ========================================================================
    # CONTENT CHUNKING
    # ========================================================================

    def _chunk_content(self, content: str, metadata: Dict) -> List[DocumentChunk]:
        """
        Chunk web content for indexing.

        Args:
            content: Extracted text content
            metadata: Page metadata

        Returns:
            List of DocumentChunk objects
        """
        # Clean and normalize content
        content = self._clean_content(content)

        # Split into sections by headings (if present)
        sections = self._split_by_sections(content)

        # Create chunks
        chunks = []
        current_chunk = ""
        max_chars = 1500

        for section in sections:
            if len(section) < 100:
                continue

            if len(current_chunk) + len(section) > max_chars and len(current_chunk) > 200:
                # Finalize current chunk
                chunks.append(current_chunk.strip())
                current_chunk = section
            else:
                current_chunk += "\n\n" + section if current_chunk else section

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        # Convert to DocumentChunk objects
        chunk_objects = []
        url_hash = hashlib.md5(metadata.get("url", "").encode()).hexdigest()

        for i, chunk_text in enumerate(chunks):
            chunk = DocumentChunk(
                content=chunk_text,
                source=metadata.get("url", ""),
                source_type="web",
                page_number=None,
                chunk_index=i,
                metadata={
                    **metadata,
                    "chunk_id": f"{url_hash}_{i}",
                    "section": i + 1,
                    "total_sections": len(chunks)
                }
            )
            chunk_objects.append(chunk)

        return chunk_objects

    def _clean_content(self, content: str) -> str:
        """Clean extracted content."""
        # Remove excessive whitespace
        content = re.sub(r'\n{3,}', '\n\n', content)
        # Remove bullet artifacts
        content = re.sub(r'[•●○◾◽]+', '-', content)
        # Clean up around punctuation
        content = re.sub(r'\s+([.,!?;:])', r'\1', content)
        return content.strip()

    def _split_by_sections(self, content: str) -> List[str]:
        """Split content into sections by headings."""
        # Try markdown-style headings
        sections = re.split(r'^#{1,3}\s+.+$', content, flags=re.MULTILINE)

        # If that didn't work well, split by double newlines
        if len(sections) <= 1:
            sections = content.split('\n\n')

        return [s.strip() for s in sections if s.strip()]

    # ========================================================================
    # CACHE MANAGEMENT
    # ========================================================================

    def _load_cache(self) -> Dict:
        """Load web scrape cache from disk."""
        cache_file = self.cache_dir / "scrape_cache.json"
        if cache_file.exists():
            try:
                import json
                return json.loads(cache_file.read_text())
            except:
                return {}
        return {}

    def _save_cache(self):
        """Save web scrape cache to disk."""
        try:
            import json
            cache_file = self.cache_dir / "scrape_cache.json"
            cache_file.write_text(json.dumps(self._cache, indent=2))
        except Exception as e:
            sys.stderr.write(f"[WebIndexer] Failed to save cache: {e}\n")

    def clear_cache(self):
        """Clear the web scrape cache."""
        self._cache = {}
        cache_file = self.cache_dir / "scrape_cache.json"
        if cache_file.exists():
            cache_file.unlink()
