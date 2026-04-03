"""Tests for statusline.py — element rendering, width limit, edge cases."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from budmon.models import BurnInfo, QuotaState, TokenUsage
from budmon.statusline import (
    _REGISTRY,
    _StatusData,
    _bar,
    _compact_time,
    _compact_tokens,
    _quota_color,
    _visible_len,
    render,
)


# ---------------------------------------------------------------------------
# Helper: bar rendering
# ---------------------------------------------------------------------------

class TestBar:

    def test_zero(self) -> None:
        assert _bar(0) == "\u2591" * 8

    def test_fifty(self) -> None:
        assert _bar(50) == "\u2588" * 4 + "\u2591" * 4

    def test_hundred(self) -> None:
        assert _bar(100) == "\u2588" * 8

    def test_clamps_negative(self) -> None:
        assert _bar(-10) == "\u2591" * 8

    def test_clamps_over_hundred(self) -> None:
        assert _bar(150) == "\u2588" * 8

    def test_rounding(self) -> None:
        # 12.5% of 8 = 1.0 → 1 filled
        result = _bar(12.5)
        assert result.count("\u2588") == 1

    def test_custom_width(self) -> None:
        result = _bar(50, width=4)
        assert result == "\u2588" * 2 + "\u2591" * 2


# ---------------------------------------------------------------------------
# Helper: ANSI visible length
# ---------------------------------------------------------------------------

class TestVisibleLen:

    def test_plain_text(self) -> None:
        assert _visible_len("hello") == 5

    def test_with_ansi(self) -> None:
        assert _visible_len("\033[31mhello\033[0m") == 5

    def test_multiple_codes(self) -> None:
        s = "\033[33m5h\033[0m \033[90m$1.00\033[0m"
        assert _visible_len(s) == 8  # "5h $1.00"

    def test_empty(self) -> None:
        assert _visible_len("") == 0


# ---------------------------------------------------------------------------
# Helper: compact time
# ---------------------------------------------------------------------------

class TestCompactTime:

    def test_zero(self) -> None:
        assert _compact_time(0) == "0m"

    def test_negative(self) -> None:
        assert _compact_time(-100) == "0m"

    def test_minutes(self) -> None:
        assert _compact_time(2700) == "45m"

    def test_hours_minutes(self) -> None:
        assert _compact_time(8040) == "2h14m"

    def test_days_hours(self) -> None:
        assert _compact_time(302400) == "3d12h"

    def test_exactly_one_hour(self) -> None:
        assert _compact_time(3600) == "1h0m"


# ---------------------------------------------------------------------------
# Helper: compact tokens
# ---------------------------------------------------------------------------

class TestCompactTokens:

    def test_small(self) -> None:
        assert _compact_tokens(42) == "42"

    def test_zero(self) -> None:
        assert _compact_tokens(0) == "0"

    def test_thousands(self) -> None:
        assert _compact_tokens(1500) == "1.5k"

    def test_large_thousands(self) -> None:
        assert _compact_tokens(125000) == "125k"

    def test_millions(self) -> None:
        assert _compact_tokens(1500000) == "1.5M"

    def test_large_millions(self) -> None:
        assert _compact_tokens(15000000) == "15M"


# ---------------------------------------------------------------------------
# Helper: quota color
# ---------------------------------------------------------------------------

class TestQuotaColor:

    def test_below_warn_no_color(self) -> None:
        assert _quota_color(0.0) == ""
        assert _quota_color(50.0) == ""

    def test_at_warn_yellow(self) -> None:
        assert _quota_color(75.0) == "\033[33m"

    def test_at_alarm_red(self) -> None:
        assert _quota_color(90.0) == "\033[31m"
        assert _quota_color(100.0) == "\033[31m"


# ---------------------------------------------------------------------------
# Element renderers
# ---------------------------------------------------------------------------

def _make_data(
    pct_5h: float = 47.0,
    pct_7d: float = 23.0,
    reset_5h: str | None = None,
    reset_7d: str | None = None,
    cost: float = 1.42,
    burn_5h: BurnInfo | None = None,
    burn_7d: BurnInfo | None = None,
    cumulative: TokenUsage | None = None,
    avg_cache_ratio: float = 0.0,
) -> _StatusData:
    if reset_5h is None:
        reset_5h = str(int(time.time()) + 7200)  # 2h from now
    if reset_7d is None:
        reset_7d = str(int(time.time()) + 302400)  # 3.5d from now
    state = QuotaState(
        pct_5h=pct_5h,
        pct_7d=pct_7d,
        reset_5h=reset_5h,
        reset_7d=reset_7d,
        cumulative=cumulative or TokenUsage(
            input_tokens=125000,
            output_tokens=42000,
            turn_count=28,
        ),
        avg_cache_ratio=avg_cache_ratio,
    )
    return _StatusData(
        state=state,
        burn_5h=burn_5h or BurnInfo(
            rate=12.0, hours_left=4.0,
            empty_epoch=time.time() + 14400,
            margin_seconds=3600, valid=True,
        ),
        burn_7d=burn_7d or BurnInfo(
            rate=0.5, hours_left=48.0,
            empty_epoch=time.time() + 172800,
            margin_seconds=7200, valid=True,
        ),
        cost=cost,
    )


class TestElementRenderers:

    def test_5h_bar_format(self) -> None:
        d = _make_data(pct_5h=47.0)
        renderer, _ = _REGISTRY["5h_bar"]
        result = renderer(d)
        visible = _visible_len(result)
        assert "5h" in result
        assert "47%" in result
        assert visible <= 15

    def test_7d_bar_format(self) -> None:
        d = _make_data(pct_7d=23.0)
        renderer, _ = _REGISTRY["7d_bar"]
        result = renderer(d)
        assert "7d" in result
        assert "23%" in result

    def test_countdown_5h_format(self) -> None:
        d = _make_data()
        renderer, _ = _REGISTRY["countdown_5h"]
        result = renderer(d)
        assert "\u2193" in result  # ↓

    def test_countdown_no_reset(self) -> None:
        d = _make_data(reset_5h="")
        renderer, _ = _REGISTRY["countdown_5h"]
        assert renderer(d) == ""

    def test_cost_format(self) -> None:
        d = _make_data(cost=1.42)
        renderer, _ = _REGISTRY["cost"]
        result = renderer(d)
        assert "$1.42" in result

    def test_cost_zero(self) -> None:
        d = _make_data(cost=0.0)
        renderer, _ = _REGISTRY["cost"]
        result = renderer(d)
        assert "$0.00" in result

    def test_burn_5h_format(self) -> None:
        d = _make_data()
        renderer, _ = _REGISTRY["burn_5h"]
        result = renderer(d)
        assert "12%/h" in result

    def test_burn_5h_invalid(self) -> None:
        d = _make_data(burn_5h=BurnInfo())
        renderer, _ = _REGISTRY["burn_5h"]
        assert renderer(d) == ""

    def test_cache_format(self) -> None:
        d = _make_data(avg_cache_ratio=0.72)
        renderer, _ = _REGISTRY["cache"]
        result = renderer(d)
        assert "72%" in result

    def test_cache_zero(self) -> None:
        d = _make_data(avg_cache_ratio=0.0)
        renderer, _ = _REGISTRY["cache"]
        assert renderer(d) == ""

    def test_tokens_in(self) -> None:
        d = _make_data()
        renderer, _ = _REGISTRY["tokens_in"]
        result = renderer(d)
        assert "125k" in result

    def test_tokens_out(self) -> None:
        d = _make_data()
        renderer, _ = _REGISTRY["tokens_out"]
        result = renderer(d)
        assert "42k" in result

    def test_requests(self) -> None:
        d = _make_data()
        renderer, _ = _REGISTRY["requests"]
        result = renderer(d)
        assert "#28" in result

    def test_model(self) -> None:
        renderer, _ = _REGISTRY["model"]
        d = _make_data()
        result = renderer(d)
        assert "opus" in result or "sonnet" in result

    def test_cwd(self) -> None:
        d = _make_data()
        d.cwd = str(Path.home() / ".DEV" / ".BUDMON")
        renderer, _ = _REGISTRY["cwd"]
        result = renderer(d)
        assert ".BUDMON" in result

    def test_cwd_empty(self) -> None:
        d = _make_data()
        d.cwd = ""
        renderer, _ = _REGISTRY["cwd"]
        assert renderer(d) == ""

    def test_model_info(self) -> None:
        d = _make_data()
        d.model_info = "Opus 4.6 (1M context)"
        renderer, _ = _REGISTRY["model_info"]
        result = renderer(d)
        assert "[Opus 4.6 (1M context)]" in result

    def test_model_info_empty(self) -> None:
        d = _make_data()
        d.model_info = ""
        renderer, _ = _REGISTRY["model_info"]
        assert renderer(d) == ""

    def test_all_renderers_registered(self) -> None:
        assert len(_REGISTRY) == 15


# ---------------------------------------------------------------------------
# render() integration
# ---------------------------------------------------------------------------

def _mock_load_state(
    pct_5h: float = 0.0,
    pct_7d: float = 0.0,
    reset_5h: str | None = None,
    reset_7d: str | None = None,
) -> QuotaState:
    """Build a QuotaState for mocking load_state()."""
    from budmon.models import HEADER_5H_UTIL, HEADER_5H_RESET, HEADER_7D_UTIL, HEADER_7D_RESET
    headers = {}
    if pct_5h > 0:
        headers[HEADER_5H_UTIL] = str(pct_5h / 100)
    if reset_5h:
        headers[HEADER_5H_RESET] = reset_5h
    if pct_7d > 0:
        headers[HEADER_7D_UTIL] = str(pct_7d / 100)
    if reset_7d:
        headers[HEADER_7D_RESET] = reset_7d
    return QuotaState(
        pct_5h=pct_5h, pct_7d=pct_7d,
        reset_5h=reset_5h, reset_7d=reset_7d,
        headers=headers,
    )


class TestRender:

    def test_no_data_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "budmon.statusline.load_state", lambda: QuotaState(),
        )
        assert render() == ""

    def test_empty_state_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "budmon.statusline.load_state", lambda: QuotaState(),
        )
        assert render() == ""

    def test_with_data(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state = _mock_load_state(
            pct_5h=47.0, pct_7d=23.0,
            reset_5h=str(int(time.time()) + 7200),
            reset_7d=str(int(time.time()) + 302400),
        )
        monkeypatch.setattr(
            "budmon.statusline.load_state", lambda: state,
        )
        result = render()
        assert "5h" in result
        assert "7d" in result
        assert "47%" in result

    def test_width_limit_drops_elements(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state = _mock_load_state(
            pct_5h=50.0, pct_7d=30.0,
            reset_5h=str(int(time.time()) + 3600),
            reset_7d=str(int(time.time()) + 86400),
        )
        monkeypatch.setattr(
            "budmon.statusline.load_state", lambda: state,
        )

        # Config with narrow width
        ini = tmp_path / "budmon.ini"
        ini.write_text(
            "[statusline]\n"
            "elements = 5h_bar, 7d_bar, countdown_5h, cost\n"
            "max_width = 20\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("budmon.config.CONFIG_FILE", ini)
        monkeypatch.setattr(
            "budmon.config.DEFAULT_INI", tmp_path / "nope.ini",
        )
        from budmon.config import Config
        monkeypatch.setattr("budmon.config.cfg", Config())

        result = render()
        visible = _visible_len(result)
        assert visible <= 20

    def test_unknown_element_key_ignored(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state = _mock_load_state(
            pct_5h=50.0,
            reset_5h=str(int(time.time()) + 3600),
            pct_7d=30.0,
        )
        monkeypatch.setattr(
            "budmon.statusline.load_state", lambda: state,
        )

        ini = tmp_path / "budmon.ini"
        ini.write_text(
            "[statusline]\nelements = bogus_widget, 5h_bar\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("budmon.config.CONFIG_FILE", ini)
        monkeypatch.setattr(
            "budmon.config.DEFAULT_INI", tmp_path / "nope.ini",
        )
        from budmon.config import Config
        monkeypatch.setattr("budmon.config.cfg", Config())

        result = render()
        assert "5h" in result


class TestNoTkinterImport:

    def test_statusline_does_not_import_tkinter(self) -> None:
        assert "tkinter" not in sys.modules

    def test_statusline_does_not_import_i18n(self) -> None:
        # i18n may be loaded by other test modules, but statusline
        # itself should not trigger it. We verify by checking the
        # import chain of the module.
        import budmon.statusline as sl
        source = Path(sl.__file__).read_text(encoding="utf-8")
        assert "import tkinter" not in source
        assert "from budmon.i18n" not in source
