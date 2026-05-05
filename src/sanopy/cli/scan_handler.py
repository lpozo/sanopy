"""Handler for the 'scan' command."""

import json
from collections import Counter
from pathlib import Path

from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from rich.table import Table

from sanopy.cli.ui import HUMAN_READABLE_REPORT_FILE
from sanopy.cli.ui import console as console
from sanopy.config import Config
from sanopy.linters import LINTER_MAP, Engine
from sanopy.linters.result import LinterResult


async def handle_scan(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    target: Path,
    only: str | None,
    skip: str | None,
    output: Path,
    verbose: bool = False,
    human_readable: bool = False,
) -> None:
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
        output: Path to the JSON file where results will be saved.
        verbose: When ``True``, prints a detailed panel for every issue found.
        human_readable: When ``True``, also writes a markdown report to
            ``linting-report.md``.
    """
    console.print(f"[bold blue]Scanning {target}...[/bold blue]")

    config = Config.load()
    active_linters = _get_active_linters(config, only, skip)

    # Use the linter mapping to instantiate the active linters
    engine = Engine(linters=[LINTER_MAP[name]() for name in active_linters])

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

        results = await engine.run_all(target, progress_callback=progress_cb)

    # Logical Sort: by file then line
    results.sort(key=lambda r: (str(r.file_path), r.line_start))

    if not results:
        console.print("[bold green]No issues found! 🎉[/bold green]")

    reporter = ScanReporter(results, target, output)
    if results:
        reporter.write_summary_report(verbose=verbose)
    reporter.write_json_report()
    if human_readable:
        reporter.write_human_readable_report()
    reporter.print_fix_hint()


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


class ScanReporter:
    """Encapsulate scan reporting for console and file outputs."""

    def __init__(
        self,
        results: list[LinterResult],
        target: Path,
        output: Path,
    ) -> None:
        """Initialize reporter with scan results and output paths.

        Args:
            results: Sorted linter results.
            target: The scanned file or directory.
            output: Path to the JSON results file.
        """
        self.results = results
        self.target = target
        self.output = output

    def write_json_report(self) -> None:
        """Write scan results as deterministic JSON output."""
        self.output.write_text(
            json.dumps([r.to_dict() for r in self.results], indent=2),
            encoding="utf-8",
        )
        console.print(
            f"\n[bold green]Results saved to {self.output}[/bold green]"
        )

    def write_human_readable_report(self) -> None:
        """Write a markdown report for human-readable sharing."""
        report_markdown = self._build_markdown_report()
        HUMAN_READABLE_REPORT_FILE.write_text(
            report_markdown, encoding="utf-8"
        )
        console.print(
            "[bold green]Human-readable report saved to "
            f"{HUMAN_READABLE_REPORT_FILE}[/bold green]"
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
            "[dim]Use the JSON report to review findings or feed other "
            "automation.[/dim]"
        )

    def write_summary_report(self, *, verbose: bool = False) -> None:
        """Print a findings summary table and optional verbose details."""
        counts: Counter[str] = Counter(r.linter_name for r in self.results)

        table = Table(title="[bold red]Findings Summary[/bold red]")
        table.add_column("Linter", style="cyan", no_wrap=True)
        table.add_column("Issues Found", justify="right", style="magenta")

        for linter, count in sorted(counts.items()):
            table.add_row(linter, str(count))

        console.print(table)

        if verbose:
            for idx, result in enumerate(self.results):
                location = f"{result.file_path}:{result.line_start}"
                if result.col_start is not None:
                    location += f":{result.col_start}"
                console.print(
                    Panel(
                        f"[bold]{result.linter_name}[/bold] "
                        f"[{result.error_code}] "
                        f"[yellow]{location}[/yellow]\n\n"
                        f"{result.message}"
                        + (
                            f"\n\n[dim]{result.snippet_context}[/dim]"
                            if result.snippet_context
                            else ""
                        ),
                        title=f"Issue {idx + 1}/{len(self.results)}",
                        border_style="red",
                    )
                )
