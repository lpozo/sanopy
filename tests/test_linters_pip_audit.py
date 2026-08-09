"""Tests for the pip-audit linter."""

import json
from pathlib import Path

import pytest

from sanopy.config import DEFAULT_IGNORED_VULNS
from sanopy.linters.base import AsyncCompletedProcess
from sanopy.linters.pip_audit import PipAuditLinter


@pytest.fixture
def linter() -> PipAuditLinter:
    """pip-audit linter instance."""
    return PipAuditLinter()


def _mock_run(mocker, stdout: str) -> None:
    mock_result = AsyncCompletedProcess(stdout=stdout, stderr="", returncode=0)
    mocker.patch.object(
        PipAuditLinter, "_run_command", return_value=mock_result
    )


@pytest.mark.parametrize(
    "stdout, expected_count, first_error_code",
    [
        # Standard vulnerability with aliases and a fix version
        (
            json.dumps(
                {
                    "dependencies": [
                        {
                            "name": "flask",
                            "version": "0.5",
                            "vulns": [
                                {
                                    "id": "PYSEC-2019-179",
                                    "fix_versions": ["1.0"],
                                    "aliases": ["CVE-2019-1010083"],
                                    "description": "Flask before 1.0 has a "
                                    "security issue.",
                                }
                            ],
                        }
                    ]
                }
            ),
            1,
            "VULN-PYSEC-2019-179",
        ),
        # Multiple vulnerabilities across packages
        (
            json.dumps(
                {
                    "dependencies": [
                        {
                            "name": "flask",
                            "version": "0.5",
                            "vulns": [
                                {"id": "PYSEC-2019-179"},
                                {"id": "PYSEC-2018-66"},
                            ],
                        },
                        {
                            "name": "jinja2",
                            "version": "3.0.2",
                            "vulns": [{"id": "PYSEC-2021-1234"}],
                        },
                    ]
                }
            ),
            3,
            "VULN-PYSEC-2019-179",
        ),
        # Dependencies audited but no vulnerabilities
        (
            json.dumps(
                {
                    "dependencies": [
                        {"name": "flask", "version": "3.0", "vulns": []},
                        {"name": "jinja2", "version": "3.1", "vulns": []},
                    ]
                }
            ),
            0,
            None,
        ),
        # Bare array format emitted by older pip-audit versions
        (
            json.dumps([{"name": "flask", "version": "3.0", "vulns": []}]),
            0,
            None,
        ),
        # Empty audit result
        (json.dumps({"dependencies": []}), 0, None),
        # Null result
        ("null", 0, None),
        # Malformed JSON
        ("pip-audit crashed", 0, None),
        # Missing dependencies key
        (json.dumps({"fixes": []}), 0, None),
        # Null dependencies
        (json.dumps({"dependencies": None}), 0, None),
        # Missing vulns key on a dependency
        (
            json.dumps(
                {"dependencies": [{"name": "flask", "version": "3.0"}]}
            ),
            0,
            None,
        ),
    ],
)
@pytest.mark.asyncio
async def test_pip_audit_scenarios(
    mocker, linter, stdout, expected_count, first_error_code
) -> None:
    """Test various pip-audit parsing scenarios."""
    _mock_run(mocker, stdout)

    results = await linter.run(Path("target.py"))

    assert len(results) == expected_count
    if expected_count > 0:
        assert results[0].error_code == first_error_code


@pytest.mark.asyncio
async def test_pip_audit_parses_fields(mocker, linter) -> None:
    """Test full field mapping from a pip-audit vulnerability."""
    stdout = json.dumps(
        {
            "dependencies": [
                {
                    "name": "flask",
                    "version": "0.5",
                    "vulns": [
                        {
                            "id": "PYSEC-2018-66",
                            "fix_versions": ["0.12.3"],
                            "aliases": ["CVE-2018-1000656"],
                            "description": "Flask before 0.12.3 contains a "
                            "validation vulnerability.",
                        }
                    ],
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
    assert result.linter_name == "Pip-Audit"
    assert result.error_code == "VULN-PYSEC-2018-66"
    assert result.snippet_context == ""
    assert all(
        part in result.message
        for part in (
            "[UNKNOWN]",
            "flask==0.5",
            "PYSEC-2018-66",
            "validation vulnerability",
            "Fix available: 0.12.3",
            "CVE-2018-1000656",
        )
    )


@pytest.mark.asyncio
async def test_pip_audit_missing_fields_fallbacks(mocker, linter) -> None:
    """Test fallbacks when a vulnerability lacks optional fields."""
    stdout = json.dumps(
        {"dependencies": [{"vulns": [{"id": "PYSEC-2000-0001"}]}]}
    )
    _mock_run(mocker, stdout)

    results = await linter.run(Path("target.py"))

    assert len(results) == 1
    result = results[0]
    assert result.error_code == "VULN-PYSEC-2000-0001"
    assert "unknown==unknown" in result.message
    assert "No details available." in result.message


def test_pip_audit_build_command(tmp_path) -> None:
    """Test that pip-audit ignores the target and returns a fixed command."""
    target = tmp_path / "mod.py"

    assert PipAuditLinter().build_command(target) == [
        "pip-audit",
        "--format",
        "json",
    ]


@pytest.mark.asyncio
async def test_pip_audit_ignores_vuln_by_default(mocker, linter) -> None:
    """Test that default ignored vulnerabilities are suppressed."""
    vuln = {"id": DEFAULT_IGNORED_VULNS[0], "description": "noisy"}
    _mock_run(
        mocker,
        json.dumps(
            {
                "dependencies": [
                    {"name": "mcp", "version": "1.0", "vulns": [vuln]}
                ]
            }
        ),
    )

    results = await linter.run(Path("target.py"))

    assert results == []


@pytest.mark.asyncio
async def test_pip_audit_ignores_vuln_by_alias(mocker) -> None:
    """Test that an alias for an ignored vulnerability is suppressed."""
    linter = PipAuditLinter(ignore_vulns=["CVE-2026-52869"])
    vuln = {"id": "PYSEC-2026-3482", "aliases": ["CVE-2026-52869"]}
    _mock_run(
        mocker,
        json.dumps(
            {
                "dependencies": [
                    {"name": "mcp", "version": "1.0", "vulns": [vuln]}
                ]
            }
        ),
    )

    results = await linter.run(Path("target.py"))

    assert results == []


@pytest.mark.asyncio
async def test_pip_audit_custom_ignore_list(mocker) -> None:
    """Test that a custom ignore list is respected."""
    linter = PipAuditLinter(ignore_vulns=["PYSEC-2000-0001"])
    _mock_run(
        mocker,
        json.dumps(
            {
                "dependencies": [
                    {
                        "name": "mcp",
                        "version": "1.0",
                        "vulns": [{"id": "PYSEC-2000-0001"}],
                    }
                ]
            }
        ),
    )

    results = await linter.run(Path("target.py"))

    assert results == []


@pytest.mark.asyncio
async def test_pip_audit_keeps_non_ignored_vuln(mocker, linter) -> None:
    """Test that a vulnerability not in the ignore list is reported."""
    vuln = {"id": "PYSEC-2026-9999", "description": "real issue"}
    _mock_run(
        mocker,
        json.dumps(
            {
                "dependencies": [
                    {"name": "flask", "version": "0.5", "vulns": [vuln]}
                ]
            }
        ),
    )

    results = await linter.run(Path("target.py"))

    assert len(results) == 1
    assert results[0].error_code == "VULN-PYSEC-2026-9999"
