"""Central configuration for BudMon — reads ~/.claude/budmon.ini.

Uses a custom INI parser that preserves comments and commented-out values.
"""

from __future__ import annotations

import locale
import shutil
from pathlib import Path

CONFIG_FILE = Path.home() / ".claude" / "budmon.ini"
DEFAULT_INI = Path(__file__).parent / "budmon.default.ini"

# ---------------------------------------------------------------------------
# Model price presets (per 1M tokens, USD)
# ---------------------------------------------------------------------------

MODEL_PRESETS: dict[str, dict[str, float]] = {
    "opus": {
        "input": 15.0, "output": 75.0,
        "cache_read": 1.5, "cache_create": 18.75,
    },
    "sonnet": {
        "input": 3.0, "output": 15.0,
        "cache_read": 0.30, "cache_create": 3.75,
    },
    "haiku": {
        "input": 0.80, "output": 4.0,
        "cache_read": 0.08, "cache_create": 1.0,
    },
}

# ---------------------------------------------------------------------------
# Defaults (used when key is missing from file)
# ---------------------------------------------------------------------------

_DEFAULTS: dict[str, str] = {
    "language": "auto",
    "model": "opus",
    "refresh_ms": "1000",
    "quota_warn_pct": "75.0",
    "quota_alarm_pct": "90.0",
    "cache_warn_ratio": "0.50",
    "cache_alarm_ratio": "0.20",
    "burn_safe_pct_h": "15.0",
    "burn_warn_pct_h": "25.0",
    "price_input": "15.0",
    "price_output": "75.0",
    "price_cache_read": "1.5",
    "price_cache_create": "18.75",
    "geometry": "",
    "statusline.elements": "cwd, model_info, 5h_bar, 7d_bar, countdown_5h, reserve",
    "statusline.max_width": "80",
}


def _detect_system_language() -> str:
    """Detect system language, return 'de' or 'en'."""
    try:
        lang = locale.getlocale()[0] or ""
    except ValueError:
        lang = ""
    if lang.startswith("de"):
        return "de"
    return "en"


class Config:
    """Configuration backed by an INI file — preserves comments on save."""

    def __init__(self) -> None:
        self._values: dict[str, str] = dict(_DEFAULTS)
        self._ensure_file()
        self._load()

    def _ensure_file(self) -> None:
        """Copy default INI to ~/.claude/ if no config exists."""
        if not CONFIG_FILE.exists() and DEFAULT_INI.exists():
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(DEFAULT_INI, CONFIG_FILE)

    def _load(self) -> None:
        """Parse INI file — extract key=value pairs, section-aware.

        Stores each key twice: as flat ``key`` (backward compat) and as
        ``section.key`` for section-aware access.  Existing code that
        reads flat keys continues to work unchanged.
        """
        if not CONFIG_FILE.exists():
            return
        try:
            current_section = ""
            for line in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if stripped.startswith("[") and stripped.endswith("]"):
                    current_section = stripped[1:-1].strip()
                    continue
                if "=" in stripped:
                    key, _, val = stripped.partition("=")
                    key = key.strip()
                    val = val.strip()
                    self._values[key] = val
                    if current_section:
                        self._values[f"{current_section}.{key}"] = val
        except OSError:
            pass

    def _save_key(self, key: str, value: str) -> None:
        """Update a single key in the INI file, preserving everything else.

        If the key exists (active or commented out), update in place.
        If not found, append to end of file.
        """
        if not CONFIG_FILE.exists():
            self._ensure_file()
            self._load()

        try:
            lines = CONFIG_FILE.read_text(encoding="utf-8").splitlines()
        except OSError:
            return

        found = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Match active key
            if stripped and not stripped.startswith("#") and not stripped.startswith("["):
                if "=" in stripped:
                    k = stripped.partition("=")[0].strip()
                    if k == key:
                        lines[i] = f"{key} = {value}"
                        found = True
                        break

        if not found:
            lines.append(f"{key} = {value}")

        try:
            CONFIG_FILE.write_text(
                "\n".join(lines) + "\n", encoding="utf-8",
            )
        except OSError:
            pass

    # -- Typed getters (flat — backward compat) ----------------------------

    def _str(self, key: str) -> str:
        return self._values.get(key, _DEFAULTS.get(key, ""))

    def _float(self, key: str) -> float:
        try:
            return float(self._str(key))
        except ValueError:
            return float(_DEFAULTS.get(key, "0"))

    def _int(self, key: str) -> int:
        try:
            return int(self._str(key))
        except ValueError:
            return int(_DEFAULTS.get(key, "0"))

    # -- Typed getters (section-aware) -------------------------------------

    def _section_str(self, section: str, key: str) -> str:
        """Read a key within a specific INI section."""
        fq = f"{section}.{key}"
        return self._values.get(fq, _DEFAULTS.get(fq, ""))

    def _section_float(self, section: str, key: str) -> float:
        """Read a float key within a specific INI section."""
        try:
            return float(self._section_str(section, key))
        except ValueError:
            return float(_DEFAULTS.get(f"{section}.{key}", "0"))

    def _section_int(self, section: str, key: str) -> int:
        """Read an int key within a specific INI section."""
        try:
            return int(self._section_str(section, key))
        except ValueError:
            return int(_DEFAULTS.get(f"{section}.{key}", "0"))

    # -- General -----------------------------------------------------------

    @property
    def language(self) -> str:
        lang = self._str("language")
        if lang == "auto":
            return _detect_system_language()
        return lang

    @property
    def language_raw(self) -> str:
        return self._str("language")

    @property
    def model(self) -> str:
        return self._str("model")

    @property
    def refresh_ms(self) -> int:
        return self._int("refresh_ms")

    # -- Thresholds --------------------------------------------------------

    @property
    def quota_warn_pct(self) -> float:
        return self._float("quota_warn_pct")

    @property
    def quota_alarm_pct(self) -> float:
        return self._float("quota_alarm_pct")

    @property
    def cache_warn_ratio(self) -> float:
        return self._float("cache_warn_ratio")

    @property
    def cache_alarm_ratio(self) -> float:
        return self._float("cache_alarm_ratio")

    @property
    def burn_safe_pct_h(self) -> float:
        return self._float("burn_safe_pct_h")

    @property
    def burn_warn_pct_h(self) -> float:
        return self._float("burn_warn_pct_h")

    # -- Prices ------------------------------------------------------------

    @property
    def prices(self) -> dict[str, float]:
        m = self.model
        if m in MODEL_PRESETS:
            return dict(MODEL_PRESETS[m])
        return {
            "input": self._float("price_input"),
            "output": self._float("price_output"),
            "cache_read": self._float("price_cache_read"),
            "cache_create": self._float("price_cache_create"),
        }

    # -- Statusline --------------------------------------------------------

    @property
    def statusline_elements(self) -> list[str]:
        """Ordered list of statusline element keys from [statusline]."""
        raw = self._section_str("statusline", "elements")
        if not raw:
            return ["cwd", "model_info", "5h_bar", "7d_bar", "countdown_5h", "reserve"]
        return [e.strip() for e in raw.split(",") if e.strip()]

    @property
    def statusline_max_width(self) -> int:
        """Maximum visible character width for statusline output."""
        val = self._section_int("statusline", "max_width")
        return val if val > 0 else 80

    # -- Window ------------------------------------------------------------

    @property
    def window_geometry(self) -> str:
        return self._str("geometry")

    @window_geometry.setter
    def window_geometry(self, value: str) -> None:
        self._values["geometry"] = value

    # -- Setters -----------------------------------------------------------

    def set_language(self, value: str) -> None:
        self._values["language"] = value
        self._save_key("language", value)

    def set_model(self, value: str) -> None:
        self._values["model"] = value
        self._save_key("model", value)

    def save(self) -> None:
        """Save only changed values (window geometry etc.)."""
        for key in ("geometry",):
            self._save_key(key, self._values.get(key, ""))


# Module-level singleton
cfg = Config()
