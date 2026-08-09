"""Tests for the configuraton system."""

from sanopy.config import Config


def test_config_default() -> None:
    """Test default config initialization."""
    config = Config()
    assert not config.only_linters
    assert not config.skip_linters


def test_config_save_load(tmp_path) -> None:
    """Test saving and loading configuration from TOML."""
    config_file = tmp_path / "sanopy.toml"
    config = Config(only_linters=["ruff"], skip_linters=["bandit"])
    config.save(config_file)

    assert config_file.exists()
    content = config_file.read_text(encoding="utf-8")
    assert "[linters]" in content
    assert "only_linters = ['ruff']" in content

    loaded = Config.load(config_file)
    assert loaded.only_linters == ["ruff"]
    assert loaded.skip_linters == ["bandit"]


def test_config_load_non_existent(tmp_path) -> None:
    """Test loading a non-existent config returns defaults."""
    config_file = tmp_path / "non_existent.toml"
    config = Config.load(config_file)
    assert config_file.exists()
    assert not config.only_linters
    assert not config.skip_linters


def test_config_normalize_linter_lists(tmp_path) -> None:
    """Test normalization of linter lists via save/load."""
    config_file = tmp_path / "test.toml"
    Config(
        skip_linters=["Ruff", "PYLINT", "ruff"],
        only_linters=["BanDit", "mypy"],
    ).save(config_file)

    loaded = Config.load(config_file)
    assert loaded.skip_linters == ["ruff", "pylint"]
    assert loaded.only_linters == ["bandit", "mypy"]


def test_config_linter_list_deduplication(tmp_path) -> None:
    """Test that linter lists deduplicate via save/load."""
    config_file = tmp_path / "test.toml"
    Config(skip_linters=["ruff", "pylint", "ruff", "bandit"]).save(config_file)
    loaded = Config.load(config_file)
    assert loaded.skip_linters == ["ruff", "pylint", "bandit"]


def test_config_empty_linter_lists(tmp_path) -> None:
    """Test handling of empty linter lists via save/load."""
    config_file = tmp_path / "test.toml"
    Config(skip_linters=[], only_linters=[]).save(config_file)
    loaded = Config.load(config_file)
    assert not loaded.skip_linters
    assert not loaded.only_linters


def test_config_whitespace_only_linter_entries(tmp_path) -> None:
    """Test that whitespace-only linter entries are removed via save/load."""
    config_file = tmp_path / "test.toml"
    Config(skip_linters=["ruff", "  ", "\t", "pylint"]).save(config_file)
    loaded = Config.load(config_file)
    assert loaded.skip_linters == ["ruff", "pylint"]


def test_config_ignored_cves_roundtrip(tmp_path) -> None:
    """Test that [safety] ignore_cves round-trips through save/load."""
    config_file = tmp_path / "test.toml"
    Config(ignored_cves=["cve-2026-0994", "CVE-2026-0994"]).save(config_file)

    content = config_file.read_text(encoding="utf-8")
    assert "[safety]" in content
    assert "ignore_cves" in content

    loaded = Config.load(config_file)
    assert loaded.ignored_cves == ["CVE-2026-0994"]


def test_config_ignored_cves_default(tmp_path) -> None:
    """Test that a missing [safety] section yields None."""
    config_file = tmp_path / "test.toml"
    Config().save(config_file)

    loaded = Config.load(config_file)
    assert loaded.ignored_cves is None
