"""Tests for ScanReporter severity normalization and finding IDs.

Severity normalization and finding-ID generation are exercised through
the public ``serialize_stdout`` API, asserting on the ``normalized_severity``
and ``id`` fields of the emitted JSON document.
"""

import json
from pathlib import Path

import pytest

from sanopy.cli.scan_handler import ScanReporter
from sanopy.linters.result import LinterResult


def _reporter(result: LinterResult, tmp_path: Path) -> ScanReporter:
    return ScanReporter([result], tmp_path, None, ["Ruff"])


def _result(
    *,
    linter_name: str = "Ruff",
    error_code: str = "E501",
    message: str = "Some message",
    raw_severity: str | None = None,
) -> LinterResult:
    return LinterResult(
        file_path=Path("mod.py"),
        line_start=1,
        line_end=None,
        col_start=None,
        col_end=None,
        linter_name=linter_name,
        error_code=error_code,
        message=message,
        raw_severity=raw_severity,
    )


def _normalized_severity(result: LinterResult, tmp_path: Path) -> str:
    payload = json.loads(_reporter(result, tmp_path).serialize_stdout())
    severity = payload["findings"][0]["linter"]["normalized_severity"]
    assert isinstance(severity, str)
    return severity


def _finding_id(result: LinterResult, tmp_path: Path) -> str:
    payload = json.loads(_reporter(result, tmp_path).serialize_stdout())
    finding_id = payload["findings"][0]["id"]
    assert isinstance(finding_id, str)
    return finding_id


@pytest.mark.parametrize(
    "raw_severity, expected",
    [
        pytest.param("error", "error", id="raw-error"),
        pytest.param("warning", "warning", id="raw-warning"),
        pytest.param("info", "info", id="raw-info"),
        pytest.param("ERROR", "error", id="raw-uppercase"),
        pytest.param("Error", "error", id="raw-mixed-case"),
        pytest.param("high", "error", id="raw-high-to-error"),
        pytest.param("critical", "error", id="raw-critical-to-error"),
        pytest.param("fatal", "error", id="raw-fatal-to-error"),
        pytest.param("medium", "warning", id="raw-medium-to-warning"),
        pytest.param("low", "info", id="raw-low-to-info"),
        pytest.param("note", "info", id="raw-note-to-info"),
        pytest.param("hint", "info", id="raw-hint-to-info"),
        pytest.param("convention", "info", id="raw-convention-to-info"),
        pytest.param("refactor", "info", id="raw-refactor-to-info"),
    ],
)
def test_normalized_severity_uses_raw_severity(
    tmp_path, raw_severity, expected
) -> None:
    """Recognized raw severities map into the matching depth bucket."""
    result = _result(raw_severity=raw_severity)
    assert _normalized_severity(result, tmp_path) == expected


def test_unrecognized_raw_severity_falls_back(tmp_path) -> None:
    """Unrecognized raw severities fall through to the code-prefix bucket."""
    result = _result(raw_severity="unknown-token")
    assert _normalized_severity(result, tmp_path) == "error"


@pytest.mark.parametrize(
    "linter_name, expected",
    [
        pytest.param("bandit", "error", id="bandit-default"),
        pytest.param("pip-audit", "error", id="pip-audit-default"),
        pytest.param("safety", "error", id="safety-default"),
        pytest.param("semgrep", "error", id="semgrep-default"),
        pytest.param("mypy", "error", id="mypy-default"),
        pytest.param("pyright", "error", id="pyright-default"),
    ],
)
def test_normalized_severity_linter_name_default(
    tmp_path, linter_name, expected
) -> None:
    """Security/type linters default to error when no raw severity."""
    result = _result(linter_name=linter_name, raw_severity=None)
    assert _normalized_severity(result, tmp_path) == expected


@pytest.mark.parametrize(
    "error_code, expected",
    [
        pytest.param("E501", "error", id="pylint-error"),
        pytest.param("F401", "error", id="pyflakes-error"),
        pytest.param("B101", "error", id="bandit-error-prefix"),
        pytest.param("W0611", "warning", id="pylint-warning"),
        pytest.param("C0111", "warning", id="pylint-convention"),
        pytest.param("R0913", "warning", id="pylint-refactor"),
        pytest.param("T0010", "info", id="unknown-prefix-info"),
    ],
)
def test_normalized_severity_code_prefix_fallback(
    tmp_path, error_code, expected
) -> None:
    """Code-prefix fallback buckets E/F/B to error, W/C/R to warning."""
    result = _result(linter_name="Pylint", error_code=error_code)
    assert _normalized_severity(result, tmp_path) == expected


def test_normalized_severity_ruff_defaults_to_info(tmp_path) -> None:
    """Non-bucketed linters without a code prefix default to info."""
    result = _result(linter_name="Vulture", error_code="unused-code")
    assert _normalized_severity(result, tmp_path) == "info"


@pytest.mark.parametrize(
    "raw_severity, expected",
    [
        pytest.param("HIGH", "error", id="bandit-high"),
        pytest.param("MEDIUM", "warning", id="bandit-medium"),
        pytest.param("LOW", "info", id="bandit-low"),
        pytest.param("CRITICAL", "error", id="bandit-critical"),
        pytest.param("UNKNOWN", "error", id="bandit-unknown"),
    ],
)
def test_normalized_severity_bandit_raw_buckets(
    tmp_path, raw_severity, expected
) -> None:
    """Bandit native severities map into error/warning/info."""
    result = _result(
        linter_name="Bandit", error_code="B101", raw_severity=raw_severity
    )
    assert _normalized_severity(result, tmp_path) == expected


def test_finding_id_deterministic(tmp_path) -> None:
    """The same finding yields the same ID every time."""
    result = _result()
    assert _finding_id(result, tmp_path) == _finding_id(result, tmp_path)


def test_finding_id_differs_on_change(tmp_path) -> None:
    """A different finding yields a different ID."""
    baseline = _finding_id(_result(), tmp_path)
    changed_message = _finding_id(
        _result(error_code="W0611", message="Different message"), tmp_path
    )
    changed_code = _finding_id(_result(error_code="F401"), tmp_path)
    assert baseline != changed_message
    assert baseline != changed_code


def test_serialize_stdout_empty_results_list(tmp_path) -> None:
    """serialize_stdout with no findings emits an empty findings array."""
    reporter = ScanReporter([], tmp_path, None, ["ruff"])
    payload = json.loads(reporter.serialize_stdout())
    assert payload["schema_version"] == "1.0.0"
    assert payload["run"]["finding_count"] == 0
    assert payload["findings"] == []


def test_write_json_report_without_output_is_noop(tmp_path) -> None:
    """write_json_report does nothing when no output path is set."""
    reporter = ScanReporter([_result()], tmp_path, None, ["Ruff"])

    reporter.write_json_report()

    assert not list(tmp_path.iterdir())
