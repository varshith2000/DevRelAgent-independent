"""
Code Chunker — Multi-language AST-based code chunking

Adapted from CodeRepoSemanticSearch/code_chunker.py

Features:
- Intelligent language detection for repositories
- AST parsing for Python, JavaScript, TypeScript, Java, Rust, Go, C/C++, Ruby
- Automatic fallback to text-based chunking when parser unavailable
- Dynamic tree-sitter parser loading
"""

import sys
from pathlib import Path
from typing import List, Dict, Optional, Any

from tools.code_search.config import (
    SUPPORTED_EXTENSIONS, PARSER_MODULES, CHUNK_SIZE, CHUNK_OVERLAP
)

# Import CodeChunk from models — handle both direct and package execution
try:
    from models.schemas import CodeChunk
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from models.schemas import CodeChunk


# Node types for extracting code elements per language
LANGUAGE_NODE_TYPES = {
    "python": {
        "function": ["function_definition"],
        "class": ["class_definition"],
        "method": ["function_definition"],
    },
    "javascript": {
        "function": ["function_declaration", "arrow_function", "function"],
        "class": ["class_declaration"],
        "method": ["method_definition"],
    },
    "typescript": {
        "function": ["function_declaration", "arrow_function"],
        "class": ["class_declaration", "interface_declaration"],
        "method": ["method_definition"],
    },
    "java": {
        "function": ["method_declaration", "constructor_declaration"],
        "class": ["class_declaration", "interface_declaration"],
        "method": ["method_declaration"],
    },
    "rust": {
        "function": ["function_item"],
        "class": ["struct_item", "impl_item", "enum_item"],
        "method": ["function_item"],
    },
    "go": {
        "function": ["function_declaration", "method_declaration"],
        "class": ["type_declaration"],
        "method": ["method_declaration"],
    },
    "c": {
        "function": ["function_definition"],
        "class": ["struct_specifier"],
        "method": [],
    },
    "cpp": {
        "function": ["function_definition"],
        "class": ["class_specifier", "struct_specifier"],
        "method": ["function_definition"],
    },
    "ruby": {
        "function": ["method"],
        "class": ["class", "module"],
        "method": ["method"],
    },
}


def log(msg: str):
    """Log to stderr."""
    sys.stderr.write(f"[chunker] {msg}\n")
    sys.stderr.flush()


class LanguageDetector:
    """Intelligent language detection for repositories by analyzing file extensions."""

    EXTENSION_MAP = {
        ".py": "python", ".pyw": "python",
        ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
        ".ts": "typescript", ".tsx": "typescript",
        ".java": "java",
        ".rs": "rust",
        ".go": "go",
        ".c": "c", ".h": "c",
        ".cpp": "cpp", ".hpp": "cpp", ".cc": "cpp", ".cxx": "cpp",
        ".rb": "ruby",
        ".php": "php",
        ".swift": "swift",
        ".kt": "kotlin",
        ".scala": "scala",
        ".cs": "csharp",
    }

    @staticmethod
    def detect_repo_language(repo_path: Path) -> str:
        """
        Detect the primary programming language of a repository.
        
        Args:
            repo_path: Path to the repository
            
        Returns:
            Primary language name (e.g., "python", "javascript")
        """
        counts: Dict[str, int] = {}
        try:
            for f in repo_path.rglob("*"):
                if f.is_file() and not any(p in str(f) for p in [".git", "node_modules", "__pycache__", ".venv"]):
                    lang = LanguageDetector.EXTENSION_MAP.get(f.suffix.lower())
                    if lang:
                        counts[lang] = counts.get(lang, 0) + 1
        except Exception:
            pass

        if not counts:
            return "python"  # default
        return max(counts, key=counts.get)

    @staticmethod
    def get_file_language(file_path: str) -> Optional[str]:
        """Get the language of a file based on its extension."""
        ext = Path(file_path).suffix.lower()
        return SUPPORTED_EXTENSIONS.get(ext)


class MultiLanguageChunker:
    """
    Multi-language code chunker with AST parsing support.
    Dynamically loads tree-sitter parsers for detected languages.
    Falls back to text-based chunking if no parser available.
    """

    def __init__(self):
        self.parsers: Dict[str, Any] = {}
        self.available_languages: set = set()
        self._detect_available_parsers()

    def _detect_available_parsers(self):
        """Detect which tree-sitter language parsers are installed."""
        for lang, module_name in PARSER_MODULES.items():
            try:
                __import__(module_name)
                self.available_languages.add(lang)
            except ImportError:
                pass

        if self.available_languages:
            log(f"Available AST parsers: {', '.join(sorted(self.available_languages))}")
        else:
            log("No AST parsers found — will use text-based chunking")

    def _get_parser(self, language: str):
        """Get or create a parser for the specified language."""
        if language in self.parsers:
            return self.parsers[language]

        if language not in self.available_languages:
            return None

        try:
            import tree_sitter
            module_name = PARSER_MODULES[language]
            lang_module = __import__(module_name)

            # tree-sitter >= 0.23: language() returns PyCapsule → wrap in Language()
            capsule = lang_module.language()
            lang_obj = tree_sitter.Language(capsule)
            parser = tree_sitter.Parser(lang_obj)

            self.parsers[language] = parser
            return parser
        except Exception as e:
            log(f"Failed to load parser for {language}: {e}")
            self.available_languages.discard(language)
            return None

    def chunk_file(self, file_path: str, content: str, language: str = None) -> List[CodeChunk]:
        """
        Chunk a file's content into semantic units.
        
        Uses AST parsing when a tree-sitter parser is available,
        otherwise falls back to text-based chunking.
        
        Args:
            file_path: Path to the file
            content: File content
            language: Programming language (auto-detected if None)
            
        Returns:
            List of CodeChunk objects
        """
        if not content.strip():
            return []

        if language is None:
            language = LanguageDetector.get_file_language(file_path) or "text"

        parser = self._get_parser(language)
        if parser and language in LANGUAGE_NODE_TYPES:
            try:
                chunks = self._chunk_with_ast(file_path, content, language, parser)
                if chunks:
                    return chunks
            except Exception as e:
                log(f"AST chunking failed for {file_path}: {e}")

        return self._chunk_text(file_path, content, language)

    def _chunk_with_ast(self, file_path: str, content: str, language: str, parser) -> List[CodeChunk]:
        """Chunk code using AST parsing."""
        tree = parser.parse(bytes(content, "utf-8"))
        root = tree.root_node

        node_types = LANGUAGE_NODE_TYPES.get(language, {})
        function_types = node_types.get("function", [])
        class_types = node_types.get("class", [])
        method_types = node_types.get("method", [])

        chunks: List[CodeChunk] = []
        self._extract_nodes(
            root, content, file_path, language,
            function_types, class_types, method_types, chunks
        )
        return chunks

    def _extract_nodes(
        self, node, content: str, file_path: str, language: str,
        function_types: List[str], class_types: List[str], method_types: List[str],
        chunks: List[CodeChunk], class_name: str = None
    ):
        """Recursively extract code nodes from AST."""
        node_type = node.type

        if node_type in class_types:
            chunk = self._create_chunk(node, content, file_path, language, "class")
            if chunk:
                chunks.append(chunk)
                name = self._get_node_name(node, language) or "UnknownClass"
                for child in node.children:
                    self._extract_nodes(
                        child, content, file_path, language,
                        function_types, class_types, method_types,
                        chunks, class_name=name
                    )
            return

        if node_type in function_types:
            chunk_type = "method" if class_name else "function"
            chunk = self._create_chunk(node, content, file_path, language, chunk_type, class_name)
            if chunk:
                chunks.append(chunk)
            return

        for child in node.children:
            self._extract_nodes(
                child, content, file_path, language,
                function_types, class_types, method_types,
                chunks, class_name=class_name
            )

    def _create_chunk(
        self, node, content: str, file_path: str, language: str,
        chunk_type: str, class_name: str = None
    ) -> Optional[CodeChunk]:
        """Create a CodeChunk from an AST node."""
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        node_text = content[node.start_byte:node.end_byte]

        if not node_text.strip():
            return None

        name = self._get_node_name(node, language)
        if class_name and name:
            name = f"{class_name}.{name}"

        docstring = self._get_docstring(node, content, language)

        return CodeChunk(
            content=node_text,
            file_path=file_path,
            chunk_type=chunk_type,
            name=name,
            start_line=start_line,
            end_line=end_line,
            language=language,
            docstring=docstring,
            metadata={"class_name": class_name} if class_name else {},
        )

    def _get_node_name(self, node, language: str) -> Optional[str]:
        """Get the name of a node (function/class name)."""
        for child in node.children:
            if child.type in ("identifier", "name", "type_identifier", "property_identifier"):
                return child.text.decode("utf-8") if isinstance(child.text, bytes) else child.text
        return None

    def _get_docstring(self, node, content: str, language: str) -> Optional[str]:
        """Extract docstring/comment from a node."""
        for child in node.children:
            if child.type == "block":
                for block_child in child.children:
                    if block_child.type == "expression_statement":
                        for expr_child in block_child.children:
                            if expr_child.type == "string":
                                text = expr_child.text
                                if isinstance(text, bytes):
                                    text = text.decode("utf-8")
                                return text.strip("\"'")
        return None

    def _chunk_text(self, file_path: str, content: str, language: str) -> List[CodeChunk]:
        """Text-based chunking for unsupported languages or fallback."""
        lines = content.split("\n")
        chunks: List[CodeChunk] = []
        words = content.split()
        total_words = len(words)

        if total_words <= CHUNK_SIZE:
            chunks.append(CodeChunk(
                content=content,
                file_path=file_path,
                chunk_type="text",
                name=Path(file_path).name,
                start_line=1,
                end_line=len(lines),
                language=language,
            ))
            return chunks

        # Split into overlapping chunks
        start_idx = 0
        chunk_num = 0
        while start_idx < total_words:
            end_idx = min(start_idx + CHUNK_SIZE, total_words)
            chunk_words = words[start_idx:end_idx]
            chunk_content = " ".join(chunk_words)

            # Estimate line numbers
            char_start = len(" ".join(words[:start_idx])) if start_idx > 0 else 0
            char_end = len(" ".join(words[:end_idx]))
            start_line = content[:char_start].count("\n") + 1
            end_line = content[:char_end].count("\n") + 1

            chunk_num += 1
            chunks.append(CodeChunk(
                content=chunk_content,
                file_path=file_path,
                chunk_type="text",
                name=f"{Path(file_path).name}:chunk_{chunk_num}",
                start_line=start_line,
                end_line=end_line,
                language=language,
            ))

            start_idx += CHUNK_SIZE - CHUNK_OVERLAP
            if end_idx >= total_words:
                break

        return chunks


# ─── Singleton ────────────────────────────────────────

_chunker: Optional[MultiLanguageChunker] = None


def get_chunker() -> MultiLanguageChunker:
    """Get the singleton MultiLanguageChunker instance."""
    global _chunker
    if _chunker is None:
        _chunker = MultiLanguageChunker()
    return _chunker


def detect_repo_language(repo_path: Path) -> str:
    """Convenience function to detect repository language."""
    return LanguageDetector.detect_repo_language(repo_path)
