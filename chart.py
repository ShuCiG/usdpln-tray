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
    ("1 hour",   3600,         1,     "%H:%M"),
    ("24 hours", 86400,        1800,  "%H:%M"),
    ("7 days",   7 * 86400,    14400, "%m-%d"),
    ("30 days",  30 * 86400,   86400, "%m-%d"),
    ("1 year",   365 * 86400,  86400, "%Y-%m"),
]
PERIODS_BY_LABEL = {p[0]: p for p in PERIODS}
CHART_TYPES = ["line", "scatter", "step"]


def load_data(db_path: str, period_seconds: int, bucket_seconds: int):
    """Return (xs, ys) for the given period and bucket size.

    Aggregates by integer-dividing ``ts`` into buckets and averaging.
    bucket_seconds=1 yields the raw samples unchanged.
    """
    since = int(time.time()) - period_seconds
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT (ts / ?) * ? AS bucket_ts, AVG(rate) "
            "FROM rates WHERE ts >= ? "
            "GROUP BY bucket_ts ORDER BY bucket_ts",
            (bucket_seconds, bucket_seconds, since),
        ).fetchall()
    xs = [datetime.fromtimestamp(r[0]) for r in rows]
    ys = [r[1] for r in rows]
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

    # Controls row
    controls = ttk.Frame(root, padding=(8, 6))
    controls.pack(side=tk.TOP, fill=tk.X)

    ttk.Label(controls, text="Period:").pack(side=tk.LEFT)
    period_var = tk.StringVar(value="24 hours")
    ttk.Combobox(
        controls, textvariable=period_var,
        values=[p[0] for p in PERIODS],
        state="readonly", width=10,
    ).pack(side=tk.LEFT, padx=(4, 16))

    ttk.Label(controls, text="Type:").pack(side=tk.LEFT)
    type_var = tk.StringVar(value="line")
    ttk.Combobox(
        controls, textvariable=type_var,
        values=CHART_TYPES,
        state="readonly", width=8,
    ).pack(side=tk.LEFT, padx=4)

    # Figure
    fig = Figure(figsize=(8, 4.5), dpi=100)
    ax = fig.add_subplot(111)
    canvas = FigureCanvasTkAgg(fig, master=root)
    canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    NavigationToolbar2Tk(canvas, root).update()

    def redraw(*_):
        ax.clear()
        label, period_s, bucket_s, fmt = PERIODS_BY_LABEL[period_var.get()]
        chart_type = type_var.get()
        xs, ys = load_data(db_path, period_s, bucket_s)

        if not xs:
            ax.text(
                0.5, 0.5, "No data in this range",
                transform=ax.transAxes, ha="center", va="center",
                color="gray",
            )
        else:
            if chart_type == "scatter":
                ax.scatter(xs, ys, s=14)
            elif chart_type == "step":
                ax.step(xs, ys, where="post", linewidth=1.5)
            else:  # line
                ax.plot(xs, ys, marker="o", linewidth=1.5, markersize=3)
            ax.xaxis.set_major_formatter(mdates.DateFormatter(fmt))
            fig.autofmt_xdate()

        ax.set_title(f"USD/PLN - last {label}  ({len(xs)} points)")
        ax.set_ylabel("PLN per USD")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        canvas.draw_idle()

    period_var.trace_add("write", redraw)
    type_var.trace_add("write", redraw)
    redraw()
    root.mainloop()


if __name__ == "__main__":
    main()
