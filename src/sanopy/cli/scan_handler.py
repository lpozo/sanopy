"""Handler for the 'scan' command."""

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from rich.table import Table

from sanopy.cli.ui import console
from sanopy.config import Config
from sanopy.linters import LINTER_MAP, BaseLinter, Engine
from sanopy.linters.pip_audit import PipAuditLinter
from sanopy.linters.result import LinterResult
from sanopy.linters.safety import SafetyLinter


async def handle_scan(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    target: Path,
    only: str | None,
    skip: str | None,
    output: Path | None,
    output_mode: Literal["machine", "human"] = "machine",
    human_readable: bool = False,
) -> tuple[int, str | None]:
    """Run all active linters on a target path and write results to JSON.

    Linters are executed in parallel. Progress is rendered in the terminal.
    When no issues are found, a success message is printed and no file is
    written.

    Args:
        target: The file or directory to scan.
        only: Optional comma-separated list of linter names to run exclusively.
            Overrides the ``only_linters`` value from config.
        skip: Optional comma-separated list of linter names to skip.
            Overrides the ``skip_linters`` value from config.
        output: Optional path to a JSON file where results will be saved.
        output_mode: Controls whether terminal output is machine-only JSON
            or human-focused progress and summaries.
        human_readable: When ``True``, also writes a markdown report to
            ``linting-report-<target>.md``.

    Returns:
        A tuple of the number of findings for the target and the serialized
        JSON document for machine stdout output, or ``None`` when the output
        is written to a file instead.
    """
    if output_mode == "human":
        console.print(f"[bold blue]Scanning {target}...[/bold blue]")

    config = Config.load()
    active_linters = _get_active_linters(config, only, skip)

    # Use the linter mapping to instantiate the active linters
    engine = Engine(
        linters=[_build_linter(name, config) for name in active_linters]
    )
    results = await _run_linters(engine, target, active_linters, output_mode)

    # Logical Sort: by file then line
    results.sort(key=lambda r: (str(r.file_path), r.line_start))

    reporter = ScanReporter(results, target, output, active_linters)
    stdout_json = _render_scan_output(
        reporter=reporter,
        output_mode=output_mode,
        human_readable=human_readable,
    )

    return len(results), stdout_json


async def _run_linters(
    engine: Engine,
    target: Path,
    active_linters: list[str],
    output_mode: Literal["machine", "human"],
) -> list[LinterResult]:
    """Run linters with optional human-mode progress rendering."""
    if output_mode != "human":
        return await engine.run_all(target)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task(
            "[cyan]Running linters...", total=len(active_linters)
        )

        def progress_cb() -> None:
            progress.update(task_id, advance=1)

        return await engine.run_all(target, progress_callback=progress_cb)


def _render_scan_output(
    *,
    reporter: "ScanReporter",
    output_mode: Literal["machine", "human"],
    human_readable: bool,
) -> str | None:
    """Render scan output according to machine/human mode settings.

    Returns:
        The serialized JSON document when machine output goes to stdout,
        otherwise ``None`` (output was written to a file or not emitted).
    """
    if output_mode == "human" and not reporter.results:
        console.print("[bold green]No issues found! 🎉[/bold green]")

    announce = output_mode == "human"

    if announce and reporter.results:
        reporter.write_summary_report()
    if reporter.output:
        reporter.write_json_report(announce=announce)
    if human_readable:
        reporter.write_human_readable_report(announce=announce)
    if announce:
        reporter.print_fix_hint()
        return None
    return reporter.serialize_stdout()


def _parse_linter_names(names: str | None, default: list[str]) -> list[str]:
    """Parse a comma-separated linter name string into a normalised list.

    Args:
        names: Comma-separated linter names, or ``None`` to use the default.
        default: The list to return when ``names`` is ``None`` or empty.

    Returns:
        A list of lowercase linter name strings.
    """
    if not names:
        return default
    return [name.strip().lower() for name in names.split(",")]


def _get_active_linters(
    config: Config, only: str | None, skip: str | None
) -> list[str]:
    """Determine which linters to run based on config and CLI flag overrides.

    CLI flags take precedence over config file values. ``only`` is applied
    before ``skip``.

    Args:
        config: The loaded configuration supplying default filter lists.
        only: Optional comma-separated linter names to run exclusively.
        skip: Optional comma-separated linter names to exclude.

    Returns:
        An ordered list of active linter name strings.
    """
    only_list = _parse_linter_names(only, config.only_linters)
    skip_list = _parse_linter_names(skip, config.skip_linters)

    active_linters = list(LINTER_MAP.keys())
    if only_list:
        active_linters = [name for name in active_linters if name in only_list]
    if skip_list:
        active_linters = [
            name for name in active_linters if name not in skip_list
        ]
    return active_linters


def _build_linter(name: str, config: Config) -> BaseLinter:
    """Instantiate a linter, passing config-dependent settings when needed.

    Args:
        name: Lowercase linter name from the active linter list.
        config: The loaded configuration.

    Returns:
        A configured linter instance.
    """
    linter_cls = LINTER_MAP[name]
    if name == "safety":
        return SafetyLinter(ignored_cves=config.ignored_cves)
    if name == "pip-audit":
        return PipAuditLinter(ignore_vulns=config.ignore_vulns)
    return linter_cls(config=config)


class ScanReporter:
    """Encapsulate scan reporting for console and file outputs."""

    def __init__(
        self,
        results: list[LinterResult],
        target: Path,
        output: Path | None,
        active_linters: list[str],
    ) -> None:
        """Initialize reporter with scan results and output paths.

        Args:
            results: Sorted linter results.
            target: The scanned file or directory.
            output: Optional path to the JSON results file.
            active_linters: Linters executed for this scan target.
        """
        self.results = results
        self.target = target
        self.output = output
        self.active_linters = active_linters

    def _serialize_results(self) -> str:
        """Return deterministic JSON serialization for scan results."""
        return json.dumps(self._build_payload(), indent=2)

    def _build_payload(self) -> dict[str, object]:
        """Build the versioned machine-readable schema envelope."""
        return {
            "schema_version": "1.0.0",
            "run": {
                "target": str(self.target),
                "generated_at": datetime.now(UTC).isoformat(),
                "active_linters": self.active_linters,
                "finding_count": len(self.results),
            },
            "findings": [self._to_finding(result) for result in self.results],
        }

    def _to_finding(self, result: LinterResult) -> dict[str, object]:
        """Map a linter result to the stable machine finding shape."""
        result_data = result.to_dict()
        return {
            "id": self._build_finding_id(result),
            "message": result_data["message"],
            "linter": {
                "name": result_data["linter_name"],
                "rule_id": result_data["error_code"],
                "raw_severity": result_data.get("raw_severity"),
                "normalized_severity": self._normalize_severity(result),
            },
            "location": {
                "path": result_data["file_path"],
                "start": {
                    "line": result_data["line_start"],
                    "column": result_data["col_start"],
                },
                "end": {
                    "line": result_data["line_end"],
                    "column": result_data["col_end"],
                },
            },
            "context": {
                "snippet": result_data["snippet_context"],
                "snippet_start_line": result_data["snippet_start_line"],
                "semantic": result_data["semantic_context"],
            },
        }

    def _build_finding_id(self, result: LinterResult) -> str:
        """Create a deterministic finding ID for cross-run tracking."""
        digest_input = "|".join(
            [
                str(result.file_path),
                str(result.line_start),
                str(result.line_end),
                str(result.col_start),
                str(result.col_end),
                result.linter_name,
                result.error_code,
                result.message,
            ]
        )
        return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()[:16]

    def _normalize_severity(self, result: LinterResult) -> str:
        """Normalize linter severities into error/warning/info buckets."""
        if result.raw_severity:
            raw = str(result.raw_severity).lower()
            if raw in {"error", "warning", "info"}:
                return raw

        linter = result.linter_name.lower()
        code = result.error_code.upper()

        if linter in {
            "bandit",
            "pip-audit",
            "safety",
            "semgrep",
            "mypy",
            "pyright",
        }:
            return "error"
        if code.startswith(("E", "F", "B")):
            return "error"
        if code.startswith(("W", "C", "R")):
            return "warning"
        return "info"

    def write_json_report(self, *, announce: bool = True) -> None:
        """Write scan results as deterministic JSON output."""
        if not self.output:
            return
        self.output.write_text(self._serialize_results(), encoding="utf-8")
        if announce:
            console.print(
                f"\n[bold green]Results saved to {self.output}[/bold green]"
            )

    def serialize_stdout(self) -> str:
        """Return the JSON document emitted for machine stdout output."""
        return self._serialize_results()

    def get_human_readable_path(self) -> Path:
        """Return the markdown report path for the current scan target."""
        target_name = (
            self.target.stem if self.target.is_file() else self.target.name
        )
        report_name = f"linting-report-{target_name}.md"
        base = self.output.parent if self.output else Path()
        return base / report_name

    def write_human_readable_report(self, *, announce: bool = True) -> None:
        """Write a markdown report for human-readable sharing."""
        report_markdown = self._build_markdown_report()
        path = self.get_human_readable_path()
        path.write_text(report_markdown, encoding="utf-8")
        if announce:
            console.print(
                "[bold green]Human-readable report saved to "
                f"{path}[/bold green]"
            )

    def _build_markdown_report(self) -> str:
        """Build a markdown linting report from the current scan results."""
        counts: Counter[str] = Counter(r.linter_name for r in self.results)
        lines: list[str] = [
            "# Linting Report",
            "",
            f"- Target: `{self.target}`",
            f"- Total issues: **{len(self.results)}**",
            "",
            "## Summary",
            "",
            "| Linter | Issues |",
            "| --- | ---: |",
        ]

        if counts:
            for linter, count in sorted(counts.items()):
                lines.append(f"| {linter} | {count} |")
        else:
            lines.append("| None | 0 |")

        lines.extend(["", "## Findings", ""])

        if not self.results:
            lines.append("No issues found.")
            lines.append("")
            return "\n".join(lines)

        for idx, result in enumerate(self.results, start=1):
            location = f"{result.file_path}:{result.line_start}"
            if result.col_start is not None:
                location += f":{result.col_start}"

            lines.extend(
                [
                    f"### {idx}. {result.linter_name} [{result.error_code}]",
                    "",
                    f"- Location: `{location}`",
                    f"- Message: {result.message}",
                ]
            )

            if result.snippet_context:
                lines.extend(["", "```python", result.snippet_context, "```"])

            lines.append("")

        return "\n".join(lines)

    def print_fix_hint(self) -> None:
        """Print the next-step hint after a scan."""
        console.print(
            "[dim]Use the JSON output to review findings or feed other "
            "automation.[/dim]"
        )

    def write_summary_report(self) -> None:
        """Print a findings summary table."""
        counts: Counter[str] = Counter(r.linter_name for r in self.results)

        table = Table(
            title=f"[bold red]Findings Summary for {self.target}[/bold red]"
        )
        table.add_column("Linter", style="cyan", no_wrap=True)
        table.add_column("Issues Found", justify="right", style="magenta")

        for linter, count in sorted(counts.items()):
            table.add_row(linter, str(count))

        console.print(table)
