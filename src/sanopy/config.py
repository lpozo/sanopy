"""Configuration management for Sanopy."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

from rich.console import Console

DEFAULT_CONFIG_PATH = Path(".sanopy.toml")

# Known vulnerabilities that cannot be resolved through the dependency tree.
DEFAULT_IGNORED_CVES = ["CVE-2026-0994"]
DEFAULT_IGNORED_VULNS = [
    "PYSEC-2026-3481",
    "PYSEC-2026-3482",
    "PYSEC-2026-3483",
]

_console = Console(stderr=True)


def _strip_dedupe(values: list[str]) -> list[str]:
    """Strip whitespace and deduplicate while preserving order."""
    cleaned: list[str] = []
    for value in values:
        value = value.strip()
        if value and value not in cleaned:
            cleaned.append(value)
    return cleaned


def _dedupe_strings(values: list[str], *, upper: bool = False) -> list[str]:
    """Strip, case-normalize, and deduplicate a list of strings."""
    return [v.upper() if upper else v.lower() for v in _strip_dedupe(values)]


@dataclass
class LinterConfig:
    """Native configuration settings for a linter.

    Attributes:
        settings: The default-category settings (e.g. pylint ``disable``).
        test: Optional overrides applied when scanning test code.
    """

    settings: dict[str, list[str]] = field(default_factory=dict)
    test: dict[str, list[str]] | None = None

    def effective(self, category: str) -> dict[str, list[str]]:
        """Merge test overrides into the base settings for a category.

        Args:
            category: The code category ('default' or 'test').

        Returns:
            The effective settings for that category.
        """
        settings = dict(self.settings)
        if category == "test" and self.test:
            settings.update(self.test)
        return settings


DEFAULT_LINTER_CONFIGS: dict[str, LinterConfig] = {
    "pylint": LinterConfig(
        settings={"disable": ["duplicate-code", "too-many-locals"]},
        test={
            "disable": [
                "C0415",
                "W0621",
                "W0613",
                "W0612",
                "C0116",
                "R0913",
                "R0917",
                "R0801",
            ]
        },
    ),
    "bandit": LinterConfig(
        settings={"skips": []},
        test={"skips": ["B101"]},
    ),
    "ruff": LinterConfig(
        settings={
            "select": [
                "E",
                "F",
                "W",
                "I",
                "N",
                "UP",
                "B",
                "A",
                "C4",
                "SIM",
                "PTH",
            ],
            "ignore": [],
        },
        test={"ignore": ["S101", "ARG001"]},
    ),
}


def _normalize_settings(
    settings: dict[str, list[str]],
) -> dict[str, list[str]]:
    return {k: _strip_dedupe(v) for k, v in settings.items()}


def _render_settings(
    settings: dict[str, list[str]],
) -> list[str]:
    return [f"{k} = {v}\n" for k, v in settings.items()]


def _as_section(data: object, key: str) -> dict[str, object]:
    """Return a table value, or an empty dict when missing/invalid."""
    section = data.get(key) if isinstance(data, dict) else None
    return section if isinstance(section, dict) else {}


def _list_from_section(
    section: dict[str, object], key: str
) -> list[str] | None:
    """Return a list value from a table, or None when absent/invalid."""
    value = section.get(key)
    if not isinstance(value, list):
        return None
    return [str(item) for item in value]


def _list_settings(section: dict[str, object]) -> dict[str, list[str]]:
    """Extract list-valued settings, skipping the test sub-table."""
    return {
        k: v for k, v in section.items() if k != "test" and isinstance(v, list)
    }


def _merge_linter_config(
    name: str, section: dict[str, object]
) -> LinterConfig:
    """Merge a [linters.<name>] section with the built-in defaults."""
    base = DEFAULT_LINTER_CONFIGS.get(name)
    settings = dict(base.settings) if base else {}
    settings.update(_list_settings(section))

    test = dict(base.test) if base and base.test else {}
    test.update(_list_settings(_as_section(section, "test")))

    return LinterConfig(settings=settings, test=test if test else None)


def _load_linter_configs(
    linter_data: dict[str, object],
) -> dict[str, LinterConfig]:
    """Merge [linters.<name>] sections with the built-in defaults.

    Provided keys win over the defaults; omitted keys keep the defaults.
    A ``[linters.<name>.test]`` sub-table overrides the test category.
    """
    valid_keys = {"only_linters", "skip_linters"}
    names = set(DEFAULT_LINTER_CONFIGS)
    names.update(
        name
        for name, value in linter_data.items()
        if name not in valid_keys and isinstance(value, dict)
    )

    return {
        name: _merge_linter_config(name, _as_section(linter_data, name))
        for name in names
    }


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
        linter_configs: Native settings per linter from the
            ``[linters.<name>]`` sections, merged with the bundled
            defaults.
    """

    only_linters: list[str] = field(default_factory=list)
    skip_linters: list[str] = field(default_factory=list)
    ignored_cves: list[str] | None = None
    ignore_vulns: list[str] | None = None
    linter_configs: dict[str, LinterConfig] = field(default_factory=dict)

    @classmethod
    def _defaults_with_materialized_sections(cls) -> Self:
        """A config with all built-in defaults materialized for writing."""
        return cls(
            ignored_cves=list(DEFAULT_IGNORED_CVES),
            ignore_vulns=list(DEFAULT_IGNORED_VULNS),
            linter_configs=_load_linter_configs({}),
        )

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
            config = cls._defaults_with_materialized_sections()
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
                linter_data = _as_section(data, "linters")

                config = cls(
                    only_linters=(
                        _list_from_section(linter_data, "only_linters") or []
                    ),
                    skip_linters=(
                        _list_from_section(linter_data, "skip_linters") or []
                    ),
                    ignored_cves=_list_from_section(
                        _as_section(data, "safety"), "ignore_cves"
                    ),
                    ignore_vulns=_list_from_section(
                        _as_section(data, "pip-audit"), "ignore_vulns"
                    ),
                    linter_configs=_load_linter_configs(linter_data),
                )
                config._normalize()
                return config
        except (OSError, ValueError):
            config = cls._defaults_with_materialized_sections()
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
        for linter_config in self.linter_configs.values():
            linter_config.settings = _normalize_settings(
                linter_config.settings
            )
            if linter_config.test is not None:
                linter_config.test = _normalize_settings(linter_config.test)

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

        for name, linter_config in self.linter_configs.items():
            lines.append(f"\n[linters.{name}]\n")
            lines.extend(_render_settings(linter_config.settings))
            if linter_config.test is not None:
                lines.append(f"\n[linters.{name}.test]\n")
                lines.extend(_render_settings(linter_config.test))

        if self.ignored_cves is not None:
            lines.append("\n[safety]\n")
            lines.append(f"ignore_cves = {self.ignored_cves}\n")
        if self.ignore_vulns is not None:
            lines.append("\n[pip-audit]\n")
            lines.append(f"ignore_vulns = {self.ignore_vulns}\n")

        config_path.write_text("".join(lines), encoding="utf-8")
