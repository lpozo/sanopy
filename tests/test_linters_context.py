"""Tests for context extraction and project scanning."""

from pathlib import Path

import pytest

from sanopy.linters.context import (
    ProjectScanner,
    SnippetProvider,
    SourceAnalyzer,
    get_linter_context,
)


def test_snippet_provider_extract(tmp_path) -> None:
    """Test extracting a raw snippet from a file."""
    test_file = tmp_path / "test.py"
    test_file.write_text(
        "def foo():\n    pass\n\ndef bar():\n    return 1\n", encoding="utf-8"
    )

    # Test raw extraction
    snippet = SnippetProvider.extract(test_file, line_start=2, context_lines=1)
    expected = "def foo():\n    pass\n"
    assert snippet == expected


def test_snippet_provider_extract_with_line_end(tmp_path) -> None:
    """Test extraction with an explicit line end."""
    test_file = tmp_path / "test.py"
    test_file.write_text("1\n2\n3\n4\n5\n", encoding="utf-8")
    snippet = SnippetProvider.extract(
        test_file, line_start=2, line_end=4, context_lines=0
    )
    assert snippet == "2\n3\n4"


@pytest.mark.parametrize(
    "snippet, start_line, expected",
    [
        ("line1\nline2", 10, "  10 | line1\n  11 | line2"),
        ("", 1, ""),
        ("single", 5, "   5 | single"),
    ],
)
def test_snippet_provider_format(
    snippet: str, start_line: int, expected: str
) -> None:
    """Test formatting a snippet with line numbers."""
    assert SnippetProvider.format(snippet, start_line=start_line) == expected


def test_source_analyzer_find_context_bounds(tmp_path) -> None:
    """Test finding the semantic context."""
    test_file = tmp_path / "test.py"
    test_file.write_text(
        "class MyClass:\n    def my_func(self):\n        pass\n",
        encoding="utf-8",
    )

    # Inside function
    _, info = SourceAnalyzer.find_context_bounds(test_file, line_start=3)
    assert "def my_func" in info

    # At class level
    _, info = SourceAnalyzer.find_context_bounds(test_file, line_start=1)
    assert "class MyClass" in info

    # Module scope
    test_file_2 = tmp_path / "module.py"
    test_file_2.write_text("x = 1\ny = 2\n", encoding="utf-8")
    _, info = SourceAnalyzer.find_context_bounds(test_file_2, line_start=2)
    assert "module scope" in info


def test_source_analyzer_fallback_search(tmp_path) -> None:
    """Test fallback search when AST parsing fails."""
    test_file = tmp_path / "bad.py"
    # Invalid syntax
    test_file.write_text("def unmatched_paren(\n    pass\n", encoding="utf-8")

    idx, info = SourceAnalyzer.find_context_bounds(test_file, line_start=2)
    assert idx == 0
    assert "in def unmatched_paren" in info


def test_source_analyzer_extract_symbols(tmp_path) -> None:
    """Test symbol extraction."""
    test_file = tmp_path / "syms.py"
    test_file.write_text(
        "class PublicClass:\n    pass\n\ndef public_func():\n    pass\n\n"
        "def _private():\n    pass\n",
        encoding="utf-8",
    )

    symbols = SourceAnalyzer.extract_symbols(test_file)
    names = [s.name for s in symbols]
    assert "PublicClass" in names
    assert "public_func" in names
    assert "_private" not in names
    assert all(s.kind in ("class", "function") for s in symbols)


def test_project_scanner_scan_project(tmp_path) -> None:
    """Test scanning a project directory."""
    project = tmp_path / "my_project"
    project.mkdir()
    (project / "app.py").write_text("def main(): pass", encoding="utf-8")
    (project / "utils.py").write_text("def helper(): pass", encoding="utf-8")
    (project / "pyproject.toml").write_text(
        '[tool.ruff]\nignore = ["E501"]\n', encoding="utf-8"
    )

    summary = ProjectScanner.scan_project(project)
    assert "app.py" in summary.file_tree
    assert "utils.py" in summary.file_tree
    assert "ruff" in summary.target_config
    assert summary.target_config["ruff"]["ignore"] == ["E501"]

    # Verify symbol collection
    symbol_names = [s.name for s in summary.public_symbols]
    assert "main" in symbol_names
    assert "helper" in symbol_names


def test_project_scanner_parse_config(tmp_path) -> None:
    """Test parsing linter configs from pyproject.toml."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pylint]\nmax-line-length = 88\n[tool.other]\nkey = "val"',
        encoding="utf-8",
    )
    config = ProjectScanner.parse_config(tmp_path)
    assert "pylint" in config
    assert config["pylint"]["max-line-length"] == 88
    assert "other" not in config


def test_get_linter_context(tmp_path) -> None:
    """Test the unified context helper wrapper."""
    test_file = tmp_path / "test.py"
    test_file.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")

    raw, start, info = get_linter_context(
        test_file, line_start=2, context_lines=1
    )
    assert raw == "line 1\nline 2\nline 3"
    assert start == 1
    assert "module scope" in info


def test_context_missing_file() -> None:
    """Test handling of missing files."""
    path = Path("non_existent.py")
    assert SnippetProvider.extract(path, 1) == ""
    idx, info = SourceAnalyzer.find_context_bounds(path, 1)
    assert idx == 0
    assert "unknown context" in info


def test_async_symbols(tmp_path) -> None:
    """Test extraction of async functions."""
    test_file = tmp_path / "async_test.py"
    test_file.write_text("async def my_async():\n    pass\n", encoding="utf-8")

    symbols = SourceAnalyzer.extract_symbols(test_file)
    assert len(symbols) == 1
    assert symbols[0].name == "my_async"
    assert symbols[0].kind == "function"

    _, info = SourceAnalyzer.find_context_bounds(test_file, line_start=2)
    assert "def my_async" in info


def test_project_scanner_scan_single_file(tmp_path) -> None:
    """Test scanning a single file instead of a directory."""
    test_file = tmp_path / "app.py"
    test_file.write_text("def main(): pass", encoding="utf-8")
    summary = ProjectScanner.scan_project(test_file)
    assert summary.file_tree == ["app.py"]
    assert len(summary.public_symbols) == 1
    assert summary.public_symbols[0].name == "main"


def test_fallback_search_no_match(tmp_path) -> None:
    """Test fallback search via public API when no class/def is found."""
    test_file = tmp_path / "no_context.py"
    test_file.write_text("print('hello')\nprint('world')", encoding="utf-8")

    # This triggers fallback via find_context_bounds
    idx, info = SourceAnalyzer.find_context_bounds(test_file, line_start=2)
    assert idx == 0
    assert "module scope" in info


def test_snippet_provider_extract_bounds(tmp_path) -> None:
    """Test snippet extraction with out-of-bounds line numbers."""
    test_file = tmp_path / "bounds.py"
    test_file.write_text("line1\nline2\nline3", encoding="utf-8")

    # Start beyond file length
    snippet = SnippetProvider.extract(test_file, line_start=10)
    assert snippet == ""

    # End bound
    snippet = SnippetProvider.extract(
        test_file, line_start=1, context_lines=10
    )
    assert snippet == "line1\nline2\nline3"


def test_extract_unicode_error(tmp_path) -> None:
    """Test handling of Unicode decode errors."""
    test_file = tmp_path / "binary.py"
    # Write some non-UTF-8 bytes
    test_file.write_bytes(b"\xff\xfe\xfd")

    snippet = SnippetProvider.extract(test_file, 1)
    assert snippet == ""

    idx, info = SourceAnalyzer.find_context_bounds(test_file, 1)
    assert idx == 0
    assert "unknown context" in info


def test_fallback_search_index_error(tmp_path) -> None:
    """Test fallback search via public API with line index out of range."""
    test_file = tmp_path / "short.py"
    test_file.write_text("line1", encoding="utf-8")

    # line_start=10 on a 1-line file triggers fallback in find_context_bounds
    idx, info = SourceAnalyzer.find_context_bounds(test_file, line_start=10)
    assert idx == 0
    assert "module scope" in info
