"""
Simple Code Search — Repository tools without MCP dependency

This is a simplified version of the code search functionality that doesn't require MCP.
It provides basic code search capabilities for demo purposes.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.code_search.code_chunker import detect_repo_language, get_chunker
from tools.code_search.config import IGNORE_PATTERNS, INDEX_DIR, REPOS_DIR, SUPPORTED_EXTENSIONS
from tools.code_search.vector_store import VectorMemory


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


# Global state
_current_repo: Optional[str] = None
_vector_memory: Optional[VectorMemory] = None


async def search_code(query: str, top_k: int = 5) -> Dict[str, Any]:
    """
    Search code semantically using natural language queries.

    Args:
        query: Natural language code search query
        top_k: Number of results to return

    Returns:
        Dictionary with search results
    """
    global _current_repo, _vector_memory

    if _vector_memory is None:
        return {
            "success": False,
            "error": "No repository indexed. Please index a repository first."
        }

    try:
        results = _vector_memory.search(query, top_k=top_k)

        formatted_results = []
        for result in results:
            formatted_results.append({
                "file_path": result.get("file_path", ""),
                "content": result.get("content", "")[:200],  # First 200 chars
                "score": result.get("score", 0.0),
                "start_line": result.get("start_line", 0),
                "end_line": result.get("end_line", 0)
            })

        return {
            "success": True,
            "query": query,
            "results": formatted_results,
            "total": len(formatted_results)
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


async def get_file_content(file_path: str) -> Dict[str, Any]:
    """
    Read and return file contents.

    Args:
        file_path: Path to the file (relative to repo root)

    Returns:
        Dictionary with file content
    """
    global _current_repo

    if _current_repo is None:
        return {
            "success": False,
            "error": "No repository loaded"
        }

    try:
        repo_path = Path(_current_repo)
        full_path = repo_path / file_path

        if not full_path.exists():
            return {
                "success": False,
                "error": f"File not found: {file_path}"
            }

        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()

        return {
            "success": True,
            "file_path": file_path,
            "content": content,
            "size": len(content)
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


async def list_files(pattern: str = "*.py") -> Dict[str, Any]:
    """
    List files matching pattern.

    Args:
        pattern: File pattern (e.g., "*.py", "test_*.py")

    Returns:
        Dictionary with list of files
    """
    global _current_repo

    if _current_repo is None:
        return {
            "success": False,
            "error": "No repository loaded"
        }

    try:
        repo_path = Path(_current_repo)
        matching_files = []

        for file_path in repo_path.rglob(pattern):
            if not _should_ignore(file_path):
                rel_path = file_path.relative_to(repo_path)
                matching_files.append(str(rel_path))

        return {
            "success": True,
            "pattern": pattern,
            "files": matching_files,
            "total": len(matching_files)
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


async def get_repo_status() -> Dict[str, Any]:
    """
    Get current repository status.

    Returns:
        Dictionary with repository info
    """
    global _current_repo, _vector_memory

    if _current_repo is None:
        return {
            "success": True,
            "current_repo": None,
            "indexed": False
        }

    repo_path = Path(_current_repo)
    language = detect_repo_language(repo_path)

    return {
        "success": True,
        "current_repo": _current_repo,
        "repo_name": repo_path.name,
        "indexed": _vector_memory is not None,
        "language": language
    }


async def load_repository(repo_name: str) -> Dict[str, Any]:
    """
    Load a previously indexed repository.

    Args:
        repo_name: Name of the repository

    Returns:
        Dictionary with load status
    """
    global _current_repo, _vector_memory

    repo_path = REPOS_DIR / repo_name
    index_path = INDEX_DIR / f"{repo_name}_index.faiss"

    if not repo_path.exists():
        return {
            "success": False,
            "error": f"Repository '{repo_name}' not found at {repo_path}"
        }

    if not index_path.exists():
        return {
            "success": False,
            "error": f"No index found for '{repo_name}'. Please index the repository first."
        }

    try:
        _current_repo = str(repo_path)
        _vector_memory = VectorMemory(str(index_path))

        return {
            "success": True,
            "repo_name": repo_name,
            "repo_path": str(repo_path),
            "index_path": str(index_path)
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


async def list_indexed_repos() -> Dict[str, Any]:
    """
    List all indexed repositories.

    Returns:
        Dictionary with list of indexed repositories
    """
    try:
        indexed = []
        if INDEX_DIR.exists():
            for index_file in INDEX_DIR.glob("*_index.faiss"):
                repo_name = index_file.name.replace("_index.faiss", "")
                indexed.append(repo_name)

        return {
            "success": True,
            "repositories": indexed,
            "total": len(indexed)
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
