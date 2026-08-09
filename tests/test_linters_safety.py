"""Tests for Safety linter."""

import json
from pathlib import Path

import pytest

from sanopy.linters.base import AsyncCompletedProcess
from sanopy.linters.safety import DEFAULT_IGNORED_CVES, SafetyLinter


@pytest.fixture
def linter() -> SafetyLinter:
    """Safety linter instance."""
    return SafetyLinter()


def _mock_run(mocker, stdout: str) -> None:
    mock_result = AsyncCompletedProcess(stdout=stdout, stderr="", returncode=0)
    mocker.patch.object(SafetyLinter, "_run_command", return_value=mock_result)


@pytest.mark.parametrize(
    "stdout, expected_count, first_error_code",
    [
        # Standard vulnerability
        (
            json.dumps(
                {
                    "vulnerabilities": [
                        {
                            "package_name": "requests",
                            "analyzed_version": "2.19.1",
                            "vulnerability_id": "1",
                            "CVE": "CVE-2018-18074",
                            "advisory": "The Requests package does not verify "
                            "server certificates.",
                            "severity": "HIGH",
                        }
                    ]
                }
            ),
            1,
            "VULN-1",
        ),
        # Warnings prepended before the JSON body
        (
            "DeprecationWarning: safety will remove support for this CLI.\n"
            + json.dumps(
                {
                    "vulnerabilities": [
                        {
                            "package_name": "django",
                            "analyzed_version": "3.2",
                            "vulnerability_id": "2",
                            "CVE": "CVE-2023-24580",
                            "severity": "MEDIUM",
                        }
                    ]
                }
            ),
            1,
            "VULN-2",
        ),
        # Multiple vulnerabilities
        (
            json.dumps(
                {
                    "vulnerabilities": [
                        {"vulnerability_id": "1"},
                        {"vulnerability_id": "2"},
                    ]
                }
            ),
            2,
            "VULN-1",
        ),
        # Empty result object
        (json.dumps({}), 0, None),
        # Missing vulnerabilities key
        (json.dumps({"other": []}), 0, None),
        # Null vulnerabilities
        (json.dumps({"vulnerabilities": None}), 0, None),
        # No JSON object at all
        ("No output", 0, None),
        # Unbalanced braces
        ('{"vulnerabilities": [{"vulnerability_id": "1"}', 0, None),
    ],
)
@pytest.mark.asyncio
async def test_safety_scenarios(
    mocker, linter, stdout, expected_count, first_error_code
) -> None:
    """Test various Safety parsing scenarios."""
    _mock_run(mocker, stdout)

    results = await linter.run(Path("target.py"))

    assert len(results) == expected_count
    if expected_count > 0:
        assert results[0].error_code == first_error_code


@pytest.mark.asyncio
async def test_safety_parses_fields(mocker, linter) -> None:
    """Test full field mapping from a Safety vulnerability."""
    stdout = json.dumps(
        {
            "vulnerabilities": [
                {
                    "package_name": "flask",
                    "analyzed_version": "2.2.2",
                    "vulnerability_id": "5",
                    "CVE": "CVE-2023-30861",
                    "advisory": "Potential Denial of Service.",
                    "severity": "high",
                }
            ]
        }
    )
    _mock_run(mocker, stdout)

    results = await linter.run(Path("target.py"))

    assert len(results) == 1
    result = results[0]
    assert result.file_path == Path("pyproject.toml")
    assert result.line_start == 1
    assert result.line_end is None
    assert result.error_code == "VULN-5"
    assert result.snippet_context == ""
    assert "flask==2.2.2" in result.message
    assert "CVE-2023-30861" in result.message
    assert result.message.startswith("[HIGH]") or result.message.startswith(
        "[high]"
    )


@pytest.mark.asyncio
async def test_safety_missing_fields_fallbacks(mocker, linter) -> None:
    """Test fallbacks when a vulnerability lacks optional fields."""
    stdout = json.dumps({"vulnerabilities": [{"vulnerability_id": "9999"}]})
    _mock_run(mocker, stdout)

    results = await linter.run(Path("target.py"))

    assert len(results) == 1
    result = results[0]
    assert result.error_code == "VULN-9999"
    assert "unknown==unknown" in result.message
    assert "(CVE: N/A)" in result.message
    assert "No details available." in result.message


@pytest.mark.parametrize(
    "severity", [None, ""], ids=["none", "empty-string"]
)
@pytest.mark.asyncio
async def test_safety_severity_fallback(mocker, linter, severity) -> None:
    """Test that a missing/empty severity becomes UNKNOWN."""
    vuln = {"vulnerability_id": "7"}
    if severity is not None:
        vuln["severity"] = severity
    _mock_run(mocker, json.dumps({"vulnerabilities": [vuln]}))

    results = await linter.run(Path("target.py"))

    assert len(results) == 1
    assert results[0].message.startswith("[UNKNOWN]")


@pytest.mark.asyncio
async def test_safety_ignores_cve_by_default(mocker, linter) -> None:
    """Test that default ignored CVEs are suppressed."""
    vuln = {
        "package_name": "sanopy",
        "analyzed_version": "0.1",
        "vulnerability_id": "42",
        "CVE": DEFAULT_IGNORED_CVES[0],
        "severity": "HIGH",
    }
    _mock_run(mocker, json.dumps({"vulnerabilities": [vuln]}))

    results = await linter.run(Path("target.py"))

    assert results == []


@pytest.mark.asyncio
async def test_safety_ignores_custom_cve(mocker) -> None:
    """Test that a custom ignored CVE list is respected."""
    linter = SafetyLinter(ignored_cves=["CVE-2020-0001"])
    vuln = {
        "vulnerability_id": "43",
        "CVE": "CVE-2020-0001",
        "severity": "HIGH",
    }
    _mock_run(mocker, json.dumps({"vulnerabilities": [vuln]}))

    results = await linter.run(Path("target.py"))

    assert results == []


@pytest.mark.asyncio
async def test_safety_keeps_non_ignored_cve(mocker, linter) -> None:
    """Test that a CVE not in the ignore list is reported."""
    vuln = {
        "vulnerability_id": "44",
        "CVE": "CVE-2021-44228",
        "severity": "CRITICAL",
    }
    _mock_run(mocker, json.dumps({"vulnerabilities": [vuln]}))

    results = await linter.run(Path("target.py"))

    assert len(results) == 1
    assert results[0].message.startswith("[CRITICAL]")


def test_safety_build_command(tmp_path) -> None:
    """Test that Safety ignores the target and returns a fixed command."""
    target = tmp_path / "mod.py"

    assert SafetyLinter().build_command(target) == [
        "safety",
        "check",
        "--output",
        "json",
    ]
