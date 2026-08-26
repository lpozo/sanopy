"""Tests for the shared linter-selection helpers."""

from typing import Any

import pytest

from sanopy.cli.selection import (
    format_install_hint,
    parse_linter_names,
    resolve_active_linters,
)
from sanopy.config import Config
from sanopy.linters import LINTER_MAP

ALL_LINTERS = list(LINTER_MAP.keys())


def _in_map_order(*names: str) -> list[str]:
    """Return ``names`` in LINTER_MAP order, which is the resolved order."""
    wanted = set(names)
    return [name for name in ALL_LINTERS if name in wanted]


@pytest.mark.parametrize(
    "raw, default, expected",
    [
        # Absent input keeps the caller's default.
        pytest.param(None, ["fallback"], ["fallback"], id="none"),
        pytest.param("", ["fallback"], ["fallback"], id="empty-string"),
        pytest.param(None, [], [], id="none-empty-default"),
        # Normalisation.
        pytest.param("ruff", [], ["ruff"], id="single"),
        pytest.param("ruff,mypy", [], ["ruff", "mypy"], id="two"),
        pytest.param(" ruff , mypy ", [], ["ruff", "mypy"], id="whitespace"),
        pytest.param("RUFF,MyPy", [], ["ruff", "mypy"], id="mixed-case"),
        pytest.param("\truff\n", [], ["ruff"], id="tabs-and-newlines"),
        # Empty entries are dropped rather than becoming "" names.
        pytest.param("ruff,,mypy", [], ["ruff", "mypy"], id="double-comma"),
        pytest.param("ruff,", [], ["ruff"], id="trailing-comma"),
        pytest.param(",ruff", [], ["ruff"], id="leading-comma"),
        pytest.param("ruff, ,mypy", [], ["ruff", "mypy"], id="blank-entry"),
        # Input that is *only* separators/whitespace falls back too.
        pytest.param("  ", ["fallback"], ["fallback"], id="spaces-only"),
        pytest.param(",", ["fallback"], ["fallback"], id="comma-only"),
        pytest.param(",,,", ["fallback"], ["fallback"], id="commas-only"),
        pytest.param(" , ", ["fallback"], ["fallback"], id="comma-spaces"),
        # Unknown names pass through; validation happens elsewhere.
        pytest.param("nope", [], ["nope"], id="unknown-name"),
        # Order and duplicates are preserved verbatim.
        pytest.param("mypy,ruff", [], ["mypy", "ruff"], id="order-kept"),
        pytest.param("ruff,ruff", [], ["ruff", "ruff"], id="duplicates-kept"),
    ],
)
def test_parse_linter_names(
    raw: str | None, default: list[str], expected: list[str]
) -> None:
    """Names are normalised, blank entries dropped, default used if empty."""
    assert parse_linter_names(raw, default) == expected


def test_parse_linter_names_returns_the_default_object_untouched() -> None:
    """The fallback must not be mutated or copied into a surprising shape."""
    default = ["ruff"]

    assert parse_linter_names(None, default) is default
    assert default == ["ruff"]


@pytest.mark.parametrize(
    "config_kwargs, only, skip, expected",
    [
        # No filters at all.
        pytest.param({}, None, None, ALL_LINTERS, id="no-filters"),
        # Config-only filtering.
        pytest.param(
            {"only_linters": ["ruff", "mypy"]},
            None,
            None,
            _in_map_order("ruff", "mypy"),
            id="config-only",
        ),
        pytest.param(
            {"skip_linters": ["ruff"]},
            None,
            None,
            [n for n in ALL_LINTERS if n != "ruff"],
            id="config-skip",
        ),
        pytest.param(
            {"only_linters": ["ruff", "mypy"], "skip_linters": ["mypy"]},
            None,
            None,
            ["ruff"],
            id="config-only-and-skip",
        ),
        # CLI-only filtering.
        pytest.param(
            {}, "ruff,mypy", None, _in_map_order("ruff", "mypy"), id="cli-only"
        ),
        pytest.param(
            {},
            None,
            "ruff",
            [n for n in ALL_LINTERS if n != "ruff"],
            id="cli-skip",
        ),
        # A CLI flag replaces its own config counterpart...
        pytest.param(
            {"only_linters": ["bandit"]},
            "ruff",
            None,
            ["ruff"],
            id="cli-only-replaces-config-only",
        ),
        pytest.param(
            {"skip_linters": ["bandit"]},
            None,
            "ruff",
            [n for n in ALL_LINTERS if n != "ruff"],
            id="cli-skip-replaces-config-skip",
        ),
        # ...but not the other one.
        pytest.param(
            {"skip_linters": ["ruff"]},
            "ruff,mypy",
            None,
            ["mypy"],
            id="config-skip-still-applies-to-cli-only",
        ),
        pytest.param(
            {"only_linters": ["bandit"]},
            None,
            "mypy",
            ["bandit"],
            id="config-only-still-applies-to-cli-skip",
        ),
        # only is applied before skip, so skip always wins a tie.
        pytest.param({}, "ruff", "ruff", [], id="only-and-skip-cancel"),
        # Normalisation reaches the resolver from both sources. A Config
        # built in code has not been through Config._normalize().
        pytest.param({}, " RUFF ", None, ["ruff"], id="cli-case-and-space"),
        pytest.param(
            {"only_linters": ["RUFF"]}, None, None, ["ruff"], id="config-case"
        ),
        pytest.param(
            {"skip_linters": [" Ruff "]},
            None,
            None,
            [n for n in ALL_LINTERS if n != "ruff"],
            id="config-skip-case-and-space",
        ),
        # Unknown names simply match nothing.
        pytest.param({}, "nope", None, [], id="unknown-only"),
        pytest.param({}, None, "nope", ALL_LINTERS, id="unknown-skip-noop"),
        pytest.param(
            {}, "ruff,nope", None, ["ruff"], id="partly-unknown-only"
        ),
        # Blank filters behave like absent ones, not like "match nothing".
        pytest.param({}, "  ", None, ALL_LINTERS, id="blank-only"),
        pytest.param({}, ",", None, ALL_LINTERS, id="comma-only-filter"),
        pytest.param({}, None, "  ", ALL_LINTERS, id="blank-skip"),
        # Skipping everything is expressible (and caught by preflight).
        pytest.param(
            {}, None, ",".join(ALL_LINTERS), [], id="skip-everything"
        ),
    ],
)
def test_resolve_active_linters(
    config_kwargs: dict[str, Any],
    only: str | None,
    skip: str | None,
    expected: list[str],
) -> None:
    """CLI flags override their config counterparts; only is applied first."""
    config = Config(**config_kwargs)

    assert resolve_active_linters(config, only=only, skip=skip) == expected


@pytest.mark.parametrize(
    "only, expected",
    [
        pytest.param("ruff,bandit", _in_map_order("ruff", "bandit"), id="two"),
        pytest.param("bandit,ruff", _in_map_order("ruff", "bandit"), id="rev"),
    ],
)
def test_resolve_active_linters_uses_linter_map_order(
    only: str, expected: list[str]
) -> None:
    """Result order follows LINTER_MAP, not the order the user typed."""
    assert resolve_active_linters(Config(), only=only) == expected


def test_resolve_active_linters_never_invents_names() -> None:
    """Every resolved name is a real key of LINTER_MAP."""
    config = Config(only_linters=["ruff", "nope"], skip_linters=["also-nope"])

    assert set(resolve_active_linters(config)) <= set(LINTER_MAP)


@pytest.mark.parametrize(
    "packages, expected",
    [
        pytest.param(["ruff"], "pip install 'sanopy[ruff]'", id="single"),
        pytest.param(
            ["pylint", "bandit"],
            "pip install 'sanopy[bandit,pylint]'",
            id="sorted-not-input-order",
        ),
        pytest.param(
            ["ruff", "ruff"], "pip install 'sanopy[ruff]'", id="deduplicated"
        ),
        pytest.param(
            ["pip-audit"],
            "pip install 'sanopy[pip-audit]'",
            id="hyphenated-extra",
        ),
        pytest.param(
            sorted(c.package_name for c in LINTER_MAP.values()),
            "pip install 'sanopy["
            + ",".join(sorted(c.package_name for c in LINTER_MAP.values()))
            + "]'",
            id="every-linter",
        ),
    ],
)
def test_format_install_hint(packages: list[str], expected: str) -> None:
    """Hints install through Sanopy's extras, sorted and deduplicated."""
    assert format_install_hint(packages) == expected


def _declared_extras() -> dict[str, list[str]]:
    """Read [project.optional-dependencies] from pyproject.toml."""
    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    with pyproject.open("rb") as file:
        extras = tomllib.load(file)["project"]["optional-dependencies"]

    assert isinstance(extras, dict)
    return extras


@pytest.mark.parametrize("package", sorted(LINTER_MAP))
def test_format_install_hint_names_a_real_extra(package: str) -> None:
    """Every linter's package_name must be a declared extra in pyproject.

    A hint naming an undeclared extra would fail when pasted.
    """
    assert LINTER_MAP[package].package_name in _declared_extras()


@pytest.mark.parametrize("package", sorted(LINTER_MAP))
def test_every_linter_extra_is_included_in_all(package: str) -> None:
    """`sanopy[all]` must pull in every linter.

    A new linter auto-registers in LINTER_MAP, so forgetting to add it to
    the `all` extra would silently ship an `all` install that cannot run
    the full set.
    """
    import re

    all_spec = _declared_extras()["all"][0]
    inside_brackets = all_spec.split("[", 1)[1].rstrip("]")
    bundled = set(re.findall(r"[\w.-]+", inside_brackets))

    assert LINTER_MAP[package].package_name in bundled


def test_scan_and_init_keep_no_private_selection_copies() -> None:
    """Neither command may reintroduce its own copy of this logic.

    Both used to filter LINTER_MAP privately, so `init` and `scan` could
    disagree about which linters were active.
    """
    from sanopy.cli import init_handler, scan_handler

    assert not hasattr(scan_handler, "_get_active_linters")
    assert not hasattr(init_handler, "_get_active_linter_names")
