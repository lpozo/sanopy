"""Tests for context extraction and project scanning."""

from pathlib import Path

import pytest

from sanopy.linters.context import (
    ProjectScanner,
    SnippetProvider,
    SourceAnalyzer,
    get_linter_context,
    read_file_content,
)

CLASS_FUNC_CONTENT = "class MyClass:\n    def my_func(self):\n        pass\n"


def _write(tmp_path: Path, name: str, content: str) -> Path:
    """Write a file into tmp_path and return its path."""
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_read_file_content(tmp_path) -> None:
    """read_file_content returns text or None for unreadable files."""
    test_file = _write(tmp_path, "test.py", "x = 1\n")
    assert read_file_content(test_file) == "x = 1\n"

    assert read_file_content(tmp_path / "missing.py") is None

    binary = tmp_path / "binary.py"
    binary.write_bytes(b"\xff\xfe\xfd")
    assert read_file_content(binary) is None


@pytest.mark.parametrize(
    "content, line_start, line_end, context_lines, expected",
    [
        # Basic extraction with surrounding context
        (
            "def foo():\n    pass\n\ndef bar():\n    return 1\n",
            2,
            None,
            1,
            "def foo():\n    pass\n",
        ),
        # Explicit line end with no surrounding context
        ("1\n2\n3\n4\n5\n", 2, 4, 0, "2\n3\n4"),
        # Line start beyond file length
        ("line1\nline2\nline3", 10, None, 5, ""),
        # Context wider than the file is clamped
        ("line1\nline2\nline3", 1, None, 10, "line1\nline2\nline3"),
        # Zero context lines without an explicit end
        ("1\n2\n3", 2, None, 0, "2"),
    ],
)
def test_snippet_provider_extract(
    tmp_path,
    content: str,
    line_start: int,
    line_end: int | None,
    context_lines: int,
    expected: str,
) -> None:
    """Test extracting raw snippets from files."""
    test_file = _write(tmp_path, "test.py", content)

    snippet = SnippetProvider.extract(
        test_file, line_start, line_end, context_lines
    )

    assert snippet == expected


@pytest.mark.parametrize(
    "snippet, start_line, expected",
    [
        ("line1\nline2", 10, "  10 | line1\n  11 | line2"),
        ("", 1, ""),
        ("single", 5, "   5 | single"),
        ("a\nb\nc", 0, "   0 | a\n   1 | b\n   2 | c"),
    ],
)
def test_snippet_provider_format(
    snippet: str, start_line: int, expected: str
) -> None:
    """Test formatting snippets with line numbers."""
    assert SnippetProvider.format(snippet, start_line) == expected


def test_snippet_provider_extract_uses_provided_content(tmp_path) -> None:
    """Extract uses caller-supplied content instead of re-reading the file."""
    test_file = _write(tmp_path, "test.py", "real content\n")

    snippet = SnippetProvider.extract(
        test_file, 1, context_lines=0, content="caller content\n"
    )

    assert snippet == "caller content"


@pytest.mark.parametrize(
    "content, line_start, expected_fragment",
    [
        # Inside a method
        (CLASS_FUNC_CONTENT, 3, "in def my_func"),
        # At class level
        (CLASS_FUNC_CONTENT, 1, "in class MyClass"),
        # Method header line resolves to the method
        (CLASS_FUNC_CONTENT, 2, "in def my_func"),
        # Module scope
        ("x = 1\ny = 2\n", 2, "in module scope"),
        # Async function
        ("async def my_async():\n    pass\n", 2, "in def my_async"),
        # Innermost nested function wins
        ("def outer():\n    def inner():\n        pass\n", 3, "in def inner"),
        # Method inside a class
        ("class A:\n    def m(self):\n        pass\n", 2, "in def m"),
    ],
)
def test_find_context_bounds(
    tmp_path, content: str, line_start: int, expected_fragment: str
) -> None:
    """Test semantic context detection for a line."""
    test_file = _write(tmp_path, "context.py", content)

    _, info = SourceAnalyzer.find_context_bounds(test_file, line_start)

    assert expected_fragment in info


def test_find_context_bounds_uses_provided_content(tmp_path) -> None:
    """find_context_bounds uses caller-supplied content, not the file."""
    test_file = _write(
        tmp_path,
        "context.py",
        "def real_func():\n    pass\n",
    )

    _, info = SourceAnalyzer.find_context_bounds(
        test_file, 2, content="class CallerClass:\n    pass\n"
    )

    assert "in class CallerClass" in info


def test_find_context_bounds_fallback_uses_provided_content(tmp_path) -> None:
    """The AST-failure fallback uses caller content instead of re-reading."""
    test_file = _write(
        tmp_path,
        "context.py",
        "def real_func(\n    pass\n",
    )

    _, info = SourceAnalyzer.find_context_bounds(
        test_file, 2, content="def caller_func(\n    pass\n"
    )

    assert "in def caller_func" in info


@pytest.mark.parametrize(
    "content, line_start, expected_fragment",
    [
        # Fallback string search for invalid syntax
        ("def unmatched_paren(\n    pass\n", 2, "in def unmatched_paren"),
        # No class/def found falls back to module scope
        ("print('hello')\nprint('world')", 2, "in module scope"),
        # Line index beyond the file falls back to module scope
        ("line1", 10, "in module scope"),
    ],
)
def test_find_context_bounds_fallback(
    tmp_path, content: str, line_start: int, expected_fragment: str
) -> None:
    """Test context detection when AST parsing fails or cannot locate."""
    test_file = _write(tmp_path, "fallback.py", content)

    idx, info = SourceAnalyzer.find_context_bounds(test_file, line_start)

    assert idx == 0
    assert expected_fragment in info


@pytest.mark.parametrize(
    "content, expected_names, expected_kinds",
    [
        # Public symbols only; private ones are skipped
        (
            "class PublicClass:\n    pass\n\ndef public_func():\n    pass\n\n"
            "def _private():\n    pass\n",
            ["PublicClass", "public_func"],
            ["class", "function"],
        ),
        # Async functions are discovered
        ("async def my_async():\n    pass\n", ["my_async"], ["function"]),
        # Methods are not top-level symbols
        ("class A:\n    def m(self):\n        pass\n", ["A"], ["class"]),
        # Empty and non-symbol files yield no symbols
        ("", [], []),
        ("import os\n", [], []),
        # Invalid syntax yields no symbols
        ("def broken(:\n", [], []),
    ],
)
def test_extract_symbols(
    tmp_path,
    content: str,
    expected_names: list[str],
    expected_kinds: list[str],
) -> None:
    """Test extraction of top-level public symbols."""
    test_file = _write(tmp_path, "syms.py", content)

    symbols = SourceAnalyzer.extract_symbols(test_file)

    assert [s.name for s in symbols] == expected_names
    assert [s.kind for s in symbols] == expected_kinds


def test_extract_symbols_capped_at_ten(tmp_path) -> None:
    """Test that symbol extraction is limited to ten symbols."""
    lines = "\n".join(f"def f{i}():\n    pass" for i in range(12))
    test_file = _write(tmp_path, "many.py", lines)

    symbols = SourceAnalyzer.extract_symbols(test_file)

    assert len(symbols) == 10


def test_extract_symbols_relative_path(tmp_path) -> None:
    """Test that a root path produces relative symbol file paths."""
    test_file = _write(tmp_path, "app.py", "def main(): pass\n")

    symbols = SourceAnalyzer.extract_symbols(test_file, root_path=tmp_path)

    assert symbols[0].file_path == Path("app.py")


def test_extract_symbols_binary_file(tmp_path) -> None:
    """Test symbol extraction from a non-UTF-8 file yields no symbols."""
    test_file = tmp_path / "binary.py"
    test_file.write_bytes(b"\xff\xfe\xfd")

    assert not SourceAnalyzer.extract_symbols(test_file)


@pytest.mark.parametrize(
    "files, expected_tree, expected_symbols, expected_config_keys",
    [
        (
            {
                "app.py": "def main(): pass\n",
                "utils.py": "def helper(): pass\n",
                "pyproject.toml": '[tool.ruff]\nignore = ["E501"]\n',
            },
            ["app.py", "utils.py"],
            ["main", "helper"],
            ["ruff"],
        ),
        (
            {"app.py": "x = 1\n"},
            ["app.py"],
            [],
            [],
        ),
    ],
)
def test_project_scanner_scan_directory(
    tmp_path,
    files: dict[str, str],
    expected_tree: list[str],
    expected_symbols: list[str],
    expected_config_keys: list[str],
) -> None:
    """Test scanning a project directory."""
    project = tmp_path / "my_project"
    project.mkdir()
    for name, content in files.items():
        (project / name).write_text(content, encoding="utf-8")

    summary = ProjectScanner.scan_project(project)

    assert summary.file_tree == expected_tree
    assert [s.name for s in summary.public_symbols] == expected_symbols
    for key in expected_config_keys:
        assert key in summary.target_config


def test_project_scanner_scan_single_file(tmp_path) -> None:
    """Test scanning a single file instead of a directory."""
    test_file = _write(tmp_path, "app.py", "def main(): pass\n")

    summary = ProjectScanner.scan_project(test_file)

    assert summary.file_tree == ["app.py"]
    assert [s.name for s in summary.public_symbols] == ["main"]


def test_project_scanner_scan_empty_directory(tmp_path) -> None:
    """Test scanning an empty directory."""
    summary = ProjectScanner.scan_project(tmp_path)

    assert not summary.file_tree
    assert not summary.public_symbols
    assert not summary.target_config


@pytest.mark.parametrize(
    "toml_content, expected_keys, unexpected_keys",
    [
        (
            '[tool.pylint]\nmax-line-length = 88\n[tool.other]\nkey = "val"',
            ["pylint"],
            ["other"],
        ),
        (
            "[tool.ruff]\nignore = ['E501']\n"
            "[tool.mypy]\nstrict = true\n"
            "[tool.vulture]\nignore_names = []\n"
            "[tool.bandit]\nx = 1\n",
            ["ruff", "mypy", "vulture"],
            ["bandit"],
        ),
        # Invalid TOML is ignored
        ("not: valid: toml [[[", [], []),
        # Empty file
        ("", [], []),
    ],
)
def test_project_scanner_parse_config(
    tmp_path,
    toml_content: str,
    expected_keys: list[str],
    unexpected_keys: list[str],
) -> None:
    """Test parsing linter sections from pyproject.toml."""
    (tmp_path / "pyproject.toml").write_text(toml_content, encoding="utf-8")

    config = ProjectScanner.parse_config(tmp_path)

    for key in expected_keys:
        assert key in config
    for key in unexpected_keys:
        assert key not in config


def test_project_scanner_parse_config_missing_file(tmp_path) -> None:
    """Test parsing config when pyproject.toml does not exist."""
    assert not ProjectScanner.parse_config(tmp_path)


@pytest.mark.parametrize(
    "content, line_start, context_lines, expected_start",
    [
        ("line 1\nline 2\nline 3\n", 2, 1, 1),
        ("x = 1\ny = 2\nz = 3\n", 2, 5, 1),
    ],
)
def test_get_linter_context(
    tmp_path,
    content: str,
    line_start: int,
    context_lines: int,
    expected_start: int,
) -> None:
    """Test the unified context helper wrapper."""
    test_file = _write(tmp_path, "test.py", content)

    raw, start, info = get_linter_context(
        test_file, line_start, context_lines=context_lines
    )

    assert raw
    assert start == expected_start
    assert "module scope" in info


def test_get_linter_context_uses_provided_content(tmp_path) -> None:
    """get_linter_context uses supplied content instead of reading the file."""
    test_file = _write(
        tmp_path,
        "test.py",
        "def real_func():\n    pass\n",
    )

    raw, start, info = get_linter_context(
        test_file,
        2,
        context_lines=1,
        content="class CallerClass:\n    def m(self):\n        pass\n",
    )

    assert raw == "class CallerClass:\n    def m(self):\n        pass"
    assert "in def m" in info


@pytest.mark.parametrize(
    "file_path",
    [Path("non_existent.py"), Path("missing/dir/other.py")],
)
def test_missing_file(file_path: Path) -> None:
    """Test that missing files degrade gracefully."""
    assert SnippetProvider.extract(file_path, 1) == ""

    idx, info = SourceAnalyzer.find_context_bounds(file_path, 1)
    assert idx == 0
    assert "unknown context" in info

    raw, start, info = get_linter_context(file_path, 1)
    assert raw == ""
    assert start == 1
    assert "unknown context" in info


def test_unicode_decode_error(tmp_path) -> None:
    """Test handling of non-UTF-8 files."""
    test_file = tmp_path / "binary.py"
    test_file.write_bytes(b"\xff\xfe\xfd")

    assert SnippetProvider.extract(test_file, 1) == ""

    idx, info = SourceAnalyzer.find_context_bounds(test_file, 1)
    assert idx == 0
    assert "unknown context" in info
