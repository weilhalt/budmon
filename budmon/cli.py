"""CLI entry point for BudMon — handles --setup, --uninstall, --version."""

from __future__ import annotations

import sys

from budmon import __version__


def main() -> None:
    """Main entry point for the budmon command."""
    args = sys.argv[1:]

    if "--version" in args or "-V" in args:
        print(f"budmon {__version__}")
        return

    if "--setup" in args:
        from budmon.setup import setup
        for line in setup():
            print(line)
        return

    if "--uninstall" in args:
        from budmon.setup import uninstall
        for line in uninstall():
            print(line)
        return

    if "--statusline" in args:
        remaining = [a for a in args if a != "--statusline"]
        if "on" in remaining:
            from budmon.setup import statusline_on
            for line in statusline_on():
                print(line)
        elif "off" in remaining:
            from budmon.setup import statusline_off
            for line in statusline_off():
                print(line)
        else:
            from budmon.statusline import render
            print(render())
        return

    if "--help" in args or "-h" in args:
        print(f"budmon {__version__} — Budget Monitor for Claude Code")
        print()
        print("Usage:")
        print("  budmon                  Start the dashboard")
        print("  budmon --setup          Install the Claude Code interceptor")
        print("  budmon --uninstall      Remove the interceptor")
        print("  budmon --statusline     Output for Claude Code status line")
        print("  budmon --statusline on  Activate status line in settings.json")
        print("  budmon --statusline off Deactivate status line")
        print("  budmon --version        Show version")
        return

    from budmon.dashboard import main as dashboard_main
    dashboard_main()
