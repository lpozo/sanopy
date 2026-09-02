"""Tests for dynamic linter discovery in the sanopy.linters package."""

import importlib
from typing import Any

import pytest

from sanopy.linters import LINTER_MAP, BaseLinter


def _discover() -> dict[str, type[BaseLinter]]:
    """Exercise the private discovery routine directly."""
    from sanopy.linters import _discover_linters

    return _discover_linters()


def test_discovery_finds_every_linter() -> None:
    """Discovery builds a map keyed by lowercase linter name."""
    discovered = _discover()

    assert set(discovered) == set(LINTER_MAP)
    assert all(issubclass(cls, BaseLinter) for cls in discovered.values())


@pytest.mark.parametrize(
    "exc",
    [
        pytest.param(ImportError("broken"), id="import-error"),
        pytest.param(AttributeError("missing"), id="attribute-error"),
    ],
)
def test_discovery_skips_failing_module(mocker, exc: Exception) -> None:
    """A module that fails to import is skipped rather than fatal.

    One linter module raising ImportError (or AttributeError while its
    attributes are scanned) must not abort discovery of the others.
    """
    real_import = importlib.import_module

    def _fail_one(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "sanopy.linters.ruff":
            raise exc
        return real_import(name, *args, **kwargs)

    mocker.patch(
        "sanopy.linters.importlib.import_module",
        side_effect=_fail_one,
    )

    discovered = _discover()

    assert "ruff" not in discovered
    assert "mypy" in discovered


def test_package_exports_only_public_names() -> None:
    """The package exposes only the documented public API."""
    from sanopy import linters

    assert linters.__all__ == [
        "BaseLinter",
        "Engine",
        "LinterResult",
        "LINTER_MAP",
    ]
    for name in (
        "RuffLinter",
        "PylintLinter",
        "BanditLinter",
        "MyPyLinter",
        "PyrightLinter",
        "SemgrepLinter",
        "VultureLinter",
        "RadonLinter",
        "SafetyLinter",
        "PipAuditLinter",
    ):
        assert not hasattr(linters, name)
