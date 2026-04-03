"""Tests for config.py — section-aware parsing and backward compatibility."""

from __future__ import annotations

from pathlib import Path

import pytest

from budmon.config import Config, CONFIG_FILE


@pytest.fixture()
def tmp_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect CONFIG_FILE to a temporary INI file."""
    ini = tmp_path / "budmon.ini"
    monkeypatch.setattr("budmon.config.CONFIG_FILE", ini)
    # Also suppress default-file copy
    monkeypatch.setattr("budmon.config.DEFAULT_INI", tmp_path / "nope.ini")
    return ini


class TestSectionAwareParsing:

    def test_flat_key_still_works(self, tmp_config: Path) -> None:
        tmp_config.write_text("[general]\nlanguage = en\n", encoding="utf-8")
        cfg = Config()
        assert cfg.language == "en"

    def test_section_key_accessible(self, tmp_config: Path) -> None:
        tmp_config.write_text(
            "[statusline]\nelements = burn_5h, cost\n", encoding="utf-8",
        )
        cfg = Config()
        assert cfg._section_str("statusline", "elements") == "burn_5h, cost"

    def test_keys_in_different_sections_dont_collide(
        self, tmp_config: Path,
    ) -> None:
        tmp_config.write_text(
            "[general]\nmax_width = 99\n"
            "[statusline]\nmax_width = 42\n",
            encoding="utf-8",
        )
        cfg = Config()
        assert cfg._section_int("statusline", "max_width") == 42
        # flat access returns last seen value
        assert cfg._int("max_width") == 42

    def test_missing_section_returns_default(self, tmp_config: Path) -> None:
        tmp_config.write_text("[general]\nlanguage = de\n", encoding="utf-8")
        cfg = Config()
        assert cfg.statusline_elements == [
            "cwd", "model_info", "5h_bar", "7d_bar", "countdown_5h", "reserve",
        ]

    def test_missing_file_returns_defaults(self, tmp_config: Path) -> None:
        # tmp_config not written → file doesn't exist
        cfg = Config()
        assert cfg.statusline_max_width == 80


class TestBackwardCompatibility:

    def test_existing_properties_unchanged(self, tmp_config: Path) -> None:
        tmp_config.write_text(
            "[general]\nlanguage = en\nrefresh_ms = 500\n"
            "[model]\nmodel = sonnet\n"
            "[thresholds]\nquota_warn_pct = 60.0\n"
            "[window]\ngeometry = +100+200\n",
            encoding="utf-8",
        )
        cfg = Config()
        assert cfg.language == "en"
        assert cfg.refresh_ms == 500
        assert cfg.model == "sonnet"
        assert cfg.quota_warn_pct == 60.0
        assert cfg.window_geometry == "+100+200"


class TestStatuslineProperties:

    def test_elements_parsed_from_config(self, tmp_config: Path) -> None:
        tmp_config.write_text(
            "[statusline]\nelements = burn_5h, cache, model\n",
            encoding="utf-8",
        )
        cfg = Config()
        assert cfg.statusline_elements == ["burn_5h", "cache", "model"]

    def test_elements_strips_whitespace(self, tmp_config: Path) -> None:
        tmp_config.write_text(
            "[statusline]\nelements =  5h_bar ,  cost \n",
            encoding="utf-8",
        )
        cfg = Config()
        assert cfg.statusline_elements == ["5h_bar", "cost"]

    def test_elements_empty_string_returns_default(
        self, tmp_config: Path,
    ) -> None:
        tmp_config.write_text("[statusline]\nelements =\n", encoding="utf-8")
        cfg = Config()
        assert cfg.statusline_elements == [
            "cwd", "model_info", "5h_bar", "7d_bar", "countdown_5h", "reserve",
        ]

    def test_max_width_from_config(self, tmp_config: Path) -> None:
        tmp_config.write_text(
            "[statusline]\nmax_width = 120\n", encoding="utf-8",
        )
        cfg = Config()
        assert cfg.statusline_max_width == 120

    def test_max_width_zero_returns_default(self, tmp_config: Path) -> None:
        tmp_config.write_text(
            "[statusline]\nmax_width = 0\n", encoding="utf-8",
        )
        cfg = Config()
        assert cfg.statusline_max_width == 80
