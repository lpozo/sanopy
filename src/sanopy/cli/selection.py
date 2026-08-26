"""Shared resolution of the active linter set.

Both the ``init`` and ``scan`` flows need to know which linters a given
configuration selects. They resolve it here so the two commands can never
disagree about what "active" means.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sanopy.linters import LINTER_MAP

if TYPE_CHECKING:
    from sanopy.config import Config


def parse_linter_names(names: str | None, default: list[str]) -> list[str]:
    """Parse a comma-separated linter name string into a normalised list.

    Empty entries are dropped, so ``"ruff,,mypy"``, ``","`` and ``"  "``
    do not yield ``""`` names — an empty name would match no linter and
    silently reduce the active set to nothing.

    Args:
        names: Comma-separated linter names, or ``None`` to use the default.
        default: The list to return when ``names`` is ``None``, empty, or
            contains no non-empty entries.

    Returns:
        A list of lowercase linter name strings.
    """
    if not names:
        return default
    parsed = [
        name.strip().lower() for name in names.split(",") if name.strip()
    ]
    return parsed or default


def _canonical(names: list[str]) -> list[str]:
    """Lowercase and strip names for comparison against LINTER_MAP keys."""
    return [name.strip().lower() for name in names]


def resolve_active_linters(
    config: Config, only: str | None = None, skip: str | None = None
) -> list[str]:
    """Determine which linters to run based on config and CLI overrides.

    CLI flags take precedence over config file values. ``only`` is applied
    before ``skip``.

    Args:
        config: The configuration supplying default filter lists.
        only: Optional comma-separated linter names to run exclusively.
        skip: Optional comma-separated linter names to exclude.

    Returns:
        An ordered list of active linter name strings, in LINTER_MAP order.
    """
    # LINTER_MAP keys are lowercase, so both sides of the comparison are
    # normalised here. Config.load() already normalises, but a Config built
    # in code has not been through it.
    only_list = _canonical(parse_linter_names(only, config.only_linters))
    skip_list = _canonical(parse_linter_names(skip, config.skip_linters))

    active = list(LINTER_MAP.keys())
    if only_list:
        active = [name for name in active if name in only_list]
    if skip_list:
        active = [name for name in active if name not in skip_list]
    return active


def format_install_hint(package_names: list[str]) -> str:
    """Build the extras-based install command for missing linters.

    Linters ship as optional extras, so the hint installs them through
    Sanopy's own extras rather than as loose packages.

    Callers printing this through Rich must pass it through
    ``rich.markup.escape``, or the markup parser strips the ``[extras]``
    brackets.

    Args:
        package_names: PyPI names of the missing linter packages.

    Returns:
        A copy-pasteable ``pip install`` command.
    """
    extras = ",".join(sorted(set(package_names)))
    return f"pip install 'sanopy[{extras}]'"
