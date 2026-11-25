"""Handler for the 'init' command."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click
from click.exceptions import Exit as ClickExit
from rich.markup import escape
from rich.panel import Panel

from sanopy.cli.selection import format_install_hint, resolve_active_linters
from sanopy.cli.ui import console, err_console
from sanopy.config import Config
from sanopy.linters import LINTER_MAP

if TYPE_CHECKING:
    from sanopy.linters.base import BaseLinter


def handle_init(
    only: str | None = None,
    skip: str | None = None,
    no_install: bool = False,
) -> None:
    """Execute the initialization flow (interactive or non-interactive).

    Args:
        only: Comma-separated linters to run exclusively by default.
        skip: Comma-separated linters to skip by default.
        no_install: When ``True``, never install missing linter packages.

    Raises:
        ClickExit: With code 2 when one or more installations fail.
    """
    handler = InitHandler()

    if only is not None or skip is not None:
        handler.handle_cli_options(only=only, skip=skip, no_install=no_install)
        return

    handler.handle_interactive_options(no_install=no_install)


class InitHandler:
    """Coordinate init command flows for CLI and interactive modes."""

    def __init__(self) -> None:
        """Initialize with the project config loaded from disk.

        If the config file is missing or invalid, a default config is
        created in memory (not yet persisted — ``save()`` is called
        later after the user confirms choices). An invalid file is
        reported, because saving will overwrite it.
        """
        try:
            self.config = Config.load()
        except FileNotFoundError:
            self.config = Config.defaults()
        except (ValueError, OSError) as exc:
            err_console.print(
                f"[yellow]{escape(str(exc))}[/yellow]\n"
                "[yellow]Continuing with built-in defaults. Saving will "
                "overwrite the existing file.[/yellow]"
            )
            self.config = Config.defaults()
        self.updater = ConfigUpdater(self.config)

    def handle_cli_options(
        self,
        *,
        only: str | None = None,
        skip: str | None = None,
        no_install: bool = False,
    ) -> None:
        """Handle non-interactive configuration from CLI options.

        Raises:
            ClickExit: With code 2 when one or more installations fail.
        """
        self.updater.apply_cli_config(only=only, skip=skip)

        failed = 0 if no_install else _install_missing_linters(self.config)

        self.config.save()
        self.print_saved_summary()
        _exit_on_install_failure(failed)

    def handle_interactive_options(self, *, no_install: bool = False) -> None:
        """Handle interactive configuration prompts and confirmation.

        Raises:
            ClickExit: With code 2 when one or more installations fail.
        """
        console.print("[bold]Sanopy Setup Wizard[/bold]\n")
        self.updater.apply_interactive_config()
        self.print_setup_summary()
        if not click.confirm("Save this configuration?", default=True):
            console.print(
                "[yellow]Setup cancelled. No changes were saved.[/yellow]"
            )
            return

        failed = (
            0 if no_install else _prompt_install_missing_linters(self.config)
        )

        self.config.save()
        self.print_saved_summary()
        _exit_on_install_failure(failed)

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


def _exit_on_install_failure(failed: int) -> None:
    """Exit non-zero when installations failed.

    ``init`` must not report success after failing to install linters, or
    a following ``sanopy scan`` in the same script fails confusingly.

    Args:
        failed: Number of packages that failed to install.

    Raises:
        ClickExit: With code 2 when ``failed`` is non-zero.
    """
    if not failed:
        return
    err_console.print(f"[red]{failed} linter(s) could not be installed.[/red]")
    raise ClickExit(2)


def _get_missing_linters(config: Config) -> list[type[BaseLinter]]:
    """Return the active linter classes that are not installed."""
    return [
        LINTER_MAP[name]
        for name in resolve_active_linters(config)
        if not LINTER_MAP[name].is_available()
    ]


def _install_linters(linter_classes: list[type[BaseLinter]]) -> int:
    """Install a list of linter packages and report results.

    Args:
        linter_classes: The linter classes to install.

    Returns:
        The number of packages that failed to install.
    """
    failed = 0
    for cls in linter_classes:
        console.print(f"  Installing [cyan]{cls.package_name}[/cyan]...")
        result = cls.install()
        if result.succeeded:
            console.print(f"  [green]{cls.package_name} installed.[/green]")
            continue

        failed += 1
        err_console.print(
            f"  [red]Failed to install {cls.package_name}.[/red]"
        )
        if result.output:
            err_console.print(f"  [dim]{escape(result.output)}[/dim]")
    return failed


def _prompt_install_missing_linters(config: Config) -> int:
    """Check for missing linters and prompt the user to install them.

    Returns:
        The number of packages that failed to install.
    """
    missing = _get_missing_linters(config)
    if not missing:
        return 0

    names = ", ".join(cls.package_name for cls in missing)
    console.print(
        f"\n[yellow]The following linters are not installed:[/yellow] {names}"
    )
    if not click.confirm("Install them now?", default=True):
        hint = format_install_hint([cls.package_name for cls in missing])
        console.print(
            "[dim]Skipping installation. "
            f"You can install them later with:[/dim]\n  {escape(hint)}"
        )
        return 0

    return _install_linters(missing)


def _install_missing_linters(config: Config) -> int:
    """Auto-install missing linters without prompting (non-interactive).

    Returns:
        The number of packages that failed to install.
    """
    missing = _get_missing_linters(config)
    if not missing:
        return 0

    names = ", ".join(cls.package_name for cls in missing)
    console.print(f"[yellow]Installing missing linters:[/yellow] {names}")
    return _install_linters(missing)
