"""Internationalization for BudMon — loads JSON language files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_LANG_DIR = Path(__file__).parent / "lang"
_REPO_ROOT = Path(__file__).parent.parent

_DEFAULT_LANG = "en"
_strings: dict[str, Any] = {}
_lang: str = _DEFAULT_LANG


def available_languages() -> list[str]:
    """Return sorted list of language codes from lang/*.json files."""
    langs = [f.stem for f in _LANG_DIR.glob("*.json") if f.is_file()]
    langs.sort()
    return langs


def load_language(lang: str) -> None:
    """Load a language file into the active string table."""
    global _strings, _lang
    path = _LANG_DIR / f"{lang}.json"
    if not path.exists():
        path = _LANG_DIR / f"{_DEFAULT_LANG}.json"
        lang = _DEFAULT_LANG
    try:
        text = path.read_text(encoding="utf-8")
        _strings = json.loads(text)
        _lang = lang
    except (json.JSONDecodeError, OSError):
        _strings = {}
        _lang = lang


def t(key: str) -> str:
    """Translate a key. Returns the key itself as fallback."""
    val = _strings.get(key)
    if isinstance(val, str):
        return val
    return key


def t_list(key: str) -> list[str]:
    """Translate a key that maps to a list of strings."""
    val = _strings.get(key)
    if isinstance(val, list):
        return val
    return []


def current_language() -> str:
    """Return the active language code."""
    return _lang


def language_name(lang: str) -> str:
    """Return the display name for a language code."""
    path = _LANG_DIR / f"{lang}.json"
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        return data.get("language_name", lang)
    except (json.JSONDecodeError, OSError):
        return lang


def help_file_path() -> Path:
    """Return the path to the README for the active language."""
    if _lang == "en":
        path = _REPO_ROOT / "README.md"
    else:
        path = _REPO_ROOT / f"README.{_lang}.md"
    if path.exists():
        return path
    return _REPO_ROOT / "README.md"


def save_preference(lang: str) -> None:
    """Persist language choice via config."""
    from budmon.config import cfg as app_cfg
    app_cfg.set_language(lang)


def load_preference() -> str:
    """Read saved language preference from config."""
    from budmon.config import cfg as app_cfg
    lang = app_cfg.language
    if (_LANG_DIR / f"{lang}.json").exists():
        return lang
    return _DEFAULT_LANG


def init() -> None:
    """Initialize i18n from saved preference."""
    load_language(load_preference())


# Auto-init on import
init()
