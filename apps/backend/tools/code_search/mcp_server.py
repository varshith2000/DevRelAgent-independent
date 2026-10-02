"""
Code Search MCP Server — Repository tools exposed via MCP protocol

Adapted from CodeRepoSemanticSearch/repo_tools.py

Tools:
- clone_repository: Clone a GitHub repository
- index_repository: Index code for semantic search  
- search_code: Natural language code search
- get_file_content: Read file contents
- list_files: List files matching pattern
- get_repo_status: Get repository info
- load_repository: Load previously indexed repo
- list_indexed_repos: List all indexed repos
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from tools.code_search.code_chunker import detect_repo_language, get_chunker
from tools.code_search.config import IGNORE_PATTERNS, INDEX_DIR, REPOS_DIR, SUPPORTED_EXTENSIONS
from tools.code_search.vector_store import VectorMemory

# Initialize MCP server
mcp = FastMCP("CodeRepoSearch")

# Global state
_current_repo: Optional[str] = None
_vector_memory: Optional[VectorMemory] = None


def mcp_log(level: str, message: str):
    """Log to stderr (MCP uses stdout for JSON)."""
    sys.stderr.write(f"[MCP:{level}] {message}\n")
    sys.stderr.flush()


def _get_repo_name_from_url(url: str) -> str:
    """Extract repository name from GitHub URL."""
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    return url.split("/")[-1]


def _should_ignore(path: Path) -> bool:
    """Check if a path should be ignored during indexing."""
    name = path.name
    path_str = str(path)
    for pattern in IGNORE_PATTERNS:
        if pattern.startswith("*"):
            if name.endswith(pattern[1:]):
                return True
        elif pattern in path_str:
            return True
    return False


@mcp.tool()
def clone_repository(repo_url: str) -> str:
    """
    Clone a GitHub repository to the local repos directory.
    
    Args:
        repo_url: Full GitHub repository URL (e.g., https://github.com/user/repo)
    
    Returns:
        Status message with the local path
    """
    global _current_repo
    
    repo_name = _get_repo_name_from_url(repo_url)
    repo_path = REPOS_DIR / repo_name

    if repo_path.exists():
        _current_repo = str(repo_path)
        language = detect_repo_language(repo_path)
        return json.dumps({
            "success": True,
            "message": f"Repository '{repo_name}' already exists at {repo_path}",
            "local_path": str(repo_path),
            "repo_name": repo_name,
            "language": language,
        })

    try:
        mcp_log("INFO", f"Cloning {repo_url}...")
        result = subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(repo_path)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return json.dumps({
                "success": False,
                "message": f"Clone failed: {result.stderr.strip()}",
            })

        _current_repo = str(repo_path)
        language = detect_repo_language(repo_path)

        return json.dumps({
            "success": True,
            "message": f"Cloned '{repo_name}' successfully",
            "local_path": str(repo_path),
            "repo_name": repo_name,
            "language": language,
        })
    except subprocess.TimeoutExpired:
        return json.dumps({"success": False, "message": "Clone timed out (120s)"})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e)})


@mcp.tool()
def index_repository(repo_path: Optional[str] = None) -> str:
    """
    Index the repository code for semantic search.
    Creates embeddings for all code chunks and stores in FAISS index.
    
    Args:
        repo_path: Optional path to repository. Uses last cloned if not provided.
    
    Returns:
        Status with indexing statistics
    """
    global _current_repo, _vector_memory

    path = Path(repo_path) if repo_path else (Path(_current_repo) if _current_repo else None)
    if not path or not path.exists():
        return json.dumps({"success": False, "message": "No repository path provided or found"})

    repo_name = path.name
    mcp_log("INFO", f"Indexing {repo_name}...")

    # Detect language
    language = detect_repo_language(path)
    mcp_log("INFO", f"Primary language: {language}")

    # Get chunker
    chunker = get_chunker()

    # Collect and chunk files
    all_chunks = []
    file_count = 0
    skipped = 0

    for file_path in sorted(path.rglob("*")):
        if not file_path.is_file():
            continue
        if _should_ignore(file_path):
            continue

        ext = file_path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            if not content.strip():
                continue

            rel_path = str(file_path.relative_to(path))
            file_lang = SUPPORTED_EXTENSIONS.get(ext, "text")
            chunks = chunker.chunk_file(rel_path, content, file_lang)
            all_chunks.extend(chunks)
            file_count += 1
        except Exception as e:
            skipped += 1
            mcp_log("WARN", f"Skipped {file_path.name}: {e}")

    if not all_chunks:
        return json.dumps({
            "success": False,
            "message": f"No code chunks found in {repo_name}",
        })

    mcp_log("INFO", f"Found {len(all_chunks)} chunks from {file_count} files")

    # Build vector index
    _vector_memory = VectorMemory(repo_name=repo_name)
    added = _vector_memory.add_chunks(all_chunks)
    _vector_memory.save()

    _current_repo = str(path)

    return json.dumps({
        "success": True,
        "message": f"Indexed {repo_name}: {added} chunks from {file_count} files",
        "repo_name": repo_name,
        "file_count": file_count,
        "chunk_count": added,
        "total_chunks_found": len(all_chunks),
        "skipped_files": skipped,
        "language": language,
    })


@mcp.tool()
def search_code(query: str, top_k: int = 5) -> str:
    """
    Search for relevant code using natural language.
    
    Args:
        query: Natural language search query
        top_k: Number of results to return (default: 5)
    
    Returns:
        Matching code chunks with file paths and scores
    """
    if not _vector_memory or not _vector_memory.is_ready:
        return json.dumps({
            "success": False,
            "message": "No repository indexed. Use index_repository first.",
        })

    results = _vector_memory.search(query, top_k=top_k)

    if not results:
        return json.dumps({
            "success": True,
            "results": [],
            "total_found": 0,
            "message": "No matching code found",
        })

    formatted = []
    for chunk, score in results:
        formatted.append({
            "file_path": chunk.file_path,
            "name": chunk.name,
            "type": chunk.chunk_type,
            "language": chunk.language,
            "lines": f"{chunk.start_line}-{chunk.end_line}",
            "score": round(score, 4),
            "content": chunk.content[:1000],
            "docstring": chunk.docstring,
        })

    return json.dumps({
        "success": True,
        "results": formatted,
        "total_found": len(formatted),
        "query": query,
    })


@mcp.tool()
def get_file_content(file_path: str) -> str:
    """
    Get the full content of a file in the repository.
    
    Args:
        file_path: Relative path to the file within the repository
    """
    if not _current_repo:
        return json.dumps({"success": False, "message": "No repository loaded"})

    full_path = Path(_current_repo) / file_path
    if not full_path.exists():
        return json.dumps({"success": False, "message": f"File not found: {file_path}"})

    try:
        content = full_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.split("\n")
        numbered = "\n".join(f"{i+1:4d} | {line}" for i, line in enumerate(lines))
        return json.dumps({
            "success": True,
            "file_path": file_path,
            "content": numbered,
            "line_count": len(lines),
        })
    except Exception as e:
        return json.dumps({"success": False, "message": str(e)})


@mcp.tool()
def list_files(pattern: str = "*.py") -> str:
    """
    List files in the repository matching a pattern.
    
    Args:
        pattern: Glob pattern to match files (default: *.py)
    """
    if not _current_repo:
        return json.dumps({"success": False, "message": "No repository loaded"})

    repo_path = Path(_current_repo)
    matches = []
    for f in sorted(repo_path.rglob(pattern)):
        if f.is_file() and not _should_ignore(f):
            matches.append(str(f.relative_to(repo_path)))

    return json.dumps({
        "success": True,
        "files": matches[:100],
        "total_count": len(matches),
        "pattern": pattern,
        "truncated": len(matches) > 100,
    })


@mcp.tool()
def get_repo_status() -> str:
    """Get the current status of the loaded repository."""
    if not _current_repo:
        return json.dumps({
            "success": True,
            "loaded": False,
            "message": "No repository loaded",
        })

    repo_path = Path(_current_repo)
    repo_name = repo_path.name
    is_indexed = _vector_memory is not None and _vector_memory.is_ready

    # Count files
    file_count = sum(
        1 for f in repo_path.rglob("*")
        if f.is_file() and not _should_ignore(f) and f.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    language = detect_repo_language(repo_path)

    return json.dumps({
        "success": True,
        "loaded": True,
        "repo_name": repo_name,
        "local_path": str(repo_path),
        "language": language,
        "is_indexed": is_indexed,
        "file_count": file_count,
        "chunk_count": _vector_memory.total_chunks if _vector_memory else 0,
    })


@mcp.tool()
def load_repository(repo_name: str) -> str:
    """
    Load a previously cloned and indexed repository.
    
    Args:
        repo_name: Name of the repository to load
    """
    global _current_repo, _vector_memory

    repo_path = REPOS_DIR / repo_name
    if not repo_path.exists():
        return json.dumps({"success": False, "message": f"Repository '{repo_name}' not found in repos/"})

    _current_repo = str(repo_path)
    language = detect_repo_language(repo_path)

    # Try to load saved index
    _vector_memory = VectorMemory(repo_name=repo_name)
    index_loaded = _vector_memory.load()

    return json.dumps({
        "success": True,
        "repo_name": repo_name,
        "local_path": str(repo_path),
        "language": language,
        "index_loaded": index_loaded,
        "chunk_count": _vector_memory.total_chunks if index_loaded else 0,
        "message": f"Loaded '{repo_name}'" + (" with index" if index_loaded else " (no index — run index_repository)"),
    })


@mcp.tool()
def list_indexed_repos() -> str:
    """List all repositories that have been cloned and indexed."""
    repos = []
    if REPOS_DIR.exists():
        for d in sorted(REPOS_DIR.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                index_dir = INDEX_DIR / d.name
                has_index = (index_dir / "faiss.index").exists()

                # Read meta if available
                meta = {}
                meta_path = index_dir / "meta.json"
                if meta_path.exists():
                    try:
                        with open(meta_path) as f:
                            meta = json.load(f)
                    except Exception:
                        pass

                repos.append({
                    "name": d.name,
                    "path": str(d),
                    "has_index": has_index,
                    "chunk_count": meta.get("chunk_count", 0),
                })

    return json.dumps({
        "success": True,
        "repos": repos,
        "total": len(repos),
    })


# ─── Entry point for standalone MCP server ────────────
if __name__ == "__main__":
    mcp_log("INFO", "Starting Code Repository Search MCP server...")
    mcp.run(transport="stdio")
