"""Reusable widget drawing functions for BudMon dashboard."""

from __future__ import annotations

from datetime import datetime, timezone

try:
    import tkinter as tk
except ImportError:
    raise SystemExit("tkinter not available.")

from budmon.config import cfg
from budmon.data import calc_burn
from budmon.i18n import t
from budmon.models import (
    BURN_ROWS,
    C_BAR_BG,
    C_BG,
    C_CYAN,
    C_DIM,
    C_FG,
    C_GREEN,
    C_RED,
    C_YELLOW,
    CANVAS_BAR_FALLBACK_H,
    CANVAS_BAR_FALLBACK_W,
    CANVAS_BAR_HEIGHT,
    CANVAS_SPARKLINE_FALLBACK_W,
    CANVAS_SPARKLINE_HEIGHT,
    CD_COUNTDOWN_WARN_SEC,
    DETAIL_ROWS,
    FIVE_HOURS,
    FONT_SIZE_BAR_VALUE,
    FONT_SIZE_COUNTDOWN,
    FONT_SIZE_COUNTDOWN_LABEL,
    FONT_SIZE_NORMAL,
    FONT_SIZE_SMALL,
    FONT_SIZE_STATUS,
    LABEL_WIDTH,
    PAD_X,
    SECONDS_PER_HOUR,
    SPARKLINE_MARGIN,
    SPARKLINE_MAX_POINTS,
    QuotaState,
    color_for_cache,
    scaled_font,
)
from typing import Any


def draw_bar(canvas: tk.Canvas, pct: float, color: str) -> None:
    """Draw progress bar with threshold markers."""
    canvas.delete("all")
    w = canvas.winfo_width() or CANVAS_BAR_FALLBACK_W
    h = canvas.winfo_height() or CANVAS_BAR_FALLBACK_H
    fill_w = max(0, min(w, int(w * pct / 100)))
    if fill_w > 0:
        canvas.create_rectangle(0, 0, fill_w, h, fill=color, outline="")
    for threshold, marker_color in [
        (cfg.quota_warn_pct, C_YELLOW), (cfg.quota_alarm_pct, C_RED),
    ]:
        x = int(w * threshold / 100)
        canvas.create_line(x, 0, x, h, fill=marker_color, width=1)


def draw_sparkline(
    canvas: tk.Canvas, ratios: list[dict[str, Any]], scale: float,
) -> None:
    """Draw cache ratio sparkline on canvas."""
    canvas.delete("all")
    if len(ratios) < 2:
        return

    w = canvas.winfo_width() or CANVAS_SPARKLINE_FALLBACK_W
    h = canvas.winfo_height() or int(CANVAS_SPARKLINE_HEIGHT * scale)
    margin = SPARKLINE_MARGIN
    plot_h = h - 2 * margin

    n = min(len(ratios), SPARKLINE_MAX_POINTS)
    data = ratios[-n:]
    step = (w - 2 * margin) / max(1, n - 1)

    y_warn = margin + plot_h * (1 - cfg.cache_warn_ratio)
    canvas.create_line(
        margin, y_warn, w - margin, y_warn, fill=C_DIM, dash=(2, 4),
    )

    points: list[tuple[float, float]] = []
    for i, entry in enumerate(data):
        x = margin + i * step
        ratio = entry.get("ratio", 0)
        y = margin + plot_h * (1 - max(0, min(1, ratio)))
        points.append((x, y))

    if len(points) >= 2:
        flat = [coord for p in points for coord in p]
        canvas.create_line(*flat, fill=C_GREEN, width=1.5, smooth=True)

    if points:
        lx, ly = points[-1]
        color = color_for_cache(data[-1].get("ratio", 0))
        canvas.create_oval(
            lx - 3, ly - 3, lx + 3, ly + 3, fill=color, outline="",
        )


def draw_countdown(
    canvas: tk.Canvas, state: QuotaState,
    cd_size: int, cd_ring_d: int, cd_ring_w: int,
    scale: float,
) -> None:
    """Draw circular countdown ring for 5h quota."""
    c = canvas
    c.delete("all")
    sz = cd_size
    rd = cd_ring_d
    rw = cd_ring_w
    r_pad = (sz - rd) // 2

    def _sf(
        size: int, weight: str = "",
    ) -> tuple[str, int] | tuple[str, int, str]:
        return scaled_font(scale, "monospace", size, weight)

    burn = calc_burn(state.pct_5h, state.reset_5h, FIVE_HOURS)

    if not state.reset_5h:
        c.create_text(
            sz // 2, sz // 2, text="--:--",
            font=_sf(FONT_SIZE_STATUS), fill=C_DIM,
        )
        return

    try:
        now = datetime.now(tz=timezone.utc)
        reset_time = datetime.fromtimestamp(
            int(state.reset_5h), tz=timezone.utc,
        )
        reset_sec = max(0, (reset_time - now).total_seconds())
    except (ValueError, OSError):
        return

    if burn.valid:
        ablauf_sec = burn.hours_left * SECONDS_PER_HOUR
    else:
        ablauf_sec = float("inf")

    if ablauf_sec < reset_sec:
        sec = int(ablauf_sec)
        label = t("cd_ablauf")
        color = C_RED if sec < CD_COUNTDOWN_WARN_SEC else C_YELLOW
    else:
        sec = int(reset_sec)
        label = t("cd_reset")
        color = C_GREEN

    total_window = FIVE_HOURS * SECONDS_PER_HOUR
    fraction = min(1.0, max(0.0, sec / total_window))
    extent = fraction * 360

    cx, cy = sz // 2, sz // 2

    c.create_oval(r_pad, r_pad, r_pad + rd, r_pad + rd,
                   fill=C_BAR_BG, outline="")
    if extent > 0:
        c.create_arc(r_pad, r_pad, r_pad + rd, r_pad + rd,
                      start=90, extent=extent, fill=color, outline="")
    c.create_oval(r_pad + rw, r_pad + rw, r_pad + rd - rw, r_pad + rd - rw,
                   fill=C_BG, outline="")

    std = sec // SECONDS_PER_HOUR
    mi = (sec % SECONDS_PER_HOUR) // 60
    sek = sec % 60
    time_str = f"{std}:{mi:02d}:{sek:02d}"
    txt_id = c.create_text(
        cx, cy, text=time_str,
        font=_sf(FONT_SIZE_COUNTDOWN, "bold"), fill=color,
    )
    bbox = c.bbox(txt_id)
    if bbox:
        c.create_rectangle(
            bbox[0] - 1, bbox[1] - 1, bbox[2] + 1, bbox[3] + 1,
            fill="#000000", outline="",
        )
    c.create_text(
        cx, cy, text=time_str,
        font=_sf(FONT_SIZE_COUNTDOWN, "bold"), fill=color,
    )
    c.create_text(
        cx, cy + int(18 * scale), text=label,
        font=_sf(FONT_SIZE_COUNTDOWN_LABEL), fill=C_DIM,
    )


# ---------------------------------------------------------------------------
# Builder functions (create tk widgets, return references)
# ---------------------------------------------------------------------------

def _font(scale: float, size: int = FONT_SIZE_NORMAL, weight: str = "") -> tuple:  # type: ignore[type-arg]
    """Scaled font shortcut."""
    return scaled_font(scale, "monospace", size, weight)


def make_bar_row(
    parent: tk.Misc, scale: float,
    label: str,
) -> tuple[tk.Frame, tk.Label, tk.Canvas, tk.Label]:
    """Create a row with label + progress bar + percent value."""
    px = max(1, int(PAD_X * scale))
    row_py = max(1, int(1 * scale))
    frame = tk.Frame(parent, bg=C_BG)
    frame.pack(fill="x", padx=px, pady=row_py)
    lbl = tk.Label(
        frame, text=label, font=_font(scale),
        bg=C_BG, fg=C_DIM, width=LABEL_WIDTH, anchor="w",
    )
    lbl.pack(side="left")
    val = tk.Label(
        frame, text="--", font=_font(scale, FONT_SIZE_BAR_VALUE, "bold"),
        bg=C_BG, fg=C_FG, anchor="w",
    )
    val.pack(side="right")
    bar = tk.Canvas(
        frame, height=int(CANVAS_BAR_HEIGHT * scale), bg=C_BAR_BG,
        highlightthickness=0, bd=0,
    )
    bar.pack(side="left", padx=(int(4 * scale), int(4 * scale)),
             fill="x", expand=True)
    return frame, lbl, bar, val


def make_burn_rows(
    parent: tk.Misc, scale: float,
) -> dict[str, tk.Label]:
    """Create burn-rate detail rows."""
    px = max(1, int(PAD_X * scale))
    row_py = max(1, int(1 * scale))
    labels: dict[str, tk.Label] = {}
    for display_name, key in BURN_ROWS:
        row = tk.Frame(parent, bg=C_BG)
        row.pack(fill="x", padx=px, pady=row_py)
        lbl_color = C_CYAN if key == "empty" else C_DIM
        tk.Label(
            row, text=t(display_name), font=_font(scale),
            bg=C_BG, fg=lbl_color, width=LABEL_WIDTH, anchor="w",
        ).pack(side="left")
        lbl = tk.Label(
            row, text="--", font=_font(scale, FONT_SIZE_NORMAL, "bold"),
            bg=C_BG, fg=lbl_color, anchor="w",
        )
        lbl.pack(side="left", padx=(int(4 * scale), 0))
        labels[key] = lbl
    return labels


def make_reset_row(parent: tk.Misc, scale: float) -> tk.Label:
    """Create a reset-time row."""
    px = max(1, int(PAD_X * scale))
    row_py = max(1, int(1 * scale))
    row = tk.Frame(parent, bg=C_BG)
    row.pack(fill="x", padx=px, pady=row_py)
    tk.Label(
        row, text=t("label_reset"), font=_font(scale),
        bg=C_BG, fg=C_DIM, width=LABEL_WIDTH, anchor="w",
    ).pack(side="left")
    lbl = tk.Label(
        row, text="--", font=_font(scale), bg=C_BG, fg=C_FG, anchor="w",
    )
    lbl.pack(side="left", padx=(int(4 * scale), 0))
    return lbl


def make_detail_column(
    parent: tk.Frame, scale: float, title: str,
) -> tuple[tk.Label, dict[str, tk.Label]]:
    """Create a token detail column (turn or cumulative)."""
    col = tk.Frame(parent, bg=C_BG)
    tk.Label(
        col, text=title, font=_font(scale, FONT_SIZE_NORMAL, "bold"),
        bg=C_BG, fg=C_DIM, anchor="w",
    ).pack(anchor="w")
    summary_lbl = tk.Label(
        col, text="--", font=_font(scale), bg=C_BG, fg=C_FG, anchor="w",
    )
    summary_lbl.pack(anchor="w", pady=(0, 1))
    detail_labels: dict[str, tk.Label] = {}
    for display_name, key in DETAIL_ROWS:
        row = tk.Frame(col, bg=C_BG)
        row.pack(fill="x")
        tk.Label(
            row, text=t(display_name), font=_font(scale, FONT_SIZE_SMALL),
            bg=C_BG, fg=C_DIM, width=9, anchor="w",
        ).pack(side="left")
        lbl = tk.Label(
            row, text="--", font=_font(scale, FONT_SIZE_SMALL),
            bg=C_BG, fg=C_FG, anchor="w",
        )
        lbl.pack(side="left", padx=(int(4 * scale), 0))
        detail_labels[key] = lbl
    return summary_lbl, detail_labels
