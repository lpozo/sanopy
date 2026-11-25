"""Context extraction and project summary utilities for linters."""

import ast
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

__all__ = [
    "CONTENT_NOT_SUPPLIED",
    "ContentArg",
    "ContentCache",
    "ProjectScanner",
    "ProjectSummary",
    "SnippetProvider",
    "SourceAnalyzer",
    "SymbolInfo",
    "get_linter_context",
    "read_file_content",
]


class _ContentNotSupplied:  # pylint: disable=too-few-public-methods
    """Sentinel type for an omitted ``content`` argument."""

    __slots__ = ()


#: Default for ``content`` parameters. It distinguishes "the caller did
#: not supply content" from an explicit ``None``, which means "the file
#: was read and found unreadable — do not try to read it again".
CONTENT_NOT_SUPPLIED = _ContentNotSupplied()

#: Value accepted by the ``content`` parameter of the context helpers.
type ContentArg = str | None | _ContentNotSupplied


@dataclass
class SymbolInfo:
    """Information about a public symbol (class or function).

    Attributes:
        name: The unqualified symbol name.
        kind: Either ``"class"`` or ``"function"``.
        line: The 1-indexed line where the symbol is defined.
        file_path: Path to the file containing the symbol.
    """

    name: str
    kind: Literal["class", "function"]
    line: int
    file_path: Path


def read_file_content(file_path: Path) -> str | None:
    """Read a file's text content, returning None when it is unreadable.

    Args:
        file_path: Path to the target file.

    Returns:
        The file's UTF-8 text content, or None if the file is missing,
        not readable, or not valid UTF-8.
    """
    try:
        return file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


class _ParsedFile:  # pylint: disable=too-few-public-methods
    """A source file parsed once and indexed for context lookups.

    Building the line-to-block index once per file turns semantic context
    lookup from an AST walk per finding into a dictionary lookup, which
    matters for files with many findings.
    """

    __slots__ = (
        "_fallback_context",
        "_line_context",
        "_tree",
        "content",
        "lines",
    )

    def __init__(self, content: str) -> None:
        self.content = content
        self.lines = content.splitlines()
        self._fallback_context: dict[int, tuple[int, str]] = {}
        try:
            self._tree: ast.AST | None = ast.parse(content)
        except SyntaxError:
            self._tree = None
        self._line_context: dict[int, tuple[int, str]] = (
            self._build_line_context(self._tree)
            if self._tree is not None
            else {}
        )

    @staticmethod
    def _build_line_context(tree: ast.AST) -> dict[int, tuple[int, str]]:
        """Map each line to its innermost function/class context.

        ``ast.walk`` yields parents before children, so assigning every
        line of each node in walk order leaves the innermost block in
        place for nested definitions.
        """
        context: dict[int, tuple[int, str]] = {}
        for node in ast.walk(tree):
            if not isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                continue
            kind = "class" if isinstance(node, ast.ClassDef) else "def"
            info = f"in {kind} {node.name}"
            end = getattr(node, "end_lineno", node.lineno)
            for line in range(node.lineno, end + 1):
                context[line] = (node.lineno - 1, info)
        return context

    def extract(
        self,
        line_start: int,
        line_end: int | None,
        context_lines: int,
    ) -> str:
        """Extract a raw snippet using the already-split source lines."""
        start_index = max(0, line_start - 1 - context_lines)
        if line_end is None:
            end_index = min(len(self.lines), line_start + context_lines)
        else:
            end_index = min(len(self.lines), line_end + context_lines)
        return "\n".join(self.lines[start_index:end_index])

    def find_context_bounds(self, line_start: int) -> tuple[int, str]:
        """Return the semantic context for a line from the cached index."""
        if self._tree is None:
            return self._fallback(line_start)

        context = self._line_context.get(line_start)
        if context is not None:
            return context
        return max(0, line_start - 10), "in module scope"

    def _fallback(self, line_start: int) -> tuple[int, str]:
        """Find context by string search when the file is not valid AST."""
        cached = self._fallback_context.get(line_start)
        if cached is not None:
            return cached

        current_idx = line_start - 1
        for i in range(current_idx, -1, -1):
            if i >= len(self.lines):
                continue
            line = self.lines[i].strip()
            if line.startswith(("def ", "class ")):
                name = line.split("(")[0].split(":")[0].strip()
                result = (i, f"in {name}")
                break
        else:
            result = (max(0, current_idx - 10), "in module scope")

        self._fallback_context[line_start] = result
        return result


class ContentCache:  # pylint: disable=too-few-public-methods
    """Per-parse cache of file reads and parsed context indexes.

    ``get`` reads each path at most once: a file that is missing or not
    valid UTF-8 is remembered as ``None``. ``get_parsed`` then parses the
    content and builds its block index at most once, so later findings in
    the same file only perform dictionary lookups.
    """

    def __init__(self) -> None:
        """Initialise an empty cache."""
        self._entries: dict[Path, str | None] = {}
        self._parsed: dict[Path, _ParsedFile | None] = {}

    def get(self, file_path: Path) -> str | None:
        """Return the file's content, reading it at most once.

        Args:
            file_path: Path to the target file.

        Returns:
            The file's UTF-8 text, or None when it is unreadable.
        """
        if file_path not in self._entries:
            self._entries[file_path] = read_file_content(file_path)
        return self._entries[file_path]

    def get_parsed(self, file_path: Path) -> _ParsedFile | None:
        """Return the parsed file, parsing it at most once.

        Args:
            file_path: Path to the target file.

        Returns:
            The parsed source, or None when the file is unreadable.
        """
        if file_path not in self._parsed:
            content = self.get(file_path)
            self._parsed[file_path] = (
                _ParsedFile(content) if content is not None else None
            )
        return self._parsed[file_path]


def _resolve_content(file_path: Path, content: ContentArg) -> str | None:
    """Resolve a ``content`` argument to text, or None when unreadable.

    Args:
        file_path: Path to the target file.
        content: Caller-supplied content, ``None`` for a file already
            known to be unreadable, or the "not supplied" sentinel.

    Returns:
        The file content to work with, or None when there is none.
    """
    if isinstance(content, _ContentNotSupplied):
        return read_file_content(file_path) if file_path.is_file() else None
    return content


@dataclass
class ProjectSummary:
    """Compact summary of a target project.

    Attributes:
        file_tree: Relative path strings for discovered Python files.
        public_symbols: Top-level public classes and functions found.
        target_config: Parsed linter configuration sections from
            ``pyproject.toml``, keyed by tool name (e.g., ``"ruff"``).
    """

    file_tree: list[str] = field(default_factory=list)
    public_symbols: list[SymbolInfo] = field(default_factory=list)
    target_config: dict[str, Any] = field(default_factory=dict)


class SnippetProvider:
    """Handles extraction and formatting of code snippets."""

    @staticmethod
    def extract(
        file_path: Path,
        line_start: int,
        line_end: int | None = None,
        context_lines: int = 5,
        content: ContentArg = CONTENT_NOT_SUPPLIED,
    ) -> str:
        """Extract a raw snippet of code without line numbers.

        Args:
            file_path: Path to the target file.
            line_start: 1-indexed starting line number.
            line_end: 1-indexed ending line number (optional).
            context_lines: Number of surrounding lines to include.
            content: Pre-read file content to avoid re-reading the file.
                Omit to read the file; pass ``None`` when the file is
                already known to be unreadable.

        Returns:
            The raw string content of the snippet.
        """
        content = _resolve_content(file_path, content)
        if content is None:
            return ""

        lines = content.splitlines()

        # Find bounds
        start_index = max(0, line_start - 1 - context_lines)
        if line_end is None:
            end_index = min(len(lines), line_start + context_lines)
        else:
            end_index = min(len(lines), line_end + context_lines)

        return "\n".join(lines[start_index:end_index])

    @staticmethod
    def format(snippet: str, start_line: int) -> str:
        """Add line numbers to a raw snippet for terminal display.

        Args:
            snippet: The raw code snippet.
            start_line: The 1-indexed line number of the first line.

        Returns:
            A formatted string with line numbers.
        """
        if not snippet:
            return ""

        lines = snippet.splitlines()
        return "\n".join(
            f"{start_line + i:4d} | {line}" for i, line in enumerate(lines)
        )


class SourceAnalyzer:
    """Analyzes Python source code for semantic context and symbols."""

    @staticmethod
    def find_context_bounds(
        file_path: Path,
        line_start: int,
        content: ContentArg = CONTENT_NOT_SUPPLIED,
    ) -> tuple[int, str]:
        """Find the semantic context (function/class) containing the line.

        Args:
            file_path: Path to the target file.
            line_start: Line number where the error occurred.
            content: Pre-read file content to avoid re-reading the file.
                Omit to read the file; pass ``None`` when the file is
                already known to be unreadable.

        Returns:
            A tuple of (start_index, info_string).
        """
        content = _resolve_content(file_path, content)
        if content is None:
            return 0, "unknown context"

        return _ParsedFile(content).find_context_bounds(line_start)

    @staticmethod
    def extract_symbols(
        file_path: Path, root_path: Path | None = None
    ) -> list[SymbolInfo]:
        """Extract top-level public classes and functions from a file.

        Args:
            file_path: Path to the .py file.
            root_path: Optional project root for relative paths.

        Returns:
            List of SymbolInfo objects (limit 10).
        """
        symbols = []
        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content)
            for node in tree.body:
                if isinstance(
                    node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
                ) and not node.name.startswith("_"):
                    kind: Literal["class", "function"] = (
                        "class"
                        if isinstance(node, ast.ClassDef)
                        else "function"
                    )
                    symbols.append(
                        SymbolInfo(
                            name=node.name,
                            kind=kind,
                            line=node.lineno,
                            file_path=file_path.relative_to(root_path)
                            if root_path
                            else file_path,
                        )
                    )
        except (OSError, UnicodeDecodeError, SyntaxError):
            pass
        return symbols[:10]


class ProjectScanner:
    """Scans projects to generate compact context summaries."""

    @staticmethod
    def scan_project(target_path: Path) -> ProjectSummary:
        """Generate a compact summary of the target project."""
        summary = ProjectSummary()
        if target_path.is_file():
            summary.file_tree = [target_path.name]
            summary.public_symbols.extend(
                SourceAnalyzer.extract_symbols(target_path)
            )
            return summary

        summary.target_config = ProjectScanner.parse_config(target_path)
        python_files = list(target_path.rglob("*.py"))
        target_files = sorted(python_files)[:50]

        for py_file in target_files:
            rel_path = py_file.relative_to(target_path)
            summary.file_tree.append(str(rel_path))

            if "__init__" not in py_file.name:
                summary.public_symbols.extend(
                    SourceAnalyzer.extract_symbols(py_file, target_path)
                )

        return summary

    @staticmethod
    def parse_config(target_path: Path) -> dict[str, Any]:
        """Search for and parse linter configurations from pyproject.toml."""
        config_data: dict[str, Any] = {}
        pyproject = target_path / "pyproject.toml"

        if pyproject.is_file():
            try:
                with pyproject.open("rb") as f:
                    data = tomllib.load(f)
                    tool = data.get("tool", {})
                    for key in ["ruff", "pylint", "mypy", "vulture"]:
                        if key in tool:
                            config_data[key] = tool[key]
            except (OSError, ValueError):
                pass

        return config_data


def get_linter_context(
    file_path: Path,
    line_start: int,
    line_end: int | None = None,
    context_lines: int = 10,
    content: ContentArg = CONTENT_NOT_SUPPLIED,
    cache: ContentCache | None = None,
) -> tuple[str, int, str]:
    """Helper for linters to get snippet and context in one call.

    Args:
        file_path: Path to the target file.
        line_start: Line number where the error occurred.
        line_end: 1-indexed ending line number (optional).
        context_lines: Number of surrounding lines to include.
        content: Pre-read file content to avoid re-reading the file.
            Omit to read the file; pass ``None`` when the file is already
            known to be unreadable.
        cache: Per-parse cache. When supplied, each file is read, parsed,
            and indexed at most once; later findings reuse the cached
            index. Takes precedence over ``content``.
    """
    if cache is not None:
        parsed = cache.get_parsed(file_path)
        if parsed is None:
            return "", 1, "unknown context"
        snippet_start_idx, semantic_info = parsed.find_context_bounds(
            line_start
        )
        return (
            parsed.extract(line_start, line_end, context_lines),
            snippet_start_idx + 1,
            semantic_info,
        )

    snippet_start_idx, semantic_info = SourceAnalyzer.find_context_bounds(
        file_path, line_start, content=content
    )
    raw_snippet = SnippetProvider.extract(
        file_path, line_start, line_end, context_lines, content=content
    )
    return raw_snippet, snippet_start_idx + 1, semantic_info
