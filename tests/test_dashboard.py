"""Tests for pure functions in budmon (models + data modules)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from budmon.models import (
    C_GREEN,
    C_RED,
    C_YELLOW,
    DEFAULT_PRICES,
    TokenUsage,
    color_for_cache,
    color_for_quota,
    format_duration,
    scaled_font,
)
from budmon.data import (
    calc_cost,
    format_reset,
    format_since,
    read_json,
)


# ---------------------------------------------------------------------------
# color_for_quota
# ---------------------------------------------------------------------------

class TestColorForQuota:
    def test_green_below_warn(self) -> None:
        assert color_for_quota(0.0) == C_GREEN
        assert color_for_quota(50.0) == C_GREEN
        assert color_for_quota(74.9) == C_GREEN

    def test_yellow_at_warn(self) -> None:
        assert color_for_quota(75.0) == C_YELLOW
        assert color_for_quota(89.9) == C_YELLOW

    def test_red_at_alarm(self) -> None:
        assert color_for_quota(90.0) == C_RED
        assert color_for_quota(100.0) == C_RED


# ---------------------------------------------------------------------------
# color_for_cache
# ---------------------------------------------------------------------------

class TestColorForCache:
    def test_green_above_warn(self) -> None:
        assert color_for_cache(1.0) == C_GREEN
        assert color_for_cache(0.51) == C_GREEN

    def test_yellow_between_alarm_and_warn(self) -> None:
        assert color_for_cache(0.50) == C_YELLOW
        assert color_for_cache(0.30) == C_YELLOW
        assert color_for_cache(0.21) == C_YELLOW

    def test_red_at_or_below_alarm(self) -> None:
        assert color_for_cache(0.20) == C_RED
        assert color_for_cache(0.0) == C_RED


# ---------------------------------------------------------------------------
# calc_cost
# ---------------------------------------------------------------------------

class TestCalcCost:
    def test_zero_tokens(self) -> None:
        usage = TokenUsage()
        assert calc_cost(usage, DEFAULT_PRICES) == 0.0

    def test_known_values(self) -> None:
        usage = TokenUsage(
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            cache_creation_input_tokens=1_000_000,
            cache_read_input_tokens=1_000_000,
        )
        expected = 15.0 + 75.0 + 18.75 + 1.5  # = 110.25
        assert calc_cost(usage, DEFAULT_PRICES) == pytest.approx(expected)

    def test_partial_usage(self) -> None:
        usage = TokenUsage(output_tokens=500_000)
        expected = 500_000 * 75.0 / 1_000_000  # = 37.5
        assert calc_cost(usage, DEFAULT_PRICES) == pytest.approx(expected)

    def test_custom_prices(self) -> None:
        usage = TokenUsage(input_tokens=1_000_000)
        prices = {**DEFAULT_PRICES, "input": 30.0}
        assert calc_cost(usage, prices) == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# format_reset
# ---------------------------------------------------------------------------

class TestFormatReset:
    def test_none_returns_question(self) -> None:
        assert format_reset(None) == "?"

    def test_empty_returns_question(self) -> None:
        assert format_reset("") == "?"

    def test_invalid_returns_question(self) -> None:
        assert format_reset("not_a_number") == "?"

    def test_future_epoch(self) -> None:
        future = int(time.time()) + 3600
        result = format_reset(str(future))
        assert ":" in result  # time format HH:MM
        assert "(" in result  # countdown in parentheses

    def test_include_date(self) -> None:
        future = int(time.time()) + 86400 * 2
        result = format_reset(str(future), include_date=True)
        assert "." in result  # date format DD.MM.
        assert "(" in result  # countdown


# ---------------------------------------------------------------------------
# format_since
# ---------------------------------------------------------------------------

class TestFormatSince:
    def test_none_returns_question(self) -> None:
        assert format_since(None) == "?"

    def test_empty_returns_question(self) -> None:
        assert format_since("") == "?"

    def test_invalid_returns_question(self) -> None:
        assert format_since("not_a_date") == "?"

    def test_valid_iso(self) -> None:
        result = format_since("2026-04-02T14:30:00+00:00")
        assert ":" in result  # time format
        assert "." in result  # date format DD.MM.

    def test_z_suffix(self) -> None:
        result = format_since("2026-04-02T14:30:00Z")
        assert ":" in result


# ---------------------------------------------------------------------------
# read_json
# ---------------------------------------------------------------------------

class TestReadJson:
    def test_nonexistent_file(self, tmp_path: Path) -> None:
        assert read_json(tmp_path / "nope.json") == {}

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.json"
        f.write_text("", encoding="utf-8")
        assert read_json(f) == {}

    def test_valid_json(self, tmp_path: Path) -> None:
        f = tmp_path / "data.json"
        f.write_text(json.dumps({"key": "value"}), encoding="utf-8")
        assert read_json(f) == {"key": "value"}

    def test_invalid_json(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.json"
        f.write_text("{broken", encoding="utf-8")
        assert read_json(f) == {}

    def test_whitespace_only(self, tmp_path: Path) -> None:
        f = tmp_path / "ws.json"
        f.write_text("   \n  ", encoding="utf-8")
        assert read_json(f) == {}


# ---------------------------------------------------------------------------
# scaled_font
# ---------------------------------------------------------------------------

class TestScaledFont:
    def test_scale_1(self) -> None:
        result = scaled_font(1.0, "monospace", 10)
        assert result == ("monospace", 10)

    def test_scale_2(self) -> None:
        result = scaled_font(2.0, "monospace", 10)
        assert result == ("monospace", 20)

    def test_with_weight(self) -> None:
        result = scaled_font(1.0, "monospace", 10, "bold")
        assert result == ("monospace", 10, "bold")

    def test_minimum_size(self) -> None:
        result = scaled_font(0.5, "monospace", 10)
        assert result[1] >= 7


# ---------------------------------------------------------------------------
# format_duration
# ---------------------------------------------------------------------------

class TestFormatDuration:
    def test_zero(self) -> None:
        result = format_duration(0)
        assert "0" in result

    def test_minutes_only(self) -> None:
        result = format_duration(45)
        assert "45" in result
        assert "0" in result  # 0 hours

    def test_hours_and_minutes(self) -> None:
        result = format_duration(125)
        assert "2" in result  # hours
        assert "5" in result  # minutes

    def test_days(self) -> None:
        result = format_duration(1500)
        assert "1" in result  # 1 day


# ---------------------------------------------------------------------------
# TokenUsage.from_dict
# ---------------------------------------------------------------------------

class TestTokenUsageFromDict:
    def test_empty_dict(self) -> None:
        tu = TokenUsage.from_dict({})
        assert tu.input_tokens == 0
        assert tu.output_tokens == 0
        assert tu.started_at == ""

    def test_full_dict(self) -> None:
        tu = TokenUsage.from_dict({
            "input_tokens": 100,
            "output_tokens": 200,
            "cache_creation_input_tokens": 50,
            "cache_read_input_tokens": 300,
            "total_tokens": 650,
            "turn_count": 5,
            "started_at": "2026-04-02T10:00:00Z",
        })
        assert tu.input_tokens == 100
        assert tu.output_tokens == 200
        assert tu.total_tokens == 650
        assert tu.started_at == "2026-04-02T10:00:00Z"

    def test_none_values(self) -> None:
        tu = TokenUsage.from_dict({
            "input_tokens": None,
            "output_tokens": None,
        })
        assert tu.input_tokens == 0
        assert tu.output_tokens == 0
