"""Tests for Safety linter using parametrization."""

import json
from pathlib import Path

import pytest

from sanopy.linters.base import AsyncCompletedProcess
from sanopy.linters.safety import SafetyLinter, _extract_json


@pytest.fixture
def linter() -> SafetyLinter:
    """Safety linter instance."""
    return SafetyLinter()


VALID_VULN_OUTPUT = json.dumps(
    {
        "vulnerabilities": [
            {
                "vulnerability_id": "85151",
                "package_name": "protobuf",
                "analyzed_version": "4.25.9",
                "CVE": "CVE-2024-TEST",
                "severity": "HIGH",
                "advisory": "DoS via recursion depth bypass.",
            }
        ]
    }
)

MULTI_VULN_OUTPUT = json.dumps(
    {
        "vulnerabilities": [
            {
                "vulnerability_id": "1001",
                "package_name": "requests",
                "analyzed_version": "2.20.0",
                "CVE": "CVE-2023-0001",
                "severity": "CRITICAL",
                "advisory": "SSRF vulnerability.",
            },
            {
                "vulnerability_id": "1002",
                "package_name": "flask",
                "analyzed_version": "1.0",
                "CVE": "CVE-2023-0002",
                "severity": "MEDIUM",
                "advisory": "XSS in debug mode.",
            },
        ]
    }
)


@pytest.mark.parametrize(
    "stdout, expected_count, first_error_code, first_pkg",
    [
        # Single vulnerability
        (VALID_VULN_OUTPUT, 1, "VULN-85151", "protobuf"),
        # Multiple vulnerabilities
        (MULTI_VULN_OUTPUT, 2, "VULN-1001", "requests"),
        # No vulnerabilities
        (json.dumps({"vulnerabilities": []}), 0, None, None),
        # Malformed JSON
        ("Safety crashed", 0, None, None),
        # Deprecation warning prepended to JSON
        (
            "\n+========+\nDEPRECATED\n+========+\n" + VALID_VULN_OUTPUT,
            1,
            "VULN-85151",
            "protobuf",
        ),
        # Missing fields in vulnerability
        (
            json.dumps({"vulnerabilities": [{"vulnerability_id": "9999"}]}),
            1,
            "VULN-9999",
            "unknown",
        ),
    ],
)
@pytest.mark.asyncio
async def test_safety_scenarios(
    mocker, linter, stdout, expected_count, first_error_code, first_pkg
) -> None:
    """Test various Safety parsing scenarios."""
    mock_result = AsyncCompletedProcess(stdout=stdout, stderr="", returncode=0)
    mocker.patch.object(SafetyLinter, "_run_command", return_value=mock_result)

    results = await linter.run(Path("pyproject.toml"))

    assert len(results) == expected_count
    if expected_count > 0:
        assert results[0].error_code == first_error_code
        assert first_pkg in results[0].message
        assert results[0].file_path == Path("pyproject.toml")


@pytest.mark.asyncio
async def test_safety_default_suppresses_known_cve(mocker) -> None:
    """CVE-2026-0994 is suppressed by the built-in default list."""
    output = json.dumps(
        {
            "vulnerabilities": [
                {
                    "vulnerability_id": "85152",
                    "package_name": "protobuf",
                    "analyzed_version": "6.0.0",
                    "CVE": "CVE-2026-0994",
                    "severity": "CRITICAL",
                    "advisory": "Test advisory.",
                }
            ]
        }
    )
    mock_result = AsyncCompletedProcess(stdout=output, stderr="", returncode=0)
    mocker.patch.object(SafetyLinter, "_run_command", return_value=mock_result)

    results = await SafetyLinter().run(Path("pyproject.toml"))

    assert results == []


@pytest.mark.parametrize(
    "ignored_cves, expected_count",
    [
        (["CVE-2024-TEST"], 0),
        ([], 1),
    ],
)
@pytest.mark.asyncio
async def test_safety_ignored_cves_override(
    mocker, ignored_cves, expected_count
) -> None:
    """A custom ignore list replaces the built-in default suppressions."""
    output = json.dumps(
        {
            "vulnerabilities": [
                {
                    "vulnerability_id": "85151",
                    "package_name": "protobuf",
                    "analyzed_version": "4.25.9",
                    "CVE": "CVE-2024-TEST",
                    "severity": "HIGH",
                    "advisory": "DoS via recursion depth bypass.",
                }
            ]
        }
    )
    mock_result = AsyncCompletedProcess(stdout=output, stderr="", returncode=0)
    mocker.patch.object(SafetyLinter, "_run_command", return_value=mock_result)

    results = await SafetyLinter(ignored_cves=ignored_cves).run(
        Path("pyproject.toml")
    )

    assert len(results) == expected_count


class TestExtractJson:
    """Tests for the _extract_json helper."""

    def test_clean_json(self) -> None:
        """Test extraction from clean JSON."""
        raw = '{"key": "value"}'
        assert json.loads(_extract_json(raw)) == {"key": "value"}

    def test_json_with_prefix(self) -> None:
        """Test extraction from JSON with deprecation warnings."""
        raw = "DEPRECATED WARNING\n\n" + '{"vulnerabilities": []}'
        result = json.loads(_extract_json(raw))
        assert result == {"vulnerabilities": []}

    def test_no_json(self) -> None:
        """Test extraction from string with no JSON."""
        with pytest.raises(ValueError, match="No JSON object found"):
            _extract_json("No braces here at all")

    def test_unbalanced_braces(self) -> None:
        """Test extraction from string with unbalanced braces."""
        with pytest.raises(ValueError, match="Unbalanced braces"):
            _extract_json("{{{")
