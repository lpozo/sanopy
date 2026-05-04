"""Handler for the 'init' command."""

import click
from rich.panel import Panel

from lintaider.cli.ui import console
from lintaider.config import Config
from lintaider.linters import LINTER_MAP


def handle_init() -> None:
    """Execute the interactive initialization flow."""
    config = Config.load()
    builder = ConfigBuilder(config)

    console.print("[bold]LintAIder Setup Wizard[/bold]\n")

    builder.select_linter_preferences()
    builder.print_summary()

    if not click.confirm("Save this configuration?", default=True):
        console.print(
            "[yellow]Setup cancelled. No changes were saved.[/yellow]"
        )
        return

    built_config = builder.build()
    built_config.save()

    skip_str = (
        ", ".join(built_config.skip_linters)
        if built_config.skip_linters
        else "None"
    )
    only_str = (
        ", ".join(built_config.only_linters)
        if built_config.only_linters
        else "All"
    )
    console.print(
        Panel(
            f"Skip Linters: [bold]{skip_str}[/bold]\n"
            f"Only Linters: [bold]{only_str}[/bold]",
            title="Configuration Saved to lintaider.toml",
            border_style="green",
        )
    )


class ConfigBuilder:
    """Interactive builder for linter configuration via CLI prompts."""

    def __init__(self, config: Config) -> None:
        """Initialize builder with a Config object.

        Args:
            config: The base configuration to build upon.
        """
        self.config = config

    def select_linter_preferences(self) -> tuple[list[str], list[str]]:
        """Prompt for linter preferences and store them.

        Returns:
            A tuple of (skip_linters, only_linters).
        """
        skip, only = self._prompt_linter_preferences()
        self.config.skip_linters = skip
        self.config.only_linters = only
        return skip, only

    def print_summary(self) -> None:
        """Display configuration summary before saving."""
        self._display_summary()

    def build(self) -> Config:
        """Return the built configuration.

        Returns:
            The populated Config object.
        """
        return self.config

    def _parse_linter_list(self, raw: str) -> list[str]:
        """Normalise a comma-separated string into a deduplicated list."""
        if not raw:
            return []
        normalized = [
            item.strip().lower() for item in raw.split(",") if item.strip()
        ]
        return list(dict.fromkeys(normalized))

    def _validate_and_filter_linters(
        self, linter_list: list[str], list_name: str
    ) -> list[str]:
        """Remove unrecognised linter names and warn the user."""
        invalid = [name for name in linter_list if name not in LINTER_MAP]
        if invalid:
            console.print(
                f"[yellow]Ignoring unknown {list_name} linters:[/yellow] "
                + ", ".join(sorted(invalid))
            )
            return [name for name in linter_list if name in LINTER_MAP]
        return linter_list

    def _prompt_linter_preferences(self) -> tuple[list[str], list[str]]:
        """Prompt for linter preferences."""
        available_linters = sorted(LINTER_MAP.keys())
        console.print(
            f"[dim]Available linters: {', '.join(available_linters)}[/dim]"
        )

        skipped_str = click.prompt(
            "Linters to skip by default (comma-separated)",
            default=",".join(self.config.skip_linters),
            show_default=True,
        )
        only_str = click.prompt(
            "Linters to exclusively run by default (comma-separated)",
            default=",".join(self.config.only_linters),
            show_default=True,
        )

        skip_linters = self._parse_linter_list(skipped_str)
        only_linters = self._parse_linter_list(only_str)

        skip_linters = self._validate_and_filter_linters(skip_linters, "skip")
        only_linters = self._validate_and_filter_linters(only_linters, "only")

        overlap = sorted(set(skip_linters).intersection(only_linters))
        if overlap:
            console.print(
                "[yellow]Removing linters present in both "
                "skip and only:[/yellow] " + ", ".join(overlap)
            )
            skip_linters = [
                name for name in skip_linters if name not in overlap
            ]

        return skip_linters, only_linters

    def _display_summary(self) -> None:
        """Display configuration summary before saving."""
        skip_str = (
            ", ".join(self.config.skip_linters)
            if self.config.skip_linters
            else "None"
        )
        only_str = (
            ", ".join(self.config.only_linters)
            if self.config.only_linters
            else "All"
        )
        console.print(
            Panel(
                f"Skip Linters: [bold]{skip_str}[/bold]\n"
                f"Only Linters: [bold]{only_str}[/bold]",
                title="Setup Summary",
                border_style="cyan",
            )
        )
