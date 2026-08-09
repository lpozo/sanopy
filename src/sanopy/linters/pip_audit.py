"""pip-audit linter implementation for dependency vulnerability scanning."""

import json
from pathlib import Path
from typing import Any

from sanopy.config import DEFAULT_IGNORED_VULNS
from sanopy.linters.base import AsyncCompletedProcess, BaseLinter
from sanopy.linters.result import LinterResult


def _as_dependencies(data: object) -> list[dict[str, Any]]:
    """Extract the dependency list from pip-audit's JSON output.

    Current pip-audit wraps results in an object; older versions emitted
    a bare array of dependencies. Non-dict entries are skipped.
    """
    if isinstance(data, dict):
        raw = data.get("dependencies") or []
    elif isinstance(data, list):
        raw = data
    else:
        raw = []
    return [d for d in raw if isinstance(d, dict)]


class PipAuditLinter(BaseLinter):
    """Linter implementation for pip-audit dependency vulnerability scanner."""

    name = "Pip-Audit"

    def __init__(self, ignore_vulns: list[str] | None = None) -> None:
        """Initialize the pip-audit linter.

        Args:
            ignore_vulns: Optional list of vulnerability IDs or aliases to
                suppress. Defaults to ``DEFAULT_IGNORED_VULNS`` when ``None``.
        """
        self.ignore_vulns = (
            DEFAULT_IGNORED_VULNS if ignore_vulns is None else ignore_vulns
        )
        super().__init__()

    def build_command(self, target: Path) -> list[str]:
        """Build the pip-audit command.

        Note: pip-audit audits the current Python environment, not a
        specific file. The target argument is accepted for interface
        compatibility but is not used directly.

        Args:
            target: The file or directory to scan (ignored by pip-audit).

        Returns:
            A list of command arguments.
        """
        return ["pip-audit", "--format", "json"]

    def parse_output(
        self,
        process_result: AsyncCompletedProcess,
        target: Path,
    ) -> list[LinterResult]:
        """Parse pip-audit JSON output.

        Args:
            process_result: The completed process result.
            target: The target that was scanned.

        Returns:
            A list of standardized linter results.
        """
        try:
            data = json.loads(process_result.stdout)
        except (json.JSONDecodeError, ValueError):
            return []

        parsed_results = []
        for dependency in _as_dependencies(data):
            for vuln in dependency.get("vulns") or []:
                vuln_id = vuln.get("id", "Unknown")

                # Skip any vulnerability the user has chosen to suppress,
                # matching by ID or any of its aliases.
                if self._is_ignored(vuln_id, vuln.get("aliases") or []):
                    continue

                parsed_results.append(
                    self._to_result(dependency, vuln, vuln_id)
                )

        return parsed_results

    def _to_result(
        self,
        dependency: dict[str, Any],
        vuln: dict[str, Any],
        vuln_id: str,
    ) -> LinterResult:
        """Build a LinterResult for a single vulnerability."""
        package_name = dependency.get("name", "unknown")
        version = dependency.get("version", "unknown")
        description = vuln.get("description", "No details available.")
        fix_versions = vuln.get("fix_versions") or []
        aliases = vuln.get("aliases") or []

        message = (
            f"[UNKNOWN] {package_name}=={version} ({vuln_id}) — {description}"
        )
        if fix_versions:
            message += f" Fix available: {', '.join(fix_versions)}."
        if aliases:
            message += f" Aliases: {', '.join(aliases)}."

        return LinterResult(
            file_path=Path("pyproject.toml"),
            line_start=1,
            line_end=None,
            col_start=None,
            col_end=None,
            linter_name=self.name,
            error_code=f"VULN-{vuln_id}",
            message=message,
            snippet_context="",
        )

    def _is_ignored(self, vuln_id: str, aliases: list[str]) -> bool:
        """Check whether a vulnerability matches the ignore list.

        Args:
            vuln_id: The primary vulnerability ID (e.g., PYSEC-...).
            aliases: The vulnerability's alias IDs (e.g., CVE-..., GHSA-...).

        Returns:
            True if the ID or any alias appears in the ignore list.
        """
        ignore_set = set(self.ignore_vulns)
        return vuln_id in ignore_set or any(
            alias in ignore_set for alias in aliases
        )
