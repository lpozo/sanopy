"""Tests for the LinterResult data model."""

from pathlib import Path

import pytest

from sanopy.linters.result import LinterResult

MANDATORY_FIELDS = [
    "file_path",
    "line_start",
    "linter_name",
    "error_code",
    "message",
]

FULL_RESULT = LinterResult(
    file_path=Path("src/main.py"),
    line_start=10,
    line_end=12,
    col_start=5,
    col_end=10,
    linter_name="pylint",
    error_code="C0111",
    message="Missing module docstring",
    raw_severity="warning",
    snippet_context="def foo():\n    pass",
    snippet_start_line=1,
    semantic_context="in def foo",
)

MINIMAL_RESULT = LinterResult(
    file_path=Path("test.py"),
    line_start=1,
    line_end=None,
    col_start=None,
    col_end=None,
    linter_name="ruff",
    error_code="E501",
    message="Line too long",
)


@pytest.mark.parametrize(
    "result, expected",
    [
        (
            FULL_RESULT,
            {
                "file_path": Path("src/main.py"),
                "line_start": 10,
                "line_end": 12,
                "col_start": 5,
                "col_end": 10,
                "linter_name": "pylint",
                "error_code": "C0111",
                "message": "Missing module docstring",
                "raw_severity": "warning",
                "snippet_context": "def foo():\n    pass",
                "snippet_start_line": 1,
                "semantic_context": "in def foo",
            },
        ),
        (
            MINIMAL_RESULT,
            {
                "file_path": Path("test.py"),
                "line_start": 1,
                "line_end": None,
                "col_start": None,
                "col_end": None,
                "linter_name": "ruff",
                "error_code": "E501",
                "message": "Line too long",
                "raw_severity": None,
                "snippet_context": "",
                "snippet_start_line": 1,
                "semantic_context": "",
            },
        ),
    ],
)
def test_linter_result_fields(
    result: LinterResult, expected: dict[str, object]
) -> None:
    """Test that all fields are exposed with the correct values/defaults."""
    for field_name, expected_value in expected.items():
        assert getattr(result, field_name) == expected_value


@pytest.mark.parametrize(
    "result, expected_path",
    [
        (FULL_RESULT, "src/main.py"),
        (MINIMAL_RESULT, "test.py"),
        (
            LinterResult(Path("x.py"), 1, None, None, None, "l", "c", "m"),
            "x.py",
        ),
    ],
)
def test_linter_result_to_dict(
    result: LinterResult, expected_path: str
) -> None:
    """Test serialization to dict, converting Path to string."""
    data = result.to_dict()

    assert data["file_path"] == expected_path
    assert isinstance(data["file_path"], str)
    for field in (
        "line_start",
        "line_end",
        "col_start",
        "col_end",
        "linter_name",
        "error_code",
        "message",
        "raw_severity",
        "snippet_context",
        "snippet_start_line",
        "semantic_context",
    ):
        assert data[field] == getattr(result, field)


@pytest.mark.parametrize(
    "data, expected",
    [
        (
            {
                "file_path": "path/to/code.py",
                "line_start": 42,
                "line_end": 45,
                "col_start": 1,
                "col_end": 80,
                "linter_name": "flake8",
                "error_code": "F401",
                "message": "Imported but unused",
                "snippet_context": "import os",
            },
            LinterResult(
                file_path=Path("path/to/code.py"),
                line_start=42,
                line_end=45,
                col_start=1,
                col_end=80,
                linter_name="flake8",
                error_code="F401",
                message="Imported but unused",
                snippet_context="import os",
            ),
        ),
        (
            {
                "file_path": "simple.py",
                "line_start": 1,
                "linter_name": "bandit",
                "error_code": "B101",
                "message": "Assert used",
            },
            LinterResult(
                file_path=Path("simple.py"),
                line_start=1,
                line_end=None,
                col_start=None,
                col_end=None,
                linter_name="bandit",
                error_code="B101",
                message="Assert used",
            ),
        ),
        (
            {
                "file_path": "full.py",
                "line_start": 2,
                "line_end": 4,
                "col_start": 3,
                "col_end": 9,
                "linter_name": "pylint",
                "error_code": "C0103",
                "message": "Bad name",
                "raw_severity": "info",
                "snippet_context": "x = 1",
                "snippet_start_line": 1,
                "semantic_context": "in module scope",
            },
            LinterResult(
                file_path=Path("full.py"),
                line_start=2,
                line_end=4,
                col_start=3,
                col_end=9,
                linter_name="pylint",
                error_code="C0103",
                message="Bad name",
                raw_severity="info",
                snippet_context="x = 1",
                snippet_start_line=1,
                semantic_context="in module scope",
            ),
        ),
    ],
)
def test_linter_result_from_dict(
    data: dict[str, object], expected: LinterResult
) -> None:
    """Test reconstruction from dicts with and without optional fields."""
    assert LinterResult.from_dict(data) == expected


@pytest.mark.parametrize(
    "result",
    [
        FULL_RESULT,
        MINIMAL_RESULT,
        LinterResult(
            file_path=Path("round/trip.py"),
            line_start=5,
            line_end=None,
            col_start=10,
            col_end=15,
            linter_name="pyright",
            error_code="reportGeneralTypeIssues",
            message="Type mismatch",
            snippet_context="x: int = 'a'",
        ),
    ],
)
def test_linter_result_roundtrip(result: LinterResult) -> None:
    """Test that to_dict and from_dict are inverse operations."""
    assert LinterResult.from_dict(result.to_dict()) == result


@pytest.mark.parametrize("missing_field", MANDATORY_FIELDS)
def test_linter_result_from_dict_missing_mandatory_field(
    missing_field: str,
) -> None:
    """Test that omitting any mandatory field raises KeyError."""
    data = {
        "file_path": "test.py",
        "line_start": 1,
        "linter_name": "bandit",
        "error_code": "B101",
        "message": "Assert used",
    }
    del data[missing_field]

    with pytest.raises(KeyError):
        LinterResult.from_dict(data)


@pytest.mark.parametrize(
    "field, bad_value",
    [
        pytest.param("line_start", "1", id="line_start-string"),
        pytest.param("line_end", "3", id="line_end-string"),
        pytest.param("col_start", "0", id="col_start-string"),
        pytest.param("linter_name", 5, id="linter_name-int"),
        pytest.param("error_code", 5, id="error_code-int"),
        pytest.param("message", 5, id="message-int"),
        pytest.param(
            "snippet_start_line", "2", id="snippet_start_line-string"
        ),
    ],
)
def test_linter_result_from_dict_wrong_type_raises(
    field: str, bad_value: object
) -> None:
    """Test that a mis-typed field raises TypeError instead of propagating."""
    data = {
        "file_path": "test.py",
        "line_start": 1,
        "linter_name": "bandit",
        "error_code": "B101",
        "message": "Assert used",
    }
    data[field] = bad_value

    with pytest.raises(TypeError, match=field):
        LinterResult.from_dict(data)
