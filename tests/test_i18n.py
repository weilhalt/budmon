"""Tests for budmon.i18n module."""

from __future__ import annotations

from budmon.i18n import (
    available_languages,
    current_language,
    help_file_path,
    language_name,
    load_language,
    t,
    t_list,
)


class TestAvailableLanguages:
    def test_has_de_and_en(self) -> None:
        langs = available_languages()
        assert "de" in langs
        assert "en" in langs

    def test_sorted(self) -> None:
        langs = available_languages()
        assert langs == sorted(langs)


class TestLoadLanguage:
    def test_load_de(self) -> None:
        load_language("de")
        assert current_language() == "de"
        assert t("title") == "BUDGET MONITOR"

    def test_load_en(self) -> None:
        load_language("en")
        assert current_language() == "en"
        assert t("waiting_for_data") == "Waiting for data..."

    def test_fallback_on_missing(self) -> None:
        load_language("xx_nonexistent")
        assert current_language() == "en"


class TestTranslate:
    def test_known_key(self) -> None:
        load_language("de")
        assert t("label_reset") == "Reset"

    def test_unknown_key_returns_key(self) -> None:
        assert t("this_key_does_not_exist") == "this_key_does_not_exist"


class TestTranslateList:
    def test_weekdays_de(self) -> None:
        load_language("de")
        days = t_list("weekdays")
        assert len(days) == 7
        assert days[0] == "Mo"

    def test_weekdays_en(self) -> None:
        load_language("en")
        days = t_list("weekdays")
        assert len(days) == 7
        assert days[0] == "Mon"

    def test_missing_key_returns_empty(self) -> None:
        assert t_list("nonexistent_list") == []


class TestLanguageName:
    def test_de(self) -> None:
        assert language_name("de") == "Deutsch"

    def test_en(self) -> None:
        assert language_name("en") == "English"


class TestHelpFilePath:
    def test_de_help_exists(self) -> None:
        load_language("de")
        assert help_file_path().name == "README.de.md"
        assert help_file_path().exists()

    def test_en_help_exists(self) -> None:
        load_language("en")
        assert help_file_path().name == "README.md"
        assert help_file_path().exists()
