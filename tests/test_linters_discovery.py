"""Tests for dynamic linter discovery in the sanopy.linters package."""

import importlib
from typing import Any

import pytest

from sanopy.linters import LINTER_MAP, BaseLinter

KNOWN_LINTER_NAMES = {
    "bandit",
    "mypy",
    "pip-audit",
    "pylint",
    "pyright",
    "radon",
    "ruff",
    "safety",
    "semgrep",
    "vulture",
}


def test_discovery_finds_every_linter() -> None:
    """The public map contains exactly the shipped linters."""
    assert set(LINTER_MAP) == KNOWN_LINTER_NAMES
    assert all(issubclass(cls, BaseLinter) for cls in LINTER_MAP.values())


@pytest.mark.parametrize(
    "exc",
    [
        pytest.param(ImportError("broken"), id="import-error"),
        pytest.param(AttributeError("missing"), id="attribute-error"),
    ],
)
def test_discovery_skips_failing_module(mocker, exc: Exception) -> None:
    """A module that fails to import is skipped rather than fatal.

    Reloading the package re-runs discovery through the public module
    surface; one linter module raising ImportError (or AttributeError
    while its attributes are scanned) must not abort discovery of the
    others. The reload is restored afterwards so later tests see the
    complete map.
    """
    linters_pkg = importlib.import_module("sanopy.linters")
    real_import = importlib.import_module

    def _fail_one(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "sanopy.linters.ruff":
            raise exc
        return real_import(name, *args, **kwargs)

    patcher = mocker.patch(
        "sanopy.linters.importlib.import_module",
        side_effect=_fail_one,
    )
    try:
        reloaded = importlib.reload(linters_pkg)
        assert "ruff" not in reloaded.LINTER_MAP
        assert "mypy" in reloaded.LINTER_MAP
    finally:
        patcher.stop()
        importlib.reload(linters_pkg)


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
