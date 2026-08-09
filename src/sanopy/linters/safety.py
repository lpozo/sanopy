"""Safety linter implementation for dependency vulnerability scanning."""

import json
import re
from pathlib import Path

from sanopy.linters.base import AsyncCompletedProcess, BaseLinter
from sanopy.linters.result import LinterResult

# Known CVEs that cannot be resolved through the dependency tree.
DEFAULT_IGNORED_CVES = ["CVE-2026-0994"]


class SafetyLinter(BaseLinter):
    """Linter implementation for Safety (Dependency vulnerability scanner)."""

    name = "Safety"

    def __init__(self, ignored_cves: list[str] | None = None) -> None:
        """Initialize the Safety linter.

        Args:
            ignored_cves: Optional list of CVE IDs to suppress. Defaults to
                ``DEFAULT_IGNORED_CVES`` when ``None``.
        """
        self.ignored_cves = (
            DEFAULT_IGNORED_CVES if ignored_cves is None else ignored_cves
        )

    def build_command(self, target: Path) -> list[str]:
        """Build the Safety command.

        Note: Safety scans the installed environment, not a specific file.
        The target argument is accepted for interface compatibility but
        is not used directly.

        Args:
            target: The file or directory to scan (ignored by Safety).

        Returns:
            A list of command arguments.
        """
        return ["safety", "check", "--output", "json"]

    def parse_output(
        self,
        process_result: AsyncCompletedProcess,
        target: Path,
    ) -> list[LinterResult]:
        """Parse Safety JSON output.

        Args:
            process_result: The completed process result.
            target: The target that was scanned.

        Returns:
            A list of standardized linter results.
        """
        try:
            raw_stdout = process_result.stdout
            json_str = _extract_json(raw_stdout)
            data = json.loads(json_str)
            vulnerabilities = data.get("vulnerabilities", [])
        except (json.JSONDecodeError, ValueError):
            return []

        parsed_results = []
        for vuln in vulnerabilities:
            package_name = vuln.get("package_name", "unknown")
            version = vuln.get("analyzed_version", "unknown")
            vuln_id = vuln.get("vulnerability_id", "Unknown")
            cve = vuln.get("CVE", "N/A")
            advisory = vuln.get("advisory", "No details available.")
            severity = vuln.get("severity") or "UNKNOWN"

            # Skip any CVE IDs the user has chosen to suppress
            if cve in self.ignored_cves:
                continue

            message = (
                f"[{severity}] {package_name}=={version} "
                f"(CVE: {cve}) — {advisory}"
            )

            parsed_results.append(
                LinterResult(
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
            )

        return parsed_results


def _extract_json(raw: str) -> str:
    """Extract the first complete JSON object from raw Safety output.

    Safety prepends deprecation warnings before the JSON body,
    so we need to find the opening brace and its matching close.

    Args:
        raw: The raw stdout string from the Safety process.

    Returns:
        A string containing only the JSON object.

    Raises:
        ValueError: If no valid JSON object is found.
    """
    match = re.search(r"\{", raw)
    if match is None:
        raise ValueError("No JSON object found in Safety output")

    start = match.start()
    depth = 0
    for index, char in enumerate(raw[start:], start=start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        if depth == 0:
            return raw[start : index + 1]

    raise ValueError("Unbalanced braces in Safety output")
