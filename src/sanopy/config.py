"""Configuration management for Sanopy."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

DEFAULT_CONFIG_PATH = Path("sanopy.toml")


@dataclass
class Config:
    """Configuration data for linter selection defaults."""

    only_linters: list[str] = field(default_factory=list)
    skip_linters: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path | None = None) -> Self:
        """Load configuration from a TOML file and environment variables.

        Args:
            path: Path to the configuration file. Defaults to sanopy.toml.

        Returns:
            A Config instance.
        """
        config_path = path or DEFAULT_CONFIG_PATH

        if not config_path.exists():
            return cls()

        try:
            with config_path.open("rb") as file:
                data = tomllib.load(file)
                linter_data = data.get("linters", {})

                valid_keys = {"only_linters", "skip_linters"}
                filtered = {
                    k: v for k, v in linter_data.items() if k in valid_keys
                }

                config = cls(**filtered)
                config._normalize()
                return config
        except (OSError, ValueError):
            return cls()

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

    def save(self, path: Path | None = None) -> None:
        """Normalise and persist the current configuration to a TOML file.

        Args:
            path: Destination path. Defaults to ``sanopy.toml`` in the
                current working directory.
        """
        self._normalize()
        config_path = path or DEFAULT_CONFIG_PATH

        lines = ["[linters]\n"]
        lines.append(f"only_linters = {self.only_linters}\n")
        lines.append(f"skip_linters = {self.skip_linters}\n")

        config_path.write_text("".join(lines), encoding="utf-8")
