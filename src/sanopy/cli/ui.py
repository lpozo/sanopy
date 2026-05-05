"""UI utilities and common constants for the CLI."""

from pathlib import Path

from rich.console import Console

console = Console()

# Default filename for scan results
SCAN_RESULT_FILE = Path("scan-result.json")

# Default filename for human-readable scan results
HUMAN_READABLE_REPORT_FILE = Path("linting-report.md")
