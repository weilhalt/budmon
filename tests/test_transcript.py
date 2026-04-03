"""Tests for transcript.py — reading token data from Claude Code JSONL."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

import budmon.transcript as transcript
from budmon.transcript import (
    _active_transcript,
    _project_dir,
    _read_last_assistant_usage,
    read_transcript_state,
)


def _assistant_entry(
    input_tokens: int = 100,
    output_tokens: int = 50,
    cache_create: int = 200,
    cache_read: int = 5000,
    ts: str = "",
) -> str:
    """Build a JSONL line for an assistant message with usage."""
    if not ts:
        ts = f"2026-04-03T12:{int(time.time()) % 60:02d}:00.000Z"
    entry = {
        "type": "assistant",
        "timestamp": ts,
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "response"}],
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_input_tokens": cache_create,
                "cache_read_input_tokens": cache_read,
            },
        },
    }
    return json.dumps(entry)


def _user_entry() -> str:
    """Build a JSONL line for a user message (no usage)."""
    return json.dumps({
        "type": "human",
        "timestamp": "2026-04-03T12:00:01.000Z",
        "message": {"role": "user", "content": "hello"},
    })


# ---------------------------------------------------------------------------
# _project_dir
# ---------------------------------------------------------------------------

class TestProjectDir:

    def test_returns_path_when_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Simulate ~/.claude/projects/<hash>/
        projects = tmp_path / "projects"
        cwd = tmp_path / "myproject"
        cwd.mkdir()
        dir_name = str(cwd).replace("/", "-").replace("\\", "-").replace(".", "-")
        (projects / dir_name).mkdir(parents=True)
        monkeypatch.setattr(transcript, "_CLAUDE_PROJECTS", projects)
        monkeypatch.chdir(cwd)
        result = _project_dir()
        assert result is not None
        assert result.is_dir()

    def test_returns_none_when_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        projects = tmp_path / "projects"
        projects.mkdir()
        monkeypatch.setattr(transcript, "_CLAUDE_PROJECTS", projects)
        result = _project_dir()
        assert result is None


# ---------------------------------------------------------------------------
# _active_transcript
# ---------------------------------------------------------------------------

class TestActiveTranscript:

    def test_finds_newest(self, tmp_path: Path) -> None:
        old = tmp_path / "old.jsonl"
        new = tmp_path / "new.jsonl"
        old.write_text("{}\n", encoding="utf-8")
        import os
        os.utime(old, (1000, 1000))
        new.write_text("{}\n", encoding="utf-8")
        assert _active_transcript(tmp_path) == new

    def test_empty_dir(self, tmp_path: Path) -> None:
        assert _active_transcript(tmp_path) is None


# ---------------------------------------------------------------------------
# _read_last_assistant_usage
# ---------------------------------------------------------------------------

class TestReadLastAssistantUsage:

    def test_reads_last_entry(self, tmp_path: Path) -> None:
        f = tmp_path / "session.jsonl"
        lines = [
            _assistant_entry(input_tokens=100, output_tokens=50),
            _user_entry(),
            _assistant_entry(input_tokens=200, output_tokens=75),
        ]
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
        usage = _read_last_assistant_usage(f)
        assert usage is not None
        assert usage["input_tokens"] == 200
        assert usage["output_tokens"] == 75

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "session.jsonl"
        f.write_text("", encoding="utf-8")
        assert _read_last_assistant_usage(f) is None

    def test_only_user_entries(self, tmp_path: Path) -> None:
        f = tmp_path / "session.jsonl"
        f.write_text(_user_entry() + "\n", encoding="utf-8")
        assert _read_last_assistant_usage(f) is None

    def test_malformed_line_skipped(self, tmp_path: Path) -> None:
        f = tmp_path / "session.jsonl"
        lines = [
            _assistant_entry(input_tokens=100, output_tokens=50),
            '{"truncated json...',  # half-written line
        ]
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
        usage = _read_last_assistant_usage(f)
        assert usage is not None
        assert usage["input_tokens"] == 100

    def test_missing_file(self, tmp_path: Path) -> None:
        f = tmp_path / "nonexistent.jsonl"
        assert _read_last_assistant_usage(f) is None

    def test_thinking_turn_output_zero(self, tmp_path: Path) -> None:
        f = tmp_path / "session.jsonl"
        f.write_text(
            _assistant_entry(input_tokens=100, output_tokens=0) + "\n",
            encoding="utf-8",
        )
        usage = _read_last_assistant_usage(f)
        assert usage is not None
        assert usage["output_tokens"] == 0


# ---------------------------------------------------------------------------
# read_transcript_state (integration)
# ---------------------------------------------------------------------------

class TestReadTranscriptState:

    def _setup_transcript(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        lines: list[str],
    ) -> None:
        projects = tmp_path / "projects"
        cwd = tmp_path / "proj"
        cwd.mkdir()
        dir_name = str(cwd).replace("/", "-").replace("\\", "-").replace(".", "-")
        proj_dir = projects / dir_name
        proj_dir.mkdir(parents=True)
        transcript_file = proj_dir / "session-abc.jsonl"
        transcript_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        monkeypatch.setattr(transcript, "_CLAUDE_PROJECTS", projects)
        monkeypatch.chdir(cwd)
        # Reset incremental state
        transcript._last_path = None
        transcript._last_pos = 0

    def test_full_state(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        lines = [
            _assistant_entry(
                input_tokens=100, output_tokens=50,
                cache_create=200, cache_read=5000,
                ts="2026-04-03T10:00:00.000Z",
            ),
            _user_entry(),
            _assistant_entry(
                input_tokens=150, output_tokens=75,
                cache_create=300, cache_read=8000,
            ),
        ]
        self._setup_transcript(tmp_path, monkeypatch, lines)
        state = read_transcript_state()
        assert state is not None
        assert state.turn_count == 2
        assert state.turn_usage is not None
        assert state.turn_usage.input_tokens == 150
        assert state.cumulative.input_tokens == 250
        assert state.cumulative.output_tokens == 125
        assert state.cumulative.cache_creation_input_tokens == 500
        assert state.cumulative.cache_read_input_tokens == 13000
        assert state.started_at == "2026-04-03T10:00:00.000Z"

    def test_no_project_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            transcript, "_CLAUDE_PROJECTS", tmp_path / "nope",
        )
        assert read_transcript_state() is None

    def test_empty_transcript(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        self._setup_transcript(tmp_path, monkeypatch, [])
        state = read_transcript_state()
        assert state is not None
        assert state.turn_count == 0
        assert state.turn_usage is None

    def test_performance_many_entries(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        lines = [_assistant_entry() for _ in range(1000)]
        self._setup_transcript(tmp_path, monkeypatch, lines)
        state = read_transcript_state()
        assert state is not None
        assert state.turn_count == 1000
