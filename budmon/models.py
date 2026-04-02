"""Data models and constants for BudMon."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# DPI / Scaling
# ---------------------------------------------------------------------------

DPI_BASE = 96.0
GDI_LOGPIXELSX = 88
XRDB_TIMEOUT_S = 3
MIN_SCALE = 1.0

# ---------------------------------------------------------------------------
# File paths (relative to ~/.claude/)
# ---------------------------------------------------------------------------

CLAUDE_DIR_NAME = ".claude"
USAGE_LIMITS_FILENAME = "usage-limits.json"
SESSION_LOG_FILENAME = "usage-session.jsonl"
HISTORY_LOG_FILENAME = "usage-history.jsonl"

# ---------------------------------------------------------------------------
# Polling / Layout
# ---------------------------------------------------------------------------

REFRESH_MS = 1000
PAD_X = 8
PAD_Y = 2
LABEL_WIDTH = 10

# Font sizes
FONT_SIZE_NORMAL = 10
FONT_SIZE_SMALL = 9
FONT_SIZE_HEADER = 14
FONT_SIZE_STATUS = 12
FONT_SIZE_CACHE = 12
FONT_SIZE_BAR_VALUE = 11
FONT_SIZE_COUNTDOWN = 18
FONT_SIZE_COUNTDOWN_LABEL = 7
FONT_SIZE_FOOTER = 8
FONT_SIZE_MIN = 7

# ---------------------------------------------------------------------------
# Token prices (per 1M tokens, Opus, April 2026)
# ---------------------------------------------------------------------------

DEFAULT_PRICES: dict[str, float] = {
    "input": 15.0,
    "cache_read": 1.5,
    "cache_create": 18.75,
    "output": 75.0,
}

TOKENS_PER_UNIT = 1_000_000

# ---------------------------------------------------------------------------
# Colors (terminal dark theme)
# ---------------------------------------------------------------------------

C_BG = "#0a0a0a"
C_FG = "#d4d4d4"
C_DIM = "#666666"
C_GREEN = "#22c55e"
C_YELLOW = "#eab308"
C_RED = "#ef4444"
C_CYAN = "#06b6d4"
C_BAR_BG = "#1e1e1e"
C_ACCENT = "#a78bfa"

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

QUOTA_WARN_PCT = 75.0
QUOTA_ALARM_PCT = 90.0
CACHE_WARN_RATIO = 0.50
CACHE_ALARM_RATIO = 0.20
BURN_SAFE_PCT_H = 15.0
BURN_WARN_PCT_H = 25.0

# ---------------------------------------------------------------------------
# Time constants
# ---------------------------------------------------------------------------

FIVE_HOURS = 5.0
SEVEN_DAYS_HOURS = 168.0
SECONDS_PER_HOUR = 3600
MINUTES_PER_DAY = 24 * 60
ELAPSED_MIN_HOURS = 0.05
MARGIN_SAFE_SECONDS = 3600

# ---------------------------------------------------------------------------
# Countdown ring
# ---------------------------------------------------------------------------

CD_BASE_SIZE = 100
CD_RING_DIAMETER = 70
CD_RING_WIDTH = 6
CD_COUNTDOWN_WARN_SEC = 1800

# ---------------------------------------------------------------------------
# Sparkline
# ---------------------------------------------------------------------------

SPARKLINE_MAX_POINTS = 60
SPARKLINE_MARGIN = 4

# Canvas fallback sizes
CANVAS_BAR_FALLBACK_W = 200
CANVAS_BAR_FALLBACK_H = 16
CANVAS_BAR_HEIGHT = 16
CANVAS_SPARKLINE_HEIGHT = 60
CANVAS_SPARKLINE_FALLBACK_W = 430

# ---------------------------------------------------------------------------
# Localization (WEEKDAYS now served by i18n.t_list("weekdays"))
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Header keys
# ---------------------------------------------------------------------------

HEADER_5H_UTIL = "anthropic-ratelimit-unified-5h-utilization"
HEADER_5H_RESET = "anthropic-ratelimit-unified-5h-reset"
HEADER_5H_STATUS = "anthropic-ratelimit-unified-5h-status"
HEADER_7D_UTIL = "anthropic-ratelimit-unified-7d-utilization"
HEADER_7D_RESET = "anthropic-ratelimit-unified-7d-reset"

# ---------------------------------------------------------------------------
# UI detail row definitions
# ---------------------------------------------------------------------------

DETAIL_ROWS: list[tuple[str, str]] = [
    ("label_anfragen", "turns"),
    ("label_seit", "since"),
    ("input", "input"),
    ("output", "output"),
    ("cache_c", "cache_create"),
    ("cache_r", "cache_read"),
]

BURN_ROWS: list[tuple[str, str]] = [
    ("label_ablauf", "empty"),
    ("label_reserve", "diff"),
    ("label_verbrauch", "rate"),
]

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TokenUsage:
    """Token counts for a single request or cumulative."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    total_tokens: int = 0
    turn_count: int = 0
    started_at: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TokenUsage:
        def _int(key: str) -> int:
            val = data.get(key, 0)
            return int(val) if val else 0

        return cls(
            input_tokens=_int("input_tokens"),
            output_tokens=_int("output_tokens"),
            cache_creation_input_tokens=_int("cache_creation_input_tokens"),
            cache_read_input_tokens=_int("cache_read_input_tokens"),
            total_tokens=_int("total_tokens"),
            turn_count=_int("turn_count"),
            started_at=str(data.get("started_at") or ""),
        )


@dataclass
class BurnInfo:
    """Burn rate calculation result."""

    rate: float = 0.0
    hours_left: float = 0.0
    empty_epoch: float = 0.0
    margin_seconds: float = 0.0
    valid: bool = False


@dataclass
class QuotaState:
    """Parsed quota state from usage-limits.json."""

    pct_5h: float = 0.0
    pct_7d: float = 0.0
    reset_5h: str | None = None
    reset_7d: str | None = None
    status_5h: str = ""
    headers: dict[str, Any] = field(default_factory=dict)
    turn_usage: TokenUsage | None = None
    cumulative: TokenUsage | None = None
    updated_at: str = ""
    cache_ratios: list[dict[str, Any]] = field(default_factory=list)
    avg_cache_ratio: float = 0.0


def color_for_quota(pct: float) -> str:
    """Color code based on quota percent (higher = worse)."""
    from budmon.config import cfg
    if pct >= cfg.quota_alarm_pct:
        return C_RED
    if pct >= cfg.quota_warn_pct:
        return C_YELLOW
    return C_GREEN


def color_for_cache(ratio: float) -> str:
    """Color code based on cache ratio (lower = worse)."""
    from budmon.config import cfg
    if ratio <= cfg.cache_alarm_ratio:
        return C_RED
    if ratio <= cfg.cache_warn_ratio:
        return C_YELLOW
    return C_GREEN


def format_duration(total_minutes: int) -> str:
    """Format minutes as 'X d Y h Z min' (localized)."""
    from budmon.i18n import t
    d = t("fmt_tag")
    h = t("fmt_std")
    m = t("fmt_min")
    tage = total_minutes // MINUTES_PER_DAY
    std = (total_minutes % MINUTES_PER_DAY) // 60
    mi = total_minutes % 60
    if tage > 0:
        return f"{tage} {d} {std} {h} {mi} {m}"
    return f"{std} {h} {mi} {m}"


def scaled_font(
    scale: float, family: str = "monospace",
    size: int = FONT_SIZE_NORMAL, weight: str = "",
) -> tuple[str, int] | tuple[str, int, str]:
    """Return a font tuple with size scaled for HiDPI."""
    scaled_size = max(FONT_SIZE_MIN, int(size * scale))
    if weight:
        return (family, scaled_size, weight)
    return (family, scaled_size)
