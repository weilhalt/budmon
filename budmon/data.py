"""Data loading and computation for BudMon (no GUI dependencies)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from budmon.models import (
    C_GREEN,
    C_RED,
    C_YELLOW,
    CLAUDE_DIR_NAME,
    ELAPSED_MIN_HOURS,
    HISTORY_LOG_FILENAME,
    MARGIN_SAFE_SECONDS,
    SECONDS_PER_HOUR,
    SESSION_LOG_FILENAME,
    TOKENS_PER_UNIT,
    USAGE_LIMITS_FILENAME,
    BurnInfo,
    QuotaState,
    TokenUsage,
    format_duration,
    HEADER_5H_UTIL,
    HEADER_5H_RESET,
    HEADER_5H_STATUS,
    HEADER_7D_UTIL,
    HEADER_7D_RESET,
)
from budmon.transcript import read_transcript_state

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------

CLAUDE_DIR = Path.home() / CLAUDE_DIR_NAME
USAGE_LIMITS_FILE = CLAUDE_DIR / USAGE_LIMITS_FILENAME
SESSION_LOG_FILE = CLAUDE_DIR / SESSION_LOG_FILENAME
HISTORY_LOG_FILE = CLAUDE_DIR / HISTORY_LOG_FILENAME


# ---------------------------------------------------------------------------
# JSON / Config
# ---------------------------------------------------------------------------

def read_json(path: Path) -> dict[str, Any]:
    """Read JSON file, return empty dict on error."""
    try:
        if not path.exists():
            return {}
        text = path.read_text(encoding="utf-8")
        return json.loads(text) if text.strip() else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_prices() -> dict[str, float]:
    """Load token prices from config (model preset or custom)."""
    from budmon.config import cfg
    return cfg.prices


# ---------------------------------------------------------------------------
# Calculations
# ---------------------------------------------------------------------------

def calc_cost(usage: TokenUsage, prices: dict[str, float]) -> float:
    """Calculate costs in dollars from token counts."""
    cost = (
        usage.input_tokens * prices["input"]
        + usage.cache_read_input_tokens * prices["cache_read"]
        + usage.cache_creation_input_tokens * prices["cache_create"]
        + usage.output_tokens * prices["output"]
    ) / TOKENS_PER_UNIT
    return cost


def calc_burn(
    pct: float, reset_epoch_str: str | None, window_h: float,
) -> BurnInfo:
    """Calculate burn rate for a quota window."""
    if not reset_epoch_str:
        return BurnInfo()

    try:
        now = datetime.now(tz=timezone.utc)
        reset_time = datetime.fromtimestamp(
            int(reset_epoch_str), tz=timezone.utc,
        )
        window_start = reset_time - timedelta(hours=window_h)
        elapsed_h = (now - window_start).total_seconds() / SECONDS_PER_HOUR
    except (ValueError, OSError):
        return BurnInfo()

    if elapsed_h < ELAPSED_MIN_HOURS:
        return BurnInfo()

    rate = pct / elapsed_h
    remaining_pct = 100.0 - pct

    if rate <= 0.01:
        return BurnInfo()

    hours_left = remaining_pct / rate
    empty_time = now + timedelta(hours=hours_left)
    margin_seconds = (empty_time - reset_time).total_seconds()

    return BurnInfo(
        rate=rate,
        hours_left=hours_left,
        empty_epoch=empty_time.timestamp(),
        margin_seconds=margin_seconds,
        valid=True,
    )


def burn_rate_color(rate: float) -> str:
    """Color for burn rate value."""
    from budmon.config import cfg
    if rate < cfg.burn_safe_pct_h:
        return C_GREEN
    if rate < cfg.burn_warn_pct_h:
        return C_YELLOW
    return C_RED


def margin_color(margin_seconds: float) -> str:
    """Color for margin (reserve) value."""
    if margin_seconds > MARGIN_SAFE_SECONDS:
        return C_GREEN
    if margin_seconds > 0:
        return C_YELLOW
    return C_RED


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _weekday(dt: datetime) -> str:
    """Get localized weekday abbreviation."""
    from budmon.i18n import t_list
    days = t_list("weekdays")
    if days and 0 <= dt.weekday() < len(days):
        return days[dt.weekday()]
    return ""


def format_reset(epoch_str: str | None, include_date: bool = False) -> str:
    """Convert epoch string to readable format with countdown."""
    from budmon.i18n import t
    if not epoch_str:
        return "?"
    try:
        epoch = int(epoch_str)
        dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
        local = dt.astimezone()
        now = datetime.now(tz=timezone.utc).astimezone()
        delta_min = max(0, int((dt - now).total_seconds()) // 60)
        countdown = format_duration(delta_min)
        uhr = t("fmt_uhr")
        time_suffix = f" {uhr}" if uhr else ""
        if include_date:
            wt = _weekday(local)
            return f"{wt}. {local.strftime('%d.%m. %H:%M')}{time_suffix} ({countdown})"
        return f"{local.strftime('%H:%M')}{time_suffix} ({countdown})"
    except (ValueError, OSError):
        return "?"


def format_since(iso_str: str | None) -> str:
    """Format ISO timestamp as 'Wt. DD.MM. HH:MM [Uhr]'."""
    from budmon.i18n import t
    if not iso_str:
        return "?"
    try:
        started = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        local = started.astimezone()
        wt = _weekday(local)
        uhr = t("fmt_uhr")
        time_suffix = f" {uhr}" if uhr else ""
        return f"{wt}. {local.strftime('%d.%m. %H:%M')}{time_suffix}"
    except (ValueError, OSError):
        return "?"


def format_burn_empty(burn: BurnInfo, window_h: float) -> str:
    """Format the 'empty at' time string."""
    from budmon.i18n import t
    if not burn.valid:
        return "--"
    empty_time = datetime.fromtimestamp(burn.empty_epoch, tz=timezone.utc)
    empty_local = empty_time.astimezone()
    total_min_left = int(burn.hours_left * 60)
    delta_str = format_duration(total_min_left)
    uhr = t("fmt_uhr")
    time_suffix = f" {uhr}" if uhr else ""
    if window_h > 24:
        wt = _weekday(empty_local)
        time_prefix = f"{wt}. {empty_local.strftime('%d.%m. %H:%M')}{time_suffix}"
    else:
        time_prefix = f"{empty_local.strftime('%H:%M')}{time_suffix}"
    return f"{time_prefix} ({delta_str})"


def format_burn_rate(burn: BurnInfo, window_h: float) -> str:
    """Format the burn rate string."""
    from budmon.i18n import t
    if not burn.valid:
        return "--"
    if window_h > 24:
        return f"{burn.rate * 24:.1f}% {t('fmt_per_day')}"
    return f"{burn.rate:.1f}% {t('fmt_per_hour')}"


def format_margin(burn: BurnInfo) -> str:
    """Format the margin (reserve) string."""
    if not burn.valid:
        return "--"
    margin_total_min = int(abs(burn.margin_seconds)) // 60
    margin_str = format_duration(margin_total_min)
    sign = "+" if burn.margin_seconds > 0 else "-"
    return f"{sign}{margin_str}"


# ---------------------------------------------------------------------------
# State parsing
# ---------------------------------------------------------------------------

def parse_quota_state(limits: dict[str, Any]) -> QuotaState:
    """Parse raw JSON dict into a typed QuotaState."""
    headers = limits.get("headers_raw", {})

    pct_5h = float(headers.get(HEADER_5H_UTIL, 0)) * 100
    pct_7d = float(headers.get(HEADER_7D_UTIL, 0)) * 100

    turn_raw = limits.get("turn_usage")
    turn_usage = TokenUsage.from_dict(turn_raw) if turn_raw else None

    cum_raw = limits.get("cumulative")
    cumulative = TokenUsage.from_dict(cum_raw) if cum_raw else None

    cache_ratios = limits.get("cache_ratios", [])
    avg_ratio = 0.0

    # Fallback: read from budget_velocity.json (written by older interceptors)
    if not cache_ratios:
        velocity_file = CLAUDE_DIR / "budget_velocity.json"
        velocity = read_json(velocity_file)
        cache_ratios = velocity.get("cache_ratios", [])
        avg_ratio = velocity.get("avg_cache_ratio", 0.0)

    if cache_ratios and avg_ratio == 0.0:
        ratios = [r.get("ratio", 0) for r in cache_ratios if r.get("ratio")]
        avg_ratio = sum(ratios) / len(ratios) if ratios else 0.0

    return QuotaState(
        pct_5h=pct_5h,
        pct_7d=pct_7d,
        reset_5h=headers.get(HEADER_5H_RESET),
        reset_7d=headers.get(HEADER_7D_RESET),
        status_5h=headers.get(HEADER_5H_STATUS, ""),
        headers=headers,
        turn_usage=turn_usage,
        cumulative=cumulative,
        updated_at=limits.get("updated_at", ""),
        cache_ratios=cache_ratios,
        avg_cache_ratio=avg_ratio,
    )


def load_state() -> QuotaState:
    """Load quota state from headers + transcript (two independent sources).

    - Headers (usage-limits.json): quota percentages, reset timestamps
    - Transcript (Claude Code JSONL): per-turn and cumulative token data

    Falls back to old interceptor data in usage-limits.json if transcript
    is unavailable (backward compatibility with v1.0.x interceptor).
    """
    limits = read_json(USAGE_LIMITS_FILE)
    state = parse_quota_state(limits) if limits else QuotaState()

    transcript = read_transcript_state()
    if transcript:
        # Transcript is the authoritative source for token data
        if transcript.turn_usage:
            state.turn_usage = transcript.turn_usage
        if transcript.cumulative:
            state.cumulative = transcript.cumulative
            # Compute cache ratios from cumulative data
            cum = transcript.cumulative
            total_in = (
                cum.cache_read_input_tokens
                + cum.cache_creation_input_tokens
                + cum.input_tokens
            )
            if total_in > 0:
                state.avg_cache_ratio = cum.cache_read_input_tokens / total_in
    # If transcript is None, parse_quota_state already populated
    # turn_usage/cumulative from the old interceptor format (fallback).

    return state
