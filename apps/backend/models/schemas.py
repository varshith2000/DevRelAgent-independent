"""
Pydantic Models for DevRelAgent

Organized by domain:
- Perception models
- Memory models  
- Code search models
- Document search models (for team)
- Tool I/O models
- Action models
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime


# ============== Perception Models ==============

class PerceptionResult(BaseModel):
    """Result of analyzing user input."""
    user_input: str
    intent: Optional[str] = None
    entities: List[str] = Field(default_factory=list)
    tool_hint: Optional[str] = None
    repo_url: Optional[str] = None


# ============== Memory Models ==============

class MemoryItem(BaseModel):
    """Item stored in semantic memory."""
    text: str
    type: Literal["tool_output", "fact", "query", "code_chunk", "system"] = "fact"
    timestamp: Optional[str] = Field(default_factory=lambda: datetime.now().isoformat())
    tool_name: Optional[str] = None
    user_query: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class RepositoryState(BaseModel):
    """State of the currently indexed repository."""
    repo_url: Optional[str] = None
    repo_name: Optional[str] = None
    local_path: Optional[str] = None
    is_cloned: bool = False
    is_indexed: bool = False
    file_count: int = 0
    chunk_count: int = 0
    last_indexed: Optional[str] = None


# ============== Code Chunk Models ==============

class CodeChunk(BaseModel):
    """Represents a chunk of code (function, class, or text block)."""
    content: str
    file_path: str
    chunk_type: Literal["function", "class", "method", "text"] = "text"
    name: Optional[str] = None
    start_line: int = 0
    end_line: int = 0
    language: str = "python"
    docstring: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SearchResult(BaseModel):
    """Result from code search."""
    chunk: CodeChunk
    score: float
    rank: int


# ============== Document Search Models (For Team) ==============

class DocumentChunk(BaseModel):
    """A chunk of document content (for team to implement)."""
    content: str
    source: str                    # file path, URL, etc.
    source_type: Literal["pdf", "word", "text", "image", "web", "swagger"] = "text"
    page_number: Optional[int] = None
    chunk_index: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DocumentSearchResult(BaseModel):
    """Result from document search."""
    chunk: DocumentChunk
    score: float
    rank: int


class IndexStatus(BaseModel):
    """Status of a document index."""
    source: str
    source_type: str
    chunk_count: int = 0
    last_indexed: Optional[str] = None
    is_ready: bool = False


# ============== Tool I/O Models ==============

class CloneRepositoryInput(BaseModel):
    """Input for clone_repository tool."""
    repo_url: str


class CloneRepositoryOutput(BaseModel):
    """Output from clone_repository tool."""
    success: bool
    local_path: str
    message: str


class IndexRepositoryInput(BaseModel):
    """Input for index_repository tool."""
    repo_path: Optional[str] = None


class IndexRepositoryOutput(BaseModel):
    """Output from index_repository tool."""
    success: bool
    file_count: int
    chunk_count: int
    message: str


class SearchCodeInput(BaseModel):
    """Input for search_code tool."""
    query: str
    top_k: int = 5


class SearchCodeOutput(BaseModel):
    """Output from search_code tool."""
    results: List[Dict[str, Any]]
    total_found: int


class GetFileContentInput(BaseModel):
    """Input for get_file_content tool."""
    file_path: str


class GetFileContentOutput(BaseModel):
    """Output from get_file_content tool."""
    content: str
    file_path: str
    line_count: int


class ToolCallResult(BaseModel):
    """Result of executing a tool."""
    tool_name: str
    arguments: Dict[str, Any]
    result: Any
    success: bool = True
    error: Optional[str] = None


# ============== API Models ==============

class ChatRequest(BaseModel):
    """Chat API request."""
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Chat API response."""
    response: str
    session_id: str
    tool_calls: List[ToolCallResult] = Field(default_factory=list)
