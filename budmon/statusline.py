"""Compact ANSI status line for Claude Code — reads BudMon data."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from budmon.data import (
    calc_burn,
    calc_cost,
    load_prices,
    load_state,
)
from budmon.models import (
    BurnInfo,
    FIVE_HOURS,
    QuotaState,
    SEVEN_DAYS_HOURS,
)

# ---------------------------------------------------------------------------
# ANSI color codes (subdued palette — color only for warnings)
# ---------------------------------------------------------------------------

_RESET = "\033[0m"
_DIM = "\033[90m"
_YELLOW = "\033[33m"
_RED = "\033[31m"

_SEPARATOR = "  "

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def _visible_len(s: str) -> int:
    """Return the visible character width, ignoring ANSI escape codes."""
    return len(_ANSI_RE.sub("", s))


def _bar(pct: float, width: int = 8) -> str:
    """Render a bar of ``width`` characters using block characters."""
    pct = max(0.0, min(100.0, pct))
    filled = round(pct / 100.0 * width)
    return "\u2588" * filled + "\u2591" * (width - filled)


def _quota_color(pct: float) -> str:
    """Return ANSI color code based on quota thresholds from config."""
    from budmon.config import cfg
    if pct >= cfg.quota_alarm_pct:
        return _RED
    if pct >= cfg.quota_warn_pct:
        return _YELLOW
    return ""


def _compact_time(total_seconds: float) -> str:
    """Format seconds as compact string: '3d12h', '2h14m', '45m', '0m'."""
    if total_seconds < 0:
        return "0m"
    total_seconds = int(total_seconds)
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    if days > 0:
        return f"{days}d{hours}h"
    if hours > 0:
        return f"{hours}h{minutes}m"
    return f"{minutes}m"


def _compact_tokens(count: int) -> str:
    """Format token count: '1.2M', '125k', '42'."""
    if count >= 1_000_000:
        val = count / 1_000_000
        return f"{val:.1f}M" if val < 10 else f"{int(val)}M"
    if count >= 1_000:
        val = count / 1_000
        return f"{val:.0f}k" if val >= 10 else f"{val:.1f}k"
    return str(count)


def _short_path(path: str) -> str:
    """Shorten a path by replacing the home directory with '~'."""
    home = str(Path.home())
    if path.startswith(home):
        return "~" + path[len(home):]
    return path


def _read_stdin_json() -> dict[str, Any]:
    """Read JSON from stdin (piped by Claude Code). Returns {} if no pipe."""
    if sys.stdin.isatty():
        return {}
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _countdown_seconds(reset_epoch: str | None) -> float:
    """Seconds until a reset epoch, or -1 if unavailable."""
    if not reset_epoch:
        return -1.0
    try:
        reset = datetime.fromtimestamp(int(reset_epoch), tz=timezone.utc)
        now = datetime.now(tz=timezone.utc)
        return max(0.0, (reset - now).total_seconds())
    except (ValueError, OSError):
        return -1.0


# ---------------------------------------------------------------------------
# Status data container
# ---------------------------------------------------------------------------

@dataclass
class _StatusData:
    """Pre-computed data passed to each element renderer."""

    state: QuotaState
    burn_5h: BurnInfo
    burn_7d: BurnInfo
    cost: float
    cwd: str = ""
    model_info: str = ""


# ---------------------------------------------------------------------------
# Element renderers — each returns a formatted string (may include ANSI)
# ---------------------------------------------------------------------------

def _render_5h_bar(d: _StatusData) -> str:
    pct = d.state.pct_5h
    color = _quota_color(pct)
    reset = _RESET if color else ""
    return f"5h {color}{_bar(pct)} {pct:.0f}%{reset}"


def _render_7d_bar(d: _StatusData) -> str:
    pct = d.state.pct_7d
    color = _quota_color(pct)
    reset = _RESET if color else ""
    return f"7d {color}{_bar(pct)} {pct:.0f}%{reset}"


def _render_countdown_5h(d: _StatusData) -> str:
    secs = _countdown_seconds(d.state.reset_5h)
    if secs < 0:
        return ""
    return f"\u2193{_compact_time(secs)}"


def _render_countdown_7d(d: _StatusData) -> str:
    secs = _countdown_seconds(d.state.reset_7d)
    if secs < 0:
        return ""
    return f"\u2193{_compact_time(secs)}"


def _render_cost(d: _StatusData) -> str:
    if d.cost < 0.01:
        return f"{_DIM}$0.00{_RESET}"
    return f"{_DIM}${d.cost:.2f}{_RESET}"


def _render_burn_5h(d: _StatusData) -> str:
    if not d.burn_5h.valid:
        return ""
    color = ""
    from budmon.config import cfg
    if d.burn_5h.rate >= cfg.burn_warn_pct_h:
        color = _RED
    elif d.burn_5h.rate >= cfg.burn_safe_pct_h:
        color = _YELLOW
    reset = _RESET if color else ""
    return f"{color}\u26a1{d.burn_5h.rate:.0f}%/h{reset}"


def _render_burn_7d(d: _StatusData) -> str:
    if not d.burn_7d.valid:
        return ""
    rate_per_day = d.burn_7d.rate * 24
    return f"\u26a1{rate_per_day:.0f}%/d"


def _render_reserve(d: _StatusData) -> str:
    if not d.burn_5h.valid:
        return ""
    margin_min = int(abs(d.burn_5h.margin_seconds))
    sign = "+" if d.burn_5h.margin_seconds > 0 else "-"
    return f"{sign}{_compact_time(margin_min)}"


def _render_cache(d: _StatusData) -> str:
    ratio = d.state.avg_cache_ratio
    if ratio <= 0:
        return ""
    pct = int(ratio * 100)
    return f"\u229e{pct}%"


def _render_tokens_in(d: _StatusData) -> str:
    cum = d.state.cumulative
    if not cum:
        return ""
    return f"\u2192{_compact_tokens(cum.input_tokens)}"


def _render_tokens_out(d: _StatusData) -> str:
    cum = d.state.cumulative
    if not cum:
        return ""
    return f"\u2190{_compact_tokens(cum.output_tokens)}"


def _render_requests(d: _StatusData) -> str:
    cum = d.state.cumulative
    if not cum or cum.turn_count <= 0:
        return ""
    return f"#{cum.turn_count}"


def _render_model(_d: _StatusData) -> str:
    from budmon.config import cfg
    return f"{_DIM}{cfg.model}{_RESET}"


def _render_cwd(d: _StatusData) -> str:
    if not d.cwd:
        return ""
    return _short_path(d.cwd)


def _render_model_info(d: _StatusData) -> str:
    if not d.model_info:
        return ""
    return f"[{d.model_info}]"


# ---------------------------------------------------------------------------
# Element registry: key → (renderer, max visible width)
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, tuple[Callable[[_StatusData], str], int]] = {
    "cwd":          (_render_cwd, 30),
    "model_info":   (_render_model_info, 30),
    "5h_bar":       (_render_5h_bar, 15),
    "7d_bar":       (_render_7d_bar, 15),
    "countdown_5h": (_render_countdown_5h, 7),
    "countdown_7d": (_render_countdown_7d, 7),
    "cost":         (_render_cost, 6),
    "burn_5h":      (_render_burn_5h, 7),
    "burn_7d":      (_render_burn_7d, 7),
    "reserve":      (_render_reserve, 7),
    "cache":        (_render_cache, 5),
    "tokens_in":    (_render_tokens_in, 6),
    "tokens_out":   (_render_tokens_out, 5),
    "requests":     (_render_requests, 4),
    "model":        (_render_model, 5),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render() -> str:
    """Render a compact ANSI status line from BudMon data.

    Reads Claude Code's stdin JSON for cwd and model info, and
    BudMon's interceptor files for quota/cost data.
    Returns an empty string when no data is available (no crash).
    """
    stdin_data = _read_stdin_json()

    state = load_state()

    # Extract cwd and model from stdin (always available, even without
    # interceptor data)
    cwd = stdin_data.get("cwd", "")
    model_obj = stdin_data.get("model", {})
    model_info = model_obj.get("display_name", "") if isinstance(model_obj, dict) else ""

    if not state.headers and not state.cumulative and not cwd and not model_info:
        return ""

    burn_5h = calc_burn(state.pct_5h, state.reset_5h, FIVE_HOURS)
    burn_7d = calc_burn(state.pct_7d, state.reset_7d, SEVEN_DAYS_HOURS)

    cost = 0.0
    if state.cumulative:
        cost = calc_cost(state.cumulative, load_prices())

    data = _StatusData(
        state=state, burn_5h=burn_5h, burn_7d=burn_7d, cost=cost,
        cwd=cwd, model_info=model_info,
    )

    from budmon.config import cfg
    elements = cfg.statusline_elements
    max_width = cfg.statusline_max_width

    parts: list[str] = []
    current_width = 0

    for key in elements:
        entry = _REGISTRY.get(key)
        if not entry:
            continue
        renderer, _ = entry
        segment = renderer(data)
        if not segment:
            continue

        seg_width = _visible_len(segment)
        needed = seg_width if not parts else seg_width + len(_SEPARATOR)

        if current_width + needed > max_width:
            break

        parts.append(segment)
        current_width += needed

    result = _SEPARATOR.join(parts)
    if result and _RESET not in result[-len(_RESET):]:
        result += _RESET
    return result
