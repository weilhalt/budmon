"""Budget Monitor Dashboard — tkinter GUI for Claude Code token usage.

Usage: python -m budmon
       budmon  (after pip install)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import tkinter as tk
except ImportError:
    raise SystemExit(
        "tkinter not available.\n"
        "  Linux:   sudo apt install python3-tk\n"
        "  macOS:   brew install python-tk\n"
        "  Windows: reinstall Python with 'tcl/tk' option checked"
    )

from budmon import __version__
from budmon.i18n import (
    available_languages,
    current_language,
    help_file_path,
    language_name,
    load_language,
    save_preference,
    t,
)
from budmon.config import cfg
from budmon.data import (
    HISTORY_LOG_FILE,
    SESSION_LOG_FILE,
    USAGE_LIMITS_FILE,
    burn_rate_color,
    calc_burn,
    calc_cost,
    format_burn_empty,
    format_burn_rate,
    format_margin,
    format_reset,
    format_since,
    load_prices,
    margin_color,
    parse_quota_state,
    read_json,
)
from budmon.models import (
    BurnInfo,
    C_ACCENT,
    C_BAR_BG,
    C_BG,
    C_CYAN,
    C_DIM,
    C_FG,
    C_GREEN,
    C_RED,
    C_YELLOW,
    CANVAS_SPARKLINE_HEIGHT,
    CD_BASE_SIZE,
    CD_RING_DIAMETER,
    CD_RING_WIDTH,
    FIVE_HOURS,
    FONT_SIZE_CACHE,
    FONT_SIZE_FOOTER,
    FONT_SIZE_HEADER,
    FONT_SIZE_NORMAL,
    FONT_SIZE_SMALL,
    FONT_SIZE_STATUS,
    PAD_X,
    SEVEN_DAYS_HOURS,
    TokenUsage,
    color_for_cache,
    color_for_quota,
    scaled_font,
)
from budmon.platform import enable_hidpi, open_in_viewer
from budmon.widgets import (
    draw_bar, draw_countdown, draw_sparkline,
    make_bar_row, make_burn_rows, make_detail_column, make_reset_row,
)


class BudgetDashboard:
    """Main window of the Budget Monitor."""

    def __init__(self) -> None:
        self._scale = enable_hidpi()
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("Budget Monitor")
        self.root.configure(bg=C_BG)
        self.root.resizable(False, False)

        icon_path = Path(__file__).parent / "icons" / "budmon-64.png"
        if icon_path.exists():
            self._icon = tk.PhotoImage(file=str(icon_path))
            self.root.iconphoto(True, self._icon)

        if self._scale > 1.0:
            self.root.tk.call("tk", "scaling", self._scale)

        self._burn_5h: dict[str, tk.Label] = {}
        self._burn_7d: dict[str, tk.Label] = {}
        self._turn_details: dict[str, tk.Label] = {}
        self._cum_details: dict[str, tk.Label] = {}
        self.root.minsize(0, 0)

        for opt, val in [
            ("*Menu.background", C_BAR_BG), ("*Menu.foreground", C_FG),
            ("*Menu.activeBackground", C_DIM), ("*Menu.activeForeground", C_FG),
            ("*Menu.relief", "flat"), ("*Menu.borderWidth", "0"),
        ]:
            self.root.option_add(opt, val)

        self.prices = load_prices()
        self._file_mtime: dict[str, float] = {}
        self._tick = 0
        self._last_limits: dict[str, Any] = {}

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_menubar()
        self._build_header()

        # 5h quota + countdown ring
        (self._quota_5h_frame, self.lbl_5h, self.bar_5h, self.lbl_5h_val,
         self.lbl_reset, self._burn_5h) = self._build_quota_section(t("label_5h_quota"))
        s = self._scale
        cd_size = int(CD_BASE_SIZE * s)
        self._cd_size = cd_size
        self._cd_ring_d = int(CD_RING_DIAMETER * s)
        self._cd_ring_w = max(2, int(CD_RING_WIDTH * s))
        self.canvas_cd = tk.Canvas(
            self.root, width=cd_size, height=cd_size,
            bg=C_BG, highlightthickness=0, bd=0,
        )
        self._cd_needs_place = True
        self._sep()

        # 7d quota
        (self._quota_7d_frame, self.lbl_7d, self.bar_7d, self.lbl_7d_val,
         self.lbl_reset_7d, self._burn_7d) = self._build_quota_section(t("label_7d_quota"))
        self._sep()

        self._build_details()
        self._build_sparkline_section()
        self._build_footer()

        self._restore_position()
        self.root.deiconify()
        self._check_first_run()
        self._refresh()

    # -- Window position ---------------------------------------------------

    def _save_position(self) -> None:
        """Save current window geometry to config."""
        cfg.window_geometry = self.root.geometry()
        cfg.save()

    def _restore_position(self) -> None:
        """Restore window position from config, or center on screen."""
        self.root.update_idletasks()
        geo = cfg.window_geometry
        if geo and "+" in geo:
            try:
                parts = geo.split("+", 1)
                coord_str = parts[1]
                coords = coord_str.replace("+-", "+NEGATIVE").split("+")
                x = int(coords[0])
                y_str = coords[1].replace("NEGATIVE", "-") if len(coords) > 1 else "0"
                y = int(y_str)
                screen_w = self.root.winfo_screenwidth()
                screen_h = self.root.winfo_screenheight()
                if 0 <= x <= screen_w - 50 and 0 <= y <= screen_h - 50:
                    self.root.geometry(f"+{x}+{y}")
                    return
            except (ValueError, IndexError):
                pass
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        win_w = self.root.winfo_width()
        win_h = self.root.winfo_height()
        self.root.geometry(
            f"+{(screen_w - win_w) // 2}+{(screen_h - win_h) // 2}",
        )

    def _on_close(self) -> None:
        """Save position and close."""
        self._save_position()
        self.root.destroy()

    def _check_first_run(self) -> None:
        """Show setup dialog if no data source is detected."""
        from budmon.data import USAGE_LIMITS_FILE
        from budmon.setup import detect_existing_interceptor, INTERCEPTOR_DEST

        # Data file exists or interceptor installed → all good
        if USAGE_LIMITS_FILE.exists():
            return
        if INTERCEPTOR_DEST.exists():
            return
        if detect_existing_interceptor():
            return

        self._show_setup_dialog()

    def _show_setup_dialog(self) -> None:
        """Show first-run setup dialog."""
        from budmon.setup import setup as run_setup

        s = self._scale
        dlg = tk.Toplevel(self.root)
        dlg.title(t("setup_title"))
        dlg.configure(bg=C_BG)
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        px = int(20 * s)
        py = int(12 * s)
        frame = tk.Frame(dlg, bg=C_BG, padx=px, pady=py)
        frame.pack(fill="both", expand=True)

        tk.Label(
            frame, text=t("setup_title"),
            font=self._sf(FONT_SIZE_HEADER, "bold"),
            bg=C_BG, fg=C_ACCENT,
        ).pack(anchor="w")

        tk.Label(
            frame, text=t("setup_message"), font=self._sf(),
            bg=C_BG, fg=C_FG, justify="left",
        ).pack(anchor="w", pady=(int(8 * s), int(12 * s)))

        btn_frame = tk.Frame(frame, bg=C_BG)
        btn_frame.pack(anchor="e")

        def do_install() -> None:
            dlg.destroy()
            msgs = run_setup()
            result_dlg = tk.Toplevel(self.root)
            result_dlg.title("Setup")
            result_dlg.configure(bg=C_BG)
            result_dlg.transient(self.root)
            result_dlg.grab_set()
            rf = tk.Frame(result_dlg, bg=C_BG, padx=px, pady=py)
            rf.pack(fill="both", expand=True)
            tk.Label(
                rf, text="\n".join(msgs), font=self._sf(FONT_SIZE_SMALL),
                bg=C_BG, fg=C_FG, justify="left",
            ).pack(anchor="w")
            ok_btn = tk.Label(
                rf, text=f"  {t('about_close')}  ",
                font=self._sf(FONT_SIZE_SMALL),
                bg=C_BAR_BG, fg=C_FG, cursor="hand2",
                padx=int(12 * s), pady=int(4 * s),
            )
            ok_btn.pack(anchor="e", pady=(int(8 * s), 0))
            ok_btn.bind("<Enter>", lambda _: ok_btn.configure(bg=C_DIM))
            ok_btn.bind("<Leave>", lambda _: ok_btn.configure(bg=C_BAR_BG))
            ok_btn.bind("<Button-1>", lambda _: result_dlg.destroy())
            result_dlg.bind("<Escape>", lambda _: result_dlg.destroy())

        for label_text, cmd in [
            (t("setup_install"), do_install),
            (t("setup_later"), dlg.destroy),
        ]:
            btn = tk.Label(
                btn_frame, text=f"  {label_text}  ",
                font=self._sf(FONT_SIZE_SMALL),
                bg=C_BAR_BG, fg=C_FG, cursor="hand2",
                padx=int(12 * s), pady=int(4 * s),
            )
            btn.pack(side="left", padx=(int(4 * s), 0))
            btn.bind("<Enter>", lambda _, w=btn: w.configure(bg=C_DIM))
            btn.bind("<Leave>", lambda _, w=btn: w.configure(bg=C_BAR_BG))
            btn.bind("<Button-1>", lambda _, fn=cmd: fn())

        dlg.bind("<Escape>", lambda _: dlg.destroy())

        dlg.update_idletasks()
        px_root = self.root.winfo_rootx()
        py_root = self.root.winfo_rooty()
        pw = self.root.winfo_width()
        ph = self.root.winfo_height()
        dw = dlg.winfo_width()
        dh = dlg.winfo_height()
        dlg.geometry(f"+{px_root + (pw - dw) // 2}+{py_root + (ph - dh) // 2}")

    # -- Helpers -----------------------------------------------------------

    def _sf(
        self, size: int = FONT_SIZE_NORMAL, weight: str = "",
        family: str = "monospace",
    ) -> tuple[str, int] | tuple[str, int, str]:
        return scaled_font(self._scale, family, size, weight)

    def _px(self) -> int:
        return max(1, int(PAD_X * self._scale))

    def _sep(self) -> None:
        sep_py = max(1, int(3 * self._scale))
        tk.Frame(self.root, bg=C_DIM, height=1).pack(
            fill="x", padx=self._px(), pady=sep_py,
        )

    # -- Build sections ----------------------------------------------------

    def _build_header(self) -> None:
        px = self._px()
        s = self._scale
        hdr = tk.Frame(self.root, bg=C_BG)
        hdr.pack(fill="x", padx=px, pady=(int(6 * s), int(2 * s)))
        tk.Label(
            hdr, text=t("title"), font=self._sf(FONT_SIZE_HEADER, "bold"),
            bg=C_BG, fg=C_ACCENT,
        ).pack(side="left")
        tk.Label(
            hdr, text=f"v{__version__}", font=self._sf(FONT_SIZE_SMALL),
            bg=C_BG, fg=C_DIM,
        ).pack(side="left", padx=(int(6 * s), 0))
        self.lbl_status = tk.Label(
            hdr, text=t("status_ok"), font=self._sf(FONT_SIZE_STATUS, "bold"),
            bg=C_BG, fg=C_GREEN,
        )
        self.lbl_status.pack(side="right")
        self.lbl_heartbeat = tk.Label(
            hdr, text="\u25cf", font=self._sf(FONT_SIZE_HEADER), bg=C_BG, fg=C_GREEN,
        )
        self.lbl_heartbeat.pack(side="right", padx=(0, int(6 * s)))
        self._sep()

    def _build_quota_section(
        self, label: str,
    ) -> tuple[tk.Frame, tk.Label, tk.Canvas, tk.Label, tk.Label, dict[str, tk.Label]]:
        """Build a quota section (bar + reset + burn rows)."""
        s = self._scale
        frame, lbl, bar, val = make_bar_row(self.root, s, label)
        reset_lbl = make_reset_row(self.root, s)
        burn_labels = make_burn_rows(self.root, s)
        return frame, lbl, bar, val, reset_lbl, burn_labels

    def _build_details(self) -> None:
        s = self._scale
        px = self._px()
        row_py = max(1, int(1 * s))
        cols = tk.Frame(self.root, bg=C_BG)
        cols.pack(fill="x", padx=px, pady=row_py)

        self.lbl_usage, self._turn_details = make_detail_column(
            cols, s, t("label_last_request"),
        )
        self.lbl_usage.master.pack(side="left", anchor="nw")  # type: ignore[union-attr]

        self.lbl_cum_tokens, self._cum_details = make_detail_column(
            cols, s, t("label_total_requests"),
        )
        self.lbl_cum_tokens.master.pack(  # type: ignore[union-attr]
            side="left", anchor="nw", padx=(int(16 * s), 0),
        )
        self._sep()

    def _build_sparkline_section(self) -> None:
        s = self._scale
        px = self._px()
        row_py = max(1, int(1 * s))
        spark_row = tk.Frame(self.root, bg=C_BG)
        spark_row.pack(fill="x", padx=px, pady=row_py)
        tk.Label(
            spark_row, text=t("label_cache_ratio"), font=self._sf(),
            bg=C_BG, fg=C_DIM,
        ).pack(side="left")
        self.lbl_cache = tk.Label(
            spark_row, text="--", font=self._sf(FONT_SIZE_CACHE, "bold"),
            bg=C_BG, fg=C_GREEN,
        )
        self.lbl_cache.pack(side="left", padx=(int(8 * s), int(12 * s)))
        tk.Label(
            spark_row, text=t("label_avg"), font=self._sf(FONT_SIZE_SMALL),
            bg=C_BG, fg=C_DIM,
        ).pack(side="left")
        self.lbl_cache_avg = tk.Label(
            spark_row, text="--", font=self._sf(), bg=C_BG, fg=C_FG,
        )
        self.lbl_cache_avg.pack(side="left", padx=(int(4 * s), 0))

        self.canvas = tk.Canvas(
            self.root, height=int(CANVAS_SPARKLINE_HEIGHT * s), bg=C_BAR_BG,
            highlightthickness=0, bd=0,
        )
        self.canvas.pack(padx=px, pady=(int(2 * s), int(4 * s)), fill="x")

    def _build_menubar(self) -> None:
        s = self._scale
        bar = tk.Frame(self.root, bg=C_BAR_BG)
        bar.pack(fill="x")
        self._popup: tk.Toplevel | None = None

        menu_items: list[tuple[str, list[tuple[str, Any]]]] = [
            (t("menu_logs"), [
                (t("menu_session_log"), lambda: open_in_viewer(SESSION_LOG_FILE)),
                (t("menu_history_log"), lambda: open_in_viewer(HISTORY_LOG_FILE)),
                ("---", None),
                (t("menu_open_folder"), lambda: self._open_log_folder()),
            ]),
            (t("menu_settings"), [
                (t("menu_language"), "submenu_lang"),
                ("---", None),
                (t("menu_model"), "submenu_model"),
                ("---", None),
                (t("menu_open_ini"), lambda: self._open_ini()),
            ]),
            (t("menu_help"), [
                (t("menu_user_guide"), lambda: open_in_viewer(help_file_path())),
                ("---", None),
                (t("menu_about"), lambda: self._show_about()),
            ]),
        ]

        for title, items in menu_items:
            btn = tk.Label(
                bar, text=f" {title} ", font=self._sf(FONT_SIZE_SMALL),
                bg=C_BAR_BG, fg=C_FG, cursor="hand2",
                padx=int(4 * s), pady=int(2 * s),
            )
            btn.pack(side="left")
            btn.bind("<Enter>", lambda e, w=btn: w.configure(bg=C_DIM))
            btn.bind("<Leave>", lambda e, w=btn: w.configure(bg=C_BAR_BG))
            btn.bind("<Button-1>", lambda e, w=btn, it=items: self._show_popup(w, it))

    def _add_popup_row(
        self, parent: tk.Frame, text: str, command: Any,
        font: Any, pad: int, vpad: int,
    ) -> None:
        """Add a clickable row to the popup menu."""
        row = tk.Label(
            parent, text=text, font=font, bg=C_BAR_BG, fg=C_FG,
            anchor="w", padx=pad, pady=vpad, cursor="hand2",
        )
        row.pack(fill="x")
        row.bind("<Enter>", lambda _: row.configure(bg=C_DIM))
        row.bind("<Leave>", lambda _: row.configure(bg=C_BAR_BG))
        row.bind("<Button-1>", lambda _, fn=command: self._popup_action(fn))

    def _popup_action(self, fn: Any) -> None:
        """Close popup, then execute action after a brief delay."""
        self._close_popup()
        self.root.after(10, fn)

    def _show_popup(
        self, anchor: tk.Widget, items: list[tuple[str, Any]],
    ) -> None:
        """Show a dark dropdown popup below the anchor widget."""
        if self._popup and self._popup.winfo_exists():
            self._close_popup()
            return
        self._close_popup()
        s = self._scale
        pad = int(8 * s)
        vpad = int(4 * s)

        popup = tk.Toplevel(self.root)
        popup.overrideredirect(True)
        popup.configure(bg=C_DIM)
        self._popup = popup

        inner = tk.Frame(popup, bg=C_BAR_BG, padx=1, pady=1)
        inner.pack(fill="both", expand=True)

        font = self._sf(FONT_SIZE_SMALL)
        cur_lang = current_language()

        for label_text, action in items:
            if action is None:
                tk.Frame(inner, bg=C_DIM, height=1).pack(
                    fill="x", padx=pad, pady=vpad,
                )
                continue
            if action == "submenu_lang":
                for lang_code in available_languages():
                    name = language_name(lang_code)
                    check = "\u2713" if lang_code == cur_lang else " "
                    self._add_popup_row(
                        inner, f" {check}  {name}",
                        lambda lc=lang_code: self._switch_language(lc),
                        font, pad, vpad,
                    )
            elif action == "submenu_model":
                from budmon.config import MODEL_PRESETS
                models = list(MODEL_PRESETS.keys()) + ["custom"]
                cur_model = cfg.model
                for model_name in models:
                    check = "\u2713" if model_name == cur_model else " "
                    display = model_name.capitalize()
                    self._add_popup_row(
                        inner, f" {check}  {display}",
                        lambda m=model_name: self._switch_model(m),
                        font, pad, vpad,
                    )
            else:
                self._add_popup_row(
                    inner, f"  {label_text}", action, font, pad, vpad,
                )

        popup.update_idletasks()
        x = anchor.winfo_rootx()
        y = anchor.winfo_rooty() + anchor.winfo_height()
        popup.geometry(f"+{x}+{y}")

        # Close on click outside or focus loss
        self._dismiss_id = self.root.bind(
            "<Button-1>", lambda _: self.root.after_idle(self._dismiss_popup),
        )
        self._focus_id = self.root.bind(
            "<FocusOut>", lambda _: self.root.after(100, self._dismiss_popup),
        )

    def _dismiss_popup(self) -> None:
        """Dismiss popup from outside click — only if still open."""
        if self._popup and self._popup.winfo_exists():
            self._close_popup()

    def _close_popup(self) -> None:
        """Close the active popup menu."""
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()
        self._popup = None
        if hasattr(self, "_dismiss_id") and self._dismiss_id:
            self.root.unbind("<Button-1>", self._dismiss_id)
            self._dismiss_id = None
        if hasattr(self, "_focus_id") and self._focus_id:
            self.root.unbind("<FocusOut>", self._focus_id)
            self._focus_id = None

    def _open_ini(self) -> None:
        """Open the config INI file in the system editor."""
        from budmon.config import CONFIG_FILE
        open_in_viewer(CONFIG_FILE)

    def _open_log_folder(self) -> None:
        """Open the log directory in the system file browser."""
        import platform as plat
        import subprocess
        log_dir = SESSION_LOG_FILE.parent
        if not log_dir.exists():
            return
        try:
            system = plat.system()
            if system == "Linux":
                cmd = ["xdg-open", str(log_dir)]
            elif system == "Darwin":
                cmd = ["open", str(log_dir)]
            else:
                cmd = ["explorer.exe", str(log_dir)]
            subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass

    def _show_about(self) -> None:
        """Show About dialog."""
        import sys
        import webbrowser

        dlg = tk.Toplevel(self.root)
        dlg.title(t("menu_about"))
        dlg.configure(bg=C_BG)
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        s = self._scale
        px = int(20 * s)
        py = int(12 * s)

        frame = tk.Frame(dlg, bg=C_BG, padx=px, pady=py)
        frame.pack(fill="both", expand=True)

        # Title + Version
        tk.Label(
            frame, text="BudMon", font=self._sf(FONT_SIZE_HEADER, "bold"),
            bg=C_BG, fg=C_ACCENT,
        ).pack(anchor="w")
        tk.Label(
            frame, text=f"v{__version__}", font=self._sf(FONT_SIZE_STATUS),
            bg=C_BG, fg=C_DIM,
        ).pack(anchor="w")

        # Description
        tk.Label(
            frame, text=t("about_description"), font=self._sf(),
            bg=C_BG, fg=C_FG, wraplength=int(300 * s), justify="left",
        ).pack(anchor="w", pady=(int(8 * s), 0))

        # Separator
        tk.Frame(frame, bg=C_DIM, height=1).pack(
            fill="x", pady=int(10 * s),
        )

        # Info rows
        info_font = self._sf(FONT_SIZE_SMALL)
        rows = [
            (t("about_author"), "weilhalt"),
            (t("about_license"), "GPL-3.0"),
            (t("about_runtime"), f"Python {sys.version_info.major}.{sys.version_info.minor} / tkinter"),
        ]
        for label_text, value in rows:
            row = tk.Frame(frame, bg=C_BG)
            row.pack(fill="x", pady=int(2 * s))
            tk.Label(
                row, text=label_text, font=info_font,
                bg=C_BG, fg=C_DIM, width=10, anchor="w",
            ).pack(side="left")
            tk.Label(
                row, text=value, font=info_font,
                bg=C_BG, fg=C_FG, anchor="w",
            ).pack(side="left")

        # Homepage link
        row = tk.Frame(frame, bg=C_BG)
        row.pack(fill="x", pady=int(2 * s))
        tk.Label(
            row, text=t("about_homepage"), font=info_font,
            bg=C_BG, fg=C_DIM, width=10, anchor="w",
        ).pack(side="left")
        url = "https://github.com/weilhalt/budmon"
        link = tk.Label(
            row, text=url, font=info_font,
            bg=C_BG, fg=C_CYAN, anchor="w", cursor="hand2",
        )
        link.pack(side="left")
        link.bind("<Button-1>", lambda _: webbrowser.open(url))
        link.bind("<Enter>", lambda _: link.configure(fg=C_GREEN))
        link.bind("<Leave>", lambda _: link.configure(fg=C_CYAN))

        # Close button
        tk.Frame(frame, bg=C_DIM, height=1).pack(
            fill="x", pady=int(10 * s),
        )
        btn = tk.Label(
            frame, text=f"  {t('about_close')}  ", font=self._sf(FONT_SIZE_SMALL),
            bg=C_BAR_BG, fg=C_FG, cursor="hand2",
            padx=int(12 * s), pady=int(4 * s),
        )
        btn.pack(anchor="e")
        btn.bind("<Enter>", lambda _: btn.configure(bg=C_DIM))
        btn.bind("<Leave>", lambda _: btn.configure(bg=C_BAR_BG))
        btn.bind("<Button-1>", lambda _: dlg.destroy())
        dlg.bind("<Escape>", lambda _: dlg.destroy())

        # Center on parent
        dlg.update_idletasks()
        px_root = self.root.winfo_rootx()
        py_root = self.root.winfo_rooty()
        pw = self.root.winfo_width()
        ph = self.root.winfo_height()
        dw = dlg.winfo_width()
        dh = dlg.winfo_height()
        dlg.geometry(f"+{px_root + (pw - dw) // 2}+{py_root + (ph - dh) // 2}")

    def _switch_language(self, lang: str) -> None:
        """Switch language and rebuild the entire UI."""
        self._save_position()
        load_language(lang)
        save_preference(lang)
        self.root.destroy()
        new_app = BudgetDashboard()
        new_app.run()

    def _switch_model(self, model: str) -> None:
        """Switch model and reload prices."""
        cfg.set_model(model)
        self.prices = load_prices()

    def _build_footer(self) -> None:
        s = self._scale
        self.lbl_updated = tk.Label(
            self.root, text="", font=self._sf(FONT_SIZE_FOOTER), bg=C_BG, fg=C_DIM,
        )
        self.lbl_updated.pack(pady=(0, int(4 * s)))

    # -- Countdown placement -----------------------------------------------

    def _place_countdown(self) -> None:
        """Position countdown ring relative to 5h bar (once)."""
        if not self._cd_needs_place:
            return
        self.root.update_idletasks()
        s = self._scale
        r = self.root
        sz = self._cd_size
        bar_x = self.bar_5h.winfo_rootx() - r.winfo_rootx()
        bar_w = self.bar_5h.winfo_width()
        marker_x = bar_x + int(bar_w * cfg.quota_alarm_pct / 100)
        cx = marker_x - sz // 2
        bar_bottom = (
            self.bar_5h.winfo_rooty() - r.winfo_rooty()
            + self.bar_5h.winfo_height()
        )
        last_lbl = self._burn_5h["rate"]
        sep_top = (
            last_lbl.winfo_rooty() - r.winfo_rooty()
            + last_lbl.winfo_height() + int(3 * s)
        )
        mid_y = (bar_bottom + sep_top) // 2
        cy = mid_y - sz // 2
        self.canvas_cd.place(x=cx, y=cy)
        self._cd_needs_place = False

    # -- Burn rate update --------------------------------------------------

    def _update_burn_labels(
        self, labels: dict[str, tk.Label],
        burn: BurnInfo, window_h: float,
    ) -> None:
        """Update burn-rate labels from computed BurnInfo."""
        if not burn.valid:
            for lbl in labels.values():
                lbl.configure(text="--", fg=C_DIM)
            return

        rate_clr = burn_rate_color(burn.rate)
        empty_clr = C_CYAN if rate_clr == C_GREEN else rate_clr
        labels["rate"].configure(text=format_burn_rate(burn, window_h), fg=C_FG)
        labels["empty"].configure(
            text=format_burn_empty(burn, window_h), fg=empty_clr,
        )
        labels["diff"].configure(
            text=format_margin(burn), fg=margin_color(burn.margin_seconds),
        )

    # -- Refresh -----------------------------------------------------------

    def _refresh(self) -> None:
        try:
            self._do_refresh()
        except Exception:
            pass  # Fail-open: GUI must never crash
        self.root.after(cfg.refresh_ms, self._refresh)

    def _do_refresh(self) -> None:
        limits = read_json(USAGE_LIMITS_FILE)

        if limits:
            self._last_limits = limits
        else:
            limits = self._last_limits

        state = parse_quota_state(limits)

        self._tick += 1
        pulse_bright = self._tick % 2 == 0
        self.lbl_heartbeat.configure(fg=C_GREEN if pulse_bright else C_DIM)

        if not state.headers:
            self.lbl_status.configure(text=t("status_wait"), fg=C_YELLOW)
            self.lbl_updated.configure(
                text=f"{t('waiting_for_data')}  |  Poll #{self._tick}",
            )
            return

        # Quotas
        draw_bar(self.bar_5h, state.pct_5h, color_for_quota(state.pct_5h))
        self.lbl_5h_val.configure(
            text=f"{state.pct_5h:.0f}%", fg=color_for_quota(state.pct_5h),
        )
        draw_bar(self.bar_7d, state.pct_7d, color_for_quota(state.pct_7d))
        self.lbl_7d_val.configure(
            text=f"{state.pct_7d:.0f}%", fg=color_for_quota(state.pct_7d),
        )
        self.lbl_reset.configure(text=format_reset(state.reset_5h))
        self.lbl_reset_7d.configure(
            text=format_reset(state.reset_7d, include_date=True),
        )

        # Status
        if state.pct_5h >= cfg.quota_alarm_pct or state.status_5h == "rejected":
            self.lbl_status.configure(text=t("status_alarm"), fg=C_RED)
        elif state.pct_5h >= cfg.quota_warn_pct:
            self.lbl_status.configure(text=t("status_warn"), fg=C_YELLOW)
        else:
            self.lbl_status.configure(text=t("status_ok"), fg=C_GREEN)

        # Cache
        if state.cache_ratios:
            latest = state.cache_ratios[-1].get("ratio", 0)
            avg = state.avg_cache_ratio or latest
            self.lbl_cache.configure(
                text=f"{latest:.1%}", fg=color_for_cache(latest),
            )
            self.lbl_cache_avg.configure(text=f"{avg:.1%}")
        else:
            self.lbl_cache.configure(text="--", fg=C_DIM)
            self.lbl_cache_avg.configure(text="--")

        # Token details
        turn_since = format_since(state.updated_at) if state.updated_at else "--"
        self._update_usage_column(
            state.turn_usage, self.lbl_usage, self._turn_details,
            "1", turn_since,
        )
        self._update_usage_column(
            state.cumulative, self.lbl_cum_tokens, self._cum_details,
            f"{state.cumulative.turn_count:,}" if state.cumulative else "0",
            format_since(state.cumulative.started_at) if state.cumulative else "--",
        )

        # Burns + Countdown + Sparkline
        burn_5h = calc_burn(state.pct_5h, state.reset_5h, FIVE_HOURS)
        self._update_burn_labels(self._burn_5h, burn_5h, FIVE_HOURS)
        burn_7d = calc_burn(state.pct_7d, state.reset_7d, SEVEN_DAYS_HOURS)
        self._update_burn_labels(self._burn_7d, burn_7d, SEVEN_DAYS_HOURS)
        self._place_countdown()
        draw_countdown(
            self.canvas_cd, state,
            self._cd_size, self._cd_ring_d, self._cd_ring_w, self._scale,
        )
        draw_sparkline(self.canvas, state.cache_ratios, self._scale)

        # Footer
        if state.updated_at:
            self.lbl_updated.configure(
                text=f"Poll #{self._tick}  |  {state.updated_at[:19]}",
            )

    def _update_usage_column(
        self, usage: TokenUsage | None, summary_lbl: tk.Label,
        detail_labels: dict[str, tk.Label],
        turns_str: str, since_str: str,
    ) -> None:
        """Update a token usage column (turn or cumulative)."""
        if not usage:
            summary_lbl.configure(text="--")
            for lbl in detail_labels.values():
                lbl.configure(text="--")
            return
        cost = calc_cost(usage, self.prices)
        summary_lbl.configure(
            text=f"{usage.total_tokens:,} Token / ${cost:.4f}",
        )
        vals = {
            "turns": turns_str, "since": since_str,
            "input": f"{usage.input_tokens:,}",
            "output": f"{usage.output_tokens:,}",
            "cache_create": f"{usage.cache_creation_input_tokens:,}",
            "cache_read": f"{usage.cache_read_input_tokens:,}",
        }
        for key, lbl in detail_labels.items():
            lbl.configure(text=vals.get(key, "--"))

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    app = BudgetDashboard()
    app.run()


if __name__ == "__main__":
    main()
