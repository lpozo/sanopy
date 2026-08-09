"""Configuration management for Sanopy."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

from rich.console import Console

DEFAULT_CONFIG_PATH = Path(".sanopy.toml")

_console = Console(stderr=True)


@dataclass
class Config:
    """Configuration data for linter selection defaults.

    Attributes:
        only_linters: Linter names to run exclusively by default.
        skip_linters: Linter names to skip by default.
        ignored_cves: Safety CVE IDs to suppress. ``None`` keeps the
            linter's built-in defaults.
    """

    only_linters: list[str] = field(default_factory=list)
    skip_linters: list[str] = field(default_factory=list)
    ignored_cves: list[str] | None = None

    @classmethod
    def load(cls, path: Path | None = None) -> Self:
        """Load configuration from a TOML file.

        If the file does not exist, create it with default values.

        Args:
            path: Path to the configuration file. Defaults to .sanopy.toml.

        Returns:
            A Config instance.
        """
        config_path = path or DEFAULT_CONFIG_PATH

        if not config_path.exists():
            # Defaults: all linters active, no skip
            config = cls(only_linters=[], skip_linters=[])
            config.save(config_path)
            _console.print(
                "[Sanopy] Created default configuration at "
                f"{config_path}. Edit this file to customize "
                "linter selection."
            )
            return config

        try:
            with config_path.open("rb") as file:
                data = tomllib.load(file)
                linter_data = data.get("linters", {})

                valid_keys = {"only_linters", "skip_linters"}
                filtered = {
                    k: v for k, v in linter_data.items() if k in valid_keys
                }

                safety_data = data.get("safety", {})
                if "ignore_cves" in safety_data:
                    filtered["ignored_cves"] = safety_data["ignore_cves"]

                config = cls(**filtered)
                config._normalize()
                return config
        except (OSError, ValueError):
            # If the file is corrupt, reset to defaults and overwrite
            config = cls(only_linters=[], skip_linters=[])
            config.save(config_path)
            _console.print(
                "[Sanopy] Invalid configuration detected. "
                f"Reset to default at {config_path}."
            )
            return config

    def _normalize(self) -> None:
        """Normalise all fields to canonical lower-case, stripped values."""
        self.only_linters = list(
            dict.fromkeys(
                v.strip().lower() for v in self.only_linters if v.strip()
            )
        )
        self.skip_linters = list(
            dict.fromkeys(
                v.strip().lower() for v in self.skip_linters if v.strip()
            )
        )
        if self.ignored_cves is not None:
            self.ignored_cves = list(
                dict.fromkeys(
                    v.strip().upper() for v in self.ignored_cves if v.strip()
                )
            )

    def save(self, path: Path | None = None) -> None:
        """Normalise and persist the current configuration to a TOML file.

        Args:
            path: Destination path. Defaults to ``.sanopy.toml`` in the
                current working directory.
        """
        self._normalize()
        config_path = path or DEFAULT_CONFIG_PATH

        lines = ["[linters]\n"]
        lines.append(f"only_linters = {self.only_linters}\n")
        lines.append(f"skip_linters = {self.skip_linters}\n")
        if self.ignored_cves is not None:
            lines.append("\n[safety]\n")
            lines.append(f"ignore_cves = {self.ignored_cves}\n")

        config_path.write_text("".join(lines), encoding="utf-8")
