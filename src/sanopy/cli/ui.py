"""UI utilities for the CLI."""

from rich.console import Console

#: Stdout console. In machine mode stdout carries the JSON document, so
#: only payload output may go here.
console = Console()

#: Stderr console for diagnostics, so that they never corrupt the JSON
#: document written to stdout in machine mode.
err_console = Console(stderr=True)
