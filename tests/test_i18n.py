"""Tests for the i18n (internationalization) module."""

from __future__ import annotations

import pytest

from faultray.i18n import MESSAGES, available_languages, get_language, set_language, t


@pytest.fixture(autouse=True)
def _reset_language():
    """Reset language to English before and after each test."""
    set_language("en")
    yield
    set_language("en")


class TestSetLanguage:
    """Test set_language function."""

    def test_set_english(self):
        set_language("en")
        assert get_language() == "en"

    def test_set_japanese(self):
        set_language("ja")
        assert get_language() == "ja"

    def test_unsupported_language_falls_back_to_english(self):
        set_language("fr")
        assert get_language() == "en"

    def test_empty_string_falls_back_to_english(self):
        set_language("")
        assert get_language() == "en"


class TestTranslation:
    """Test the t() translation function."""

    def test_translate_english(self):
        set_language("en")
        assert t("resilience_score") == "Resilience Score"

    def test_translate_japanese(self):
        set_language("ja")
        assert t("resilience_score") == "レジリエンススコア"

    def test_translate_with_interpolation(self):
        set_language("en")
        result = t("scan_complete", count=42)
        assert result == "Scan complete: 42 components discovered"

    def test_translate_with_interpolation_japanese(self):
        set_language("ja")
        result = t("scan_complete", count=5)
        assert result == "スキャン完了: 5個のコンポーネントを検出"

    def test_missing_key_returns_key(self):
        result = t("nonexistent_key")
        assert result == "nonexistent_key"

    def test_all_english_keys_have_japanese_translations(self):
        for key in MESSAGES["en"]:
            assert key in MESSAGES["ja"], f"Missing Japanese translation for '{key}'"

    def test_all_japanese_keys_have_english_translations(self):
        for key in MESSAGES["ja"]:
            assert key in MESSAGES["en"], f"Missing English translation for '{key}'"


class TestAvailableLanguages:
    """Test available_languages function."""

    def test_returns_sorted_list(self):
        langs = available_languages()
        assert isinstance(langs, list)
        assert langs == sorted(langs)

    def test_includes_en_and_ja(self):
        langs = available_languages()
        assert "en" in langs
        assert "ja" in langs


class TestMessages:
    """Test message dictionary structure."""

    def test_messages_is_not_empty(self):
        assert len(MESSAGES) >= 2

    def test_each_language_has_messages(self):
        for lang, messages in MESSAGES.items():
            assert len(messages) > 0, f"Language '{lang}' has no messages"

    def test_no_issues_translation(self):
        set_language("en")
        assert t("no_issues") == "No issues found"
        set_language("ja")
        assert t("no_issues") == "問題は見つかりませんでした"
