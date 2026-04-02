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

    if "--help" in args or "-h" in args:
        print(f"budmon {__version__} — Budget Monitor for Claude Code")
        print()
        print("Usage:")
        print("  budmon              Start the dashboard")
        print("  budmon --setup      Install the Claude Code interceptor")
        print("  budmon --uninstall  Remove the interceptor")
        print("  budmon --version    Show version")
        return

    from budmon.dashboard import main as dashboard_main
    dashboard_main()
