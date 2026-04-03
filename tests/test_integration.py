"""Integration tests — full data pipeline in a sandboxed environment.

Simulates the complete BudMon setup:
  1. Fake ~/.claude/ with usage-limits.json (interceptor headers)
  2. Fake transcript JSONL (Claude Code token data)
  3. load_state() combines both sources
  4. Statusline renders from combined state
  5. Graceful degradation when sources are missing

All paths are redirected to tmp_path — no real files touched.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

import budmon.data as data_mod
import budmon.transcript as transcript_mod
from budmon.data import load_state
from budmon.models import QuotaState


# ---------------------------------------------------------------------------
# Helpers: build fake Claude Code environment
# ---------------------------------------------------------------------------

def _write_usage_limits(claude_dir: Path, pct_5h: float = 0.47,
                        pct_7d: float = 0.23,
                        reset_5h_offset: int = 7200,
                        reset_7d_offset: int = 302400) -> Path:
    """Write a fake usage-limits.json with rate-limit headers."""
    f = claude_dir / "usage-limits.json"
    now = int(time.time())
    data = {
        "source": "interceptor",
        "interceptor_version": "1.1.0",
        "updated_at": "2026-04-03T12:00:00Z",
        "headers_raw": {
            "anthropic-ratelimit-unified-5h-utilization": str(pct_5h),
            "anthropic-ratelimit-unified-5h-reset": str(now + reset_5h_offset),
            "anthropic-ratelimit-unified-5h-status": "active",
            "anthropic-ratelimit-unified-7d-utilization": str(pct_7d),
            "anthropic-ratelimit-unified-7d-reset": str(now + reset_7d_offset),
        },
    }
    f.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return f


def _write_transcript(project_dir: Path, session_id: str = "test-session",
                      turns: int = 5) -> Path:
    """Write a fake transcript JSONL with assistant entries."""
    f = project_dir / f"{session_id}.jsonl"
    lines = []
    for i in range(turns):
        # User entry
        lines.append(json.dumps({
            "type": "human",
            "timestamp": f"2026-04-03T10:{i:02d}:00.000Z",
            "sessionId": session_id,
            "message": {"role": "user", "content": f"message {i}"},
        }))
        # Assistant entry with usage
        lines.append(json.dumps({
            "type": "assistant",
            "timestamp": f"2026-04-03T10:{i:02d}:30.000Z",
            "sessionId": session_id,
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": f"response {i}"}],
                "usage": {
                    "input_tokens": 100 + i * 10,
                    "output_tokens": 50 + i * 5,
                    "cache_creation_input_tokens": 200 + i * 20,
                    "cache_read_input_tokens": 5000 + i * 500,
                },
            },
        }))
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f


def _setup_sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                   with_headers: bool = True,
                   with_transcript: bool = True,
                   turns: int = 5) -> dict:
    """Build a complete sandboxed Claude Code environment.

    Returns dict with paths for inspection.
    """
    # Fake ~/.claude/
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()

    # Fake CWD project
    project_cwd = tmp_path / "myproject"
    project_cwd.mkdir()

    # Fake transcript project dir
    # Path hash: /tmp/pytest-xxx/myproject → -tmp-pytest-xxx-myproject
    dir_name = str(project_cwd).replace("/", "-").replace("\\", "-").replace(".", "-")
    projects_dir = claude_dir / "projects"
    project_transcript_dir = projects_dir / dir_name
    project_transcript_dir.mkdir(parents=True)

    # Redirect all paths
    monkeypatch.setattr(data_mod, "USAGE_LIMITS_FILE", claude_dir / "usage-limits.json")
    monkeypatch.setattr(data_mod, "CLAUDE_DIR", claude_dir)
    monkeypatch.setattr(transcript_mod, "_CLAUDE_PROJECTS", projects_dir)
    monkeypatch.chdir(project_cwd)

    # Reset transcript incremental state
    transcript_mod._last_path = None
    transcript_mod._last_pos = 0
    transcript_mod._cumulative_in = 0
    transcript_mod._cumulative_out = 0
    transcript_mod._cumulative_cache_create = 0
    transcript_mod._cumulative_cache_read = 0
    transcript_mod._turn_count = 0
    transcript_mod._started_at = ""

    result = {
        "claude_dir": claude_dir,
        "project_cwd": project_cwd,
        "transcript_dir": project_transcript_dir,
    }

    if with_headers:
        result["usage_limits"] = _write_usage_limits(claude_dir)

    if with_transcript:
        result["transcript"] = _write_transcript(
            project_transcript_dir, turns=turns,
        )

    return result


# ---------------------------------------------------------------------------
# Scenario 1: Both sources available (normal operation)
# ---------------------------------------------------------------------------

class TestBothSources:

    def test_quota_from_headers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup_sandbox(tmp_path, monkeypatch)
        state = load_state()
        assert state.pct_5h == pytest.approx(47.0)
        assert state.pct_7d == pytest.approx(23.0)
        assert state.reset_5h is not None
        assert state.reset_7d is not None

    def test_tokens_from_transcript(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup_sandbox(tmp_path, monkeypatch, turns=3)
        state = load_state()
        assert state.turn_usage is not None
        # Last turn: input=120, output=60
        assert state.turn_usage.input_tokens == 120
        assert state.turn_usage.output_tokens == 60
        assert state.cumulative is not None
        # Cumulative: sum of 3 turns
        assert state.cumulative.input_tokens == 100 + 110 + 120
        assert state.cumulative.output_tokens == 50 + 55 + 60

    def test_cache_ratio_computed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup_sandbox(tmp_path, monkeypatch, turns=3)
        state = load_state()
        assert state.avg_cache_ratio > 0.0
        assert state.avg_cache_ratio <= 1.0

    def test_turn_count(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup_sandbox(tmp_path, monkeypatch, turns=7)
        state = load_state()
        assert state.cumulative is not None
        assert state.cumulative.turn_count == 7

    def test_started_at_is_first_entry(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup_sandbox(tmp_path, monkeypatch, turns=3)
        state = load_state()
        assert state.cumulative is not None
        assert state.cumulative.started_at == "2026-04-03T10:00:30.000Z"


# ---------------------------------------------------------------------------
# Scenario 2: Headers only (no transcript — e.g. new project, no session yet)
# ---------------------------------------------------------------------------

class TestHeadersOnly:

    def test_quota_available(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup_sandbox(tmp_path, monkeypatch, with_transcript=False)
        state = load_state()
        assert state.pct_5h == pytest.approx(47.0)
        assert state.pct_7d == pytest.approx(23.0)

    def test_tokens_unavailable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup_sandbox(tmp_path, monkeypatch, with_transcript=False)
        state = load_state()
        # No transcript → no token data (unless old interceptor format)
        assert state.turn_usage is None
        assert state.cumulative is None


# ---------------------------------------------------------------------------
# Scenario 3: Transcript only (no interceptor — plain `claude` without wrapper)
# ---------------------------------------------------------------------------

class TestTranscriptOnly:

    def test_quota_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup_sandbox(tmp_path, monkeypatch, with_headers=False)
        state = load_state()
        assert state.pct_5h == 0.0
        assert state.pct_7d == 0.0
        assert not state.headers

    def test_tokens_available(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup_sandbox(tmp_path, monkeypatch, with_headers=False, turns=4)
        state = load_state()
        assert state.turn_usage is not None
        assert state.cumulative is not None
        assert state.cumulative.turn_count == 4


# ---------------------------------------------------------------------------
# Scenario 4: Nothing available (fresh install, no data)
# ---------------------------------------------------------------------------

class TestNoSources:

    def test_empty_state(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup_sandbox(
            tmp_path, monkeypatch,
            with_headers=False, with_transcript=False,
        )
        state = load_state()
        assert state.pct_5h == 0.0
        assert state.pct_7d == 0.0
        assert state.turn_usage is None
        assert state.cumulative is None
        assert not state.headers


# ---------------------------------------------------------------------------
# Scenario 5: Concurrent write (half-written transcript line)
# ---------------------------------------------------------------------------

class TestConcurrentWrite:

    def test_malformed_last_line_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        env = _setup_sandbox(tmp_path, monkeypatch, turns=3)
        # Append a half-written line
        with env["transcript"].open("a", encoding="utf-8") as f:
            f.write('{"type":"assistant","message":{"role":"assis')
        state = load_state()
        # Should still read the last complete assistant entry
        assert state.turn_usage is not None
        assert state.turn_usage.input_tokens == 120  # 3rd turn


# ---------------------------------------------------------------------------
# Scenario 6: Backward compatibility (old interceptor with turn_usage in JSON)
# ---------------------------------------------------------------------------

class TestBackwardCompat:

    def test_old_interceptor_format(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        env = _setup_sandbox(
            tmp_path, monkeypatch,
            with_headers=True, with_transcript=False,
        )
        # Add old-style turn_usage to usage-limits.json
        f = env["usage_limits"]
        data = json.loads(f.read_text(encoding="utf-8"))
        data["turn_usage"] = {
            "input_tokens": 999,
            "output_tokens": 888,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        }
        data["cumulative"] = {
            "input_tokens": 5000,
            "output_tokens": 3000,
            "total_tokens": 8000,
            "turn_count": 10,
            "started_at": "2026-04-03T09:00:00Z",
        }
        f.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

        state = load_state()
        # No transcript → falls back to old interceptor data
        assert state.turn_usage is not None
        assert state.turn_usage.input_tokens == 999
        assert state.cumulative is not None
        assert state.cumulative.turn_count == 10


# ---------------------------------------------------------------------------
# Scenario 7: Statusline renders from sandboxed data
# ---------------------------------------------------------------------------

class TestStatuslineIntegration:

    def test_renders_with_sandbox_data(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup_sandbox(tmp_path, monkeypatch, turns=5)
        from budmon.statusline import render, _visible_len
        # Mock stdin (no pipe in test)
        monkeypatch.setattr("budmon.statusline._read_stdin_json", lambda: {})
        result = render()
        assert "5h" in result
        assert "47%" in result

    def test_renders_empty_without_data(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup_sandbox(
            tmp_path, monkeypatch,
            with_headers=False, with_transcript=False,
        )
        from budmon.statusline import render
        monkeypatch.setattr("budmon.statusline._read_stdin_json", lambda: {})
        result = render()
        assert result == ""


# ---------------------------------------------------------------------------
# Scenario 8: Interceptor file verification
# ---------------------------------------------------------------------------

class TestInterceptorFile:

    def test_no_transform_stream(self) -> None:
        src = Path(__file__).parent.parent / "budmon" / "interceptor.mjs"
        content = src.read_text(encoding="utf-8")
        assert "TransformStream" not in content
        assert "new Response" not in content
        assert "pipeThrough" not in content

    def test_returns_original_response(self) -> None:
        src = Path(__file__).parent.parent / "budmon" / "interceptor.mjs"
        content = src.read_text(encoding="utf-8")
        # Must have `return response;` (not return wrapXxx(response))
        assert "return response;" in content

    def test_header_only_version(self) -> None:
        src = Path(__file__).parent.parent / "budmon" / "interceptor.mjs"
        content = src.read_text(encoding="utf-8")
        assert 'INTERCEPTOR_VERSION = "1.1.0"' in content
        assert "header-only" in content.lower()


# ---------------------------------------------------------------------------
# Scenario 9: Session switch (new transcript file appears)
# ---------------------------------------------------------------------------

class TestSessionSwitch:

    def test_detects_new_session(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        env = _setup_sandbox(tmp_path, monkeypatch, turns=3)
        state1 = load_state()
        assert state1.cumulative.turn_count == 3

        # Simulate new session — write a second transcript
        import os
        os.utime(env["transcript"], (1000, 1000))  # make old
        _write_transcript(
            env["transcript_dir"],
            session_id="new-session",
            turns=2,
        )
        # Reset incremental state (new file detected by path change)
        transcript_mod._last_path = None

        state2 = load_state()
        assert state2.cumulative.turn_count == 2  # new session, not 3+2
