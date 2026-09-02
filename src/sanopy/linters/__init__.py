"""Linter discovery and management package."""

import importlib
import pkgutil
from pathlib import Path

from sanopy.linters.base import BaseLinter
from sanopy.linters.engine import Engine
from sanopy.linters.result import LinterResult


def _discover_linters() -> dict[str, type[BaseLinter]]:
    """Dynamically discover all BaseLinter subclasses in this package.

    Iterates through all modules in the current package and identifies
    classes that inherit from BaseLinter (excluding BaseLinter itself).

    Returns:
        A dictionary mapping lowercase linter names to their classes.
    """
    linter_map: dict[str, type[BaseLinter]] = {}
    package_path = [str(Path(__file__).parent)]

    for _, module_name, is_pkg in pkgutil.iter_modules(package_path):
        if is_pkg or module_name in (
            "base",
            "engine",
            "result",
            "context",
            "config_discovery",
        ):
            continue

        try:
            # module_name comes from pkgutil.iter_modules() over this
            # package's own directory, so it is never user-controlled.
            module = importlib.import_module(  # nosemgrep
                f"sanopy.linters.{module_name}"
            )
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BaseLinter)
                    and attr is not BaseLinter
                ):
                    linter_map[attr.name.lower()] = attr
        except (ImportError, AttributeError):
            continue

    return linter_map


# Build the dynamic map
LINTER_MAP = _discover_linters()

# Export core classes and the map
__all__ = ["BaseLinter", "Engine", "LinterResult", "LINTER_MAP"]
