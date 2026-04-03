"""Tests for statusline_on/off in setup.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from budmon.setup import (
    _strip_jsonc,
    statusline_off,
    statusline_on,
)


@pytest.fixture()
def tmp_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect SETTINGS_FILE to a temp directory."""
    settings = tmp_path / "settings.json"
    monkeypatch.setattr("budmon.setup.SETTINGS_FILE", settings)
    return settings


# ---------------------------------------------------------------------------
# JSONC stripping
# ---------------------------------------------------------------------------

class TestStripJsonc:

    def test_line_comments(self) -> None:
        raw = '{\n  // comment\n  "key": "val"\n}'
        clean = _strip_jsonc(raw)
        assert json.loads(clean) == {"key": "val"}

    def test_block_comments(self) -> None:
        raw = '{\n  /* block\n  comment */\n  "key": "val"\n}'
        clean = _strip_jsonc(raw)
        assert json.loads(clean) == {"key": "val"}

    def test_trailing_comma(self) -> None:
        raw = '{"a": 1, "b": 2,}'
        clean = _strip_jsonc(raw)
        assert json.loads(clean) == {"a": 1, "b": 2}

    def test_clean_json_unchanged(self) -> None:
        raw = '{"key": "value"}'
        assert _strip_jsonc(raw) == raw


# ---------------------------------------------------------------------------
# statusline_on
# ---------------------------------------------------------------------------

class TestStatuslineOn:

    def test_creates_settings_if_missing(
        self, tmp_settings: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "budmon.setup.shutil.which",
            lambda _name: "/usr/local/bin/budmon",
        )
        msgs = statusline_on()
        assert tmp_settings.exists()
        data = json.loads(tmp_settings.read_text(encoding="utf-8"))
        assert data["statusLine"]["command"] == "/usr/local/bin/budmon --statusline"
        assert any("activated" in m.lower() for m in msgs)

    def test_preserves_existing_keys(
        self, tmp_settings: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        tmp_settings.write_text(
            json.dumps({"language": "Deutsch", "hooks": {}}),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "budmon.setup.shutil.which",
            lambda _name: "/usr/bin/budmon",
        )
        msgs = statusline_on()
        data = json.loads(tmp_settings.read_text(encoding="utf-8"))
        assert data["language"] == "Deutsch"
        assert data["hooks"] == {}
        assert "statusLine" in data

    def test_warns_when_replacing_foreign(
        self, tmp_settings: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        tmp_settings.write_text(
            json.dumps({
                "statusLine": {
                    "type": "command",
                    "command": "ccusage statusline",
                },
            }),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "budmon.setup.shutil.which",
            lambda _name: "/usr/bin/budmon",
        )
        msgs = statusline_on()
        assert any("ccusage" in m for m in msgs)

    def test_no_warn_when_replacing_own(
        self, tmp_settings: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        tmp_settings.write_text(
            json.dumps({
                "statusLine": {
                    "type": "command",
                    "command": "/old/budmon --statusline",
                },
            }),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "budmon.setup.shutil.which",
            lambda _name: "/new/budmon",
        )
        msgs = statusline_on()
        assert not any("Replacing" in m for m in msgs)

    def test_fallback_to_sys_executable(
        self, tmp_settings: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("budmon.setup.shutil.which", lambda _name: None)
        monkeypatch.setattr("budmon.setup.sys.executable", "/usr/bin/python3")
        msgs = statusline_on()
        data = json.loads(tmp_settings.read_text(encoding="utf-8"))
        assert "-m budmon --statusline" in data["statusLine"]["command"]

    def test_error_when_no_budmon_found(
        self, tmp_settings: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("budmon.setup.shutil.which", lambda _name: None)
        monkeypatch.setattr("budmon.setup.sys.executable", "")
        msgs = statusline_on()
        assert any("error" in m.lower() for m in msgs)
        assert not tmp_settings.exists()


# ---------------------------------------------------------------------------
# statusline_off
# ---------------------------------------------------------------------------

class TestStatuslineOff:

    def test_removes_budmon_statusline(
        self, tmp_settings: Path,
    ) -> None:
        tmp_settings.write_text(
            json.dumps({
                "language": "Deutsch",
                "statusLine": {
                    "type": "command",
                    "command": "/usr/bin/budmon --statusline",
                },
            }),
            encoding="utf-8",
        )
        msgs = statusline_off()
        data = json.loads(tmp_settings.read_text(encoding="utf-8"))
        assert "statusLine" not in data
        assert data["language"] == "Deutsch"
        assert any("deactivated" in m.lower() for m in msgs)

    def test_refuses_foreign_statusline(
        self, tmp_settings: Path,
    ) -> None:
        tmp_settings.write_text(
            json.dumps({
                "statusLine": {
                    "type": "command",
                    "command": "ccusage statusline",
                },
            }),
            encoding="utf-8",
        )
        msgs = statusline_off()
        # Should NOT modify
        data = json.loads(tmp_settings.read_text(encoding="utf-8"))
        assert "statusLine" in data
        assert any("not budmon" in m.lower() for m in msgs)

    def test_no_settings_file(self, tmp_settings: Path) -> None:
        msgs = statusline_off()
        assert any("not configured" in m.lower() for m in msgs)

    def test_empty_statusline(self, tmp_settings: Path) -> None:
        tmp_settings.write_text(
            json.dumps({"statusLine": {}}), encoding="utf-8",
        )
        msgs = statusline_off()
        assert any("not configured" in m.lower() or "not budmon" in m.lower()
                    for m in msgs)
