#!/usr/bin/env python3
"""USD/PLN monitor — system tray app with rate alerts.

Polls Yahoo Finance for the live USD/PLN spot rate, logs every reading to a
local SQLite database, and raises desktop / email alerts on sharp moves or
threshold crossings. Runs either as a tray icon (default) or headless
(``--headless``) for terminal/background use.
"""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import notify

# pystray, Pillow, and matplotlib are only needed for the tray + chart UI on
# Windows. They are imported lazily inside run_tray() / make_icon_image() so
# that headless mode (e.g. inside a Linux Docker container) can run without
# those packages installed.

def _base_dir() -> str:
    """Return the directory next to the running script or frozen .exe."""
    if getattr(sys, "frozen", False):
        # Bundled by PyInstaller — sys.executable is usdpln-tray.exe
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


SCRIPT_DIR = _base_dir()
# Both paths can be overridden by env vars for container/Docker deployments.
DB_PATH = os.environ.get("USDPLN_DB_PATH", os.path.join(SCRIPT_DIR, "rates.db"))
CONFIG_PATH = os.environ.get(
    "USDPLN_CONFIG_PATH", os.path.join(SCRIPT_DIR, "config.json")
)
YAHOO_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/USDPLN%3DX"
    "?interval=1m&range=1d"
)
# Yahoo rejects the default python-requests UA with HTTP 429.
YAHOO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

DEFAULT_CONFIG = {
    "refresh_interval": 60,
    "alerts": {
        "spike_pct": 1.0,
        "spike_window_seconds": 3600,
        "threshold_high": None,
        "threshold_low": None,
    },
    "desktop_notifications": True,
    "email": {
        "enabled": False,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 465,
        "username": "",
        "password": "",
        "from_addr": "",
        "to_addr": "",
    },
}

_http_session: requests.Session | None = None


def _get_session() -> requests.Session:
    global _http_session
    if _http_session is None:
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        session.mount("https://", HTTPAdapter(max_retries=retry))
        _http_session = session
    return _http_session


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

def deep_merge(base: dict, override: dict) -> dict:
    """Return a copy of base with override merged in, recursing into dicts."""
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: str) -> dict:
    """Load config JSON merged over defaults; fall back to defaults if absent."""
    if not os.path.exists(path):
        print(f"[config] {path} not found; using defaults")
        return deep_merge(DEFAULT_CONFIG, {})
    try:
        with open(path, encoding="utf-8") as f:
            user_cfg = json.load(f)
        return deep_merge(DEFAULT_CONFIG, user_cfg)
    except Exception as e:
        print(f"[config] failed to read {path}: {e}; using defaults")
        return deep_merge(DEFAULT_CONFIG, {})


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------

def init_db() -> None:
    """Create the rates and alerts tables if missing."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS rates ("
            "ts INTEGER PRIMARY KEY, rate REAL NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS alerts ("
            "ts INTEGER NOT NULL, kind TEXT NOT NULL, message TEXT NOT NULL)"
        )


def save_rate(rate: float) -> None:
    """Store one rate sample keyed by unix timestamp."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO rates (ts, rate) VALUES (?, ?)",
            (int(time.time()), rate),
        )


def log_alert(kind: str, message: str) -> None:
    """Record a fired alert in the alerts table."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO alerts (ts, kind, message) VALUES (?, ?, ?)",
                (int(time.time()), kind, message),
            )
    except Exception:
        pass  # DB write failure must not break the loop


def last_known_rate() -> float | None:
    """Return the most recent stored rate, or None if the DB is empty."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT rate FROM rates ORDER BY ts DESC LIMIT 1"
            ).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def last_known_rate_ts() -> int | None:
    """Return the timestamp of the most recent stored rate, or None."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT ts FROM rates ORDER BY ts DESC LIMIT 1"
            ).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def baseline_rate(window_seconds: int) -> float | None:
    """Most recent stored rate at or before ``now - window_seconds``.

    Used as the comparison anchor for spike alerts so that the threshold
    has a fixed time-window meaning (e.g. 1% per hour) independent of how
    often we poll.
    """
    target_ts = int(time.time()) - window_seconds
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT rate FROM rates WHERE ts <= ? ORDER BY ts DESC LIMIT 1",
                (target_ts,),
            ).fetchone()
        return row[0] if row else None
    except Exception:
        return None


# --------------------------------------------------------------------------
# Rate fetching and alerting
# --------------------------------------------------------------------------

def fetch_rate() -> tuple[float | None, str]:
    """Fetch the current USD/PLN rate. Returns (rate, display_label).

    rate is None on failure; the rate is saved to the DB on success.
    Over weekends and outside trading hours Yahoo keeps returning the last
    close as ``regularMarketPrice``, so the rate will just plateau — there is
    no separate "market closed" signal to handle here.
    """
    try:
        r = _get_session().get(YAHOO_URL, headers=YAHOO_HEADERS, timeout=10)
        r.raise_for_status()
        meta = r.json()["chart"]["result"][0]["meta"]
        rate = float(meta["regularMarketPrice"])
        try:
            save_rate(rate)
        except Exception:
            pass  # DB write failure must not break the app
        return rate, f"USD/PLN: {rate:.4f}"
    except Exception as e:
        return None, f"USD/PLN: error ({e})"


def _format_window(seconds: int) -> str:
    """Human label for a spike-window duration (used in alert messages)."""
    if seconds >= 3600 and seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds >= 60 and seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def check_alerts(prev: float | None, baseline: float | None,
                  curr: float | None, config: dict,
                  skip_spike: bool = False) -> list:
    """Return a list of (kind, message) alerts for the new reading.

    Spike alerts compare ``curr`` against ``baseline`` (the rate from
    ~spike_window_seconds ago) so the threshold has a fixed time-window
    meaning regardless of poll rate. Threshold crossings compare against
    ``prev`` (the immediately preceding reading) so each crossing fires
    exactly once. ``skip_spike`` suppresses the spike check on the first
    poll after a long downtime, where ``baseline`` would otherwise be a
    stale value from before the gap.
    """
    alerts: list[tuple[str, str]] = []
    if curr is None:
        return alerts

    a = config["alerts"]
    if not skip_spike:
        spike_pct = a.get("spike_pct")
        if spike_pct and baseline is not None:
            pct = (curr - baseline) / baseline * 100
            if abs(pct) >= spike_pct:
                window_label = _format_window(a.get("spike_window_seconds", 3600))
                alerts.append((
                    "spike",
                    f"USD/PLN moved {pct:+.2f}% in {window_label} "
                    f"({baseline:.4f} -> {curr:.4f})",
                ))

    if prev is not None:
        high = a.get("threshold_high")
        if high is not None and prev < high <= curr:
            alerts.append(("high", f"USD/PLN rose above {high}: {curr:.4f}"))

        low = a.get("threshold_low")
        if low is not None and prev > low >= curr:
            alerts.append(("low", f"USD/PLN fell below {low}: {curr:.4f}"))

    return alerts


def dispatch_alerts(alerts: list, config: dict, headless: bool) -> None:
    """Log alerts and deliver them via toast (tray mode) and/or email."""
    messages = []
    for kind, message in alerts:
        log_alert(kind, message)
        messages.append(message)
        print(f"[alert] {message}")
    body = "\n".join(messages)

    if not headless and config["desktop_notifications"]:
        notify.send_toast("USD/PLN alert", body)

    email_cfg = config["email"]
    if email_cfg.get("enabled"):
        notify.send_email(email_cfg, "USD/PLN alert", body)


def process_reading(prev_rate: float | None, config: dict,
                     headless: bool, skip_spike: bool = False) -> tuple[float | None, str]:
    """Fetch a rate, check it against prev_rate + windowed baseline, and dispatch any alerts."""
    rate, label = fetch_rate()
    if rate is not None:
        window_s = config["alerts"].get("spike_window_seconds", 3600)
        baseline = baseline_rate(window_s)
        alerts = check_alerts(prev_rate, baseline, rate, config, skip_spike=skip_spike)
        if alerts:
            dispatch_alerts(alerts, config, headless)
    return rate, label


# --------------------------------------------------------------------------
# Tray icon
# --------------------------------------------------------------------------

def make_icon_image(text: str):
    """Render a large centered '$' into a 64x64 icon (PIL Image)."""
    from PIL import Image, ImageDraw, ImageFont

    size = 64
    img = Image.new("RGBA", (size, size), (30, 30, 30, 255))
    draw = ImageDraw.Draw(img)
    # Try to use a bold font sized to fill the icon; fall back to default
    try:
        if sys.platform == "win32":
            font_path = os.path.join(
                os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "arialbd.ttf"
            )
        else:
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        font = ImageFont.truetype(font_path, 52)
    except Exception:
        font = ImageFont.load_default()
    glyph = "$"
    # Center the glyph using its real bounding box
    left, top, right, bottom = draw.textbbox((0, 0), glyph, font=font)
    x = (size - (right - left)) / 2 - left
    y = (size - (bottom - top)) / 2 - top
    draw.text((x, y), glyph, fill=(50, 200, 50, 255), font=font)
    return img


_chart_proc: subprocess.Popen | None = None


def open_chart() -> None:
    """Spawn the chart UI in its own process so the Tk window stays off the pystray loop.

    In source mode this runs ``python chart.py``; in a PyInstaller bundle it
    re-launches the same .exe with the internal ``--chart`` flag so a single
    binary covers both modes. The handle is cached so repeated menu clicks
    do not stack chart windows.
    """
    global _chart_proc
    if _chart_proc is not None and _chart_proc.poll() is None:
        return  # already running
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if getattr(sys, "frozen", False):
        _chart_proc = subprocess.Popen(
            [sys.executable, "--chart"], creationflags=creationflags
        )
    else:
        chart_path = os.path.join(SCRIPT_DIR, "chart.py")
        _chart_proc = subprocess.Popen(
            [sys.executable, chart_path], creationflags=creationflags
        )


def run_tray(config: dict) -> None:
    """Run the app as a system tray icon."""
    import pystray

    init_db()
    prev_rate = last_known_rate()
    last_ts = last_known_rate_ts()
    skip_spike = last_ts is not None and (
        time.time() - last_ts > 1.5 * config["refresh_interval"]
    )
    rate_lock = threading.Lock()

    rate, label = process_reading(prev_rate, config, headless=False, skip_spike=skip_spike)
    if rate is not None:
        prev_rate = rate

    icon = pystray.Icon(
        name="usdpln",
        icon=make_icon_image(label),
        title=label,  # tooltip shown on hover
        menu=pystray.Menu(
            pystray.MenuItem(lambda item: icon.title, None, enabled=False),
            pystray.MenuItem("Rate chart", lambda icon, item: open_chart()),
            pystray.MenuItem("Refresh", lambda icon, item: refresh(icon)),
            pystray.MenuItem("Exit", lambda icon, item: icon.stop()),
        ),
    )

    def refresh(icon):
        nonlocal prev_rate
        with rate_lock:
            current_prev = prev_rate
        new_rate, new_label = process_reading(current_prev, config, headless=False)
        with rate_lock:
            if new_rate is not None:
                prev_rate = new_rate
        icon.title = new_label
        icon.icon = make_icon_image(new_label)

    def auto_refresh():
        while True:
            time.sleep(config["refresh_interval"])
            if not icon.visible:
                break
            refresh(icon)

    threading.Thread(target=auto_refresh, daemon=True).start()
    icon.run()


# --------------------------------------------------------------------------
# Headless mode
# --------------------------------------------------------------------------

def run_headless(config: dict) -> None:
    """Run the app without a tray icon — alerts are email-only."""
    init_db()
    # Line-buffer stdout so piped / Task Scheduler logs update per reading.
    sys.stdout.reconfigure(line_buffering=True)
    interval = config["refresh_interval"]
    prev_rate = last_known_rate()
    last_ts = last_known_rate_ts()
    skip_spike = last_ts is not None and (time.time() - last_ts > 1.5 * interval)
    print(f"[usdpln] headless mode - polling every {interval}s. Ctrl+C to stop.")
    try:
        while True:
            rate, label = process_reading(prev_rate, config, headless=True,
                                          skip_spike=skip_spike)
            skip_spike = False  # only skip on first poll after a long gap
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[usdpln] {stamp}  {label}")
            if rate is not None:
                prev_rate = rate
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[usdpln] stopped.")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="USD/PLN exchange rate monitor with alerts."
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="run without a tray icon; alerts are email-only",
    )
    parser.add_argument(
        "--config", default=CONFIG_PATH,
        help="path to the config JSON file (default: config.json)",
    )
    # Internal: used by the PyInstaller bundle to invoke the chart UI without
    # needing a separate executable. Hidden from --help.
    parser.add_argument("--chart", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.chart:
        import chart
        chart.main(db_path=DB_PATH)
        return

    config = load_config(args.config)
    if args.headless:
        run_headless(config)
    else:
        run_tray(config)


if __name__ == "__main__":
    main()
