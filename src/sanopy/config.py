"""Configuration management for Sanopy."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

from rich.console import Console

DEFAULT_CONFIG_PATH = Path(".sanopy.toml")

_console = Console(stderr=True)


def _dedupe_strings(values: list[str], *, upper: bool = False) -> list[str]:
    """Strip, case-normalize, and deduplicate a list of strings."""
    cleaned: list[str] = []
    for value in values:
        value = value.strip()
        if not value:
            continue
        value = value.upper() if upper else value.lower()
        if value not in cleaned:
            cleaned.append(value)
    return cleaned


@dataclass
class Config:
    """Configuration data for linter selection defaults.

    Attributes:
        only_linters: Linter names to run exclusively by default.
        skip_linters: Linter names to skip by default.
        ignored_cves: Safety CVE IDs to suppress. ``None`` keeps the
            linter's built-in defaults.
        ignore_vulns: pip-audit vulnerability IDs or aliases to suppress.
            ``None`` keeps the linter's built-in defaults.
    """

    only_linters: list[str] = field(default_factory=list)
    skip_linters: list[str] = field(default_factory=list)
    ignored_cves: list[str] | None = None
    ignore_vulns: list[str] | None = None

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

                pip_audit_data = data.get("pip-audit", {})
                if "ignore_vulns" in pip_audit_data:
                    filtered["ignore_vulns"] = pip_audit_data["ignore_vulns"]

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
        """Normalise all fields to canonical case-stripped values."""
        self.only_linters = _dedupe_strings(self.only_linters)
        self.skip_linters = _dedupe_strings(self.skip_linters)
        if self.ignored_cves is not None:
            self.ignored_cves = _dedupe_strings(self.ignored_cves, upper=True)
        if self.ignore_vulns is not None:
            self.ignore_vulns = _dedupe_strings(self.ignore_vulns, upper=True)

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
        if self.ignore_vulns is not None:
            lines.append("\n[pip-audit]\n")
            lines.append(f"ignore_vulns = {self.ignore_vulns}\n")

        config_path.write_text("".join(lines), encoding="utf-8")
