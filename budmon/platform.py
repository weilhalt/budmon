"""Platform utilities: HiDPI detection and file viewer."""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
import subprocess
from pathlib import Path
from tkinter import messagebox

from budmon.models import DPI_BASE, GDI_LOGPIXELSX, MIN_SCALE, XRDB_TIMEOUT_S


def enable_hidpi() -> float:
    """Enable HiDPI awareness and return the scaling factor."""
    system = platform.system()
    scale = 1.0

    if system == "Windows":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore[union-attr]
        except (AttributeError, OSError):
            try:
                ctypes.windll.user32.SetProcessDPIAware()  # type: ignore[union-attr]
            except (AttributeError, OSError):
                pass
        try:
            hdc = ctypes.windll.user32.GetDC(0)  # type: ignore[union-attr]
            dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, GDI_LOGPIXELSX)  # type: ignore[union-attr]
            ctypes.windll.user32.ReleaseDC(0, hdc)  # type: ignore[union-attr]
            scale = dpi / DPI_BASE
        except (AttributeError, OSError):
            pass

    elif system == "Linux":
        gdk_scale = os.environ.get("GDK_SCALE", "")
        if gdk_scale:
            try:
                scale = float(gdk_scale)
            except ValueError:
                pass
        else:
            try:
                result = subprocess.run(
                    ["xrdb", "-query"],
                    capture_output=True, text=True, timeout=XRDB_TIMEOUT_S,
                )
                for line in result.stdout.splitlines():
                    if line.startswith("Xft.dpi:"):
                        dpi = float(line.split(":", 1)[1].strip())
                        scale = dpi / DPI_BASE
                        break
            except (OSError, subprocess.TimeoutExpired, ValueError):
                pass

    return max(MIN_SCALE, scale)


def open_in_viewer(path: Path) -> None:
    """Open file in system text editor."""
    if not path.exists():
        messagebox.showinfo("Log", f"File does not exist yet:\n{path.name}")
        return
    system = platform.system()
    try:
        if system == "Linux":
            editor = os.environ.get("EDITOR", "")
            if editor and shutil.which(editor):
                cmd = [editor, str(path)]
            else:
                cmd = ["xdg-open", str(path)]
                subprocess.run(
                    ["xdg-mime", "default",
                     "org.gnome.TextEditor.desktop", "text/plain"],
                    capture_output=True, timeout=XRDB_TIMEOUT_S,
                )
            subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        elif system == "Darwin":
            subprocess.Popen(
                ["open", "-t", str(path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                ["notepad.exe", str(path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    except OSError:
        messagebox.showerror("Log", "Could not open editor.")
