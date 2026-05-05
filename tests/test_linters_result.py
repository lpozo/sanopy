"""Tests for the LinterResult data model."""

from pathlib import Path

import pytest

from sanopy.linters.result import LinterResult


def test_linter_result_creation() -> None:
    """Test standard creation of LinterResult."""
    result = LinterResult(
        file_path=Path("src/main.py"),
        line_start=10,
        line_end=12,
        col_start=5,
        col_end=10,
        linter_name="pylint",
        error_code="C0111",
        message="Missing module docstring",
        snippet_context="def foo():\n    pass",
    )

    assert result.file_path == Path("src/main.py")
    assert result.line_start == 10
    assert result.line_end == 12
    assert result.col_start == 5
    assert result.col_end == 10
    assert result.linter_name == "pylint"
    assert result.error_code == "C0111"
    assert result.message == "Missing module docstring"
    assert result.snippet_context == "def foo():\n    pass"


def test_linter_result_optional_fields_defaults() -> None:
    """Test LinterResult with mandatory fields and default snippet context."""
    result = LinterResult(
        file_path=Path("test.py"),
        line_start=1,
        line_end=None,
        col_start=None,
        col_end=None,
        linter_name="ruff",
        error_code="E501",
        message="Line too long",
    )

    assert result.line_end is None
    assert result.col_start is None
    assert result.col_end is None
    assert result.snippet_context == ""


def test_linter_result_to_dict() -> None:
    """Test serialization to dict, ensuring Path is converted to string."""
    result = LinterResult(
        file_path=Path("folder/file.py"),
        line_start=1,
        line_end=None,
        col_start=None,
        col_end=None,
        linter_name="mypy",
        error_code="attr-defined",
        message="Item has no attribute",
        snippet_context="print(obj.attr)",
    )

    data = result.to_dict()

    assert data["file_path"] == "folder/file.py"
    assert isinstance(data["file_path"], str)
    assert data["linter_name"] == "mypy"
    assert data["line_start"] == 1
    assert data["line_end"] is None
    assert data["snippet_context"] == "print(obj.attr)"


def test_linter_result_from_dict_full() -> None:
    """Test reconstruction from a complete dictionary."""
    data = {
        "file_path": "path/to/code.py",
        "line_start": 42,
        "line_end": 45,
        "col_start": 1,
        "col_end": 80,
        "linter_name": "flake8",
        "error_code": "F401",
        "message": "Imported but unused",
        "snippet_context": "import os",
    }

    result = LinterResult.from_dict(data)

    assert result.file_path == Path("path/to/code.py")
    assert result.line_start == 42
    assert result.line_end == 45
    assert result.col_start == 1
    assert result.col_end == 80
    assert result.linter_name == "flake8"
    assert result.error_code == "F401"
    assert result.message == "Imported but unused"
    assert result.snippet_context == "import os"


def test_linter_result_from_dict_minimal() -> None:
    """Test reconstruction from minimal dict with missing optional keys."""
    data = {
        "file_path": "simple.py",
        "line_start": 1,
        "linter_name": "bandit",
        "error_code": "B101",
        "message": "Assert used",
    }

    result = LinterResult.from_dict(data)

    assert result.file_path == Path("simple.py")
    assert result.line_end is None
    assert result.col_start is None
    assert result.snippet_context == ""


def test_linter_result_roundtrip() -> None:
    """Test that to_dict and from_dict are inverse operations."""
    original = LinterResult(
        file_path=Path("round/trip.py"),
        line_start=5,
        line_end=None,
        col_start=10,
        col_end=15,
        linter_name="pyright",
        error_code="reportGeneralTypeIssues",
        message="Type mismatch",
        snippet_context="x: int = 'a'",
    )

    reconstructed = LinterResult.from_dict(original.to_dict())

    assert original == reconstructed


def test_linter_result_from_dict_invalid_data() -> None:
    """Test that missing mandatory fields in from_dict raises KeyError."""
    incomplete_data = {
        "file_path": "test.py"
    }  # Missing line_start, linter_name, etc.

    with pytest.raises(KeyError):
        LinterResult.from_dict(incomplete_data)
