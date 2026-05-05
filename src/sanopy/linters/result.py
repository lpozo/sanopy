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

        Args:
            data: The dictionary containing linter result data.

        Returns:
            A new LinterResult instance.
        """
        return cls(
            file_path=Path(data["file_path"]),
            line_start=data["line_start"],
            line_end=data.get("line_end"),
            col_start=data.get("col_start"),
            col_end=data.get("col_end"),
            linter_name=data["linter_name"],
            error_code=data["error_code"],
            message=data["message"],
            snippet_context=data.get("snippet_context", ""),
            snippet_start_line=data.get("snippet_start_line", 1),
            semantic_context=data.get("semantic_context", ""),
        )
