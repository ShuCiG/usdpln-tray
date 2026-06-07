#!/usr/bin/env python3
"""USD/PLN rate-history chart window.

Standalone Tk window that reads ``rates.db`` and plots the rate over a chosen
period. Spawned as a subprocess from the tray app, but runnable on its own.
"""

import argparse
import os
import sqlite3
import sys
import time
import tkinter as tk
from datetime import datetime
from tkinter import ttk

import matplotlib

matplotlib.use("TkAgg")
import matplotlib.dates as mdates
from matplotlib.backends.backend_tkagg import (
    FigureCanvasTkAgg,
    NavigationToolbar2Tk,
)
from matplotlib.figure import Figure

def _base_dir() -> str:
    """Directory next to the running script or frozen .exe."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


SCRIPT_DIR = _base_dir()
DEFAULT_DB = os.environ.get("USDPLN_DB_PATH", os.path.join(SCRIPT_DIR, "rates.db"))

# (label, period_seconds, bucket_seconds, x-axis fmt)
PERIODS = [
    ("1 hour",   3600,         60,    "%H:%M"),
    ("24 hours", 86400,        1800,  "%H:%M"),
    ("7 days",   7 * 86400,    14400, "%m-%d"),
    ("30 days",  30 * 86400,   86400, "%m-%d"),
    ("1 year",   365 * 86400,  86400, "%Y-%m"),
]
PERIODS_BY_LABEL = {p[0]: p for p in PERIODS}
CHART_TYPES = ["line", "scatter", "step"]

# Stocks-style palette — kept in lockstep with tooltip.py so the chart and
# the popup widget read as one design.
BG_COLOR = "#2a2a2c"
LABEL_COLOR = "#b0b0b0"
GRID_COLOR = "#3a3a3c"
UP_COLOR = "#30d158"
DOWN_COLOR = "#ff453a"


def _style_axes(ax) -> None:
    """Recolor an Axes for the dark Stocks-style palette."""
    ax.set_facecolor(BG_COLOR)
    for spine in ax.spines.values():
        spine.set_color(GRID_COLOR)
    ax.tick_params(colors=LABEL_COLOR, labelsize=8, length=0)
    ax.yaxis.label.set_color(LABEL_COLOR)
    ax.xaxis.label.set_color(LABEL_COLOR)
    ax.title.set_color(LABEL_COLOR)


def load_data(db_path: str, period_seconds: int, bucket_seconds: int):
    """Return (xs, ys) for the requested period with weekend / outage gaps
    forward-filled from the last known rate.

    Aggregates by integer-dividing ``ts`` into buckets and averaging, then
    iterates every bucket between ``since`` and ``now`` carrying the last
    observed value across empty buckets. Without this the chart would draw a
    flat line between two distant points across a weekend, or — in this
    user's case — a single dot when only one Friday close fell in the window.
    Forward-fill seeds from the most recent sample BEFORE ``since`` so the
    series starts on bucket #1, not on whenever the first real data point
    inside the window happens to land.
    """
    now = int(time.time())
    since = now - period_seconds
    with sqlite3.connect(db_path) as conn:
        seed_row = conn.execute(
            "SELECT rate FROM rates WHERE ts < ? ORDER BY ts DESC LIMIT 1",
            (since,),
        ).fetchone()
        rows = conn.execute(
            "SELECT (ts / ?) * ? AS bucket_ts, AVG(rate) "
            "FROM rates WHERE ts >= ? AND ts <= ? "
            "GROUP BY bucket_ts ORDER BY bucket_ts",
            (bucket_seconds, bucket_seconds, since, now),
        ).fetchall()

    by_bucket = {int(b): v for b, v in rows}
    first_bucket = (since // bucket_seconds) * bucket_seconds
    last_bucket = (now // bucket_seconds) * bucket_seconds

    carry: float | None = seed_row[0] if seed_row else None
    xs: list[datetime] = []
    ys: list[float] = []
    for b in range(first_bucket, last_bucket + 1, bucket_seconds):
        if b in by_bucket:
            carry = by_bucket[b]
        if carry is None:
            continue  # no data anywhere yet — skip until first real value
        xs.append(datetime.fromtimestamp(b))
        ys.append(carry)
    return xs, ys


def main(db_path: str | None = None) -> None:
    """Open the chart window.

    ``db_path`` is honoured when called programmatically (e.g. from
    ``tray.py --chart`` inside the PyInstaller bundle). When None, argparse
    is used to read ``--db`` from ``sys.argv``.
    """
    if db_path is None:
        parser = argparse.ArgumentParser(description="USD/PLN rate history chart.")
        parser.add_argument(
            "--db", default=DEFAULT_DB,
            help="path to rates.db (default: alongside chart.py)",
        )
        # In a frozen bundle, tray.exe re-launches itself with --chart;
        # ignore that flag if it slipped into argv.
        parser.add_argument("--chart", action="store_true", help=argparse.SUPPRESS)
        args = parser.parse_args()
        db_path = args.db

    if not os.path.exists(db_path):
        print(f"[chart] DB not found: {db_path}")
        return

    root = tk.Tk()
    root.title("USD/PLN - rate history")
    root.geometry("900x550")
    root.configure(bg=BG_COLOR)

    # ttk widgets are themed via the global Style — give the combobox row
    # the same dark surface as the figure so there's no light strip on top.
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("Dark.TFrame", background=BG_COLOR)
    style.configure("Dark.TLabel", background=BG_COLOR, foreground=LABEL_COLOR)
    style.configure(
        "Dark.TCombobox",
        fieldbackground=BG_COLOR, background=BG_COLOR,
        foreground="#ffffff", arrowcolor=LABEL_COLOR,
    )

    controls = ttk.Frame(root, padding=(10, 8), style="Dark.TFrame")
    controls.pack(side=tk.TOP, fill=tk.X)

    ttk.Label(controls, text="Period:", style="Dark.TLabel").pack(side=tk.LEFT)
    period_var = tk.StringVar(value="24 hours")
    ttk.Combobox(
        controls, textvariable=period_var,
        values=[p[0] for p in PERIODS],
        state="readonly", width=10, style="Dark.TCombobox",
    ).pack(side=tk.LEFT, padx=(4, 16))

    ttk.Label(controls, text="Type:", style="Dark.TLabel").pack(side=tk.LEFT)
    type_var = tk.StringVar(value="line")
    ttk.Combobox(
        controls, textvariable=type_var,
        values=CHART_TYPES,
        state="readonly", width=8, style="Dark.TCombobox",
    ).pack(side=tk.LEFT, padx=4)

    # Figure
    fig = Figure(figsize=(8, 4.5), dpi=100, facecolor=BG_COLOR)
    ax = fig.add_subplot(111)
    canvas = FigureCanvasTkAgg(fig, master=root)
    canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    toolbar = NavigationToolbar2Tk(canvas, root)
    toolbar.config(background=BG_COLOR)
    # Hide nav buttons that read as broken on a dark canvas (Back/Forward
    # carry a disabled-state PNG alpha that shows the checker pattern, and
    # Subplots is the kind of dialog noone using a quote chart will reach for).
    for name in ("Back", "Forward", "Subplots"):
        btn = getattr(toolbar, "_buttons", {}).get(name)
        if btn is not None:
            btn.pack_forget()
    for child in toolbar.winfo_children():
        try:
            child.config(background=BG_COLOR, borderwidth=0, highlightbackground=BG_COLOR)
        except tk.TclError:
            pass
    toolbar.update()

    def redraw(*_):
        ax.clear()
        label, period_s, bucket_s, fmt = PERIODS_BY_LABEL[period_var.get()]
        chart_type = type_var.get()
        xs, ys = load_data(db_path, period_s, bucket_s)

        _style_axes(ax)

        if not xs:
            ax.text(
                0.5, 0.5, "No data in this range",
                transform=ax.transAxes, ha="center", va="center",
                color=LABEL_COLOR,
            )
        else:
            # Accent follows total move across the visible window, like the
            # tooltip sparkline does against chartPreviousClose.
            accent = UP_COLOR if ys[-1] >= ys[0] else DOWN_COLOR

            if chart_type == "scatter":
                ax.scatter(xs, ys, s=10, color=accent)
            elif chart_type == "step":
                ax.step(xs, ys, where="post", linewidth=1.5, color=accent)
            else:  # line — no markers, dense forward-filled series reads as a curve
                ax.plot(xs, ys, linewidth=1.5, color=accent)

            # Dashed reference at the window's starting value — same idea as
            # the tooltip's prev_close line: visual "above means up".
            ax.axhline(ys[0], color=accent, linestyle=(0, (2, 3)), linewidth=1, alpha=0.7)

            ax.xaxis.set_major_formatter(mdates.DateFormatter(fmt))
            fig.autofmt_xdate()
            # Pin x-axis to the full requested period so a sparse series
            # doesn't auto-zoom into a 30-minute window.
            now_dt = datetime.fromtimestamp(int(time.time()))
            since_dt = datetime.fromtimestamp(int(time.time()) - period_s)
            ax.set_xlim(since_dt, now_dt)

        ax.set_title(f"USD/PLN - last {label}  ({len(xs)} points)")
        ax.grid(True, color=GRID_COLOR, alpha=0.5, linewidth=0.5)
        fig.tight_layout()
        canvas.draw_idle()

    period_var.trace_add("write", redraw)
    type_var.trace_add("write", redraw)
    redraw()
    root.mainloop()


if __name__ == "__main__":
    main()
