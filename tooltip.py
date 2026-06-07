#!/usr/bin/env python3
"""USD/PLN tray tooltip — borderless iOS-Stocks-style popup card.

Fetches the live USD/PLN quote and the intraday minute series from the same
Yahoo Finance endpoint used by ``tray.py``, then renders a small card with
symbol, current price, daily change, OHLC and a sparkline. Designed to be
spawned as a subprocess from the tray icon's left-click action so its Tk
main loop stays out of pystray's event loop.
"""

import sys
import tkinter as tk
from datetime import datetime

import requests

# Reuse the endpoint constants so the tooltip and the poller stay in lockstep.
from tray import YAHOO_URL, YAHOO_HEADERS

CARD_W = 380
CARD_H = 160
BG_COLOR = "#2a2a2c"
LABEL_COLOR = "#b0b0b0"
VALUE_COLOR = "#ffffff"
UP_COLOR = "#30d158"
DOWN_COLOR = "#ff453a"


def fetch_data() -> dict | None:
    """Return the parsed payload for the card, or None on failure."""
    try:
        r = requests.get(YAHOO_URL, headers=YAHOO_HEADERS, timeout=10)
        r.raise_for_status()
        result = r.json()["chart"]["result"][0]
        meta = result["meta"]
        timestamps = result.get("timestamp") or []
        closes_raw = result["indicators"]["quote"][0].get("close") or []
        # Drop nulls — Yahoo emits one per in-progress minute.
        clean = [(t, c) for t, c in zip(timestamps, closes_raw) if c is not None]
        if not clean:
            return None
        ts_clean, close_clean = zip(*clean)
        return {
            "symbol": meta.get("symbol", "USDPLN=X"),
            "current": float(meta["regularMarketPrice"]),
            "high": float(meta["regularMarketDayHigh"]),
            "low": float(meta["regularMarketDayLow"]),
            "prev_close": float(meta["chartPreviousClose"]),
            # Yahoo doesn't expose regularMarketOpen for FX — first tick of the
            # series is today's open.
            "open": float(close_clean[0]),
            "ts": list(ts_clean),
            "closes": list(close_clean),
        }
    except Exception as e:
        print(f"[tooltip] fetch failed: {e}", file=sys.stderr)
        return None


def _draw_sparkline(canvas: tk.Canvas, ts: list[int], closes: list[float],
                    prev_close: float, accent: str, w: int, h: int) -> None:
    if len(closes) < 2:
        return
    if len(closes) > 120:
        step = len(closes) // 120
        ts = ts[::step]
        closes = closes[::step]

    pad_l, pad_r, pad_t, pad_b = 4, 4, 4, 14
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b

    y_min = min(min(closes), prev_close)
    y_max = max(max(closes), prev_close)
    y_range = (y_max - y_min) or 1e-6

    def y_for(v: float) -> float:
        return pad_t + (1 - (v - y_min) / y_range) * plot_h

    # Dashed reference at previous close.
    ref_y = y_for(prev_close)
    canvas.create_line(pad_l, ref_y, pad_l + plot_w, ref_y,
                       fill=accent, dash=(2, 3), width=1)

    # Sparkline polyline.
    points: list[float] = []
    n = len(closes)
    for i, v in enumerate(closes):
        x = pad_l + (i / (n - 1)) * plot_w
        points.extend([x, y_for(v)])
    canvas.create_line(*points, fill=accent, width=1.5)

    # Three time labels: first / middle / last.
    label_y = h - 6
    for idx in (0, n // 2, n - 1):
        x = pad_l + (idx / (n - 1)) * plot_w if n > 1 else pad_l
        # fromtimestamp without tz returns local time — what the user reads.
        label = datetime.fromtimestamp(ts[idx]).strftime("%H")
        canvas.create_text(x, label_y, text=label, fill=LABEL_COLOR,
                           font=("Segoe UI", 7))


def _render_card(root: tk.Tk, data: dict) -> None:
    change = data["current"] - data["prev_close"]
    change_pct = (change / data["prev_close"]) * 100
    up = change >= 0
    accent = UP_COLOR if up else DOWN_COLOR
    arrow = "▲" if up else "▼"
    sign = "+" if up else ""

    outer = tk.Frame(root, bg=BG_COLOR, padx=14, pady=10)
    outer.pack(fill=tk.BOTH, expand=True)

    left = tk.Frame(outer, bg=BG_COLOR)
    left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    right = tk.Frame(outer, bg=BG_COLOR)
    right.pack(side=tk.RIGHT, fill=tk.BOTH)

    # --- left column ---------------------------------------------------------
    sym_row = tk.Frame(left, bg=BG_COLOR)
    sym_row.pack(anchor="w")
    tk.Label(sym_row, text=arrow, fg=accent, bg=BG_COLOR,
             font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)
    tk.Label(sym_row, text=" " + data["symbol"], fg=VALUE_COLOR, bg=BG_COLOR,
             font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)

    tk.Label(left, text="USD/PLN", fg=LABEL_COLOR, bg=BG_COLOR,
             font=("Segoe UI", 9)).pack(anchor="w")

    def ohlc_row(label: str, value: float) -> None:
        row = tk.Frame(left, bg=BG_COLOR)
        row.pack(anchor="w", pady=(2, 0))
        tk.Label(row, text=label, fg=LABEL_COLOR, bg=BG_COLOR,
                 font=("Segoe UI", 8), width=6, anchor="w").pack(side=tk.LEFT)
        tk.Label(row, text=f"{value:.4f}", fg=VALUE_COLOR, bg=BG_COLOR,
                 font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT)

    ohlc_row("Open", data["open"])
    ohlc_row("High", data["high"])
    ohlc_row("Low", data["low"])

    tk.Label(left, text=f"{data['current']:.4f}", fg=VALUE_COLOR, bg=BG_COLOR,
             font=("Segoe UI", 22, "bold")).pack(anchor="w", pady=(6, 0))

    # --- right column --------------------------------------------------------
    tk.Label(right, text=f"{sign}{change:.4f}", fg=accent, bg=BG_COLOR,
             font=("Segoe UI", 11, "bold")).pack(anchor="e")
    tk.Label(right, text=f"{sign}{change_pct:.2f}%", fg=accent, bg=BG_COLOR,
             font=("Segoe UI", 11, "bold")).pack(anchor="e")

    spark_w, spark_h = 180, 90
    canvas = tk.Canvas(right, width=spark_w, height=spark_h,
                       bg=BG_COLOR, highlightthickness=0)
    canvas.pack(anchor="e", pady=(8, 0))
    _draw_sparkline(canvas, data["ts"], data["closes"],
                    data["prev_close"], accent, spark_w, spark_h)


def _render_error(root: tk.Tk, message: str) -> None:
    frame = tk.Frame(root, bg=BG_COLOR, padx=14, pady=10)
    frame.pack(fill=tk.BOTH, expand=True)
    tk.Label(frame, text="USD/PLN", fg=VALUE_COLOR, bg=BG_COLOR,
             font=("Segoe UI", 11, "bold")).pack(anchor="w")
    tk.Label(frame, text=message, fg=DOWN_COLOR, bg=BG_COLOR,
             font=("Segoe UI", 9), wraplength=CARD_W - 30,
             justify="left").pack(anchor="w", pady=(8, 0))


def main() -> None:
    """Show the tooltip card and block until dismissed."""
    data = fetch_data()

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(bg=BG_COLOR)

    if data is not None:
        _render_card(root, data)
    else:
        _render_error(root, "Failed to fetch quote. Check connection and try again.")

    root.update_idletasks()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    # 20px right margin, 60px above the taskbar.
    x = sw - CARD_W - 20
    y = sh - CARD_H - 60
    root.geometry(f"{CARD_W}x{CARD_H}+{x}+{y}")

    def dismiss(_event=None) -> None:
        try:
            root.destroy()
        except Exception:
            pass

    root.bind("<FocusOut>", dismiss)
    root.bind("<Escape>", dismiss)

    root.focus_force()
    root.mainloop()


if __name__ == "__main__":
    main()
