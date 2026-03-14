"""Simple internationalization framework without gettext dependency.

Provides message translation for supported languages.  Defaults to English
so existing behaviour is unchanged.

Usage::

    from infrasim.i18n import t, set_language

    set_language("ja")
    print(t("resilience_score"))       # "レジリエンススコア"
    print(t("scan_complete", count=5)) # "スキャン完了: 5個のコンポーネントを検出"
"""

from __future__ import annotations

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "resilience_score": "Resilience Score",
        "critical_findings": "Critical Findings",
        "warning_findings": "Warnings",
        "passed_scenarios": "Passed",
        "no_issues": "No issues found",
        "scan_complete": "Scan complete: {count} components discovered",
        "simulation_running": "Running chaos simulation...",
        "simulation_complete": "Simulation complete",
        "error_recovery": "Error recovered: {detail}",
        "telemetry_disabled": "Telemetry is disabled",
        "telemetry_enabled": "Telemetry is enabled",
        "loading_model": "Loading infrastructure model...",
        "model_saved": "Model saved to {path}",
    },
    "ja": {
        "resilience_score": "レジリエンススコア",
        "critical_findings": "重大な発見",
        "warning_findings": "警告",
        "passed_scenarios": "合格",
        "no_issues": "問題は見つかりませんでした",
        "scan_complete": "スキャン完了: {count}個のコンポーネントを検出",
        "simulation_running": "カオスシミュレーションを実行中...",
        "simulation_complete": "シミュレーション完了",
        "error_recovery": "エラー回復: {detail}",
        "telemetry_disabled": "テレメトリは無効です",
        "telemetry_enabled": "テレメトリは有効です",
        "loading_model": "インフラモデルを読み込み中...",
        "model_saved": "モデルを{path}に保存しました",
    },
}

_current_lang = "en"


def set_language(lang: str) -> None:
    """Set the active language.

    Falls back to English if the requested language is not supported.
    """
    global _current_lang
    _current_lang = lang if lang in MESSAGES else "en"


def get_language() -> str:
    """Return the currently active language code."""
    return _current_lang


def available_languages() -> list[str]:
    """Return list of supported language codes."""
    return sorted(MESSAGES.keys())


def t(key: str, **kwargs) -> str:
    """Translate a message key.

    Keyword arguments are interpolated into the message via ``str.format()``.
    Returns the key itself if no translation is found.
    """
    msg = MESSAGES.get(_current_lang, MESSAGES["en"]).get(key, key)
    return msg.format(**kwargs) if kwargs else msg
