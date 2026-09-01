"""Data models for linting results."""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Self


# pylint: disable=too-many-instance-attributes
@dataclass
class LinterResult:
    """Standardized output representing an error from any linter.

    Attributes:
        file_path: Path to the file containing the error.
        line_start: 1-indexed starting line number of the error.
        line_end: 1-indexed ending line number of the error, if available.
        col_start: 1-indexed starting column number, if available.
        col_end: 1-indexed ending column number, if available.
        linter_name: Name of the linter that produced the error.
        error_code: The specific error code from the linter.
        message: The descriptive error message.
            raw_severity: Original severity if provided by the linter.
        snippet_context: The code surrounding the error for local reporting.
    """

    file_path: Path
    line_start: int
    line_end: int | None
    col_start: int | None
    col_end: int | None
    linter_name: str
    error_code: str
    message: str
    raw_severity: str | None = None
    snippet_context: str = ""
    snippet_start_line: int = 1
    semantic_context: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialise this result to a JSON-compatible dictionary.

        The ``file_path`` field is converted from a ``Path`` object to a
        plain string so the output can be written directly to JSON.

        Returns:
            A dictionary suitable for ``json.dumps``.
        """
        data = asdict(self)
        data["file_path"] = str(data["file_path"])
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Reconstruct a LinterResult from a dict (e.g., loaded from JSON).

        Mandatory fields must be present and correctly typed, otherwise a
        ``KeyError`` (missing) or ``TypeError`` (mis-typed) is raised rather
        than silently producing a broken result.

        Args:
            data: The dictionary containing linter result data.

        Returns:
            A new LinterResult instance.

        Raises:
            KeyError: If a mandatory field is missing.
            TypeError: If a mandatory field has the wrong type.
        """
        file_path = data["file_path"]
        line_start = cls._require_int(data, "line_start")
        line_end = cls._optional_int(data, "line_end")
        col_start = cls._optional_int(data, "col_start")
        col_end = cls._optional_int(data, "col_end")
        linter_name = cls._require_str(data, "linter_name")
        error_code = cls._require_str(data, "error_code")
        message = cls._require_str(data, "message")

        return cls(
            file_path=Path(file_path),
            line_start=line_start,
            line_end=line_end,
            col_start=col_start,
            col_end=col_end,
            linter_name=linter_name,
            error_code=error_code,
            message=message,
            raw_severity=data.get("raw_severity"),
            snippet_context=data.get("snippet_context", ""),
            snippet_start_line=_as_int(data.get("snippet_start_line", 1)),
            semantic_context=data.get("semantic_context", ""),
        )

    @staticmethod
    def _require_int(data: dict[str, Any], key: str) -> int:
        """Return and validate an int field that must be present."""
        return _require_type(data[key], int, key)

    @staticmethod
    def _optional_int(data: dict[str, Any], key: str) -> int | None:
        """Return and validate an optional int field."""
        if key not in data or data[key] is None:
            return None
        return _require_type(data[key], int, key)

    @staticmethod
    def _require_str(data: dict[str, Any], key: str) -> str:
        """Return and validate a str field that must be present."""
        return _require_type(data[key], str, key)


def _require_type[T](value: Any, expected: type[T], name: str) -> T:
    """Return ``value`` if it is an ``expected``, else raise TypeError."""
    if not isinstance(value, expected):
        raise TypeError(
            f"{name} must be {expected.__name__}, got {type(value).__name__}"
        )
    return value


def _as_int(value: Any) -> int:
    """Validate that ``value`` is an int, raising TypeError otherwise."""
    return _require_type(value, int, "snippet_start_line")
