"""Handler for the 'init' command."""

import click
from rich.panel import Panel

from sanopy.cli.ui import console
from sanopy.config import Config
from sanopy.linters import LINTER_MAP


def handle_init(only: str | None = None, skip: str | None = None) -> None:
    """Execute the initialization flow (interactive or non-interactive)."""
    handler = InitHandler()

    if only is not None or skip is not None:
        handler.handle_cli_options(only=only, skip=skip)
        return

    handler.handle_interactive_options()


class InitHandler:
    """Coordinate init command flows for CLI and interactive modes."""

    def __init__(self) -> None:
        """Initialize with the project config loaded from disk."""
        self.config = Config.load()
        self.updater = ConfigUpdater(self.config)

    def handle_cli_options(
        self, *, only: str | None = None, skip: str | None = None
    ) -> None:
        """Handle non-interactive configuration from CLI options."""
        self.updater.apply_cli_config(only=only, skip=skip)

        self.config.save()
        self.print_saved_summary()

    def handle_interactive_options(self) -> None:
        """Handle interactive configuration prompts and confirmation."""
        console.print("[bold]Sanopy Setup Wizard[/bold]\n")
        self.updater.apply_interactive_config()
        self.print_setup_summary()
        if not click.confirm("Save this configuration?", default=True):
            console.print(
                "[yellow]Setup cancelled. No changes were saved.[/yellow]"
            )
            return

        self.config.save()
        self.print_saved_summary()

    def print_setup_summary(self) -> None:
        """Print setup summary before asking for confirmation."""
        self._print_config_summary(title="Setup Summary", border_style="cyan")

    def print_saved_summary(self) -> None:
        """Print a success panel with the saved linter configuration."""
        self._print_config_summary(
            title="Configuration Saved to .sanopy.toml",
            border_style="green",
        )

    def _print_config_summary(self, *, title: str, border_style: str) -> None:
        """Print a panel with current skip/only linter configuration."""
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
                title=title,
                border_style=border_style,
            )
        )


class ConfigUpdater:
    """Apply CLI and interactive updates to linter configuration."""

    def __init__(self, config: Config) -> None:
        """Initialize updater with a Config object.

        Args:
            config: The base configuration to build upon.
        """
        self.config = config

    def apply_interactive_config(self) -> None:
        """Apply config preferences collected from interactive prompts."""
        skipped_str, only_str = self._prompt_linter_preferences()
        skip_linters, only_linters = self._resolve_linter_preferences(
            skipped_str=skipped_str,
            only_str=only_str,
            announce_overlap=True,
        )
        self.config.skip_linters = skip_linters
        self.config.only_linters = only_linters

    def apply_cli_config(
        self, *, only: str | None = None, skip: str | None = None
    ) -> None:
        """Apply non-interactive linter config from CLI options."""
        skip_linters, only_linters = self._resolve_linter_preferences(
            skipped_str=skip or "",
            only_str=only or "",
            announce_overlap=False,
        )
        self.config.skip_linters = skip_linters
        self.config.only_linters = only_linters

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

    def _prompt_linter_preferences(self) -> tuple[str, str]:
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

        return skipped_str, only_str

    def _resolve_linter_preferences(
        self,
        *,
        skipped_str: str,
        only_str: str,
        announce_overlap: bool,
    ) -> tuple[list[str], list[str]]:
        """Parse, validate, and reconcile skip/only linter lists."""
        skip_linters = self._parse_linter_list(skipped_str)
        only_linters = self._parse_linter_list(only_str)

        skip_linters = self._validate_and_filter_linters(skip_linters, "skip")
        only_linters = self._validate_and_filter_linters(only_linters, "only")

        overlap = sorted(set(skip_linters).intersection(only_linters))
        if overlap:
            if announce_overlap:
                console.print(
                    "[yellow]Removing linters present in both "
                    "skip and only:[/yellow] " + ", ".join(overlap)
                )
            skip_linters = [
                name for name in skip_linters if name not in overlap
            ]

        return skip_linters, only_linters
