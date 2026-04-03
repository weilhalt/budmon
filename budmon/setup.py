"""BudMon setup and uninstall — installs the fetch interceptor for Claude Code."""

from __future__ import annotations

import json
import platform
import re
import shutil
import stat
import sys
from importlib.resources import files as pkg_files
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
INTERCEPTOR_DEST = CLAUDE_DIR / "budmon-interceptor.mjs"
WRAPPER_NAME = "claude-budmon"
DESKTOP_FILE = Path.home() / ".local" / "share" / "applications" / "budmon.desktop"

DESKTOP_TEMPLATE = """\
[Desktop Entry]
Name=BudMon
Name[de]=BudMon
Comment=Budget Monitor for Claude Code
Comment[de]=Budget-Monitor für Claude Code
GenericName=Budget Monitor
GenericName[de]=Budget-Monitor
Exec={exec_path}
Icon={icon_path}
Type=Application
Terminal=false
Categories=Development;Utility;Monitor;
Keywords=claude;budget;token;monitor;dashboard;
Keywords[de]=claude;budget;token;monitor;dashboard;kosten;verbrauch;
StartupWMClass=budmon
"""

# Known existing interceptor filenames (detect before installing)
KNOWN_INTERCEPTORS = [
    "cache-fix-preload.mjs",
    "claude-interceptor.mjs",
]

# Shell config files to check for alias insertion
SHELL_CONFIGS = [
    Path.home() / ".bashrc",
    Path.home() / ".zshrc",
]

ALIAS_MARKER = "# budmon-interceptor"
ALIAS_LINE_TEMPLATE = (
    'alias claude-budmon=\'NODE_OPTIONS="--import {mjs}" claude\'  {marker}'
)

WINDOWS_CMD_TEMPLATE = (
    '@echo off\r\n'
    'set NODE_OPTIONS=--import {mjs}\r\n'
    'claude %*\r\n'
)


def _interceptor_source() -> Path:
    """Return the path to the bundled interceptor.mjs."""
    return Path(str(pkg_files("budmon") / "interceptor.mjs"))


def detect_existing_interceptor() -> str | None:
    """Check if user already has a compatible interceptor.

    Returns the filename if found, None otherwise.
    """
    for name in KNOWN_INTERCEPTORS:
        path = CLAUDE_DIR / name
        if path.exists():
            try:
                text = path.read_text(encoding="utf-8")
                if "usage-limits" in text and "ratelimit" in text:
                    return name
            except OSError:
                continue
    return None


def _find_windows_path_dir() -> Path | None:
    """Find a suitable directory on PATH for the Windows .cmd wrapper."""
    npm_global = Path.home() / ".npm-global" / "bin"
    if npm_global.exists():
        return npm_global
    local_bin = Path.home() / "AppData" / "Local" / "Microsoft" / "WindowsApps"
    if local_bin.exists():
        return local_bin
    local_bin2 = Path.home() / ".local" / "bin"
    if local_bin2.exists():
        return local_bin2
    return None


def setup() -> list[str]:
    """Install the BudMon interceptor. Returns list of status messages."""
    msgs: list[str] = []

    # Check Claude Code exists
    if not CLAUDE_DIR.exists():
        return ["~/.claude/ not found. Is Claude Code installed?"]

    # Check if claude binary is available
    if not shutil.which("claude"):
        msgs.append(
            "Warning: 'claude' not found on PATH. "
            "Make sure Claude Code is installed."
        )

    # Check for existing compatible interceptor
    existing = detect_existing_interceptor()
    if existing:
        msgs.append(
            f"Compatible interceptor found: ~/.claude/{existing}"
        )
        msgs.append(
            "BudMon can already read your data. No additional setup needed."
        )
        msgs.append("Start Claude Code normally and then run 'budmon'.")
        return msgs

    # Copy interceptor
    src = _interceptor_source()
    if not src.exists():
        return [f"Interceptor source not found: {src}"]

    INTERCEPTOR_DEST.write_text(
        src.read_text(encoding="utf-8"), encoding="utf-8",
    )
    msgs.append(f"Installed: {INTERCEPTOR_DEST}")

    # Platform-specific alias/wrapper
    system = platform.system()
    if system == "Windows":
        target_dir = _find_windows_path_dir()
        if target_dir:
            cmd_path = target_dir / f"{WRAPPER_NAME}.cmd"
            mjs_path = str(INTERCEPTOR_DEST).replace("\\", "/")
            cmd_path.write_text(
                WINDOWS_CMD_TEMPLATE.format(mjs=mjs_path),
                encoding="utf-8",
            )
            msgs.append(f"Installed: {cmd_path}")
            msgs.append(f"Start Claude with: {WRAPPER_NAME}")
        else:
            msgs.append(
                "Could not find a PATH directory for the wrapper."
            )
            mjs_path = str(INTERCEPTOR_DEST).replace("\\", "/")
            msgs.append(
                f'Manual setup: set NODE_OPTIONS=--import {mjs_path}'
            )
            msgs.append("Then run: claude")
    else:
        # Linux / macOS: add alias to shell config
        alias_line = ALIAS_LINE_TEMPLATE.format(
            mjs=INTERCEPTOR_DEST, marker=ALIAS_MARKER,
        )
        installed_alias = False
        for rc in SHELL_CONFIGS:
            if rc.exists():
                text = rc.read_text(encoding="utf-8")
                if ALIAS_MARKER in text:
                    msgs.append(f"Alias already in {rc.name}")
                    installed_alias = True
                    continue
                rc.write_text(
                    text.rstrip("\n") + "\n\n" + alias_line + "\n",
                    encoding="utf-8",
                )
                msgs.append(f"Alias added to {rc.name}")
                installed_alias = True

        if not installed_alias:
            msgs.append("No .bashrc or .zshrc found.")
            msgs.append(f"Add manually: {alias_line}")

        # Also create a standalone wrapper script in ~/.local/bin
        local_bin = Path.home() / ".local" / "bin"
        if local_bin.exists() or local_bin.parent.exists():
            local_bin.mkdir(parents=True, exist_ok=True)
            wrapper = local_bin / WRAPPER_NAME
            wrapper.write_text(
                f'#!/bin/sh\n'
                f'export NODE_OPTIONS="--import {INTERCEPTOR_DEST}"\n'
                f'exec claude "$@"\n',
                encoding="utf-8",
            )
            wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
            msgs.append(f"Installed: {wrapper}")

    # Linux: create .desktop file
    if platform.system() == "Linux":
        budmon_bin = shutil.which("budmon")
        if budmon_bin:
            icon = Path(__file__).parent / "icons" / "budmon.svg"
            icon_str = str(icon) if icon.exists() else "budmon"
            DESKTOP_FILE.parent.mkdir(parents=True, exist_ok=True)
            DESKTOP_FILE.write_text(
                DESKTOP_TEMPLATE.format(exec_path=budmon_bin, icon_path=icon_str),
                encoding="utf-8",
            )
            msgs.append(f"Installed: {DESKTOP_FILE}")

    msgs.append("")
    msgs.append("Setup complete. Start Claude with: claude-budmon")
    msgs.append("Then run 'budmon' to see the dashboard.")
    return msgs


def uninstall() -> list[str]:
    """Remove BudMon interceptor and aliases. Returns status messages."""
    msgs: list[str] = []

    # Remove interceptor file
    if INTERCEPTOR_DEST.exists():
        INTERCEPTOR_DEST.unlink()
        msgs.append(f"Removed: {INTERCEPTOR_DEST}")
    else:
        msgs.append("Interceptor not found (already removed?).")

    # Remove shell aliases
    for rc in SHELL_CONFIGS:
        if rc.exists():
            text = rc.read_text(encoding="utf-8")
            if ALIAS_MARKER in text:
                lines = [
                    ln for ln in text.splitlines()
                    if ALIAS_MARKER not in ln
                ]
                rc.write_text("\n".join(lines) + "\n", encoding="utf-8")
                msgs.append(f"Alias removed from {rc.name}")

    # Remove wrapper script
    local_bin = Path.home() / ".local" / "bin"
    wrapper = local_bin / WRAPPER_NAME
    if wrapper.exists():
        wrapper.unlink()
        msgs.append(f"Removed: {wrapper}")

    # Remove Windows .cmd
    system = platform.system()
    if system == "Windows":
        target_dir = _find_windows_path_dir()
        if target_dir:
            cmd_path = target_dir / f"{WRAPPER_NAME}.cmd"
            if cmd_path.exists():
                cmd_path.unlink()
                msgs.append(f"Removed: {cmd_path}")

    # Remove .desktop file
    if DESKTOP_FILE.exists():
        DESKTOP_FILE.unlink()
        msgs.append(f"Removed: {DESKTOP_FILE}")

    msgs.append("")
    msgs.append("Uninstall complete. Data files in ~/.claude/ were kept.")
    return msgs


# ---------------------------------------------------------------------------
# Status line activation / deactivation
# ---------------------------------------------------------------------------

SETTINGS_FILE = CLAUDE_DIR / "settings.json"

_JSONC_LINE_COMMENT = re.compile(r"^\s*//.*$", re.MULTILINE)
_JSONC_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_JSONC_TRAILING_COMMA = re.compile(r",\s*([}\]])")


def _strip_jsonc(text: str) -> str:
    """Remove JSONC extensions (comments, trailing commas) for json.loads."""
    text = _JSONC_BLOCK_COMMENT.sub("", text)
    text = _JSONC_LINE_COMMENT.sub("", text)
    text = _JSONC_TRAILING_COMMA.sub(r"\1", text)
    return text


def _read_settings() -> dict:
    """Read settings.json, tolerating JSONC format."""
    if not SETTINGS_FILE.exists():
        return {}
    try:
        raw = SETTINGS_FILE.read_text(encoding="utf-8")
        return json.loads(_strip_jsonc(raw))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_settings(data: dict) -> None:
    """Write settings.json with consistent formatting."""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _resolve_budmon_command() -> str | None:
    """Find the best command string to invoke ``budmon --statusline``.

    Returns None if budmon cannot be located.
    """
    # Prefer the entry-point script on PATH
    which = shutil.which("budmon")
    if which:
        return f"{which} --statusline"
    # Fallback: python -m budmon
    exe = sys.executable
    if exe:
        return f"{exe} -m budmon --statusline"
    return None


def statusline_on() -> list[str]:
    """Activate BudMon status line in Claude Code settings.json."""
    msgs: list[str] = []

    command = _resolve_budmon_command()
    if not command:
        return ["Error: Cannot find budmon on PATH or via Python executable."]

    data = _read_settings()

    # Warn if replacing a foreign status line
    existing = data.get("statusLine", {})
    if isinstance(existing, dict):
        old_cmd = existing.get("command", "")
        if old_cmd and "budmon" not in old_cmd:
            msgs.append(f"Replacing: {old_cmd}")

    data["statusLine"] = {"type": "command", "command": command}

    try:
        _write_settings(data)
    except (OSError, PermissionError) as exc:
        return [f"Error writing {SETTINGS_FILE}: {exc}"]

    msgs.append(f"Status line activated: {command}")
    msgs.append("Restart Claude Code to apply.")
    return msgs


def statusline_off() -> list[str]:
    """Deactivate BudMon status line in Claude Code settings.json."""
    msgs: list[str] = []

    data = _read_settings()
    existing = data.get("statusLine", {})

    if not isinstance(existing, dict) or not existing:
        return ["Status line is not configured — nothing to remove."]

    old_cmd = existing.get("command", "")
    if "budmon" not in old_cmd:
        return [f"Status line is set to '{old_cmd}' (not budmon) — not modifying."]

    del data["statusLine"]

    try:
        _write_settings(data)
    except (OSError, PermissionError) as exc:
        return [f"Error writing {SETTINGS_FILE}: {exc}"]

    msgs.append("Status line deactivated.")
    msgs.append("Restart Claude Code to apply.")
    return msgs
