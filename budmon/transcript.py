"""Read token usage from Claude Code's transcript JSONL files.

Claude Code writes a JSONL file per session at:
  ~/.claude/projects/<project-hash>/<session-id>.jsonl

Each assistant entry contains ``message.usage`` with input_tokens,
output_tokens, cache_creation_input_tokens, cache_read_input_tokens.

This module reads that data as a non-invasive alternative to
intercepting the SSE response stream.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from budmon.models import TokenUsage, TranscriptState

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

_CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"

# Incremental reading state (module-level, reset per session file)
_last_path: Path | None = None
_last_pos: int = 0
_cumulative_in: int = 0
_cumulative_out: int = 0
_cumulative_cache_create: int = 0
_cumulative_cache_read: int = 0
_turn_count: int = 0
_started_at: str = ""


def _project_dir() -> Path | None:
    """Construct the Claude Code project directory for the current CWD.

    Claude Code uses the absolute CWD path with ``/`` replaced by ``-``
    as the directory name under ``~/.claude/projects/``.
    """
    cwd = Path.cwd().resolve()
    # Claude Code replaces / . and \ with - in the project dir name.
    # Linux: /home/user/.DEV/.BUDMON → -home-user--DEV--BUDMON
    # Windows: C:\Users\foo → needs verification (R6)
    dir_name = str(cwd).replace("/", "-").replace("\\", "-").replace(".", "-")
    project = _CLAUDE_PROJECTS / dir_name
    if project.is_dir():
        return project
    return None


def _active_transcript(project_dir: Path) -> Path | None:
    """Find the most recently modified ``.jsonl`` file (= active session)."""
    jsonls = list(project_dir.glob("*.jsonl"))
    if not jsonls:
        return None
    return max(jsonls, key=lambda f: f.stat().st_mtime)


def _read_last_assistant_usage(path: Path) -> dict[str, Any] | None:
    """Read the last assistant entry's usage from a transcript JSONL.

    Uses tail-read (last 50 KB) to avoid parsing the entire file.
    Silently skips malformed lines (concurrent write protection).
    """
    try:
        size = path.stat().st_size
        read_size = min(size, 50_000)
        with path.open(encoding="utf-8", errors="replace") as f:
            f.seek(max(0, size - read_size))
            tail = f.read()
    except OSError:
        return None

    for line in reversed(tail.strip().splitlines()):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = entry.get("message")
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            usage = msg.get("usage")
            if isinstance(usage, dict):
                return usage
    return None


def _read_cumulative_incremental(path: Path) -> None:
    """Read new assistant entries since last position (incremental).

    Updates module-level cumulative counters. Resets when the file
    changes (new session).
    """
    global _last_path, _last_pos
    global _cumulative_in, _cumulative_out
    global _cumulative_cache_create, _cumulative_cache_read
    global _turn_count, _started_at

    # Reset if file changed (new session)
    if _last_path != path:
        _last_path = path
        _last_pos = 0
        _cumulative_in = 0
        _cumulative_out = 0
        _cumulative_cache_create = 0
        _cumulative_cache_read = 0
        _turn_count = 0
        _started_at = ""

    try:
        size = path.stat().st_size
    except OSError:
        return

    if size <= _last_pos:
        return  # No new data

    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            f.seek(_last_pos)
            new_data = f.read()
            _last_pos = f.tell()
    except OSError:
        return

    for line in new_data.strip().splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = entry.get("message")
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        usage = msg.get("usage")
        if not isinstance(usage, dict):
            continue

        _cumulative_in += usage.get("input_tokens", 0)
        _cumulative_out += usage.get("output_tokens", 0)
        _cumulative_cache_create += usage.get(
            "cache_creation_input_tokens", 0,
        )
        _cumulative_cache_read += usage.get(
            "cache_read_input_tokens", 0,
        )
        _turn_count += 1

        if not _started_at:
            ts = entry.get("timestamp", "")
            if ts:
                _started_at = ts


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def read_transcript_state() -> TranscriptState | None:
    """Read token data from the active Claude Code transcript.

    Returns None if no transcript is found (graceful degradation).
    """
    project = _project_dir()
    if not project:
        return None

    path = _active_transcript(project)
    if not path:
        return None

    # Per-turn usage (last assistant message)
    last_usage = _read_last_assistant_usage(path)
    turn_usage = TokenUsage.from_dict(last_usage) if last_usage else None

    # Cumulative (incremental read)
    _read_cumulative_incremental(path)

    cumulative = TokenUsage(
        input_tokens=_cumulative_in,
        output_tokens=_cumulative_out,
        cache_creation_input_tokens=_cumulative_cache_create,
        cache_read_input_tokens=_cumulative_cache_read,
        total_tokens=_cumulative_in + _cumulative_out,
        turn_count=_turn_count,
        started_at=_started_at,
    )

    return TranscriptState(
        turn_usage=turn_usage,
        cumulative=cumulative,
        turn_count=_turn_count,
        started_at=_started_at,
    )
