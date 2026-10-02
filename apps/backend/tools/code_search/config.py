"""
Code Search Tool — Configuration

Paths, embedding settings, supported extensions, and ignore patterns.
Adapted from CodeRepoSemanticSearch/config.py
"""

from pathlib import Path

from config.settings import get_settings

_settings = get_settings()

# Base paths (relative to project root)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent.resolve()
DATA_DIR = PROJECT_ROOT / "data"
REPOS_DIR = DATA_DIR / "repos"
INDEX_DIR = DATA_DIR / "code_index"

# Create directories
REPOS_DIR.mkdir(parents=True, exist_ok=True)
INDEX_DIR.mkdir(parents=True, exist_ok=True)

# Ollama Embedding Settings
OLLAMA_BASE_URL = _settings.ollama_base_url
OLLAMA_EMBED_URL = _settings.resolved_ollama_embed_url
OLLAMA_URL = _settings.resolved_ollama_generate_url  # For vision models
EMBED_MODEL = _settings.embed_model
EMBED_DIMENSION = 768  # nomic-embed-text dimension
VISION_MODEL = _settings.vision_model  # For image captioning

# Chunking Settings
CHUNK_SIZE = 256   # words per chunk (text fallback)
CHUNK_OVERLAP = 40

# Agent Settings
MAX_AGENT_STEPS = 10

# Supported file extensions for indexing
SUPPORTED_EXTENSIONS = {
    # AST-based chunking
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".java": "java",
    ".rs": "rust",
    ".go": "go",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".rb": "ruby",
    # Text-based chunking
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".cs": "csharp",
    ".md": "markdown",
    ".txt": "text",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
}

# Files/directories to ignore during indexing
IGNORE_PATTERNS = [
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    "node_modules",
    ".pytest_cache",
    "*.pyc",
    "*.pyo",
    ".env",
    ".idea",
    ".vscode",
    ".DS_Store",
    "dist",
    "build",
    ".next",
    "coverage",
]

# Tree-sitter parser module mapping
PARSER_MODULES = {
    "python": "tree_sitter_python",
    "javascript": "tree_sitter_javascript",
    "typescript": "tree_sitter_typescript",
    "java": "tree_sitter_java",
    "rust": "tree_sitter_rust",
    "go": "tree_sitter_go",
    "c": "tree_sitter_c",
    "cpp": "tree_sitter_cpp",
    "ruby": "tree_sitter_ruby",
}
