"""Tests for the configuration system."""

import pytest

from sanopy.config import Config


@pytest.mark.parametrize(
    "kwargs, expected_only, expected_skip, expected_cves",
    [
        # Defaults
        ({}, [], [], None),
        # Only linters
        ({"only_linters": ["ruff"]}, ["ruff"], [], None),
        # Normalization: case, whitespace, deduplication
        (
            {
                "only_linters": ["Ruff", " PYLINT ", "ruff"],
                "skip_linters": ["BanDit", "mypy"],
            },
            ["ruff", "pylint"],
            ["bandit", "mypy"],
            None,
        ),
        # Skip list deduplication
        (
            {"skip_linters": ["ruff", "pylint", "ruff", "bandit"]},
            [],
            ["ruff", "pylint", "bandit"],
            None,
        ),
        # Explicit empty lists
        ({"skip_linters": [], "only_linters": []}, [], [], None),
        # Whitespace-only entries are dropped
        (
            {"skip_linters": ["ruff", "  ", "\t", "pylint"]},
            [],
            ["ruff", "pylint"],
            None,
        ),
        # Ignored CVEs are uppercased and deduplicated
        (
            {"ignored_cves": ["cve-2026-0994", "CVE-2026-0994"]},
            [],
            [],
            ["CVE-2026-0994"],
        ),
        # Explicit empty ignored CVEs are preserved
        ({"ignored_cves": []}, [], [], []),
    ],
)
def test_config_roundtrip(
    tmp_path, kwargs, expected_only, expected_skip, expected_cves
):
    """Test that configuration values round-trip through save/load."""
    config_file = tmp_path / "sanopy.toml"
    Config(**kwargs).save(config_file)

    loaded = Config.load(config_file)

    assert loaded.only_linters == expected_only
    assert loaded.skip_linters == expected_skip
    assert loaded.ignored_cves == expected_cves


def test_config_default() -> None:
    """Test default config initialization."""
    config = Config()
    assert not config.only_linters
    assert not config.skip_linters
    assert config.ignored_cves is None


def test_config_save_writes_sections(tmp_path) -> None:
    """Test that save writes the expected TOML sections."""
    config_file = tmp_path / "sanopy.toml"
    Config(only_linters=["ruff"], ignored_cves=["CVE-1"]).save(config_file)

    content = config_file.read_text(encoding="utf-8")
    assert "[linters]" in content
    assert "only_linters = ['ruff']" in content
    assert "[safety]" in content
    assert "ignore_cves = ['CVE-1']" in content


def test_config_load_creates_defaults(tmp_path) -> None:
    """Test loading a non-existent config creates the file with defaults."""
    config_file = tmp_path / "non_existent.toml"
    config = Config.load(config_file)

    assert config_file.exists()
    assert not config.only_linters
    assert not config.skip_linters
    assert config.ignored_cves is None


@pytest.mark.parametrize(
    "content",
    [
        "not valid toml [[[",
        "[linters\nonly_linters = ",
    ],
)
def test_config_invalid_file_resets_to_defaults(
    tmp_path, content: str
) -> None:
    """Test that a corrupt config file is reset to defaults."""
    config_file = tmp_path / "bad.toml"
    config_file.write_text(content, encoding="utf-8")

    config = Config.load(config_file)

    assert not config.only_linters
    assert not config.skip_linters
    assert config.ignored_cves is None
    # The file is overwritten with valid defaults
    reloaded = Config.load(config_file)
    assert reloaded.only_linters == []


def test_config_ignores_unknown_linter_keys(tmp_path) -> None:
    """Test that unknown [linters] keys are ignored on load."""
    config_file = tmp_path / "test.toml"
    config_file.write_text(
        '[linters]\nonly_linters = ["ruff"]\nskip_linters = []\n'
        'color = "red"\n',
        encoding="utf-8",
    )

    loaded = Config.load(config_file)

    assert loaded.only_linters == ["ruff"]
    assert not hasattr(loaded, "color")


def test_config_load_safety_only(tmp_path) -> None:
    """Test loading a config with only a [safety] section."""
    config_file = tmp_path / "test.toml"
    config_file.write_text(
        '[safety]\nignore_cves = ["CVE-1", "cve-2"]\n', encoding="utf-8"
    )

    loaded = Config.load(config_file)

    assert loaded.ignored_cves == ["CVE-1", "CVE-2"]
    assert loaded.only_linters == []
    assert loaded.skip_linters == []
