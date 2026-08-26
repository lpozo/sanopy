"""Shared fixtures for the test suite."""

import pytest

from sanopy.config import Config
from sanopy.linters import LINTER_MAP


@pytest.fixture
def mock_scan_config(mocker):
    """Make scan preflight succeed with default config and every linter.

    Not autouse: patching ``is_available`` globally would hide real
    resolution behaviour from the linter tests that exercise it. CLI test
    modules opt in with a module-level autouse wrapper.
    """
    mocker.patch("sanopy.cli.scan_handler.Config.load", return_value=Config())
    mocker.patch("sanopy.cli.scan_handler.Config.exists", return_value=True)
    for cls in LINTER_MAP.values():
        mocker.patch.object(cls, "is_available", return_value=True)
