"""Context extraction and project summary utilities for linters."""

import ast
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
    kind: str  # "class" or "function"
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
        content: str | None = None,
    ) -> str:
        """Extract a raw snippet of code without line numbers.

        Args:
            file_path: Path to the target file.
            line_start: 1-indexed starting line number.
            line_end: 1-indexed ending line number (optional).
            context_lines: Number of surrounding lines to include.
            content: Pre-read file content to avoid re-reading the file.

        Returns:
            The raw string content of the snippet.
        """
        if content is None:
            if not file_path.is_file():
                return ""
            content = read_file_content(file_path)
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
        file_path: Path, line_start: int, content: str | None = None
    ) -> tuple[int, str]:
        """Find the semantic context (function/class) containing the line.

        Args:
            file_path: Path to the target file.
            line_start: Line number where the error occurred.
            content: Pre-read file content to avoid re-reading the file.

        Returns:
            A tuple of (start_index, info_string).
        """
        if content is None:
            if not file_path.is_file():
                return 0, "unknown context"
            content = read_file_content(file_path)
            if content is None:
                return SourceAnalyzer._fallback_search(file_path, line_start)

        try:
            tree = ast.parse(content)
            innermost_node = SourceAnalyzer._find_innermost_block(
                tree, line_start
            )

            if isinstance(
                innermost_node,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
            ):
                kind = (
                    "class"
                    if isinstance(innermost_node, ast.ClassDef)
                    else "def"
                )
                return (
                    innermost_node.lineno - 1,
                    f"in {kind} {innermost_node.name}",
                )

            return max(0, line_start - 10), "in module scope"
        except SyntaxError:
            return SourceAnalyzer._fallback_search(
                file_path, line_start, content=content
            )

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
                    kind = (
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

    @staticmethod
    def _find_innermost_block(
        tree: ast.AST, line_start: int
    ) -> ast.AST | None:
        """Find the innermost function or class block containing the line."""
        innermost_node = None
        for node in ast.walk(tree):
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                start = node.lineno
                end = getattr(node, "end_lineno", node.lineno)
                if start <= line_start <= end and (
                    innermost_node is None
                    or node.lineno >= innermost_node.lineno
                ):
                    innermost_node = node
        return innermost_node

    @staticmethod
    def _fallback_search(
        file_path: Path, line_start: int, content: str | None = None
    ) -> tuple[int, str]:
        """Simple string-based search for context when AST fails."""
        try:
            if content is None:
                content = file_path.read_text(encoding="utf-8")
            lines = content.splitlines()
            current_idx = line_start - 1
            for i in range(current_idx, -1, -1):
                if i >= len(lines):
                    continue
                line = lines[i].strip()
                if line.startswith(("def ", "class ")):
                    name = line.split("(")[0].split(":")[0].strip()
                    return i, f"in {name}"
            return max(0, current_idx - 10), "in module scope"
        except (OSError, UnicodeDecodeError, IndexError):
            return 0, "unknown context"


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
    content: str | None = None,
) -> tuple[str, int, str]:
    """Helper for linters to get snippet and context in one call.

    Args:
        file_path: Path to the target file.
        line_start: Line number where the error occurred.
        line_end: 1-indexed ending line number (optional).
        context_lines: Number of surrounding lines to include.
        content: Pre-read file content to avoid re-reading the file.
            Pass the same content across findings in a single file so the
            file is read and parsed only once.
    """
    snippet_start_idx, semantic_info = SourceAnalyzer.find_context_bounds(
        file_path, line_start, content=content
    )
    raw_snippet = SnippetProvider.extract(
        file_path, line_start, line_end, context_lines, content=content
    )
    return raw_snippet, snippet_start_idx + 1, semantic_info
