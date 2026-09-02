"""Tests for the configuration system."""

import pytest

from sanopy.config import (
    DEFAULT_IGNORED_CVES,
    DEFAULT_IGNORED_VULNS,
    DEFAULT_LINTER_CONFIGS,
    Config,
    LinterConfig,
)


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


def test_config_save_is_atomic_and_leaves_no_temp_files(tmp_path) -> None:
    """save writes atomically and leaves no temp residue behind."""
    config_file = tmp_path / "sanopy.toml"
    config_file.write_text("old", encoding="utf-8")

    Config(only_linters=["ruff"]).save(config_file)

    loaded = Config.load(config_file)
    assert loaded.only_linters == ["ruff"]
    assert [p.name for p in tmp_path.iterdir()] == ["sanopy.toml"]


def test_config_save_cleans_temp_on_failure(tmp_path) -> None:
    """A failed save removes the temp file and leaves the target intact."""
    from unittest.mock import patch

    config_file = tmp_path / "sanopy.toml"
    config_file.write_text("original", encoding="utf-8")
    config = Config(only_linters=["ruff"])

    with (
        patch("pathlib.Path.replace", side_effect=OSError("disk full")),
        pytest.raises(OSError),
    ):
        config.save(config_file)

    assert config_file.read_text(encoding="utf-8") == "original"
    assert [p.name for p in tmp_path.iterdir()] == ["sanopy.toml"]


def test_config_load_raises_when_file_missing(tmp_path) -> None:
    """Test loading a non-existent config raises FileNotFoundError."""
    config_file = tmp_path / "non_existent.toml"

    with pytest.raises(FileNotFoundError, match="sanopy init"):
        Config.load(config_file)

    assert not config_file.exists()


def test_config_load_propagates_os_error(tmp_path) -> None:
    """OSError from reading the file is not masked as ValueError.

    Permission errors and disk failures are OS-level issues, not
    invalid TOML — re-raising them as ValueError("Invalid
    configuration") hides the real cause from callers.
    """
    from unittest.mock import patch

    config_file = tmp_path / ".sanopy.toml"
    config_file.write_text("[linters]\n", encoding="utf-8")

    with (
        patch(
            "sanopy.config.tomllib.load",
            side_effect=PermissionError("Permission denied"),
        ),
        pytest.raises(OSError, match="Permission denied"),
    ):
        Config.load(config_file)


@pytest.mark.parametrize(
    "content",
    [
        pytest.param("not valid toml [[[", id="garbage"),
        pytest.param("[linters\nonly_linters = ", id="unterminated-table"),
        pytest.param("only_linters = [", id="unterminated-list"),
        pytest.param("key = ", id="missing-value"),
        pytest.param('a = "unterminated', id="unterminated-string"),
        pytest.param("[a]\nx = 1\n[a]\nx = 2", id="duplicate-table"),
        pytest.param("x = 1\nx = 2", id="duplicate-key"),
        pytest.param("\x00\x01binary", id="binary-junk"),
    ],
)
def test_config_load_raises_on_invalid_toml(tmp_path, content: str) -> None:
    """Test that an invalid config file raises ValueError."""
    config_file = tmp_path / "bad.toml"
    config_file.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="sanopy init"):
        Config.load(config_file)

    # The file is NOT overwritten
    assert config_file.read_text(encoding="utf-8") == content


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
    assert not loaded.only_linters
    assert not loaded.skip_linters


@pytest.mark.parametrize(
    "ignore_vulns, expected",
    [
        # Defaults
        (None, None),
        # Uppercased and deduplicated
        (
            ["pysec-2026-3482", "PYSEC-2026-3482"],
            ["PYSEC-2026-3482"],
        ),
        # Explicit empty list is preserved
        ([], []),
    ],
)
def test_config_roundtrip_pip_audit_ignore_vulns(
    tmp_path, ignore_vulns, expected
) -> None:
    """Test that pip-audit ignore list round-trips through save/load."""
    config_file = tmp_path / "sanopy.toml"
    Config(ignore_vulns=ignore_vulns).save(config_file)

    loaded = Config.load(config_file)

    assert loaded.ignore_vulns == expected


def test_config_save_writes_pip_audit_section(tmp_path) -> None:
    """Test that save writes the [pip-audit] section."""
    config_file = tmp_path / "sanopy.toml"
    Config(ignore_vulns=["PYSEC-1"]).save(config_file)

    content = config_file.read_text(encoding="utf-8")
    assert "[pip-audit]" in content
    assert "ignore_vulns = ['PYSEC-1']" in content


def test_config_load_pip_audit_only(tmp_path) -> None:
    """Test loading a config with only a [pip-audit] section."""
    config_file = tmp_path / "test.toml"
    config_file.write_text(
        '[pip-audit]\nignore_vulns = ["pysec-2026-3482"]\n',
        encoding="utf-8",
    )

    loaded = Config.load(config_file)

    assert loaded.ignore_vulns == ["PYSEC-2026-3482"]
    assert not loaded.only_linters
    assert not loaded.skip_linters


def test_config_save_writes_linter_sections(tmp_path) -> None:
    """Test that save writes [linters.<name>] sections and test overrides."""
    config_file = tmp_path / "sanopy.toml"
    Config(
        linter_configs={
            "ruff": LinterConfig(
                settings={"select": ["E"], "ignore": []},
                test={"ignore": ["S101"]},
            )
        }
    ).save(config_file)

    content = config_file.read_text(encoding="utf-8")
    assert "[linters.ruff]" in content
    assert "select = ['E']" in content
    assert "[linters.ruff.test]" in content
    assert "ignore = ['S101']" in content


def test_config_roundtrip_linter_configs(tmp_path) -> None:
    """Test that per-linter settings round-trip through save/load."""
    config_file = tmp_path / "sanopy.toml"
    original = Config(
        linter_configs={
            "ruff": LinterConfig(
                settings={"select": ["E", "F"], "ignore": ["S101"]},
                test={"ignore": ["S101", "ARG001"]},
            )
        }
    )
    original.save(config_file)

    loaded = Config.load(config_file)

    assert loaded.linter_configs["ruff"].settings == {
        "select": ["E", "F"],
        "ignore": ["S101"],
    }
    assert loaded.linter_configs["ruff"].test == {"ignore": ["S101", "ARG001"]}


def test_config_load_merges_default_linter_settings(tmp_path) -> None:
    """Test that a partial section keeps the bundled defaults for gaps."""
    config_file = tmp_path / "test.toml"
    config_file.write_text(
        '[linters.ruff]\nignore = ["X"]\n', encoding="utf-8"
    )

    loaded = Config.load(config_file)

    ruff = loaded.linter_configs["ruff"]
    assert ruff.settings["ignore"] == ["X"]
    assert "E" in ruff.settings["select"]
    assert ruff.test == {"ignore": ["S101", "ARG001"]}


def test_config_load_test_section_overrides_defaults(tmp_path) -> None:
    """Test that a [linters.<name>.test] section overrides the default."""
    config_file = tmp_path / "test.toml"
    config_file.write_text(
        '[linters.bandit]\nskips = ["B101"]\n'
        "[linters.bandit.test]\nskips = []\n",
        encoding="utf-8",
    )

    loaded = Config.load(config_file)

    bandit = loaded.linter_configs["bandit"]
    assert bandit.settings["skips"] == ["B101"]
    assert bandit.test == {"skips": []}


def test_config_normalizes_linter_config_values(tmp_path) -> None:
    """Test that linter settings are stripped and deduplicated."""
    config_file = tmp_path / "test.toml"
    config_file.write_text(
        '[linters.pylint]\ndisable = [" C0415 ", "C0415", "W0621"]\n',
        encoding="utf-8",
    )

    loaded = Config.load(config_file)

    assert loaded.linter_configs["pylint"].settings["disable"] == [
        "C0415",
        "W0621",
    ]


@pytest.mark.parametrize(
    "content, expected",
    [
        pytest.param("[linters]\n", True, id="valid-file"),
        pytest.param("", True, id="empty-file"),
        pytest.param("not valid toml [[[", True, id="invalid-file-still-is"),
        pytest.param(None, False, id="absent"),
    ],
)
def test_config_exists(tmp_path, content: str | None, expected: bool) -> None:
    """exists() is a pure presence check; it never parses the file."""
    config_file = tmp_path / ".sanopy.toml"
    if content is not None:
        config_file.write_text(content, encoding="utf-8")

    assert Config.exists(config_file) is expected


def test_config_exists_reports_false_for_a_directory(tmp_path) -> None:
    """A directory named .sanopy.toml is not a usable config file."""
    (tmp_path / ".sanopy.toml").mkdir()

    # Path.exists() is true for directories, so this documents the gap:
    # load() is what rejects it, with an OSError (IsADirectoryError).
    assert Config.exists(tmp_path / ".sanopy.toml") is True
    with pytest.raises(OSError):
        Config.load(tmp_path / ".sanopy.toml")


def test_config_exists_uses_default_path(monkeypatch, tmp_path) -> None:
    """Config.exists() without a path checks .sanopy.toml in cwd."""
    monkeypatch.chdir(tmp_path)
    assert Config.exists() is False

    (tmp_path / ".sanopy.toml").write_text("[linters]\n", encoding="utf-8")
    assert Config.exists() is True


def test_config_defaults_materializes_every_section(tmp_path) -> None:
    """Config.defaults() fills in all sections so save() writes them out."""
    config = Config.defaults()

    assert config.ignored_cves == DEFAULT_IGNORED_CVES
    assert config.ignore_vulns == DEFAULT_IGNORED_VULNS
    assert config.linter_configs == DEFAULT_LINTER_CONFIGS

    config_file = tmp_path / ".sanopy.toml"
    config.save(config_file)

    content = config_file.read_text(encoding="utf-8")
    assert "[safety]" in content
    assert "[pip-audit]" in content
    for name in ("pylint", "bandit", "ruff"):
        assert f"[linters.{name}]" in content


def test_config_defaults_does_not_share_mutable_state() -> None:
    """Each defaults() call must be independently mutable."""
    first = Config.defaults()
    second = Config.defaults()

    assert first.ignored_cves is not None
    first.ignored_cves.append("CVE-9999-1")

    assert second.ignored_cves == DEFAULT_IGNORED_CVES
    assert "CVE-9999-1" not in DEFAULT_IGNORED_CVES


def test_config_defaults_round_trips_through_save_and_load(tmp_path) -> None:
    """What defaults() writes must read back identically.

    `init` writes this file and `scan` reads it, so a lossy round trip
    would silently change which linters run.
    """
    config_file = tmp_path / ".sanopy.toml"
    Config.defaults().save(config_file)

    reloaded = Config.load(config_file)

    assert reloaded == Config.defaults()


def test_default_suppressions_stay_minimal() -> None:
    """Shipped defaults are seeded into user configs, so keep them minimal.

    Suppressions specific to Sanopy's own environment belong in Sanopy's
    own .sanopy.toml, which replaces these defaults rather than extending
    them. Guard against them creeping back into the shipped defaults.
    """
    assert DEFAULT_IGNORED_CVES == ["CVE-2026-0994"]
